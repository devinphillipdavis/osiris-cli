"""
Tests for Gemma Model Provider & Provider Registry
==================================================
Verifies the provider-neutral interface, Gemma provider contracts,
health status diagnostics, mock fixtures, error handling, and streaming.
"""

import json
import pytest

from osiris_cli.providers import (
    BaseModelProvider,
    ExecutionPlacement,
    FinishReason,
    GEMMA_MANIFEST,
    GemmaProvider,
    HealthStatus,
    OllamaCompatibilityProvider,
    ProviderRequest,
    create_provider,
    get_active_provider,
    get_available_providers,
    reset_active_provider,
)


def test_gemma_manifest_completeness():
    """Verify all canonical Gemma models are catalogued with valid resource envelopes."""
    assert "gemma-3-270m" in GEMMA_MANIFEST
    assert "gemma-3-1b" in GEMMA_MANIFEST
    assert "gemma-2-2b" in GEMMA_MANIFEST
    assert "gemma-3-4b" in GEMMA_MANIFEST
    assert "gemma-3-12b" in GEMMA_MANIFEST
    assert "gemma-3-27b" in GEMMA_MANIFEST

    spec_1b = GEMMA_MANIFEST["gemma-3-1b"]
    assert spec_1b.context_window >= 32768
    assert spec_1b.recommended_placement == ExecutionPlacement.EDGE_MOBILE
    assert spec_1b.memory_footprint_mb < 2000  # fits in mobile RAM budget


def test_gemma_provider_capabilities():
    """Verify capabilities reflect model parameters and supported features."""
    provider = GemmaProvider(model="gemma-3-1b", mode="mock")
    caps = provider.capabilities()
    assert caps.provider_name == "gemma"
    assert caps.supports_streaming is True
    assert caps.supports_structured_output is True
    assert caps.supports_tool_calling is True
    assert caps.max_context_length >= 32768
    assert caps.default_placement == ExecutionPlacement.EDGE_MOBILE


def test_gemma_provider_mock_generate():
    """Test deterministic generation fixture without network dependencies."""
    provider = GemmaProvider(model="gemma-3-1b", mode="mock")
    req = ProviderRequest(prompt="Synthesize a quantum bell state.", max_tokens=100)
    resp = provider.generate(req)

    assert resp.is_success
    assert resp.provider == "gemma"
    assert resp.model == "gemma-3-1b"
    assert "deterministic mock response" in resp.content
    assert resp.eval_count > 0
    assert resp.prompt_eval_count > 0
    assert resp.finish_reason == FinishReason.STOP


def test_gemma_provider_structured_output():
    """Verify JSON schema enforcement in structured responses."""
    provider = GemmaProvider(model="gemma-3-1b", mode="mock")
    schema = {
        "type": "object",
        "properties": {
            "circuit_name": {"type": "string"},
            "qubit_count": {"type": "integer"},
            "is_clifford": {"type": "boolean"},
        },
        "required": ["circuit_name", "qubit_count"],
    }
    req = ProviderRequest(
        prompt="Output circuit spec",
        response_schema=schema,
    )
    resp = provider.generate(req)
    assert resp.is_success
    assert resp.structured_output is not None
    assert isinstance(resp.structured_output, dict)
    assert "circuit_name" in resp.structured_output
    assert resp.structured_output["qubit_count"] == 1
    assert resp.structured_output["is_clifford"] is True


def test_gemma_provider_streaming():
    """Verify streaming token iterator and termination."""
    provider = GemmaProvider(model="gemma-3-1b", mode="mock")
    req = ProviderRequest(prompt="One two three four five.")
    chunks = list(provider.stream(req))

    assert len(chunks) > 1
    assert any(c.is_final for c in chunks)
    full_text = "".join(c.text for c in chunks)
    assert "deterministic mock response" in full_text
    assert chunks[-1].finish_reason == FinishReason.STOP


def test_gemma_provider_cancellation():
    """Verify request cancellation aborts generation gracefully."""
    provider = GemmaProvider(model="gemma-3-1b", mode="mock")
    req = ProviderRequest(prompt="Cancel test", request_id="cancel-req-123")

    provider.cancel("cancel-req-123")
    resp = provider.generate(req)

    assert resp.finish_reason == FinishReason.CANCELLED
    assert not resp.is_success
    assert "cancelled" in resp.error.lower()


def test_gemma_provider_health_unconfigured():
    """Verify health returns NOT_CONFIGURED when endpoint is missing in endpoint mode."""
    provider = GemmaProvider(model="gemma-3-1b", mode="endpoint", endpoint_url="")
    health = provider.health()

    assert health.status == HealthStatus.NOT_CONFIGURED
    assert health.available is False
    assert "not configured" in health.message.lower()


def test_gemma_provider_token_count():
    """Verify token count heuristic operates reliably."""
    provider = GemmaProvider(model="gemma-3-1b", mode="mock")
    req = ProviderRequest(prompt="Quantum computing requires fault-tolerant logical qubits.")
    tokens = provider.token_count(req)
    assert tokens >= 5
    assert tokens <= 20


def test_registry_resolution():
    """Verify provider registry and fallback resolution order."""
    reset_active_provider()
    providers = get_available_providers()
    assert "gemma" in providers
    assert "gemini" in providers
    assert "ollama" in providers

    # Explicit instantiation
    gemma = create_provider("gemma", mode="mock")
    assert isinstance(gemma, GemmaProvider)

    # Active provider defaults to healthy registered provider
    active = get_active_provider()
    assert isinstance(active, BaseModelProvider)
    reset_active_provider()


def test_ollama_compat_health_when_offline():
    """Verify Ollama compatibility provider reports UNAVAILABLE when daemon is offline."""
    ollama = OllamaCompatibilityProvider(host="http://127.0.0.1:65530", timeout=0.5)
    health = ollama.health()
    assert health.status == HealthStatus.UNAVAILABLE
    assert health.available is False


def test_gemma_provider_unconfigured_auto_mode_no_crash():
    """Verify GemmaProvider in auto mode with unset endpoint resolves cleanly without ValueError."""
    provider = GemmaProvider(mode="auto", endpoint_url="")
    req = ProviderRequest(prompt="Hello OSIRIS")
    chunks = list(provider.stream(req))
    assert len(chunks) > 0
    full_text = "".join(c.text for c in chunks)
    assert len(full_text) > 0


def test_gemma_provider_endpoint_mode_invalid_url_no_crash():
    """Verify GemmaProvider in endpoint mode with empty endpoint never throws ValueError: unknown url type."""
    provider = GemmaProvider(mode="endpoint", endpoint_url="")
    req = ProviderRequest(prompt="Test prompt")
    # Stream must yield fallback mock or error chunk, never raise ValueError
    chunks = list(provider.stream(req))
    assert len(chunks) > 0
    # Generate must return clean ProviderResponse
    resp = provider.generate(req)
    assert resp is not None

