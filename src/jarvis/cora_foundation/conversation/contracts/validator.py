"""Schema validation for conversation contracts v1.

Invalid objects never enter the Engine. This module is validation-only —
no Engine, Planner, Gateway, Desktop, Persona, or Avatar logic.
"""

from __future__ import annotations

from typing import Any, Mapping, Union

from .context import ConversationContext
from .decision import ConversationDecision, DecisionKind
from .request import ConversationRequest
from .response import ConversationResponse
from .schema import (
    KIND_CONTEXT,
    KIND_DECISION,
    KIND_REQUEST,
    KIND_RESPONSE,
    KIND_STATE,
    dumps_canonical,
    loads_canonical,
    require_v1_envelope,
)
from .state import ConversationState, ErrorClass, LifecyclePhase, PresentationHint

Contract = Union[
    ConversationRequest,
    ConversationContext,
    ConversationDecision,
    ConversationResponse,
    ConversationState,
]


class ValidationError(ValueError):
    """Raised when a conversation contract fails schema validation."""


def _require_nonempty_str(data: Mapping[str, Any], key: str) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValidationError(f"{key} must be a non-empty string")
    return value.strip()


def _optional_str(data: Mapping[str, Any], key: str) -> str | None:
    value = data.get(key)
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValidationError(f"{key} must be a string or null")
    return value


def _require_bool(data: Mapping[str, Any], key: str, default: bool = False) -> bool:
    if key not in data:
        return default
    value = data[key]
    if not isinstance(value, bool):
        raise ValidationError(f"{key} must be a boolean")
    return value


def _require_mapping(data: Mapping[str, Any], key: str) -> Mapping[str, Any]:
    if key not in data or data[key] is None:
        return {}
    value = data[key]
    if not isinstance(value, Mapping):
        raise ValidationError(f"{key} must be an object")
    return value


def validate_request(data: Mapping[str, Any] | ConversationRequest) -> ConversationRequest:
    if isinstance(data, ConversationRequest):
        data = data.to_canonical_dict()
    kind = require_v1_envelope(data) if "schema_family" in data else KIND_REQUEST
    if kind != KIND_REQUEST:
        raise ValidationError(f"expected {KIND_REQUEST}, got {kind}")

    workspace_id = data.get("workspace_id")
    if not isinstance(workspace_id, str) or not workspace_id.strip():
        raise ValidationError("workspace_id is required (workspace_missing)")

    input_text = data.get("input")
    if not isinstance(input_text, str):
        raise ValidationError("input must be a string")

    return ConversationRequest(
        request_id=_require_nonempty_str(data, "request_id"),
        session_id=_require_nonempty_str(data, "session_id"),
        workspace_id=workspace_id.strip(),
        input=input_text,
        barge_in=_require_bool(data, "barge_in", False),
        resume_of=_optional_str(data, "resume_of"),
        client_at=_optional_str(data, "client_at"),
        metadata=_require_mapping(data, "metadata"),
    )


def validate_context(data: Mapping[str, Any] | ConversationContext) -> ConversationContext:
    if isinstance(data, ConversationContext):
        data = data.to_canonical_dict()
    kind = require_v1_envelope(data) if "schema_family" in data else KIND_CONTEXT
    if kind != KIND_CONTEXT:
        raise ValidationError(f"expected {KIND_CONTEXT}, got {kind}")

    return ConversationContext(
        request_id=_require_nonempty_str(data, "request_id"),
        session_id=_require_nonempty_str(data, "session_id"),
        workspace_id=_require_nonempty_str(data, "workspace_id"),
        conversation=_require_mapping(data, "conversation"),
        workspace=_require_mapping(data, "workspace"),
        core=_require_mapping(data, "core"),
        runtime=_require_mapping(data, "runtime"),
        sealed=_require_bool(data, "sealed", False),
    )


def validate_decision(data: Mapping[str, Any] | ConversationDecision) -> ConversationDecision:
    if isinstance(data, ConversationDecision):
        data = data.to_canonical_dict()
    kind = require_v1_envelope(data) if "schema_family" in data else KIND_DECISION
    if kind != KIND_DECISION:
        raise ValidationError(f"expected {KIND_DECISION}, got {kind}")

    raw_kind = data.get("decision_kind", data.get("kind"))
    # Prefer decision_kind — envelope already uses kind=ConversationDecision
    if raw_kind in (KIND_DECISION, "ConversationDecision"):
        raise ValidationError("decision_kind is required")
    try:
        decision_kind = DecisionKind(raw_kind)
    except Exception as exc:
        raise ValidationError(f"invalid decision kind: {raw_kind!r}") from exc

    tool_intent = _require_mapping(data, "tool_intent")
    if decision_kind == DecisionKind.TOOL and not tool_intent.get("capability"):
        raise ValidationError("tool decisions require tool_intent.capability")

    reason = data.get("reason", "")
    if reason is None:
        reason = ""
    if not isinstance(reason, str):
        raise ValidationError("reason must be a string")

    return ConversationDecision(
        decision_id=_require_nonempty_str(data, "decision_id"),
        request_id=_require_nonempty_str(data, "request_id"),
        kind=decision_kind,
        workspace_id=_require_nonempty_str(data, "workspace_id"),
        planner_ref=_optional_str(data, "planner_ref"),
        tool_intent=tool_intent,
        reason=reason,
    )


