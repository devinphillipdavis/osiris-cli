#!/usr/bin/env python3
"""
governance_ledger.py
====================
Governance & Merkle Provenance Anchor Engine for the Tau-Phase Anomaly & Erratum v4.2.0.

Aggregates:
  1. Source Digest (H_source).
  2. Formalization Audit Digest (H_formal).
  3. Forensic Challenge Digest (H_challenge).
  4. Controlled Falsification Digest (H_experiment).

Enforces:
  SYS-021: Payload-Bound Grant (GRANT-TAU-ERRATUM-001).
  SYS-023: Merkle DAG Provenance Ledger commitment.
  SYS-024: Claims Firewall status: REFUTED / QUARANTINED (operational_allowed = False).
"""

import sys
import os
import json
import hashlib
from datetime import datetime, timezone
from typing import Dict, Any, List


def hash_file(filepath: str) -> str:
    h = hashlib.sha256()
    with open(filepath, "rb") as f:
        while chunk := f.read(8192):
            h.update(chunk)
    return h.hexdigest()


def compute_merkle_root(hashes: List[str]) -> str:
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
        "grant_id": "GRANT-TAU-ERRATUM-001",
        "grant_type": "SCIENTIFIC_ERRATUM_GOVERNANCE_AUDIT",
        "subject": "Tau-Phase Anomaly & Theta-Lock Refutation (Erratum v4.2.0)",
        "organism_id": "tau_phase_erratum_study",
        "merkle_root": merkle_root,
        "leaf_hashes": leaf_hashes,
        "claims_firewall_status": {
            "THETA_LOCK": "REFUTED",
            "K8_REVIVAL": "REFUTED",
            "F_MAX": "REFUTED",
            "LAMBDA_PHI": "NOT_MEASURED",
            "NEGENTROPY_136": "ARTIFACT_DISPROVED"
        },
        "operational_invariants": {
            "operational_allowed": False,
            "runtime_coherence_floor": 0.0920,
            "universal_memory_invariant_kg": 2.176435e-8,
            "bell_state_fidelity_ceiling_allowed": False
        },
        "governance_standard": "SYS-021 / SYS-023 / SYS-024",
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "status": "SEALED_REFUTED"
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
            "payload_digest": leaf_hashes["H_experiment"],
            "digest_algorithm": "SHA-256",
            "author": "Devin Phillip Davis",
            "organization": "Agile Defense Systems LLC",
            "status": "SEALED_REFUTED",
            "governance_standard": "SYS-021",
            "timestamp_utc": grant_entry["timestamp_utc"]
        })
        with open(master_registry, "a", encoding="utf-8") as f:
            f.write(registry_line + "\n")

    return grant_entry


if __name__ == "__main__":
    entry = record_provenance()
    print("=== GOVERNANCE & MERKLE LEDGER COMMIT: TAU-PHASE ===")
    print(f"Grant ID:         {entry['grant_id']}")
    print(f"Merkle Root:      {entry['merkle_root']}")
    print(f"H_source:         {entry['leaf_hashes']['H_source']}")
    print(f"H_formalize:      {entry['leaf_hashes']['H_formalize']}")
    print(f"H_challenge:      {entry['leaf_hashes']['H_challenge']}")
    print(f"H_experiment:     {entry['leaf_hashes']['H_experiment']}")
    print(f"Status:           {entry['status']}")
