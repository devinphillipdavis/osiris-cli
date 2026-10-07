# OSIRIS v4.3.2 — release notes (2026-10-07)

A verification and packaging release, driven by the independent acceptance record in
`osiris-governance/docs/15_ACCEPTANCE_RECORD_VERIFIED_LOOP_2026-10-07.md` (verdict: HOLD).

Not yet installed into any running environment. The NCLM-1 v1b window closes
2026-10-08 23:59:59 UTC; install afterwards (see "Installing" below).

## Fixed

- **Benchmark tasks ship with the package.** `bench_tasks/` installs beside `osiris_bench.py`,
  so an installed benchmark finds its 9 tasks (v4.3.1 raised FileNotFoundError). No
  `__init__.py` was added, so `suite_sha256` is unchanged (`09037df6…`).
- **Benchmark results go to `~/.osiris/bench`**, where the console reads them. An installed
  copy used to write under the virtualenv's `lib/` directory.
- **A verifier pass needs a receipt.** `verify_loop.verified_first_passing` accepts a pass only
  with a receipt whose `candidate_digest` names the candidate; a missing or empty receipt fails
  with `RECEIPT_MISSING`.
- **Hypothesis outcomes must come from the right kind of experiment.** A hypothesis declares
  what decides it (`/hypothesis hyp-N tests run|bench|trial-bench|evo`); `/outcome` refuses an
  undeclared hypothesis and evidence of another kind (`HYPOTHESIS_EXPERIMENT_MISMATCH`). The
  hints after an organism run or a trial only suggest hypotheses of the matching kind. This is
  the error behind hyp-1's withdrawn "refuted" outcome. The check compares experiment kinds; it
  cannot tell whether a same-kind run measured the hypothesis's metric.
- **NCLM-1 progress report** (`nclm_analysis.py`): rows labelled by ledger index with real
  timestamps, compared against the frozen corpus unigram (5.0805), and no home-made gate
  verdict. The verdict belongs to `NCLM-1_v1_evaluate.py` alone (Amendment 4).

## New

- `verify_loop.verified_first_passing` and `CandidateArtifact`: a generate-and-verify loop
  with a typed candidate, a required confinement guard (from `osiris-governance`), fail-closed
  auditing and receipt binding. **No console command or benchmark uses it yet**: `/sprint
  execute` keeps its own gates (assigned write path, protected-file check, sandbox, `/apply`),
  and the benchmark keeps verifying with the candidate's own test because that loop is what it
  measures against hidden tests.
- NCLM-1 manual collection workflow: `NCLM1_MANUAL_WORKFLOW.md`, `start_nclm_workflow.sh`,
  `nclm_analysis.py`.

## Comparability

`runner_sha256` covers `verify_loop.py`, which changed. Benchmark rounds from 4.3.2 are not
comparable with earlier rounds; the benchmark records both hashes per run, so this is visible
in the ledger.

## Installing

From a checkout, after the NCLM-1 window: `pip install --upgrade /path/to/osiris-cli`. A wheel
built from this tree was installed into a scratch target and loaded all 9 benchmark tasks with
the unchanged suite hash, the hardened loop and the hypothesis check.
