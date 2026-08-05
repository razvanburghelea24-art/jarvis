"""TDD — ResponseStreamer (deliver ConversationResponse chunks · no LLM)."""

from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest

from src.jarvis.cora_foundation.conversation import (
    ConversationEngine,
    ConversationEvents,
    ConversationHarness,
    ConversationResponse,
    EventJournal,
    LifecyclePhase,
    RequestValidator,
    ResponseStreamer,
    STREAM_CANCELLED,
    STREAM_CHUNK,
    STREAM_COMPLETED,
    STREAM_INTERRUPTED,
    STREAM_RESUMED,
    STREAM_STARTED,
    reset_conversation_event_journal_for_tests,
)

ST_PATH = (
    Path(__file__).resolve().parents[1]
    / "src"
    / "jarvis"
    / "cora_foundation"
    / "conversation"
    / "engine"
    / "streaming.py"
)


def setup_function():
    reset_conversation_event_journal_for_tests()


def _req(**overrides):
    raw = {
        "request_id": "req-st-1",
        "session_id": "sess-st",
        "workspace_id": "ws-nymods",
        "input": "hello",
        "barge_in": False,
        "metadata": {},
    }
    raw.update(overrides)
    return RequestValidator().validate(raw)


def _resp(text: str, *, response_id: str = "resp_st") -> ConversationResponse:
    return ConversationResponse(
        response_id=response_id,
        request_id="req-st-1",
        decision_id="dec_st",
        phase=LifecyclePhase.COMPLETED,
        text=text,
        incomplete=False,
        metadata={"response_mode": "test"},
    )


def test_empty_stream():
    journal = EventJournal()
    bus = ConversationEvents(on_event=journal.record)
    streamer = ResponseStreamer(events=bus, chunk_size=8)
    req = _req()
    result = streamer.run(_resp(""), req)
    assert result.completed is True
    assert result.cancelled is False
    assert result.chunks == ()
    assert journal.types(request_id=req.request_id) == [STREAM_STARTED, STREAM_COMPLETED]


def test_single_chunk():
    journal = EventJournal()
    bus = ConversationEvents(on_event=journal.record)
    streamer = ResponseStreamer(events=bus, chunk_size=64)
    req = _req()
    result = streamer.run(_resp("hi"), req)
    assert result.completed is True
    assert len(result.chunks) == 1
    assert result.chunks[0].text == "hi"
    assert result.chunks[0].index == 0
    types = journal.types(request_id=req.request_id)
    assert types == [STREAM_STARTED, STREAM_CHUNK, STREAM_COMPLETED]


def test_multi_chunk_order():
    journal = EventJournal()
    bus = ConversationEvents(on_event=journal.record)
    streamer = ResponseStreamer(events=bus, chunk_size=4)
    req = _req()
    text = "abcdefghij"
    result = streamer.run(_resp(text), req)
    assert result.completed is True
    assert "".join(c.text for c in result.chunks) == text
    assert [c.index for c in result.chunks] == list(range(len(result.chunks)))
    assert len(result.chunks) == 3
    types = journal.types(request_id=req.request_id)
    assert types[0] == STREAM_STARTED
    assert types.count(STREAM_CHUNK) == 3
    assert types[-1] == STREAM_COMPLETED


def test_cancel_mid_stream():
    journal = EventJournal()
    bus = ConversationEvents(on_event=journal.record)
    streamer = ResponseStreamer(events=bus, chunk_size=4)
    req = _req()
    gen = streamer.stream(_resp("abcdefghij"), req)
    first = next(gen)
    assert first.text == "abcd"
    streamer.cancel()
    rest = list(gen)
    assert rest == []
    types = journal.types(request_id=req.request_id)
    assert STREAM_STARTED in types
    assert STREAM_CHUNK in types
    assert STREAM_CANCELLED in types
    assert STREAM_COMPLETED not in types


def test_interrupt_parks_and_resume_continues():
    journal = EventJournal()
    bus = ConversationEvents(on_event=journal.record)
    streamer = ResponseStreamer(events=bus, chunk_size=4)
    req = _req(request_id="req-barge")
    text = "abcdefghij"
    gen = streamer.stream(_resp(text), req)
    first = next(gen)
    assert first.text == "abcd"
    streamer.interrupt()
    rest = list(gen)
    assert rest == []
    assert streamer.parked is not None
    assert streamer.parked.remaining_text == "efghij"
    types = journal.types(request_id=req.request_id)
    assert STREAM_INTERRUPTED in types
    assert STREAM_CANCELLED not in types
    assert STREAM_COMPLETED not in types

    resumed = streamer.run_resume(req)
    assert resumed.resumed is True
    assert resumed.completed is True
    assert "".join(c.text for c in resumed.chunks) == "efghij"
    types2 = journal.types(request_id=req.request_id)
    assert STREAM_RESUMED in types2
    assert STREAM_COMPLETED in types2


def test_cancel_does_not_park():
    streamer = ResponseStreamer(chunk_size=4)
    req = _req()
    gen = streamer.stream(_resp("abcdefghij"), req)
    next(gen)
    streamer.cancel()
    list(gen)
    assert streamer.parked is None


def test_engine_barge_in_api():
    engine = ConversationEngine()
    req = _req(request_id="req-eng-barge")
    resp = engine.submit(req)
    # Force a long response for chunking by streaming the built text
    long = _resp((resp.text or "x") * 20, response_id=resp.response_id)
    gen = engine.stream(long, req)
    next(gen)
    engine.interrupt_stream()
    assert list(gen) == []
    assert engine.streamer.parked is not None
    result = engine.resume_stream_run(req)
    assert result.resumed is True
    assert result.completed is True


def test_chunk_serialization():
    streamer = ResponseStreamer(chunk_size=3)
    req = _req()
    result = streamer.run(_resp("abcdef"), req)
    raw = result.to_dict()
    assert json.dumps(raw)
    assert raw["completed"] is True
    assert raw["chunks"][0]["index"] == 0


def test_harness_stream_pass():
    h = ConversationHarness(chunk_size=16)
    result = h.run_turn(
        {
            "request_id": "req-st-h",
            "session_id": "s",
            "workspace_id": "w",
            "input": "stream please",
        },
        stream=True,
    )
    assert result.ok is True
    assert result.stream is not None
    assert result.stream.completed is True
    assert "".join(c.text for c in result.stream.chunks) == result.response.text
    types = h.event_journal.types(request_id="req-st-h")
    assert STREAM_STARTED in types
    assert STREAM_COMPLETED in types


def test_engine_stream_api():
    engine = ConversationEngine()
    assert engine.SKELETON is False
    req = _req(request_id="req-st-eng")
    resp = engine.submit(req)
    chunks = [c for c in engine.stream(resp, req) if not c.done]
    assert "".join(c.text for c in chunks) == resp.text


def test_no_llm_planner_electron():
    forbidden = {"openai", "anthropic", "planner", "electron", "persona", "gateway", "httpx"}
    tree = ast.parse(ST_PATH.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            mod = (node.module or "").lower()
            if mod.startswith("."):
                continue
            for bad in forbidden:
                assert bad not in mod.split(".")
        elif isinstance(node, ast.Import):
            for alias in node.names:
                for bad in forbidden:
                    assert bad not in alias.name.lower().split(".")
