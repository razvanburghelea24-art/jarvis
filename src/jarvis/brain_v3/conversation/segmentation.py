"""Conversation segmentation, ordering, and cue detection."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable, List, Sequence, Tuple

from .context import SpeakerAttribution
from .models import Message, compute_content_hash

_QUOTED_SPEAKER_RE = re.compile(
    r"(?P<prefix>^|\n)(?P<speaker>[^\n:]{1,80})\s+(?:a\s+spus|spus|said|wrote|reported)\s*:\s*",
    re.IGNORECASE,
)
_INLINE_QUOTE_RE = re.compile(
    r'(?P<quote>[«""](?P<text>[^»""]{2,800})[»""])',
)
_CODE_BLOCK_RE = re.compile(r"```[\s\S]*?```|`[^`\n]{1,400}`")
_NEGATION_RE = re.compile(
    r"\b(?:nu|not|never|no|fără|without|don't|do not|must not|must remain off|"
    r"nu vreau|nu activa|don't activate)\b",
    re.IGNORECASE,
)
_CORRECTION_RE = re.compile(
    r"\b(?:corect|correction|actually|de fapt|wrong|greșit|mistake|"
    r"not that|instead|rather|clarify|clarific)\b",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class QuotedSegment:
    text: str
    start: int
    end: int
    attribution: SpeakerAttribution
    marker: str = ""


def normalize_whitespace(text: str) -> str:
    from .normalizer import normalize_whitespace as _normalize

    return _normalize(text)


def order_messages(messages: Sequence[Message]) -> List[Message]:
    indexed = list(enumerate(messages))
    indexed.sort(
        key=lambda pair: (
            pair[1].sequence_index if pair[1].sequence_index >= 0 else pair[0],
            pair[1].timestamp or "",
            pair[0],
        )
    )
    ordered: List[Message] = []
    for new_index, (_, message) in enumerate(indexed):
        if message.sequence_index != new_index:
            ordered.append(
                Message(
                    message_id=message.message_id,
                    conversation_id=message.conversation_id,
                    role=message.role,
                    content=message.content,
                    sequence_index=new_index,
                    content_hash=message.content_hash,
                    author=message.author,
                    timestamp=message.timestamp,
                    metadata=dict(message.metadata),
                )
            )
        else:
            ordered.append(message)
    return ordered


def dedupe_messages(messages: Iterable[Message]) -> List[Message]:
    seen: set[tuple[str, str]] = set()
    result: List[Message] = []
    for message in messages:
        key = (message.role, message.content_hash)
        if key in seen:
            continue
        seen.add(key)
        result.append(message)
    return result


def detect_quoted_segments(text: str) -> List[QuotedSegment]:
    if not text:
        return []
    segments: List[QuotedSegment] = []
    protected = _mask_code_blocks(text)
    for match in _QUOTED_SPEAKER_RE.finditer(protected):
        remainder = protected[match.end() :]
        quote_end = _find_quote_end(remainder)
        quoted = remainder[:quote_end].strip()
        if quoted:
            segments.append(
                QuotedSegment(
                    text=quoted,
                    start=match.end(),
                    end=match.end() + quote_end,
                    attribution=SpeakerAttribution.QUOTED_UNVERIFIED,
                    marker=match.group("speaker").strip(),
                )
            )
    for match in _INLINE_QUOTE_RE.finditer(protected):
        segments.append(
            QuotedSegment(
                text=match.group("text").strip(),
                start=match.start("quote"),
                end=match.end("quote"),
                attribution=SpeakerAttribution.QUOTED_UNVERIFIED,
                marker="inline_quote",
            )
        )
    segments.sort(key=lambda s: s.start)
    return segments


def detect_negation(text: str) -> bool:
    return bool(text and _NEGATION_RE.search(text))


def detect_correction(text: str) -> bool:
    return bool(text and _CORRECTION_RE.search(text))


def _mask_code_blocks(text: str) -> str:
    return _CODE_BLOCK_RE.sub(lambda m: " " * len(m.group(0)), text)


def _find_quote_end(text: str) -> int:
    for idx, char in enumerate(text):
        if char == "\n" and idx > 0:
            return idx
    return len(text)


def message_dedupe_key(message: Message) -> Tuple[str, str]:
    return message.role, message.content_hash or compute_content_hash(message.content)
