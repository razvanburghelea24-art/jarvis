"""n8n transport — injectable; default mock never hits n8n API."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Protocol
from uuid import uuid4


@dataclass(frozen=True)
class N8NTransportResult:
    ok: bool
    external_id: str | None = None
    data: Mapping[str, Any] | None = None
    error: str | None = None


class N8NTransport(Protocol):
    def workflow_status(
        self, *, workflow_id: str, payload: Mapping[str, Any]
    ) -> N8NTransportResult: ...

    def list_workflows(self, *, payload: Mapping[str, Any]) -> N8NTransportResult: ...

    def execution_status(
        self, *, workflow_id: str, payload: Mapping[str, Any]
    ) -> N8NTransportResult: ...

    def execution_logs(
        self, *, workflow_id: str, payload: Mapping[str, Any]
    ) -> N8NTransportResult: ...

    def workflow_info(
        self, *, workflow_id: str, payload: Mapping[str, Any]
    ) -> N8NTransportResult: ...

    def execute_workflow(
        self, *, workflow_id: str, payload: Mapping[str, Any]
    ) -> N8NTransportResult: ...

    def activate_workflow(
        self, *, workflow_id: str, payload: Mapping[str, Any]
    ) -> N8NTransportResult: ...

    def deactivate_workflow(
        self, *, workflow_id: str, payload: Mapping[str, Any]
    ) -> N8NTransportResult: ...

    def cancel_execution(
        self, *, workflow_id: str, payload: Mapping[str, Any]
    ) -> N8NTransportResult: ...


class MockN8NTransport:
    """Deterministic in-memory n8n — live=False always."""

    live = False

    def workflow_status(
        self, *, workflow_id: str, payload: Mapping[str, Any]
    ) -> N8NTransportResult:
        return N8NTransportResult(
            ok=True,
            external_id=workflow_id,
            data={"workflow_id": workflow_id, "active": True, "live": False},
        )

    def list_workflows(self, *, payload: Mapping[str, Any]) -> N8NTransportResult:
        return N8NTransportResult(
            ok=True,
            external_id="n8n",
            data={
                "workflows": [
                    {"id": "wf_1", "name": "Notify Discord"},
                    {"id": "wf_2", "name": "Deploy Hook"},
                ],
                "live": False,
            },
        )

    def execution_status(
        self, *, workflow_id: str, payload: Mapping[str, Any]
    ) -> N8NTransportResult:
        eid = str(payload.get("execution_id") or f"ex_{uuid4().hex[:8]}")
        return N8NTransportResult(
            ok=True,
            external_id=eid,
            data={
                "workflow_id": workflow_id,
                "execution_id": eid,
                "status": "success",
                "live": False,
            },
        )

    def execution_logs(
        self, *, workflow_id: str, payload: Mapping[str, Any]
    ) -> N8NTransportResult:
        eid = str(payload.get("execution_id") or "ex_stub")
        return N8NTransportResult(
            ok=True,
            external_id=eid,
            data={
                "workflow_id": workflow_id,
                "execution_id": eid,
                "lines": ["[mock] start", "[mock] done"],
                "live": False,
            },
        )

    def workflow_info(
        self, *, workflow_id: str, payload: Mapping[str, Any]
    ) -> N8NTransportResult:
        return N8NTransportResult(
            ok=True,
            external_id=workflow_id,
            data={"workflow_id": workflow_id, "name": f"wf-{workflow_id}", "live": False},
        )

    def execute_workflow(
        self, *, workflow_id: str, payload: Mapping[str, Any]
    ) -> N8NTransportResult:
        eid = f"ex_{uuid4().hex[:10]}"
        return N8NTransportResult(
            ok=True,
            external_id=eid,
            data={
                "workflow_id": workflow_id,
                "execution_id": eid,
                "action": "execute",
                "live": False,
            },
        )

    def activate_workflow(
        self, *, workflow_id: str, payload: Mapping[str, Any]
    ) -> N8NTransportResult:
        return N8NTransportResult(
            ok=True,
            external_id=workflow_id,
            data={"workflow_id": workflow_id, "active": True, "action": "activate", "live": False},
        )

    def deactivate_workflow(
        self, *, workflow_id: str, payload: Mapping[str, Any]
    ) -> N8NTransportResult:
        return N8NTransportResult(
            ok=True,
            external_id=workflow_id,
            data={
                "workflow_id": workflow_id,
                "active": False,
                "action": "deactivate",
                "live": False,
            },
        )

    def cancel_execution(
        self, *, workflow_id: str, payload: Mapping[str, Any]
    ) -> N8NTransportResult:
        eid = str(payload.get("execution_id") or "").strip()
        if not eid:
            return N8NTransportResult(ok=False, error="missing_execution_id")
        return N8NTransportResult(
            ok=True,
            external_id=eid,
            data={
                "workflow_id": workflow_id,
                "execution_id": eid,
                "action": "cancel",
                "live": False,
            },
        )
