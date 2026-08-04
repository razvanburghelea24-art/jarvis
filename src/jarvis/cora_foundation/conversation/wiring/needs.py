"""Derive RouteNeeds from ActiveWorkspaceContext / ConversationContext (wiring only)."""

from __future__ import annotations

from typing import Any, Mapping

from ...llm import RouteNeeds
from ...workspace import WorkspaceEngine
from ..contracts import ConversationContext


def route_needs_from_context(
    context: ConversationContext,
    workspace: WorkspaceEngine,
) -> RouteNeeds:
    """
    Map workspace identity → capability needs.

    No vendor names. Router matches capabilities.
    """
    active = workspace.get_context(context.session_id)
    ws_type = (active.workspace_type if active else "general").lower()
    preferred = (active.preferred_provider if active else None) or ""
    meta: Mapping[str, Any] = dict(context.conversation.get("metadata") or {})

    # Explicit offline hint from request metadata or preferred offline provider
    if meta.get("require_offline") or preferred == "ollama" or ws_type in {"casual", "offline"}:
        return RouteNeeds(require_offline=True, reasoning=6, speed=5)

    if ws_type in {"coding", "code", "dev"}:
        return RouteNeeds(coding=9, reasoning=8)

    if ws_type in {"analysis", "deep", "research"}:
        return RouteNeeds(reasoning=8, creativity=6, context_window=7)

    # General chat — let router score speed/cost/reasoning
    return RouteNeeds()
