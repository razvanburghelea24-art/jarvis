"""Secret redaction for audit payloads — never store secrets."""

from __future__ import annotations

import re
from typing import Any

_REDACTED = "[REDACTED]"

_SECRET_KEY_RE = re.compile(
    r"(token|password|passwd|secret|api[_-]?key|authorization|bearer|private[_-]?key|credential)",
    re.IGNORECASE,
)

_SECRET_VALUE_RE = re.compile(
    r"(?i)\b(bearer\s+[a-z0-9\-._~+/]+=*|sk-[a-z0-9]{10,}|ghp_[a-z0-9]{20,}|xox[baprs]-[a-z0-9-]{10,})\b"
)


def redact_value(value: Any) -> Any:
    """Recursively redact secret-shaped keys/values. Audit-only helper — no auth logic."""
    if isinstance(value, dict):
        out: dict[str, Any] = {}
        for k, v in value.items():
            if _SECRET_KEY_RE.search(str(k)):
                out[str(k)] = _REDACTED
            else:
                out[str(k)] = redact_value(v)
        return out
    if isinstance(value, list):
        return [redact_value(v) for v in value]
    if isinstance(value, str):
        if _SECRET_VALUE_RE.search(value):
            return _SECRET_VALUE_RE.sub(_REDACTED, value)
        return value
    return value
