"""
Tests verifying status dashboard and /ignite command truthfulness:
- Enforces SYS-024 Claims Firewall: No refuted or unmeasured claims presented as physical invariants.
- Enforces SYS-026 NCLM Speaking Gate telemetry reporting.
- Enforces agreement between /ignite banner and metamorphosis engine.
"""

import io
import sys
from unittest.mock import patch
import pytest

from osiris_cli.osiris_repl import OsirisReplState, display_status, execute_ignite


def test_display_status_truthfulness_and_claims_firewall():
    """Verify that display_status does not emit refuted or unmeasured claims as live invariants."""
    state = OsirisReplState()
    buf = io.StringIO()
    
    with patch("sys.stdout", buf):
        display_status(state)
        
    output = buf.getvalue()

    # SYS-024 Claims Firewall: Refuted/unmeasured claims must NOT appear as live invariants
    assert "Resonance Angle: 51.843°" not in output
    assert "Pyramid face slope arctan(14/11)" not in output
    assert "Memory Invariant: Λ_Φ" not in output
    assert "Peak Fidelity  : F_max" not in output
    assert "Substrate State: COLD (Run /ignite)" not in output
    assert "11D CRSM" not in output

    # Must report real empirical telemetry
    assert "Substrate Node : Node Alpha" in output
    assert "AST Firewall   :" in output
    assert "SYS-025" in output
    assert "Coherence Floor:" in output
    assert "Genome State   :" in output
    assert "Mentor Engine  :" in output
    assert "NCLM-1 Voice   :" in output
    assert "SYS-026" in output
    assert "Claims Firewall: 40 registered claims | 5 REFUTED · 3 ARTIFACT · 1 NOT_MEASURED (SYS-024 Enforced)" in output


def test_execute_ignite_truthfulness_and_banner_harmony():
    """Verify that execute_ignite banner does not emit contradictory 11D CRSM claims."""
    state = OsirisReplState()
    buf = io.StringIO()
    
    with patch("sys.stdout", buf):
        res = execute_ignite(state)
        
    output = buf.getvalue()

    # Contradictory pseudo-scientific claims must NOT appear
    assert "11D CRSM Substrate LOCKED & OPERATIONAL" not in output
    assert "Clifford Substrate: Cl(3,0)" not in output
    assert "Locking Resonance: θ_lock = 51.843°" not in output
    assert "Memory Invariant: Λ_Φ" not in output

    # Substrate and mesh verification must agree with real Node Alpha edge runtime
    assert "Physical Substrate: Node Alpha Mobile Edge" in output
    assert "Vector Hardware:  ARMv8-A NEON SIMD" in output
    assert "AST Firewall:     CIL L0-L6 Interposition Active [SYS-025 ENFORCED FAIL-CLOSED]" in output
    assert "Cognitive Substrate: Mentor Engine & NCLM-1 Speaking Gate" in output
    assert "SYS-026" in output
    assert "DELIBERATIVE MESH READY" in output
    assert res["status"] == "SUCCESS"
    assert "event_hash" in res


def test_execute_ignite_dry_run():
    """Verify that execute_ignite with dry_run=True applies zero mutations and does not log events."""
    state = OsirisReplState()
    initial_ledger_len = len(state.evidence_ledger)
    buf = io.StringIO()

    with patch("sys.stdout", buf):
        res = execute_ignite(state, dry_run=True)

    output = buf.getvalue()

    assert "[IGNITION::DRY-RUN]" in output
    assert "Edge substrate verified; zero mutations applied." in output
    assert res["status"] == "DRY_RUN"
    assert res["verified"] is True
    assert res["promoted_count"] == 0
    assert len(state.evidence_ledger) == initial_ledger_len
    assert state.ignited is False