def validate_response(data: Mapping[str, Any] | ConversationResponse) -> ConversationResponse:
    if isinstance(data, ConversationResponse):
        data = data.to_canonical_dict()
    kind = require_v1_envelope(data) if "schema_family" in data else KIND_RESPONSE
    if kind != KIND_RESPONSE:
        raise ValidationError(f"expected {KIND_RESPONSE}, got {kind}")

    raw_phase = data.get("phase")
    try:
        phase = LifecyclePhase(raw_phase)
    except Exception as exc:
        raise ValidationError(f"invalid response phase: {raw_phase!r}") from exc

    text = data.get("text", "")
    if text is None:
        text = ""
    if not isinstance(text, str):
        raise ValidationError("text must be a string")

    citations = data.get("citations") or []
    if not isinstance(citations, (list, tuple)) or not all(isinstance(c, str) for c in citations):
        raise ValidationError("citations must be a list of strings")

    return ConversationResponse(
        response_id=_require_nonempty_str(data, "response_id"),
        request_id=_require_nonempty_str(data, "request_id"),
        decision_id=_optional_str(data, "decision_id"),
        phase=phase,
        text=text,
        incomplete=_require_bool(data, "incomplete", False),
        tool_summary=_optional_str(data, "tool_summary"),
        citations=tuple(citations),
        metadata=_require_mapping(data, "metadata"),
    )


def validate_state(data: Mapping[str, Any] | ConversationState) -> ConversationState:
    if isinstance(data, ConversationState):
        data = data.to_canonical_dict()
    kind = require_v1_envelope(data) if "schema_family" in data else KIND_STATE
    if kind != KIND_STATE:
        raise ValidationError(f"expected {KIND_STATE}, got {kind}")

    try:
        lifecycle = LifecyclePhase(data.get("lifecycle"))
    except Exception as exc:
        raise ValidationError(f"invalid lifecycle: {data.get('lifecycle')!r}") from exc
    try:
        presentation = PresentationHint(data.get("presentation"))
    except Exception as exc:
        raise ValidationError(f"invalid presentation: {data.get('presentation')!r}") from exc

    error_raw = data.get("error_class")
    error_class: ErrorClass | None
    if error_raw is None:
        error_class = None
    else:
        try:
            error_class = ErrorClass(error_raw)
        except Exception as exc:
            raise ValidationError(f"invalid error_class: {error_raw!r}") from exc

    return ConversationState(
        session_id=_require_nonempty_str(data, "session_id"),
        request_id=_optional_str(data, "request_id"),
        workspace_id=_require_nonempty_str(data, "workspace_id"),
        lifecycle=lifecycle,
        presentation=presentation,
        error_class=error_class,
    )


def validate(data: Mapping[str, Any] | Contract) -> Contract:
    """Validate any canonical envelope or already-typed contract."""
    if isinstance(
        data,
        (
            ConversationRequest,
            ConversationContext,
            ConversationDecision,
            ConversationResponse,
            ConversationState,
        ),
    ):
        data = data.to_canonical_dict()

    try:
        kind = require_v1_envelope(data)
    except ValueError as exc:
        raise ValidationError(str(exc)) from exc

    if kind == KIND_REQUEST:
        return validate_request(data)
    if kind == KIND_CONTEXT:
        return validate_context(data)
    if kind == KIND_DECISION:
        return validate_decision(data)
    if kind == KIND_RESPONSE:
        return validate_response(data)
    if kind == KIND_STATE:
        return validate_state(data)
    raise ValidationError(f"unsupported kind: {kind}")


def to_canonical_json(obj: Contract) -> str:
    return dumps_canonical(obj.to_canonical_dict())


def from_canonical_json(raw: str | bytes) -> Contract:
    try:
        data = loads_canonical(raw)
    except Exception as exc:
        raise ValidationError(f"invalid JSON: {exc}") from exc
    return validate(data)
