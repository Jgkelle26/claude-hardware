"""ThemeManager — loads, switches, and renders visual themes."""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

from PIL import Image

from clod.event_bus import EventBus
from clod.events import AUDIO_AMPLITUDE, FACE_SET_STATE, FaceState
from clod.matrix_backends import DisplayBackend
from clod.themes.base import ThemeRenderer

logger = logging.getLogger(__name__)


class ThemeManager:
    """Manages a list of :class:`ThemeRenderer` instances and drives the render loop.

    Subscribes to ``FACE_SET_STATE`` and ``AUDIO_AMPLITUDE`` events and
    forwards them to the currently active theme.
    """

    def __init__(self, bus: EventBus, backend: DisplayBackend, fps: int = 20) -> None:
        self.bus = bus
        self.backend = backend
        self.fps = fps

        self.themes: list[ThemeRenderer] = []
        self.active_index: int = 0

        bus.on(FACE_SET_STATE, self._on_face_set_state)
        bus.on(AUDIO_AMPLITUDE, self._on_audio_amplitude)

    # ------------------------------------------------------------------ #
    # Theme list management
    # ------------------------------------------------------------------ #

    def add_theme(self, theme: ThemeRenderer) -> None:
        """Append a theme to the rotation list."""
        self.themes.append(theme)
        logger.info("Registered theme %r (index %d)", theme.name, len(self.themes) - 1)

    def next_theme(self) -> None:
        """Cycle to the next theme in the list."""
        if not self.themes:
            return
        self.themes[self.active_index].on_deactivate()
        self.active_index = (self.active_index + 1) % len(self.themes)
        self.themes[self.active_index].on_activate()
        logger.info("Switched to theme %r", self.current_theme_name)

    def previous_theme(self) -> None:
        """Cycle to the previous theme in the list."""
        if not self.themes:
            return
        self.themes[self.active_index].on_deactivate()
        self.active_index = (self.active_index - 1) % len(self.themes)
        self.themes[self.active_index].on_activate()
        logger.info("Switched to theme %r", self.current_theme_name)

    @property
    def current_theme_name(self) -> str:
        """Human-readable name of the active theme."""
        if not self.themes:
            return "(none)"
        return self.themes[self.active_index].name

    # ------------------------------------------------------------------ #
    # Event handlers
    # ------------------------------------------------------------------ #

    def _on_face_set_state(self, payload: Any) -> None:
        if isinstance(payload, FaceState):
            state = payload
        elif isinstance(payload, str):
            try:
                state = FaceState(payload)
            except ValueError:
                return
        else:
            return

        if self.themes:
            self.themes[self.active_index].set_state(state)

    def _on_audio_amplitude(self, payload: Any) -> None:
        try:
            amplitude = max(0.0, min(1.0, float(payload)))
        except (TypeError, ValueError):
            return

        if self.themes:
            self.themes[self.active_index].set_amplitude(amplitude)

    # ------------------------------------------------------------------ #
    # Render loop
    # ------------------------------------------------------------------ #

    async def run(self) -> None:
        """Main render loop running at *self.fps*.

        Each iteration asks the active theme's :meth:`draw_frame` for a
        64x64 RGB image and passes it to the display backend.
        """
        frame_period: float = 1.0 / self.fps
        last_time: float = time.monotonic()

        while True:
            now = time.monotonic()
            dt = now - last_time
            last_time = now

            if self.themes:
                image = self.themes[self.active_index].draw_frame(dt)
            else:
                # No themes registered — render black.
                image = Image.new("RGB", (self.backend.width, self.backend.height), (0, 0, 0))

            self.backend.render(image)

            elapsed = time.monotonic() - now
            sleep_for = frame_period - elapsed
            if sleep_for > 0:
                await asyncio.sleep(sleep_for)
            else:
                await asyncio.sleep(0)
