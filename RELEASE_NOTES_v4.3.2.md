# OSIRIS v4.3.2 — release notes (2026-10-07)

A verification, packaging, and stability release addressing REPL dispatch crashes, audit findings from the independent acceptance record in `osiris-governance/docs/15_ACCEPTANCE_RECORD_VERIFIED_LOOP_2026-10-07.md`, and packaging distribution.

Verified in a `git archive` tree with core dependencies only, the home directory hidden and no reachable Ollama: 593 passed, 1 skipped on Python 3.11 and 3.12. A wheel built from the tree and installed into a fresh environment imports the console and loads all 9 benchmark tasks.

## Fixed

- **Menu letters B, C, F (and `/runs`, `/apply`, `/discard`, `/sprint`, `/nclm`, `/facts`) crashed the REPL.** The REPL kept its own copy of the console's command table and it had drifted: nine handlers it called were missing or took different arguments, and `/gaps` opened a new draft instead of listing drafts. The REPL now routes through the console's `run_command()`; `tests/test_repl_dispatch.py` checks that every console call in the REPL exists and binds.
- **A failing command ended the session.** A command that raises now reports which command failed, keeps the traceback in `~/.osiris/logs/repl_errors.log`, and returns to the prompt.
- **Benchmark tasks ship with the package.** `bench_tasks/` installs beside `osiris_bench.py`, so an installed benchmark finds its 9 tasks (v4.3.1 raised `FileNotFoundError`). No `__init__.py` was added, so `suite_sha256` is unchanged (`09037df6…`).
- **Benchmark results go to `~/.osiris/bench`**, where the console reads them. An installed copy used to write under the virtualenv's `lib/` directory.
- **A verifier pass needs a receipt.** `verify_loop.verified_first_passing` accepts a pass only with a receipt whose `candidate_digest` names the candidate; a missing or empty receipt fails with `RECEIPT_MISSING`.
- **Hypothesis outcomes must come from the right kind of experiment.** A hypothesis declares what decides it (`/hypothesis hyp-N tests run|bench|trial-bench|evo`); `/outcome` refuses an undeclared hypothesis and evidence of another kind (`HYPOTHESIS_EXPERIMENT_MISMATCH`). The hints after an organism run or a trial only suggest hypotheses of the matching kind.
- **`/status` called the historical CRSM constants "invariants"** (and gave Λ_Φ a unit of kg). It now shows θ_lock, Λ_Φ and F_max as historical parameters with their claims-register verdicts (REFUTED, NOT_MEASURED).
- **NCLM-1 progress report** (`nclm_analysis.py`): rows labelled by ledger index with real timestamps, compared against the frozen corpus unigram (5.0805), and no home-made gate verdict. The verdict belongs to `NCLM-1_v1_evaluate.py` alone (Amendment 4).

## New

- `verify_loop.verified_first_passing` and `CandidateArtifact`: a generate-and-verify loop with a typed candidate, a required confinement guard (from `osiris-governance`), fail-closed auditing and receipt binding. **No console command or benchmark uses it yet**: `/sprint execute` keeps its own gates (assigned write path, protected-file check, sandbox, `/apply`), and the benchmark keeps verifying with the candidate's own test because that loop is what it measures against hidden tests.
- NCLM-1 manual collection workflow: `NCLM1_MANUAL_WORKFLOW.md`, `start_nclm_workflow.sh`, `nclm_analysis.py`.

## Comparability

`runner_sha256` covers `verify_loop.py`, which changed. Benchmark rounds from 4.3.2 are not comparable with earlier rounds; the benchmark records both hashes per run, so this is visible in the ledger.

## Tests and CI

- Tests point `OLLAMA_HOST` at an address nothing listens on (`OSIRIS_TEST_LIVE_OLLAMA=1` opts in): a busy local Ollama made `tests/test_integration.py` hang. `test_architecture` uses the pinned dnalang-core ledger when dnalang-core is absent.
- The CI workflow builds the wheel, installs it in a clean environment and imports the console from it. `scripts/ci_local.sh` runs the suite with the home directory hidden plus the same wheel check.

## Upgrading & Installing

- `/update` installs from GitHub `main`; from this release on it delivers the fixed console.
- Editable install: `git pull && pip install -e .` in your checkout.
- Clean wheel install: `pip install --upgrade /path/to/osiris-cli`.

## Known issues

Unchanged from v4.3.1: legacy code outside the console and `osiris_cli` still contains old absolute paths; the CI lint selection reports pre-existing findings; Python 3.9 and 3.10 were not tested locally.
