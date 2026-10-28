#!/usr/bin/env python3
"""
tests/test_gap_analyzer.py
10-Scenario Deterministic Acceptance Test Suite for CapabilityGapAnalyzer.

Pure and offline: the capability and backend names are fixture strings; nothing is
called or submitted.
"""

import math
from dataclasses import replace

from osiris_cli.gap_analyzer import (
    AnalysisInput,
    CapabilityGapAnalyzer,
    CapabilitySpec,
    ContextFact,
    ContextRequirement,
    Disposition,
    GapKind,
    PolicyAssessment,
    PolicyState,
    ProposedStep,
    compute_action_fingerprint,
)


def _baseline_fixture() -> AnalysisInput:
    cap = CapabilitySpec(
        capability_id="qpu.scimitar.angle_sweep",
        required_inputs=("backend", "shots"),
        context_requirements=(
            ContextRequirement(key="calibration_spc_status", max_age_seconds=300.0, require_snapshot_match=True),
        ),
        supported_targets=("NODE_ALPHA_EDGE", "NODE_BETA_WORKSTATION"),
        required_verifiers=("pytest_spc_gate",),
        enabled=True,
    )
    step = ProposedStep(
        step_id="step-001",
        capability_id="qpu.scimitar.angle_sweep",
        target_node="NODE_ALPHA_EDGE",
        parameters={"backend": "ibm_brisbane", "shots": 4000},
        workspace_snapshot_id="95d0acb5",
        intent_confidence=0.95,
    )
    fp = compute_action_fingerprint(step)
    fact = ContextFact(
        key="calibration_spc_status",
        value={"drift_detected": False},
        observed_at_epoch=1000.0,
        snapshot_id="95d0acb5",
    )
    return AnalysisInput(
        step=step,
        current_epoch=1100.0,
        active_snapshot_id="95d0acb5",
        registered_capabilities={cap.capability_id: cap},
        available_targets=frozenset({"NODE_ALPHA_EDGE", "NODE_BETA_WORKSTATION"}),
        available_verifiers=frozenset({"pytest_spc_gate"}),
        context_facts=(fact,),
        policy=PolicyAssessment(state=PolicyState.ALLOWED, bound_action_fingerprint=fp),
    )


def _with_step(inp: AnalysisInput, **changes) -> AnalysisInput:
    """Change the step and re-bind the approval to it, isolating the gap under test."""
    step = replace(inp.step, **changes)
    policy = replace(inp.policy, bound_action_fingerprint=compute_action_fingerprint(step))
    return replace(inp, step=step, policy=policy)


def _with_capability(inp: AnalysisInput, **changes) -> AnalysisInput:
    cap = replace(inp.registered_capabilities[inp.step.capability_id], **changes)
    return replace(inp, registered_capabilities={cap.capability_id: cap})


def _kinds(report):
    return [g.kind for g in report.gaps]


# Scenario 1
def test_baseline_is_ready():
    inp = _baseline_fixture()
    report = CapabilityGapAnalyzer.analyze(inp)
    assert report.disposition == Disposition.READY
    assert report.gaps == ()
    assert report.is_ready
    assert report.step_id == "step-001"
    assert report.action_fingerprint == compute_action_fingerprint(inp.step)


# Scenario 2
def test_fingerprint_is_canonical_and_payload_bound():
    step = _baseline_fixture().step
    fp = compute_action_fingerprint(step)
    assert len(fp) == 64 and int(fp, 16) >= 0

    reordered = replace(step, parameters={"shots": 4000, "backend": "ibm_brisbane"})
    assert compute_action_fingerprint(reordered) == fp
    assert compute_action_fingerprint(replace(step, step_id="step-999")) == fp

    for changed in (
        replace(step, parameters={"backend": "ibm_brisbane", "shots": 4001}),
        replace(step, workspace_snapshot_id="a1b2c3d4"),
        replace(step, target_node="NODE_BETA_WORKSTATION"),
        replace(step, capability_id="qpu.scimitar.other"),
    ):
        assert compute_action_fingerprint(changed) != fp


# Scenario 3
def test_approval_does_not_survive_a_payload_change():
    inp = _baseline_fixture()
    mutated = replace(inp, step=replace(inp.step, parameters={"backend": "ibm_brisbane", "shots": 8000}))
    report = CapabilityGapAnalyzer.analyze(mutated)
    assert report.disposition == Disposition.NEEDS_POLICY
    assert [(g.kind, g.subject) for g in report.gaps] == [
        (GapKind.POLICY_UNEVALUATED, "SYS-021::FINGERPRINT_MISMATCH")
    ]

    unbound = replace(inp, policy=PolicyAssessment(state=PolicyState.ALLOWED))
    assert CapabilityGapAnalyzer.analyze(unbound).disposition == Disposition.NEEDS_POLICY


# Scenario 4
def test_low_or_nan_intent_confidence_needs_clarification():
    inp = _baseline_fixture()
    for confidence in (0.40, math.nan):
        report = CapabilityGapAnalyzer.analyze(_with_step(inp, intent_confidence=confidence))
        assert report.disposition == Disposition.NEEDS_CLARIFICATION
        assert _kinds(report) == [GapKind.INTENT_AMBIGUITY]


