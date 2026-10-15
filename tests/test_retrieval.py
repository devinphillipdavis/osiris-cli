"""The olmo3-embed-7b retrieval backend without the model: loader, metrics, cache, loop,
ledger, capsules, hardware policy and the /retrieval commands, driven by a fake encoder.

tests/test_retrieval_models.py runs the same code with a tiny real Olmo3 model when the
optional extras are installed; tests/test_olmo_retrieval.py uses the real 7B weights on request.
"""
import ast
import http.server
import json
import math
import os
import threading
import zipfile
from pathlib import Path

import numpy as np
import pytest

from osiris_cli.retrieval import commands, metrics, policy, scifact
from osiris_cli.retrieval.cache import EmbeddingCache
from osiris_cli.retrieval.embedder import (
    MODEL_ID,
    SCIFACT_INSTRUCTION,
    EmbedderConfig,
    OlmoEmbedder,
)
from osiris_cli.retrieval.evidence import RetrievalLedger, verify_capsule
from osiris_cli.retrieval.retrieval_loop import RetrievalLoop

CORPUS = {
    "10": {"title": "Vitamin D and bone", "text": "vitamin d supplements raise bone density in adults"},
    "11": {"title": "Pasta", "text": "cooking pasta in salted water"},
    "12": {"title": "", "text": "statins lower cholesterol and heart attack risk"},
    "13": {"title": "Sleep", "text": "short sleep raises blood pressure"},
    "14": {"title": "Bone loss", "text": "bone density falls without vitamin d"},
}
QUERIES = {  # "0" and "2" are train claims: in queries.jsonl, not in qrels/test.tsv
    "0": "pasta cooking water", "1": "vitamin d raises bone density", "2": "sleep and memory",
    "3": "statins cut heart attack risk", "5": "short sleep raises blood pressure",
}
QRELS_TSV = "query-id\tcorpus-id\tscore\r\n1\t10\t1\r\n1\t14\t1\r\n3\t12\t1\r\n5\t13\t1\r\n5\t11\t0\r\n"
VOCAB = sorted({w for d in CORPUS.values() for w in (d["title"] + " " + d["text"]).lower().split()}
               | {w for q in QUERIES.values() for w in q.split()})


class BagOfWords:
    """Stands in for a SentenceTransformer: word counts, normalized; records the prompts it got."""

    def __init__(self):
        self.prompts, self.texts_encoded = [], 0

    def encode(self, texts, prompt=None, normalize_embeddings=True, **kwargs):
        self.prompts.append(prompt)
        self.texts_encoded += len(texts)
        out = np.zeros((len(texts), len(VOCAB)), dtype=np.float32)
        for i, text in enumerate(texts):
            for w in text.lower().split():
                if w in VOCAB:
                    out[i, VOCAB.index(w)] += 1
        norms = np.linalg.norm(out, axis=1, keepdims=True)
        return out / np.where(norms == 0, 1, norms)


class Constant(BagOfWords):
    def encode(self, texts, **kwargs):
        return np.ones((len(texts), 4), dtype=np.float32) / 2


def write_dataset(root):
    root = Path(root)
    (root / "qrels").mkdir(parents=True, exist_ok=True)
    (root / "corpus.jsonl").write_text("".join(json.dumps({"_id": k, **v}) + "\n" for k, v in CORPUS.items()))
    (root / "queries.jsonl").write_text("".join(json.dumps({"_id": k, "text": v}) + "\n" for k, v in QUERIES.items()))
    (root / "qrels" / "test.tsv").write_bytes(QRELS_TSV.encode())
    return str(root)


@pytest.fixture
def home(monkeypatch, tmp_path):
    """Retrieval state under tmp; a desktop with 64 GiB and no GPU; HOME is a fresh directory."""
    monkeypatch.setenv("OSIRIS_RETRIEVAL_HOME", str(tmp_path / "retrieval"))
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.delenv("TERMUX_VERSION", raising=False)
    monkeypatch.delenv("OSIRIS_RETRIEVAL_ALLOW_EDGE", raising=False)
    monkeypatch.setattr(policy, "is_edge", lambda env=None: False)
    monkeypatch.setattr(policy, "cuda_info", lambda: (False, None))
    monkeypatch.setattr(policy, "mem_available_gib", lambda: 64.0)
    (tmp_path / "home").mkdir()
    return tmp_path


