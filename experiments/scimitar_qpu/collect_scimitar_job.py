#!/usr/bin/env python3
"""Collect an existing IBM Quantum Runtime job and write count data + summary."""
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

OUTDIR = Path("scimitar_sse_results")

def main():
    if len(sys.argv) != 2:
        raise SystemExit("Usage: python collect_scimitar_job.py JOB_ID")
    job_id = sys.argv[1]
    token = os.environ.get("QISKIT_IBM_TOKEN")
    if not token:
        raise SystemExit("Missing QISKIT_IBM_TOKEN.")
    from qiskit_ibm_runtime import QiskitRuntimeService
    channel = os.environ.get("QISKIT_IBM_CHANNEL", "ibm_quantum_platform")
    instance = os.environ.get("QISKIT_IBM_INSTANCE")
    kw = {"channel": channel, "token": token}
    if instance:
        kw["instance"] = instance
    service = QiskitRuntimeService(**kw)
    job = service.job(job_id)
    result = job.result()
    counts = []
    for i, pub in enumerate(result):
        try:
            cts = pub.data.meas.get_counts()
        except Exception:
            cts = {}
        counts.append({"circuit_index": i, "counts": cts})
    payload = {
        "job_id": job_id,
        "backend": getattr(job, "backend", lambda: None)().name if callable(getattr(job, "backend", None)) else None,
        "status": str(job.status()),
        "collected_utc": datetime.now(timezone.utc).isoformat(),
        "counts": counts,
        "caveat": "Map circuit_index to manifest.json circuits in the same experiment directory."
    }
    OUTDIR.mkdir(parents=True, exist_ok=True)
    path = OUTDIR / f"job_{job_id}_counts.json"
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(json.dumps({"saved": str(path), "circuits": len(counts), "status": payload["status"]}, indent=2))

if __name__ == "__main__":
    main()
