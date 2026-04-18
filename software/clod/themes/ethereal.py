"""Ethereal Stripes theme — fragmented vertical color columns that drift and pixelate."""

from __future__ import annotations

import logging
import math
import random
from dataclasses import dataclass, field
from typing import List, Tuple

from PIL import Image, ImageDraw

from clod.events import FaceState
from clod.themes.base import ThemeRenderer

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Color palette
# ---------------------------------------------------------------------------

STRIPE_COLORS: list[tuple[int, int, int]] = [
    (180, 70, 70),     # dusty rose
    (200, 135, 75),    # warm sand
    (190, 180, 90),    # muted gold
    (80, 150, 110),    # sage green
    (70, 120, 180),    # slate blue
    (110, 75, 160),    # soft purple
    (160, 75, 120),    # muted mauve
    (35, 35, 50),      # dark slate
    (210, 210, 220),   # soft white
]

# Darker palette for sleeping state — deep twilight tones
SLEEPING_COLORS: list[tuple[int, int, int]] = [
    (25, 20, 50),      # deep indigo
    (40, 30, 70),      # dark purple
    (20, 35, 65),      # midnight blue
    (50, 25, 55),      # dark plum
    (15, 30, 55),      # navy
    (35, 40, 75),      # twilight blue
    (45, 20, 45),      # dark berry
    (10, 15, 35),      # near black blue
    (55, 50, 80),      # dim lavender
]

# Thinking palette — restricted to 3-4 similar tones
THINKING_COLORS: list[tuple[int, int, int]] = [
    (70, 100, 165),    # medium blue
    (85, 115, 180),    # lighter blue
    (55, 80, 145),     # deeper blue
    (95, 130, 190),    # soft blue
]

# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------


@dataclass
class Fragment:
    """A single horizontal chunk of a column rendered with an x-offset."""

    y: int
    height: int
    x_offset: float


@dataclass
class Column:
    """A vertical stripe that can fragment and drift across the canvas."""

    x: float
    width: int
    color: tuple[int, int, int]
    fragmentation: float
    drift_speed: float
    phase: float  # unique oscillation phase for each column
    fragments: list[Fragment] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Per-state target parameters
# ---------------------------------------------------------------------------

@dataclass
class _StateParams:
    """Target values for a given FaceState."""

    frag_min: float
    frag_max: float
    drift_min: float
    drift_max: float
    frag_osc_speed: float  # oscillation speed multiplier
    brightness: float  # 0.0-1.0 color brightness multiplier
    jitter: float  # per-frame random horizontal jitter for fragments


_STATE_PARAMS: dict[FaceState, _StateParams] = {
    FaceState.IDLE: _StateParams(
        frag_min=0.0, frag_max=0.15,
        drift_min=0.3, drift_max=1.2,
        frag_osc_speed=0.3,
        brightness=1.0,
        jitter=0.0,
    ),
    FaceState.LISTENING: _StateParams(
        frag_min=0.0, frag_max=0.0,
        drift_min=0.0, drift_max=0.0,
        frag_osc_speed=0.0,
        brightness=1.1,
        jitter=0.0,
    ),
    FaceState.THINKING: _StateParams(
        frag_min=0.2, frag_max=0.45,
        drift_min=1.5, drift_max=3.0,
        frag_osc_speed=0.8,
        brightness=1.0,
        jitter=1.0,
    ),
    FaceState.SPEAKING: _StateParams(
        frag_min=0.0, frag_max=0.3,
        drift_min=0.4, drift_max=1.0,
        frag_osc_speed=4.0,
        brightness=1.0,
        jitter=0.5,
    ),
    FaceState.ERROR: _StateParams(
        frag_min=0.1, frag_max=0.25,
        drift_min=0.1, drift_max=0.3,
        frag_osc_speed=0.5,
        brightness=0.85,
        jitter=0.5,
    ),
    FaceState.HAPPY: _StateParams(
        frag_min=0.05, frag_max=0.1,
        drift_min=0.8, drift_max=1.5,
        frag_osc_speed=0.0,
        brightness=1.0,
        jitter=0.0,
    ),
    FaceState.SLEEPING: _StateParams(
        frag_min=0.0, frag_max=0.0,
        drift_min=0.05, drift_max=0.1,
        frag_osc_speed=0.0,
        brightness=1.0,  # no dimming — dark colors handle this
        jitter=0.0,
    ),
}


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------

