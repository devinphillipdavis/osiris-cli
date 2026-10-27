"""One interactive surface: legacy entry points open the OSIRIS REPL."""

import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import osiris_launcher
import osiris_shell
from osiris_cli import osiris_repl


def test_legacy_shell_opens_the_repl(monkeypatch):
    calls = []
    monkeypatch.delenv("OSIRIS_LEGACY_SHELL", raising=False)
    monkeypatch.setattr(osiris_repl, "main", lambda argv=None: calls.append(argv))
    monkeypatch.setattr(osiris_shell, "legacy_main", lambda: calls.append("legacy"))
    osiris_shell.main()
    assert calls == [[]]


def test_legacy_shell_escape_hatch(monkeypatch):
    calls = []
    monkeypatch.setenv("OSIRIS_LEGACY_SHELL", "1")
    monkeypatch.setattr(osiris_repl, "main", lambda argv=None: calls.append(argv))
    monkeypatch.setattr(osiris_shell, "legacy_main", lambda: calls.append("legacy"))
    osiris_shell.main()
    assert calls == ["legacy"]


def test_launcher_chat_opens_the_repl(monkeypatch):
    calls = []
    monkeypatch.setattr(osiris_repl, "main", lambda argv=None: calls.append(argv))
    osiris_launcher.cmd_chat(types.SimpleNamespace(tui=False))
    assert calls == [[]]


def test_launcher_chat_tui_keeps_textual(monkeypatch):
    calls = []
    fake = types.ModuleType("osiris_tui_core")
    fake.run_textual_mode = lambda: calls.append("tui")
    monkeypatch.setitem(sys.modules, "osiris_tui_core", fake)
    monkeypatch.setattr(osiris_repl, "main", lambda argv=None: calls.append(argv))
    osiris_launcher.cmd_chat(types.SimpleNamespace(tui=True))
    assert calls == ["tui"]
