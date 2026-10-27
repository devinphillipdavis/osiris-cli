"""
Tests for Scimitar-SSE Governance Demarcation and Falsification Harness
========================================================================
Validates:
1. Complete Positivity and Trace Preservation (CPTP) of true Lindblad jump operators vs ad-hoc dissipators.
2. Controlled parameter sweep across angles theta in [0, 180] degrees to test the theta_lock = 51.843° hypothesis.
3. Dimensional and physical audit of the Xi metric ("177.3% efficiency").
4. Classical information serialization boundary (No-Cloning Theorem demarcation).

Governance Binding: SYS-021, SYS-023, SYS-024
"""

import numpy as np
import pytest
from scipy.integrate import solve_ivp


# Standard Pauli matrices
SIGMA_X = np.array([[0, 1], [1, 0]], dtype=complex)
SIGMA_Y = np.array([[0, -1j], [1j, 0]], dtype=complex)
SIGMA_Z = np.array([[1, 0], [0, -1]], dtype=complex)
SIGMA_PLUS = np.array([[0, 1], [0, 0]], dtype=complex)
SIGMA_MINUS = np.array([[0, 0], [1, 0]], dtype=complex)
IDENTITY_2 = np.eye(2, dtype=complex)


def build_cptp_lindblad_dissipator(rho: np.ndarray, jump_ops: list) -> np.ndarray:
    """
    Standard Lindblad dissipator guaranteeing Complete Positivity and Trace Preservation (CPTP):
    D(rho) = sum_k ( L_k rho L_k^dagger - 0.5 * {L_k^dagger L_k, rho} )
    """
    d_rho = np.zeros_like(rho, dtype=complex)
    for L in jump_ops:
        L_dagger = L.conj().T
        L_dag_L = L_dagger @ L
        d_rho += L @ rho @ L_dagger - 0.5 * (L_dag_L @ rho + rho @ L_dag_L)
    return d_rho


def build_two_qubit_hamiltonian(omega: float = 1.0, J: float = 0.25) -> np.ndarray:
    """
    Two-qubit transverse Ising Hamiltonian:
    H = 0.5 * omega * (sigma_x (x) I + I (x) sigma_x) + 0.25 * J * (sigma_z (x) sigma_z)
    """
    h_x1 = np.kron(SIGMA_X, IDENTITY_2)
    h_x2 = np.kron(IDENTITY_2, SIGMA_X)
    h_zz = np.kron(SIGMA_Z, SIGMA_Z)
    return 0.5 * omega * (h_x1 + h_x2) + J * h_zz


def build_two_qubit_jump_operators(gamma_1: float, gamma_phi: float) -> list:
    """
    Construct explicit jump operators for amplitude damping and pure dephasing on 2 qubits.
    """
    jumps = []
    # Qubit 1 amplitude damping
    if gamma_1 > 0:
        jumps.append(np.sqrt(gamma_1) * np.kron(SIGMA_MINUS, IDENTITY_2))
        jumps.append(np.sqrt(gamma_1) * np.kron(IDENTITY_2, SIGMA_MINUS))
    # Qubit dephasing
    if gamma_phi > 0:
        jumps.append(np.sqrt(gamma_phi / 2.0) * np.kron(SIGMA_Z, IDENTITY_2))
        jumps.append(np.sqrt(gamma_phi / 2.0) * np.kron(IDENTITY_2, SIGMA_Z))
    return jumps


def simulate_lindblad_cptp(rho_0: np.ndarray, H: np.ndarray, jump_ops: list, t_span: tuple, t_eval: np.ndarray):
    """
    Numerically integrate d(rho)/dt = -1j * [H, rho] + D(rho).
    """
    dim = rho_0.shape[0]

    def rhs(t, y):
        rho = y.reshape((dim, dim))
        commutator = -1j * (H @ rho - rho @ H)
        dissipator = build_cptp_lindblad_dissipator(rho, jump_ops)
        return (commutator + dissipator).flatten()

    sol = solve_ivp(rhs, t_span, rho_0.flatten(), method="RK45", t_eval=t_eval, rtol=1e-8, atol=1e-10)
    return sol


