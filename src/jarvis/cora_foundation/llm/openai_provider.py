"""OpenAIProvider — LLMAdapter for OpenAI Chat Completions API."""

from __future__ import annotations

from typing import Any

from .capabilities import CAPABILITY_OPENAI_DEFAULT, ModelCapability
from .contracts import LLMRequest, LLMResponse
from .http_util import env_key, post_json

DEFAULT_BASE_URL = "https://api.openai.com/v1"
DEFAULT_MODEL = "gpt-4o-mini"


class OpenAIError(RuntimeError):
    pass


class OpenAIProvider:
    provider_id = "openai"

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
        self.api_key = api_key if api_key is not None else env_key("OPENAI_API_KEY", "CORA_OPENAI_API_KEY")
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout_sec = float(timeout_sec)
        self.capability = capability or ModelCapability(
            **{**CAPABILITY_OPENAI_DEFAULT.to_dict(), "model_id": model, "provider_id": self.provider_id}
        )
        self._opener = opener

    def complete(self, request: LLMRequest) -> LLMResponse:
        if not self.api_key and self._opener is None:
            raise OpenAIError("OPENAI_API_KEY missing")
        model = request.model or self.model
        messages: list[dict[str, str]] = []
        if request.system_prompt:
            messages.append({"role": "system", "content": request.system_prompt})
        for msg in request.messages:
            messages.append(
                {"role": str(msg.get("role") or "user"), "content": str(msg.get("content") or "")}
            )
        body = {
            "model": model,
            "messages": messages,
            "temperature": request.temperature,
            "max_tokens": request.max_tokens,
            "stream": False,
        }
        try:
            raw = post_json(
                f"{self.base_url}/chat/completions",
                body,
                headers={"Authorization": f"Bearer {self.api_key or 'test'}"},
                timeout_sec=self.timeout_sec,
                opener=self._opener,
            )
        except RuntimeError as exc:
            raise OpenAIError(str(exc)) from exc
        return self._to_response(raw, model=model)

    def _to_response(self, raw: dict[str, Any], *, model: str) -> LLMResponse:
        if raw.get("error"):
            err = raw["error"]
            msg = err.get("message") if isinstance(err, dict) else str(err)
            raise OpenAIError(str(msg))
        choices = raw.get("choices") or []
        text = ""
        finish = "stop"
        if choices:
            choice = choices[0]
            text = str((choice.get("message") or {}).get("content") or "")
            finish = str(choice.get("finish_reason") or "stop")
        usage = raw.get("usage") or {}
        return LLMResponse(
            text=text,
            finish_reason=finish,
            usage={
                "prompt_tokens": int(usage.get("prompt_tokens") or 0),
                "completion_tokens": int(usage.get("completion_tokens") or 0),
                "total_tokens": int(usage.get("total_tokens") or 0),
            },
            tool_calls=(),
            model=str(raw.get("model") or model),
            provider=self.provider_id,
            metadata={"adapter": "OpenAIProvider", "streaming": False, "tool_calling": False},
        )
