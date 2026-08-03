"""Read-only adapter base — translate only."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from ..types import IntegrationObject, IntegrationSource, new_object_id


class ReadOnlyAdapter(ABC):
    """Adapters must not decide, memorize, policy, AI, or write."""

    name: str
    source: IntegrationSource

    @abstractmethod
    def is_enabled(self) -> bool:
        raise NotImplementedError

    @abstractmethod
    def health(self) -> IntegrationObject:
        raise NotImplementedError

    def snapshot(self) -> list[IntegrationObject]:
        """Default read-only snapshot — subclasses append domain reads."""
        if not self.is_enabled():
            return []
        return [self.health()]

    def _obj(
        self,
        *,
        kind: str,
        title: str | None = None,
        status: str | None = None,
        refs: dict[str, str] | None = None,
        payload: dict[str, Any] | None = None,
    ) -> IntegrationObject:
        return IntegrationObject(
            object_id=new_object_id(self.source, kind),
            source=self.source,
            kind=kind,
            title=title,
            status=status,
            refs=dict(refs or {}),
            payload=dict(payload or {}),
            read_only=True,
        )
