#!/usr/bin/env python3
"""OSIRIS Compliant Sovereign Execution Wrapper
=============================================
Enforces physical dual-substrate invariants, architecture probing,
thermal/temporal horizons, and unbuffered UTF-8 stream topologies:
- Node Alpha (Mobile Edge - Fold7/Termux): Strict 300.0s temporal lock
- Node Beta (Compute Workstation - PC/WSL): Extended 1800.0s execution horizon
"""

import os
import platform
import subprocess
import sys


def launch_sovereign_repl() -> int:
    # 1. Probe Substrate Context
    arch = platform.machine().lower()
    is_termux = bool(
        os.environ.get("TERMUX_VERSION") or
        os.path.exists("/data/data/com.termux") or
        "com.termux" in os.environ.get("PREFIX", "")
    )
    is_alpha = (arch in ["aarch64", "arm64"]) or is_termux
    node_name = "Alpha (Mobile Edge - Fold7/Termux)" if is_alpha else "Beta (Compute Workstation - PC/WSL)"

    # 2. Assign Thermal/Temporal Horizon
    timeout_limit = 300.0 if is_alpha else 1800.0
    print(f"\033[1;36m[Node {node_name}]\033[0m Initializing OSIRIS daemon with {timeout_limit:.0f}s temporal horizon...")

    # 3. Apply dna::}{lang Topology Variables
    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"

    # 4. Execute with enforced sovereignty
    try:
        res = subprocess.run(
            [sys.executable, "-m", "osiris_cli.osiris_repl"],
            env=env,
            timeout=timeout_limit,
        )
        return res.returncode
    except subprocess.TimeoutExpired:
        print(f"\n\033[1;31m[Node {node_name}] Execution halted: {timeout_limit:.0f}s thermal/temporal horizon reached.\033[0m")
        return 124
    except KeyboardInterrupt:
        print(f"\n\033[1;33m[Node {node_name}] Session closed by operator.\033[0m")
        return 0


if __name__ == "__main__":
    sys.exit(launch_sovereign_repl())
