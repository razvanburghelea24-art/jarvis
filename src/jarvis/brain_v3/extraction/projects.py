"""Project extraction heuristics."""

from __future__ import annotations

import re
from typing import Optional

_PATTERNS = (
    re.compile(r"\b(?:project|proiect)\b[\s:,-]+(?P<value>.{3,200})", re.IGNORECASE),
    re.compile(r"\bBrain\s+V3\b.{0,120}", re.IGNORECASE),
    re.compile(r"\bPhase\s+\d+\b.{0,120}", re.IGNORECASE),
    re.compile(r"\b(?:repo|repository|branch)\b[\s:,-]+(?P<value>.{3,120})", re.IGNORECASE),
)


def match_project(text: str) -> Optional[str]:
    stripped = (text or "").strip()
    if not stripped:
        return None
    for pattern in _PATTERNS:
        match = pattern.search(stripped)
        if not match:
            continue
        if "value" in match.groupdict() and match.group("value"):
            return match.group("value").strip()
        return match.group(0).strip()
    return None
