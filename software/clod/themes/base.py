"""Abstract base class for all visual themes."""

from __future__ import annotations

from abc import ABC, abstractmethod

from PIL import Image

from clod.events import FaceState


class ThemeRenderer(ABC):
    """Base class for all visual themes.

    Subclasses implement :meth:`draw_frame` to produce one 64x64 RGB frame.
    The ThemeManager calls :meth:`set_state` / :meth:`set_amplitude` whenever
    the corresponding events arrive, then calls :meth:`draw_frame` each tick.
    """

    def __init__(self, width: int = 64, height: int = 64) -> None:
        self.width = width
        self.height = height
        self._current_state: FaceState = FaceState.IDLE
        self._amplitude: float = 0.0

    @property
    @abstractmethod
    def name(self) -> str:
        """Human-readable theme name for display."""
        ...

    def set_state(self, state: FaceState) -> None:
        """React to face state change. Default stores it."""
        self._current_state = state

    def set_amplitude(self, amplitude: float) -> None:
        """React to audio amplitude (0.0-1.0). Default stores it."""
        self._amplitude = amplitude

    @abstractmethod
    def draw_frame(self, dt: float) -> Image.Image:
        """Draw one frame. *dt* = seconds since last frame. Return 64x64 RGB Image."""
        ...

    def on_activate(self) -> None:
        """Called when this theme becomes the active theme. Reset internal state."""

    def on_deactivate(self) -> None:
        """Called when switching away from this theme."""
