"""Cora Foundation — Phase 1C Command Gateway.

Single command entry. Gateway does not execute business logic.
Default OFF. No live Discord/Overlay/n8n/GitHub integrations.
"""

from .capabilities import CapabilityRegistry, default_capability_registry
from .conversation_accept import ConversationAcceptResult, accept_conversation_request
from .dispatcher import CapabilityDispatcher, DispatchResult
from .flags import ENV_ENABLED, gateway_enabled_from_env
from .gateway import CommandGateway, get_command_gateway, reset_command_gateway_for_tests
from .intent import IntentEngine
from .policy import PolicyDecisionKind, PolicyEngine
from .types import CommandEnvelope, ExecutionPlan, Intent, NormalizedCommand, RiskLevel, SourceChannel

__all__ = [
    "ENV_ENABLED",
    "CapabilityDispatcher",
    "CapabilityRegistry",
    "CommandEnvelope",
    "CommandGateway",
    "ConversationAcceptResult",
    "DispatchResult",
    "ExecutionPlan",
    "Intent",
    "IntentEngine",
    "NormalizedCommand",
    "PolicyDecisionKind",
    "PolicyEngine",
    "RiskLevel",
    "SourceChannel",
    "accept_conversation_request",
    "default_capability_registry",
    "gateway_enabled_from_env",
    "get_command_gateway",
    "reset_command_gateway_for_tests",
]
