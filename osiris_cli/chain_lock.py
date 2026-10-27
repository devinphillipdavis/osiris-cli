"""One writer at a time for OSIRIS's hash-chained JSONL ledgers.

A chained append is read-the-tip, hash, write. Two writers that read the same tip both link
to it and the chain forks (the exchange log forked seven times on 2026-10-07 that way). Every
chained append therefore happens inside ``locked_tail``: an exclusive lock on the ledger, the
real last entry read from disk under that lock, and the write made before the lock is released.

A tail that cannot be read (a torn or hand-edited last line) is not papered over with an
in-memory head -- that is how forks and breaks are made. The append is refused with
``ChainTailError`` and the ledger has to be repaired first.

Locking: ``fcntl.flock`` where it exists (Linux, Termux/PRoot, macOS). Elsewhere a sidecar
``<ledger>.lock`` created with O_EXCL; if it cannot be taken within ``timeout_s`` the append
is refused with ``ChainLockTimeout``, never made unlocked.
"""

from __future__ import annotations

import contextlib
import json
import os
import time
from typing import Any, Callable, Dict, Iterator, Optional, Tuple

try:
    import fcntl
except ImportError:  # Windows
    fcntl = None

LOCK_TIMEOUT_S = 10.0


class ChainTailError(RuntimeError):
    """The ledger's last entry cannot be read, so there is no tip to chain to."""


class ChainLockTimeout(RuntimeError):
    """Another writer held the ledger longer than the timeout."""


def read_tail(f, block: int = 65536) -> Optional[Dict[str, Any]]:
    """The last non-empty line of an open binary file, parsed. None for an empty file. Reads
    backwards in blocks, so a long last line (a pasted document) is not a full-file read."""
    f.seek(0, os.SEEK_END)
    pos = f.tell()
    buf = b""
    while pos > 0:
        step = min(block, pos)
        pos -= step
        f.seek(pos)
        buf = f.read(step) + buf
        lines = [ln for ln in buf.split(b"\n") if ln.strip()]
        if not lines:
            continue
        if len(lines) > 1 or pos == 0:
            try:
                entry = json.loads(lines[-1].decode("utf-8"))
            except (UnicodeDecodeError, ValueError) as e:
                raise ChainTailError(f"last entry of {getattr(f, 'name', 'ledger')} is not JSON ({e})") from None
            if not isinstance(entry, dict) or not isinstance(entry.get("hash"), str):
                raise ChainTailError(f"last entry of {getattr(f, 'name', 'ledger')} has no hash")
            return entry
    return None


@contextlib.contextmanager
def _sidecar_lock(path: str, timeout_s: float) -> Iterator[None]:
    lock_path = path + ".lock"
    deadline = time.monotonic() + timeout_s
    while True:
        try:
            fd = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            break
        except FileExistsError:
            if time.monotonic() >= deadline:
                raise ChainLockTimeout(f"{lock_path} held for more than {timeout_s:.0f}s") from None
            time.sleep(0.05)
    try:
        os.write(fd, str(os.getpid()).encode())
        yield
    finally:
        os.close(fd)
        with contextlib.suppress(OSError):
            os.unlink(lock_path)


@contextlib.contextmanager
def locked_tail(path: str, timeout_s: float = LOCK_TIMEOUT_S) -> Iterator[Tuple[Any, Optional[Dict[str, Any]]]]:
    """Yields ``(f, last_entry)`` with the ledger exclusively locked. ``f`` is the ledger opened
    binary for append; write the new line(s) to it before leaving the block."""
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    fd = os.open(path, os.O_RDWR | os.O_APPEND | os.O_CREAT, 0o600)
    with os.fdopen(fd, "r+b") as f:
        if fcntl is not None:
            fcntl.flock(f.fileno(), fcntl.LOCK_EX)
            try:
                yield f, read_tail(f)
            finally:
                fcntl.flock(f.fileno(), fcntl.LOCK_UN)
        else:
            with _sidecar_lock(path, timeout_s):
                yield f, read_tail(f)


def write_line(f, entry: Dict[str, Any], **dumps_kw: Any) -> None:
    """Append one JSON line and make it durable before the lock is released."""
    f.seek(0, os.SEEK_END)
    f.write((json.dumps(entry, **dumps_kw) + "\n").encode("utf-8"))
    f.flush()
    os.fsync(f.fileno())


def append_chained(path: str, build: Callable[[Optional[Dict[str, Any]]], Dict[str, Any]],
                   **dumps_kw: Any) -> Dict[str, Any]:
    """Append ``build(last_entry)`` -- the complete new entry, hash included -- under the lock."""
    with locked_tail(path) as (f, last):
        entry = build(last)
        write_line(f, entry, **dumps_kw)
    return entry
