# OSIRIS v4.5.4 — Release Notes (2026-10-11)

A major sovereignty, hardware governance, and quantum batching release: enforces the deterministic interactive REPL prompt invariant `osiris::}{> `, establishes dual-substrate dynamic hardware detection and temporal execution boundaries, removes hardcoded paths, incorporates the RQC S2 12-job multi-PUB batching harness with S2 Amendment 5 bundle verification, integrates the Willow QVM sampler, adds the `/welcome` command onboarding tour, and anchors newly minted Phase-Conjugate Recalibration Telemetry (`10.5281/zenodo.23213288`).

Verified on the release tree: the full test suite on Python 3.12: 871 passed, 3 skipped (100% pass rate).

## 1. Sovereign REPL & Dual-Substrate Hardware Mesh (`osiris_cli/osiris_repl.py`, `run_sovereign_repl.py`)

- **Strict Prompt Invariant**: Enforces the deterministic prompt string `osiris::}{> ` across interactive sessions, satisfying the OSIRIS Unified REPL Execution Contract.
- **Dual-Substrate Architecture Awareness**: Introduces `run_sovereign_repl.py`, an architecture-aware execution harness that detects whether the host is running on **Node Alpha** (`aarch64` / `arm64`, e.g. Pixel 10 Pro Fold / Termux) or **Node Beta** (`x86_64` / `AMD64`, e.g. Intel Core Ultra Workstation / WSL).
- **Temporal & Thermal Horizon Boundaries**: Enforces strict hardware-governed timeout horizons:
  - **Node Alpha (Mobile Edge)**: 300.0s temporal lock, NEON SIMD, unbuffered UTF-8 streaming (`PYTHONUNBUFFERED=1`, `PYTHONIOENCODING=utf-8`).
  - **Node Beta (Compute Workstation)**: 1800.0s horizon, AVX2/AVX-VNNI acceleration, multi-threaded batch execution.
- **Dynamic Path Resolution**: Purged legacy hardcoded `/root/osiris-cli` and `~/fold/` paths; paths are now resolved dynamically via filesystem probes and repository root detection.

## 2. RQC S2 Multi-PUB Batching & Willow QVM Support (`rqc/`, `docs/rqc/`)

- **12-Job Multi-PUB Batching**: Implements the batched execution harness for RQC S2 (`rqc/batch.py`, `docs/rqc/S2/s2_run_batched.py`). Within each block, 80 participants (seed × arm) run in lockstep, collapsing barrier executions into 12 multi-PUB jobs of 80 PUBs each under registered IBM Quantum Heron hardware rules.
- **S2 Amendment 5 Cryptographic Bundle**: Implements cryptographic bundle manifest verification (`rqc/control.py`, `AMENDMENT_5_MANIFEST.json`) registered under DOI `10.5281/zenodo.23256344`. Ensures code and document SHA-256 integrity before authorizing hardware execution.
- **Willow QVM Sampler & Cirq Interop**: Adds Google Willow QVM sampler support, Cirq circuit conversion, and collision-adjusted XEB analysis (`rqc/circuits.py`, `rqc/samplers.py`).
- **Honest Execution Safeguards**: Restricts XEB calculations to verifiable shot distributions, eliminating fabricated estimations from legacy execution paths. Enforces strict QPU budget stops (`BudgetExhausted`).
- **Runtime Fake Provider Compatibility**: Adds graceful fallback for IBM fake provider backends (e.g. `FakeKingston` falling back to `FakeMarrakesh` when running on modern runtimes where Kingston is not exported).

## 3. Onboarding & Governance Tooling (`osiris_cli/welcome.py`, claims register)

- **Interactive `/welcome` Tour**: Added an onboarding walkthrough that introduces console commands, configuration profiles, and governance concepts by suggesting commands without running any without user intent.
- **Claims Register Updates**: Tightened tau-phase matching criteria, clarified artifact provenance chains, and marked refuted premises (`TESSERACT_DECODER: REFUTED`, `RQC_XEB_PIPELINE: NOT_MEASURED`).
- **Garbage Collection Isolation**: Drains pending reference cycle queues before evaluating zero-reference-cycle invariants in `test_sovereign_transformer.py`, ensuring C-extension noise from quantum libraries does not interfere with transformer autograd tests.

## 4. Evidence & Citable Identifiers

- **Predecessor Software Release (v4.5.3)**: [10.5281/zenodo.23257201](https://doi.org/10.5281/zenodo.23257201)
- **Phase-Conjugate Recalibration Telemetry Ledger (PCRB)**: [10.5281/zenodo.23213288](https://doi.org/10.5281/zenodo.23213288) (SHA-256: `2b6a98b5a184f24f1e71e5c8698845ed6cc9ae5631d1ea9446411b7a32879e8f`)
- **Parent Experiment (Scimitar-SSE)**: [10.5281/zenodo.19505923](https://doi.org/10.5281/zenodo.19505923)
- **RQC S2 Preregistration**: [10.5281/zenodo.23241223](https://doi.org/10.5281/zenodo.23241223)
- **RQC S2 Amendment 5 Bundle**: [10.5281/zenodo.23256344](https://doi.org/10.5281/zenodo.23256344)
