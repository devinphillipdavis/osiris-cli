"""No script assumes where a node keeps its checkout (/root on Node Alpha, /home/enki on Node Beta)."""

import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
CHECKOUT_PATHS = ("/root/osiris-cli", "/home/enki/osiris-cli")


def test_no_tracked_script_hard_codes_a_node_checkout_path():
    # Tracked files only: a venv or build/ inside the checkout legitimately holds absolute paths.
    try:
        tracked = subprocess.run(["git", "-C", str(ROOT), "ls-files", "-z", "*.py", "*.sh"],
                                 capture_output=True, text=True, check=True).stdout.split("\0")
    except (OSError, subprocess.CalledProcessError):
        pytest.skip("not a git checkout")
    this = Path(__file__).resolve().relative_to(ROOT).as_posix()
    offenders = [f"{rel}: {p}" for rel in tracked if rel != this
                 for p in CHECKOUT_PATHS if (ROOT / rel).is_file()
                 and p in (ROOT / rel).read_text(errors="ignore")]
    assert not offenders, offenders
