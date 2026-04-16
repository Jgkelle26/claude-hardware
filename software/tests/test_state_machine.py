"""Tests for clod.state_machine.StateMachine."""

from __future__ import annotations

import asyncio

import pytest

from clod.event_bus import EventBus
from clod.events import (
    AUDIO_VAD_START,
    BUTTON_PRESSED,
    CLAUDE_ERROR,
    CLAUDE_STREAM_CHUNK,
    FACE_SET_STATE,
    STT_FINAL,
    TTS_END,
    FaceState,
    SystemState,
)
from clod.state_machine import StateMachine


def _track_face_events(bus: EventBus) -> list[FaceState]:
    received: list[FaceState] = []

    async def cb(payload: FaceState) -> None:
        received.append(payload)

    bus.on(FACE_SET_STATE, cb)
    return received


@pytest.mark.asyncio
async def test_initial_state_is_sleeping() -> None:
    bus = EventBus()
    sm = StateMachine(bus)
    assert sm.current_state == SystemState.SLEEPING


@pytest.mark.asyncio
async def test_button_wakes_from_sleeping() -> None:
    bus = EventBus()
    sm = StateMachine(bus)
    await bus.emit(BUTTON_PRESSED)
    assert sm.current_state == SystemState.IDLE


@pytest.mark.asyncio
async def test_vad_start_from_idle_to_listening() -> None:
    bus = EventBus()
    sm = StateMachine(bus)
    await bus.emit(BUTTON_PRESSED)  # SLEEPING -> IDLE
    await bus.emit(AUDIO_VAD_START)
    assert sm.current_state == SystemState.LISTENING


@pytest.mark.asyncio
async def test_happy_path() -> None:
    bus = EventBus()
    sm = StateMachine(bus)
    faces = _track_face_events(bus)

    await bus.emit(BUTTON_PRESSED)  # SLEEPING -> IDLE
    assert sm.current_state == SystemState.IDLE

    await bus.emit(AUDIO_VAD_START)  # IDLE -> LISTENING
    assert sm.current_state == SystemState.LISTENING

    await bus.emit(STT_FINAL, "hello")  # LISTENING -> THINKING
    assert sm.current_state == SystemState.THINKING

    await bus.emit(CLAUDE_STREAM_CHUNK, "hi")  # THINKING -> SPEAKING
    assert sm.current_state == SystemState.SPEAKING

    await bus.emit(TTS_END)  # SPEAKING -> IDLE
    assert sm.current_state == SystemState.IDLE

    assert faces == [
        FaceState.IDLE,
        FaceState.LISTENING,
        FaceState.THINKING,
        FaceState.SPEAKING,
        FaceState.IDLE,
    ]


@pytest.mark.asyncio
async def test_error_state_returns_to_idle_after_timeout(monkeypatch) -> None:
    # Speed up the error timeout so tests run fast.
    import clod.state_machine as sm_module

    monkeypatch.setattr(sm_module, "ERROR_TIMEOUT_SECONDS", 0.05)

    bus = EventBus()
    sm = StateMachine(bus)

    await bus.emit(BUTTON_PRESSED)  # SLEEPING -> IDLE
    await bus.emit(AUDIO_VAD_START)  # IDLE -> LISTENING
    await bus.emit(STT_FINAL, "x")  # LISTENING -> THINKING
    await bus.emit(CLAUDE_ERROR, "bad")  # THINKING -> ERROR
    assert sm.current_state == SystemState.ERROR

    await asyncio.sleep(0.15)
    assert sm.current_state == SystemState.IDLE


@pytest.mark.asyncio
async def test_face_set_state_emitted_on_each_transition() -> None:
    bus = EventBus()
    sm = StateMachine(bus)
    faces = _track_face_events(bus)

    await bus.emit(BUTTON_PRESSED)
    assert sm.current_state == SystemState.IDLE
    assert faces[-1] == FaceState.IDLE

    await bus.emit(AUDIO_VAD_START)
    assert faces[-1] == FaceState.LISTENING

    await bus.emit(STT_FINAL)
    assert faces[-1] == FaceState.THINKING
