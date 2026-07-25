"""Secret detection and redaction for conversation content."""

from __future__ import annotations

import re
from typing import Tuple

_SECRET_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b"), "[REDACTED_AWS_KEY]"),
    (re.compile(r"\b(?:sk|pk|rk)_(?:live|test)_[A-Za-z0-9]{16,}\b"), "[REDACTED_STRIPE_KEY]"),
    (re.compile(r"\bgh[pousr]_[A-Za-z0-9]{36,}\b"), "[REDACTED_GH_TOKEN]"),
    (re.compile(r"\bsk-[A-Za-z0-9]{32,}\b"), "[REDACTED_OPENAI_KEY]"),
    (re.compile(r"\bAIza[0-9A-Za-z_\-]{20,}\b"), "[REDACTED_GOOG_KEY]"),
    (re.compile(r"Authorization:\s*Bearer\s+\S+", re.IGNORECASE), "Authorization: Bearer [REDACTED]"),
    (re.compile(r"\bBearer\s+[A-Za-z0-9._\-+/=]{16,}\b", re.IGNORECASE), "Bearer [REDACTED]"),
    (
        re.compile(
            r"\b(?:pass(?:word)?|secret|token|api[_-]?key|private[_-]?key|"
            r"(?:refresh|access|session)[_-]?token)\s*[:=]\s*\S+\b",
            re.IGNORECASE,
        ),
        "[REDACTED_SECRET]",
    ),
    (
        re.compile(
            r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----[\s\S]+?"
            r"-----END (?:RSA |EC |OPENSSH )?PRIVATE KEY-----",
            re.IGNORECASE,
        ),
        "[REDACTED_PRIVATE_KEY]",
    ),
    (re.compile(r"\b(?:eyJ[0-9A-Za-z._\-]+)\b"), "[REDACTED_JWT]"),
]


def redact_secrets(text: str) -> Tuple[str, bool]:
    """Return redacted text and whether secret-like content was detected."""
    if not text:
        return "", False
    blocked = False
    redacted = text
    for pattern, repl in _SECRET_PATTERNS:
        if pattern.search(redacted):
            blocked = True
            redacted = pattern.sub(repl, redacted)
    return redacted, blocked
