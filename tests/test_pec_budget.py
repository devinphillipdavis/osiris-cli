"""PEC sampling-overhead budget and the runtime's pre-submission gate."""

import math

import pytest

from osiris.compiler.dna_ir import (
    QuantumCircuitIR,
    QuantumRegister,
    ClassicalRegister,
    IROperation,
    IROpType,
)
from osiris.compiler.dna_runtime import QuantumRuntime, RuntimeConfig
from osiris.compiler.pec_budget import (
    PECBudgetExceeded,
    check_pec_budget,
    error_mass_from_layers,
    estimate_error_mass,
    estimator_options,
)

RATES = {"h": 0.001, "cx": 0.01}


def _bell_ir() -> QuantumCircuitIR:
    circuit = QuantumCircuitIR(
        name="bell",
        quantum_registers=[QuantumRegister("q", 2)],
        classical_registers=[ClassicalRegister("c", 2)],
        operations=[
            IROperation(IROpType.H, [0]),
            IROperation(IROpType.CX, [0, 1]),
            IROperation(IROpType.BARRIER, [0, 1]),
            IROperation(IROpType.MEASURE, [0, 1], classical_bits=[0, 1]),
        ],
        source_organism="test",
        lineage_hash="abc123",
    )
    circuit.compute_metrics()
    return circuit


def test_overhead_is_exp_4_lambda():
    budget = check_pec_budget(0.5, shots=1000)
    assert budget.status == "full"
    assert budget.gamma == pytest.approx(math.e)
    assert budget.overhead_full == pytest.approx(math.e ** 2)
    assert budget.noise_gain == 0.0
    assert budget.shots_required == math.ceil(1000 * math.e ** 2)


def test_zero_error_mass_costs_nothing():
    budget = check_pec_budget(0.0, shots=1024)
    assert budget.overhead == 1.0
    assert budget.shots_required == 1024


def test_cap_boundary_counts_as_full():
    budget = check_pec_budget(math.log(100) / 4, shots=10, max_overhead=100)
    assert budget.status == "full"
    assert budget.shots_required == 1000


def test_over_cap_is_rejected_with_the_gain_that_would_fit():
    budget = check_pec_budget(1.5, shots=1000, max_overhead=100)
    assert budget.status == "rejected"
    assert not budget.within_budget
    assert budget.overhead_full == pytest.approx(math.exp(6))
    assert budget.noise_gain == pytest.approx(1 - math.log(100) / 6)


def test_partial_cancellation_only_when_allowed():
    budget = check_pec_budget(1.5, shots=1000, max_overhead=100, allow_partial=True)
    assert budget.status == "partial"
    assert budget.overhead == 100
    assert budget.shots_required == 100_000
    # The partial plan's own overhead is exp(4 (1 - g) Λ) = the cap.
    assert math.exp(4 * (1 - budget.noise_gain) * 1.5) == pytest.approx(100)


def test_huge_error_mass_does_not_overflow():
    budget = check_pec_budget(300.0, shots=1000)
    assert budget.overhead_full == math.inf
    assert budget.status == "rejected"
    assert 0.99 < budget.noise_gain < 1


@pytest.mark.parametrize("kwargs", [
    {"error_mass": -0.1, "shots": 10},
    {"error_mass": math.nan, "shots": 10},
    {"error_mass": 0.1, "shots": 0},
    {"error_mass": 0.1, "shots": 10, "max_overhead": 0.5},
    {"error_mass": 0.1, "shots": 10, "max_overhead": math.inf},
])
def test_invalid_inputs_are_refused(kwargs):
    with pytest.raises(ValueError):
        check_pec_budget(**kwargs)


def test_error_mass_from_layers_sums_every_executed_layer():
    layer = [0.01, 0.005]
    assert error_mass_from_layers([layer, layer, [0.02]]) == pytest.approx(0.05)
    with pytest.raises(ValueError):
        error_mass_from_layers([[0.01, -0.001]])


def test_estimate_counts_gates_but_not_readout_or_barriers():
    assert estimate_error_mass(_bell_ir(), RATES) == pytest.approx(0.011)


def test_estimate_refuses_gates_without_a_rate():
    with pytest.raises(ValueError, match="cx"):
        estimate_error_mass(_bell_ir(), {"h": 0.001})


def test_estimator_options_without_pec_carry_resilience_level():
    assert estimator_options(1, 1024) == {"default_shots": 1024, "resilience_level": 1}
    with pytest.raises(ValueError):
        estimator_options(3, 1024)


def test_estimator_options_pin_the_approved_pec_plan():
    budget = check_pec_budget(1.5, shots=1000, max_overhead=100, allow_partial=True)
    options = estimator_options(2, 1000, budget)
    assert options["default_shots"] == 100_000
    assert options["resilience"] == {
        "pec_mitigation": True,
        "pec": {"max_overhead": 100, "noise_gain": budget.noise_gain},
    }
    with pytest.raises(PECBudgetExceeded):
        estimator_options(2, 1000, check_pec_budget(1.5, shots=1000, max_overhead=100))


def test_estimator_options_are_accepted_by_qiskit_runtime():
    runtime_options = pytest.importorskip("qiskit_ibm_runtime.options")
    budget = check_pec_budget(1.5, shots=1000, max_overhead=100, allow_partial=True)
    options = runtime_options.EstimatorOptions(**estimator_options(1, 1000, budget))
    assert options.resilience.pec_mitigation is True
    assert options.resilience.pec.noise_gain == pytest.approx(budget.noise_gain)


def test_runtime_rejects_over_budget_pec_before_the_mock_fallback():
    runtime = QuantumRuntime(RuntimeConfig(
        backend_name="missing-backend",
        shots=8,
        allow_mock=True,
        pec_mitigation=True,
        pec_max_overhead=100,
        gate_error_rates={"h": 0.9, "cx": 0.9},
    ))
    with pytest.raises(PECBudgetExceeded):
        runtime.execute(_bell_ir())
    assert runtime.execution_log == []


def test_runtime_runs_within_budget_and_uses_learned_layers_first():
    runtime = QuantumRuntime(RuntimeConfig(
        backend_name="sovereign",
        shots=16,
        pec_mitigation=True,
        gate_error_rates={"h": 0.9, "cx": 0.9},   # would be rejected
    ))
    result = runtime.execute(_bell_ir(), layer_rates=[[0.01], [0.02]])
    assert result.status == "completed"
    assert runtime.pec_budget(_bell_ir(), [[0.01], [0.02]]).error_mass == pytest.approx(0.03)


def test_runtime_pec_needs_an_error_model():
    runtime = QuantumRuntime(RuntimeConfig(backend_name="sovereign", pec_mitigation=True))
    with pytest.raises(ValueError, match="gate_error_rates"):
        runtime.execute(_bell_ir())


def test_runtime_estimator_options_follow_config():
    plain = QuantumRuntime(RuntimeConfig(shots=512, resilience_level=0))
    assert plain.estimator_options(_bell_ir()) == {"default_shots": 512, "resilience_level": 0}

    pec = QuantumRuntime(RuntimeConfig(shots=512, pec_mitigation=True, gate_error_rates=RATES))
    options = pec.estimator_options(_bell_ir())
    assert options["resilience"]["pec"]["noise_gain"] == 0.0
    assert options["default_shots"] == math.ceil(512 * math.exp(4 * 0.011))
