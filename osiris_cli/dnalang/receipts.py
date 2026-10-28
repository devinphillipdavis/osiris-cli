"""
DNA-Lang Typed Evaluation Receipts & Proof-Carrying Evidence (SYS-021 / SYS-023)
================================================================================
Enforces proof-carrying evolution:
  - EvaluationReceipt: cryptographically bound measurement receipt.
  - PromotionPolicy: deterministic, strictly non-tie, non-NaN/inf promotion gate.
"""

from __future__ import annotations

import hashlib
import json
import math
import time
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, Optional, Tuple


@dataclass
class EvaluationReceipt:
    """
    Cryptographically verifiable evaluation receipt binding:
    - Candidate digest
    - Parent lineage
    - Evaluator version
    - Input artifacts hash
    - Measured metric, value, and uncertainty
    """
    candidate_id: str
    candidate_digest: str
    parent_id: Optional[str]
    evaluator_id: str
    evaluator_version: str
    metric_name: str
    fitness_score: float
    uncertainty: float = 0.0
    passed: bool = True
    input_artifacts_hash: str = ""
    details: Dict[str, Any] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)
    receipt_digest: str = field(default_factory=lambda: "")

    def __post_init__(self):
        if not self.receipt_digest:
            self.receipt_digest = self.compute_digest()

    def compute_digest(self) -> str:
        """RFC 8785 canonical byte digest over immutable fields."""
        payload = {
            "candidate_id": self.candidate_id,
            "candidate_digest": self.candidate_digest,
            "parent_id": self.parent_id,
            "evaluator_id": self.evaluator_id,
            "evaluator_version": self.evaluator_version,
            "metric_name": self.metric_name,
            "fitness_score": self.fitness_score,
            "uncertainty": self.uncertainty,
            "passed": self.passed,
            "input_artifacts_hash": self.input_artifacts_hash,
            "timestamp": self.timestamp,
        }
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        return hashlib.sha256(canonical).hexdigest()

    def is_valid_score(self) -> Tuple[bool, str]:
        """Verify numeric validity of score."""
        if math.isnan(self.fitness_score):
            return False, "Fitness score is NaN"
        if math.isinf(self.fitness_score):
            return False, "Fitness score is Infinite"
        if self.fitness_score < 0.0:
            return False, f"Fitness score {self.fitness_score} is negative"
        return True, "Valid score"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> EvaluationReceipt:
        return cls(**data)


@dataclass
class PromotionPolicy:
    """
    Deterministic gate governing whether a candidate replaces the current champion.
    Strictly forbids tie replacements, regressions, and ungrounded improvements.
    """
    min_improvement: float = 0.0001
    allow_ties: bool = False
    require_receipt_match: bool = True
    max_uncertainty: float = 0.20

    def evaluate_promotion(
        self,
        candidate_receipt: EvaluationReceipt,
        champion_receipt: Optional[EvaluationReceipt],
        expected_candidate_digest: str,
    ) -> Tuple[bool, str]:
        """
        Evaluate candidate against champion under strict proof-carrying criteria.
        Returns:
            (promoted: bool, reason: str)
        """
        # 1. Payload digest binding (tamper prevention per SYS-021)
        if self.require_receipt_match and (candidate_receipt.candidate_digest != expected_candidate_digest):
            return False, (
                f"PROMOTION_REJECTED (SYS-021): Candidate digest mismatch. "
                f"Receipt claims {candidate_receipt.candidate_digest[:16]}..., "
                f"Actual payload is {expected_candidate_digest[:16]}..."
            )

        # 2. Deterministic acceptance criteria pass
        if not candidate_receipt.passed:
            return False, "PROMOTION_REJECTED: Candidate failed deterministic acceptance criteria"

        # 3. Numeric validity (reject NaN / inf)
        valid_score, score_msg = candidate_receipt.is_valid_score()
        if not valid_score:
            return False, f"PROMOTION_REJECTED: {score_msg}"

        # 4. Uncertainty ceiling
        if candidate_receipt.uncertainty > self.max_uncertainty:
            return False, (
                f"PROMOTION_REJECTED: Uncertainty {candidate_receipt.uncertainty:.4f} "
                f"exceeds ceiling {self.max_uncertainty:.4f}"
            )

        # 5. Genesis establishment
        if champion_receipt is None:
            return True, "PROMOTED: Genesis champion established"

        # 6. Baseline comparison
        baseline = champion_receipt.fitness_score
        cand_score = candidate_receipt.fitness_score

        if math.isnan(baseline) or math.isinf(baseline):
            return True, "PROMOTED: Prior champion score was invalid numeric value"

        # Regression check
        if cand_score < baseline:
            return False, f"PROMOTION_REJECTED: Fitness regression ({cand_score:.4f} < {baseline:.4f})"

        # Tie check
        diff = cand_score - baseline
        if abs(diff) < 1e-9:
            if not self.allow_ties:
                return False, f"PROMOTION_REJECTED: Fitness tie ({cand_score:.4f} == {baseline:.4f}) rejected by strict improvement policy"

        # Minimum improvement check
        if diff < self.min_improvement:
            return False, (
                f"PROMOTION_REJECTED: Improvement {diff:.5f} below minimum threshold {self.min_improvement:.5f}"
            )

        return True, f"PROMOTED: Fitness improved from {baseline:.4f} to {cand_score:.4f} (+{diff:.4f})"
