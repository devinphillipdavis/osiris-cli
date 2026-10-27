#!/usr/bin/env python3
"""
measure_organism.py
===================
Adversarial Measurement & Governance Scorecard for the Tau-Phase Erratum Organism.

Evaluates:
  Test 1: Claims register integrity: verified REFUTED status for theta_lock and K8.
  Test 2: Operational lock enforcement: operational_allowed = False.
  Test 3: Active invariant protection: Gamma_floor = 0.0920 preserved; refuted constants locked out.

Outputs:
  measurement_scorecard.json
"""

import sys
import os
import json
from typing import Dict, Any


def run_measurement_battery() -> Dict[str, Any]:
    base_dir = os.path.dirname(os.path.dirname(__file__))

    formal_path = os.path.join(base_dir, "formalize", "formalize_report.json")
    challenge_path = os.path.join(base_dir, "challenge", "challenge_verdict.json")
    govern_path = os.path.join(base_dir, "govern", "merkle_provenance_anchor.json")
    exp_path = os.path.join(base_dir, "experiments", "experiment_results.json")

    with open(formal_path, "r", encoding="utf-8") as f:
        formal_data = json.load(f)
    with open(challenge_path, "r", encoding="utf-8") as f:
        challenge_data = json.load(f)
    with open(govern_path, "r", encoding="utf-8") as f:
        govern_data = json.load(f)
    with open(exp_path, "r", encoding="utf-8") as f:
        exp_data = json.load(f)

    # ---------------------------------------------------------
    # Test 1: Claims Register Integrity (Refutations Verified)
    # ---------------------------------------------------------
    claims_status = govern_data["claims_firewall_status"]
    test1_pass = (
        claims_status["THETA_LOCK"] == "REFUTED" and
        claims_status["K8_REVIVAL"] == "REFUTED" and
        claims_status["F_MAX"] == "REFUTED" and
        claims_status["LAMBDA_PHI"] == "NOT_MEASURED" and
        exp_data["all_claims_refuted"] is True
    )

    # ---------------------------------------------------------
    # Test 2: Operational Lock Enforcement (Fail-Closed)
    # ---------------------------------------------------------
    operational_allowed = govern_data["operational_invariants"]["operational_allowed"]
    test2_pass = (operational_allowed is False)

    # ---------------------------------------------------------
    # Test 3: Active Physical Invariant Preservation
    # ---------------------------------------------------------
    coherence_floor = govern_data["operational_invariants"]["runtime_coherence_floor"]
    planck_mass_kg = govern_data["operational_invariants"]["universal_memory_invariant_kg"]
    test3_pass = (
        coherence_floor == 0.0920 and
        abs(planck_mass_kg - 2.176435e-8) < 1e-12
    )

    all_tests_passed = test1_pass and test2_pass and test3_pass

    scorecard = {
        "organism_id": "tau_phase_erratum_study",
        "evaluation_battery": {
            "test_1_claims_refutation_integrity": {
                "description": "Assert that theta_lock, K8_revival, and F_max are formally classified as REFUTED",
                "verdict": "PASS" if test1_pass else "FAIL",
                "claims_audited": ["THETA_LOCK", "K8_REVIVAL", "F_MAX", "LAMBDA_PHI"]
            },
            "test_2_operational_recovery_lock": {
                "description": "Assert that operational_allowed is strictly False (SYS-024 fail-closed gate)",
                "verdict": "PASS" if test2_pass else "FAIL",
                "operational_allowed": operational_allowed
            },
            "test_3_active_invariant_preservation": {
                "description": "Assert that genuine physical invariants (Gamma_floor = 0.0920) remain enforced",
                "verdict": "PASS" if test3_pass else "FAIL",
                "coherence_floor": coherence_floor,
                "planck_mass_kg": planck_mass_kg
            }
        },
        "all_governance_tests_passed": all_tests_passed,
        "organism_maturity_verdict": "ERRATUM_GOVERNANCE_INTEGRITY_PROVEN" if all_tests_passed else "GOVERNANCE_BREACH",
        "merkle_anchor": govern_data["merkle_root"]
    }

    return scorecard


if __name__ == "__main__":
    card = run_measurement_battery()
    out_file = os.path.join(os.path.dirname(__file__), "measurement_scorecard.json")
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(card, f, indent=2)

    print("================================================================================")
    print("      OSIRIS + DNA-LANG: TAU-PHASE ERRATUM MEASUREMENT SCORECARD")
    print("================================================================================")
    for k, v in card["evaluation_battery"].items():
        print(f"  {k:<38}: [{v['verdict']}]")
        print(f"    Details: {v['description']}")
    print("--------------------------------------------------------------------------------")
    print(f"Overall Governance Verdict: {card['organism_maturity_verdict']}")
    print(f"Merkle Anchor:             {card['merkle_anchor']}")
    print(f"Scorecard Artifact:        {out_file}")
    print("================================================================================")
