"""ContextBuilder — extension point (skeleton).

Will assemble ConversationContext windows. No Memory/LLM I/O yet.
"""

from __future__ import annotations

from ..contracts import ConversationContext, ConversationRequest
from ._skeleton import SkeletonNotImplemented


class ContextBuilder:
    """Build ConversationContext from Conversation + Workspace + Core + Runtime."""

    def build(self, request: ConversationRequest) -> ConversationContext:
        # TODO: Conversation / Workspace / Core / Runtime windows
        raise SkeletonNotImplemented("TODO: ContextBuilder.build")
