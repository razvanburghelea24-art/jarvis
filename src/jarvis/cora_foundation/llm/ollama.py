"""OllamaProvider — first real LLMAdapter (offline-first · no API key).

Talks to local Ollama HTTP API (/api/chat). Default base: http://127.0.0.1:11434
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any

from .capabilities import CAPABILITY_OLLAMA_DEFAULT, ModelCapability
from .contracts import LLMRequest, LLMResponse

DEFAULT_BASE_URL = "http://127.0.0.1:11434"
DEFAULT_MODEL = "llama3.2"


class OllamaError(RuntimeError):
    """Raised when Ollama is unreachable or returns an error payload."""


class OllamaProvider:
    """Implements LLMAdapter against a local Ollama daemon."""

    provider_id = "ollama"

    def __init__(
        self,
        *,
        base_url: str = DEFAULT_BASE_URL,
        model: str = DEFAULT_MODEL,
        timeout_sec: float = 120.0,
        capability: ModelCapability | None = None,
        opener: Any | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout_sec = float(timeout_sec)
        self.capability = capability or ModelCapability(
            **{
                **CAPABILITY_OLLAMA_DEFAULT.to_dict(),
                "model_id": model,
                "provider_id": self.provider_id,
            }
        )
        # Injectable for tests (callable url, data, timeout -> bytes)
        self._opener = opener

    def complete(self, request: LLMRequest) -> LLMResponse:
        model = request.model or self.model
        messages = self._build_messages(request)
        body = {
            "model": model,
            "messages": messages,
            "stream": False,
            "options": {
                "temperature": request.temperature,
                "num_predict": request.max_tokens,
            },
        }
        raw = self._post_json("/api/chat", body)
        return self._to_response(raw, model=model, request=request)

    def ping(self) -> bool:
        """True if Ollama tags endpoint responds."""
        try:
            self._get_json("/api/tags")
            return True
        except OllamaError:
            return False

    def _build_messages(self, request: LLMRequest) -> list[dict[str, str]]:
        out: list[dict[str, str]] = []
        if request.system_prompt:
            out.append({"role": "system", "content": request.system_prompt})
        for msg in request.messages:
            role = str(msg.get("role") or "user")
            content = str(msg.get("content") or "")
            out.append({"role": role, "content": content})
        if not out:
            out.append({"role": "user", "content": ""})
        return out

    def _to_response(
        self,
        raw: dict[str, Any],
        *,
        model: str,
        request: LLMRequest,
    ) -> LLMResponse:
        if raw.get("error"):
            raise OllamaError(str(raw["error"]))
        message = raw.get("message") or {}
        text = str(message.get("content") or "")
        prompt_eval = int(raw.get("prompt_eval_count") or 0)
        eval_count = int(raw.get("eval_count") or 0)
        done_reason = str(raw.get("done_reason") or ("stop" if raw.get("done") else "unknown"))
        return LLMResponse(
            text=text,
            finish_reason=done_reason,
            usage={
                "prompt_tokens": prompt_eval,
                "completion_tokens": eval_count,
                "total_tokens": prompt_eval + eval_count,
            },
            tool_calls=(),
            model=str(raw.get("model") or model),
            provider=self.provider_id,
            metadata={
                "adapter": "OllamaProvider",
                "base_url": self.base_url,
                "request_model": request.model,
            },
        )

    def _post_json(self, path: str, body: dict[str, Any]) -> dict[str, Any]:
        data = json.dumps(body).encode("utf-8")
        url = f"{self.base_url}{path}"
        if self._opener is not None:
            raw_bytes = self._opener(url, data, self.timeout_sec)
            return json.loads(raw_bytes.decode("utf-8"))
        req = urllib.request.Request(
            url,
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout_sec) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise OllamaError(f"HTTP {exc.code}: {detail}") from exc
        except urllib.error.URLError as exc:
            raise OllamaError(f"Ollama unreachable at {self.base_url}: {exc.reason}") from exc

    def _get_json(self, path: str) -> dict[str, Any]:
        url = f"{self.base_url}{path}"
        if self._opener is not None:
            # opener for tests is POST-oriented; GET ping uses urllib unless opener returns tags
            raw_bytes = self._opener(url, None, self.timeout_sec)
            return json.loads(raw_bytes.decode("utf-8"))
        req = urllib.request.Request(url, method="GET")
        try:
            with urllib.request.urlopen(req, timeout=self.timeout_sec) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.URLError as exc:
            raise OllamaError(f"Ollama unreachable at {self.base_url}: {exc.reason}") from exc
