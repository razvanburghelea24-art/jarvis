"""RequestValidator — ConversationRequest schema gate (contracts only).

Accepts: schema family/version, required fields, data types.
Rejects: missing fields, wrong family, unknown version, invalid types/JSON.
Does NOT validate Workspace existence, Memory, Planner, permissions, or tools.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Mapping

from ..contracts import ConversationRequest, ValidationError, validate_request
from ..contracts.schema import KIND_REQUEST, SCHEMA_FAMILY, SCHEMA_VERSION

ERROR_MISSING_FIELD = "MISSING_FIELD"
ERROR_WRONG_FAMILY = "WRONG_FAMILY"
ERROR_UNKNOWN_VERSION = "UNKNOWN_VERSION"
ERROR_WRONG_KIND = "WRONG_KIND"
ERROR_INVALID_TYPE = "INVALID_TYPE"
ERROR_INVALID_JSON = "INVALID_JSON"
ERROR_INVALID_REQUEST = "INVALID_REQUEST"


@dataclass(frozen=True)
class RequestValidationError(Exception):
    code: str
    message: str
    field: str | None = None

    def __str__(self) -> str:
        return f"{self.code}: {self.message}"

    def to_dict(self) -> dict[str, Any]:
        return {"code": self.code, "message": self.message, "field": self.field}


@dataclass(frozen=True)
class RequestValidationResult:
    ok: bool
    request: ConversationRequest | None
    errors: tuple[RequestValidationError, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "request": self.request.to_canonical_dict() if self.request else None,
            "errors": [e.to_dict() for e in self.errors],
        }


def _map_error(exc: Exception) -> RequestValidationError:
    msg = str(exc)
    low = msg.lower()
    if "schema_family" in low:
        return RequestValidationError(ERROR_WRONG_FAMILY, msg, field="schema_family")
    if "schema_version" in low:
        return RequestValidationError(ERROR_UNKNOWN_VERSION, msg, field="schema_version")
    if "kind must" in low or "expected ConversationRequest" in msg or "expected cora" in low:
        return RequestValidationError(ERROR_WRONG_KIND, msg, field="kind")
    if "must be a boolean" in low or "must be a string" in low or "must be an object" in low:
        field = None
        for name in ("barge_in", "input", "metadata", "request_id", "session_id", "workspace_id"):
            if name in low:
                field = name
                break
        return RequestValidationError(ERROR_INVALID_TYPE, msg, field=field)
    if "required" in low or "non-empty" in low or "workspace_missing" in low:
        field = None
        for name in ("request_id", "session_id", "workspace_id", "input"):
            if name in low:
                field = name
                break
        return RequestValidationError(ERROR_MISSING_FIELD, msg, field=field)
    return RequestValidationError(ERROR_INVALID_REQUEST, msg)


class RequestValidator:
    """Validate ConversationRequest before context/decision. Contracts only."""

    def check(
        self,
        request: Mapping[str, Any] | ConversationRequest | str | bytes | None,
    ) -> RequestValidationResult:
        """PASS/FAIL with standardized errors — never raises for validation failures."""
        try:
            raw = self._normalize_input(request)
        except RequestValidationError as err:
            return RequestValidationResult(ok=False, request=None, errors=(err,))
        except Exception as exc:  # noqa: BLE001
            return RequestValidationResult(
                ok=False,
                request=None,
                errors=(RequestValidationError(ERROR_INVALID_REQUEST, str(exc)),),
            )

        # Explicit family/version/kind gates when envelope present
        pre = self._precheck_envelope(raw)
        if pre is not None:
            return RequestValidationResult(ok=False, request=None, errors=(pre,))

        try:
            validated = validate_request(raw)
            return RequestValidationResult(ok=True, request=validated, errors=())
        except (ValidationError, ValueError, TypeError) as exc:
            return RequestValidationResult(ok=False, request=None, errors=(_map_error(exc),))

    def validate(
        self,
        request: Mapping[str, Any] | ConversationRequest | str | bytes | None,
    ) -> ConversationRequest:
        """Spine entry — returns request or raises ValidationError."""
        result = self.check(request)
        if result.ok and result.request is not None:
            return result.request
        detail = "; ".join(f"{e.code}:{e.message}" for e in result.errors) or "invalid request"
        raise ValidationError(detail)

    def _normalize_input(
        self,
        request: Mapping[str, Any] | ConversationRequest | str | bytes | None,
    ) -> dict[str, Any]:
        if request is None:
            raise RequestValidationError(ERROR_MISSING_FIELD, "missing ConversationRequest body", field=None)
        if isinstance(request, ConversationRequest):
            return request.to_canonical_dict()
        if isinstance(request, (str, bytes)):
            try:
                data = json.loads(request)
            except json.JSONDecodeError as exc:
                raise RequestValidationError(ERROR_INVALID_JSON, f"invalid JSON: {exc}") from exc
            if not isinstance(data, dict):
                raise RequestValidationError(ERROR_INVALID_TYPE, "JSON root must be an object")
            return data
        if not isinstance(request, Mapping):
            raise RequestValidationError(ERROR_INVALID_TYPE, "request must be an object or JSON string")
        raw = dict(request)
        if "schema_family" not in raw:
            raw = {
                "schema_family": SCHEMA_FAMILY,
                "schema_version": SCHEMA_VERSION,
                "kind": KIND_REQUEST,
                **raw,
            }
        return raw

    def _precheck_envelope(self, raw: Mapping[str, Any]) -> RequestValidationError | None:
        if "schema_family" in raw and raw.get("schema_family") != SCHEMA_FAMILY:
            return RequestValidationError(
                ERROR_WRONG_FAMILY,
                f"schema_family must be {SCHEMA_FAMILY!r}",
                field="schema_family",
            )
        if "schema_version" in raw and raw.get("schema_version") != SCHEMA_VERSION:
            return RequestValidationError(
                ERROR_UNKNOWN_VERSION,
                f"schema_version must be {SCHEMA_VERSION}",
                field="schema_version",
            )
        if "kind" in raw and raw.get("kind") != KIND_REQUEST:
            return RequestValidationError(
                ERROR_WRONG_KIND,
                f"kind must be {KIND_REQUEST!r}",
                field="kind",
            )
        return None
