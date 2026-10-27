"""A fixed probe set: the same held-out replies, scored at every milestone checkpoint.

The speaking gate scores each held-out exchange once, with whatever weights the
core had when it arrived, and the curriculum changes domain every 100 exchanges,
so a falling gate average mixes learning with easier topics. Here held-out
replies are drawn once and frozen (spread over the whole ledger, every mentor
voice represented), and each milestone checkpoint (organism.milestone<N>.npz,
kept every 1,000 steps by the console) is scored on all of them, whole reply,
through the gate's own scorer. A change between two rows is the same text read
by different weights. The set is never redrawn; every row carries its SHA-256
and the checkpoint's.

    python -m osiris_cli.probeset freeze [--size 100]        # once: draw the set from the ledger
    python -m osiris_cli.probeset score [CHECKPOINT.npz|live ...]   # unscored milestones, or these
    python -m osiris_cli.probeset show

Held-out replies are never trained on, by the live core or the batch trainer.
Files, in the living home: probe_set.json (the frozen set) and
probe_scores.jsonl (one row per checkpoint scored).
"""

from __future__ import annotations

import argparse
import glob
import json
import os
import re
import sys
import time
from collections import Counter
from typing import Callable, Dict, List, Optional, Sequence, Tuple

from osiris_cli import living, prepost

PROBE_SET = "probe_set.json"
PROBE_LOG = "probe_scores.jsonl"
PROBE_SIZE = 100
MIN_PER_VOICE = 5               # every mentor voice is represented, however rare
MIN_SET = living.GATE_WINDOW    # fewer scorable held-out replies than the gate needs is too few to freeze
RULE = ("held-out, learnable, non-core exchanges whose reply fills a scoring window (>= 8 bytes); per voice "
        f"min(count, {MIN_PER_VOICE}), the rest of the size in proportion to what each voice has left (largest "
        "remainder, ties by name); within a voice, evenly spaced by ledger index from the first to the last")
MILESTONE_RE = re.compile(r"organism\.milestone(\d+)\.npz$")


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


# ---------------------------------------------------------------------------
# Drawing the set
# ---------------------------------------------------------------------------

def candidates(rows: Sequence[dict]) -> List[dict]:
    """The exchanges the gate scores (train.rescore_chat's rule) whose reply fills at least one window."""
    return [r for r in rows if r.get("heldout") and r.get("learnable") and r.get("voice") != "core"
            and isinstance(r.get("index"), int) and len(r.get("reply", "").encode("utf-8", errors="ignore")) >= 8]


def spread(items: Sequence, k: int) -> list:
    """k of items, evenly spaced from the first to the last."""
    if k >= len(items):
        return list(items)
    if k <= 1:
        return list(items[:k])
    return [items[round(i * (len(items) - 1) / (k - 1))] for i in range(k)]


def quotas(counts: Dict[str, int], size: int) -> Dict[str, int]:
    """Items per voice: min(count, MIN_PER_VOICE) each, then the rest of size in proportion to what is left."""
    q = {v: min(n, MIN_PER_VOICE) for v, n in counts.items()}
    left = {v: counts[v] - q[v] for v in counts}
    room = min(size - sum(q.values()), sum(left.values()))
    if room > 0:
        share = {v: room * left[v] / sum(left.values()) for v in left}
        for v in share:
            q[v] += int(share[v])
        rest = room - sum(int(s) for s in share.values())
        for v in sorted(share, key=lambda v: (int(share[v]) - share[v], v))[:rest]:
            q[v] += 1
    return q


def select(rows: Sequence[dict], size: int = PROBE_SIZE) -> List[dict]:
    by_voice: Dict[str, List[dict]] = {}
    for r in sorted(candidates(rows), key=lambda r: r["index"]):
        by_voice.setdefault(r.get("voice") or "unknown", []).append(r)
    q = quotas({v: len(rs) for v, rs in by_voice.items()}, size)
    return sorted((r for v, rs in by_voice.items() for r in spread(rs, q[v])), key=lambda r: r["index"])


def set_path(home: str) -> str:
    return os.path.join(home, PROBE_SET)


def log_path(home: str) -> str:
    return os.path.join(home, PROBE_LOG)


