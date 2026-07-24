"""Brain V3 explicit errors."""

from __future__ import annotations


class BrainV3Error(Exception):
    """Base Brain V3 error."""


class ValidationError(BrainV3Error):
    pass


class NotFoundError(BrainV3Error):
    pass


class ConflictError(BrainV3Error):
    pass


class LimitExceededError(BrainV3Error):
    pass


class SchemaError(BrainV3Error):
    pass


class DisabledError(BrainV3Error):
    pass
