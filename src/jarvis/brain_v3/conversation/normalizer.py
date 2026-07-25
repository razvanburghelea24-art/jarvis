"""Whitespace and Unicode normalisation for conversation text."""

from __future__ import annotations

import re
import unicodedata

_MULTI_SPACE = re.compile(r"[ \t]+")
_MULTI_NEWLINE = re.compile(r"\n{3,}")


def normalize_whitespace(text: str) -> str:
    if not text:
        return ""
    normalized = unicodedata.normalize("NFC", text)
    normalized = normalized.replace("\r\n", "\n").replace("\r", "\n")
    lines = [_MULTI_SPACE.sub(" ", line.strip()) for line in normalized.split("\n")]
    normalized = "\n".join(lines).strip()
    return _MULTI_NEWLINE.sub("\n\n", normalized)