def freeze(home: str, size: int = PROBE_SIZE) -> dict:
    """Draw the probe set from home's exchange ledger and write it. An existing set is never replaced."""
    from osiris_cli.probes import verify_chain
    path = set_path(home)
    if os.path.exists(path):
        raise FileExistsError(f"{path} is already frozen (sha256 {prepost.file_sha256(path)[:12]}); "
                              "a probe set is never redrawn")
    ledger = os.path.join(home, "exchanges.jsonl")
    rows = prepost.read_exchanges(ledger)
    items = select(rows, size)
    if len(items) < MIN_SET:
        raise ValueError(f"{len(items)} scorable held-out replies in {ledger}; a probe set needs {MIN_SET}")
    chain = verify_chain(ledger)
    body = {"created": _now(), "size": size, "rule": RULE,
            "ledger": {"path": os.path.abspath(ledger), "sha256": prepost.file_sha256(ledger), "rows": len(rows),
                       "head": chain.get("head"), "intact": chain.get("intact"),
                       "candidates": len(candidates(rows))},
            "items": [{"index": r["index"], "hash": r["hash"], "voice": r.get("voice"), "reply": r["reply"]}
                      for r in items]}
    with open(path, "x", encoding="utf-8") as f:
        json.dump(body, f, ensure_ascii=False, indent=1)
    return {"path": path, "sha256": prepost.file_sha256(path), "n": len(items),
            "by_voice": dict(Counter(it["voice"] for it in body["items"]))}


def load_set(home: str) -> Optional[Tuple[dict, str]]:
    """(the frozen set, its file's SHA-256), or None before one is frozen."""
    path = set_path(home)
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as f:
        return json.load(f), prepost.file_sha256(path)


# ---------------------------------------------------------------------------
# Scoring checkpoints
# ---------------------------------------------------------------------------

def read_log(home: str) -> List[dict]:
    try:
        with open(log_path(home), encoding="utf-8") as f:
            lines = f.read().splitlines()
    except OSError:
        return []
    rows = []
    for line in lines:
        try:
            rows.append(json.loads(line))
        except ValueError:
            continue   # a row cut short by a crash
    return rows


def current_rows(home: str, probe_sha: str) -> List[dict]:
    """Rows for this set by the current scorer, one per checkpoint (the last), in step order."""
    rows = {(r.get("checkpoint"), r.get("step")): r for r in read_log(home)
            if r.get("probe_set_sha256") == probe_sha and r.get("scorer") == living.SCORER}
    return sorted(rows.values(), key=lambda r: r["step"])


def milestones(organism_dir: str) -> List[Tuple[str, str]]:
    """(npz, json) of every complete milestone checkpoint, oldest first."""
    found = []
    for p in glob.glob(os.path.join(organism_dir, "organism.milestone*.npz")):
        m = MILESTONE_RE.search(p)
        if m and os.path.exists(p[:-4] + ".json"):
            found.append((int(m.group(1)), p, p[:-4] + ".json"))
    return [(p, j) for _, p, j in sorted(found)]


def checkpoint_step(meta: str) -> int:
    with open(meta, encoding="utf-8") as f:
        return int(json.load(f).get("step", 0))


def unscored(home: str, probe_sha: str, checkpoints: Sequence[Tuple[str, str]]) -> List[Tuple[str, str]]:
    done = {(r["checkpoint"], r["step"]) for r in current_rows(home, probe_sha)}
    return [(c, m) for c, m in checkpoints if (os.path.basename(c), checkpoint_step(m)) not in done]


def pending(home: str, organism_dir: str) -> List[Tuple[str, str]]:
    """Milestones the current scorer has not scored on the frozen set (none before a set is frozen)."""
    s = load_set(home)
    return unscored(home, s[1], milestones(organism_dir)) if s else []


def score_checkpoint(ckpt: str, meta: str, probe: dict, probe_sha: str) -> dict:
    """One log row: every probe reply scored, whole, by the weights in ckpt."""
    model, _, step = prepost.load_files(ckpt, meta)
    scorer = living.loaded_scorer()
    if scorer != living.SCORER:
        raise RuntimeError(f"the loaded osiris.nclm scores as version {scorer}, not {living.SCORER}: an older "
                           "copy of the model code (check PYTHONPATH)")
    span = prepost._console().ORGANISM_GEOMETRY["max_seq_len"]
    t0 = time.time()
    bpb = [living.model_bits_per_byte(model, it["reply"], span) for it in probe["items"]]
    by_voice: Dict[str, List[float]] = {}
    for it, b in zip(probe["items"], bpb):
        if b is not None:
            by_voice.setdefault(it["voice"], []).append(b)
    scored = [b for b in bpb if b is not None]
    return {"t": _now(), "checkpoint": os.path.basename(ckpt), "step": step,
            "checkpoint_sha256": prepost.file_sha256(ckpt), "probe_set_sha256": probe_sha, "scorer": scorer,
            "n": len(scored), "bpb": round(sum(scored) / len(scored), 4) if scored else None,
            "by_voice": {v: [len(bs), round(sum(bs) / len(bs), 4)] for v, bs in sorted(by_voice.items())},
            "items": [None if b is None else round(b, 4) for b in bpb], "seconds": round(time.time() - t0, 1)}


