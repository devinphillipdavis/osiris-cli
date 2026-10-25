"""Keys typed while a command prints are captured, not scattered into its output.

Reproduces 2026-10-25: '/architecture' typed during /check output was echoed into the
bench table, looked lost, was retyped, and the terminal delivered
'/architecture/architecture'. Runs a child on a real pseudo-terminal, because the bug
lives in terminal echo and line discipline, which mocks cannot reproduce.
"""

import os
import select
import subprocess
import sys
import textwrap
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent

pty = pytest.importorskip("pty")
pytestmark = pytest.mark.skipif(sys.platform == "win32", reason="POSIX terminals only")


class Terminal:
    """A child Python process attached to a pseudo-terminal, driven like a keyboard."""

    def __init__(self, body: str):
        script = f"import sys, time\nsys.path.insert(0, {str(ROOT)!r})\n" + textwrap.dedent(body)
        self.master, slave = pty.openpty()
        self.proc = subprocess.Popen(
            [sys.executable, "-c", script],
            stdin=slave, stdout=slave, stderr=slave, close_fds=True, start_new_session=True,
        )
        os.close(slave)
        self.seen = b""
        self.pos = 0  # everything before this has been consumed by expect()

    def expect(self, marker: str, timeout: float = 10.0) -> bytes:
        """Consume output up to and including the next `marker`; return that stretch."""
        start = self.pos
        deadline = time.time() + timeout
        while marker.encode() not in self.seen[start:]:
            remaining = deadline - time.time()
            if remaining <= 0 or not select.select([self.master], [], [], remaining)[0]:
                raise AssertionError(f"never saw {marker!r}; output: {self.seen[start:]!r}")
            try:
                self.seen += os.read(self.master, 4096)
            except OSError:
                raise AssertionError(f"child exited before {marker!r}; output: {self.seen[start:]!r}")
        self.pos = self.seen.index(marker.encode(), start) + len(marker)
        return self.seen[start:self.pos]

    def type(self, keys: str) -> None:
        os.write(self.master, keys.encode())

    def value(self, label: str) -> str:
        """The repr printed after 'label=' on its own line."""
        self.expect(f"{label}=")
        return eval(self.expect("\n").decode().strip())  # noqa: S307 - our own child printed a repr

    def close(self):
        self.proc.kill()
        self.proc.wait(timeout=5)
        os.close(self.master)


@pytest.fixture
def terminal():
    made = []

    def make(body):
        t = Terminal(body)
        made.append(t)
        return t

    yield make
    for t in made:
        t.close()


COMMAND = """
from osiris_cli.living import PausingStdin, TypeAhead
with TypeAhead(True) as typed:
    real = sys.stdin
    sys.stdin = PausingStdin(real)
    try:
        print("READY", flush=True)   # capture is active: keys typed from here on are the test
        time.sleep(1.0)
        print("TABLE-ROW", flush=True)
        {in_command}
    finally:
        sys.stdin = real
print("TYPED=" + repr(typed.text), flush=True)
print("PROMPT", flush=True)
print("LINE=" + repr(sys.stdin.readline()), flush=True)
"""


def test_keys_typed_during_output_are_not_echoed_into_it_or_doubled(terminal):
    t = terminal(COMMAND.format(in_command="pass"))
    t.expect("READY")
    t.type("/archi")                       # typed while the command is still printing
    output = t.expect("TABLE-ROW")
    assert b"/archi" not in output         # not scattered into the command's output
    assert t.value("TYPED") == "/archi"    # captured, so the REPL can show it
    t.expect("PROMPT")
    t.type("/architecture\n")              # what the user retypes at the prompt
    assert t.value("LINE") == "/architecture\n"   # was '/architecture/architecture\n'


def test_finished_line_typed_during_output_is_captured_whole(terminal):
    t = terminal(COMMAND.format(in_command="pass"))
    t.expect("READY")
    t.type("/status\n")
    t.expect("TABLE-ROW")
    assert t.value("TYPED") == "/status\n"


def test_a_question_inside_the_command_reads_normally_with_echo(terminal):
    # The question is printed inside paused(), so anything typed after it is unambiguously
    # the answer. (Keys landing in the microseconds between a command's print and its read
    # count as typed-ahead; no person types that fast, a test harness does.)
    t = terminal(COMMAND.format(in_command=(
        'from osiris_cli.living import paused\n'
        '        with paused():\n'
        '            print("ASK", flush=True)\n'
        '            print("ANS=" + repr(real.readline()), flush=True)'
    )))
    t.expect("READY")
    t.type("early")                        # typed before the question existed
    t.expect("ASK")
    t.type("yes\n")
    echoed = t.expect("ANS=")
    assert b"yes" in echoed                # the answer is echoed as the user types it
    assert eval(t.expect("\n").decode().strip()) == "yes\n"   # noqa: S307
    assert t.value("TYPED") == "early"     # early keys are kept apart, not mixed into the answer


def test_terminal_mode_is_restored_after_a_command(terminal):
    t = terminal("""
import termios
from osiris_cli.living import TypeAhead
before = termios.tcgetattr(0)
try:
    with TypeAhead(True):
        raise RuntimeError("command failed")
except RuntimeError:
    pass
print("RESTORED=" + repr(termios.tcgetattr(0) == before), flush=True)
""")
    assert t.value("RESTORED") is True


def test_dispatch_capturing_is_plain_dispatch_off_a_terminal(monkeypatch):
    import io

    from osiris_cli import osiris_repl

    calls = []
    monkeypatch.setattr(osiris_repl, "safe_dispatch", lambda state, line: calls.append(line))
    monkeypatch.setattr(sys, "stdin", io.StringIO(""))
    osiris_repl.dispatch_capturing(osiris_repl.SESSION, "/status")
    assert calls == ["/status"]


def test_pausing_stdin_reads_inside_paused(monkeypatch):
    import io

    from osiris_cli import living

    events = []

    class Recorder:
        def __enter__(self):
            events.append("pause")

        def __exit__(self, *exc):
            events.append("resume")
            return False

    monkeypatch.setattr(living, "paused", Recorder)
    stdin = living.PausingStdin(io.StringIO("a\nb\n"))
    assert stdin.readline() == "a\n"
    assert list(stdin) == ["b\n"]
    assert events[:2] == ["pause", "resume"] and len(events) >= 4
