"""Preference extraction heuristics."""

from __future__ import annotations

import re
from typing import Optional

_PATTERNS = (
    re.compile(r"\b(?:prefer|preference|i prefer|would rather)\b.+", re.IGNORECASE),
    re.compile(r"\b(?:vreau|nu vreau|prefer)\b.+", re.IGNORECASE),
    re.compile(r"\bmust remain off\b.+?", re.IGNORECASE),
    re.compile(r"\b(?:always|never)\b.+(?:use|want|need)\b", re.IGNORECASE),
)


def match_preference(text: str) -> Optional[str]:
    stripped = (text or "").strip()
    if not stripped:
        return None
    for pattern in _PATTERNS:
        match = pattern.search(stripped)
        if match:
            return match.group(0).strip()
    return None
