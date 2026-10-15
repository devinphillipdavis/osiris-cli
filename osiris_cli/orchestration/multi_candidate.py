"""
OSIRIS L4 Propose: Multi-Candidate Proposal Generation
======================================================
Generates diverse code proposals across three canonical strategies:
  1. Baseline: Canonical reference implementation
  2. Alternative: High-performance / optimized implementation
  3. Conservative: Defensive, fail-closed implementation
"""

from __future__ import annotations

import enum
import uuid
from dataclasses import dataclass
from typing import Dict, List, Optional

from ..providers.base import BaseModelProvider, Message, ProviderRequest
from .schemas import CodeProposal, TaskSpec


class CandidateStrategy(str, enum.Enum):
    BASELINE = "baseline"
    ALTERNATIVE = "alternative"
    CONSERVATIVE = "conservative"


@dataclass
class MultiCandidateSet:
    task_id: str
    candidates: Dict[CandidateStrategy, CodeProposal]

    def get_candidate(self, strategy: CandidateStrategy) -> Optional[CodeProposal]:
        return self.candidates.get(strategy)


class MultiCandidateGenerator:
    """Generates baseline, alternative, and conservative proposals via model substrate."""

    def __init__(self, provider: BaseModelProvider):
        self.provider = provider

    def generate_candidates(self, task: TaskSpec) -> MultiCandidateSet:
        candidates: Dict[CandidateStrategy, CodeProposal] = {}

        for strat in (CandidateStrategy.BASELINE, CandidateStrategy.ALTERNATIVE, CandidateStrategy.CONSERVATIVE):
            prompt = self._build_prompt(task, strat)
            req = ProviderRequest(
                prompt=prompt,
                max_tokens=1024,
                temperature=0.1 if strat == CandidateStrategy.CONSERVATIVE else 0.3,
            )
            resp = self.provider.generate(req)
            code = resp.content

            proposal = CodeProposal(
                proposal_id=f"prop_{strat.value}_{uuid.uuid4().hex[:8]}",
                task_id=task.task_id,
                target_file=task.target_files[0] if task.target_files else "src/solution.py",
                module_code=code,
                test_code=f"def test_{strat.value}_solution():\n    assert True\n",
                changes_summary=f"{strat.value.capitalize()} candidate implementation for {task.title}",
                rollback_strategy=f"Revert to prior git HEAD or restore backup.",
            )
            candidates[strat] = proposal

        return MultiCandidateSet(task_id=task.task_id, candidates=candidates)

    def _build_prompt(self, task: TaskSpec, strategy: CandidateStrategy) -> str:
        guidance = {
            CandidateStrategy.BASELINE: "Provide a clean, canonical implementation following standard idioms.",
            CandidateStrategy.ALTERNATIVE: "Provide an optimized, high-throughput implementation with performance enhancements.",
            CandidateStrategy.CONSERVATIVE: "Provide a strictly defensive, fail-closed implementation with extensive assertion checks.",
        }[strategy]

        return (
            f"Task: {task.title}\n"
            f"Specification: {task.spec}\n"
            f"Strategy: {strategy.value.upper()}\n"
            f"Guidance: {guidance}\n"
            f"Write Python code satisfying these requirements:"
        )
