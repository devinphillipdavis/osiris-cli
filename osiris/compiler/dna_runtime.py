"""
DNA-Lang Quantum Runtime — Execute circuits on simulators or IBM Quantum.
"""

import os
import time
from typing import Any, Dict, List, Optional
from dataclasses import dataclass, field

from .dna_ir import QuantumCircuitIR
from .pec_budget import (
    DEFAULT_MAX_OVERHEAD, PECBudget, PECBudgetExceeded,
    check_pec_budget, error_mass_from_layers, estimate_error_mass,
    estimator_options,
)


@dataclass
class RuntimeConfig:
    ibm_token: Optional[str] = None
    backend_name: str = "ibm_brisbane"
    use_simulator: bool = False
    shots: int = 1024
    optimization_level: int = 3
    resilience_level: int = 1  # Estimator only; Sampler has no resilience levels
    max_execution_time: int = 3600
    allow_mock: bool = False
    # PEC is checked against its sampling-overhead cap before anything runs.
    pec_mitigation: bool = False
    pec_max_overhead: float = DEFAULT_MAX_OVERHEAD
    pec_allow_partial: bool = False
    gate_error_rates: Optional[Dict[str, float]] = None

    def __post_init__(self):
        if not self.ibm_token:
            self.ibm_token = os.environ.get("IBM_QUANTUM_TOKEN")


@dataclass
class ExecutionResult:
    job_id: Optional[str] = None
    backend: str = ""
    status: str = "unknown"
    execution_time: float = 0.0
    timestamp: str = ""
    counts: Dict[str, int] = field(default_factory=dict)
    fidelity: float = 0.0
    success_rate: float = 0.0
    lambda_measured: float = 0.0
    gamma_measured: float = 0.0
    phi_measured: float = 0.0
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "job_id": self.job_id,
            "backend": self.backend,
            "status": self.status,
            "execution_time": self.execution_time,
            "counts": self.counts,
            "metrics": {"fidelity": self.fidelity, "success_rate": self.success_rate},
            "physics": {
                "lambda": self.lambda_measured,
                "gamma": self.gamma_measured,
                "phi": self.phi_measured,
            },
            "error": self.error,
        }


class QuantumRuntime:
    """Execute circuits without silently substituting a mock backend."""

    def __init__(self, config: Optional[RuntimeConfig] = None):
        self.config = config or RuntimeConfig()
        self.execution_log: List[ExecutionResult] = []

    def execute(self, circuit: QuantumCircuitIR,
                layer_rates: Optional[List[List[float]]] = None) -> ExecutionResult:
        """Execute a circuit using the configured backend.

        Mock execution is available only when explicitly enabled in the
        configuration, so backend failures cannot be mistaken for results.
        With PEC enabled, an over-budget circuit raises PECBudgetExceeded
        before any backend (or the mock) is touched.
        """
        if self.config.pec_mitigation:
            budget = self.pec_budget(circuit, layer_rates)
            if not budget.within_budget:
                raise PECBudgetExceeded(budget)
        t0 = time.time()
        try:
            from .backends.registry import BackendRegistry
            backend = BackendRegistry.get(self.config.backend_name)
            result = backend.execute(circuit, shots=self.config.shots)
        except Exception as exc:
            if not self.config.allow_mock:
                raise RuntimeError(
                    f"Backend '{self.config.backend_name}' execution failed"
                ) from exc
            result = self._mock_execution(circuit)
        result.execution_time = time.time() - t0
        self.execution_log.append(result)
        return result

    def pec_budget(self, circuit: QuantumCircuitIR,
                   layer_rates: Optional[List[List[float]]] = None) -> PECBudget:
        """PEC sampling-overhead check for this circuit under the configured cap.

        Learned Pauli-Lindblad rates (one list per executed layer) give the
        exact error mass; without them it is estimated from
        ``config.gate_error_rates``.
        """
        if layer_rates is not None:
            error_mass = error_mass_from_layers(layer_rates)
        elif self.config.gate_error_rates is not None:
            error_mass = estimate_error_mass(circuit, self.config.gate_error_rates)
        else:
            raise ValueError(
                "PEC budget needs learned layer rates or RuntimeConfig.gate_error_rates"
            )
        return check_pec_budget(error_mass, self.config.shots,
                                self.config.pec_max_overhead,
                                self.config.pec_allow_partial)

    def estimator_options(self, circuit: QuantumCircuitIR,
                          layer_rates: Optional[List[List[float]]] = None) -> Dict[str, Any]:
        """EstimatorV2 options: the configured resilience_level, plus PEC
        settings when PEC is enabled and the circuit passes its budget check."""
        budget = self.pec_budget(circuit, layer_rates) if self.config.pec_mitigation else None
        return estimator_options(self.config.resilience_level, self.config.shots, budget)

    @staticmethod
    def _ir_to_qiskit(circuit: QuantumCircuitIR):
        """Convert IR to Qiskit QuantumCircuit."""
        from qiskit import QuantumCircuit
        nq = sum(r.size for r in circuit.quantum_registers)
        nc = sum(r.size for r in circuit.classical_registers)
        qc = QuantumCircuit(nq, nc)
        from .dna_ir import IROpType
        gate_map = {
            IROpType.H: 'h', IROpType.X: 'x', IROpType.Y: 'y', IROpType.Z: 'z',
            IROpType.CX: 'cx', IROpType.CY: 'cy', IROpType.CZ: 'cz',
            IROpType.SWAP: 'swap', IROpType.CCX: 'ccx',
        }
        for op in circuit.operations:
            if op.op_type == IROpType.MEASURE:
                for i, q in enumerate(op.qubits):
                    cb = op.classical_bits[i] if op.classical_bits and i < len(op.classical_bits) else q
                    qc.measure(q, cb)
            elif op.op_type in gate_map:
                getattr(qc, gate_map[op.op_type])(*op.qubits)
        return qc

    def _mock_execution(self, circuit: QuantumCircuitIR) -> ExecutionResult:
        import random
        n_qubits = circuit.qubit_count
        shots = self.config.shots
        counts: Dict[str, int] = {}
        for _ in range(shots):
            bits = "".join(str(random.randint(0, 1)) for _ in range(n_qubits))
            counts[bits] = counts.get(bits, 0) + 1
        dominant = max(counts, key=counts.get)
        fidelity = counts[dominant] / shots
        return ExecutionResult(
            job_id="mock_" + str(int(time.time())),
            backend="local_mock",
            status="completed",
            timestamp=str(time.time()),
            counts=counts,
            fidelity=fidelity,
            success_rate=fidelity,
        )

    def _execute_qiskit(self, qc) -> ExecutionResult:
        from qiskit.quantum_info import Statevector
        sv = Statevector.from_instruction(qc.remove_final_measurements(inplace=False))
        counts = dict(sv.sample_counts(self.config.shots))
        dominant = max(counts, key=counts.get)
        fidelity = counts[dominant] / self.config.shots
        return ExecutionResult(
            job_id="sv_" + str(int(time.time())),
            backend="statevector_simulator",
            status="completed",
            timestamp=str(time.time()),
            counts=counts,
            fidelity=fidelity,
            success_rate=fidelity,
        )