@pytest.fixture
def fake():
    model = BagOfWords()
    return model, (lambda config: OlmoEmbedder(config, model=model))


def run(line, factory):
    return commands.run_command(line, embedder_factory=factory)


# ── dataset ──────────────────────────────────────────────────────────────────

def test_loader_keeps_only_judged_test_queries_and_reads_crlf_qrels(tmp_path):
    data = scifact.load(write_dataset(tmp_path))
    assert sorted(data.queries) == ["1", "3", "5"] and data.queries_in_file == 5
    assert data.qrels == {"1": {"10": 1, "14": 1}, "3": {"12": 1}, "5": {"13": 1}}   # the 0 grade is dropped
    assert set(data.files) == {"corpus.jsonl", "queries.jsonl", "qrels/test.tsv"}


def test_documents_are_formatted_as_mteb_formats_them():
    assert scifact.doc_text({"title": "T", "text": "body "}) == "T body"
    assert scifact.doc_text({"title": "", "text": "body "}) == "body "


def test_query_ids_sort_numerically():
    data = scifact.SciFactData(corpus={}, queries={"10": "", "9": "", "100": ""}, qrels={})
    assert data.query_ids() == ["9", "10", "100"]


def test_missing_files_say_how_to_get_them(tmp_path):
    with pytest.raises(scifact.DatasetError, match="load-scifact"):
        scifact.load(str(tmp_path))


def test_toy_data_differs_from_the_pinned_reference(tmp_path):
    problems = scifact.check_against_reference(scifact.load(write_dataset(tmp_path)))
    assert any("5 documents, the reference has 5183" in p for p in problems)


