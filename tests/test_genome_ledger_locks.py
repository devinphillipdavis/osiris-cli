"""GenomeLedger.append waits for both locks a genome-ledger writer can hold: chain_lock's lock on
the ledger itself (MemoryLineageAgent and other chain_lock writers) and the <ledger>.lock sidecar
(older copies of genome_ledger.py, e.g. the one Termux runs)."""
import fcntl
import json
import os
import threading

import pytest

import genome_ledger as gl
from osiris_cli import chain_lock

FIXTURE_LEDGER = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures", "dnalang_ledger_v0_2_0.py")
WAIT_S = 0.3


@pytest.fixture(autouse=True)
def _dnalang_ledger_source(monkeypatch):
    if not os.path.exists(gl.LEDGER_SRC):
        monkeypatch.setattr(gl, "LEDGER_SRC", FIXTURE_LEDGER)
        monkeypatch.setattr(gl, "_ledger_mod", None)


def _rows(path):
    with open(path, encoding="utf-8") as f:
        return [json.loads(ln) for ln in f if ln.strip()]


def _append_while_held(led, hold):
    """Starts led.append in a thread while `hold` is entered; returns (blocked_while_held, rows_while_held)."""
    done = threading.Event()
    errors = []

    def writer():
        try:
            led.append("second", {"n": 2})
        except BaseException as e:  # surfaced below, not swallowed
            errors.append(e)
        finally:
            done.set()

    with hold():
        t = threading.Thread(target=writer)
        t.start()
        blocked = not done.wait(WAIT_S)
        rows_while_held = len(_rows(led.filepath))
    t.join(10)
    assert not errors, errors
    return blocked, rows_while_held


def _assert_one_chain(led):
    rows = _rows(led.filepath)
    assert [r["kind"] for r in rows] == ["first", "second"]
    assert rows[1]["prev"] == rows[0]["hash"]
    assert led.verify()


def test_append_waits_for_a_chain_lock_writer(tmp_path):
    led = gl.GenomeLedger(str(tmp_path / "genome_ledger.jsonl"))
    led.append("first", {"n": 1})

    def hold():
        return chain_lock.locked_tail(led.filepath)

    blocked, rows_while_held = _append_while_held(led, hold)
    assert blocked and rows_while_held == 1
    _assert_one_chain(led)


def test_append_waits_for_an_older_copy_holding_the_sidecar(tmp_path):
    led = gl.GenomeLedger(str(tmp_path / "genome_ledger.jsonl"))
    led.append("first", {"n": 1})

    class hold:
        def __enter__(self):
            self.f = open(led.filepath + ".lock", "w")
            fcntl.flock(self.f, fcntl.LOCK_EX)

        def __exit__(self, *exc):
            fcntl.flock(self.f, fcntl.LOCK_UN)
            self.f.close()

    blocked, rows_while_held = _append_while_held(led, hold)
    assert blocked and rows_while_held == 1
    _assert_one_chain(led)


def test_append_refuses_a_torn_tail_without_writing(tmp_path):
    led = gl.GenomeLedger(str(tmp_path / "genome_ledger.jsonl"))
    led.append("first", {"n": 1})
    with open(led.filepath, "a", encoding="utf-8") as f:
        f.write('{"torn": ')
    size = os.path.getsize(led.filepath)
    with pytest.raises(chain_lock.ChainTailError):
        led.append("second", {"n": 2})
    assert os.path.getsize(led.filepath) == size
