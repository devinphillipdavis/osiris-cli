# Scimitar-SSE QPU pilot

## What this tests
A small one-qubit, angle-swept control-sequence pilot. It compares a free-idle Ramsey-style baseline with an XY4-like phase-offset sequence near the manuscript's proposed 51.843° value. This is a *mapped control-sequence proxy*, not a direct test of toroidal electromagnetic geometry or inter-device quantum coherence.

## Security
The previously uploaded IBM API-key JSON should be treated as compromised. Revoke/rotate that key in IBM Quantum before running. Never commit the replacement key or paste it into source. Set it in the shell environment.

## Install
Use a clean Python virtual environment and a current Qiskit/IBM Runtime install:

```bash
python -m venv .venv
# Linux/macOS/WSL
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install qiskit qiskit-ibm-runtime
```

## Dry run
```bash
python scimitar_sse_qpu.py --dry-run
```

## Configure credentials safely
Linux/macOS/WSL:
```bash
read -s QISKIT_IBM_TOKEN
export QISKIT_IBM_TOKEN
# Optional if your account needs a specific instance:
export QISKIT_IBM_INSTANCE='YOUR_INSTANCE_CRN'
export QISKIT_IBM_CHANNEL='ibm_quantum_platform'
```

PowerShell:
```powershell
$env:QISKIT_IBM_TOKEN = Read-Host -AsSecureString | ConvertFrom-SecureString
```
The PowerShell example above is not directly compatible with the Python process because it produces an encrypted string; instead set the variable through your OS secret manager or use a secure terminal method that places the actual token only in the process environment. Do not save it in a script or shell history.

## Submit
First inspect the generated manifest/QASM. Then explicitly submit:
```bash
python scimitar_sse_qpu.py --submit --shots 2048
```
Optional explicit backend:
```bash
python scimitar_sse_qpu.py --submit --backend BACKEND_NAME --shots 2048
```

The script chooses the least-busy operational physical backend if no backend is specified. It submits asynchronously and prints the job ID. Check job status in IBM Quantum before collecting results. Then run `python collect_scimitar_job.py JOB_ID` to save counts.

## Evidence outputs
- `scimitar_sse_results/manifest.json`: configuration, circuit order, backend, and job ID.
- `scimitar_sse_results/qasm/`: portable circuit definitions from dry-run.
- `scimitar_sse_results/job_<JOB_ID>_counts.json`: raw counts after collection.

## Limitations / interpretation
1. The requested 51.843° is mapped to a software phase parameter. It is not a physically implemented toroidal field angle.
2. Circuit-level `RZ` operations may compile to virtual frame changes; this is not a calibrated analog-field experiment.
3. The current pilot is exploratory. It does not pre-register a confirmatory statistical test, characterize T1/T2, or equalize all pulse-duration effects. For a publishable result, inspect transpiled circuits, obtain backend calibration metadata, add randomized repetitions and matched-duration controls, and predefine the primary statistic before looking at results.
4. A lower survival probability is not necessarily lower coherence; analyze against the expected ideal circuit and readout calibration.
5. No QPU job has been submitted merely by generating these files. Submission occurs only when the script is run with `--submit`.