class _Files(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


def test_download_fetches_the_split_and_records_where_from(tmp_path, monkeypatch):
    src = write_dataset(tmp_path / "hub" / "mteb" / "scifact" / "abc123")
    handler = lambda *a, **k: _Files(*a, directory=str(tmp_path / "hub"), **k)  # noqa: E731
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        monkeypatch.setenv("OSIRIS_HF_DATASET_URL", f"http://127.0.0.1:{server.server_port}/{{repo}}/{{revision}}/{{path}}")
        dest = tmp_path / "dest"
        assert scifact.download(str(dest), revision="abc123") == scifact.split_files("test")
        assert (dest / "qrels" / "test.tsv").read_bytes() == Path(src, "qrels", "test.tsv").read_bytes()
        source = json.loads((dest / "SOURCE.json").read_text())
        assert source["files"]["corpus.jsonl"]["revision"] == "abc123"
        assert scifact.download(str(dest), revision="abc123") == []          # present files are kept
        with pytest.raises(scifact.DatasetError, match="network access"):
            scifact.download(str(tmp_path / "other"), revision="missing")
        assert not any(p.name.startswith(".download-") for p in (tmp_path / "other").rglob("*"))
    finally:
        server.shutdown()
        server.server_close()


def test_copied_in_files_get_no_invented_provenance(tmp_path):
    dest = write_dataset(tmp_path / "copied")
    assert scifact.download(dest) == []
    assert not os.path.exists(os.path.join(dest, "SOURCE.json"))


# ── metrics ──────────────────────────────────────────────────────────────────

def test_ndcg_mrr_recall_by_hand():
    rel = {"a": 1, "b": 1}
    assert metrics.ndcg_at_k(["a", "x", "b"], rel) == pytest.approx((1 + 1 / math.log2(4)) / (1 + 1 / math.log2(3)))
    assert metrics.mrr_at_k(["x", "a"], rel) == 0.5
    assert metrics.recall_at_k(["x", "a"], rel) == 0.5
    assert metrics.ndcg_at_k(["x"] * 10 + ["a"], rel) == 0.0                    # rank 11 is past the cut
    assert metrics.ndcg_at_k(["b", "a"], {"a": 2, "b": 1}) == pytest.approx(     # linear gains
        (1 + 2 / math.log2(3)) / (2 + 1 / math.log2(3)))


def test_comparison_with_the_card_needs_the_full_split_and_setup():
    full = {"ndcg_at_10": 0.79, "ndcg_at_10_stderr": 0.02, "queries": 300}
    assert metrics.compare_with_reference(full, True)["comparable"] is True
    pilot = metrics.compare_with_reference({"ndcg_at_10": 0.70, "ndcg_at_10_stderr": 0.06, "queries": 25}, True)
    assert pilot["comparable"] is False and "25 of the 300" in pilot["not_comparable_because"][0]
    assert pilot["reference_inside_ci95"] is True and pilot["difference"] == round(0.70 - 0.7947, 4)
    tiny = metrics.compare_with_reference({"ndcg_at_10": 1.0, "ndcg_at_10_stderr": 0.0, "queries": 2}, True)
    assert "ci95" not in tiny                                                   # no interval from 2 queries
    assert metrics.compare_with_reference(full, False, ["model x"])["comparable"] is False


# ── embedder, cache, loop ────────────────────────────────────────────────────

def test_queries_get_the_instruction_and_documents_do_not():
    model = BagOfWords()
    emb = OlmoEmbedder(EmbedderConfig(), model=model)
    emb.encode_queries(["a claim"])
    emb.encode_documents(["an abstract"])
    assert model.prompts == [f"Instruct: {SCIFACT_INSTRUCTION}\nQuery: ", None]
    assert SCIFACT_INSTRUCTION == "Given a scientific claim, retrieve documents that support or refute the claim"
    raw = OlmoEmbedder(EmbedderConfig(query_prompt="query: "), model=model)
    raw.encode_queries(["x"])
    assert model.prompts[-1] == "query: "


def test_cache_resumes_and_reencodes_only_what_changed(tmp_path):
    model = BagOfWords()
    emb = OlmoEmbedder(EmbedderConfig(), model=model)
    cache = EmbeddingCache(str(tmp_path))
    ids = [f"d{i:02d}" for i in range(10)]
    texts = [f"vitamin bone {i}" for i in range(10)]
    fp = {"model_id": "m", "revision": "r1"}
    first, stats = cache.embed(fp, ids, texts, emb.encode_documents, chunk_size=4)
    assert stats["encoded"] == 10 and model.texts_encoded == 10
    again, stats = cache.embed(fp, ids, texts, emb.encode_documents, chunk_size=4)
    assert stats == dict(stats, reused=10, encoded=0) and np.array_equal(first, again)
    texts[5] = "pasta"
    _, stats = cache.embed(fp, ids, texts, emb.encode_documents, chunk_size=4)
    assert stats["encoded"] == 4                                                # only chunk 1
    _, stats = cache.embed(dict(fp, revision="r2"), ids, texts, emb.encode_documents, chunk_size=4)
    assert stats["encoded"] == 10                                               # another revision
    chunk = Path(cache.directory(fp)) / "chunk-00000.npy"
    chunk.write_bytes(b"not numpy")
    _, stats = cache.embed(fp, ids, texts, emb.encode_documents, chunk_size=4)
    assert stats["encoded"] == 4
    assert [e["documents"] for e in cache.entries()] == [10, 10]


def test_ties_are_broken_by_doc_id():
    loop = RetrievalLoop(OlmoEmbedder(EmbedderConfig(), model=Constant()), top_k=3)
    loop.build_index({k: CORPUS[k] for k in ("14", "10", "12", "11")})
    result = loop.retrieve("q", "anything")
    assert result.ranked_doc_ids == ["10", "11", "12"] and len(result.scores) == 3


def test_the_loop_ranks_the_matching_abstract_first():
    loop = RetrievalLoop(OlmoEmbedder(EmbedderConfig(), model=BagOfWords()), top_k=2)
    loop.build_index(CORPUS)
    result = loop.retrieve("3", QUERIES["3"])
    assert result.ranked_doc_ids[0] == "12" and result.scores[0] > result.scores[1]


# ── ledger and capsules ──────────────────────────────────────────────────────

def test_ledger_chain_detects_edits(tmp_path):
    ledger = RetrievalLedger(str(tmp_path / "l.jsonl"))
    for i in range(3):
        ledger.append("retrieval_query", {"run_id": "r", "i": i})
    assert ledger.verify()[0]
    rows = ledger.rows()
    rows[1]["payload"]["i"] = 9
    Path(ledger.path).write_text("".join(json.dumps(r) + "\n" for r in rows))
    ok, why = ledger.verify()
    assert not ok and "row 1" in why
    rows = RetrievalLedger(str(tmp_path / "l.jsonl")).rows()
    Path(ledger.path).write_text("".join(json.dumps(r) + "\n" for r in [rows[0], rows[2]]))
    assert not ledger.verify()[0]                                               # a dropped row


def _end_to_end(factory, extra=""):
    assert "documents" in run("load-scifact", factory)
    out = run(f"run --full {extra}", factory)
    assert "3 of 3 queries" in out, out
    out = run("evaluate", factory)
    assert "nDCG@10" in out and "not directly comparable" in out, out
    return out


def test_load_run_evaluate_capsule_verify(home, fake, monkeypatch):
    model, factory = fake
    write_dataset(home / "retrieval" / "scifact")
    out = _end_to_end(factory)
    assert "the dataset differs from the pinned mteb/scifact test split" in out
    runs = os.listdir(home / "retrieval" / "runs")
    run_json = json.loads((home / "retrieval" / "runs" / runs[0] / "run.json").read_text())
    assert run_json["config"]["query_prompt_used"] == f"Instruct: {SCIFACT_INSTRUCTION}\nQuery: "
    assert run_json["metrics"]["ndcg_at_10"] == pytest.approx(1.0)              # bag of words solves the toy set

    capsule = home / "out" / "scifact.evidence.zip"
    out = run(f"capsule {capsule}", factory)
    assert "self-check: intact" in out, out
    assert "intact" in run(f"verify {capsule}", factory)
    with zipfile.ZipFile(capsule) as z:
        manifest = json.loads(z.read("manifest.json"))
        names = set(z.namelist())
    assert manifest["capsule_type"] == "olmo3_embedding_retrieval_v1" and manifest["signed"] is False
    assert manifest["model_id"] == MODEL_ID and manifest["comparable_to_model_card"] is False
    assert {"config.json", "corpus_index_meta.json", "queries.jsonl", "rankings.jsonl", "metrics.json",
            "ledger_block.json", "summary.md", "qrels.jsonl"} <= names

    rows = RetrievalLedger(str(home / "retrieval" / "ledger.jsonl")).rows()
    queries = [r["payload"] for r in rows if r["kind"] == "retrieval_query"]
    assert [q["query_id"] for q in queries] == ["1", "3", "5"]
    assert {"model_revision", "query_instruction_sha256", "top_k", "ranked_doc_ids", "scores", "latency_ms"} <= set(queries[0])
    assert rows[-1]["kind"] == "retrieval_capsule_written"
    assert not any((home / "home").iterdir())                                   # nothing outside its own state


def _rewrite(capsule, dest, name, edit, fix_digest):
    with zipfile.ZipFile(capsule) as z:
        files = {n: z.read(n) for n in z.namelist()}
    files[name] = edit(files[name])
    if fix_digest:
        import hashlib
        manifest = json.loads(files["manifest.json"])
        manifest["files"][name] = hashlib.sha256(files[name]).hexdigest()
        files["manifest.json"] = json.dumps(manifest).encode()
    with zipfile.ZipFile(dest, "w") as z:
        for n, data in files.items():
            z.writestr(n, data)
    return dest


def test_verify_catches_edited_capsules(home, fake):
    _, factory = fake
    write_dataset(home / "retrieval" / "scifact")
    _end_to_end(factory)
    capsule = str(home / "c.evidence.zip")
    run(f"capsule {capsule}", factory)

    def worse_ranking(data):
        rows = [json.loads(line) for line in data.decode().splitlines()]
        rows[0]["ranked_doc_ids"] = list(reversed(rows[0]["ranked_doc_ids"]))
        return "".join(json.dumps(r, sort_keys=True) + "\n" for r in rows).encode()

    ok, problems = verify_capsule(_rewrite(capsule, str(home / "a.zip"), "rankings.jsonl", worse_ranking, False))
    assert not ok and "rankings.jsonl does not match its digest" in problems[0]
    ok, problems = verify_capsule(_rewrite(capsule, str(home / "b.zip"), "rankings.jsonl", worse_ranking, True))
    assert not ok and any("recomputed from the rankings" in p for p in problems)
    assert any("differs from its ledger row" in p for p in problems)

    def better_metrics(data):
        m = json.loads(data)
        m["metrics"]["mrr_at_10"] = 0.1
        return json.dumps(m).encode()

    ok, problems = verify_capsule(_rewrite(capsule, str(home / "c.zip"), "metrics.json", better_metrics, True))
    assert not ok and any(p.startswith("mrr_at_10") for p in problems)

    def edit_ledger(data):
        rows = json.loads(data)
        rows[1]["payload"]["latency_ms"] = 1.0
        return json.dumps(rows).encode()

    ok, problems = verify_capsule(_rewrite(capsule, str(home / "d.zip"), "ledger_block.json", edit_ledger, True))
    assert not ok and any(p.startswith("ledger block") for p in problems)
    assert "NOT intact" in run(f"verify {home / 'd.zip'}", factory)


def test_evaluate_refuses_when_the_dataset_changed_after_the_run(home, fake):
    _, factory = fake
    data = write_dataset(home / "retrieval" / "scifact")
    run("load-scifact", factory)
    run("run --full", factory)
    with open(os.path.join(data, "qrels", "test.tsv"), "a") as f:
        f.write("3\t10\t1\r\n")
    assert "differ from the ones this run used" in run("evaluate", factory)


# ── policy and commands ──────────────────────────────────────────────────────

def test_hardware_policy():
    assert not policy.place(MODEL_ID, env={}, edge=True, cuda=(False, None), ram_gib=64).allowed
    assert policy.place(MODEL_ID, env={"OSIRIS_RETRIEVAL_ALLOW_EDGE": "1"}, edge=True, cuda=(False, None),
                        ram_gib=64).mode == "pilot"
    low = policy.place(MODEL_ID, env={}, edge=False, cuda=(False, None), ram_gib=8)
    assert not low.allowed and "--force" in low.reasons[0]
    assert policy.place(MODEL_ID, force=True, env={}, edge=False, cuda=(False, None), ram_gib=8).allowed
    cpu = policy.place(MODEL_ID, env={}, edge=False, cuda=(False, None), ram_gib=64)
    assert (cpu.mode, cpu.default_queries, cpu.batch_size, cpu.device) == ("pilot", 25, 2, "cpu")
    gpu = policy.place(MODEL_ID, env={}, edge=False, cuda=(True, 24.0), ram_gib=8)
    assert (gpu.mode, gpu.default_queries, gpu.device) == ("full", None, "cuda")
    assert policy.place("small/model", env={}, edge=True, cuda=(False, None), ram_gib=1).allowed


def test_a_cpu_pilot_samples_queries_reproducibly():
    ids = [str(i) for i in range(300)]
    a = commands.select_queries(ids, 25, "random", 0)
    assert a == commands.select_queries(ids, 25, "random", 0) and len(a) == 25 and a == sorted(a, key=int)
    assert a != commands.select_queries(ids, 25, "random", 1)
    assert commands.select_queries(ids, 3, "first", 0) == ["0", "1", "2"]
    assert commands.select_queries(ids, None, "random", 0) == ids


def test_refusals_say_why(home, fake, monkeypatch):
    _, factory = fake
    assert "load-scifact first" in run("run", factory)
    assert "refused" in run("run --top-k", factory)
    assert "refused" in run("no-such-command", factory)
    assert "could not parse" in run('query "unclosed', factory)
    monkeypatch.setattr(policy, "mem_available_gib", lambda: 4.0)
    write_dataset(home / "retrieval" / "scifact")
    assert "hardware policy" in run("run", factory)
    assert "usage" in run("--help", factory).lower()


def test_without_the_extras_the_backend_says_what_to_install(home, monkeypatch):
    from osiris_cli.retrieval import embedder

    def missing(module):
        raise embedder.MissingDependency(f"the retrieval backend needs '{module}': pip install \"osiris-cli[retrieval]\"")

    monkeypatch.setattr(embedder, "require", missing)
    write_dataset(home / "retrieval" / "scifact")
    assert 'osiris-cli[retrieval]' in commands.run_command("build-index")


def test_status_reports_each_part(home, fake):
    _, factory = fake
    out = run("status", factory)
    assert "hardware" in out and "load-scifact first" in out and "runs      : none" in out and "not a verdict" in out
    write_dataset(home / "retrieval" / "scifact")
    run("run --full", factory)
    out = run("", factory)
    assert "differs from the reference in 6 ways" in out and "not evaluated" in out and "chain intact" in out


def test_query_ranks_evidence_and_ledgers_only_a_hash(home, fake):
    _, factory = fake
    write_dataset(home / "retrieval" / "scifact")
    out = run('query "do statins lower heart attack risk" --top-k 2', factory)
    assert "1. [12]" in out and "not a verdict" in out
    row = RetrievalLedger(str(home / "retrieval" / "ledger.jsonl")).rows()[-1]
    assert row["payload"]["query_sha256"] and "statins" not in json.dumps(row)


def test_retrieval_never_imports_the_promotion_paths():
    """Retrieval supplies evidence; claims, facts, notes and training are written elsewhere."""
    forbidden = {"osiris_cli.claims", "osiris_cli.living", "osiris_cli.paste_learning", "osiris_cli.train",
                 "osiris_cli.knowledge", "genome_ledger", "osiris_termux_console", "gemini_bridge"}
    pkg = Path(commands.__file__).parent
    for path in pkg.glob("*.py"):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            names = [a.name for a in node.names] if isinstance(node, ast.Import) else \
                [node.module or ""] if isinstance(node, ast.ImportFrom) else []
            assert not forbidden & set(names), f"{path.name} imports {forbidden & set(names)}"


def test_the_repl_and_the_cli_route_to_retrieval(monkeypatch, capsys):
    from osiris_cli import osiris_repl, retrieval

    monkeypatch.setattr(retrieval, "run_command", lambda arg: f"ROUTED<{arg}>")
    osiris_repl.dispatch_command(osiris_repl.SESSION, "/retrieval run --queries 25")
    assert "ROUTED<run --queries 25>" in capsys.readouterr().out
    monkeypatch.setattr(retrieval, "main", lambda argv: 0 if argv == ["status"] else 3)
    with pytest.raises(SystemExit) as stop:
        osiris_repl.main(["retrieval", "status"])
    assert stop.value.code == 0


def test_ledger_appends_from_many_writers_keep_one_chain(tmp_path):
    ledger = RetrievalLedger(str(tmp_path / "l.jsonl"))
    ledger.append("big", {"note": "x" * 9000})                                  # longer than a read block

    def write(n):
        for i in range(25):
            RetrievalLedger(ledger.path).append("retrieval_query", {"writer": n, "i": i})

    threads = [threading.Thread(target=write, args=(n,)) for n in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    ok, msg = ledger.verify()
    assert ok, msg
    assert len(ledger.rows()) == 101


def test_queries_zero_is_refused_not_defaulted(home, fake):
    _, factory = fake
    write_dataset(home / "retrieval" / "scifact")
    assert "at least 1" in run("run --queries 0", factory)


def test_float32_needs_twice_the_memory():
    assert policy.place(MODEL_ID, env={}, edge=False, cuda=(False, None), ram_gib=20).allowed
    fp32 = policy.place(MODEL_ID, env={}, edge=False, cuda=(False, None), ram_gib=20, dtype="float32")
    assert not fp32.allowed and "float32 needs about 32 GiB" in fp32.reasons[0]


def test_a_session_reuses_the_loaded_model_until_unload(home, monkeypatch):
    built = []

    class Counting(OlmoEmbedder):
        def __init__(self, config):
            built.append(config)
            super().__init__(config, model=BagOfWords())

    monkeypatch.setattr(commands, "OlmoEmbedder", Counting)
    monkeypatch.setattr(commands, "_LOADED", {})
    write_dataset(home / "retrieval" / "scifact")
    for _ in range(2):
        assert "1. [12]" in commands.run_command('query "statins heart attack risk"')
    assert len(built) == 1
    assert "loaded    : petegordon/olmo3-embed-7b" in commands.run_command("status")
    commands.run_command('query "statins" --instruction ""')                    # another config: reloaded
    assert len(built) == 2
    assert "unloaded petegordon/olmo3-embed-7b" in commands.run_command("unload")
    assert "no model is loaded" in commands.run_command("unload")