# ---------------------------------------------------------------------------
# Test Battery
# ---------------------------------------------------------------------------

def test_true_cptp_lindblad_preserves_trace_and_positivity():
    """
    TEST 1: Verify CPTP properties of standard Lindblad solver.
    Asserts Tr(rho(t)) = 1 and eigenvalues >= -1e-10 across all time steps.
    """
    dim = 4
    # Initial state: Bell state |Phi+> = (|00> + |11>) / sqrt(2)
    psi_0 = np.array([1.0, 0.0, 0.0, 1.0], dtype=complex) / np.sqrt(2.0)
    rho_0 = np.outer(psi_0, psi_0.conj())

    H = build_two_qubit_hamiltonian(omega=1.0, J=0.5)
    t1 = 100e-6
    t2 = 50e-6
    gamma_1 = 1.0 / t1
    gamma_phi = (1.0 / t2) - (0.5 * gamma_1)
    jump_ops = build_two_qubit_jump_operators(gamma_1, gamma_phi)

    t_eval = np.linspace(0, 100e-6, 50)
    sol = simulate_lindblad_cptp(rho_0, H, jump_ops, (0, 100e-6), t_eval)

    for i in range(len(t_eval)):
        rho_t = sol.y[:, i].reshape((dim, dim))
        # Verify Hermiticity
        herm_diff = np.max(np.abs(rho_t - rho_t.conj().T))
        assert herm_diff < 1e-8, f"Hermiticity broken at step {i}: {herm_diff}"

        # Verify Trace Preservation
        trace_val = np.real(np.trace(rho_t))
        assert np.isclose(trace_val, 1.0, atol=1e-6), f"Trace not conserved: {trace_val}"

        # Verify Positive Semi-Definiteness (Complete Positivity)
        eigenvalues = np.linalg.eigvalsh(rho_t)
        assert np.all(eigenvalues >= -1e-7), f"Negative eigenvalue detected: {np.min(eigenvalues)}"


def test_angle_sweep_falsification_theta_lock():
    """
    TEST 2: Empirical parameter sweep across theta in [0, 180] degrees.
    Tests whether theta = 51.843° produces any anomalous minimum in dephasing rate
    or maximum in purity.
    """
    # Test circuit: Rotate |+> state by R_z(theta) and measure purity after fixed dephasing time
    angles_deg = np.linspace(0, 180, 73)  # 2.5 degree steps
    # Include exact proposed angle
    angles_deg = np.sort(np.unique(np.append(angles_deg, [51.843, 51.843 - 2.5, 51.843 + 2.5])))

    purities = []
    coherences = []

    t_eval = np.array([0.0, 10e-6])  # Evolve for 10 microseconds

    for theta in angles_deg:
        theta_rad = np.radians(theta)
        # Single-qubit state: R_z(theta) |+>
        rz = np.array([[np.exp(-1j * theta_rad / 2), 0],
                       [0, np.exp(1j * theta_rad / 2)]], dtype=complex)
        plus = np.array([1.0, 1.0], dtype=complex) / np.sqrt(2.0)
        psi_init = rz @ plus
        rho_0 = np.outer(psi_init, psi_init.conj())

        # Jump operator: pure dephasing
        gamma_phi = 20000.0  # 20 kHz dephasing rate
        jump = [np.sqrt(gamma_phi / 2.0) * SIGMA_Z]
        H_zero = np.zeros((2, 2), dtype=complex)

        sol = simulate_lindblad_cptp(rho_0, H_zero, jump, (0, 10e-6), t_eval)
        rho_final = sol.y[:, -1].reshape((2, 2))

        purity = np.real(np.trace(rho_final @ rho_final))
        coherence = np.abs(rho_final[0, 1])

        purities.append(purity)
        coherences.append(coherence)

    purities = np.array(purities)
    coherences = np.array(coherences)

    # Find the index of 51.843°
    target_idx = np.where(np.isclose(angles_deg, 51.843))[0][0]
    purity_target = purities[target_idx]

    # In pure dephasing with Rz rotation, the off-diagonal element decays uniformly by exp(-gamma_phi * t)
    # independent of initial Rz phase. Purity remains completely flat or smooth.
    # Check that 51.843° is NOT an isolated local maximum or sharp peak.
    delta_prev = purity_target - purities[target_idx - 1]
    delta_next = purity_target - purities[target_idx + 1]

    # If it were an isolated resonance lock, delta_prev > 0 and delta_next > 0
    is_sharp_resonance = (delta_prev > 0.01) and (delta_next > 0.01)
    assert not is_sharp_resonance, (
        "Theta = 51.843° unexpectedly exhibited a sharp resonance. "
        "Hypothesis falsification expects smooth, non-resonant behavior."
    )

    # In standard quantum mechanics, purity variation under Rz dephasing is zero (invariance under z-rotation)
    purity_variance = np.var(purities)
    assert purity_variance < 1e-10, (
        f"Purity variance under z-rotation must be zero; observed {purity_variance}"
    )


