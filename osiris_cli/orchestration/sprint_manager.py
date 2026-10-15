"""
OSIRIS L2 Orchestrator: Sprint Manager & Stopping Conditions
============================================================
Enforces task-bound step budgets, walltime horizon bounds, and empirical
convergence stopping conditions across iterative agent execution.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple


@dataclass
class SprintState:
    sprint_id: str
    max_steps: int = 10
    current_step: int = 0
    start_time: float = field(default_factory=time.time)
    max_duration_seconds: float = 300.0
    loss_history: List[float] = field(default_factory=list)
    convergence_threshold: float = 0.005
    convergence_window: int = 3
    is_converged: bool = False
    is_aborted: bool = False
    abort_reason: str = ""
    step_records: List[Dict[str, Any]] = field(default_factory=list)

    def advance_step(self, step_metrics: Dict[str, Any], loss: Optional[float] = None) -> None:
        self.current_step += 1
        if loss is not None:
            self.loss_history.append(loss)
            self._check_convergence()
        self.step_records.append({
            "step": self.current_step,
            "timestamp": time.time(),
            "metrics": step_metrics,
            "loss": loss,
        })

    def _check_convergence(self) -> None:
        if len(self.loss_history) >= self.convergence_window:
            recent = self.loss_history[-self.convergence_window:]
            deltas = [abs(recent[i] - recent[i - 1]) for i in range(1, len(recent))]
            if max(deltas) <= self.convergence_threshold:
                self.is_converged = True

    def should_stop(self) -> Tuple[bool, str]:
        """Evaluate all stopping criteria."""
        if self.is_aborted:
            return True, f"Aborted: {self.abort_reason}"
        if self.current_step >= self.max_steps:
            return True, f"Step budget exhausted ({self.current_step}/{self.max_steps})"
        elapsed = time.time() - self.start_time
        if elapsed >= self.max_duration_seconds:
            return True, f"Execution horizon expired ({elapsed:.1f}s >= {self.max_duration_seconds}s)"
        if self.is_converged:
            return True, f"Converged: delta <= {self.convergence_threshold} over {self.convergence_window} steps"
        return False, "Continuing"

    def abort(self, reason: str) -> None:
        self.is_aborted = True
        self.abort_reason = reason


class SprintManager:
    """Orchestrates multi-agent sprint execution bounds."""

    def __init__(self, default_max_steps: int = 10, default_horizon_s: float = 300.0):
        self.default_max_steps = default_max_steps
        self.default_horizon_s = default_horizon_s

    def create_sprint(self, sprint_id: str, max_steps: Optional[int] = None, horizon_s: Optional[float] = None) -> SprintState:
        return SprintState(
            sprint_id=sprint_id,
            max_steps=max_steps or self.default_max_steps,
            max_duration_seconds=horizon_s or self.default_horizon_s,
        )
