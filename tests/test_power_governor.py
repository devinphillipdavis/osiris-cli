"""PowerGovernor: readings are measured or reported unknown, never invented; an unreadable
sensor refuses unattended work; Engine 3's background step obeys the unattended check."""

import json
import subprocess
from unittest.mock import patch

import pytest

from osiris_cli import osiris_repl
from osiris_cli.osiris_repl import PowerGovernor


def reading(**fields):
    base = {"percentage": 80, "temperature": 27.4, "plugged": "UNPLUGGED"}
    base.update(fields)
    return subprocess.CompletedProcess(["termux-battery-status"], 0, json.dumps(base), "")


def termux(monkeypatch, run, binary="/usr/bin/termux-battery-status"):
    calls = []

    def fake_run(argv, **kw):
        calls.append((argv, kw))
        return run(argv, **kw) if callable(run) else run

    monkeypatch.setattr(osiris_repl.subprocess, "run", fake_run)
    monkeypatch.setattr(osiris_repl.shutil, "which", lambda name: binary)
    gov = PowerGovernor()
    gov._is_termux = True
    return gov, calls


def test_no_sensor_node_reports_unknown_not_invented_numbers():
    gov = PowerGovernor()
    gov._is_termux = False
    dec = gov.check()
    assert dec.allowed and dec.is_desktop and not dec.measured
    assert dec.battery_pct is None and dec.temp_c is None
    assert "Bat: unknown" in repr(dec) and "100.0" not in repr(dec)


def test_measured_reading_is_reported(monkeypatch):
    gov, calls = termux(monkeypatch, reading())
    dec = gov.check()
    assert dec.allowed and dec.measured and (dec.battery_pct, dec.temp_c) == (80.0, 27.4)
    assert dec.summary().endswith("(Bat: 80.0%, Temp: 27.4°C)")
    # termux-api takes ~2.2 s under PRoot on the Fold; the old 1.5 s limit always timed out
    assert calls[0][1]["timeout"] >= 5


def test_falls_back_to_the_termux_bin_when_not_on_path(monkeypatch):
    gov, calls = termux(monkeypatch, reading(), binary=None)
    monkeypatch.setattr(osiris_repl.os, "access", lambda path, mode: path.startswith(osiris_repl.TERMUX_BIN))
    assert gov.check().measured
    assert calls[0][0] == [f"{osiris_repl.TERMUX_BIN}/termux-battery-status"]


def test_readings_are_cached(monkeypatch):
    gov, calls = termux(monkeypatch, reading())
    gov.check()
    gov.check(unattended=True)
    assert len(calls) == 1


@pytest.mark.parametrize("fields, reason", [
    ({"temperature": 47.0}, "Thermal abort"),
    ({"percentage": 9}, "Battery critical"),
])
def test_limits_block(monkeypatch, fields, reason):
    gov, _ = termux(monkeypatch, reading(**fields))
    dec = gov.check()
    assert not dec.allowed and dec.reason.startswith(reason)


def test_low_battery_while_plugged_is_allowed(monkeypatch):
    gov, _ = termux(monkeypatch, reading(percentage=9, plugged="PLUGGED_AC"))
    assert gov.check().allowed


@pytest.mark.parametrize("run", [
    subprocess.CompletedProcess([], 1, "", "no api"),
    subprocess.CompletedProcess([], 0, "not json", ""),
    subprocess.TimeoutExpired("termux-battery-status", 6),
])
def test_unreadable_sensor_refuses_unattended_only(monkeypatch, run):
    def raise_or_return(argv, **kw):
        if isinstance(run, Exception):
            raise run
        return run

    gov, _ = termux(monkeypatch, raise_or_return)
    attended, unattended = gov.check(), gov.check(unattended=True)
    assert attended.allowed and attended.battery_pct is None
    assert not unattended.allowed and "fail-closed" in unattended.reason


def test_incomplete_reading_refuses_unattended(monkeypatch):
    gov, _ = termux(monkeypatch, subprocess.CompletedProcess([], 0, json.dumps({"percentage": 70}), ""))
    assert gov.check().allowed and gov.check().temp_c is None
    assert not gov.check(unattended=True).allowed


# ── Engine 3 background step ───────────────────────────────────────────────────

otc = pytest.importorskip("osiris_termux_console")


def test_background_learning_is_wired_to_the_unattended_check(monkeypatch):
    seen = []
    monkeypatch.setattr(osiris_repl.SESSION.power_gov, "check",
                        lambda unattended=False: seen.append(unattended) or osiris_repl.PowerDecision(False, "no"))
    assert otc.UNATTENDED_POWER_GATE() == (False, "no")
    assert seen == [True]


@pytest.mark.parametrize("gate, ran", [
    (lambda: (True, "ok"), True),
    (lambda: (False, "Power sensor unreadable"), False),
    (lambda: 1 / 0, False),
])
def test_background_learning_obeys_the_gate(monkeypatch, gate, ran):
    learned, notes = [], []
    monkeypatch.setattr(otc, "UNATTENDED_POWER_GATE", gate)
    monkeypatch.setattr(otc, "_organism_learn", learned.append)
    monkeypatch.setattr(otc, "_organism_telemetry", notes.append)
    otc._organism_learn_if_powered("an exchange")
    assert bool(learned) is ran
    assert ran or notes[0].startswith("SKIP reason=")
