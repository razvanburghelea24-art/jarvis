"""Event extraction heuristics."""

from __future__ import annotations

import re
from typing import Optional

_PATTERNS = (
    re.compile(r"\b(?:passed|passing|tests passed)\b.+", re.IGNORECASE),
    re.compile(r"\b(?:integrated|integration complete)\b.+", re.IGNORECASE),
    re.compile(r"\bHEAD\b.{0,80}", re.IGNORECASE),
    re.compile(r"\b(?:phase\s+\d+\s+(?:complete|done|integrated))\b.+", re.IGNORECASE),
    re.compile(r"\b(?:failure|failed|verdict)\b.+", re.IGNORECASE),
)


def match_event(text: str) -> Optional[str]:
    stripped = (text or "").strip()
    if not stripped:
        return None
    for pattern in _PATTERNS:
        match = pattern.search(stripped)
        if match:
            return match.group(0).strip()
    return None
