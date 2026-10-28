#!/usr/bin/env python3
"""
Scimitar-SSE QPU pilot: angle-swept, coherence-sensitive control experiment.

This is a *mapped control-sequence pilot*, not a direct test of toroidal fields
or device-independent quantum coherence. It submits to IBM Quantum only when
run explicitly with --submit and valid credentials in environment variables.

Required environment:
  QISKIT_IBM_TOKEN       IBM Quantum API key (rotated if previously exposed)
Optional:
  QISKIT_IBM_INSTANCE    IBM Quantum instance/CRN
  QISKIT_IBM_CHANNEL     defaults to ibm_quantum_platform

Artifacts are written under scimitar_sse_results/.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import platform
import sys
from datetime import datetime, timezone
from pathlib import Path

LOCK_DEG = 51.843
ANGLE_OFFSETS_DEG = [-20.0, -10.0, 0.0, 10.0, 20.0]
DEFAULT_DELAYS_NS = [0, 500, 1000, 2000, 4000]
DEFAULT_SHOTS = 2048
OUTDIR = Path("scimitar_sse_results")


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def make_circuit(angle_deg: float, delay_ns: int, arm: str, name: str):
    """Create one-qubit Ramsey-survival circuit.

    arm='free': free idle between preparation/readout rotations.
    arm='xy4': four nominal pi pulses with a phase-offset control parameter.
    The angle is a *software control-phase surrogate*, not a toroidal field angle.
    """
    from qiskit import QuantumCircuit, QuantumRegister, ClassicalRegister
    from qiskit.circuit.library import HGate

    q = QuantumRegister(1, "q")
    c = ClassicalRegister(1, "meas")
    qc = QuantumCircuit(q, c, name=name)
    qc.h(q[0])  # |+>, Ramsey-like preparation

    if arm == "free":
        qc.delay(delay_ns, q[0], unit="ns")
    elif arm == "xy4":
        # Split the requested idle interval into four free-evolution segments.
        # Gate durations add to wall-clock duration; record this as a limitation.
        seg = delay_ns // 4
        rem = delay_ns - 3 * seg
        phase = math.radians(angle_deg)
        xy4_phases = [phase, phase + math.pi / 2, phase, phase + math.pi / 2]
        for idx, pulse_phase in enumerate(xy4_phases):
            this_delay = rem if idx == 3 else seg
            if this_delay:
                qc.delay(this_delay, q[0], unit="ns")
            # XY4-like pi rotations in the XY plane, globally phase-offset,
            # expressed as RZ(phi) RX(pi) RZ(-phi). This is a test control
            # sequence, not an assertion that IBM hardware implements a
            # toroidal field. Verify the transpiled sequence before interpreting.
            qc.rz(pulse_phase, q[0])
            qc.rx(math.pi, q[0])
            qc.rz(-pulse_phase, q[0])
    else:
        raise ValueError(f"Unknown arm: {arm}")

    qc.h(q[0])  # map X-basis coherence to computational-basis population
    qc.measure(q[0], c[0])
    return qc


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--submit", action="store_true",
                        help="Actually submit jobs to IBM Quantum hardware.")
    parser.add_argument("--backend", default="",
                        help="Optional explicit backend name; default is least-busy operational QPU.")
    parser.add_argument("--shots", type=int, default=DEFAULT_SHOTS)
    parser.add_argument("--delays-ns", default=",".join(map(str, DEFAULT_DELAYS_NS)))
    parser.add_argument("--dry-run", action="store_true",
                        help="Build and validate circuits locally without connecting or submitting.")
    args = parser.parse_args()

    delays = [int(x.strip()) for x in args.delays_ns.split(",") if x.strip()]
    if not delays or any(d < 0 for d in delays):
        raise SystemExit("Delays must be a comma-separated list of nonnegative nanoseconds.")
    if args.shots < 1:
        raise SystemExit("--shots must be positive.")

    angles = [LOCK_DEG + off for off in ANGLE_OFFSETS_DEG]
    circuits = []
    metadata = []
    for delay_ns in delays:
        # Free-evolution baseline only needs to be run once per delay.
        name = f"free_d{delay_ns}ns"
        circuits.append(make_circuit(LOCK_DEG, delay_ns, "free", name))
        metadata.append({"name": name, "arm": "free", "angle_deg": None, "delay_ns": delay_ns})
        for angle in angles:
            name = f"xy4_a{angle:.3f}_d{delay_ns}ns".replace("-", "m").replace(".", "p")
            circuits.append(make_circuit(angle, delay_ns, "xy4", name))
            metadata.append({"name": name, "arm": "xy4", "angle_deg": angle, "delay_ns": delay_ns})

    OUTDIR.mkdir(parents=True, exist_ok=True)
    manifest = {
        "experiment": "Scimitar-SSE mapped angle-sweep coherence pilot",
        "created_utc": utc_now(),
        "status": "LOCAL_CIRCUITS_BUILT_NOT_SUBMITTED",
        "hypothesis": "A phase-offset control sequence near 51.843 degrees improves X-basis survival versus matched controls.",
        "interpretation_guardrail": "This does not directly test toroidal electromagnetic geometry or physical quantum-state transfer between nodes.",
        "lock_angle_deg_from_manuscript": LOCK_DEG,
        "angles_deg": angles,
        "delays_ns": delays,
        "shots_per_circuit": args.shots,
        "circuit_count": len(circuits),
        "circuits": metadata,
        "runtime": {"python": sys.version, "platform": platform.platform()},
    }

    if args.dry_run or not args.submit:
        manifest["status"] = "DRY_RUN_ONLY" if args.dry_run else "READY_NOT_SUBMITTED"
        # Save portable OpenQASM 3 for review/transfer without credentials.
        qasm_dir = OUTDIR / "qasm"
        qasm_dir.mkdir(exist_ok=True)
        for qc in circuits:
            try:
                from qiskit import qasm3
                (qasm_dir / f"{qc.name}.qasm").write_text(qasm3.dumps(qc), encoding="utf-8")
            except Exception as exc:
                manifest.setdefault("qasm_export_warnings", []).append(
                    f"{qc.name}: {type(exc).__name__}: {exc}"
                )
        (OUTDIR / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        print(json.dumps({
            "status": manifest["status"],
            "circuits": len(circuits),
            "angles_deg": angles,
            "delays_ns": delays,
            "manifest": str(OUTDIR / "manifest.json"),
            "qasm_dir": str(qasm_dir),
            "next_step": "Set QISKIT_IBM_TOKEN securely, then rerun with --submit."
        }, indent=2))
        return

    token = os.environ.get("QISKIT_IBM_TOKEN")
    if not token:
        raise SystemExit("Missing QISKIT_IBM_TOKEN. Do not put API keys in source files or command history.")
    from qiskit import transpile
    from qiskit_ibm_runtime import QiskitRuntimeService, SamplerV2

    channel = os.environ.get("QISKIT_IBM_CHANNEL", "ibm_quantum_platform")
    instance = os.environ.get("QISKIT_IBM_INSTANCE")
    service_kwargs = {"channel": channel, "token": token}
    if instance:
        service_kwargs["instance"] = instance
    service = QiskitRuntimeService(**service_kwargs)

    if args.backend:
        backend = service.backend(args.backend)
        if getattr(backend, "simulator", False):
            raise SystemExit("Refusing simulator backend: this run is intended for physical QPU.")
    else:
        backend = service.least_busy(operational=True, simulator=False, min_num_qubits=1)

    isa_circuits = transpile(circuits, backend=backend, optimization_level=1)
    # Guard against accidental empty / malformed circuits before a paid/queued submission.
    if len(isa_circuits) != len(circuits):
        raise RuntimeError("Transpilation changed circuit count; refusing submission.")
    manifest.update({
        "status": "SUBMITTING",
        "backend": backend.name,
        "backend_num_qubits": getattr(backend, "num_qubits", None),
        "transpiler_optimization_level": 1,
        "submitted_utc": utc_now(),
    })
    (OUTDIR / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    sampler = SamplerV2(mode=backend)
    job = sampler.run(isa_circuits, shots=args.shots)
    manifest["status"] = "SUBMITTED"
    manifest["job_id"] = job.job_id()
    manifest["submitted_utc"] = utc_now()
    (OUTDIR / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(json.dumps({
        "status": "SUBMITTED",
        "backend": backend.name,
        "job_id": job.job_id(),
        "manifest": str(OUTDIR / "manifest.json"),
        "note": "Job is asynchronous. Run python collect_scimitar_job.py JOB_ID after it completes."
    }, indent=2))


if __name__ == "__main__":
    main()
