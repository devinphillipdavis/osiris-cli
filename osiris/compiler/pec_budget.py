"""
PEC sampling-overhead budget — decide before submission whether probabilistic
error cancellation fits a shot budget.

IBM's PEC learns a sparse Pauli-Lindblad noise model per layer. A layer with
rates λ_k costs γ = exp(2 Σ λ_k), and the circuit's sampling overhead is the
product of γ² over its layers: exp(4Λ), with Λ the circuit's total error mass.
Λ is close to the expected number of errors per shot, so each extra expected
error multiplies the shot cost by about e⁴ ≈ 55.

Partial cancellation (Qiskit Runtime's ``noise_gain``) leaves a fraction g of
the learned noise in place and costs exp(4(1 - g)Λ), so a cap M on the overhead
forces g ≥ 1 - ln(M) / (4Λ). That residual noise is residual bias.
"""

import math
from dataclasses import asdict, dataclass
from typing import Any, Dict, Iterable, Mapping, Optional

from .dna_ir import IROpType, QuantumCircuitIR

# Qiskit Runtime's PecOptions.max_overhead default (qiskit-ibm-runtime 0.51).
DEFAULT_MAX_OVERHEAD = 100.0

# Not cancelled by PEC: readout error is TREX's job, and barriers are not gates.
_NOT_CANCELLED = {IROpType.MEASURE, IROpType.BARRIER, IROpType.RESET}

# exp() overflows a float just above 709.
_MAX_EXPONENT = 700.0


@dataclass
class PECBudget:
    """Outcome of a PEC overhead check.

    ``noise_gain``, ``overhead`` and ``shots_required`` describe the cheapest
    run the cap allows: full cancellation when it fits, otherwise the partial
    one. ``status`` says whether that run is approved ("full" or "partial") or
    refused ("rejected", because partial cancellation was not allowed).
    """
    error_mass: float
    gamma: float
    overhead_full: float
    max_overhead: float
    noise_gain: float
    overhead: float
    shots: int
    shots_required: int
    status: str

    @property
    def within_budget(self) -> bool:
        return self.status != "rejected"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class PECBudgetExceeded(RuntimeError):
    """Full PEC needs more sampling overhead than the budget allows."""

    def __init__(self, budget: PECBudget):
        self.budget = budget
        super().__init__(
            f"PEC needs {budget.overhead_full:.3g}x sampling overhead "
            f"(error mass {budget.error_mass:.3f}) but max_overhead is "
            f"{budget.max_overhead:g}x; fitting the cap would leave "
            f"noise_gain >= {budget.noise_gain:.2f} of the learned noise "
            f"uncancelled (allow partial cancellation to accept that)"
        )


def _exp(x: float) -> float:
    return math.exp(x) if x <= _MAX_EXPONENT else math.inf


def _check_rate(name: str, rate: float) -> float:
    rate = float(rate)
    if not (0.0 <= rate < 1.0):
        raise ValueError(f"{name} must be in [0, 1), got {rate}")
    return rate


def error_mass_from_layers(layer_rates: Iterable[Iterable[float]]) -> float:
    """Λ from learned Pauli-Lindblad rates.

    Give one sequence of rates λ_k per layer *as executed*: a learned layer
    that appears three times in the circuit is listed three times.
    """
    return sum(
        _check_rate(f"layer {i} rate", rate)
        for i, rates in enumerate(layer_rates)
        for rate in rates
    )


def estimate_error_mass(circuit: QuantumCircuitIR,
                        gate_error_rates: Mapping[str, float]) -> float:
    """First-order Λ: the sum of per-gate error probabilities.

    ``gate_error_rates`` maps IR gate names ("cx", "h", ...) to error
    probabilities, e.g. from backend calibration data. A gate with no rate is
    an error rather than a free gate. The estimate is taken before
    transpilation and ignores idle errors; routing and basis decomposition add
    gates, so it understates the executed circuit's error mass. Prefer
    learned layer rates (error_mass_from_layers) when you have them.
    """
    gates = [op for op in circuit.operations if op.op_type not in _NOT_CANCELLED]
    missing = sorted({op.op_type.value for op in gates} - set(gate_error_rates))
    if missing:
        raise ValueError(f"No error rate for gate(s): {', '.join(missing)}")
    rates = {name: _check_rate(f"error rate for {name}", rate)
             for name, rate in gate_error_rates.items()}
    return sum(rates[op.op_type.value] for op in gates)


def check_pec_budget(error_mass: float, shots: int,
                     max_overhead: float = DEFAULT_MAX_OVERHEAD,
                     allow_partial: bool = False) -> PECBudget:
    """Check whether PEC on a circuit with error mass Λ fits the overhead cap.

    ``shots`` is the unmitigated shot count whose precision the PEC run should
    match; ``shots_required`` is what the run then costs. Over the cap, the
    check approves partial cancellation only when ``allow_partial`` is set.
    """
    if not (math.isfinite(error_mass) and error_mass >= 0):
        raise ValueError(f"error_mass must be finite and >= 0, got {error_mass}")
    if shots < 1:
        raise ValueError(f"shots must be >= 1, got {shots}")
    if not (math.isfinite(max_overhead) and max_overhead >= 1):
        raise ValueError(f"max_overhead must be finite and >= 1, got {max_overhead}")

    overhead_full = _exp(4 * error_mass)
    if overhead_full <= max_overhead or math.isclose(overhead_full, max_overhead):
        noise_gain, overhead = 0.0, min(overhead_full, max_overhead)
        status = "full"
    else:
        noise_gain = 1 - math.log(max_overhead) / (4 * error_mass)
        overhead = max_overhead
        status = "partial" if allow_partial else "rejected"

    return PECBudget(
        error_mass=error_mass,
        gamma=_exp(2 * error_mass),
        overhead_full=overhead_full,
        max_overhead=max_overhead,
        noise_gain=noise_gain,
        overhead=overhead,
        shots=shots,
        shots_required=math.ceil(shots * overhead),
        status=status,
    )


def estimator_options(resilience_level: int, shots: int,
                      budget: Optional[PECBudget] = None) -> Dict[str, Any]:
    """Options for ``qiskit_ibm_runtime.EstimatorV2(options=...)``.

    With an approved PEC budget, PEC is switched on with the budget's
    ``noise_gain`` pinned (not "auto"), and ``default_shots`` — Estimator's
    total shots per circuit — becomes ``shots_required``, so the mitigated
    estimate keeps the precision of ``shots`` unmitigated shots.
    """
    if resilience_level not in (0, 1, 2):
        raise ValueError(f"Estimator resilience_level must be 0, 1 or 2, got {resilience_level}")
    options: Dict[str, Any] = {"default_shots": shots, "resilience_level": resilience_level}
    if budget is not None:
        if not budget.within_budget:
            raise PECBudgetExceeded(budget)
        options["default_shots"] = budget.shots_required
        options["resilience"] = {
            "pec_mitigation": True,
            "pec": {"max_overhead": budget.max_overhead, "noise_gain": budget.noise_gain},
        }
    return options
