"""Decision extraction heuristics."""

from __future__ import annotations

import re
from typing import Optional

_PATTERNS = (
    re.compile(r"\b(?:decided|decision|we decided)\b.+", re.IGNORECASE),
    re.compile(r"\b(?:rămâne|ramane|remains?)\b.+", re.IGNORECASE),
    re.compile(r"\b(?:nu activa|do not activate|must stay off|will remain off)\b.+", re.IGNORECASE),
    re.compile(r"\b(?:single[- ]writer|approval[- ]gated)\b.+", re.IGNORECASE),
)


def match_decision(text: str) -> Optional[str]:
    stripped = (text or "").strip()
    if not stripped:
        return None
    for pattern in _PATTERNS:
        match = pattern.search(stripped)
        if match:
            return match.group(0).strip()
    return None
