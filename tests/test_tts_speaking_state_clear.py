"""TTS face-state SPEAKING must clear to IDLE when playback ends.

Root cause of the B+C+D activation ``speaking`` lock: ``_notify_speaking_state(False)``
previously left the face/state file on SPEAKING forever ("let daemon manage"),
so chat multi-turn TTS stranded ``jarvis_state``. F5 synthesis and the playback
watchdog are untouched — only the face-state clear path is covered here.
"""

from __future__ import annotations

import queue
from unittest.mock import MagicMock, patch

import pytest

from desktop_app.face_widget import JarvisState
from jarvis.output.tts import ChatterboxTTS, PiperTTS


def _mgr(current: JarvisState) -> MagicMock:
    mgr = MagicMock()
    mgr.state = current
    return mgr


def _piper(q: queue.Queue | None = None) -> PiperTTS:
    eng = PiperTTS.__new__(PiperTTS)
    eng._q = q if q is not None else queue.Queue()
    return eng


def _chatterbox(q: queue.Queue | None = None) -> ChatterboxTTS:
    eng = ChatterboxTTS.__new__(ChatterboxTTS)
    eng._q = q if q is not None else queue.Queue()
    return eng


@pytest.mark.unit
def test_piper_notify_speaking_false_clears_speaking_to_idle():
    eng = _piper()
    mgr = _mgr(JarvisState.SPEAKING)
    with patch("desktop_app.face_widget.get_jarvis_state", return_value=mgr):
        PiperTTS._notify_speaking_state(eng, False)
    mgr.set_state.assert_called_once_with(JarvisState.IDLE)


@pytest.mark.unit
def test_piper_notify_speaking_false_skips_idle_when_queue_has_more():
    q = queue.Queue()
    q.put("next utterance")
    eng = _piper(q)
    mgr = _mgr(JarvisState.SPEAKING)
    with patch("desktop_app.face_widget.get_jarvis_state", return_value=mgr):
        PiperTTS._notify_speaking_state(eng, False)
    mgr.set_state.assert_not_called()


@pytest.mark.unit
def test_piper_notify_force_clears_even_with_queued_items():
    q = queue.Queue()
    q.put("leftover")
    eng = _piper(q)
    mgr = _mgr(JarvisState.SPEAKING)
    with patch("desktop_app.face_widget.get_jarvis_state", return_value=mgr):
        PiperTTS._notify_speaking_state(eng, False, force=True)
    mgr.set_state.assert_called_once_with(JarvisState.IDLE)


@pytest.mark.unit
@pytest.mark.parametrize("state", [
    JarvisState.LISTENING,
    JarvisState.THINKING,
    JarvisState.IDLE,
])
def test_piper_notify_speaking_false_does_not_clobber_newer_state(state):
    eng = _piper()
    mgr = _mgr(state)
    with patch("desktop_app.face_widget.get_jarvis_state", return_value=mgr):
        PiperTTS._notify_speaking_state(eng, False)
    mgr.set_state.assert_not_called()


@pytest.mark.unit
def test_piper_notify_speaking_true_sets_speaking():
    eng = _piper()
    mgr = _mgr(JarvisState.IDLE)
    with patch("desktop_app.face_widget.get_jarvis_state", return_value=mgr):
        PiperTTS._notify_speaking_state(eng, True)
    mgr.set_state.assert_called_once_with(JarvisState.SPEAKING)


@pytest.mark.unit
def test_piper_notify_exception_is_swallowed():
    eng = _piper()
    with patch(
        "desktop_app.face_widget.get_jarvis_state",
        side_effect=RuntimeError("boom"),
    ):
        PiperTTS._notify_speaking_state(eng, False)  # must not raise


@pytest.mark.unit
def test_chatterbox_notify_speaking_false_clears_speaking_to_idle():
    eng = _chatterbox()
    mgr = _mgr(JarvisState.SPEAKING)
    with patch("desktop_app.face_widget.get_jarvis_state", return_value=mgr):
        ChatterboxTTS._notify_speaking_state(eng, False)
    mgr.set_state.assert_called_once_with(JarvisState.IDLE)


@pytest.mark.unit
def test_chatterbox_notify_skips_idle_when_queue_has_more():
    q = queue.Queue()
    q.put("next")
    eng = _chatterbox(q)
    mgr = _mgr(JarvisState.SPEAKING)
    with patch("desktop_app.face_widget.get_jarvis_state", return_value=mgr):
        ChatterboxTTS._notify_speaking_state(eng, False)
    mgr.set_state.assert_not_called()
