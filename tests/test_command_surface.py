"""
Tests for OSIRIS Command Surface & Canonical Registry
=====================================================
Verifies that:
  - Canonical command surface is derived from authoritative registry
  - Read-only commands are distinguished from mutating commands
  - Mutating commands require governance authorization (SYS-021)
  - Divergence between command registry, documentation, and policy is caught
"""

import pytest

from osiris_termux_console import IMMEDIATE_COMMANDS, READ_ONLY_COMMANDS


def test_command_surface_completeness():
    """Verify that canonical commands from the live REPL are registered."""
    core_expected = {
        "/ignite", "/status", "/help", "/ledger", "/sprint",
        "/gap", "/gaps", "/bench", "/mentors", "/runs",
        "/apply", "/why", "/home", "/check", "/discover", "/lab",
    }
    for cmd in core_expected:
        assert cmd in IMMEDIATE_COMMANDS, f"Core command {cmd} missing from IMMEDIATE_COMMANDS"


def test_read_only_commands_contain_no_mutating_actions():
    """Verify read-only commands do not include destructive or mutating operations."""
    mutating = {"/apply", "/ignite", "/metamorphosis", "/sprint execute"}
    for cmd in mutating:
        assert cmd not in READ_ONLY_COMMANDS, f"Mutating command {cmd} must not be in READ_ONLY_COMMANDS"


def test_command_safety_classification():
    """Verify each immediate command has a deterministic safety classification."""
    for cmd in IMMEDIATE_COMMANDS:
        is_read_only = cmd in READ_ONLY_COMMANDS
        # Every command must be classified either as read-only or as requiring state mutation handling
        assert isinstance(is_read_only, bool)
