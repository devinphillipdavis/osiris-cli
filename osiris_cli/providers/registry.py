"""
OSIRIS Model Provider Registry
==============================
Central registry and factory for managing and activating model providers.
Supports automatic discovery, prioritization, and fallbacks:
  Gemma (default/native) -> Gemini (cloud burst) -> Ollama (local compat)
"""

from __future__ import annotations

import logging
import os
from typing import Dict, List, Optional, Type

from .base import BaseModelProvider, HealthStatus
from .gemma import GEMMA_MANIFEST, GemmaProvider
from .gemini_compat import GeminiCompatibilityProvider
from .ollama_compat import OllamaCompatibilityProvider

logger = logging.getLogger("OSIRIS_PROVIDER_REGISTRY")

_REGISTRY: Dict[str, Type[BaseModelProvider]] = {
    "gemma": GemmaProvider,
    "gemini": GeminiCompatibilityProvider,
    "ollama": OllamaCompatibilityProvider,
}

_ACTIVE_PROVIDER: Optional[BaseModelProvider] = None


def register_provider(name: str, provider_cls: Type[BaseModelProvider]) -> None:
    """Register a custom provider class."""
    _REGISTRY[name.lower()] = provider_cls


def get_available_providers() -> List[str]:
    """Return names of registered providers."""
    return list(_REGISTRY.keys())


def create_provider(name: str, **kwargs) -> BaseModelProvider:
    """Instantiate a provider by name."""
    cls = _REGISTRY.get(name.lower())
    if not cls:
        raise ValueError(f"Unknown provider '{name}'. Available: {get_available_providers()}")
    return cls(**kwargs)


def get_active_provider(force_name: Optional[str] = None, **kwargs) -> BaseModelProvider:
    """
    Get or resolve the active model provider.
    Priority order:
      1. Explicit force_name
      2. Environment variable OSIRIS_MODEL_PROVIDER
      3. GemmaProvider if available/configured
      4. Gemini if GEMINI_API_KEY is configured
      5. Ollama if running
      6. Default to Gemma in mock mode for fail-safe deterministic operation
    """
    global _ACTIVE_PROVIDER
    if force_name:
        _ACTIVE_PROVIDER = create_provider(force_name, **kwargs)
        return _ACTIVE_PROVIDER

    if _ACTIVE_PROVIDER is not None:
        return _ACTIVE_PROVIDER

    env_provider = os.environ.get("OSIRIS_MODEL_PROVIDER", "").lower()
    if env_provider and env_provider in _REGISTRY:
        _ACTIVE_PROVIDER = create_provider(env_provider, **kwargs)
        return _ACTIVE_PROVIDER

    # 1. Gemma if configured or live local endpoint
    gemma = GemmaProvider(**kwargs)
    if gemma.mode == "endpoint" and gemma.health().available:
        _ACTIVE_PROVIDER = gemma
        return _ACTIVE_PROVIDER

    # 2. Gemini if configured
    try:
        import gemini_bridge
        if gemini_bridge.is_configured():
            gemini = GeminiCompatibilityProvider(**kwargs)
            if gemini.health().available:
                _ACTIVE_PROVIDER = gemini
                return _ACTIVE_PROVIDER
    except Exception:
        pass

    # 3. Default to Gemma (local or mock)
    _ACTIVE_PROVIDER = gemma
    return _ACTIVE_PROVIDER


def reset_active_provider() -> None:
    """Reset the cached singleton."""
    global _ACTIVE_PROVIDER
    _ACTIVE_PROVIDER = None