def _lerp(a: float, b: float, t: float) -> float:
    """Linear interpolation clamped to [a, b] range."""
    return a + (b - a) * max(0.0, min(1.0, t))


def _clamp(v: int, lo: int, hi: int) -> int:
    return max(lo, min(hi, v))


def _apply_brightness(
    color: tuple[int, int, int], brightness: float
) -> tuple[int, int, int]:
    return (
        _clamp(int(color[0] * brightness), 0, 255),
        _clamp(int(color[1] * brightness), 0, 255),
        _clamp(int(color[2] * brightness), 0, 255),
    )


def _hue_shift(
    color: tuple[int, int, int], shift: float
) -> tuple[int, int, int]:
    """Rotate the hue of *color* by *shift* (0.0-1.0)."""
    r, g, b = color[0] / 255.0, color[1] / 255.0, color[2] / 255.0
    max_c = max(r, g, b)
    min_c = min(r, g, b)
    diff = max_c - min_c

    # Convert to HSV
    if diff == 0:
        h = 0.0
    elif max_c == r:
        h = ((g - b) / diff) % 6
    elif max_c == g:
        h = ((b - r) / diff) + 2
    else:
        h = ((r - g) / diff) + 4
    h /= 6.0
    s = 0.0 if max_c == 0 else diff / max_c
    v = max_c

    # Shift hue
    h = (h + shift) % 1.0

    # Convert back to RGB
    i = int(h * 6.0)
    f = h * 6.0 - i
    p = v * (1.0 - s)
    q = v * (1.0 - f * s)
    t = v * (1.0 - (1.0 - f) * s)

    i %= 6
    if i == 0:
        r2, g2, b2 = v, t, p
    elif i == 1:
        r2, g2, b2 = q, v, p
    elif i == 2:
        r2, g2, b2 = p, v, t
    elif i == 3:
        r2, g2, b2 = p, q, v
    elif i == 4:
        r2, g2, b2 = t, p, v
    else:
        r2, g2, b2 = v, p, q

    return (
        _clamp(int(r2 * 255), 0, 255),
        _clamp(int(g2 * 255), 0, 255),
        _clamp(int(b2 * 255), 0, 255),
    )


def _generate_fragments(
    column_height: int, fragmentation: float, jitter: float
) -> list[Fragment]:
    """Create a list of fragments that tiles the full column height.

    Fragment count grows with *fragmentation*; each fragment gets a random
    horizontal offset scaled by *fragmentation* and *jitter*.
    """
    if fragmentation <= 0.0:
        return []

    num_fragments = int(fragmentation * 20) + 1
    # Distribute heights to cover the full column
    base_h = column_height // num_fragments
    remainder = column_height - base_h * num_fragments

    fragments: list[Fragment] = []
    y = 0
    for i in range(num_fragments):
        h = base_h + (1 if i < remainder else 0)
        h = max(1, min(h, 8))  # clamp to 1-8
        if y >= column_height:
            break
        if y + h > column_height:
            h = column_height - y
        max_offset = fragmentation * (4.0 + jitter)
        x_offset = random.uniform(-max_offset, max_offset)
        fragments.append(Fragment(y=y, height=h, x_offset=x_offset))
        y += h

    # Fill any remaining gap at the bottom
    while y < column_height:
        h = min(column_height - y, max(2, int(random.uniform(2, 8))))
        max_offset = fragmentation * (4.0 + jitter)
        x_offset = random.uniform(-max_offset, max_offset)
        fragments.append(Fragment(y=y, height=h, x_offset=x_offset))
        y += h

    return fragments


# ---------------------------------------------------------------------------
# Theme implementation
# ---------------------------------------------------------------------------


