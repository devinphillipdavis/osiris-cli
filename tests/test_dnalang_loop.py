"""
Tests for Recursive DNA-Lang Governed Evolution Loop
====================================================
Verifies:
  - Parsing and capability allowlist enforcement
  - Rejection of unauthorized capabilities
  - Sandboxed acceptance evaluation
  - Baseline comparison and promotion gating
  - Lineage tracking and rollback references
"""

import os
import pytest

from osiris_cli.dnalang import CandidateEvolutionLoop, GenomeCandidate
from osiris.compiler.dna_ir import QuantumCircuitIR, IROperation, IROpType, QuantumRegister, ClassicalRegister


def test_dnalang_parse_and_validate():
    """Verify DNA-Lang parsing and capability allowlist."""
    loop = CandidateEvolutionLoop()

    # Valid genome
    ok, ir, reason = loop.parse_and_validate("BellState")
    assert ok is True
    assert ir is not None
    assert ir.qubit_count >= 1

    # Malformed genome
    ok, ir, reason = loop.parse_and_validate("invalid {{{ genome")
    assert ok is False
    assert "failure" in reason.lower() or "syntax" in reason.lower()


def test_dnalang_capability_rejection():
    """Verify capability allowlist rejects unauthorized operations before execution."""
    loop = CandidateEvolutionLoop()

    # Create dummy circuit with unauthorized op
    bad_circuit = QuantumCircuitIR(
        name="bad",
        quantum_registers=[QuantumRegister("q", 1)],
        classical_registers=[ClassicalRegister("c", 1)],
        operations=[IROperation(IROpType.RESET, [0])],  # RESET not in ALLOWED_CAPABILITIES
        source_organism="bad",
        lineage_hash="bad123",
    )

    class MockConverter:
        def compile(self, src):
            return bad_circuit

    loop_mock = CandidateEvolutionLoop(converter=MockConverter())
    ok, ir, reason = loop_mock.parse_and_validate("SomeSource")
    assert ok is False
    assert "Unauthorized capability" in reason


def test_dnalang_controlled_cycle_promotion(tmp_path):
    """Verify 12-step cycle: passes acceptance, improves fitness, promotes, records rollback."""
    ledger = str(tmp_path / "dnalang_lineage.jsonl")
    loop = CandidateEvolutionLoop(lineage_ledger_path=ledger)

    def acceptance_1(ir: QuantumCircuitIR):
        # Baseline acceptance: returns True with fitness 0.80
        return True, 0.80

    res1 = loop.run_cycle("Optimize Bell state circuit", acceptance_1)
    assert res1["promoted"] is True
    assert res1["new_fitness"] == 0.80
    assert res1["generation"] == 1
    assert res1["rollback_ref"] == "GENESIS"
    assert "Optimize circuit depth" in res1["next_gap"]

    # Second cycle: lower fitness -> rejected / not promoted
    def acceptance_worse(ir: QuantumCircuitIR):
        return True, 0.70  # worse than 0.80

    res2 = loop.run_cycle("Attempt another mutation", acceptance_worse)
    assert res2["promoted"] is False
    assert res2["generation"] == 1  # Not incremented
    assert "failed to achieve fitness" in res2["next_gap"]

    # Third cycle: higher fitness -> promoted!
    def acceptance_better(ir: QuantumCircuitIR):
        return True, 0.95  # better than 0.80

    res3 = loop.run_cycle("Attempt high fitness mutation", acceptance_better)
    assert res3["promoted"] is True
    assert res3["generation"] == 2
    assert res3["new_fitness"] == 0.95

    # Check ledger recorded all 3 cycles
    assert os.path.exists(ledger)
    with open(ledger) as f:
        lines = [ln for ln in f if ln.strip()]
        assert len(lines) == 3
