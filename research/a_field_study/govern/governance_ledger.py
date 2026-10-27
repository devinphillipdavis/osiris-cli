#!/usr/bin/env python3
"""
governance_ledger.py
====================
Governance & Merkle Provenance Anchor Engine for the A-Field Research Organism.

Aggregates:
  1. Ingestion Source Digest (H_source).
  2. Formalization Symbolic & Precision Digest (H_formal).
  3. Adversarial Challenge Digest (H_challenge).
  4. Falsification Experiment Digest (H_experiment).

Enforces:
  SYS-021: Payload-Bound Authorization Grant (GRANT-AFIELD-001).
  SYS-023: Merkle DAG Provenance Ledger commitment.
  SYS-024: Claims Firewall Quarantine status tracking.
"""

import sys
import os
import json
import hashlib
from datetime import datetime, timezone
from typing import Dict, Any


def hash_file(filepath: str) -> str:
    h = hashlib.sha256()
    with open(filepath, "rb") as f:
        while chunk := f.read(8192):
            h.update(chunk)
    return h.hexdigest()


def compute_merkle_root(hashes: list[str]) -> str:
    """Computes a binary Merkle tree root from an array of hex hashes."""
    if not hashes:
        return hashlib.sha256(b"").hexdigest()
    current = sorted(hashes)
    while len(current) > 1:
        next_level = []
        for i in range(0, len(current), 2):
            left = current[i]
            right = current[i+1] if i+1 < len(current) else current[i]
            combined = hashlib.sha256((left + right).encode("utf-8")).hexdigest()
            next_level.append(combined)
        current = next_level
    return current[0]


def record_provenance() -> Dict[str, Any]:
    base_dir = os.path.dirname(os.path.dirname(__file__))

    source_path = os.path.join(base_dir, "ingest", "source_document.txt")
    formal_path = os.path.join(base_dir, "formalize", "formalize_report.json")
    challenge_path = os.path.join(base_dir, "challenge", "challenge_verdict.json")
    experiment_path = os.path.join(base_dir, "experiments", "experiment_results.json")

    leaf_hashes = {
        "H_source": hash_file(source_path),
        "H_formalize": hash_file(formal_path),
        "H_challenge": hash_file(challenge_path),
        "H_experiment": hash_file(experiment_path),
    }

    merkle_root = compute_merkle_root(list(leaf_hashes.values()))

    grant_entry = {
        "grant_id": "GRANT-AFIELD-001",
        "grant_type": "SCIENTIFIC_RESEARCH_ORGANISM_AUDIT",
        "subject": "The Fine-Structure Constant as an A-Field Quantity: Impedance, Flux, and Prefactor Pair Structure",
        "organism_id": "alpha_a_field_study",
        "merkle_root": merkle_root,
        "leaf_hashes": leaf_hashes,
        "claims_firewall_status": {
            "ALPHA-CLAIM-001": "VERIFIED_ARTIFACT",
            "ALPHA-CLAIM-002": "SUPPORTED_REPRESENTATION_ACCOUNTING",
            "ALPHA-CLAIM-003": "QUARANTINED_MODEL_PROPOSED",
            "ALPHA-CLAIM-004": "QUARANTINED_OPEN_THEORY",
            "ALPHA-CLAIM-005": "QUARANTINED_OPEN_THEORY",
            "ALPHA-CLAIM-006": "QUARANTINED_OVERCLAIM"
        },
        "gates_status": {
            "GATE-01": "PASS",
            "GATE-02": "BLOCKED",
            "GATE-03": "BLOCKED",
            "GATE-04": "BLOCKED"
        },
        "governance_standard": "SYS-021 / SYS-023 / SYS-024",
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "status": "SEALED_QUARANTINE"
    }

    # Write anchor to govern directory
    anchor_file = os.path.join(os.path.dirname(__file__), "merkle_provenance_anchor.json")
    with open(anchor_file, "w", encoding="utf-8") as f:
        json.dump(grant_entry, f, indent=2)

    # Append to master grants_registry.jsonl in osiris-cli/provenance
    repo_root = os.path.dirname(os.path.dirname(base_dir))
    master_registry = os.path.join(repo_root, "provenance", "grants_registry.jsonl")
    if os.path.exists(master_registry):
        registry_line = json.dumps({
            "grant_id": grant_entry["grant_id"],
            "grant_type": grant_entry["grant_type"],
            "subject": grant_entry["subject"],
            "merkle_root": merkle_root,
            "payload_digest": leaf_hashes["H_formalize"],
            "digest_algorithm": "SHA-256",
            "author": "Devin Phillip Davis",
            "organization": "Agile Defense Systems LLC",
            "status": "SEALED_QUARANTINE",
            "governance_standard": "SYS-021",
            "timestamp_utc": grant_entry["timestamp_utc"]
        })
        with open(master_registry, "a", encoding="utf-8") as f:
            f.write(registry_line + "\n")

    return grant_entry


if __name__ == "__main__":
    entry = record_provenance()
    print("=== GOVERNANCE & MERKLE LEDGER COMMIT ===")
    print(f"Grant ID:         {entry['grant_id']}")
    print(f"Merkle Root:      {entry['merkle_root']}")
    print(f"H_source:         {entry['leaf_hashes']['H_source']}")
    print(f"H_formalize:      {entry['leaf_hashes']['H_formalize']}")
    print(f"H_challenge:      {entry['leaf_hashes']['H_challenge']}")
    print(f"H_experiment:     {entry['leaf_hashes']['H_experiment']}")
    print(f"Status:           {entry['status']}")
