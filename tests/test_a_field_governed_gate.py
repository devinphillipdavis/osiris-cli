from research.a_field_study.governed_gate import GateVerdict, evaluate_research_gates


def fixtures():
    invariant = "identity != interpretation != physical law != independent prediction"
    genome = {
        "organism_id": "alpha_a_field_study",
        "organism_type": "research_genome",
        "version": "1.0.0",
        "governance": {"epistemic_invariant": invariant},
        "claims": [
            {"id": "C1", "standing": "ARTIFACT", "quarantined": False, "firewall_status": "VERIFIED"},
            {"id": "C2", "standing": "HYPOTHESIS", "quarantined": True, "firewall_status": "MODEL_PROPOSED"},
        ],
        "gates": [
            {"gate_id": "GATE-01", "status": "PASS", "blocking": False},
            {"gate_id": "GATE-02", "status": "BLOCKED", "blocking": True},
            {"gate_id": "GATE-03", "status": "BLOCKED", "blocking": True},
            {"gate_id": "GATE-04", "status": "BLOCKED", "blocking": True},
        ],
    }
    receipt = {
        "organism_id": "alpha_a_field_study",
        "epistemic_invariant": invariant,
        "governance_status": {"SYS_023_evidence_recorded": True},
    }
    return genome, receipt


def test_blocked_research_gates_never_pass():
    genome, receipt = fixtures()
    result = evaluate_research_gates(genome, receipt)
    assert result.verdict is GateVerdict.BLOCKED
    assert result.passed_gate_ids == ("GATE-01",)
    assert set(result.blocked_gate_ids) == {"GATE-02", "GATE-03", "GATE-04"}


def test_receipt_mismatch_fails_closed():
    genome, receipt = fixtures()
    receipt["organism_id"] = "other-organism"
    result = evaluate_research_gates(genome, receipt)
    assert result.verdict is GateVerdict.BLOCKED
    assert any("does not match" in reason for reason in result.reasons)


def test_promotion_request_is_never_authorized_here():
    genome, receipt = fixtures()
    result = evaluate_research_gates(genome, receipt, required_gate_ids=("GATE-01",), promotion_requested=True)
    assert result.verdict is GateVerdict.BLOCKED
    assert any("promotion denied" in reason for reason in result.reasons)


def test_invalid_claim_standing_is_rejected():
    genome, receipt = fixtures()
    genome["claims"][0]["standing"] = "PROVEN_NEW_PHYSICS"
    result = evaluate_research_gates(genome, receipt)
    assert result.verdict is GateVerdict.BLOCKED
    assert any("invalid or missing standing" in reason for reason in result.reasons)


def test_missing_gate_is_blocked():
    genome, receipt = fixtures()
    genome["gates"] = [row for row in genome["gates"] if row["gate_id"] != "GATE-04"]
    result = evaluate_research_gates(genome, receipt)
    assert result.verdict is GateVerdict.BLOCKED
    assert "GATE-04" in result.blocked_gate_ids
