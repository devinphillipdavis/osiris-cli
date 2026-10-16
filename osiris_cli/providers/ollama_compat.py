"""
Ollama Compatibility Provider
=============================
Optional backwards-compatibility adapter preserving existing Ollama paths
(local Qwen/DeepSeek) as secondary backends without making Ollama an
architectural prerequisite for the OSIRIS core.
"""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
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


class OllamaCompatibilityProvider(BaseModelProvider):
    """Wraps Ollama HTTP API conforming to BaseModelProvider."""

    def __init__(self, host: Optional[str] = None, model: str = "qwen2.5:1.5b", timeout: float = 60.0):
        self.host = (host or os.environ.get("OLLAMA_HOST", "http://localhost:11434")).rstrip("/")
        self.selected_model = model
        self.timeout = timeout
        self.cancelled_requests: set[str] = set()

    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(
            provider_name="ollama_compat",
            supports_streaming=True,
            supports_structured_output=True,
            supports_tool_calling=False,
            supports_token_count=True,
            supported_models=["qwen2.5:1.5b", "qwen2.5:7b", "deepseek-coder", "llama3.2:1b"],
            max_context_length=4096,
            default_placement=ExecutionPlacement.WORKSTATION,
            metadata={"host": self.host},
        )

    def health(self) -> ProviderHealth:
        t0 = time.monotonic()
        url = f"{self.host}/api/tags"
        try:
            req = urllib.request.Request(url, method="GET")
            with urllib.request.urlopen(req, timeout=min(3.0, self.timeout)) as resp:
                if resp.getcode() == 200:
                    data = json.loads(resp.read().decode())
                    models = [m.get("name", "") for m in data.get("models", [])]
                    return ProviderHealth(
                        status=HealthStatus.HEALTHY,
                        available=True,
                        provider_name="ollama_compat",
                        selected_model=self.selected_model,
                        message=f"Ollama reachable at {self.host} with {len(models)} model(s)",
                        details={"installed_models": models},
                        latency_ms=(time.monotonic() - t0) * 1000,
                    )
                return ProviderHealth(
                    status=HealthStatus.DEGRADED,
                    available=False,
                    provider_name="ollama_compat",
                    message=f"Ollama returned HTTP {resp.getcode()}",
                )
        except urllib.error.URLError as e:
            return ProviderHealth(
                status=HealthStatus.UNAVAILABLE,
                available=False,
                provider_name="ollama_compat",
                message=f"Ollama service unreachable at {self.host} ({e.reason})",
            )
        except Exception as e:
            return ProviderHealth(
                status=HealthStatus.UNAVAILABLE,
                available=False,
                provider_name="ollama_compat",
                message=f"Ollama check error: {e}",
            )

    def cancel(self, request_id: str) -> bool:
        self.cancelled_requests.add(request_id)
        return True

    def generate(self, request: ProviderRequest) -> ProviderResponse:
        t0 = time.monotonic()
        if request.request_id in self.cancelled_requests:
            return ProviderResponse(
                content="", model=self.selected_model, provider="ollama_compat",
                request_id=request.request_id, finish_reason=FinishReason.CANCELLED, error="Cancelled"
            )

        model = request.model or self.selected_model
        payload = {
            "model": model,
            "prompt": request.get_full_prompt(),
            "stream": False,
            "options": {
                "num_predict": request.max_tokens,
                "temperature": request.temperature,
            },
        }
        if request.system:
            payload["system"] = request.system
        if request.response_schema:
            payload["format"] = request.response_schema

        body = json.dumps(payload).encode()
        req = urllib.request.Request(f"{self.host}/api/generate", data=body,
                                     headers={"Content-Type": "application/json"}, method="POST")

        try:
            with urllib.request.urlopen(req, timeout=request.timeout) as resp:
                data = json.loads(resp.read().decode())
                content = data.get("response", "")
                duration = (time.monotonic() - t0) * 1000.0
                eval_count = data.get("eval_count", 0)

                structured_out = None
                if request.response_schema and content:
                    try:
                        structured_out = json.loads(content)
                    except Exception:
                        pass

                return ProviderResponse(
                    content=content,
                    model=model,
                    provider="ollama_compat",
                    request_id=request.request_id,
                    finish_reason=FinishReason.STOP if data.get("done") else FinishReason.LENGTH,
                    eval_count=eval_count,
                    prompt_eval_count=data.get("prompt_eval_count", 0),
                    total_duration_ms=duration,
                    structured_output=structured_out,
                )
        except Exception as e:
            return ProviderResponse(
                content="",
                model=model,
                provider="ollama_compat",
                request_id=request.request_id,
                finish_reason=FinishReason.ERROR,
                error=f"Ollama call failed: {e}",
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
