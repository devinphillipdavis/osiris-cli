"""
Google Gemini Compatibility Provider
====================================
Adapts the existing gemini_bridge.py Google REST integration into the
unified BaseModelProvider contract.
"""

from __future__ import annotations

import json
import os
import time
from typing import Iterator, Optional

from .base import (
    BaseModelProvider,
    ExecutionPlacement,
    FinishReason,
    HealthStatus,
    ProviderCapabilities,
    ProviderHealth,
    ProviderRequest,
    ProviderResponse,
    ProviderStreamChunk,
)


class GeminiCompatibilityProvider(BaseModelProvider):
    """Wraps Google Gemini REST API conforming to BaseModelProvider."""

    def __init__(self, model: str = "gemini-3.6-flash", timeout: float = 45.0):
        self.selected_model = model
        self.timeout = timeout
        self.cancelled_requests: set[str] = set()

    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(
            provider_name="gemini_compat",
            supports_streaming=False,
            supports_structured_output=True,
            supports_tool_calling=True,
            supports_token_count=True,
            supported_models=["gemini-3.6-flash", "gemini-2.5-flash", "gemini-1.5-pro"],
            max_context_length=1048576,
            default_placement=ExecutionPlacement.CLOUD,
        )

    def health(self) -> ProviderHealth:
        api_key = os.environ.get("GEMINI_API_KEY", "").strip()
        if not api_key:
            return ProviderHealth(
                status=HealthStatus.NOT_CONFIGURED,
                available=False,
                provider_name="gemini_compat",
                selected_model=self.selected_model,
                message="GEMINI_API_KEY environment variable is not set",
            )
        return ProviderHealth(
            status=HealthStatus.HEALTHY,
            available=True,
            provider_name="gemini_compat",
            selected_model=self.selected_model,
            message="Gemini API key is configured",
        )

    def cancel(self, request_id: str) -> bool:
        self.cancelled_requests.add(request_id)
        return True

    def generate(self, request: ProviderRequest) -> ProviderResponse:
        t0 = time.monotonic()
        if request.request_id in self.cancelled_requests:
            return ProviderResponse(
                content="", model=self.selected_model, provider="gemini_compat",
                request_id=request.request_id, finish_reason=FinishReason.CANCELLED, error="Cancelled"
            )

        try:
            import gemini_bridge
        except ImportError:
            return ProviderResponse(
                content="", model=self.selected_model, provider="gemini_compat",
                request_id=request.request_id, finish_reason=FinishReason.ERROR,
                error="gemini_bridge module not found in path"
            )

        if not gemini_bridge.is_configured():
            return ProviderResponse(
                content="", model=self.selected_model, provider="gemini_compat",
                request_id=request.request_id, finish_reason=FinishReason.ERROR,
                error="GEMINI_API_KEY not configured"
            )

        try:
            text = gemini_bridge.query(
                system_prompt=request.system,
                user_prompt=request.get_full_prompt(),
                timeout=int(request.timeout),
                response_schema=request.response_schema,
            )
            duration = (time.monotonic() - t0) * 1000.0

            structured_out = None
            if request.response_schema and text:
                try:
                    structured_out = json.loads(text)
                except Exception:
                    pass

            return ProviderResponse(
                content=text,
                model=gemini_bridge.model_name(),
                provider="gemini_compat",
                request_id=request.request_id,
                finish_reason=FinishReason.STOP,
                eval_count=len(text.split()),
                prompt_eval_count=self.token_count(request),
                total_duration_ms=duration,
                structured_output=structured_out,
            )
        except gemini_bridge.GeminiUnavailable as e:
            return ProviderResponse(
                content="",
                model=self.selected_model,
                provider="gemini_compat",
                request_id=request.request_id,
                finish_reason=FinishReason.ERROR,
                error=f"Gemini unavailable: {e}",
                total_duration_ms=(time.monotonic() - t0) * 1000.0,
            )

    def stream(self, request: ProviderRequest) -> Iterator[ProviderStreamChunk]:
        resp = self.generate(request)
        yield ProviderStreamChunk(
            text=resp.content,
            is_final=True,
            chunk_index=0,
            request_id=request.request_id,
            finish_reason=resp.finish_reason,
        )