class EtherealTheme(ThemeRenderer):
    """Ethereal Stripes — fragmented vertical color columns."""

    def __init__(self, width: int = 64, height: int = 64) -> None:
        super().__init__(width, height)
        self._columns: list[Column] = []
        self._time: float = 0.0
        self._transition_progress: float = 1.0  # 1.0 = fully transitioned
        self._prev_params: _StateParams = _STATE_PARAMS[FaceState.IDLE]
        self._target_params: _StateParams = _STATE_PARAMS[FaceState.IDLE]
        self._error_flash_timer: float = 0.0
        self._happy_hue_offset: float = 0.0
        self._sleeping_pulse_col: int = 0
        self._sleeping_pulse_timer: float = 0.0
        self._rng = random.Random(42)

    # ------------------------------------------------------------------
    # ThemeRenderer interface
    # ------------------------------------------------------------------

    @property
    def name(self) -> str:
        return "Ethereal"

    def set_state(self, state: FaceState) -> None:
        if state != self._current_state:
            self._prev_params = self._effective_params()
            self._target_params = _STATE_PARAMS.get(
                state, _STATE_PARAMS[FaceState.IDLE]
            )
            self._transition_progress = 0.0
            if state == FaceState.SLEEPING:
                self._sleeping_pulse_col = self._rng.randint(
                    0, max(0, len(self._columns) - 1)
                )
                self._sleeping_pulse_timer = 0.0
        super().set_state(state)

    def on_activate(self) -> None:
        """Generate columns filling the 64-pixel canvas."""
        self._columns = []
        self._time = 0.0
        self._transition_progress = 1.0
        self._prev_params = _STATE_PARAMS[FaceState.IDLE]
        self._target_params = _STATE_PARAMS[FaceState.IDLE]
        self._error_flash_timer = 0.0
        self._happy_hue_offset = 0.0
        self._sleeping_pulse_col = 0
        self._sleeping_pulse_timer = 0.0

        x = 0.0
        color_index = 0
        while x < self.width:
            w = self._rng.randint(4, 8)
            # Ensure last column fills remaining space
            if x + w >= self.width:
                w = self.width - int(x)
                if w <= 0:
                    break
                w = max(w, 1)
            color = STRIPE_COLORS[color_index % len(STRIPE_COLORS)]
            color_index += 1
            drift = self._rng.uniform(0.5, 2.0)
            phase = self._rng.uniform(0.0, math.tau)
            self._columns.append(
                Column(
                    x=x,
                    width=w,
                    color=color,
                    fragmentation=0.0,
                    drift_speed=drift,
                    phase=phase,
                )
            )
            x += w

        logger.debug("EtherealTheme activated with %d columns", len(self._columns))

    def on_deactivate(self) -> None:
        self._columns = []

    def draw_frame(self, dt: float) -> Image.Image:
        self._time += dt

        # Advance transition (lerp over ~0.5 seconds)
        if self._transition_progress < 1.0:
            self._transition_progress = min(
                1.0, self._transition_progress + dt / 0.5
            )

        params = self._effective_params()

        # State-specific timers
        self._error_flash_timer += dt
        if self._current_state == FaceState.HAPPY:
            self._happy_hue_offset += dt / 2.0  # full rotation in 2s
        if self._current_state == FaceState.SLEEPING:
            self._sleeping_pulse_timer += dt

        # Update columns
        for i, col in enumerate(self._columns):
            # Drift
            target_drift = _lerp(
                params.drift_min, params.drift_max,
                (math.sin(self._time * 0.3 + col.phase) + 1.0) / 2.0,
            )
            col.drift_speed = _lerp(col.drift_speed, target_drift, min(1.0, dt * 3.0))
            col.x = (col.x + col.drift_speed * dt) % self.width

            # Fragmentation target
            osc = (math.sin(self._time * params.frag_osc_speed + col.phase) + 1.0) / 2.0
            target_frag = _lerp(params.frag_min, params.frag_max, osc)
            col.fragmentation = _lerp(
                col.fragmentation, target_frag, min(1.0, dt * 4.0)
            )

            # Generate fragments for this frame
            col.fragments = _generate_fragments(
                self.height, col.fragmentation, params.jitter
            )

        # Draw
        img = Image.new("RGB", (self.width, self.height), (0, 0, 0))
        draw = ImageDraw.Draw(img)

        for i, col in enumerate(self._columns):
            color = col.color

            # SLEEPING: use dark twilight palette instead of dimming
            if self._current_state == FaceState.SLEEPING:
                color = SLEEPING_COLORS[i % len(SLEEPING_COLORS)]
                # One column gently pulses slightly brighter
                if i == self._sleeping_pulse_col:
                    pulse = (math.sin(self._sleeping_pulse_timer * 1.0) + 1.0) / 2.0
                    color = _apply_brightness(color, 1.0 + pulse * 0.6)

            # THINKING: use restricted blue palette
            elif self._current_state == FaceState.THINKING:
                color = THINKING_COLORS[i % len(THINKING_COLORS)]

            # HAPPY: gentle hue shift
            elif self._current_state == FaceState.HAPPY:
                color = _hue_shift(color, self._happy_hue_offset + i * 0.1)

            # ERROR: desaturate and warm — columns slowly lose color
            elif self._current_state == FaceState.ERROR:
                # Blend toward a muted warm tone
                warm = (140, 95, 70)  # dusty amber
                blend = 0.4 + 0.2 * math.sin(self._error_flash_timer * 1.5 + i)
                color = (
                    int(color[0] * (1 - blend) + warm[0] * blend),
                    int(color[1] * (1 - blend) + warm[1] * blend),
                    int(color[2] * (1 - blend) + warm[2] * blend),
                )

            # Brightness adjustment
            color = _apply_brightness(color, params.brightness)

            # Draw the column (or its fragments)
            self._draw_column(draw, col, color)

        return img

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _effective_params(self) -> _StateParams:
        """Return blended parameters between previous and target state."""
        t = self._transition_progress
        if t >= 1.0:
            return self._target_params
        p = self._prev_params
        q = self._target_params
        return _StateParams(
            frag_min=_lerp(p.frag_min, q.frag_min, t),
            frag_max=_lerp(p.frag_max, q.frag_max, t),
            drift_min=_lerp(p.drift_min, q.drift_min, t),
            drift_max=_lerp(p.drift_max, q.drift_max, t),
            frag_osc_speed=_lerp(p.frag_osc_speed, q.frag_osc_speed, t),
            brightness=_lerp(p.brightness, q.brightness, t),
            jitter=_lerp(p.jitter, q.jitter, t),
        )

    def _draw_column(
        self,
        draw: ImageDraw.ImageDraw,
        col: Column,
        color: tuple[int, int, int],
    ) -> None:
        """Draw a single column, handling wrapping and fragmentation."""
        if col.fragmentation <= 0.0 or not col.fragments:
            # Solid stripe — draw once or twice if wrapping
            self._draw_rect_wrap(draw, col.x, 0, col.width, self.height, color)
        else:
            for frag in col.fragments:
                fx = col.x + frag.x_offset
                self._draw_rect_wrap(
                    draw, fx, frag.y, col.width, frag.height, color
                )

    def _draw_rect_wrap(
        self,
        draw: ImageDraw.ImageDraw,
        x: float,
        y: int,
        w: int,
        h: int,
        color: tuple[int, int, int],
    ) -> None:
        """Draw a rectangle that wraps horizontally around the canvas."""
        ix = int(round(x)) % self.width
        x1 = ix
        x2 = ix + w - 1
        y2 = min(y + h - 1, self.height - 1)

        if y > y2:
            return

        if x2 < self.width:
            # Fits without wrapping
            draw.rectangle([x1, y, x2, y2], fill=color)
        else:
            # Wraps around — draw two pieces
            draw.rectangle([x1, y, self.width - 1, y2], fill=color)
            draw.rectangle([0, y, x2 - self.width, y2], fill=color)
