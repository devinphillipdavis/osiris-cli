"""
OSIRIS Quantum Substrate: Statistical Process Control (SPC) & Calibration Drift Monitor
========================================================================================
Implements time-ordered process control signatures for spotting calibration drift
between posterior predictive replicas and real time-ordered measurements.

Signatures tracked:
  1. Slow Trends & Drift Lines (OLS slope & replica tail comparison)
  2. Runs of Same-Sign Residuals (Lag-1 Autocorrelation rho_1 vs replica envelope)
  3. Session-Level Step Shifts (Between-session variance & max mean delta)
  4. CUSUM / Sequential Change-Point Monitor (Two-sided CUSUM, threshold h = 27.0)

Governance: SYS-021, SYS-022, SYS-023, SYS-024
"""

from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional, Tuple
import numpy as np


@dataclass
class MeasurementRun:
    """Individual time-ordered measurement run with operating conditions."""
    run_id: str
    timestamp: float  # Unix epoch seconds (t_k)
    observed_value: float  # y_k^obs
    predicted_mean: float  # E[y_k | theta]
    predicted_std: float   # sigma_k
    session_id: str = "default_session"
    operating_conditions: Dict[str, Any] = field(default_factory=dict)
    posterior_replicas: List[float] = field(default_factory=list)  # [y_{k,s}^rep] for s=1..S

    @property
    def standardized_residual(self) -> float:
        """r_k^obs = (y_k^obs - E[y_k | theta]) / sigma_k"""
        std = max(self.predicted_std, 1e-12)
        return float((self.observed_value - self.predicted_mean) / std)

    def replica_standardized_residuals(self) -> np.ndarray:
        """r_{k,s}^rep = (y_{k,s}^rep - E[y_k | theta]) / sigma_k"""
        if not self.posterior_replicas:
            return np.array([], dtype=float)
        std = max(self.predicted_std, 1e-12)
        reps = np.asarray(self.posterior_replicas, dtype=float)
        return (reps - self.predicted_mean) / std


@dataclass
class CUSUMConfig:
    """Configuration for two-sided CUSUM drift detection."""
    target_mu: float = 0.0
    slack_k: float = 0.5
    threshold_h: float = 27.0  # Pre-declared threshold per SPC specification


@dataclass
class DriftSignatureResult:
    """Verdict and telemetry for an individual SPC drift signature."""
    signature_name: str
    detected: bool
    test_statistic: float
    threshold_or_pvalue: float
    details: Dict[str, Any] = field(default_factory=dict)


