"""
Tests for OSIRIS Statistical Process Control (SPC) & Calibration Drift Monitor
==============================================================================
Validates:
  1. Temporal sequence enforcement (rejects shuffled/unordered timestamps).
  2. Nominal i.i.d. stability (no false alarms).
  3. Slow trend detection (monotonic drift slope).
  4. Runs of same-sign residuals (Lag-1 autocorrelation rho_1).
  5. Session-level step shifts.
  6. Two-sided CUSUM sequential monitor breach (threshold h = 27.0).
  7. Subsystem calibration verification.

Governance: SYS-021, SYS-022, SYS-023, SYS-024
"""

import numpy as np
import pytest

from osiris_cli.quantum.calibration_spc import (
    MeasurementRun,
    CUSUMConfig,
    TimeOrderedSPCValidator,
    verify_subsystem_calibrations,
)


def _generate_synthetic_runs(
    n: int = 100,
    mu_true: float = 0.0,
    sigma_true: float = 1.0,
    mean_shift: float = 0.0,
    trend_rate: float = 0.0,
    ar1_phi: float = 0.0,
    session_shift: float = 0.0,
    n_replicas: int = 200,
    seed: int = 42,
) -> list[MeasurementRun]:
    """Helper to generate time-ordered measurement runs with posterior replicas."""
    rng = np.random.default_rng(seed)
    timestamps = np.sort(1700000000.0 + np.cumsum(rng.uniform(1.0, 10.0, size=n)))

    # Base noise
    innovations = rng.normal(0.0, sigma_true, size=n)
    y_vals = np.empty(n)
    val = 0.0
    for k in range(n):
        val = ar1_phi * val + innovations[k]
        session_offset = session_shift if k >= (n // 2) else 0.0
        y_vals[k] = (
            mu_true
            + mean_shift
            + trend_rate * (timestamps[k] - timestamps[0])
            + session_offset
            + val
        )

    runs = []
    for k in range(n):
        # Generate independent posterior predictive replicas from nominal model (no drift)
        replicas = rng.normal(mu_true, sigma_true, size=n_replicas).tolist()
        session_id = "session_B" if k >= (n // 2) else "session_A"
        runs.append(
            MeasurementRun(
                run_id=f"run_{k:04d}",
                timestamp=float(timestamps[k]),
                observed_value=float(y_vals[k]),
                predicted_mean=mu_true,
                predicted_std=sigma_true,
                session_id=session_id,
                posterior_replicas=replicas,
            )
        )
    return runs


def test_temporal_order_preservation():
    """Test 1: Fails closed when temporal sequence is violated or shuffled."""
    validator = TimeOrderedSPCValidator()
    runs = _generate_synthetic_runs(n=10)

    # Invert order of two runs
    runs[3].timestamp, runs[4].timestamp = runs[4].timestamp, runs[3].timestamp

    with pytest.raises(ValueError, match="Temporal sequence violated"):
        validator.audit_runs(runs)


def test_iid_nominal_no_false_alarm():
    """Test 2: Pure i.i.d. noise does not trip any drift signatures or CUSUM threshold."""
    validator = TimeOrderedSPCValidator(cusum_config=CUSUMConfig(threshold_h=27.0))
    runs = _generate_synthetic_runs(n=80, trend_rate=0.0, ar1_phi=0.0, session_shift=0.0)

    report = validator.audit_runs(runs)

    assert report.temporal_ordering_verified is True
    assert report.trend_signature.detected is False
    assert report.autocorrelation_signature.detected is False
    assert report.session_shift_signature.detected is False
    assert report.cusum_signature.detected is False
    assert report.drift_detected is False
    assert report.recalibration_required is False
    assert report.cusum_signature.test_statistic < 27.0


def test_slow_trend_signature():
    """Test 3: Detects slow monotonic upward drift."""
    validator = TimeOrderedSPCValidator()
    # Injected drift rate that accumulates ~ 3.5 sigma over 100 runs
    runs = _generate_synthetic_runs(n=100, trend_rate=0.007, ar1_phi=0.0)

    report = validator.audit_runs(runs)

    assert report.trend_signature.detected is True
    assert report.trend_signature.details["t_statistic"] > 3.0
    assert report.drift_detected is True


def test_autocorrelation_signature():
    """Test 4: Detects runs of same-sign residuals (AR(1) non-independence)."""
    validator = TimeOrderedSPCValidator()
    # Injected AR(1) with phi = 0.70
    runs = _generate_synthetic_runs(n=120, ar1_phi=0.70)

    report = validator.audit_runs(runs)

    assert report.autocorrelation_signature.detected is True
    assert report.autocorrelation_signature.test_statistic > 0.50
    assert report.autocorrelation_signature.threshold_or_pvalue < 0.01
    assert report.drift_detected is True


def test_session_step_shift_signature():
    """Test 5: Detects sharp step shift between experimental sessions."""
    validator = TimeOrderedSPCValidator()
    # Step shift of 2.5 sigma between session A and session B
    runs = _generate_synthetic_runs(n=80, session_shift=2.5)

    report = validator.audit_runs(runs)

    assert report.session_shift_signature.detected is True
    assert report.session_shift_signature.test_statistic > 1.8
    assert report.drift_detected is True


def test_cusum_threshold_breach():
    """Test 6: Sustained positive shift breaches CUSUM threshold h = 27.0."""
    validator = TimeOrderedSPCValidator(
        cusum_config=CUSUMConfig(target_mu=0.0, slack_k=0.5, threshold_h=27.0)
    )
    # Sustained shift of +1.5 sigma causes S_k to accumulate (~1.0 per step) and breach 27.0
    runs = _generate_synthetic_runs(n=60, mean_shift=1.5)

    report = validator.audit_runs(runs)

    assert report.cusum_signature.detected is True
    assert report.cusum_signature.test_statistic > 27.0
    assert report.cusum_signature.details["breach_direction"] == "upward_drift"
    assert report.cusum_signature.details["breach_index"] > 0
    assert report.recalibration_required is True
    assert report.drift_detected is True


def test_cusum_negative_shift_breach():
    """Test 7: Sustained negative shift breaches downward CUSUM (S^-) threshold."""
    validator = TimeOrderedSPCValidator(
        cusum_config=CUSUMConfig(target_mu=0.0, slack_k=0.5, threshold_h=27.0)
    )
    # Sustained shift of -1.5 sigma causes S_k^- to accumulate and breach 27.0
    runs = _generate_synthetic_runs(n=60, mean_shift=-1.5)

    report = validator.audit_runs(runs)

    assert report.cusum_signature.detected is True
    assert report.cusum_signature.test_statistic > 27.0
    assert report.cusum_signature.details["breach_direction"] == "downward_drift"
    assert report.cusum_signature.details["breach_index"] > 0
    assert report.recalibration_required is True
    assert report.drift_detected is True


def test_cusum_reset_behavior():
    """Test 8: Transient zero-mean perturbations reset to 0 without accumulating to breach."""
    validator = TimeOrderedSPCValidator(
        cusum_config=CUSUMConfig(target_mu=0.0, slack_k=0.5, threshold_h=27.0)
    )
    # Create runs where one isolated burst (+1.0 sigma for 5 steps) occurs, then goes back to zero
    runs = _generate_synthetic_runs(n=50, mean_shift=0.0)
    for k in range(10, 15):
        runs[k].observed_value += 1.0

    report = validator.audit_runs(runs)

    # Isolated sub-threshold burst is reset by slack_k and does not breach 27.0
    assert report.cusum_signature.detected is False
    assert report.cusum_signature.test_statistic < 10.0


def test_subsystem_isolation():
    """Test 9: Validates calibration of independent subsystems prior to system-level diagnosis."""
    nominal_subsystems = {
        "dielectric_permittivity": {"drift_rate": 0.01, "tolerance": 0.05},
        "gravitational_sensor": {"drift_rate": -0.02, "tolerance": 0.05},
        "magnetic_flux_meter": {"drift_rate": 0.03, "tolerance": 0.05},
    }
    result_pass = verify_subsystem_calibrations(nominal_subsystems)
    assert result_pass["all_subsystems_calibrated"] is True

    drifting_subsystems = {
        "dielectric_permittivity": {"drift_rate": 0.08, "tolerance": 0.05},  # Exceeds tolerance
        "gravitational_sensor": {"drift_rate": 0.01, "tolerance": 0.05},
    }
    result_fail = verify_subsystem_calibrations(drifting_subsystems)
    assert result_fail["all_subsystems_calibrated"] is False
    assert result_fail["subsystems"]["dielectric_permittivity"]["calibrated"] is False


def test_qpu_evidence_binding():
    """Test 10: Associates observations with circuit, backend, job ID, and calibration hash.

    Rule: Never infer drift from a calibration hash change alone;
    drift must be demonstrated by statistical residual divergence.
    """
    validator = TimeOrderedSPCValidator()
    runs = _generate_synthetic_runs(n=40, mean_shift=0.0)

    # Assign QPU metadata with a mid-stream calibration hash change
    for k, r in enumerate(runs):
        r.circuit_id = f"xy4_delay_{k % 5 * 500}ns"
        r.backend = "ibm_brisbane"
        r.job_id = f"job_cib_{k:04d}"
        r.calibration_hash = "cal_hash_001" if k < 20 else "cal_hash_002"
        r.model_version = "nclm_v4.6.0"

    report = validator.audit_runs(runs)

    # 1. Report captures both calibration hashes and the backend
    assert report.qpu_backends == ["ibm_brisbane"]
    assert report.calibration_hashes == ["cal_hash_001", "cal_hash_002"]

    # 2. Invariant: Hash change without residual divergence DOES NOT declare drift
    assert report.drift_detected is False
    assert report.recalibration_required is False

    # 3. Conversely, inject true residual shift in the second session
    runs_drift = _generate_synthetic_runs(n=40, session_shift=2.5)
    for k, r in enumerate(runs_drift):
        r.circuit_id = f"xy4_delay_{k % 5 * 500}ns"
        r.backend = "ibm_brisbane"
        r.job_id = f"job_cib_{k:04d}"
        r.calibration_hash = "cal_hash_constant"  # Constant hash, but real drift!

    report_drift = validator.audit_runs(runs_drift)
    assert report_drift.drift_detected is True
    assert report_drift.session_shift_signature.detected is True