def record(home: str, row: dict) -> None:
    with open(log_path(home), "a", encoding="utf-8") as f:
        f.write(json.dumps(row) + "\n")


def describe(row: dict) -> str:
    voices = ", ".join(f"{v.split(':')[-1]} {m:.2f} ({n})" for v, (n, m) in row["by_voice"].items())
    return (f"step {row['step']:>6}  {row['bpb']:.3f} bits/byte on {row['n']} probe replies  "
            f"[{voices}]  {row['checkpoint']}")


def score(home: str, checkpoints: Sequence[Tuple[str, str]], log: Callable[[str], None] = lambda s: None
          ) -> List[dict]:
    """Score the checkpoints not yet scored on the frozen set, oldest step first, and log each row."""
    s = load_set(home)
    if s is None:
        return []
    rows = []
    for ckpt, meta in sorted(unscored(home, s[1], checkpoints), key=lambda cm: checkpoint_step(cm[1])):
        row = score_checkpoint(ckpt, meta, *s)
        record(home, row)
        log(describe(row))
        rows.append(row)
    return rows


def score_pending(home: str, organism_dir: str, log: Callable[[str], None] = lambda s: None) -> List[dict]:
    return score(home, milestones(organism_dir), log)


def status_line(home: str) -> Optional[str]:
    s = load_set(home)
    if s is None:
        return None
    rows = [r for r in current_rows(home, s[1]) if r.get("bpb") is not None]
    head = f"probe set     {len(s[0]['items'])} frozen held-out replies"
    if not rows:
        return head + " · no checkpoint scored yet"
    a, b = rows[0], rows[-1]
    if a is b:
        return f"{head} · step {b['step']}: {b['bpb']:.2f} bpb"
    return f"{head} · step {a['step']}: {a['bpb']:.2f} -> step {b['step']}: {b['bpb']:.2f} bpb ({len(rows)} checkpoints)"


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _named(paths: Sequence[str]) -> List[Tuple[str, str]]:
    out = []
    for p in paths:
        ckpt, meta = prepost.live_paths() if p == "live" else (p, p[:-4] + ".json")
        if not (os.path.exists(ckpt) and os.path.exists(meta)):
            raise SystemExit(f"no checkpoint at {ckpt} (with {meta})")
        out.append((ckpt, meta))
    return out


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m osiris_cli.probeset", description=__doc__.split("\n\n")[0])
    ap.add_argument("--home", default=living.LIVING_HOME, help="the living home whose ledger and probe set to use")
    sub = ap.add_subparsers(dest="cmd", required=True)
    f = sub.add_parser("freeze", help="draw and freeze the probe set (once)")
    f.add_argument("--size", type=int, default=PROBE_SIZE)
    s = sub.add_parser("score", help="score unscored milestones, or the checkpoints named")
    s.add_argument("checkpoints", nargs="*", help=".npz files (with their .json beside them), or 'live'")
    sub.add_parser("show", help="the frozen set and every checkpoint scored on it")
    a = ap.parse_args(argv)

    if a.cmd == "freeze":
        try:
            print(json.dumps(freeze(a.home, a.size), indent=1))
        except (FileExistsError, ValueError) as e:
            print(f"not frozen: {e}")
            return 1
        return 0
    if load_set(a.home) is None:
        print(f"no probe set in {a.home}: python -m osiris_cli.probeset freeze")
        return 1
    if a.cmd == "score":
        where = os.path.dirname(prepost.live_paths()[0])
        todo = _named(a.checkpoints) if a.checkpoints else milestones(where)
        rows = score(a.home, todo, log=print)
        print(f"{len(rows)} checkpoint(s) scored" + ("" if rows else " (all already scored on this set)"))
        return 0
    probe, sha = load_set(a.home)
    voices = Counter(it["voice"] for it in probe["items"])
    print(f"probe set {set_path(a.home)}\n  sha256 {sha}\n  frozen {probe['created']}, {len(probe['items'])} "
          f"replies from {probe['ledger']['candidates']} candidates: "
          + ", ".join(f"{v} {n}" for v, n in voices.most_common()))
    for row in current_rows(a.home, sha):
        print("  " + describe(row))
    return 0


if __name__ == "__main__":
    sys.exit(main())
