"""
Unit test suite verifying remediation of Node Alpha audit findings:
1. Mentor round reachability preflight & scorecard integrity exclusions (no infrastructure failures scored as model fails).
2. NBA (Next Best Action) reachability guard preventing recommendations of unreachable backends.
3. Claims Firewall compliance on /mesh (SYS-024).
4. PowerGovernor fail-open mode and ledger event logging.
5. runpy RuntimeWarning elimination via lazy loading.
6. Organism baseline dual-reporting (nats and bpb vs unigram baseline).
"""

import io
import json
import os
import subprocess
import sys
from unittest.mock import MagicMock, patch
import pytest

import protege
import osiris_termux_console as console
from osiris_cli.osiris_repl import SESSION, PowerGovernor, execute_mesh


def test_scorecard_integrity_exclusions_and_quarantine():
    """Verify that 0.0s unreachable rounds and quarantined runs are excluded from capability scores."""
    entries, problem = protege.load_ledger()
    assert not problem, f"Ledger error: {problem}"
    
    suite = protege.current_suite()
    runner = protege.current_runner()
    cands, skipped = protege.candidates(entries, suite, runner)
    card = protege.scorecard(cands)
    
    # qwen2.5-coder:7b must have exactly 3 scored attempts (from the genuine 420s run) and 3 integrity exclusions
    qwen_key = "ollama/qwen2.5-coder:7b"
    assert qwen_key in card, f"{qwen_key} missing from scorecard: {list(card.keys())}"
    m = card[qwen_key]
    
    assert m["candidates"] == 3, f"Expected 3 candidates, got {m['candidates']}"
    assert m["verified"] == 0, f"Expected 0 verified, got {m['verified']}"
    assert m["integrity_excluded"] == 3, f"Expected 3 integrity exclusions, got {m['integrity_excluded']}"
    assert m["no_output"] == 3, f"Expected 3 no_output, got {m['no_output']}"
    
    # Wilson interval for 0/3 must be 0.00 to 0.56
    lo, hi = m["ci"]
    assert round(lo, 2) == 0.00
    assert round(hi, 2) == 0.56
    
    formatted = protege.format_scorecard(card, skipped, suite)
    assert "0/3   Wilson 95% 0.00-0.56" in formatted
    assert "integrity exclusions   3   (missing/unreachable evidence; not scored)" in formatted


def test_next_mentor_round_guards_unreachable_ollama():
    """Verify Next Best Action never recommends local benchmarks when Ollama is offline."""
    with patch("osiris_termux_console._ollama_models", return_value=None):
        nb = console._next_mentor_round(protege)
        assert nb is None, f"Expected None when Ollama is unreachable, got {nb}"
        
        # In _next_best(), verify it falls through away from local bench
        action = console._next_best()
        assert not action["cmd"].startswith("/bench") or "gemini" in action["cmd"]


def test_bench_preflight_blocks_unreachable_backend(capsys):
    """Verify _bench and _bench_preflight fail-closed if Ollama is unreachable."""
    with patch("osiris_termux_console._ollama_models", return_value=None):
        console._bench("/bench")
        out = capsys.readouterr().out
        assert "BACKEND UNREACHABLE" in out
        assert "Ollama daemon is offline" in out
        assert "Refusing" in out and "evidence ledger contamination" in out
        
        console._bench("/bench now")
        out_now = capsys.readouterr().out
        assert "BACKEND UNREACHABLE" in out_now


def test_mesh_enforces_sys024_claims_firewall(capsys):
    """Verify execute_mesh() labels 9-agent cognitive mesh under SYS-024 Claims Firewall."""
    execute_mesh()
    out = capsys.readouterr().out
    assert "SYS-024" in out
    assert "MODEL_PROPOSED / DELIBERATION ROLES" in out
    assert "Simulation Persona Scaffold" in out
    assert "Empirical verification required" in out


def test_power_governor_fail_open_and_ledger_event():
    """Verify PowerGovernor reports fail-open mode and logs POWER_SENSOR_OUTAGE to evidence ledger."""
    SESSION.evidence_ledger.clear()
    
    with patch("subprocess.run", side_effect=Exception("Sensor offline")), \
         patch.dict(os.environ, {"TERMUX_VERSION": "0.118.0"}):
        gov = PowerGovernor()
        gov._is_termux = True
        dec = gov.check()
        assert dec.allowed is True
        assert "operating in fail-open mode" in dec.reason
        
        # Verify POWER_SENSOR_OUTAGE logged in SESSION.evidence_ledger
        events = [e for e in SESSION.evidence_ledger if e["event_type"] == "POWER_SENSOR_OUTAGE"]
        assert len(events) == 1
        assert events[0]["details"]["mode"] == "FAIL_OPEN"
        assert "offline" in events[0]["details"]["reason"]


def test_runpy_runtime_warning_eliminated():
    """Verify running osiris_repl as module emits zero runpy RuntimeWarnings."""
    cmd = [
        sys.executable,
        "-W", "error::RuntimeWarning",
        "-m", "osiris_cli.osiris_repl",
        "--help"
    ]
    res = subprocess.run(cmd, capture_output=True, text=True)
    assert res.returncode == 0
    assert "RuntimeWarning" not in res.stderr


def test_organism_status_dual_baseline_reporting(capsys):
    """Verify _organism_status reports mean loss in nats alongside unigram baseline comparison."""
    with patch.dict(console._organism_state, {
        "model": "dummy",
        "step": 42,
        "history": [6.2, 6.0, 5.8, 5.5, 5.3, 5.0, 4.8, 4.6, 4.4, 4.2]
    }):
        console._organism_status()
        out = capsys.readouterr().out
        assert "ORGANISM STATUS" in out
        assert "nats" in out
        assert "vs 5.08 unigram baseline" in out
