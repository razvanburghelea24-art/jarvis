"""Dispatcher — ToolPlan → DispatchRequest (never execute adapters).

Law:
  No Adapter without Dispatcher.
  No Dispatcher without ToolPlan.
  No ToolPlan without PlannerDecision.
"""

from .contracts import (
    ApprovalState,
    DispatchExecutionMode,
    DispatchOutcome,
    DispatchRequest,
    DispatchResult,
)
from .dispatcher import Dispatcher

__all__ = [
    "ApprovalState",
    "DispatchExecutionMode",
    "DispatchOutcome",
    "DispatchRequest",
    "DispatchResult",
    "Dispatcher",
]
