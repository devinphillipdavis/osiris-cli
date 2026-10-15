"""
OSIRIS L1 Intent Router: Risk Tiering & Cost-of-Error Scoring
============================================================
Routes user intents and programmatic task specs into risk tiers with
mathematical cost-of-error scores, assigning required governance gates.
"""

from __future__ import annotations

import enum
import re
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from .schemas import IntentProposal


class RiskTier(str, enum.Enum):
    TIER_1_CLEAN = "tier_1_clean"                   # 0.00: Read-only inspection, help, query
    TIER_2_OBSERVATION = "tier_2_observation"       # 0.10: Code reading, test execution, benchmarks
    TIER_3_MUTATING = "tier_3_mutating"             # 0.60: File modification, code proposals
    TIER_4_CRITICAL = "tier_4_critical_security"    # 0.95: Governance, compute expenditure, system calls


@dataclass
class IntentRoutingDecision:
    intent_proposal: IntentProposal
    risk_tier: RiskTier
    cost_of_error: float
    required_gates: List[str]
    requires_human_grant: bool
    rationale: str


class IntentRouter:
    """Classifies user intent, computes cost-of-error, and assigns governance gates."""

    READ_ONLY_PATTERNS = [
        r"^\s*/?(status|why|home|runs|help|ui|mentors|digest|introspect|physics|check)",
        r"\b(what is|explain|show|view|query|read|inspect)\b",
    ]

    MUTATING_PATTERNS = [
        r"^\s*/?(apply|ignite|sprint|metamorphosis|learn|train|dna)",
        r"\b(write|create|modify|patch|refactor|update|delete|overwrite|synthesize)\b",
    ]

    CRITICAL_PATTERNS = [
        r"\b(policy\.json|cloudbuild\.yaml|QUARANTINE_NOTICE\.md|os\.system|subprocess|eval|exec)\b",
        r"\b(grant|authorize|bypass|spend|root|enclave_admin)\b",
    ]

    def evaluate(self, raw_prompt: str, domain: str = "general") -> IntentRoutingDecision:
        p_lower = raw_prompt.lower().strip()

        # Check critical security patterns first
        for pat in self.CRITICAL_PATTERNS:
            if re.search(pat, p_lower):
                intent = IntentProposal(
                    intent_id=f"intent_{uuid.uuid4().hex[:8]}",
                    raw_prompt=raw_prompt,
                    intent_type="critical_security",
                    domain=domain,
                    confidence=0.98,
                    risk_level="critical",
                )
                return IntentRoutingDecision(
                    intent_proposal=intent,
                    risk_tier=RiskTier.TIER_4_CRITICAL,
                    cost_of_error=0.95,
                    required_gates=["GATE_AST_FIREWALL", "GATE_PAYLOAD_GRANT", "GATE_AUDIT_LEDGER"],
                    requires_human_grant=True,
                    rationale="Triggered critical security or governance protection rule.",
                )

        # Check mutating patterns
        for pat in self.MUTATING_PATTERNS:
            if re.search(pat, p_lower):
                intent = IntentProposal(
                    intent_id=f"intent_{uuid.uuid4().hex[:8]}",
                    raw_prompt=raw_prompt,
                    intent_type="code_modification",
                    domain=domain,
                    confidence=0.90,
                    risk_level="high",
                )
                return IntentRoutingDecision(
                    intent_proposal=intent,
                    risk_tier=RiskTier.TIER_3_MUTATING,
                    cost_of_error=0.60,
                    required_gates=["GATE_AST_FIREWALL", "GATE_PAYLOAD_GRANT"],
                    requires_human_grant=True,
                    rationale="Mutates files, genome, or advances state machine (SYS-021 bound).",
                )

        # Check read-only patterns
        for pat in self.READ_ONLY_PATTERNS:
            if re.search(pat, p_lower):
                intent = IntentProposal(
                    intent_id=f"intent_{uuid.uuid4().hex[:8]}",
                    raw_prompt=raw_prompt,
                    intent_type="query",
                    domain=domain,
                    confidence=0.95,
                    risk_level="low",
                )
                return IntentRoutingDecision(
                    intent_proposal=intent,
                    risk_tier=RiskTier.TIER_1_CLEAN,
                    cost_of_error=0.00,
                    required_gates=["GATE_READ_ONLY"],
                    requires_human_grant=False,
                    rationale="Inspection command or informational query without side-effects.",
                )

        # Default fallback to observation tier
        intent = IntentProposal(
            intent_id=f"intent_{uuid.uuid4().hex[:8]}",
            raw_prompt=raw_prompt,
            intent_type="general_reasoning",
            domain=domain,
            confidence=0.80,
            risk_level="low",
        )
        return IntentRoutingDecision(
            intent_proposal=intent,
            risk_tier=RiskTier.TIER_2_OBSERVATION,
            cost_of_error=0.10,
            required_gates=["GATE_PROVENANCE_LOG"],
            requires_human_grant=False,
            rationale="Standard reasoning or conversational interaction.",
        )
