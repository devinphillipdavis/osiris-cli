"""
OSIRIS Provider Mentor Adapter
=============================
Bridges OSIRIS BaseModelProvider (Gemma, Gemini, Ollama) to the Mentor interface
expected by osiris_cli.living.Osiris.

Ensures OSIRIS conversational voice never fails-closed solely due to an offline
Ollama daemon by routing queries to first-class Gemma substrates, Gemini burst,
or local deterministic mock engines.
"""

from __future__ import annotations

import logging
import os
from typing import Any, Dict, Iterator, List, Optional

from .base import BaseModelProvider, HealthStatus, Message, ProviderRequest
from .registry import create_provider, get_active_provider

logger = logging.getLogger("OSIRIS_MENTOR_ADAPTER")


class ProviderMentorAdapter:
    """
    Mentor adapter wrapping BaseModelProvider into the duck-typed interface
    used by Osiris.converse() and Osiris.prewarm().
    """

    def __init__(
        self,
        provider: Optional[BaseModelProvider] = None,
        model: Optional[str] = None,
        timeout: float = 60.0,
    ):
        self._provider = provider
        self._model = model
        self.timeout = timeout

    @property
    def provider(self) -> BaseModelProvider:
        if self._provider is None:
            self._provider = get_active_provider()
        return self._provider

    @property
    def base(self) -> str:
        prov = self.provider
        try:
            prov_name = prov.capabilities().provider_name
        except Exception:
            prov_name = getattr(prov, "name", prov.__class__.__name__.lower())
            if prov_name.endswith("provider"):
                prov_name = prov_name[:-8]
        endpoint = getattr(prov, "endpoint", getattr(prov, "mode", "native"))
        return f"{prov_name}://{endpoint}"

    def installed(self) -> List[str]:
        """Return list of available models for the current provider."""
        try:
            caps = self.provider.capabilities()
            return list(caps.supported_models)
        except Exception as e:
            logger.warning(f"Failed to query provider capabilities: {e}")
            return ["gemma-3-1b", "gemma-3-270m", "gemma-2-2b"]

    def model(self) -> Optional[str]:
        """Resolve current active model."""
        if self._model:
            return self._model
        env_model = os.environ.get("OSIRIS_CHAT_MODEL")
        if env_model:
            return env_model
        models = self.installed()
        return models[0] if models else "gemma-3-1b"

    def set_model(self, name: Optional[str]) -> None:
        """Set explicitly pinned mentor model."""
        self._model = name

    def fast_model(self) -> Optional[str]:
        """Return low-latency / small variant model if available."""
        models = self.installed()
        for m in models:
            if "270m" in m or "1b" in m or "2b" in m:
                if m != self.model():
                    return m
        return None

    def unload(self, model: Optional[str] = None) -> None:
        """Free model memory if supported by substrate."""
        if hasattr(self.provider, "unload"):
            try:
                getattr(self.provider, "unload")(model)
            except Exception:
                pass

    def warm(self, messages: List[Dict[str, str]], model: Optional[str] = None) -> None:
        """Warm up model inference cache with 1 token."""
        req = self._convert_messages(messages, model=model, max_tokens=1, stream=False)
        try:
            self.provider.generate(req)
        except Exception as e:
            logger.debug(f"Mentor warm-up failed: {e}")

    def stream(self, messages: List[Dict[str, str]], model: Optional[str] = None) -> Iterator[str]:
        """Stream conversational chunks from the active provider with automatic fallback."""
        target_model = model or self.model()
        req = self._convert_messages(messages, model=target_model, max_tokens=1024, stream=True)

        try:
            chunks = self.provider.stream(req)
            yielded_any = False
            for chunk in chunks:
                if chunk.text:
                    yielded_any = True
                    yield chunk.text
            if not yielded_any:
                # Fallback to non-streaming generate if stream yielded nothing
                resp = self.provider.generate(req)
                if resp.content:
                    yield resp.content
        except Exception as e:
            logger.warning(f"Primary mentor streaming error ({type(e).__name__}: {e}), attempting fallback...")
            # If current provider fails, try fallback mock provider for fail-safe REPL continuity
            try:
                fallback_provider = create_provider("gemma", mode="mock", model="gemma-3-1b")
                resp = fallback_provider.generate(req)
                yield f"[gemma:mock fallback] {resp.content}"
            except Exception as e_fallback:
                raise ConnectionError(f"Mentor substrate exhausted: {e} -> fallback error: {e_fallback}") from e

    def _convert_messages(
        self,
        messages: List[Dict[str, str]],
        model: Optional[str] = None,
        max_tokens: int = 512,
        stream: bool = False,
    ) -> ProviderRequest:
        converted = [
            Message(role=m.get("role", "user"), content=m.get("content", ""))
            for m in messages
        ]
        return ProviderRequest(
            messages=converted,
            model=model or self.model(),
            max_tokens=max_tokens,
            stream=stream,
            timeout=self.timeout,
        )
