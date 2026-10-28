"""chain_lock: concurrent writers never fork a hash-chained ledger, and an unreadable tail
blocks the append instead of being replaced with a guess."""

import hashlib
import json
import multiprocessing
import os

import pytest

from osiris_cli import chain_lock
from osiris_cli.probes import verify_chain

GENESIS = "0" * 64
FIXTURE_LEDGER = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures", "dnalang_ledger_v0_2_0.py")


def _exchange_entry(i):
    def build(last):
        entry = {"t": i, "user": f"msg {i}", "prev": last["hash"] if last else GENESIS}
        body = json.dumps(entry, sort_keys=True, ensure_ascii=False)
        entry["hash"] = hashlib.sha256(body.encode()).hexdigest()
        return entry
    return build


def _writer(path, start, count):
    for i in range(start, start + count):
        chain_lock.append_chained(path, _exchange_entry(i), ensure_ascii=False)


def test_concurrent_processes_never_fork(tmp_path):
    path = str(tmp_path / "exchanges.jsonl")
    ctx = multiprocessing.get_context("fork" if hasattr(os, "fork") else "spawn")
    procs = [ctx.Process(target=_writer, args=(path, k * 1000, 40)) for k in range(4)]
    for p in procs:
        p.start()
    for p in procs:
        p.join(60)
        assert p.exitcode == 0
    report = verify_chain(path)
    assert report["intact"] and report["entries"] == 160
    assert report["forks"] == []


def test_unreadable_tail_blocks_the_append(tmp_path):
    path = tmp_path / "ledger.jsonl"
    chain_lock.append_chained(str(path), _exchange_entry(0))
    with open(path, "a", encoding="utf-8") as f:
        f.write('{"torn": ')                              # a write cut short
    before = path.read_bytes()
    with pytest.raises(chain_lock.ChainTailError):
        chain_lock.append_chained(str(path), _exchange_entry(1))
    assert path.read_bytes() == before


def test_tail_without_a_hash_blocks(tmp_path):
    path = tmp_path / "ledger.jsonl"
    path.write_text('{"no": "hash"}\n')
    with pytest.raises(chain_lock.ChainTailError):
        chain_lock.append_chained(str(path), _exchange_entry(0))


def test_long_last_line_is_read_from_the_end(tmp_path):
    path = str(tmp_path / "ledger.jsonl")
    chain_lock.append_chained(path, _exchange_entry(0))
    big = _exchange_entry(1)
    chain_lock.append_chained(path, lambda last: dict(big(last), user="x" * 300_000))
    with open(path, "rb") as f:
        tail = chain_lock.read_tail(f, block=4096)
    assert tail["t"] == 1 and len(tail["user"]) == 300_000


def test_sidecar_lock_when_flock_is_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(chain_lock, "fcntl", None)
    path = str(tmp_path / "ledger.jsonl")
    _writer(path, 0, 3)
    assert verify_chain(path)["entries"] == 3
    assert not os.path.exists(path + ".lock")
    open(path + ".lock", "w").close()                     # another writer holds it
    with pytest.raises(chain_lock.ChainLockTimeout):
        with chain_lock.locked_tail(path, timeout_s=0.2):
            pass


# ── the ledgers that use it ────────────────────────────────────────────────────

def test_learning_ledger_chains_and_blocks_on_a_torn_tail(tmp_path):
    from osiris_cli import paste_learning

    home = str(tmp_path)
    h1 = paste_learning.append_learning_ledger(home, "A", {})
    h2 = paste_learning.append_learning_ledger(home, "B", {})
    rows = [json.loads(ln) for ln in open(paste_learning.get_learning_ledger_path(home))]
    assert [r["prev_hash"] for r in rows] == [GENESIS, h1] and rows[1]["hash"] == h2
    with open(paste_learning.get_learning_ledger_path(home), "a") as f:
        f.write("garbage")
    with pytest.raises(chain_lock.ChainTailError):
        paste_learning.append_learning_ledger(home, "C", {})


def _genome_ledger_module(monkeypatch):
    """genome_ledger, falling back to the pinned dnalang ledger.py when dnalang-core is absent."""
    import genome_ledger as gl

    if not os.path.exists(gl.LEDGER_SRC):
        monkeypatch.setattr(gl, "LEDGER_SRC", FIXTURE_LEDGER)
        monkeypatch.setattr(gl, "_ledger_mod", None)
    return gl


def test_lineage_agent_chains(tmp_path, monkeypatch):
    from osiris_cli.orchestration.agents import MemoryLineageAgent

    gl = _genome_ledger_module(monkeypatch)
    agent = MemoryLineageAgent(str(tmp_path / "genome_ledger.jsonl"))
    h1 = agent.record_event("X", {"a": 1})
    gl.GenomeLedger(agent.ledger_file).append("file_change", {"path": "f.py"})
    agent.record_event("Y", {})
    rows = [json.loads(ln) for ln in open(agent.ledger_file)]
    assert [r["kind"] for r in rows] == ["X", "file_change", "Y"]
    assert rows[1]["prev"] == h1 and rows[2]["prev"] == rows[1]["hash"]
    assert gl.GenomeLedger(agent.ledger_file).verify()


def test_lineage_agent_writes_nothing_without_dnalang(tmp_path, monkeypatch):
    import genome_ledger as gl
    from osiris_cli.orchestration.agents import MemoryLineageAgent

    monkeypatch.setattr(gl, "LEDGER_SRC", str(tmp_path / "missing" / "ledger.py"))
    monkeypatch.setattr(gl, "_ledger_mod", None)
    agent = MemoryLineageAgent(str(tmp_path / "genome_ledger.jsonl"))
    with pytest.raises(FileNotFoundError):
        agent.record_event("X", {"a": 1})
    assert not os.path.exists(agent.ledger_file)


def test_gemini_ledger_still_verifies(tmp_path):
    from osiris_cli.gemini_gateway import Ledger

    led = Ledger(str(tmp_path / "g.jsonl"))
    led.append("SENT", {"n": 1})
    led.append("RESULT", {"n": 2})
    assert led.verify() == (True, "ok")


def test_exchange_log_blocks_on_a_torn_tail(tmp_path):
    from osiris_cli.living import Osiris

    o = Osiris(core=None, mentor=None, home=str(tmp_path), out=lambda s: None, background=False)
    o._record({"t": "1", "user": "a"})
    with open(o.log_path, "a") as f:
        f.write("{")
    with pytest.raises(chain_lock.ChainTailError):
        o._record({"t": "2", "user": "b"})
