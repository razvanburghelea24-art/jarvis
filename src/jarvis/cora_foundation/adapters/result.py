"""Adapter execution result — sole output of live adapters (not dispatcher.DispatchResult).

Owner contract shape (adapter DispatchResult):
  status · request_id · adapter · operation · external_id · duration · error · metadata

States only: READY → RUNNING → SUCCESS | FAILED
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Mapping
from uuid import uuid4

from ..conversation.contracts.schema import freeze_mapping

SCHEMA_FAMILY = "cora.adapter.contracts"
SCHEMA_VERSION = 1
KIND_RESULT = "AdapterResult"


class AdapterStatus(str, Enum):
    READY = "ready"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"


@dataclass(frozen=True)
class AdapterResult:
    """Final result of executing one DispatchRequest via an adapter."""

    status: AdapterStatus
    request_id: str
    adapter: str
    operation: str
    external_id: str | None = None
    duration: float = 0.0
    error: str | None = None
    metadata: Mapping[str, Any] = None  # type: ignore[assignment]
    result_id: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "metadata", freeze_mapping(self.metadata))
        if isinstance(self.status, str):
            object.__setattr__(self, "status", AdapterStatus(self.status))
        object.__setattr__(self, "duration", float(self.duration))
        if not self.result_id:
            object.__setattr__(self, "result_id", f"ares_{uuid4().hex[:12]}")

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "schema_family": SCHEMA_FAMILY,
            "schema_version": SCHEMA_VERSION,
            "kind": KIND_RESULT,
            "result_id": self.result_id,
            "status": self.status.value,
            "request_id": self.request_id,
            "adapter": self.adapter,
            "operation": self.operation,
            "external_id": self.external_id,
            "duration": self.duration,
            "error": self.error,
            "metadata": dict(self.metadata),
        }
