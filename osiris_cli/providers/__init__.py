"""
OSIRIS Provider-Neutral Inference Layer
=======================================
"""

from .base import (
    BaseModelProvider,
    ExecutionPlacement,
    FinishReason,
    HealthStatus,
    Message,
    ProviderCapabilities,
    ProviderHealth,
    ProviderRequest,
    ProviderResponse,
    ProviderStreamChunk,
)
from .gemma import GEMMA_MANIFEST, GemmaModelSpec, GemmaProvider
from .gemini_compat import GeminiCompatibilityProvider
from .ollama_compat import OllamaCompatibilityProvider
from .registry import (
    create_provider,
    get_active_provider,
    get_available_providers,
    register_provider,
    reset_active_provider,
)

__all__ = [
    "BaseModelProvider",
    "ExecutionPlacement",
    "FinishReason",
    "HealthStatus",
    "Message",
    "ProviderCapabilities",
    "ProviderHealth",
    "ProviderRequest",
    "ProviderResponse",
    "ProviderStreamChunk",
    "GEMMA_MANIFEST",
    "GemmaModelSpec",
    "GemmaProvider",
    "GeminiCompatibilityProvider",
    "OllamaCompatibilityProvider",
    "create_provider",
    "get_active_provider",
    "get_available_providers",
    "register_provider",
    "reset_active_provider",
]
