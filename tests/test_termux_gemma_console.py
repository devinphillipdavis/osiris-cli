"""
Tests for Termux Runtime Console with Governed Gemma Inference
=============================================================
Verifies that osiris_termux_console.py routes model queries, council cards,
and code synthesis through the governed Gemma inference substrate.
"""

import os
import pytest

import osiris_termux_console as otc
from osiris_cli.providers import GemmaProvider, get_active_provider, reset_active_provider


@pytest.fixture(autouse=True)
def setup_gemma_env():
    """Ensure Gemma mock provider is active for console tests."""
    reset_active_provider()
    os.environ["OSIRIS_MODEL_PROVIDER"] = "gemma"
    os.environ["OSIRIS_GEMMA_MOCK"] = "1"
    prov = get_active_provider(mode="mock", model="gemma-3-1b")
    yield prov
    os.environ.pop("OSIRIS_GEMMA_MOCK", None)
    os.environ.pop("OSIRIS_MODEL_PROVIDER", None)
    reset_active_provider()


def test_termux_console_reachability_with_gemma():
    """Verify that _check_ollama_reachable reports true via Gemma substrate."""
    ok, base = otc._check_ollama_reachable(timeout=0.2)
    assert ok is True
    assert "gemma" in base


def test_termux_console_council_engines_status():
    """Verify that startup council card reflects Gemma substrate status."""
    engines = otc._council_engines(substrate_ok=True)
    architect_row = next(e for e in engines if e[1] == "Architect")
    assert "gemma" in architect_row[2] or "gemma" in architect_row[3]
    assert "UNREACHABLE" not in architect_row[3]


def test_termux_console_query_model_stream():
    """Verify streaming token execution through query_model with Gemma."""
    resp = otc.query_model("Synthesize quantum gate", model="gemma-3-1b", stream=True)
    assert len(resp) > 0


def test_termux_console_synthesize():
    """Verify code synthesis through Gemma provider."""
    code = otc._synthesize("def compute_fidelity(): pass", structured=False)
    assert len(code) > 0
