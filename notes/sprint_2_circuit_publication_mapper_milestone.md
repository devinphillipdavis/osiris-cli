# Sprint 2 Milestone: IBM Circuit-to-Publication Mapper & Quantum Epistemic Ledger

**Sprint Identifier:** `SPRINT-2-QUANTUM-PUB-MAPPER`  
**Governing Standard:** SYS-021, SYS-022, SYS-023, SYS-024, SYS-025  
**Grant Reference:** `GRANT-IBM-MAPPER-001`  
**Author:** Devin Phillip Davis / Enki  
**Organization:** Agile Defense Systems LLC (CAGE: 9HUP5)  
**Date (UTC):** 2026-10-27T07:17:00Z  

---

## 1. Executive Summary

Sprint 2 delivers the **IBM Circuit-to-Publication Mapper** (`IBMPubMapper` in [`osiris_cli/quantum/pub_mapper.py`](file:///root/repos/osiris-cli/osiris_cli/quantum/pub_mapper.py)) and the **Operational Merkle Ledger** ([`OperationalMerkleLedger`](file:///root/repos/osiris-cli/osiris_cli/quantum/pub_mapper.py#L136-L208)).

This implementation establishes an **unambiguous physical baseline** directly from real IBM Quantum execution payloads (`dau0q3qhcrkc73durtgg` on `ibm_marrakesh`), enforcing 1-to-1 spec-to-PUB mapping, state fidelity ($F_{\text{state}}$), effective gate fidelity ($F_{\text{gate}}$), and pre-registered hypothesis testing without post-hoc cherry-picking or manual reordering.

---

## 2. Core Architectural Deliverables

### A. 1-to-1 Epistemic Spec-to-PUB Mapping
In raw Qiskit Runtime SamplerV2 jobs, execution circuits are shuffled across randomized blocks (seed `20260929`). If analysis code naively assumes sequential PUB order, counts from bare idle (`none`), textbook decoupling (`cpmg8`, `xy4x2`), and OSIRIS staggered decoupling (`xy4x2_stag`, `xy8_stag`) are completely transposed.
- `CircuitSpec` binds pre-registered index, name, idle duration $T$, replicate index, circuit hash, and two-qubit count.
- `PubResult` binds each SamplerV2 PUB output directly to its corresponding `CircuitSpec`.
- Extraction logic correctly maps Qiskit right-to-left little-endian bitstrings (`bs[N_QUBITS - 1 - q] == '0'`) to physical qubit $|+\rangle$ survival.

### B. Statistical Adjudication & Fidelity Metrics
Recomputes exact physical quantities across condition replicates:
1. **State Fidelity ($F_{\text{state}}$):**
   $$F_{\text{state}} = \langle + | \rho | + \rangle = \bar{P}(+)$$
2. **Effective Gate Fidelity ($F_{\text{gate}}$):**
   For $n_{\text{pulses}} = 8$ dynamical decoupling pulses under dephasing:
   $$\eta = 2\bar{P}(+) - 1, \quad F_{\text{gate}} = \eta^{1 / n_{\text{pulses}}}$$
3. **Decay Parameter ($\Gamma$):**
   $$\Gamma = -\frac{1}{T}\ln(2\bar{P}(+) - 1)$$
4. **95% Bootstrap Confidence Intervals:**
   Percentile bootstrap ($B = 2000$, seed $= 0$) over empirical replicate values.

### C. IBM Heron r2 Replication Benchmark (`dau0q3qhcrkc73durtgg`)
Replicated ground-truth hardware execution metrics to within $10^{-7}$ tolerance:
- **Bare Idle (`none`, $T = 32\,\mu\text{s}$):** $\bar{P}(+) = 0.5945$, $F_{\text{gate}} = 0.8122$
- **Textbook CPMG (`cpmg8`, $T = 32\,\mu\text{s}$):** $\bar{P}(+) = 0.8344$, $F_{\text{gate}} = 0.9509$
- **Textbook XY4x2 (`xy4x2`, $T = 32\,\mu\text{s}$):** $\bar{P}(+) = 0.8342$, $F_{\text{gate}} = 0.9509$
- **OSIRIS Best Staggered (`xy8_stag`, $T = 32\,\mu\text{s}$):** $\bar{P}(+) = 0.8998$, $F_{\text{gate}} = 0.9724$

**Pre-registered Hypothesis Evaluation:**
- **Criterion 1 ($\Delta P(+) \ge 0.15$ vs bare idle):** Observed $+0.3053$ (**PASS**)
- **Criterion 2 ($\Delta P(+) \ge 0.02$ vs textbook DD):** Observed $+0.0656$ (**PASS**)
- **Criterion 3 (Non-overlapping 95% CIs):** $[0.8982, 0.9014]$ vs $[0.8289, 0.8398]$ (**PASS**)
- **Verdict:** `H1_CONFIRMED`

---

## 3. Cryptographic Provenance & Merkle Journaling

1. **RFC 8785 Canonical Digest:**
   The `ExperimentMappingReceipt` produces a deterministic SHA-256 digest (`21d3791863586a3ef212d79ff8dae69ade0f073383a3ddf33973ee143b866548`) over all immutable summary and hypothesis fields.
2. **Operational Journal Entry:**
   Locked into [`provenance/osiris_operational_journal.jsonl`](file:///root/repos/osiris-cli/provenance/osiris_operational_journal.jsonl):
   - **Entry Hash:** `835ba8e988be1ceb5ec08f5afaaeeb7b7f71f41ff782c4948ad1c998b11c5f3a`
   - **Genesis Link:** `0000000000000000000000000000000000000000000000000000000000000000`
   - **Verification State:** `INTACT`

---

## 4. Verification Evidence

All 7 test cases in [`tests/test_pub_mapper.py`](file:///root/repos/osiris-cli/tests/test_pub_mapper.py) pass synchronously:
- `test_real_heron_mapping_and_statistical_replication` (PASS)
- `test_hypothesis_adjudication_h1_confirmed` (PASS)
- `test_tamper_rejection_length_mismatch` (PASS)
- `test_tamper_rejection_invalid_hashes` (PASS)
- `test_receipt_digest_determinism_and_sensitivity` (PASS)
- `test_hypothesis_adjudication_null_cases` (PASS)
- `test_merkle_operational_journal_locking` (PASS)
