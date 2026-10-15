"""
OSIRIS L0 Intake: Task Run Record
================================
Implements bounded run isolation per task, tracking capability permissions,
compute token budget ceilings, and maximum execution horizons.
"""

from __future__ import annotations

import hashlib
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from .schemas import TaskSpec


@dataclass
class TaskRunRecord:
    task_spec: TaskSpec
    granted_permissions: List[str] = field(default_factory=list)
    token_budget: int = 4096
    max_walltime_seconds: float = 300.0  # Default 300s temporal lock
    run_id: str = field(default_factory=lambda: "")
    status: str = "PENDING"  # PENDING, ACTIVE, COMPLETED, FAILED, BLOCKED
    start_time: float = field(default_factory=time.time)
    end_time: Optional[float] = None
    tokens_used: int = 0
    events: List[Dict[str, Any]] = field(default_factory=list)

    def __post_init__(self):
        if not self.run_id:
            h = hashlib.sha256(
                f"{self.task_spec.task_id}:{self.start_time}:{uuid.uuid4().hex[:8]}".encode("utf-8")
            ).hexdigest()
            self.run_id = f"run_{h[:16]}"

    def start(self) -> None:
        self.status = "ACTIVE"
        self.start_time = time.time()
        self.log_event("RUN_STARTED", {"run_id": self.run_id, "task_id": self.task_spec.task_id})

    def record_token_usage(self, count: int) -> bool:
        """Accumulate token usage. Returns False if budget ceiling exceeded."""
        self.tokens_used += count
        if self.tokens_used > self.token_budget:
            self.status = "BLOCKED"
            self.log_event("BUDGET_EXCEEDED", {"used": self.tokens_used, "ceiling": self.token_budget})
            return False
        return True

    def check_walltime(self) -> bool:
        """Returns True if within walltime horizon; marks FAILED if expired."""
        elapsed = time.time() - self.start_time
        if elapsed > self.max_walltime_seconds:
            self.status = "FAILED"
            self.log_event("WALLTIME_EXPIRED", {"elapsed": elapsed, "limit": self.max_walltime_seconds})
            return False
        return True

    def can_perform(self, permission: str) -> bool:
        """Check if permission was granted for this run."""
        return permission in self.granted_permissions or "all" in self.granted_permissions

    def finish(self, success: bool = True, details: Optional[Dict[str, Any]] = None) -> None:
        self.end_time = time.time()
        self.status = "COMPLETED" if success else "FAILED"
        self.log_event("RUN_FINISHED", {"status": self.status, "duration": self.end_time - self.start_time, "details": details or {}})

    def log_event(self, event_type: str, payload: Dict[str, Any]) -> None:
        self.events.append({
            "timestamp": time.time(),
            "event_type": event_type,
            "payload": payload,
        })