@dataclass
class CalibrationDriftReport:
    """Master report summarizing time-ordered calibration drift diagnostics."""
    temporal_ordering_verified: bool
    total_runs: int
    num_sessions: int
    num_replicas: int
    trend_signature: DriftSignatureResult
    autocorrelation_signature: DriftSignatureResult
    session_shift_signature: DriftSignatureResult
    cusum_signature: DriftSignatureResult
    drift_detected: bool
    recalibration_required: bool
    provenance_tag: str = "temporal_spc_audit"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class TimeOrderedSPCValidator:
    """
    Validator implementing time-ordered process control signatures
    to detect calibration drift in experimental and quantum telemetry.
    """

    def __init__(self, cusum_config: Optional[CUSUMConfig] = None):
        self.cusum_config = cusum_config or CUSUMConfig()

    def verify_temporal_sequence(self, runs: List[MeasurementRun]) -> bool:
        """Enforce strict non-decreasing temporal order: t_0 <= t_1 <= ... <= t_{N-1}."""
        if len(runs) < 2:
            return True
        for i in range(len(runs) - 1):
            if runs[i + 1].timestamp < runs[i].timestamp:
                raise ValueError(
                    f"Temporal sequence violated: run {runs[i+1].run_id} at t={runs[i+1].timestamp} "
                    f"precedes run {runs[i].run_id} at t={runs[i].timestamp}. Never shuffle time-series data."
                )
        return True

    def evaluate_trend_signature(
        self,
        t: np.ndarray,
        r_obs: np.ndarray,
        r_rep: np.ndarray,
        alpha: float = 0.01,
    ) -> DriftSignatureResult:
        """
        Signature 1: Monotonic Trends & Drift Lines.
        Fits OLS slope on observed residuals vs time and compares against replica slope distribution.
        """
        n = len(r_obs)
        if n < 5:
            return DriftSignatureResult(
                signature_name="monotonic_trend",
                detected=False,
                test_statistic=0.0,
                threshold_or_pvalue=1.0,
                details={"reason": "insufficient_samples"},
            )

        # Standardize time indices to avoid overflow/scale mismatch
        t_norm = (t - np.mean(t)) / (np.std(t) + 1e-12)
        slope_obs = float(np.sum(t_norm * (r_obs - np.mean(r_obs))) / (np.sum(t_norm**2) + 1e-12))

        # Residual variance and SE of slope
        fitted = np.mean(r_obs) + slope_obs * t_norm
        ss_res = np.sum((r_obs - fitted) ** 2)
        s_err = np.sqrt(ss_res / (n - 2) / (np.sum(t_norm**2) + 1e-12))
        t_stat = float(slope_obs / (s_err + 1e-12))

        # Check against replica slopes if replicas exist
        replica_detected = False
        p_val_replicas = 1.0
        if r_rep.shape[1] > 0:
            s_count = r_rep.shape[1]
            replica_slopes = np.empty(s_count)
            for s in range(s_count):
                r_s = r_rep[:, s]
                replica_slopes[s] = np.sum(t_norm * (r_s - np.mean(r_s))) / (np.sum(t_norm**2) + 1e-12)

            # Fraction of replica slopes with absolute value >= observed
            p_val_replicas = float(np.mean(np.abs(replica_slopes) >= np.abs(slope_obs)))
            replica_detected = p_val_replicas < alpha
        else:
            # Fall back to standard two-tailed t-test approximation (|t| > 2.58 for alpha=0.01)
            replica_detected = abs(t_stat) > 2.58

        return DriftSignatureResult(
            signature_name="monotonic_trend",
            detected=replica_detected,
            test_statistic=slope_obs,
            threshold_or_pvalue=p_val_replicas if r_rep.shape[1] > 0 else 0.01,
            details={
                "t_statistic": t_stat,
                "slope_normalized": slope_obs,
                "p_value_vs_replicas": p_val_replicas,
            },
        )

    def evaluate_autocorrelation_signature(
        self,
        r_obs: np.ndarray,
        r_rep: np.ndarray,
        alpha: float = 0.01,
    ) -> DriftSignatureResult:
        """
        Signature 2: Runs of Same-Sign Residuals (Lag-1 Autocorrelation rho_1).
        Flags when observed rho_1 falls in extreme tails of the posterior replica distribution.
        """
        n = len(r_obs)
        if n < 5:
            return DriftSignatureResult(
                signature_name="lag1_autocorrelation",
                detected=False,
                test_statistic=0.0,
                threshold_or_pvalue=1.0,
                details={"reason": "insufficient_samples"},
            )

        def calc_rho1(x: np.ndarray) -> float:
            dev = x - np.mean(x)
            var = np.sum(dev**2)
            if var < 1e-12:
                return 0.0
            cov = np.sum(dev[:-1] * dev[1:])
            return float(cov / var)

        rho1_obs = calc_rho1(r_obs)

        p_val = 1.0
        detected = False
        if r_rep.shape[1] > 0:
            s_count = r_rep.shape[1]
            rep_rho1 = np.array([calc_rho1(r_rep[:, s]) for s in range(s_count)])
            # Two-tailed tail probability: how often does replica rho1 exceed observed?
            p_val = float(np.mean(np.abs(rep_rho1) >= np.abs(rho1_obs)))
            detected = p_val < alpha
        else:
            # Standard i.i.d. asymptotic standard error is 1 / sqrt(n)
            se_rho = 1.0 / np.sqrt(n)
            z_rho = rho1_obs / se_rho
            detected = abs(z_rho) > 2.58
            p_val = 0.01 if detected else 0.5

        return DriftSignatureResult(
            signature_name="lag1_autocorrelation",
            detected=detected,
            test_statistic=rho1_obs,
            threshold_or_pvalue=p_val,
            details={"rho1_observed": rho1_obs, "p_value": p_val},
        )

    def evaluate_session_shift_signature(
        self,
        runs: List[MeasurementRun],
        r_obs: np.ndarray,
        r_rep: np.ndarray,
        alpha: float = 0.01,
    ) -> DriftSignatureResult:
        """
        Signature 3: Session-Level Step Shifts.
        Evaluates inter-session mean discrepancies delta_mu_max vs replica baseline.
        """
        sessions = [r.session_id for r in runs]
        unique_sessions = sorted(list(set(sessions)))

        if len(unique_sessions) < 2:
            return DriftSignatureResult(
                signature_name="session_step_shift",
                detected=False,
                test_statistic=0.0,
                threshold_or_pvalue=1.0,
                details={"unique_sessions": len(unique_sessions)},
            )

        session_indices = {s_id: [idx for idx, r in enumerate(runs) if r.session_id == s_id] for s_id in unique_sessions}
        session_means_obs = [np.mean(r_obs[session_indices[s_id]]) for s_id in unique_sessions]
        max_shift_obs = float(np.max(session_means_obs) - np.min(session_means_obs))

        detected = False
        p_val = 1.0
        if r_rep.shape[1] > 0:
            s_count = r_rep.shape[1]
            rep_max_shifts = np.empty(s_count)
            for s in range(s_count):
                rep_s = r_rep[:, s]
                s_means = [np.mean(rep_s[session_indices[s_id]]) for s_id in unique_sessions]
                rep_max_shifts[s] = np.max(s_means) - np.min(s_means)
            p_val = float(np.mean(rep_max_shifts >= max_shift_obs))
            detected = p_val < alpha
        else:
            # Shift > 3.0 standard errors between sessions
            detected = max_shift_obs > 1.5

        return DriftSignatureResult(
            signature_name="session_step_shift",
            detected=detected,
            test_statistic=max_shift_obs,
            threshold_or_pvalue=p_val,
            details={
                "session_count": len(unique_sessions),
                "max_shift": max_shift_obs,
                "session_means": dict(zip(unique_sessions, session_means_obs)),
            },
        )

    def evaluate_cusum_signature(
        self,
        r_obs: np.ndarray,
    ) -> DriftSignatureResult:
        """
        Signature 4: Cumulative Sum (CUSUM) Statistical Process Control Monitor.
        Two-sided sequential detector:
          S_k^+ = max(0, S_{k-1}^+ + (X_k - mu_0 - k_slack))
          S_k^- = max(0, S_{k-1}^- - (X_k - mu_0 + k_slack))
        Breaches when S_k > h (default h = 27.0).
        """
        cfg = self.cusum_config
        s_pos = 0.0
        s_neg = 0.0
        s_pos_history = []
        s_neg_history = []

        breach_index = -1
        breach_direction = None

        for k, x in enumerate(r_obs):
            s_pos = max(0.0, s_pos + (x - cfg.target_mu - cfg.slack_k))
            s_neg = max(0.0, s_neg - (x - cfg.target_mu + cfg.slack_k))

            s_pos_history.append(float(s_pos))
            s_neg_history.append(float(s_neg))

            if breach_index == -1:
                if s_pos > cfg.threshold_h:
                    breach_index = k
                    breach_direction = "upward_drift"
                elif s_neg > cfg.threshold_h:
                    breach_index = k
                    breach_direction = "downward_drift"

        max_cusum = float(max(max(s_pos_history), max(s_neg_history)))
        detected = breach_index != -1

        return DriftSignatureResult(
            signature_name="cusum_sequential_monitor",
            detected=detected,
            test_statistic=max_cusum,
            threshold_or_pvalue=cfg.threshold_h,
            details={
                "breach_index": breach_index,
                "breach_direction": breach_direction,
                "max_positive_cusum": float(max(s_pos_history)),
                "max_negative_cusum": float(max(s_neg_history)),
                "slack_k": cfg.slack_k,
                "threshold_h": cfg.threshold_h,
            },
        )

    def audit_runs(self, runs: List[MeasurementRun]) -> CalibrationDriftReport:
        """
        Executes full time-ordered calibration drift audit over measurement runs.
        """
        self.verify_temporal_sequence(runs)

        n = len(runs)
        if n == 0:
            raise ValueError("No measurement runs provided for calibration audit.")

        t = np.array([r.timestamp for r in runs], dtype=float)
        r_obs = np.array([r.standardized_residual for r in runs], dtype=float)

        # Assemble posterior replicas into matrix (n, S)
        s_counts = [len(r.posterior_replicas) for r in runs]
        has_consistent_replicas = len(set(s_counts)) == 1 and s_counts[0] > 0
        if has_consistent_replicas:
            r_rep = np.column_stack([r.replica_standardized_residuals() for r in runs]).T
        else:
            r_rep = np.empty((n, 0), dtype=float)

        trend_res = self.evaluate_trend_signature(t, r_obs, r_rep)
        autocorr_res = self.evaluate_autocorrelation_signature(r_obs, r_rep)
        session_res = self.evaluate_session_shift_signature(runs, r_obs, r_rep)
        cusum_res = self.evaluate_cusum_signature(r_obs)

        any_drift = (
            trend_res.detected
            or autocorr_res.detected
            or session_res.detected
            or cusum_res.detected
        )

        # Recalibration is strictly required if CUSUM breaches threshold or multiple signatures trip
        tripped_count = sum(
            1 for sig in [trend_res, autocorr_res, session_res, cusum_res] if sig.detected
        )
        recalibration_required = cusum_res.detected or tripped_count >= 2

        sessions = set(r.session_id for r in runs)

        return CalibrationDriftReport(
            temporal_ordering_verified=True,
            total_runs=n,
            num_sessions=len(sessions),
            num_replicas=r_rep.shape[1],
            trend_signature=trend_res,
            autocorrelation_signature=autocorr_res,
            session_shift_signature=session_res,
            cusum_signature=cusum_res,
            drift_detected=any_drift,
            recalibration_required=recalibration_required,
        )


def verify_subsystem_calibrations(
    subsystems: Dict[str, Dict[str, Any]]
) -> Dict[str, Any]:
    """
    Check calibration for independent subsystems (e.g. epsilon_r, G, B)
    prior to interpreting full power-observation drift.
    """
    results = {}
    all_calibrated = True

    for name, params in subsystems.items():
        drift_rate = float(params.get("drift_rate", 0.0))
        tolerance = float(params.get("tolerance", 0.05))
        is_valid = abs(drift_rate) <= tolerance
        if not is_valid:
            all_calibrated = False
        results[name] = {
            "drift_rate": drift_rate,
            "tolerance": tolerance,
            "calibrated": is_valid,
        }

    return {
        "all_subsystems_calibrated": all_calibrated,
        "subsystems": results,
    }
