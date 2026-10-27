"""GovernanceController.verify_target_scope: symlink-safe, never unscoped."""

import os

import pytest

from osiris_cli.orchestration.controller import GovernanceController

scope = GovernanceController.verify_target_scope


@pytest.fixture
def workspace(tmp_path, monkeypatch):
    ws = tmp_path / "ws"
    ws.mkdir()
    (tmp_path / "outside.py").write_text("x = 1\n")
    monkeypatch.chdir(ws)
    return ws


def test_relative_target_inside_scope(workspace):
    assert scope("module.py", [str(workspace)])[0] is True
    assert scope("pkg/module.py")[0] is True          # default scope: the working directory


def test_no_scope_means_working_directory_not_anywhere(workspace):
    ok, msg = scope(str(workspace.parent / "outside.py"))
    assert ok is False and "outside permitted scope" in msg


def test_traversal_is_refused(workspace):
    assert scope("../outside.py", [str(workspace)])[0] is False


def test_symlink_pointing_outside_is_refused(workspace):
    (workspace / "link.py").symlink_to(workspace.parent / "outside.py")
    ok, msg = scope("link.py", [str(workspace)])
    assert ok is False and "outside permitted scope" in msg


def test_symlink_to_a_governance_file_is_refused(workspace):
    (workspace / "policy.json").write_text("{}")
    (workspace / "innocent.txt").symlink_to(workspace / "policy.json")
    ok, msg = scope("innocent.txt", [str(workspace)])
    assert ok is False and "immutable governance artifact" in msg


def test_sibling_with_shared_prefix_is_not_inside(tmp_path, monkeypatch):
    (tmp_path / "ws").mkdir()
    (tmp_path / "ws-evil").mkdir()
    monkeypatch.chdir(tmp_path)
    assert scope(str(tmp_path / "ws-evil" / "m.py"), [str(tmp_path / "ws")])[0] is False
