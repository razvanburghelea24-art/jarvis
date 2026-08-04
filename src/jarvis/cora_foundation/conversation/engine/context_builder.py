"""ContextBuilder — assemble ConversationContext from injectable providers.

Single responsibility: ConversationRequest → ConversationContext.
Does not decide, respond, plan, emit state, or call external APIs.
"""

from __future__ import annotations

from typing import Any, Mapping

from ..contracts import ConversationContext, ConversationRequest
from .context_providers import (
    DEFAULT_LIMITS,
    ContextProvider,
    StubConversationMemoryProvider,
    StubCoreMemoryProvider,
    StubRuntimeSnapshotProvider,
    StubWorkspaceProvider,
)


class ContextBuilder:
    """
    Compose context windows via ContextProvider (stubs now; real stores later).

    v1 ConversationContext windows:
      conversation ← request echo + conversation_memory + limits + metadata
      workspace    ← active_workspace + workspace_memory
      core         ← core_memory
      runtime      ← runtime_snapshot
    """

    def __init__(
        self,
        *,
        conversation_memory: ContextProvider | None = None,
        workspace: ContextProvider | None = None,
        core_memory: ContextProvider | None = None,
        runtime_snapshot: ContextProvider | None = None,
        limits: Mapping[str, Any] | None = None,
    ) -> None:
        self.conversation_memory = conversation_memory or StubConversationMemoryProvider()
        self.workspace = workspace or StubWorkspaceProvider()
        self.core_memory = core_memory or StubCoreMemoryProvider()
        self.runtime_snapshot = runtime_snapshot or StubRuntimeSnapshotProvider()
        self.limits = dict(limits or DEFAULT_LIMITS)

    def build(self, request: ConversationRequest) -> ConversationContext:
        # Read-only composition — never mutate request
        conv_mem = dict(self.conversation_memory.fetch(request))
        ws = dict(self.workspace.fetch(request))
        core_mem = dict(self.core_memory.fetch(request))
        runtime = dict(self.runtime_snapshot.fetch(request))

        conversation_window: dict[str, Any] = {
            "request": {
                "request_id": request.request_id,
                "session_id": request.session_id,
                "workspace_id": request.workspace_id,
                "input": request.input,
                "barge_in": request.barge_in,
                "resume_of": request.resume_of,
                "client_at": request.client_at,
            },
            "memory": conv_mem,
            "limits": dict(self.limits),
            "metadata": dict(request.metadata),
        }

        workspace_window: dict[str, Any] = {
            "active": dict(ws.get("active") or {"workspace_id": request.workspace_id}),
            "memory": dict(ws.get("memory") or {}),
        }

        core_window: dict[str, Any] = {
            "memory": core_mem,
        }

        runtime_window: dict[str, Any] = {
            "snapshot": runtime,
        }

        return ConversationContext(
            request_id=request.request_id,
            session_id=request.session_id,
            workspace_id=request.workspace_id,
            conversation=conversation_window,
            workspace=workspace_window,
            core=core_window,
            runtime=runtime_window,
            sealed=True,
        )
