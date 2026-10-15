"""`/retrieval ...` in the REPL and `osiris retrieval ...` on the command line.

    status                       dependencies, hardware policy, dataset, caches, runs, ledger
    load-scifact                 download mteb/scifact (pinned revision) and check it
    build-index                  embed the corpus into the resumable cache
    run [--queries N | --full]   retrieve for judged test queries; saves rankings, ledgers each query
    evaluate [RUN]               nDCG@10 / MRR@10 / Recall@10 and the comparison with the model card
    capsule PATH [RUN]           write an evidence capsule (.evidence.zip)
    verify PATH                  check a capsule's internal consistency
    query <claim text>           rank abstracts as evidence candidates for one claim
    unload                       free the model this session holds

State lives under $OSIRIS_RETRIEVAL_HOME (default ~/.osiris/retrieval).
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import random
import shlex
import sys
import time
import uuid
from typing import Any, Callable, Dict, List, Optional

from osiris_cli.retrieval import metrics as metrics_mod
from osiris_cli.retrieval import policy, scifact
from osiris_cli.retrieval.cache import EmbeddingCache
from osiris_cli.retrieval.embedder import (
    MODEL_ID,
    QUERY_TEMPLATE,
    SCIFACT_INSTRUCTION,
    EmbedderConfig,
    MissingDependency,
    OlmoEmbedder,
    sha256_text,
)
from osiris_cli.retrieval.evidence import RetrievalLedger, verify_capsule, write_capsule
from osiris_cli.retrieval.retrieval_loop import RetrievalLoop

DEFAULT_PROMPT = QUERY_TEMPLATE.format(instruction=SCIFACT_INSTRUCTION)
BOUNDARY = ("Retrieved abstracts are evidence candidates ranked by embedding similarity: not a verdict, "
            "and nothing is promoted to the claims register, facts or training data.")

EmbedderFactory = Callable[[EmbedderConfig], Any]


class Refused(RuntimeError):
    """A command that will not run, with the reason to show."""


class _Parser(argparse.ArgumentParser):
    def error(self, message):
        raise Refused(f"{message}\n{self.format_usage().strip()}")

    def exit(self, status=0, message=None):
        raise Refused(message or "")


def home() -> str:
    return os.environ.get("OSIRIS_RETRIEVAL_HOME") or os.path.join(os.path.expanduser("~"), ".osiris", "retrieval")


def _paths(args) -> Dict[str, str]:
    root = home()
    return {"data": args.data or os.path.join(root, "scifact"), "cache": os.path.join(root, "cache"),
            "runs": os.path.join(root, "runs"), "ledger": os.path.join(root, "ledger.jsonl")}


def _model_options(p: argparse.ArgumentParser) -> None:
    p.add_argument("--model", default=MODEL_ID, help=f"sentence-transformers model (default {MODEL_ID})")
    p.add_argument("--revision", help="model commit SHA to pin (default: what the Hub has now)")
    p.add_argument("--device", help="cuda, cuda:1, cpu (default: cuda when available)")
    p.add_argument("--dtype", default="bfloat16", choices=["bfloat16", "float16", "float32", "auto"])
    p.add_argument("--batch-size", type=int, help="default: 8 on a GPU, 2 on a CPU")
    p.add_argument("--instruction", default=SCIFACT_INSTRUCTION,
                   help="query instruction (default: MTEB's SciFact prompt); '' for none")
    p.add_argument("--query-prompt", help="raw query prefix for other models; overrides --instruction")
    p.add_argument("--force", action="store_true", help="run although free RAM looks too small")


def build_parser() -> argparse.ArgumentParser:
    parser = _Parser(prog="osiris retrieval", description="olmo3-embed-7b retrieval as an evidence backend")
    parser.add_argument("--data", help="BEIR SciFact directory (default $OSIRIS_RETRIEVAL_HOME/scifact)")
    sub = parser.add_subparsers(dest="command", parser_class=_Parser)
    sub.add_parser("status", help="what is installed, allowed, downloaded, cached and ledgered")
    p = sub.add_parser("load-scifact", help="download mteb/scifact and check it")
    p.add_argument("--revision", default=scifact.REVISION, help="dataset commit (default: the one mteb pins)")
    p = sub.add_parser("build-index", help="embed the corpus into the cache")
    _model_options(p)
    p.add_argument("--corpus-limit", type=int, help="first N documents only: a smoke test, not comparable")
    p = sub.add_parser("run", help="retrieve for judged test queries")
    _model_options(p)
    p.add_argument("--queries", type=int, help="number of queries (default: all; 25 on a CPU)")
    p.add_argument("--full", action="store_true", help="all 300 test queries, also on a CPU")
    p.add_argument("--sample", choices=["random", "first"], default="random",
                   help="how a subset is drawn: seeded random (default) or the lowest ids, which are "
                        "the claims starting with digits")
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--top-k", type=int, default=10)
    p.add_argument("--corpus-limit", type=int, help="index the first N documents only: not comparable")
    p = sub.add_parser("evaluate", help="score a run against the qrels")
    p.add_argument("run_id", nargs="?", help="default: the latest run")
    p = sub.add_parser("capsule", help="write an evidence capsule")
    p.add_argument("path")
    p.add_argument("run_id", nargs="?", help="default: the latest run")
    p = sub.add_parser("verify", help="check a capsule")
    p.add_argument("path")
    p = sub.add_parser("query", help="evidence candidates for one claim")
    _model_options(p)
    p.add_argument("--top-k", type=int, default=5)
    p.add_argument("text", nargs="+")
    sub.add_parser("unload", help="free the model this session holds")
    return parser


# ── helpers ───────────────────────────────────────────────────────────────────

def _versions() -> Dict[str, Optional[str]]:
    from importlib import metadata

    out = {}
    for dist, module in (("torch", "torch"), ("sentence-transformers", "sentence_transformers"),
                         ("transformers", "transformers")):
        if importlib.util.find_spec(module) is None:
            out[dist] = None
            continue
        try:
            out[dist] = metadata.version(dist)
        except metadata.PackageNotFoundError:
            out[dist] = "installed"
    return out


def _placement(args) -> policy.Placement:
    placed = policy.place(args.model, device=args.device, force=args.force, dtype=args.dtype)
    if not placed.allowed:
        raise Refused("hardware policy: " + "; ".join(placed.reasons))
    return placed


# The last model loaded in this process: a REPL session reuses it instead of reading
# 13.8 GB of weights again for every command. `/retrieval unload` frees it.
_LOADED: Dict[str, Any] = {}


def _embedder(args, placed: policy.Placement, factory: Optional[EmbedderFactory]):
    config = EmbedderConfig(model_id=args.model, revision=args.revision, device=placed.device, dtype=args.dtype,
                            batch_size=args.batch_size or placed.batch_size, query_instruction=args.instruction,
                            query_prompt=args.query_prompt)
    if factory is not None:
        return factory(config)
    held = _LOADED.get("embedder")
    if held is not None and held.config == config:
        return held
    _LOADED.clear()
    _LOADED["embedder"] = OlmoEmbedder(config)
    return _LOADED["embedder"]


def unload() -> bool:
    """Free the model this process holds; False if none was loaded."""
    held = _LOADED.pop("embedder", None)
    if held is None:
        return False
    del held
    import gc

    gc.collect()
    if importlib.util.find_spec("torch") is not None:
        import torch

        if torch.cuda.is_available():
            torch.cuda.empty_cache()
    return True


def _progress(out: Callable[[str], None]):
    started = time.time()

    def report(done: int, total: int, encoded_now: int) -> None:
        if not encoded_now:
            return
        rate = encoded_now / max(time.time() - started, 1e-6)
        left = (total - done) / rate if rate else 0
        out(f"  index: {done:,}/{total:,} documents ({encoded_now:,} embedded now, {rate:.1f}/s, "
            f"~{left / 60:.0f} min left)")
    return report


def _load_index(args, embedder, data: scifact.SciFactData, paths, out, top_k: int = 10):
    corpus = data.corpus
    if getattr(args, "corpus_limit", None):
        corpus = {d: corpus[d] for d in sorted(corpus)[:args.corpus_limit]}
    loop = RetrievalLoop(embedder, top_k=top_k)
    stats = loop.build_index(corpus, EmbeddingCache(paths["cache"]), progress=_progress(out))
    stats["corpus_limited"] = len(corpus) != len(data.corpus)
    return loop, stats


def select_queries(ids: List[str], n: Optional[int], method: str, seed: int) -> List[str]:
    if n is None or n >= len(ids):
        return list(ids)
    if n < 1:
        raise Refused("--queries must be at least 1")
    if method == "first":
        return list(ids[:n])
    chosen = set(random.Random(seed).sample(ids, n))
    return [q for q in ids if q in chosen]


def _runs(paths) -> List[str]:
    if not os.path.isdir(paths["runs"]):
        return []
    return sorted(d for d in os.listdir(paths["runs"]) if os.path.isfile(os.path.join(paths["runs"], d, "run.json")))


def _load_run(paths, run_id: Optional[str]):
    runs = _runs(paths)
    if not runs:
        raise Refused("no runs yet: /retrieval run first")
    run_id = run_id or runs[-1]
    if run_id not in runs:
        raise Refused(f"no run {run_id!r}; runs: {', '.join(runs[-5:])}")
    where = os.path.join(paths["runs"], run_id)
    with open(os.path.join(where, "run.json"), encoding="utf-8") as f:
        run = json.load(f)
    with open(os.path.join(where, "rankings.jsonl"), encoding="utf-8") as f:
        rankings = [json.loads(line) for line in f if line.strip()]
    return run, rankings, where


def _save_json(path: str, value: Any) -> None:
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(value, f, indent=2, sort_keys=True)
    os.replace(tmp, path)


def _data_for_run(run, paths) -> scifact.SciFactData:
    data = scifact.load(paths["data"], run["dataset"]["split"])
    if data.files != run["dataset"]["files"]:
        raise Refused(f"the dataset files in {paths['data']} differ from the ones this run used")
    return data


def _setup_problems(run: Dict[str, Any], data: scifact.SciFactData) -> List[str]:
    """Why a run's setup differs from the model card's (beyond the number of queries)."""
    cfg, env, index = run["config"], run.get("environment", {}), run["index"]
    problems = []
    if cfg["model_id"] != MODEL_ID:
        problems.append(f"model {cfg['model_id']}")
    if cfg["query_prompt_used"] != DEFAULT_PROMPT:
        problems.append("a different query prompt")
    if env.get("dtype") != "bfloat16":
        problems.append(f"dtype {env.get('dtype')}")
    if env.get("max_seq_length") not in (None, 512):
        problems.append(f"max length {env.get('max_seq_length')}")
    if index.get("corpus_limited"):
        problems.append(f"only {index.get('documents')} documents indexed")
    if cfg["top_k"] < 10:
        problems.append(f"top_k {cfg['top_k']} < 10")
    differences = scifact.check_against_reference(data)
    if differences:
        problems.append(f"the dataset differs from the pinned mteb/scifact test split ({differences[-1]}; "
                        f"{len(differences)} differences in all)")
    return problems


# ── commands ──────────────────────────────────────────────────────────────────

def cmd_status(args, paths, factory, out) -> str:
    lines = ["OSIRIS retrieval · olmo3-embed-7b evidence backend"]
    versions = _versions()
    missing = [k for k, v in versions.items() if v is None]
    lines.append("  libraries : " + ("missing " + ", ".join(missing) + ' -> pip install "osiris-cli[retrieval]"'
                                     if missing else ", ".join(f"{k} {v}" for k, v in versions.items())))
    lines.append("  hardware  : " + policy.place(MODEL_ID).summary())
    try:
        data = scifact.load(paths["data"])
        problems = scifact.check_against_reference(data)
        lines.append(f"  dataset   : {paths['data']}: {len(data.corpus):,} documents, {len(data.queries)} judged "
                     f"test queries; " + ("matches the pinned mteb/scifact sizes and counts" if not problems
                                          else f"differs from the reference in {len(problems)} ways "
                                               f"({problems[-1]}; /retrieval load-scifact lists them)"))
    except scifact.DatasetError as e:
        lines.append(f"  dataset   : {e}")
    entries = EmbeddingCache(paths["cache"]).entries()
    lines.append(f"  caches    : {len(entries)}" + "".join(
        f"\n              {e['key']}: {e['fingerprint'].get('model_id')}@{str(e['fingerprint'].get('revision'))[:12]} "
        f"{e['fingerprint'].get('dtype')}, {e['documents']:,} documents" for e in entries))
    runs = _runs(paths)
    if runs:
        run, _, _ = _load_run(paths, runs[-1])
        m = run.get("metrics")
        lines.append(f"  runs      : {len(runs)}; latest {runs[-1]} ({run['config']['model_id']}, "
                     f"{len(run['query_ids'])} queries" + (f", nDCG@10 {m['ndcg_at_10']:.4f})" if m else ", not evaluated)"))
    else:
        lines.append("  runs      : none")
    held = _LOADED.get("embedder")
    if held is not None:
        lines.append(f"  loaded    : {held.config.model_id} on {held.device} (/retrieval unload frees it)")
    ok, msg = RetrievalLedger(paths["ledger"]).verify()
    lines.append(f"  ledger    : {paths['ledger']}: {msg}" + ("" if ok else "  <-- BROKEN"))
    lines.append("  boundary  : " + BOUNDARY)
    return "\n".join(lines)


def cmd_load_scifact(args, paths, factory, out) -> str:
    fetched = scifact.download(paths["data"], revision=args.revision)
    data = scifact.load(paths["data"])
    problems = scifact.check_against_reference(data)
    RetrievalLedger(paths["ledger"]).append("dataset_loaded", {
        "dataset": scifact.REPO, "revision": args.revision, "downloaded": fetched, "files": data.files,
        "documents": len(data.corpus), "judged_queries": len(data.queries), "reference_problems": problems})
    lines = [f"[retrieval] {paths['data']}: " + (f"downloaded {', '.join(fetched)}" if fetched else "files already present"),
             f"  {len(data.corpus):,} documents, {len(data.queries)} judged {data.split} queries "
             f"({data.queries_in_file} in queries.jsonl), {sum(len(v) for v in data.qrels.values())} relevant pairs"]
    lines += [f"  {rel}: sha256 {d['sha256']} ({d['bytes']:,} bytes)" for rel, d in sorted(data.files.items())]
    lines.append("  matches the pinned mteb/scifact sizes and counts" if not problems
                 else "  differs from the reference: " + "; ".join(problems))
    return "\n".join(lines)


def cmd_build_index(args, paths, factory, out) -> str:
    placed = _placement(args)
    data = scifact.load(paths["data"])
    embedder = _embedder(args, placed, factory)
    loop, stats = _load_index(args, embedder, data, paths, out)
    env = embedder.environment()
    RetrievalLedger(paths["ledger"]).append("index_built", {
        "model_id": args.model, "model_revision": env.get("resolved_revision"), "fingerprint": embedder.fingerprint(),
        "stats": stats, "dataset_files": data.files})
    return (f"[retrieval] index {stats['cache_key']}: {stats['documents']:,} documents x {stats['dimension']} dims "
            f"({stats['reused']:,} from cache, {stats['encoded']:,} embedded in {stats['seconds']:.0f} s) on "
            f"{env.get('device')} in {env.get('dtype')}" + (" -- corpus limited: not comparable" if stats["corpus_limited"] else ""))


def cmd_run(args, paths, factory, out) -> str:
    if args.top_k < 1:
        raise Refused("--top-k must be at least 1")
    placed = _placement(args)
    data = scifact.load(paths["data"])
    wanted = None if args.full else (args.queries if args.queries is not None else placed.default_queries)
    query_ids = select_queries(data.query_ids(), wanted, args.sample, args.seed)
    embedder = _embedder(args, placed, factory)
    loop, stats = _load_index(args, embedder, data, paths, out, top_k=args.top_k)
    env = embedder.environment()
    run_id = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime()) + "-" + uuid.uuid4().hex[:6]
    config = dict(embedder.config_dict(), top_k=args.top_k)
    instruction_sha = sha256_text(config["query_prompt_used"])
    selection = {"method": "all" if len(query_ids) == len(data.queries) else args.sample,
                 "seed": args.seed if args.sample == "random" else None, "requested": wanted,
                 "of": len(data.queries)}
    run = {"run_id": run_id, "config": config, "environment": env, "fingerprint": embedder.fingerprint(),
           "index": stats, "placement": {"mode": placed.mode, "reasons": placed.reasons},
           "dataset": {"name": scifact.REPO, "revision": (data.source.get("files", {}).get("corpus.jsonl") or {})
                       .get("revision"), "split": data.split, "files": data.files},
           "query_selection": selection, "query_ids": query_ids,
           "started": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
    ledger = RetrievalLedger(paths["ledger"])
    ledger.append("retrieval_run_started", {"run_id": run_id, "config": config, "fingerprint": run["fingerprint"],
                                            "query_selection": selection, "dataset_files": data.files})

    def record(result) -> None:
        ledger.append("retrieval_query", {
            "run_id": run_id, "dataset": scifact.REPO, "query_id": result.query_id, "model_id": args.model,
            "model_revision": env.get("resolved_revision"), "query_instruction_sha256": instruction_sha,
            "top_k": args.top_k, "ranked_doc_ids": result.ranked_doc_ids,
            "scores": [round(s, 6) for s in result.scores], "latency_ms": result.latency_ms})

    results = loop.run(data.queries, query_ids, on_result=record)
    rankings = [dict(r.to_dict(), scores=[round(s, 6) for s in r.scores]) for r in results]
    where = os.path.join(paths["runs"], run_id)
    os.makedirs(where, exist_ok=True)
    body = "".join(json.dumps(r, sort_keys=True) + "\n" for r in rankings)
    with open(os.path.join(where, "rankings.jsonl"), "w", encoding="utf-8") as f:
        f.write(body)
    run["finished"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    run["rankings_sha256"] = hashlib.sha256(body.encode("utf-8")).hexdigest()
    _save_json(os.path.join(where, "run.json"), run)
    ledger.append("retrieval_run_finished", {"run_id": run_id, "queries": len(rankings),
                                             "rankings_sha256": run["rankings_sha256"]})
    mean_ms = sum(r.latency_ms for r in results) / max(len(results), 1)
    return (f"[retrieval] run {run_id}: {len(results)} of {len(data.queries)} queries "
            f"({selection['method']}), top {args.top_k}, {mean_ms:.0f} ms per query on {env.get('device')}\n"
            f"  index: {stats['documents']:,} documents ({stats['reused']:,} cached, {stats['encoded']:,} embedded now)\n"
            f"  next: /retrieval evaluate {run_id}")


def _evaluate(run, rankings, paths, where) -> Dict[str, Any]:
    data = _data_for_run(run, paths)
    run["metrics"] = metrics_mod.evaluate(rankings, data.qrels, k=10)
    problems = _setup_problems(run, data)
    run["comparison"] = metrics_mod.compare_with_reference(run["metrics"], not problems, problems)
    _save_json(os.path.join(where, "run.json"), run)
    RetrievalLedger(paths["ledger"]).append("retrieval_evaluated", {
        "run_id": run["run_id"], "metrics": {k: v for k, v in run["metrics"].items() if k != "per_query"},
        "comparable": run["comparison"]["comparable"],
        "not_comparable_because": run["comparison"]["not_comparable_because"]})
    return run


def cmd_evaluate(args, paths, factory, out) -> str:
    run, rankings, where = _load_run(paths, args.run_id)
    run = _evaluate(run, rankings, paths, where)
    m, c = run["metrics"], run["comparison"]
    se = f" ± {m['ndcg_at_10_stderr']:.4f} (standard error)" if m.get("ndcg_at_10_stderr") else ""
    lines = [f"[retrieval] run {run['run_id']}: {m['queries']} queries",
             f"  nDCG@10   {m['ndcg_at_10']:.4f}{se}", f"  MRR@10    {m['mrr_at_10']:.4f}",
             f"  Recall@10 {m['recall_at_10']:.4f}",
             f"  model card: {c['reference']['value']} over {c['reference']['queries']} test queries "
             f"(difference {c['difference']:+.4f})"]
    if c.get("ci95"):
        lines.append(f"  95% interval {c['ci95'][0]}-{c['ci95'][1]} (normal approximation); the card's figure is "
                     + ("inside it" if c["reference_inside_ci95"] else "OUTSIDE it"))
    lines.append("  comparable with the card" if c["comparable"] else
                 "  not directly comparable: " + "; ".join(c["not_comparable_because"]))
    lines.append("  note: SciFact is in-domain for this model (its train qrels were training data)")
    return "\n".join(lines)


def cmd_capsule(args, paths, factory, out) -> str:
    run, rankings, where = _load_run(paths, args.run_id)
    if "metrics" not in run:
        run = _evaluate(run, rankings, paths, where)
    data = _data_for_run(run, paths)
    ledger = RetrievalLedger(paths["ledger"])
    block = ledger.run_block(run["run_id"])
    manifest = write_capsule(args.path, run, data.queries, data.qrels, rankings, block)
    with open(args.path, "rb") as f:
        digest = hashlib.sha256(f.read()).hexdigest()
    ledger.append("retrieval_capsule_written", {"run_id": run["run_id"], "capsule": os.path.basename(args.path),
                                                "capsule_sha256": digest})
    ok, problems = verify_capsule(args.path)
    return (f"[retrieval] capsule {args.path} (sha256 {digest[:16]}...): run {run['run_id']}, "
            f"{len(rankings)} queries, {len(block)} ledger rows, nDCG@10 {run['metrics']['ndcg_at_10']:.4f}, "
            f"comparable with the card: {manifest['comparable_to_model_card']}\n"
            f"  self-check: {'intact' if ok else 'PROBLEMS: ' + '; '.join(problems)} (unsigned)")


def cmd_verify(args, paths, factory, out) -> str:
    ok, problems = verify_capsule(args.path)
    if ok:
        return (f"[retrieval] {args.path}: intact -- digests, metrics recomputed from the rankings and the "
                "ledger chain agree. The capsule is unsigned, so this shows consistency, not who made it.")
    return f"[retrieval] {args.path}: NOT intact\n" + "\n".join(f"  - {p}" for p in problems)


def cmd_query(args, paths, factory, out) -> str:
    if args.top_k < 1:
        raise Refused("--top-k must be at least 1")
    text = " ".join(args.text).strip()
    placed = _placement(args)
    data = scifact.load(paths["data"])
    embedder = _embedder(args, placed, factory)
    loop, stats = _load_index(args, embedder, data, paths, out, top_k=args.top_k)
    result = loop.retrieve("adhoc", text)
    env = embedder.environment()
    RetrievalLedger(paths["ledger"]).append("retrieval_query", {
        "run_id": None, "dataset": scifact.REPO, "query_sha256": sha256_text(text), "model_id": args.model,
        "model_revision": env.get("resolved_revision"),
        "query_instruction_sha256": sha256_text(embedder.config.resolved_query_prompt()), "top_k": args.top_k,
        "ranked_doc_ids": result.ranked_doc_ids, "scores": [round(s, 6) for s in result.scores],
        "latency_ms": result.latency_ms})
    lines = [f"[retrieval] evidence candidates for: {text[:200]}", f"  ({BOUNDARY})"]
    for rank, (doc_id, score) in enumerate(zip(result.ranked_doc_ids, result.scores), 1):
        doc = data.corpus[doc_id]
        lines.append(f"  {rank}. [{doc_id}] {score:.4f}  {doc.get('title') or '(untitled)'}")
        lines.append(f"     {doc['text'][:220]}{'...' if len(doc['text']) > 220 else ''}")
    return "\n".join(lines)


def cmd_unload(args, paths, factory, out) -> str:
    held = _LOADED.get("embedder")
    name = held.config.model_id if held is not None else None
    unload()
    return f"[retrieval] unloaded {name}" if name else "[retrieval] no model is loaded in this session"


COMMANDS = {"status": cmd_status, "load-scifact": cmd_load_scifact, "build-index": cmd_build_index,
            "run": cmd_run, "evaluate": cmd_evaluate, "capsule": cmd_capsule, "verify": cmd_verify,
            "query": cmd_query, "unload": cmd_unload}


def execute(argv: List[str], embedder_factory: Optional[EmbedderFactory] = None,
            out: Callable[[str], None] = print) -> str:
    """Run one command; raises Refused, MissingDependency or scifact.DatasetError."""
    parser = build_parser()
    if not argv or argv[0] in ("-h", "--help", "help"):
        return parser.format_help()
    args = parser.parse_args(argv)
    if args.command is None:
        return parser.format_help()
    return COMMANDS[args.command](args, _paths(args), embedder_factory, out)


def run_command(arg: str, embedder_factory: Optional[EmbedderFactory] = None) -> str:
    """REPL `/retrieval ...`: the command's report, or why it did not run."""
    try:
        argv = shlex.split(arg)
    except ValueError as e:
        return f"[retrieval] could not parse the arguments: {e}"
    try:
        return execute(argv or ["status"], embedder_factory, out=lambda line: print(line, flush=True))
    except (Refused, MissingDependency, scifact.DatasetError, ValueError) as e:
        return f"[retrieval] refused: {e}"


def main(argv: Optional[List[str]] = None, embedder_factory: Optional[EmbedderFactory] = None) -> int:
    """`osiris retrieval ...`: prints the report; exit status 0, or 1 if the command was refused."""
    argv = sys.argv[1:] if argv is None else argv
    try:
        print(execute(argv, embedder_factory, out=lambda line: print(line, flush=True)))
        return 0
    except (Refused, MissingDependency, scifact.DatasetError, ValueError) as e:
        print(f"[retrieval] refused: {e}", file=sys.stderr)
        return 1
