"""DecisionEngine — extension point (skeleton).

Will consult Planner (never LLM→Tool). No Planner wiring yet.
"""

from __future__ import annotations

from ..contracts import ConversationContext, ConversationDecision, ConversationRequest
from ._skeleton import SkeletonNotImplemented


class DecisionEngine:
    """Produce ConversationDecision (answer | tool | clarify | switch_workspace | refuse)."""

    def decide(
        self,
        request: ConversationRequest,
        context: ConversationContext,
    ) -> ConversationDecision:
        # TODO: Engine → Planner → Gateway → Tool (LLM synthesize optional later)
        raise SkeletonNotImplemented("TODO: DecisionEngine.decide")
