"""Top-level state machine orchestrating Clod's behavior."""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Optional

from clod.event_bus import EventBus
from clod.events import (
    AUDIO_VAD_START,
    BUTTON_PRESSED,
    CLAUDE_ERROR,
    CLAUDE_STREAM_CHUNK,
    FACE_SET_STATE,
    STT_FINAL,
    TTS_END,
    WAKE_DETECTED,
    FaceState,
    SystemState,
)

logger = logging.getLogger(__name__)

ERROR_TIMEOUT_SECONDS = 3.0

_STATE_TO_FACE: dict[SystemState, FaceState] = {
    SystemState.SLEEPING: FaceState.SLEEPING,
    SystemState.IDLE: FaceState.IDLE,
    SystemState.LISTENING: FaceState.LISTENING,
    SystemState.THINKING: FaceState.THINKING,
    SystemState.SPEAKING: FaceState.SPEAKING,
    SystemState.ERROR: FaceState.ERROR,
}

_TRANSITIONS: dict[tuple[SystemState, str], SystemState] = {
    (SystemState.SLEEPING, WAKE_DETECTED): SystemState.IDLE,
    (SystemState.SLEEPING, BUTTON_PRESSED): SystemState.IDLE,
    (SystemState.IDLE, AUDIO_VAD_START): SystemState.LISTENING,
    (SystemState.IDLE, BUTTON_PRESSED): SystemState.LISTENING,
    (SystemState.LISTENING, STT_FINAL): SystemState.THINKING,
    (SystemState.THINKING, CLAUDE_STREAM_CHUNK): SystemState.SPEAKING,
    (SystemState.THINKING, CLAUDE_ERROR): SystemState.ERROR,
    (SystemState.SPEAKING, TTS_END): SystemState.IDLE,
    (SystemState.SPEAKING, CLAUDE_ERROR): SystemState.ERROR,
    (SystemState.ERROR, "_timeout"): SystemState.IDLE,
}


class StateMachine:
    """Consumes events from the bus and transitions between SystemStates."""

    def __init__(self, bus: EventBus) -> None:
        self._bus = bus
        self._state: SystemState = SystemState.SLEEPING
        self._error_timeout_task: Optional[asyncio.Task[None]] = None

        # Subscribe to every event that appears on the left side of a transition.
        event_types = {evt for (_, evt) in _TRANSITIONS if evt != "_timeout"}
        for evt in event_types:
            self._bus.on(evt, self._make_handler(evt))

    def _make_handler(self, event_type: str):
        async def handler(_payload: Any) -> None:
            await self._handle(event_type)

        return handler

    @property
    def current_state(self) -> SystemState:
        return self._state

    async def _handle(self, event_type: str) -> None:
        key = (self._state, event_type)
        if key not in _TRANSITIONS:
            return
        new_state = _TRANSITIONS[key]
        await self._transition(new_state)

    async def _transition(self, new_state: SystemState) -> None:
        old_state = self._state
        logger.info("State transition: %s -> %s", old_state.name, new_state.name)
        self._state = new_state

        # Cancel any pending error timeout if we're leaving ERROR.
        if old_state == SystemState.ERROR and self._error_timeout_task is not None:
            self._error_timeout_task.cancel()
            self._error_timeout_task = None

        await self._bus.emit(FACE_SET_STATE, _STATE_TO_FACE[new_state])

        if new_state == SystemState.ERROR:
            self._error_timeout_task = asyncio.create_task(self._error_timeout())

    async def _error_timeout(self) -> None:
        try:
            await asyncio.sleep(ERROR_TIMEOUT_SECONDS)
        except asyncio.CancelledError:
            return
        if self._state == SystemState.ERROR:
            await self._handle("_timeout")
