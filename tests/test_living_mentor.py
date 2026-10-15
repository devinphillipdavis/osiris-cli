"""
Tests for Provider Mentor Adapter & Living Conversational Fallback
=================================================================
Verifies that ProviderMentorAdapter satisfies the duck-typed contract
expected by osiris_cli.living.Osiris, and enables conversation through
the Gemma-native substrate even when Ollama is offline.
"""

import pytest
from osiris_cli.providers import GemmaProvider, ProviderMentorAdapter
from osiris_cli.living import Osiris


def test_provider_mentor_adapter_interface():
    """Verify ProviderMentorAdapter exposes all required methods and attributes."""
    gemma = GemmaProvider(model="gemma-3-1b", mode="mock")
    adapter = ProviderMentorAdapter(provider=gemma)

    assert "gemma://" in adapter.base
    installed = adapter.installed()
    assert isinstance(installed, list)
    assert len(installed) > 0
    assert "gemma-3-1b" in installed

    # Model resolution
    assert adapter.model() in adapter.installed()
    adapter.set_model("gemma-3-270m")
    assert adapter.model() == "gemma-3-270m"

    # Fast model resolution
    fast = adapter.fast_model()
    assert fast is not None
    assert "270m" in fast or "1b" in fast or "2b" in fast


def test_provider_mentor_adapter_streaming():
    """Verify streaming chunks through the adapter."""
    gemma = GemmaProvider(model="gemma-3-1b", mode="mock")
    adapter = ProviderMentorAdapter(provider=gemma)

    messages = [
        {"role": "system", "content": "You are a test mentor."},
        {"role": "user", "content": "Explain quantum decoherence."},
    ]
    chunks = list(adapter.stream(messages))
    assert len(chunks) > 0
    full_text = "".join(chunks)
    assert len(full_text) > 0


def test_osiris_converse_with_gemma_mentor(tmp_path):
    """Verify Osiris.converse() works end-to-end with GemmaProvider as mentor."""
    gemma = GemmaProvider(model="gemma-3-1b", mode="mock")
    adapter = ProviderMentorAdapter(provider=gemma)

    out_chunks = []
    osiris = Osiris(
        core=None,
        mentor=adapter,
        home=str(tmp_path),
        out=lambda s: out_chunks.append(s),
        claims_register=False,
    )

    reply = osiris.converse("What is the status of the quantum simulation?")
    assert len(reply) > 0
    assert len(out_chunks) > 0
    # Verify that exchange was recorded to the ledger
    assert osiris.stats["exchanges"] == 1
