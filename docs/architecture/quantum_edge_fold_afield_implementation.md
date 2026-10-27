# OSIRIS Quantum-Edge + A-Field Implementation Contract

**Status:** Implementation proposal; not a hardware validation result  
**Scope:** OSIRIS CLI, DNA-Lang research organism, OSIRIS Android foldable IME, Node Alpha/Node Beta bridge  
**Authority boundary:** Models propose; deterministic code validates; measurements create evidence; SYS-021 authorization controls protected actions; humans promote.

## Delivery boundary

This change adds a local research-gate evaluator and tests. It does not execute experiments, authorize deployment, access a secure element, send telemetry, change grant status, or promote a hypothesis. It is not a replacement for the canonical SYS-021 verifier.

The A-Field organism currently reports GATE-01 as passed and GATE-02 through GATE-04 as blocked. The outgoing/returning field-pair interpretation remains a hypothesis. Algebraic identities are definitional transformations, not independent empirical confirmations.

## Research-gate contract

The evaluator accepts a genome and evidence receipt as data. It rejects malformed claim IDs, unknown epistemic standing, duplicate gate IDs, missing gates, non-PASS required gates, receipt/genome identity mismatch, and absent SYS-023 evidence attestation. Any such condition is fail-closed.

PASS means only that supplied metadata meets this local contract. It does not independently validate the physics, recompute the evidence digest, prove receipt authenticity, or grant execution authority. A separate verifier must authenticate payload-bound authorization and provenance.

## Pixel Fold / Quantum-Edge readiness contract

Pixel 11 Pro Fold is a proposed target, not a verified device profile in this repository. Hardware, silicon, secure-element capabilities, and OEM APIs must be confirmed against official device documentation and physical tests before claims are promoted.

1. **Device identity:** record exact model, Android/API level, build fingerprint, and posture capabilities from the connected test device. Do not infer Pixel 11 specifications from earlier Pixel devices.
2. **IME safety:** verify hinge/posture-aware split layout, focus continuity, accessibility, keyboard privacy, and no background clipboard collection.
3. **Intent routing:** only explicit user-selected text/topic/URL or direct keyboard actions may enter the router; each action carries a typed request, declared capability, and audit event.
4. **Local-first execution:** local routes must work with network unavailable; tests must prove sensitive payloads are not emitted to network transports.
5. **Zero-egress evidence:** record scope, duration, monitored interfaces, allowed endpoints, observed socket/packet evidence, tool versions, and digest. No egress must not be claimed from a missing log.
6. **Cryptography:** use documented Android Keystore/StrongBox APIs where available. Do not assume Titan low-level applet access or ML-DSA hardware support without OEM documentation and device-level proof.
7. **QLDPC decoder:** benchmark quantized neural and sparse lookup candidates against the same corpus, correctness oracle, memory cap, latency distribution, and energy/thermal budget.
8. **Manufacturing/RF:** 3MF geometry and material selection are proposals only. ESD conductivity and RF shielding require material data and physical measurements.

Each gate state is NOT_MEASURED, PASS, FAIL, or BLOCKED. NOT_MEASURED is never PASS. Automated gate results do not grant permission to install, sign, deploy, or promote.

## Cross-node transfer

Cross-node transfer is a data operation, not authorization. Alpha/Beta messages must include schema version, source/destination node identifiers, payload digest, replay protection, and data classification. A valid digest does not prove sender identity or confer execution rights. Remote commands remain disabled unless a separate SYS-021 grant is verified at the receiving node.

## Required verification before release

- Run focused unit tests in the supported repository environment.
- Run existing regression tests and static analysis.
- Confirm the actual SYS-021 verifier enforcement path; do not infer completeness from proposal text.
- Recompute digest and Merkle calculations from source bytes in a clean checkout.
- For Android, build and test the IME on a real supported foldable, including posture changes, offline mode, privacy, and accessibility.
- For zero-egress, collect packet/socket evidence and independently review the capture.
- For secure-element, RF, or QLDPC claims, require device or benchmark evidence and retain raw measurements.

Until checks are independently recorded, this work remains an unmerged branch and all hardware gates remain NOT_MEASURED or BLOCKED. No deployment or scientific claim promotion is authorized by this document.