# Scenario 5
def test_missing_or_blank_input_needs_clarification():
    inp = _with_step(_baseline_fixture(), parameters={"backend": "   "})
    report = CapabilityGapAnalyzer.analyze(inp)
    assert report.disposition == Disposition.NEEDS_CLARIFICATION
    assert [(g.kind, g.subject) for g in report.gaps] == [
        (GapKind.MISSING_INPUT, "backend"),
        (GapKind.MISSING_INPUT, "shots"),
    ]


# Scenario 6
def test_missing_and_stale_context_need_context():
    inp = _baseline_fixture()

    missing = CapabilityGapAnalyzer.analyze(replace(inp, context_facts=()))
    assert missing.disposition == Disposition.NEEDS_CONTEXT
    assert _kinds(missing) == [GapKind.MISSING_CONTEXT]

    stale = CapabilityGapAnalyzer.analyze(replace(inp, current_epoch=1400.0))
    assert stale.disposition == Disposition.NEEDS_CONTEXT
    assert _kinds(stale) == [GapKind.STALE_CONTEXT]
    assert "400.0s exceeds max_age 300.0s" in stale.gaps[0].detail


# Scenario 7
def test_snapshot_mismatch_needs_context():
    inp = _baseline_fixture()
    moved = CapabilityGapAnalyzer.analyze(replace(inp, active_snapshot_id="a1b2c3d4"))
    assert moved.disposition == Disposition.NEEDS_CONTEXT
    assert [(g.kind, g.subject) for g in moved.gaps] == [
        (GapKind.SNAPSHOT_MISMATCH, "calibration_spc_status"),
        (GapKind.SNAPSHOT_MISMATCH, "workspace_snapshot_id"),
    ]


def test_step_without_a_snapshot_is_not_ready():
    report = CapabilityGapAnalyzer.analyze(_with_step(_baseline_fixture(), workspace_snapshot_id=""))
    assert report.disposition == Disposition.NEEDS_CONTEXT
    assert [(g.kind, g.subject) for g in report.gaps] == [
        (GapKind.SNAPSHOT_MISMATCH, "workspace_snapshot_id")
    ]


# Scenario 8
def test_contradictory_evidence_at_active_snapshot_blocks():
    inp = _baseline_fixture()
    conflicting = ContextFact(
        key="calibration_spc_status",
        value={"drift_detected": True},
        observed_at_epoch=1050.0,
        snapshot_id="95d0acb5",
    )
    report = CapabilityGapAnalyzer.analyze(replace(inp, context_facts=inp.context_facts + (conflicting,)))
    assert report.disposition == Disposition.BLOCKED
    assert _kinds(report) == [GapKind.CONTRADICTORY_EVIDENCE]


def test_refreshed_fact_from_an_older_snapshot_is_not_a_contradiction():
    inp = _baseline_fixture()
    superseded = ContextFact(
        key="calibration_spc_status",
        value={"drift_detected": True},
        observed_at_epoch=900.0,
        snapshot_id="0ld5nap0",
    )
    report = CapabilityGapAnalyzer.analyze(replace(inp, context_facts=(superseded,) + inp.context_facts))
    assert report.disposition == Disposition.READY
    assert report.gaps == ()


# Scenario 9
def test_unavailable_capability_target_or_verifier_blocks():
    inp = _baseline_fixture()
    cases = [
        (replace(inp, registered_capabilities={}), GapKind.CAPABILITY_UNAVAILABLE),
        (_with_capability(inp, enabled=False), GapKind.CAPABILITY_UNAVAILABLE),
        (replace(inp, available_targets=frozenset({"NODE_BETA_WORKSTATION"})), GapKind.EXECUTION_UNAVAILABLE),
        (_with_capability(inp, supported_targets=("NODE_BETA_WORKSTATION",)), GapKind.EXECUTION_UNAVAILABLE),
        (replace(inp, available_verifiers=frozenset()), GapKind.VERIFICATION_UNAVAILABLE),
    ]
    for case, kind in cases:
        report = CapabilityGapAnalyzer.analyze(case)
        assert report.disposition == Disposition.BLOCKED
        assert _kinds(report) == [kind]


# Scenario 10
def test_policy_states_and_disposition_precedence():
    inp = _baseline_fixture()
    fp = compute_action_fingerprint(inp.step)

    assert CapabilityGapAnalyzer.analyze(replace(inp, policy=None)).disposition == Disposition.NEEDS_POLICY
    unevaluated = replace(inp, policy=PolicyAssessment(state=PolicyState.UNEVALUATED))
    assert CapabilityGapAnalyzer.analyze(unevaluated).disposition == Disposition.NEEDS_POLICY

    waiting = CapabilityGapAnalyzer.analyze(
        replace(inp, policy=PolicyAssessment(state=PolicyState.APPROVAL_REQUIRED))
    )
    assert waiting.disposition == Disposition.WAITING_APPROVAL
    assert fp[:12] in waiting.gaps[0].remediation

    # A denial outranks every other gap, and the gap order is fixed by kind.
    denied = replace(
        inp,
        step=replace(inp.step, parameters={"backend": "ibm_brisbane"}, intent_confidence=0.10),
        policy=PolicyAssessment(state=PolicyState.DENIED, reason="Outside approved scope."),
    )
    report = CapabilityGapAnalyzer.analyze(denied)
    assert report.disposition == Disposition.BLOCKED
    assert _kinds(report) == [GapKind.POLICY_DENIED, GapKind.INTENT_AMBIGUITY, GapKind.MISSING_INPUT]
    assert report.gaps[0].detail == "Outside approved scope."
    assert CapabilityGapAnalyzer.analyze(denied) == report
