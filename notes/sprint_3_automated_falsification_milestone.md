# Sprint 3 Milestone: Automated Adversarial Falsification Engine & Epistemic Quarantine

**Sprint Identifier:** `SPRINT-3-ADVERSARIAL-FALSIFICATION`  
**Governing Standard:** SYS-021, SYS-023, SYS-024, SYS-025  
**Grant Reference:** `GRANT-FALSIFY-001`  
**Author:** Devin Phillip Davis / Enki  
**Organization:** Agile Defense Systems LLC (CAGE: 9HUP5)  
**Date (UTC):** 2026-10-27T07:21:00Z  

---

## 1. Executive Summary

Sprint 3 delivers the **Automated Adversarial Falsification Engine** ([`AdversarialFalsificationEngine`](file:///root/repos/osiris-cli/osiris_cli/dnalang/falsification.py#L90-L280) in [`osiris_cli/dnalang/falsification.py`](file:///root/repos/osiris-cli/osiris_cli/dnalang/falsification.py)).

This engine enforces the **SYS-024 Claims Firewall & Epistemic Quarantine Invariant**. Autonomous genetic candidates and quantum control proposals claiming coherence improvement or computational advantage are prohibited from progressing to human authorization (`READY_FOR_HUMAN_AUTH`) until they survive an automated battery of 4 adversarial null-hypothesis controls. If any null control falsifies the advantage, the candidate is locked behind the claims firewall as `QUARANTINED_MODEL_PROPOSED`.

---

## 2. Adversarial Null-Hypothesis Battery

The engine tests candidate proposals against four distinct physical and statistical falsifiers:

1. **Sign-Flipped Phase Control (`SIGN_FLIPPED_PHASE_NULL`):**
   Inverts phase angles ($\theta \to -\theta$ and $R_z(\theta) \to R_z(-\theta)$). If the candidate's claimed advantage persists under sign reversal ($\Delta \le \epsilon$), the effect is diagnosed as an uncalibrated hardware asymmetry rather than genuine dynamical error cancellation.
2. **Pulse Timing / Gate Shuffle Control (`TIMING_SHUFFLE_CROSSTALK_NULL`):**
   Permutes the relative timing slots and offsets across qubits while preserving total idle duration. If the candidate fails to outperform the timing-shuffled sequence, the advantage is an idle drift artifact rather than bipartite crosstalk cancellation.
3. **Noiseless Unitary Sanity Check (`NOISELESS_UNITARY_SANITY_CHECK`):**
   Verifies that the evaluated metric is strictly well-defined, non-divergent, and physically bounded within $[0, 1]$ (strictly rejecting `NaN`, `\pm\infty`, and out-of-bounds metrics).
4. **Hardware Baseline Contrast (`HARDWARE_BASELINE_CONTRAST`):**
   Contrasts the candidate directly against the verified, append-only physical hardware baseline locked into [`provenance/osiris_operational_journal.jsonl`](file:///root/repos/osiris-cli/provenance/osiris_operational_journal.jsonl) from IBM Heron r2 (`ibm_marrakesh`). Enforces pre-registered advantage thresholds: $\Delta P(+) \ge 0.15$ over bare idle and $\Delta P(+) \ge 0.02$ over textbook simultaneous DD.

---

## 3. Cryptographic Falsification Receipt

Every evaluation produces an RFC 8785 canonical [`FalsificationReceipt`](file:///root/repos/osiris-cli/osiris_cli/dnalang/falsification.py#L42-L88):
- Cryptographically binds `candidate_id`, `candidate_digest`, `baseline_journal_hash`, `controls_executed`, `status`, and `quarantine_notice`.
- If any control fails: emits `status: QUARANTINED_MODEL_PROPOSED` and halts progression.
- If all controls pass: emits `status: READY_FOR_HUMAN_AUTH`, permitting human operator authorization per SYS-021.

---

## 4. Verification Evidence

All 6 test cases in [`tests/test_falsification_engine.py`](file:///root/repos/osiris-cli/tests/test_falsification_engine.py) pass synchronously:
- `test_adversarial_falsification_passes_valid_candidate` (PASS)
- `test_adversarial_falsification_quarantines_sign_flip_artifact` (PASS)
- `test_adversarial_falsification_quarantines_timing_shuffle_artifact` (PASS)
- `test_adversarial_falsification_quarantines_sub_hardware_baseline` (PASS)
- `test_adversarial_falsification_quarantines_nan_and_inf` (PASS)
- `test_falsification_receipt_canonical_digest_determinism` (PASS)

Full regression across Sprints 1, 2, and 3: **27 passed in 4.26s**.
