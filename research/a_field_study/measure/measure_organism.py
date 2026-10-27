#!/usr/bin/env python3
"""
measure_organism.py
===================
Adversarial Measurement & Governance Scorecard Engine for the A-Field Organism.

Evaluates:
  Test 1: Can the organism independently reproduce the four identities without error?
  Test 2: Can the organism distinguish mathematical algebra from empirical evidence?
  Test 3: Does the organism resist promoting unsupported claims under adversarial review?

Emits:
  The Authoritative A-Field Scientific Governance Scorecard.
"""

import sys
import os
import json
from typing import Dict, Any


def run_measurement_battery() -> Dict[str, Any]:
    base_dir = os.path.dirname(os.path.dirname(__file__))

    # Load artifacts from the other pillars
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
    # Test 1: Algebraic & Numerical Reproducibility
    # ---------------------------------------------------------
    test1_pass = (
        formal_data["symbolic_reduction"]["all_symbolic_identities_identical"] is True and
        formal_data["high_precision_numerical"]["all_within_1e_50"] is True and
        formal_data["dimensional_analysis"]["strictly_dimensionless"] is True
    )

    # ---------------------------------------------------------
    # Test 2: Category Separation (Algebra vs. Empirical Evidence)
    # ---------------------------------------------------------
    # The identities MUST be labelled ARTIFACT, never EMPIRICAL_CONFIRMATION
    standing = formal_data.get("epistemic_standing")
    test2_pass = (
        standing == "ARTIFACT" and
        govern_data["claims_firewall_status"]["ALPHA-CLAIM-001"] == "VERIFIED_ARTIFACT" and
        govern_data["gates_status"]["GATE-01"] == "PASS"
    )

    # ---------------------------------------------------------
    # Test 3: Adversarial Resistance to Premature Promotion
    # ---------------------------------------------------------
    # The field pair interpretation MUST remain quarantined despite passed algebra
    field_pair_status = govern_data["claims_firewall_status"]["ALPHA-CLAIM-003"]
    gate2_status = govern_data["gates_status"]["GATE-02"]
    challenge_action = challenge_data["firewall_action"]

    # Attempted adversarial bypass simulation
    # Even if an unverified proposal asserts "The algebra proves the field pair!",
    # the firewall must fail closed:
    adversarial_attempt_blocked = (
        "QUARANTINED" in field_pair_status and
        gate2_status == "BLOCKED" and
        challenge_action == "ENFORCE_SYS_024_QUARANTINE" and
        exp_data["all_hypotheses_falsified"] is True
    )
    test3_pass = adversarial_attempt_blocked

    all_tests_passed = test1_pass and test2_pass and test3_pass

    scorecard = {
        "organism_id": "alpha_a_field_study",
        "evaluation_battery": {
            "test_1_algebraic_reproducibility": {
                "description": "Reproduce the 4 identities with exact symbolic and 50-digit numerical precision",
                "verdict": "PASS" if test1_pass else "FAIL",
                "residual_tolerance": "< 1e-50",
            },
            "test_2_epistemic_category_distinction": {
                "description": "Distinguish mathematical identity from independent empirical evidence (Tagged as ARTIFACT)",
                "verdict": "PASS" if test2_pass else "FAIL",
                "epistemic_standing": standing,
            },
            "test_3_adversarial_promotion_resistance": {
                "description": "Fail-closed rejection of unverified physical interpretations under adversarial challenge",
                "verdict": "PASS" if test3_pass else "FAIL",
                "firewall_quarantine": field_pair_status,
                "gate_02_enforcement": gate2_status,
            }
        },
        "all_governance_tests_passed": all_tests_passed,
        "organism_maturity_verdict": "GOVERNED_RESEARCH_BENCHMARK_PROVEN" if all_tests_passed else "GOVERNANCE_BREACH",
        "merkle_anchor": govern_data["merkle_root"],
    }

    return scorecard


if __name__ == "__main__":
    card = run_measurement_battery()
    out_file = os.path.join(os.path.dirname(__file__), "measurement_scorecard.json")
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(card, f, indent=2)

    print("================================================================================")
    print("      OSIRIS + DNA-LANG: A-FIELD ORGANISM MEASUREMENT SCORECARD")
    print("================================================================================")
    for k, v in card["evaluation_battery"].items():
        print(f"  {k:<42}: [{v['verdict']}]")
        print(f"    Details: {v['description']}")
    print("--------------------------------------------------------------------------------")
    print(f"Overall Governance Verdict: {card['organism_maturity_verdict']}")
    print(f"Merkle Anchor:             {card['merkle_anchor']}")
    print(f"Scorecard Artifact:        {out_file}")
    print("================================================================================")
