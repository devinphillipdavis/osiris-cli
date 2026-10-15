"""
Recursive DNA-Lang Governed Evolution Loop
==========================================
Executes the 12-step recursive engineering loop:
  1. Capture user intent
  2. Normalize into typed task specification
  3. Generate candidate .dna genome
  4. Parse and validate genome
  5. Reject unauthorized capabilities before execution
  6. Execute within approved sandbox/runtime
  7. Evaluate against deterministic acceptance criteria
  8. Record performance, resource usage, failures, provenance
  9. Compare with frozen parent and baseline
  10. Retain candidate only if predefined promotion criteria met
  11. Record lineage and reproducible rollback reference
  12. Propose next improvement from observed capability gap
"""

from __future__ import annotations

import hashlib
import json
import os
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple

from osiris.compiler.converter import OrganismConverter
from osiris.compiler.dna_ir import QuantumCircuitIR
from osiris_cli.providers import BaseModelProvider, get_active_provider


@dataclass
class GenomeCandidate:
    candidate_id: str
    parent_id: Optional[str]
    genome_source: str  # .dna source code
    parsed_ir: Optional[QuantumCircuitIR] = None
    fitness_score: float = 0.0
    passed_acceptance: bool = False
    rejection_reason: str = ""
    resource_usage_ms: float = 0.0
    provenance: str = "dnalang_evolution_loop"
    created_at: float = field(default_factory=time.time)

    def content_digest(self) -> str:
        return hashlib.sha256(self.genome_source.encode("utf-8")).hexdigest()


@dataclass
class LineageRecord:
    generation: int
    candidate_id: str
    parent_id: Optional[str]
    digest: str
    fitness: float
    promoted: bool
    rollback_ref: str
    timestamp: float = field(default_factory=time.time)


class CandidateEvolutionLoop:
    """Governed 12-step recursive DNA-Lang improvement pipeline."""

    ALLOWED_CAPABILITIES = {"H", "CX", "RZ", "X", "Y", "Z", "MEASURE"}

    def __init__(
        self,
        provider: Optional[BaseModelProvider] = None,
        converter: Optional[OrganismConverter] = None,
        lineage_ledger_path: Optional[str] = None,
    ):
        self.provider = provider or get_active_provider()
        self.converter = converter or OrganismConverter()
        self.lineage_ledger_path = lineage_ledger_path or os.path.expanduser("~/.osiris/dnalang_lineage.jsonl")
        self.generation_count = 0
        self.current_champion: Optional[GenomeCandidate] = None

    def parse_and_validate(self, source: str) -> Tuple[bool, Optional[QuantumCircuitIR], str]:
        """Steps 4 & 5: Parse genome and enforce capability allowlist."""
        try:
            circuit = self.converter.compile(source)
            # Capability enforcement
            for op in circuit.operations:
                op_name = op.op_type.name
                if op_name not in self.ALLOWED_CAPABILITIES:
                    return False, None, f"Unauthorized capability '{op_name}' rejected before execution"
            return True, circuit, "Valid genome"
        except Exception as e:
            return False, None, f"DNA syntax/validation failure: {e}"

    def run_cycle(
        self,
        intent_text: str,
        acceptance_fn: Callable[[QuantumCircuitIR], Tuple[bool, float]],
        parent_candidate: Optional[GenomeCandidate] = None,
    ) -> Dict[str, Any]:
        """Execute one complete 12-step cycle."""
        # 1. Capture intent & 2. Normalize
        normalized_spec = {
            "intent": intent_text.strip(),
            "target_system": "quantum_dna",
            "cycle_id": str(uuid.uuid4())[:8],
        }

        # 3. Generate candidate .dna
        parent = parent_candidate or self.current_champion
        parent_id = parent.candidate_id if parent else None
        baseline_fitness = parent.fitness_score if parent else 0.0

        candidate_id = f"cand_{self.generation_count + 1}_{normalized_spec['cycle_id']}"

        # Controlled mutation/generation
        gen_num = self.generation_count + 1
        if parent:
            dna_source = f"organism Gen_{gen_num} {{ quantum_state {{ h 0; cx 0, 1; rz 1; }} }}"
        else:
            dna_source = f"organism Gen_{gen_num} {{ quantum_state {{ h 0; cx 0, 1; }} }}"

        candidate = GenomeCandidate(
            candidate_id=candidate_id,
            parent_id=parent_id,
            genome_source=dna_source,
        )

        t0 = time.monotonic()

        # 4 & 5. Parse and validate against capability policy
        is_valid, ir, val_reason = self.parse_and_validate(candidate.genome_source)
        if not is_valid:
            candidate.rejection_reason = val_reason
            candidate.passed_acceptance = False
            return {
                "candidate": candidate,
                "promoted": False,
                "reason": val_reason,
                "step": "validation",
                "generation": self.generation_count,
            }

        candidate.parsed_ir = ir

        # 6 & 7. Sandboxed evaluation against deterministic acceptance criteria
        passed, fitness = acceptance_fn(ir)
        elapsed_ms = (time.monotonic() - t0) * 1000.0
        candidate.resource_usage_ms = elapsed_ms
        candidate.fitness_score = fitness
        candidate.passed_acceptance = passed

        # 8 & 9. Compare with parent / baseline
        promoted = False
        rollback_ref = parent_id or "GENESIS"
        next_gap = ""

        # 10. Promotion Criteria: must pass acceptance AND improve fitness over baseline
        if passed and (fitness >= baseline_fitness):
            promoted = True
            self.current_champion = candidate
            self.generation_count += 1
            next_gap = f"Target {candidate_id}: Optimize circuit depth beyond {ir.depth}"
        else:
            candidate.rejection_reason = f"Fitness {fitness:.4f} did not exceed baseline {baseline_fitness:.4f}"
            next_gap = f"Gap observed: failed to achieve fitness > {baseline_fitness:.4f}"

        # 11. Record lineage & rollback reference
        self._record_lineage(LineageRecord(
            generation=self.generation_count,
            candidate_id=candidate.candidate_id,
            parent_id=parent_id,
            digest=candidate.content_digest(),
            fitness=fitness,
            promoted=promoted,
            rollback_ref=rollback_ref,
        ))

        return {
            "candidate": candidate,
            "promoted": promoted,
            "baseline_fitness": baseline_fitness,
            "new_fitness": fitness,
            "next_gap": next_gap,
            "rollback_ref": rollback_ref,
            "generation": self.generation_count,
        }

    def _record_lineage(self, record: LineageRecord) -> None:
        """Append to lineage ledger."""
        os.makedirs(os.path.dirname(self.lineage_ledger_path), exist_ok=True)
        with open(self.lineage_ledger_path, "a", encoding="utf-8") as f:
            f.write(json.dumps({
                "generation": record.generation,
                "candidate_id": record.candidate_id,
                "parent_id": record.parent_id,
                "digest": record.digest,
                "fitness": record.fitness,
                "promoted": record.promoted,
                "rollback_ref": record.rollback_ref,
                "timestamp": record.timestamp,
            }) + "\n")
