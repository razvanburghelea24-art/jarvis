"""Constraint and entity extraction heuristics."""

from __future__ import annotations

import re
from typing import Optional, Tuple

_CONSTRAINT_PATTERNS = (
    re.compile(r"\b(?:fără push|fara push|no push)\b.+?", re.IGNORECASE),
    re.compile(r"\b(?:no pr|fără pr|fara pr)\b.+?", re.IGNORECASE),
    re.compile(r"\b(?:security neatins|security untouched|do not touch security)\b.+?", re.IGNORECASE),
    re.compile(r"\b(?:no live activation|fără activare live|dry[- ]run)\b.+?", re.IGNORECASE),
    re.compile(r"\b(?:execution forbidden|non-executable)\b.+?", re.IGNORECASE),
)

_INJECTION_PATTERNS = (
    re.compile(r"\b(?:ignore (?:previous|prior) rules|ignor[aă]\s+regulile)\b", re.IGNORECASE),
    re.compile(r"\b(?:activate|activeaz[aă])\s+h\b", re.IGNORECASE),
    re.compile(r"\b(?:approve all commands|aproba toate comenzile)\b", re.IGNORECASE),
    re.compile(r"\b(?:git reset|run shell|execute automatically)\b", re.IGNORECASE),
    re.compile(r"\b(?:administrator access|dezactiv\w*\s+approval)\b", re.IGNORECASE),
)

_ENTITY_PATTERNS = (
    re.compile(
        r"\b(?:component|module|service|person|user|feature)\b[\s:,-]+(?P<value>.{2,120})",
        re.IGNORECASE,
    ),
)


def match_constraint(text: str) -> Optional[str]:
    stripped = (text or "").strip()
    if not stripped:
        return None
    for pattern in _CONSTRAINT_PATTERNS:
        match = pattern.search(stripped)
        if match:
            return match.group(0).strip()
    return None


def match_injection(text: str) -> Optional[str]:
    stripped = (text or "").strip()
    if not stripped:
        return None
    for pattern in _INJECTION_PATTERNS:
        match = pattern.search(stripped)
        if match:
            return match.group(0).strip()
    return None


def match_entity(text: str) -> Optional[str]:
    stripped = (text or "").strip()
    if not stripped:
        return None
    for pattern in _ENTITY_PATTERNS:
        match = pattern.search(stripped)
        if match and match.group("value"):
            return match.group("value").strip()
    return None


def classify_hostile(text: str) -> Tuple[Optional[str], bool]:
    """Return hostile snippet and whether it looks like prompt injection."""
    snippet = match_injection(text)
    return snippet, bool(snippet)
