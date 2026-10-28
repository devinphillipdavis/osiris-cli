# OSIRIS

[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.23063462.svg)](https://doi.org/10.5281/zenodo.23063462)

OSIRIS is a local-first research console for testing whether a small language model can learn from conversation and improve under a conservative, audit-friendly governance loop. The project combines a local language-model workflow, a held-out gate for model behavior, provenance-focused ledger mechanics, and optional tooling for quantum/physics experimentation.

This repository is primarily Python (about 96.6% of the codebase), with supporting TeX, Shell, OpenQASM, and a small amount of C/Cython.

Author: Devin Phillip Davis (Agile Defense Systems LLC)
License: OSIRIS Source-Available Dual License v1.0 (see `LICENSE`)

## What OSIRIS is

OSIRIS is designed around a simple operational idea:

- a local model can be trained on conversations and documents
- the model may answer in its own voice only after it clears a held-out gate
- deterministic code decides, measures, and records what happened
- evidence is retained in a provenance-conscious workflow instead of relying on narrative claims alone

In practice, the project includes:

- a console and REPL (`osiris_cli/osiris_repl.py`)
- a local-first training and learning pipeline
- a governance layer that distinguishes authored claims from measured evidence
- quantum and hardware-analysis tooling
- a research bundle covering experiments, evaluation, and reproducible artifacts

## Repository status

Current package version: 4.5.4

The project is intentionally research-oriented rather than a conventional, consumer-facing CLI. Many modules are experimental, academic, or specific to a local research workflow. The repository documents a wide range of activities spanning:

- local language-model training and evaluation
- execution provenance and ledger validation
- quantum benchmarks and hardware test frameworks
- simulation and analysis pipelines
- experiments and publication artifacts

## Install

The project is packaged with setuptools and exposes a console command:

```bash
python -m pip install -e .
```

Optional feature sets are available:

```bash
python -m pip install -e '.[tui]'
python -m pip install -e '.[quantum]'
python -m pip install -e '.[plot]'
python -m pip install -e '.[forge]'
python -m pip install -e '.[retrieval]'
```

Run the console:

```bash
osiris
```

Or invoke the package directly:

```bash
python -m osiris_cli
```

## High-level architecture

The repository has a few major layers:

### 1. Console and orchestration

The main runtime lives in `osiris_cli/` and includes modules for:

- REPL behavior and command orchestration
- knowledge access and retrieval metadata
- living system state and recordkeeping
- provider/gateway integrations
- training and learning loops

The console entry point is declared in `pyproject.toml`:

```toml
[project.scripts]
osiris = "osiris_cli.osiris_repl:main"
```

### 2. Language-model and learning pipeline

The project includes a local, continuously learning model stack and infrastructure for gating model voice or output. The design emphasizes local execution, structured memory, and governance over unverified claims.

### 3. Provenance and evidence infrastructure

The repo contains a significant amount of code and documentation about write-ahead ledgers, hash chaining, and measured execution logs. This is a key design principle: evidence is captured before and after execution, and recorded with enough structure to support later audit.

### 4. Quantum and hardware research tooling

In addition to the CLI, OSIRIS includes protocols and tooling for:

- IBM QPU job analysis
- benchmark generation and reporting
- dynamical-decoupling studies
- anomaly detection and research notebooks/scripts
- quantum-discovery project scaffolding

## Repository layout

A representative view of the project structure:

- `README.md` — project overview and entry point
- `pyproject.toml` — packaging metadata and optional dependency groups
- `osiris_cli/` — primary console and runtime modules
- `tests/` — repository test suite
- `quantum_discovery/` — research framework for discovery-oriented analysis
- `experiments/` — execution and experiment folders
- `bench_tasks/` — benchmark task definitions
- `docs/` and top-level research markdown files — design notes, evidence, audit docs, and operational summaries

Notable files:

- `LICENSE`
- `pyproject.toml`
- `osiris_cli/osiris_repl.py`
- `osiris_cli/knowledge.py`
- `quantum_discovery/README.md`
- `experiments/`

## Quick start examples

### Start the CLI

```bash
osiris
```

### Install with TUI support

```bash
python -m pip install -e '.[tui]'
```

### Install for quantum research workflows

```bash
python -m pip install -e '.[quantum,tui,plot]'
```

## Research and evidence posture

The repo makes an explicit distinction between:

- local-first model development
- empirical evidence collection
- provenance and auditability
- research exploration versus production readiness

The codebase and docs stress measured behavior, reproducibility, and recorded evidence. This is stronger than a generic model wrapper; it is oriented around evaluating whether the system learns under controlled conditions and whether the observations are auditable.

## Tests

The repository includes a Python test suite under `tests/` and is configured with pytest in `pyproject.toml`.

Typical usage:

```bash
pytest -o cache_dir=/tmp/osiris_pytest_cache tests/
```

## Key design principles

- local-first execution
- explicit governance of model voice and output
- audit-friendly record keeping
- measured evaluation instead of narrative-only claims
- experimentation that can coexist with a production CLI shell

## Notable project themes

The repo repeatedly touches these themes:

- continual learning from conversation and documents
- held-out performance gates
- local-only or local-first model workflows
- quantum benchmarking and experiment provenance
- research artifacts and publication-ready documentation

## License and provenance

This repository is source-available under the OSIRIS Dual License v1.0. The project also includes a research record and provenance-oriented documentation intended to support evidence review and scientific traceability.

## Summary

OSIRIS is best understood as a research console and experiment harness for a governed local language model, not simply a conventional command-line app. Its value comes from bringing together:

- local model operation
- training and learning loops
- governance and evaluation gates
- provenance-aware records
- quantum and hardware analysis tooling

That combination makes it a useful project for reproducible, evidence-anchored experimentation in AI and quantum-adjacent research.

## Repository composition

The GitHub repository composition is roughly:

- Python: 96.6%
- TeX: 1.2%
- Shell: 0.9%
- OpenQASM: 0.7%
- Jupyter Notebook: 0.3%
- Cython: 0.2%
- C: 0.1%

## Related documentation

A few useful starting points in this repo include:

- `README.md`
- `pyproject.toml`
- `quantum_discovery/README.md`
- `osiris_cli/knowledge.py`
- `osiris_cli/osiris_repl.py`
- `LICENSE`

If you want a single high-signal way to enter the project, start with the console entry point and then move into the research documents and experimental folders.
