"""Cora Foundation package (1A–1E + Phase 3–6A + Snapshot 8.2 + Conversation contracts v1)."""

from . import agents
from . import audit
from . import computer_operator
from . import conversation
from . import dispatcher
from . import emergency_stop
from . import gateway
from . import identity
from . import integration
from . import llm
from . import memory
from . import orchestrator
from . import planner
from . import snapshot
from . import tool_routing
from . import workspace
from . import adapters  # after dispatcher/conversation — avoid circular import

__all__ = [
    "agents",
    "audit",
    "computer_operator",
    "conversation",
    "dispatcher",
    "emergency_stop",
    "gateway",
    "identity",
    "integration",
    "llm",
    "memory",
    "orchestrator",
    "planner",
    "snapshot",
    "tool_routing",
    "workspace",
    "adapters",
]