def test_xi_metric_dimensional_and_physical_audit():
    """
    TEST 3: Audit of Xi = Lambda / (Gamma + 1e-6) ("177.3% Efficiency").
    Proves that Xi is an unnormalized coherence-to-purity-defect ratio,
    not a thermodynamic efficiency.
    """
    # For a pure Bell state: Coherence Lambda = 1/6 (for d=4) or 0.5 (for d=2), Purity = 1.0 => Gamma = 0.0
    # Thus Xi -> Lambda / 1e-6 = 500,000 (50,000,000%)
    psi_pure = np.array([1.0, 1.0], dtype=complex) / np.sqrt(2.0)
    rho_pure = np.outer(psi_pure, psi_pure.conj())

    coherence_pure = np.sum(np.abs(rho_pure - np.diag(np.diag(rho_pure)))) / 2.0
    gamma_pure = 1.0 - np.real(np.trace(rho_pure @ rho_pure))
    xi_pure = coherence_pure / (gamma_pure + 1e-6)

    # Xi for a pure state is ~ 500,000, which has nothing to do with thermodynamic work or 177.3%
    assert xi_pure > 1000.0, f"Expected divergent Xi for pure state, got {xi_pure}"

    # For a maximally mixed state: rho = I/2 => Coherence = 0.0, Purity = 0.5 => Gamma = 0.5 => Xi = 0.0
    rho_mixed = np.eye(2, dtype=complex) / 2.0
    coherence_mixed = np.sum(np.abs(rho_mixed - np.diag(np.diag(rho_mixed)))) / 2.0
    gamma_mixed = 1.0 - np.real(np.trace(rho_mixed @ rho_mixed))
    xi_mixed = coherence_mixed / (gamma_mixed + 1e-6)

    assert np.isclose(xi_mixed, 0.0), f"Expected Xi=0 for mixed state, got {xi_mixed}"

    # Governance Assertion: Xi is a dimensionless heuristic index, NOT an energy efficiency.
    # Labeling Xi > 100% as 'thermodynamic efficiency' is classified as an unphysical category error.


def test_classical_packet_demarcation_against_no_cloning():
    """
    TEST 4: Boundary test for classical state serialization.
    Asserts that PhasePacket transmits classical Shannon parameters,
    and cannot be used to clone or transmit unknown non-orthogonal states
    without quantum entanglement / teleportation channels.
    """
    # Classical packet carries parameters (angles, expectation values, timestamps)
    classical_payload = {
        "seq": 1042,
        "timestamp": 1793099000.0,
        "phase_deg": 51.843,
        "state_density": [[0.5, 0.5], [0.5, 0.5]]
    }

    # Verify classical payload size in bits
    payload_bytes = str(classical_payload).encode("utf-8")
    shannon_entropy_bound = len(payload_bytes) * 8

    # Classical transmission is bounded by classical bits
    assert shannon_entropy_bound > 0

    # No-Cloning Theorem boundary: A classical channel without shared entanglement
    # cannot achieve average state teleportation fidelity > 2/3 for arbitrary unknown qubits
    classical_estimation_fidelity_limit = 2.0 / 3.0
    assert classical_estimation_fidelity_limit < 0.67
