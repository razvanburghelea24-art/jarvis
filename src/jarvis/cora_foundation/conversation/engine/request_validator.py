"""RequestValidator — extension point (skeleton).

Will wrap contracts.validate_request. No business logic yet.
"""

from __future__ import annotations

from typing import Any, Mapping

from ..contracts import ConversationRequest
from ._skeleton import SkeletonNotImplemented


class RequestValidator:
    """Validate ConversationRequest before context/decision."""

    def validate(self, request: Mapping[str, Any] | ConversationRequest) -> ConversationRequest:
        # TODO: call contracts.validate_request / Gateway Accept path
        raise SkeletonNotImplemented("TODO: RequestValidator.validate")
