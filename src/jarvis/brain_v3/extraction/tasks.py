"""Task extraction heuristics."""

from __future__ import annotations

import re
from typing import Optional

_PATTERNS = (
    re.compile(r"\b(?:implement|implementation)\b.+", re.IGNORECASE),
    re.compile(r"\b(?:test|testing|verify)\b.+", re.IGNORECASE),
    re.compile(r"\b(?:fix|repair|resolve)\b.+", re.IGNORECASE),
    re.compile(r"\b(?:todo|task|next step)\b.+", re.IGNORECASE),
)


def match_task(text: str) -> Optional[str]:
    stripped = (text or "").strip()
    if not stripped:
        return None
    for pattern in _PATTERNS:
        match = pattern.search(stripped)
        if match:
            return match.group(0).strip()
    return None
