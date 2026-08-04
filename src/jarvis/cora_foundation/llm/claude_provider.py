"""ClaudeProvider — LLMAdapter for Anthropic Messages API."""

from __future__ import annotations

from typing import Any

from .capabilities import CAPABILITY_CLAUDE_DEFAULT, ModelCapability
from .contracts import LLMRequest, LLMResponse
from .http_util import env_key, post_json

DEFAULT_BASE_URL = "https://api.anthropic.com/v1"
DEFAULT_MODEL = "claude-sonnet-4-20250514"
ANTHROPIC_VERSION = "2023-06-01"


class ClaudeError(RuntimeError):
    pass


class ClaudeProvider:
    provider_id = "claude"

    def __init__(
        self,
        *,
        api_key: str | None = None,
        base_url: str = DEFAULT_BASE_URL,
        model: str = DEFAULT_MODEL,
        timeout_sec: float = 120.0,
        capability: ModelCapability | None = None,
        opener: Any | None = None,
    ) -> None:
        self.api_key = api_key if api_key is not None else env_key(
            "ANTHROPIC_API_KEY", "CLAUDE_API_KEY", "CORA_ANTHROPIC_API_KEY"
        )
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout_sec = float(timeout_sec)
        self.capability = capability or ModelCapability(
            **{**CAPABILITY_CLAUDE_DEFAULT.to_dict(), "model_id": model, "provider_id": self.provider_id}
        )
        self._opener = opener

    def complete(self, request: LLMRequest) -> LLMResponse:
        if not self.api_key and self._opener is None:
            raise ClaudeError("ANTHROPIC_API_KEY missing")
        model = request.model or self.model
        messages: list[dict[str, str]] = []
        for msg in request.messages:
            role = str(msg.get("role") or "user")
            if role == "system":
                continue
            messages.append({"role": role, "content": str(msg.get("content") or "")})
        if not messages:
            messages = [{"role": "user", "content": ""}]
        body: dict[str, Any] = {
            "model": model,
            "max_tokens": request.max_tokens,
            "temperature": request.temperature,
            "messages": messages,
        }
        if request.system_prompt:
            body["system"] = request.system_prompt
        try:
            raw = post_json(
                f"{self.base_url}/messages",
                body,
                headers={
                    "x-api-key": self.api_key or "test",
                    "anthropic-version": ANTHROPIC_VERSION,
                },
                timeout_sec=self.timeout_sec,
                opener=self._opener,
            )
        except RuntimeError as exc:
            raise ClaudeError(str(exc)) from exc
        return self._to_response(raw, model=model)

    def _to_response(self, raw: dict[str, Any], *, model: str) -> LLMResponse:
        if raw.get("type") == "error" or raw.get("error"):
            err = raw.get("error") or raw
            msg = err.get("message") if isinstance(err, dict) else str(err)
            raise ClaudeError(str(msg))
        parts = raw.get("content") or []
        texts = []
        for part in parts:
            if isinstance(part, dict) and part.get("type") == "text":
                texts.append(str(part.get("text") or ""))
        usage = raw.get("usage") or {}
        prompt_t = int(usage.get("input_tokens") or 0)
        completion_t = int(usage.get("output_tokens") or 0)
        return LLMResponse(
            text="".join(texts),
            finish_reason=str(raw.get("stop_reason") or "stop"),
            usage={
                "prompt_tokens": prompt_t,
                "completion_tokens": completion_t,
                "total_tokens": prompt_t + completion_t,
            },
            tool_calls=(),
            model=str(raw.get("model") or model),
            provider=self.provider_id,
            metadata={"adapter": "ClaudeProvider", "streaming": False, "tool_calling": False},
        )
