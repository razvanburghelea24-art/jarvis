"""ResponseStreamer — deliver ConversationResponse as ordered chunks.

Does NOT generate content · call LLM · Planner · Memory · Decision · Electron.
Only slices an already-built ConversationResponse and emits progress events.

Barge-in:
  cancel()     → hard abort (no park)
  interrupt()  → park remainder · lifecycle Interrupted
  resume()     → continue parked text · lifecycle Resume → Streaming → Completed
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
    STREAM_INTERRUPTED,
    STREAM_RESUMED,
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
    interrupted: bool = False
    resumed: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "response_id": self.response_id,
            "request_id": self.request_id,
            "chunks": [c.to_dict() for c in self.chunks],
            "cancelled": self.cancelled,
            "completed": self.completed,
            "interrupted": self.interrupted,
            "resumed": self.resumed,
        }


@dataclass
class ParkedStream:
    response: ConversationResponse
    request: ConversationRequest
    remaining_text: str
    next_index: int
    chunks_emitted: int


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
        self._interrupt_requested = False
        self._parked: ParkedStream | None = None

    @property
    def parked(self) -> ParkedStream | None:
        return self._parked

    def cancel(self) -> None:
        """Hard abort — does not park remainder for resume."""
        self._cancelled = True
        self._interrupt_requested = False
        self._parked = None

    def interrupt(self) -> None:
        """Barge-in — stop emission and park remainder for resume()."""
        self._interrupt_requested = True
        self._cancelled = True

    def reset(self) -> None:
        self._cancelled = False
        self._interrupt_requested = False
        self._parked = None

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
        """Yield content chunks then a final done=True marker (unless cancelled/interrupted)."""
        self._cancelled = False
        self._interrupt_requested = False
        self._parked = None
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

        yield from self._emit_pieces(
            pieces,
            response=response,
            request=request,
            start_index=0,
            park_on_interrupt=True,
        )

    def resume(
        self,
        request: ConversationRequest | None = None,
    ) -> Iterator[StreamChunk]:
        """Continue a parked barge-in stream. Yields nothing if nothing parked."""
        parked = self._parked
        if parked is None:
            yield from ()
            return

        req = request or parked.request
        self._cancelled = False
        self._interrupt_requested = False
        remaining = parked.remaining_text
        start_index = parked.next_index
        response = parked.response
        self._parked = None

        pieces = self.split_text(remaining)
        self._events.emit(
            STREAM_RESUMED,
            req,
            payload={
                "response_id": response.response_id,
                "remaining_chars": len(remaining),
                "chunk_count": len(pieces),
                "resume_index": start_index,
            },
        )
        self._transition(
            req,
            previous="Waiting",
            current="Speaking",
            lifecycle="Resume",
        )
        self._transition(req, previous="Speaking", current="Speaking")

        yield from self._emit_pieces(
            pieces,
            response=response,
            request=req,
            start_index=start_index,
            park_on_interrupt=True,
        )

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
        interrupted = self._parked is not None
        cancelled = self._cancelled and not completed and not interrupted
        return StreamResult(
            response_id=response.response_id,
            request_id=request.request_id,
            chunks=tuple(content),
            cancelled=cancelled,
            completed=completed,
            interrupted=interrupted,
            resumed=False,
        )

    def run_resume(
        self,
        request: ConversationRequest | None = None,
    ) -> StreamResult:
        parked = self._parked
        if parked is None:
            return StreamResult(
                response_id="",
                request_id=(request.request_id if request else ""),
                chunks=(),
                cancelled=False,
                completed=False,
                interrupted=False,
                resumed=False,
            )
        response_id = parked.response.response_id
        request_id = (request or parked.request).request_id
        content: list[StreamChunk] = []
        completed = False
        for chunk in self.resume(request):
            if chunk.done:
                completed = True
            else:
                content.append(chunk)
        interrupted = self._parked is not None
        cancelled = self._cancelled and not completed and not interrupted
        return StreamResult(
            response_id=response_id,
            request_id=request_id,
            chunks=tuple(content),
            cancelled=cancelled,
            completed=completed,
            interrupted=interrupted,
            resumed=True,
        )

    def _emit_pieces(
        self,
        pieces: list[str],
        *,
        response: ConversationResponse,
        request: ConversationRequest,
        start_index: int,
        park_on_interrupt: bool,
    ) -> Iterator[StreamChunk]:
        emitted = 0
        for offset, piece in enumerate(pieces):
            if self._cancelled:
                index = start_index + offset
                if park_on_interrupt and self._interrupt_requested:
                    remaining = "".join(pieces[offset:])
                    self._parked = ParkedStream(
                        response=response,
                        request=request,
                        remaining_text=remaining,
                        next_index=index,
                        chunks_emitted=emitted,
                    )
                    self._events.emit(
                        STREAM_INTERRUPTED,
                        request,
                        payload={
                            "response_id": response.response_id,
                            "chunks_emitted": emitted,
                            "index": index,
                            "remaining_chars": len(remaining),
                            "barge_in": True,
                        },
                    )
                    self._transition(
                        request,
                        previous="Speaking",
                        current="Waiting",
                        lifecycle="Interrupted",
                    )
                else:
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

            index = start_index + offset
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
            if park_on_interrupt and self._interrupt_requested:
                self._parked = ParkedStream(
                    response=response,
                    request=request,
                    remaining_text="",
                    next_index=start_index + len(pieces),
                    chunks_emitted=emitted,
                )
                self._events.emit(
                    STREAM_INTERRUPTED,
                    request,
                    payload={
                        "response_id": response.response_id,
                        "chunks_emitted": emitted,
                        "remaining_chars": 0,
                        "barge_in": True,
                    },
                )
                self._transition(
                    request,
                    previous="Speaking",
                    current="Waiting",
                    lifecycle="Interrupted",
                )
            else:
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
            index=start_index + emitted,
            text="",
            response_id=response.response_id,
            request_id=request.request_id,
            done=True,
        )
        if self._on_chunk is not None:
            self._on_chunk(done)
        yield done

    def _transition(
        self,
        request: ConversationRequest,
        *,
        previous: str,
        current: str,
        lifecycle: str | None = None,
    ) -> ConversationState | None:
        if self._state_emitter is None:
            return None
        return self._state_emitter.emit_transition(
            request,
            previous=previous,
            current=current,
            lifecycle=lifecycle,
        )
