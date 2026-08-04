"""ResponseBuilder — extension point (skeleton).

Will build ConversationResponse. Streaming is LAST (not here yet).
"""

from __future__ import annotations

from ..contracts import (
    ConversationContext,
    ConversationDecision,
    ConversationRequest,
    ConversationResponse,
)
from ._skeleton import SkeletonNotImplemented


class ResponseBuilder:
    """Build ConversationResponse (non-streaming first; streaming later)."""

    def build(
        self,
        request: ConversationRequest,
        context: ConversationContext,
        decision: ConversationDecision,
    ) -> ConversationResponse:
        # TODO: synthesize response text; streaming lands after solid non-stream path
        raise SkeletonNotImplemented("TODO: ResponseBuilder.build")
