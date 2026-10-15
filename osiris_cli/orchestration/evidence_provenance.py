"""
OSIRIS L3 Evidence: Provenance Record Binding
============================================
Binds registered claims, experimental observations, and research notes
to verifiable SHA-256 provenance records, enforcing SYS-022 and SYS-024.
"""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class ProvenanceRecord:
    claim_id: str
    source_artifact: str  # File path, git commit hash, or formal citation
    artifact_hash: str    # SHA-256 of source content
    verified_by: str      # e.g. "pytest:test_quantum_fitness", "human_registered"
    timestamp: float = field(default_factory=time.time)
    metadata: Dict[str, Any] = field(default_factory=dict)
    merkle_leaf: str = field(default_factory=lambda: "")

    def __post_init__(self):
        if not self.merkle_leaf:
            payload = json.dumps({
                "claim_id": self.claim_id,
                "source": self.source_artifact,
                "hash": self.artifact_hash,
                "verifier": self.verified_by,
                "timestamp": self.timestamp,
            }, sort_keys=True).encode("utf-8")
            self.merkle_leaf = hashlib.sha256(payload).hexdigest()


class EvidenceProvenanceRegistry:
    """Manages verifiable provenance records and Merkle proof generation for L3 Evidence."""

    def __init__(self):
        self._records: Dict[str, ProvenanceRecord] = {}

    def register_evidence(
        self,
        claim_id: str,
        source_artifact: str,
        content_bytes: bytes,
        verified_by: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> ProvenanceRecord:
        h = hashlib.sha256(content_bytes).hexdigest()
        rec = ProvenanceRecord(
            claim_id=claim_id,
            source_artifact=source_artifact,
            artifact_hash=h,
            verified_by=verified_by,
            metadata=metadata or {},
        )
        self._records[claim_id] = rec
        return rec

    def get_record(self, claim_id: str) -> Optional[ProvenanceRecord]:
        return self._records.get(claim_id)

    def verify_provenance(self, claim_id: str, expected_content_bytes: bytes) -> bool:
        rec = self.get_record(claim_id)
        if not rec:
            return False
        h = hashlib.sha256(expected_content_bytes).hexdigest()
        return rec.artifact_hash == h

    def compute_merkle_root(self) -> str:
        """Compute Merkle root across all registered provenance leaves."""
        leaves = [rec.merkle_leaf for rec in sorted(self._records.values(), key=lambda r: r.claim_id)]
        if not leaves:
            return hashlib.sha256(b"genesis_provenance").hexdigest()

        current_level = list(leaves)
        while len(current_level) > 1:
            next_level = []
            for i in range(0, len(current_level), 2):
                left = current_level[i]
                right = current_level[i + 1] if i + 1 < len(current_level) else left
                combined = hashlib.sha256((left + right).encode("utf-8")).hexdigest()
                next_level.append(combined)
            current_level = next_level

        return current_level[0]
