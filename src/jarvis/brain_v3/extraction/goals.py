"""Goal extraction heuristics."""

from __future__ import annotations

import re
from typing import Optional

_PATTERNS = (
    re.compile(r"\b(?:goal|objective|obiectiv)\b.+", re.IGNORECASE),
    re.compile(r"\b(?:trebuie\s+să|trebuie sa|must become|needs to become)\b.+", re.IGNORECASE),
    re.compile(r"\b(?:should understand|trebuie să înțeleagă|trebuie sa inteleaga)\b.+", re.IGNORECASE),
)


def match_goal(text: str) -> Optional[str]:
    stripped = (text or "").strip()
    if not stripped:
        return None
    for pattern in _PATTERNS:
        match = pattern.search(stripped)
        if match:
            return match.group(0).strip()
    return None
