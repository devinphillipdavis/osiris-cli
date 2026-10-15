"""
Tests for L0-L5 Governed Subsystems
===================================
Verifies TaskRunRecord (L0), IntentRouter (L1), SprintManager (L2),
EvidenceProvenanceRegistry (L3), MultiCandidateGenerator (L4), and
IndependentCriticVerifier (L5).
"""

import time
import pytest

from osiris_cli.orchestration import (
    CandidateStrategy,
    EvidenceProvenanceRegistry,
    IndependentCriticVerifier,
    IntentRouter,
    MultiCandidateGenerator,
    RiskTier,
    SprintManager,
    TaskRunRecord,
    TaskSpec,
    CodeProposal,
)
from osiris_cli.providers import GemmaProvider


def test_l0_task_run_record():
    task = TaskSpec(task_id="task_001", title="Test Task", spec="Do test")
    run = TaskRunRecord(task_spec=task, granted_permissions=["fs:read"], token_budget=100)

    assert run.run_id.startswith("run_")
    assert run.can_perform("fs:read") is True
    assert run.can_perform("fs:write") is False

    run.start()
    assert run.status == "ACTIVE"

    # Token budget test
    ok = run.record_token_usage(50)
    assert ok is True
    assert run.tokens_used == 50

    # Exceed budget
    ok = run.record_token_usage(60)
    assert ok is False
    assert run.status == "BLOCKED"

    # Walltime check
    assert run.check_walltime() is True


def test_l1_intent_router():
    router = IntentRouter()

    # Read-only query
    d1 = router.evaluate("show /status of the quantum sim")
    assert d1.risk_tier == RiskTier.TIER_1_CLEAN
    assert d1.cost_of_error == 0.0
    assert d1.requires_human_grant is False

    # Mutating command
    d2 = router.evaluate("apply patch to add new module")
    assert d2.risk_tier == RiskTier.TIER_3_MUTATING
    assert d2.cost_of_error == 0.60
    assert d2.requires_human_grant is True
    assert "GATE_PAYLOAD_GRANT" in d2.required_gates

    # Critical security target
    d3 = router.evaluate("modify policy.json to disable firewall")
    assert d3.risk_tier == RiskTier.TIER_4_CRITICAL
    assert d3.cost_of_error == 0.95
    assert d3.requires_human_grant is True
    assert "GATE_AST_FIREWALL" in d3.required_gates


def test_l2_sprint_manager():
    mgr = SprintManager(default_max_steps=5)
    sprint = mgr.create_sprint("sprint_001")

    # Step advancing
    sprint.advance_step({"accuracy": 0.8}, loss=0.50)
    assert sprint.current_step == 1
    stop, _ = sprint.should_stop()
    assert stop is False

    # Simulate convergence
    sprint.advance_step({}, loss=0.450)
    sprint.advance_step({}, loss=0.451)
    sprint.advance_step({}, loss=0.452)
    stop, reason = sprint.should_stop()
    assert stop is True
    assert "Converged" in reason


def test_l3_evidence_provenance():
    reg = EvidenceProvenanceRegistry()
    content = b"measured_fidelity = 0.9823; tau = 46.9787us"
    rec = reg.register_evidence(
        claim_id="CLAIM-QUANTUM-001",
        source_artifact="results/flywheel_proof.json",
        content_bytes=content,
        verified_by="pytest:test_flywheel",
    )

    assert rec.claim_id == "CLAIM-QUANTUM-001"
    assert rec.artifact_hash is not None
    assert reg.verify_provenance("CLAIM-QUANTUM-001", content) is True
    assert reg.verify_provenance("CLAIM-QUANTUM-001", b"tampered_data") is False

    merkle_root = reg.compute_merkle_root()
    assert len(merkle_root) == 64


def test_l4_multi_candidate_generation():
    provider = GemmaProvider(model="gemma-3-1b", mode="mock")
    gen = MultiCandidateGenerator(provider)
    task = TaskSpec(task_id="task_404", title="Compute Fib", spec="Fibonacci sequence", target_files=["fib.py"])

    c_set = gen.generate_candidates(task)
    assert c_set.get_candidate(CandidateStrategy.BASELINE) is not None
    assert c_set.get_candidate(CandidateStrategy.ALTERNATIVE) is not None
    assert c_set.get_candidate(CandidateStrategy.CONSERVATIVE) is not None

    base_prop = c_set.get_candidate(CandidateStrategy.BASELINE)
    assert len(base_prop.payload_digest()) == 64


def test_l5_independent_critic_verifier():
    verifier = IndependentCriticVerifier()

    # Clean proposal
    p_clean = CodeProposal(
        proposal_id="p1",
        task_id="t1",
        target_file="src/math_ops.py",
        module_code="def add(a: int, b: int) -> int:\n    return a + b\n",
        test_code="def test_add():\n    assert True\n",
    )
    r1 = verifier.verify_proposal(p_clean)
    assert r1.overall_verdict == "PASS"
    assert r1.static_ast_pass is True

    # Malicious proposal with os.system
    p_bad = CodeProposal(
        proposal_id="p2",
        task_id="t2",
        target_file="src/exploit.py",
        module_code="import os\nos.system('rm -rf /')\n",
        test_code="",
    )
    r2 = verifier.verify_proposal(p_bad)
    assert r2.overall_verdict == "FAIL"
    assert r2.static_ast_pass is False
    assert any("banned_call" in b for b in r2.banned_constructs_found)

    # Proposal targeting immutable file
    p_imm = CodeProposal(
        proposal_id="p3",
        task_id="t3",
        target_file="policy.json",
        module_code='{"allow_all": true}',
        test_code="",
    )
    r3 = verifier.verify_proposal(p_imm)
    assert r3.overall_verdict == "BLOCKED"
    assert "immutable_target_violation" in r3.banned_constructs_found
