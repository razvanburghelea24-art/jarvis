"""Railway transport — injectable; default mock never hits Railway API."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Protocol
from uuid import uuid4


@dataclass(frozen=True)
class RailwayTransportResult:
    ok: bool
    external_id: str | None = None
    data: Mapping[str, Any] | None = None
    error: str | None = None


class RailwayTransport(Protocol):
    def project_status(
        self, *, project_id: str, payload: Mapping[str, Any]
    ) -> RailwayTransportResult: ...

    def service_status(
        self, *, project_id: str, service_id: str, payload: Mapping[str, Any]
    ) -> RailwayTransportResult: ...

    def deployment_status(
        self, *, project_id: str, service_id: str, payload: Mapping[str, Any]
    ) -> RailwayTransportResult: ...

    def list_services(
        self, *, project_id: str, payload: Mapping[str, Any]
    ) -> RailwayTransportResult: ...

    def list_deployments(
        self, *, project_id: str, service_id: str, payload: Mapping[str, Any]
    ) -> RailwayTransportResult: ...

    def logs(
        self, *, project_id: str, service_id: str, payload: Mapping[str, Any]
    ) -> RailwayTransportResult: ...

    def environment_info(
        self, *, project_id: str, payload: Mapping[str, Any]
    ) -> RailwayTransportResult: ...

    def deploy(
        self, *, project_id: str, service_id: str, payload: Mapping[str, Any]
    ) -> RailwayTransportResult: ...

    def restart_service(
        self, *, project_id: str, service_id: str, payload: Mapping[str, Any]
    ) -> RailwayTransportResult: ...

    def rollback(
        self, *, project_id: str, service_id: str, payload: Mapping[str, Any]
    ) -> RailwayTransportResult: ...

    def set_variable(
        self, *, project_id: str, service_id: str, payload: Mapping[str, Any]
    ) -> RailwayTransportResult: ...

    def delete_variable(
        self, *, project_id: str, service_id: str, payload: Mapping[str, Any]
    ) -> RailwayTransportResult: ...


class MockRailwayTransport:
    """Deterministic in-memory Railway — live=False always."""

    live = False

    def project_status(
        self, *, project_id: str, payload: Mapping[str, Any]
    ) -> RailwayTransportResult:
        return RailwayTransportResult(
            ok=True,
            external_id=project_id,
            data={"project_id": project_id, "status": "healthy", "live": False},
        )

    def service_status(
        self, *, project_id: str, service_id: str, payload: Mapping[str, Any]
    ) -> RailwayTransportResult:
        return RailwayTransportResult(
            ok=True,
            external_id=service_id,
            data={
                "project_id": project_id,
                "service_id": service_id,
                "status": "running",
                "live": False,
            },
        )

    def deployment_status(
        self, *, project_id: str, service_id: str, payload: Mapping[str, Any]
    ) -> RailwayTransportResult:
        dep = str(payload.get("deployment_id") or f"dep_{uuid4().hex[:8]}")
        return RailwayTransportResult(
            ok=True,
            external_id=dep,
            data={
                "project_id": project_id,
                "service_id": service_id,
                "deployment_id": dep,
                "status": "SUCCESS",
                "live": False,
            },
        )

    def list_services(
        self, *, project_id: str, payload: Mapping[str, Any]
    ) -> RailwayTransportResult:
        return RailwayTransportResult(
            ok=True,
            external_id=project_id,
            data={
                "project_id": project_id,
                "services": [{"id": "svc_web", "name": "web"}, {"id": "svc_worker", "name": "worker"}],
                "live": False,
            },
        )

    def list_deployments(
        self, *, project_id: str, service_id: str, payload: Mapping[str, Any]
    ) -> RailwayTransportResult:
        return RailwayTransportResult(
            ok=True,
            external_id=service_id,
            data={
                "project_id": project_id,
                "service_id": service_id,
                "deployments": [{"id": "dep_1", "status": "SUCCESS"}],
                "live": False,
            },
        )

    def logs(
        self, *, project_id: str, service_id: str, payload: Mapping[str, Any]
    ) -> RailwayTransportResult:
        return RailwayTransportResult(
            ok=True,
            external_id=service_id,
            data={
                "project_id": project_id,
                "service_id": service_id,
                "lines": ["[mock] boot ok", "[mock] listening"],
                "live": False,
            },
        )

    def environment_info(
        self, *, project_id: str, payload: Mapping[str, Any]
    ) -> RailwayTransportResult:
        return RailwayTransportResult(
            ok=True,
            external_id=project_id,
            data={"project_id": project_id, "env": "production", "vars_count": 0, "live": False},
        )

    def deploy(
        self, *, project_id: str, service_id: str, payload: Mapping[str, Any]
    ) -> RailwayTransportResult:
        dep = f"dep_{uuid4().hex[:10]}"
        return RailwayTransportResult(
            ok=True,
            external_id=dep,
            data={
                "project_id": project_id,
                "service_id": service_id,
                "deployment_id": dep,
                "action": "deploy",
                "live": False,
            },
        )

    def restart_service(
        self, *, project_id: str, service_id: str, payload: Mapping[str, Any]
    ) -> RailwayTransportResult:
        return RailwayTransportResult(
            ok=True,
            external_id=service_id,
            data={
                "project_id": project_id,
                "service_id": service_id,
                "action": "restart",
                "live": False,
            },
        )

    def rollback(
        self, *, project_id: str, service_id: str, payload: Mapping[str, Any]
    ) -> RailwayTransportResult:
        target = str(payload.get("deployment_id") or "dep_prev")
        return RailwayTransportResult(
            ok=True,
            external_id=target,
            data={
                "project_id": project_id,
                "service_id": service_id,
                "deployment_id": target,
                "action": "rollback",
                "live": False,
            },
        )

    def set_variable(
        self, *, project_id: str, service_id: str, payload: Mapping[str, Any]
    ) -> RailwayTransportResult:
        key = str(payload.get("key") or "").strip()
        if not key:
            return RailwayTransportResult(ok=False, error="missing_key")
        return RailwayTransportResult(
            ok=True,
            external_id=key,
            data={
                "project_id": project_id,
                "service_id": service_id,
                "key": key,
                "action": "set_variable",
                "live": False,
            },
        )

    def delete_variable(
        self, *, project_id: str, service_id: str, payload: Mapping[str, Any]
    ) -> RailwayTransportResult:
        key = str(payload.get("key") or "").strip()
        if not key:
            return RailwayTransportResult(ok=False, error="missing_key")
        return RailwayTransportResult(
            ok=True,
            external_id=key,
            data={
                "project_id": project_id,
                "service_id": service_id,
                "key": key,
                "action": "delete_variable",
                "live": False,
            },
        )
