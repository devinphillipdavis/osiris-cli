"""Hash-chained retrieval ledger and evidence capsules.

The ledger is append-only JSON lines; each row carries the hash of the row
before it, so editing, dropping or reordering rows breaks the chain.
Free-text queries are recorded by SHA-256, not by their text.

A capsule is a zip a reviewer can check without OSIRIS's state: the run's
config, the queries and qrels it was scored on, the rankings with scores, the
metrics, the run's ledger rows and a summary. ``verify_capsule`` recomputes the
file digests, the metrics from the rankings and qrels, and the ledger chain.
The capsule is not signed: anyone can build a new, self-consistent capsule.
Verification catches edits that break consistency, not a forger.

Retrieved abstracts are evidence candidates. Nothing here decides whether a
claim is true, and nothing writes to the claims register, facts or training data.
"""

from __future__ import annotations

import hashlib
import io
import json
import os
import time
import zipfile
from typing import Any, Dict, List, Optional, Sequence, Tuple

from osiris_cli.retrieval.metrics import evaluate

try:
    import fcntl
except ImportError:      # Windows: appends are not locked
    fcntl = None

GENESIS = "0" * 64
CAPSULE_TYPE = "olmo3_embedding_retrieval_v1"
CAPSULE_FILES = ("config.json", "corpus_index_meta.json", "queries.jsonl", "qrels.jsonl", "rankings.jsonl",
                 "metrics.json", "ledger_block.json", "summary.md")
LIMITATIONS = [
    "English-only model",
    "512-token input limit: longer abstracts are truncated",
    "embedding retrieval ranks candidate evidence; it does not establish factual truth",
    "SciFact is in-domain for this model: its train qrels were in the training data",
    "results depend on hardware, dtype and library versions",
    "capsule manifest is unsigned",
]


