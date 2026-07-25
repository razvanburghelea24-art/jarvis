"""Candidate text normalisation and clamping."""

from __future__ import annotations

import re
import unicodedata

_MAX_VALUE_LEN = 2_000
_MULTI_SPACE = re.compile(r"\s+")


def clamp_candidate_text(text: str, *, max_len: int = _MAX_VALUE_LEN) -> str:
    if not text:
        return ""
    normalized = unicodedata.normalize("NFC", text.strip())
    normalized = _MULTI_SPACE.sub(" ", normalized)
    if len(normalized) > max_len:
        return normalized[: max_len - 3].rstrip() + "..."
    return normalized


def normalize_candidate_key(text: str) -> str:
    return clamp_candidate_text(text).lower()
