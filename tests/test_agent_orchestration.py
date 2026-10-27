"""
Tests for OSIRIS Governed Multi-Agent Orchestration Platform
============================================================
Verifies:
  - Intent classification and architectural decomposition
  - AST Firewall (SYS-025) blocking exec, eval, os.system, subprocess(shell=True)
  - Scope protection for immutable governance files
  - Payload-bound grant authorization (SYS-021)
  - End-to-end pipeline execution and audit receipt chain
"""

import os
import time
import pytest

from osiris_cli.orchestration import (
    CodeProposal,
    ExecutionGrant,
    GovernanceController,
    GovernedAgentEngine,
    IntentAgent,
    IntentProposal,
    TaskSpec,
)
from osiris_cli.providers import GemmaProvider

FIXTURE_LEDGER = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures", "dnalang_ledger_v0_2_0.py")


def test_intent_agent_classification():
    """Verify intent agent maps prompts into typed proposals with domains."""
    agent = IntentAgent()
    p1 = agent.interpret("Implement a Clifford gate optimizer")
    assert p1.intent_type == "code_modification"

    p2 = agent.interpret("Run benchmark suite on qvm quantum simulator")
    assert p2.intent_type in ("research", "benchmark")
    assert p2.domain == "quantum"


def test_ast_firewall_blocks_forbidden_calls():
    """Verify SYS-025 AST Firewall rejects exec, eval, os.system, compile, subprocess(shell=True)."""
    # Clean code passes
    clean_code = "def add(a, b):\n    return a + b\n"
    ok, violations = GovernanceController.inspect_ast(clean_code)
    assert ok is True
    assert len(violations) == 0

    # exec() rejected
    bad_exec = "def attack():\n    exec('import os; os.system(\"rm -rf /\")')\n"
    ok, violations = GovernanceController.inspect_ast(bad_exec)
    assert ok is False
    assert any("Forbidden call: 'exec'" in v for v in violations)

    # eval() rejected
    bad_eval = "x = eval('2 + 2')\n"
    ok, violations = GovernanceController.inspect_ast(bad_eval)
    assert ok is False
    assert any("Forbidden call: 'eval'" in v for v in violations)

    # os.system() rejected
    bad_os = "import os\nos.system('echo pwned')\n"
    ok, violations = GovernanceController.inspect_ast(bad_os)
    assert ok is False
    assert any("Forbidden os call: 'os.system'" in v for v in violations)

    # subprocess with shell=True rejected
    bad_sp = "import subprocess\nsubprocess.run('ls', shell=True)\n"
    ok, violations = GovernanceController.inspect_ast(bad_sp)
    assert ok is False
    assert any("shell=True" in v for v in violations)


def test_scope_protection_blocks_governance_files():
    """Verify target scope rejects attempts to mutate immutable governance files."""
    for forbidden in ["policy.json", "cloudbuild.yaml", "QUARANTINE_NOTICE.md", "GEMINI.md"]:
        ok, msg = GovernanceController.verify_target_scope(f"/root/{forbidden}")
        assert ok is False
        assert "immutable governance artifact" in msg


def test_payload_bound_authorization_sys021():
    """Verify SYS-021 strictly binds authorization to exact payload digest."""
    proposal = CodeProposal(
        proposal_id="p-001",
        task_id="t-001",
        target_file="module.py",
        module_code="def valid():\n    return 42\n",
        test_code="def test_valid():\n    assert valid() == 42\n",
    )
    correct_digest = proposal.payload_digest()

    # 1. Valid grant
    valid_grant = ExecutionGrant(
        grant_id="grant-101",
        payload_digest=correct_digest,
        authorized_by="operator",
        authorized_at=time.time(),
        expires_at=time.time() + 300,
    )
    ok, msg = GovernanceController.authorize_execution(proposal, valid_grant)
    assert ok is True
    assert msg == "AUTHORIZED"

    # 2. Grant with mismatched digest (tampered code)
    tampered_grant = ExecutionGrant(
        grant_id="grant-102",
        payload_digest="0123456789abcdef" * 4,
        authorized_by="operator",
        authorized_at=time.time(),
        expires_at=time.time() + 300,
    )
    ok, msg = GovernanceController.authorize_execution(proposal, tampered_grant)
    assert ok is False
    assert "Grant digest mismatch" in msg

    # 3. Expired grant
    expired_grant = ExecutionGrant(
        grant_id="grant-103",
        payload_digest=correct_digest,
        authorized_by="operator",
        authorized_at=time.time() - 600,
        expires_at=time.time() - 300,
    )
    ok, msg = GovernanceController.authorize_execution(proposal, expired_grant)
    assert ok is False

    # 4. Missing grant fails closed
    ok, msg = GovernanceController.authorize_execution(proposal, None)
    assert ok is False
    assert "Missing execution grant" in msg


def test_end_to_end_governed_engine(tmp_path, monkeypatch):
    """Verify full governed loop: intent -> plan -> synthesis -> verification -> ledger."""
    import genome_ledger as gl

    if not os.path.exists(gl.LEDGER_SRC):  # no dnalang-core: use the pinned ledger.py
        monkeypatch.setattr(gl, "LEDGER_SRC", FIXTURE_LEDGER)
        monkeypatch.setattr(gl, "_ledger_mod", None)
    ledger_file = str(tmp_path / "test_ledger.jsonl")
    provider = GemmaProvider(model="gemma-3-1b", mode="mock")
    engine = GovernedAgentEngine(
        provider=provider,
        ledger_file=ledger_file,
        allowed_paths=[str(tmp_path)],
    )

    result = engine.run_sprint_step(
        goal="Implement simple math adder function",
        target_file=str(tmp_path / "adder.py"),
    )

    assert result["intent"].intent_type == "code_modification"
    assert result["verification"].is_passing
    assert result["authorized"] is False  # Stopped at authorization gate (no grant)
    assert len(result["payload_digest"]) == 64
    assert len(result["ledger_receipt_hash"]) == 64
    led = gl.GenomeLedger(ledger_file)
    assert led.tip() == result["ledger_receipt_hash"]
    assert led.chain[-1]["kind"] == "governed_agent_step"
    assert led.verify()

    # Now authorize with exact payload digest
    grant = ExecutionGrant(
        grant_id="grant-auth-1",
        payload_digest=result["payload_digest"],
        authorized_by="human_operator",
        authorized_at=time.time(),
        expires_at=time.time() + 60,
    )
    result_auth = engine.run_sprint_step(
        goal="Implement simple math adder function",
        target_file=str(tmp_path / "adder.py"),
        grant=grant,
    )
    assert result_auth["authorized"] is True
    assert result_auth["auth_message"] == "AUTHORIZED"