def _canon(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _row_hash(row: Dict[str, Any]) -> str:
    return _sha(_canon({k: row[k] for k in ("kind", "payload", "prev", "ts")}))


class RetrievalLedger:
    def __init__(self, path: str):
        self.path = path

    def rows(self) -> List[Dict[str, Any]]:
        if not os.path.exists(self.path):
            return []
        with open(self.path, encoding="utf-8") as f:
            return [json.loads(line) for line in f if line.strip()]

    def _tip(self, f) -> str:
        """Hash of the last row, read from the end of the open file."""
        f.seek(0, os.SEEK_END)
        end = f.tell()
        tail, step = b"", 4096
        while end > 0:
            start = max(0, end - step)
            f.seek(start)
            tail = f.read(end - start) + tail
            end = start
            lines = [line for line in tail.split(b"\n") if line.strip()]
            if len(lines) > 1 or (lines and end == 0):
                return json.loads(lines[-1])["hash"]
        return GENESIS

    def append(self, kind: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)
        fd = os.open(self.path, os.O_RDWR | os.O_APPEND | os.O_CREAT, 0o600)
        with os.fdopen(fd, "r+b") as f:
            if fcntl is not None:
                fcntl.flock(f.fileno(), fcntl.LOCK_EX)   # another process's row lands before or after, not between
            row = {"kind": kind, "payload": payload, "prev": self._tip(f),
                   "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
            row["hash"] = _row_hash(row)
            f.write((json.dumps(row, ensure_ascii=False) + "\n").encode("utf-8"))
            f.flush()
            os.fsync(f.fileno())
        return row

    def verify(self) -> Tuple[bool, str]:
        try:
            rows = self.rows()
        except ValueError as e:
            return False, f"unreadable: {e}"
        problem = chain_problem(rows, GENESIS)
        return (False, problem) if problem else (True, f"{len(rows)} row{'' if len(rows) == 1 else 's'}, chain intact")

    def run_block(self, run_id: str) -> List[Dict[str, Any]]:
        """The contiguous rows from the run's first row to its last, so the links can be checked.

        Rows another command wrote in between (a free-text query, by hash) are included.
        """
        rows = self.rows()
        mine = [i for i, r in enumerate(rows) if r["payload"].get("run_id") == run_id]
        return rows[mine[0]:mine[-1] + 1] if mine else []


def chain_problem(rows: Sequence[Dict[str, Any]], first_prev: Optional[str]) -> Optional[str]:
    """Why ``rows`` are not a valid chain segment (None when they are).

    ``first_prev`` is what the first row must link to: the genesis hash for a
    whole ledger, None for a segment cut out of one.
    """
    for i, row in enumerate(rows):
        try:
            if row["hash"] != _row_hash(row):
                return f"row {i} ({row.get('kind')}): hash does not match its contents"
            if i == 0 and first_prev is not None and row["prev"] != first_prev:
                return "row 0: does not link to the start of the chain"
            if i > 0 and row["prev"] != rows[i - 1]["hash"]:
                return f"row {i} ({row['kind']}): does not link to row {i - 1}"
        except KeyError as e:
            return f"row {i}: missing {e}"
    return None


def _jsonl(rows: Sequence[Dict[str, Any]]) -> str:
    return "".join(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n" for r in rows)


def build_manifest(run: Dict[str, Any], files: Dict[str, bytes]) -> Dict[str, Any]:
    env = run.get("environment", {})
    comparison = run.get("comparison", {})
    return {
        "capsule_type": CAPSULE_TYPE,
        "run_id": run["run_id"],
        "retrieval_backend": f"sentence-transformers:{run['config']['model_id']}",
        "model_id": run["config"]["model_id"],
        "model_revision": env.get("resolved_revision") or run["config"].get("revision"),
        "embedding_dimension": run["index"].get("dimension"),
        "max_sequence_length": env.get("max_seq_length"),
        "dataset": run["dataset"].get("name"),
        "dataset_revision": run["dataset"].get("revision"),
        "dataset_split": run["dataset"].get("split"),
        "dataset_files": run["dataset"].get("files"),
        "qrels_source": f"{run['dataset'].get('name')} qrels/{run['dataset'].get('split')}.tsv",
        "query_instruction": run["config"].get("query_instruction"),
        "query_prompt": run["config"].get("query_prompt_used"),
        "query_selection": run.get("query_selection"),
        "top_k": run["config"]["top_k"],
        "dtype": env.get("dtype"),
        "device": env.get("device"),
        "libraries": env.get("libraries"),
        "determinism": "hardware_and_library_dependent",
        "network_access": "required_for_initial_download",
        "metrics": {k: v for k, v in run.get("metrics", {}).items() if k != "per_query"},
        "comparable_to_model_card": comparison.get("comparable"),
        "not_comparable_because": comparison.get("not_comparable_because"),
        "limitations": LIMITATIONS,
        "files": {name: hashlib.sha256(data).hexdigest() for name, data in sorted(files.items())},
        "signed": False,
    }


def summary_markdown(run: Dict[str, Any]) -> str:
    m, c = run.get("metrics", {}), run.get("comparison", {})
    lines = [f"# Retrieval run {run['run_id']}", "",
             f"- **Model:** {run['config']['model_id']} @ "
             f"{run.get('environment', {}).get('resolved_revision') or 'revision unresolved'}",
             f"- **Dataset:** {run['dataset'].get('name')} {run['dataset'].get('split')} "
             f"({run['index'].get('documents')} documents indexed)",
             f"- **Queries:** {m.get('queries')} ({run.get('query_selection', {}).get('method')})",
             f"- **nDCG@10:** {m.get('ndcg_at_10', 0):.4f}"
             + (f" (standard error {m['ndcg_at_10_stderr']:.4f})" if m.get("ndcg_at_10_stderr") else ""),
             f"- **MRR@10:** {m.get('mrr_at_10', 0):.4f}", f"- **Recall@10:** {m.get('recall_at_10', 0):.4f}",
             f"- **Model card:** {c.get('reference', {}).get('value')} over "
             f"{c.get('reference', {}).get('queries')} queries; "
             + ("comparable." if c.get("comparable") else
                "not directly comparable: " + "; ".join(c.get("not_comparable_because") or ["not evaluated"]) + "."),
             ""]
    if c.get("ci95"):
        lines.insert(-1, f"- **95% interval (normal approximation):** {c['ci95'][0]}-{c['ci95'][1]}; "
                         f"the card's figure is {'inside' if c.get('reference_inside_ci95') else 'outside'} it")
    lines += ["Retrieved abstracts are evidence candidates ranked by similarity. They do not show that a claim "
              "is true or false, and no claim is promoted on their basis.", "",
              "This capsule is unsigned; `osiris retrieval verify` checks its internal consistency."]
    return "\n".join(lines) + "\n"


def write_capsule(path: str, run: Dict[str, Any], queries: Dict[str, str], qrels: Dict[str, Dict[str, int]],
                  rankings: Sequence[Dict[str, Any]], ledger_rows: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    """Write the capsule zip; returns its manifest."""
    ids = [r["query_id"] for r in rankings]
    files = {
        "config.json": json.dumps(run["config"], indent=2, sort_keys=True),
        "corpus_index_meta.json": json.dumps(run["index"], indent=2, sort_keys=True),
        "queries.jsonl": _jsonl([{"query_id": q, "text": queries[q]} for q in ids]),
        "qrels.jsonl": _jsonl([{"query_id": q, "relevant": qrels[q]} for q in ids]),
        "rankings.jsonl": _jsonl(rankings),
        "metrics.json": json.dumps({"metrics": run["metrics"], "comparison": run.get("comparison")},
                                   indent=2, sort_keys=True),
        "ledger_block.json": json.dumps(list(ledger_rows), indent=2, ensure_ascii=False),
        "summary.md": summary_markdown(run),
    }
    data = {name: text.encode("utf-8") for name, text in files.items()}
    manifest = build_manifest(run, data)
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as z:
        z.writestr("manifest.json", json.dumps(manifest, indent=2, sort_keys=True))
        for name in CAPSULE_FILES:
            z.writestr(name, data[name])
    return manifest


def _read_jsonl(text: str) -> List[Dict[str, Any]]:
    return [json.loads(line) for line in io.StringIO(text) if line.strip()]


def verify_capsule(path: str, tolerance: float = 1e-9) -> Tuple[bool, List[str]]:
    """(intact, problems). Intact means internally consistent, not authentic."""
    problems: List[str] = []
    try:
        with zipfile.ZipFile(path) as z:
            names = set(z.namelist())
            if "manifest.json" not in names:
                return False, ["no manifest.json"]
            manifest = json.loads(z.read("manifest.json"))
            contents = {n: z.read(n) for n in CAPSULE_FILES if n in names}
    except (OSError, zipfile.BadZipFile, ValueError) as e:
        return False, [f"unreadable capsule: {e}"]
    if manifest.get("capsule_type") != CAPSULE_TYPE:
        problems.append(f"capsule_type is {manifest.get('capsule_type')!r}, expected {CAPSULE_TYPE}")
    listed = manifest.get("files", {})
    for name in CAPSULE_FILES:
        if name not in contents:
            problems.append(f"{name} is missing")
        elif listed.get(name) != hashlib.sha256(contents[name]).hexdigest():
            problems.append(f"{name} does not match its digest in the manifest")
    if problems:
        return False, problems

    rankings = _read_jsonl(contents["rankings.jsonl"].decode("utf-8"))
    qrels = {r["query_id"]: r["relevant"] for r in _read_jsonl(contents["qrels.jsonl"].decode("utf-8"))}
    stored = json.loads(contents["metrics.json"])["metrics"]
    recomputed = evaluate(rankings, qrels, k=stored.get("k", 10))
    for name in ("ndcg_at_10", "mrr_at_10", "recall_at_10", "queries"):
        if name in stored and abs((recomputed.get(name) or 0) - (stored.get(name) or 0)) > tolerance:
            problems.append(f"{name}: stored {stored.get(name)}, recomputed from the rankings {recomputed.get(name)}")
    for name in ("ndcg_at_10", "mrr_at_10", "recall_at_10"):
        if name in manifest.get("metrics", {}) and manifest["metrics"][name] != stored.get(name):
            problems.append(f"manifest {name} differs from metrics.json")

    ledger_rows = json.loads(contents["ledger_block.json"])
    chain = chain_problem(ledger_rows, None)
    if chain:
        problems.append(f"ledger block: {chain}")
    mine = [r for r in ledger_rows if r.get("payload", {}).get("run_id") == manifest.get("run_id")]
    ledgered = {r["payload"]["query_id"]: r["payload"]["ranked_doc_ids"] for r in mine
                if r.get("kind") == "retrieval_query"}
    if len(ledgered) != len(rankings):
        problems.append(f"{len(rankings)} rankings but {len(ledgered)} ledgered queries for this run")
    for row in rankings:
        if ledgered.get(row["query_id"]) != row["ranked_doc_ids"]:
            problems.append(f"query {row['query_id']}: ranking differs from its ledger row")
            break
    return not problems, problems
