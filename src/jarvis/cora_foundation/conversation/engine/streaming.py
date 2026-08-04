"""ResponseStreamer — deliver ConversationResponse as ordered chunks.

Does NOT generate content · call LLM · Planner · Memory · Decision · Electron.
Only slices an already-built ConversationResponse and emits progress events.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from dataclasses import dataclass
from typing import Any

from ..contracts import ConversationRequest, ConversationResponse, ConversationState
from .conversation_events import (
    STREAM_CANCELLED,
    STREAM_CHUNK,
    STREAM_COMPLETED,
    STREAM_STARTED,
    ConversationEvents,
)
from .state_emitter import StateEmitter

DEFAULT_CHUNK_SIZE = 24


@dataclass(frozen=True)
class StreamChunk:
    index: int
    text: str
    response_id: str
    request_id: str
    done: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "index": self.index,
            "text": self.text,
            "response_id": self.response_id,
            "request_id": self.request_id,
            "done": self.done,
        }


@dataclass(frozen=True)
class StreamResult:
    response_id: str
    request_id: str
    chunks: tuple[StreamChunk, ...]
    cancelled: bool
    completed: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "response_id": self.response_id,
            "request_id": self.request_id,
            "chunks": [c.to_dict() for c in self.chunks],
            "cancelled": self.cancelled,
            "completed": self.completed,
        }


class ResponseStreamer:
    """Progressive delivery of a finished ConversationResponse."""

    def __init__(
        self,
        *,
        events: ConversationEvents | None = None,
        state_emitter: StateEmitter | None = None,
        on_chunk: Callable[[StreamChunk], None] | None = None,
        chunk_size: int = DEFAULT_CHUNK_SIZE,
    ) -> None:
        self._events = events or ConversationEvents()
        self._state_emitter = state_emitter
        self._on_chunk = on_chunk
        self._chunk_size = max(1, int(chunk_size))
        self._cancelled = False

    def cancel(self) -> None:
        self._cancelled = True

    def reset(self) -> None:
        self._cancelled = False

    def split_text(self, text: str) -> list[str]:
        """Deterministic chunking only — does not invent content."""
        if not text:
            return []
        size = self._chunk_size
        return [text[i : i + size] for i in range(0, len(text), size)]

    def stream(
        self,
        response: ConversationResponse,
        request: ConversationRequest,
    ) -> Iterator[StreamChunk]:
        """Yield content chunks then a final done=True marker (unless cancelled)."""
        self._cancelled = False
        pieces = self.split_text(response.text or "")
        self._events.emit(
            STREAM_STARTED,
            request,
            payload={
                "response_id": response.response_id,
                "chunk_count": len(pieces),
                "chunk_size": self._chunk_size,
            },
        )
        self._transition(request, previous="Thinking", current="Speaking")

        emitted = 0
        for index, piece in enumerate(pieces):
            if self._cancelled:
                self._events.emit(
                    STREAM_CANCELLED,
                    request,
                    payload={
                        "response_id": response.response_id,
                        "chunks_emitted": emitted,
                        "index": index,
                    },
                )
                return
            chunk = StreamChunk(
                index=index,
                text=piece,
                response_id=response.response_id,
                request_id=request.request_id,
                done=False,
            )
            emitted += 1
            self._events.emit(STREAM_CHUNK, request, payload=chunk.to_dict())
            if self._on_chunk is not None:
                self._on_chunk(chunk)
            yield chunk

        if self._cancelled:
            self._events.emit(
                STREAM_CANCELLED,
                request,
                payload={
                    "response_id": response.response_id,
                    "chunks_emitted": emitted,
                },
            )
            return

        self._events.emit(
            STREAM_COMPLETED,
            request,
            payload={
                "response_id": response.response_id,
                "chunks_emitted": emitted,
                "completed": True,
            },
        )
        self._transition(request, previous="Speaking", current="Completed")
        done = StreamChunk(
            index=emitted,
            text="",
            response_id=response.response_id,
            request_id=request.request_id,
            done=True,
        )
        if self._on_chunk is not None:
            self._on_chunk(done)
        yield done

    def run(
        self,
        response: ConversationResponse,
        request: ConversationRequest,
    ) -> StreamResult:
        content: list[StreamChunk] = []
        completed = False
        for chunk in self.stream(response, request):
            if chunk.done:
                completed = True
            else:
                content.append(chunk)
        cancelled = self._cancelled and not completed
        return StreamResult(
            response_id=response.response_id,
            request_id=request.request_id,
            chunks=tuple(content),
            cancelled=cancelled,
            completed=completed,
        )

    def _transition(
        self,
        request: ConversationRequest,
        *,
        previous: str,
        current: str,
    ) -> ConversationState | None:
        if self._state_emitter is None:
            return None
        return self._state_emitter.emit_transition(
            request, previous=previous, current=current
        )
