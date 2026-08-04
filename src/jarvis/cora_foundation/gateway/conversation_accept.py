"""Gateway Accept — ConversationRequest validation only.

Flow:
  ConversationRequest → Schema Validator → PASS/FAIL → Audit → STOP

No Planner, Engine, LLM, Tool Routing, or Memory writes.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Mapping

from ..conversation.contracts import ConversationRequest, ValidationError, validate_request
from .audit_hooks import AuditJournal


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


HTTP_OK = 200
HTTP_BAD_REQUEST = 400
CODE_OK = "OK"
CODE_INVALID = "INVALID_REQUEST"


@dataclass(frozen=True)
class ConversationAcceptResult:
    """Transport-layer accept result (not an Engine decision)."""

    ok: bool
    status_code: int
    code: str
    message: str
    request: ConversationRequest | None
    errors: tuple[str, ...]
    audited: bool
    at: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "status_code": self.status_code,
            "code": self.code,
            "message": self.message,
            "request": self.request.to_canonical_dict() if self.request else None,
            "errors": list(self.errors),
            "audited": self.audited,
            "at": self.at,
        }


def accept_conversation_request(
    payload: Mapping[str, Any] | ConversationRequest | None,
    *,
    audit: AuditJournal | None = None,
) -> ConversationAcceptResult:
    """
    Validate ConversationRequest and audit the outcome. Stops immediately after.
    Does not call Planner / Engine / LLM / tools / Memory.
    """
    at = _now()
    request_id = "unknown"
    workspace_id = None
    session_id = None

    if payload is None:
        result = ConversationAcceptResult(
            ok=False,
            status_code=HTTP_BAD_REQUEST,
            code=CODE_INVALID,
            message="missing ConversationRequest body",
            request=None,
            errors=("missing body",),
            audited=False,
            at=at,
        )
        _audit(audit, result, request_id=request_id, workspace_id=workspace_id, session_id=session_id)
        return result

    try:
        if isinstance(payload, ConversationRequest):
            raw = payload.to_canonical_dict()
        else:
            raw = dict(payload)
        request_id = str(raw.get("request_id") or request_id)
        workspace_id = raw.get("workspace_id")
        session_id = raw.get("session_id")
        # Ensure envelope for validator when client sends bare fields
        if "schema_family" not in raw:
            raw = {
                "schema_family": "cora.conversation.contracts",
                "schema_version": 1,
                "kind": "ConversationRequest",
                **raw,
            }
        validated = validate_request(raw)
        result = ConversationAcceptResult(
            ok=True,
            status_code=HTTP_OK,
            code=CODE_OK,
            message="ConversationRequest accepted (validate-only; Engine not invoked)",
            request=validated,
            errors=(),
            audited=False,
            at=at,
        )
        audited = _audit(
            audit,
            result,
            request_id=validated.request_id,
            workspace_id=validated.workspace_id,
            session_id=validated.session_id,
        )
        return ConversationAcceptResult(
            ok=result.ok,
            status_code=result.status_code,
            code=result.code,
            message=result.message,
            request=result.request,
            errors=result.errors,
            audited=audited,
            at=result.at,
        )
    except (ValidationError, ValueError, TypeError) as exc:
        result = ConversationAcceptResult(
            ok=False,
            status_code=HTTP_BAD_REQUEST,
            code=CODE_INVALID,
            message=str(exc),
            request=None,
            errors=(str(exc),),
            audited=False,
            at=at,
        )
        audited = _audit(
            audit,
            result,
            request_id=request_id,
            workspace_id=str(workspace_id) if workspace_id else None,
            session_id=str(session_id) if session_id else None,
        )
        return ConversationAcceptResult(
            ok=result.ok,
            status_code=result.status_code,
            code=result.code,
            message=result.message,
            request=None,
            errors=result.errors,
            audited=audited,
            at=result.at,
        )


def _audit(
    audit: AuditJournal | None,
    result: ConversationAcceptResult,
    *,
    request_id: str,
    workspace_id: str | None,
    session_id: str | None,
) -> bool:
    if audit is None:
        return False
    audit.emit(
        AuditJournal.REQUEST_RECEIVED,
        request_id,
        workspace_id=workspace_id,
        session_id=session_id,
        source="conversation_accept",
        status="received",
        metadata={
            "surface": "conversation_accept",
            "phase": "received",
        },
    )
    event_type = (
        AuditJournal.REQUEST_COMPLETED if result.ok else AuditJournal.REQUEST_FAILED
    )
    audit.emit(
        event_type,
        request_id,
        workspace_id=workspace_id,
        session_id=session_id,
        source="conversation_accept",
        status="ok" if result.ok else "failed",
        metadata={
            "surface": "conversation_accept",
            "status_code": result.status_code,
            "code": result.code,
            "message": result.message,
            "ok": result.ok,
            "engine_invoked": False,
            "planner_invoked": False,
            "llm_invoked": False,
            "tools_invoked": False,
        },
    )
    return True
