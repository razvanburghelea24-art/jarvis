"""Beta 1A — Conversation Engine Test Harness.

Fake Gateway → Skeleton with fakes → Fake Response.
No LLM · Planner · Memory · Tools · Streaming · Desktop.
"""

from .fakes import (
    FakeContextBuilder,
    FakeDecisionEngine,
    FakeRequestValidator,
    FakeResponseBuilder,
    FakeStateEmitter,
)
from .runner import ConversationHarness, HarnessResult

__all__ = [
    "ConversationHarness",
    "FakeContextBuilder",
    "FakeDecisionEngine",
    "FakeRequestValidator",
    "FakeResponseBuilder",
    "FakeStateEmitter",
    "HarnessResult",
]
