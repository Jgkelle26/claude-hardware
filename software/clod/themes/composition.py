"""Composition theme -- geometric pixel art inspired by De Stijl / Mondrian.

Divides the 64x64 canvas into rectangular zones, each holding a different
pattern type (stripes, hatches, checkerboard, solid).  Animation behavior
adapts to the current FaceState.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from enum import Enum
from typing import List, Tuple

from PIL import Image, ImageDraw

from clod.events import FaceState
from clod.themes.base import ThemeRenderer

# ---------------------------------------------------------------------------
# Palette
# ---------------------------------------------------------------------------

PALETTE: List[Tuple[int, int, int]] = [
    (255, 0, 0),       # red
    (0, 85, 255),      # blue
    (0, 136, 68),      # green
    (255, 102, 0),     # orange
    (255, 204, 0),     # yellow
    (0, 0, 0),         # black
    (255, 255, 255),   # white
]

BACKGROUND: Tuple[int, int, int] = (245, 230, 208)  # cream


# ---------------------------------------------------------------------------
# Pattern enumeration
# ---------------------------------------------------------------------------

class PatternType(Enum):
    STRIPES_V = "stripes_v"
    STRIPES_H = "stripes_h"
    HATCHES_45 = "hatches_45"
    HATCHES_N45 = "hatches_n45"
    CHECKERBOARD = "checkerboard"
    SOLID = "solid"


ALL_PATTERNS: List[PatternType] = list(PatternType)


# ---------------------------------------------------------------------------
# Zone dataclass
# ---------------------------------------------------------------------------

@dataclass
class Zone:
    """A rectangular region of the canvas with its own pattern."""

    x: int
    y: int
    width: int
    height: int
    pattern: PatternType
    color1: Tuple[int, int, int]
    color2: Tuple[int, int, int]
    phase: float = 0.0
    # Morph timer -- counts time until the next IDLE morph for this zone.
    morph_timer: float = field(default_factory=lambda: random.uniform(2.0, 3.0))


# ---------------------------------------------------------------------------
# Pattern drawing helpers
# ---------------------------------------------------------------------------

def _draw_stripes(
    draw: ImageDraw.ImageDraw,
    x: int,
    y: int,
    w: int,
    h: int,
    color1: Tuple[int, int, int],
    color2: Tuple[int, int, int],
    stripe_width: int = 3,
    horizontal: bool = False,
) -> None:
    """Draw alternating vertical or horizontal stripes inside the zone."""
    # Fill background with color2 first, then draw color1 stripes.
    draw.rectangle([x, y, x + w - 1, y + h - 1], fill=color2)
    if horizontal:
        row = 0
        while row < h:
            draw.rectangle(
                [x, y + row, x + w - 1, min(y + row + stripe_width - 1, y + h - 1)],
                fill=color1,
            )
            row += stripe_width * 2
    else:
        col = 0
        while col < w:
            draw.rectangle(
                [x + col, y, min(x + col + stripe_width - 1, x + w - 1), y + h - 1],
                fill=color1,
            )
            col += stripe_width * 2


def _draw_hatches(
    draw: ImageDraw.ImageDraw,
    x: int,
    y: int,
    w: int,
    h: int,
    color1: Tuple[int, int, int],
    color2: Tuple[int, int, int],
    angle: int = 45,
) -> None:
    """Draw diagonal hatch lines (45 or -45 degrees) inside the zone."""
    draw.rectangle([x, y, x + w - 1, y + h - 1], fill=color2)
    spacing = 4
    span = w + h  # lines need to cover the full diagonal
    for offset in range(-span, span, spacing):
        if angle > 0:
            # 45-degree: top-left to bottom-right direction
            x0 = x + offset
            y0 = y
            x1 = x + offset + h
            y1 = y + h
        else:
            # -45-degree: top-right to bottom-left direction
            x0 = x + w + offset
            y0 = y
            x1 = x + w + offset - h
            y1 = y + h
        draw.line([(x0, y0), (x1, y1)], fill=color1, width=1)
    # Re-mask the area outside the zone by redrawing borders.
    # Instead, we clip by drawing a rectangle *around* the zone.
    # Pillow doesn't support true clipping, so we accept minor bleed for speed.


def _draw_checkerboard(
    draw: ImageDraw.ImageDraw,
    x: int,
    y: int,
    w: int,
    h: int,
    color1: Tuple[int, int, int],
    color2: Tuple[int, int, int],
    cell_size: int = 4,
) -> None:
    """Draw a checkerboard pattern inside the zone."""
    for row in range(0, h, cell_size):
        for col in range(0, w, cell_size):
            c = color1 if (row // cell_size + col // cell_size) % 2 == 0 else color2
            rx = x + col
            ry = y + row
            draw.rectangle(
                [rx, ry, min(rx + cell_size - 1, x + w - 1), min(ry + cell_size - 1, y + h - 1)],
                fill=c,
            )


def _draw_solid(
    draw: ImageDraw.ImageDraw,
    x: int,
    y: int,
    w: int,
    h: int,
    color: Tuple[int, int, int],
) -> None:
    """Fill the zone with a single color."""
    draw.rectangle([x, y, x + w - 1, y + h - 1], fill=color)


# ---------------------------------------------------------------------------
# Color helpers
# ---------------------------------------------------------------------------

def _random_color_pair() -> Tuple[Tuple[int, int, int], Tuple[int, int, int]]:
    """Pick two distinct random colors from the palette."""
    c1, c2 = random.sample(PALETTE, 2)
    return c1, c2


def _brighten(color: Tuple[int, int, int], factor: float = 1.3) -> Tuple[int, int, int]:
    """Brighten a color by *factor*, clamping to 255."""
    return tuple(min(255, int(c * factor)) for c in color)  # type: ignore[return-value]


def _dim(color: Tuple[int, int, int], factor: float = 0.2) -> Tuple[int, int, int]:
    """Dim a color to *factor* of its original brightness."""
    return tuple(int(c * factor) for c in color)  # type: ignore[return-value]


def _lerp_color(
    a: Tuple[int, int, int], b: Tuple[int, int, int], t: float
) -> Tuple[int, int, int]:
    """Linearly interpolate between two colors.  *t* in [0, 1]."""
    t = max(0.0, min(1.0, t))
    return (
        int(a[0] + (b[0] - a[0]) * t),
        int(a[1] + (b[1] - a[1]) * t),
        int(a[2] + (b[2] - a[2]) * t),
    )


# ---------------------------------------------------------------------------
# Zone layout generator
# ---------------------------------------------------------------------------

def _generate_zones(width: int, height: int, count: int = 6) -> List[Zone]:
    """Generate a set of non-overlapping rectangular zones via recursive split.

    The algorithm starts with the full canvas and recursively splits
    rectangles either vertically or horizontally at random offsets until
    *count* zones have been produced.
    """
    rects: List[Tuple[int, int, int, int]] = [(0, 0, width, height)]

    while len(rects) < count:
        # Pick the largest rectangle to split.
        rects.sort(key=lambda r: r[2] * r[3], reverse=True)
        rx, ry, rw, rh = rects.pop(0)

        if rw >= rh and rw >= 8:
            # Vertical split.
            split = random.randint(max(4, rw // 4), rw - 4)
            rects.append((rx, ry, split, rh))
            rects.append((rx + split, ry, rw - split, rh))
        elif rh >= 8:
            # Horizontal split.
            split = random.randint(max(4, rh // 4), rh - 4)
            rects.append((rx, ry, rw, split))
            rects.append((rx, ry + split, rw, rh - split))
        else:
            # Too small to split, put it back.
            rects.insert(0, (rx, ry, rw, rh))
            break

    zones: List[Zone] = []
    for rx, ry, rw, rh in rects:
        pattern = random.choice(ALL_PATTERNS)
        c1, c2 = _random_color_pair()
        zones.append(Zone(x=rx, y=ry, width=rw, height=rh, pattern=pattern, color1=c1, color2=c2))
    return zones


# ---------------------------------------------------------------------------
# Main theme class
# ---------------------------------------------------------------------------

class CompositionTheme(ThemeRenderer):
    """Geometric composition theme -- Mondrian meets digital glitch."""

    def __init__(self, width: int = 64, height: int = 64) -> None:
        super().__init__(width, height)
        self._zones: List[Zone] = []
        self._time: float = 0.0
        # Track previous state for transition handling.
        self._prev_state: FaceState = FaceState.IDLE
        # Global phase accumulators used by various state animations.
        self._thinking_timer: float = 0.0
        self._error_flash_timer: float = 0.0
        self._speaking_phase: float = 0.0
        self._happy_phase: float = 0.0
        self._sleep_flicker_timer: float = 0.0
        self._sleep_flicker_zone: int = 0
        # Snapshot of zone layouts for THINKING shuffle.
        self._shuffle_interval: float = 0.15
        self._shuffle_timer: float = 0.0

    # ------------------------------------------------------------------
    # ThemeRenderer interface
    # ------------------------------------------------------------------

    @property
    def name(self) -> str:
        return "Composition"

    def on_activate(self) -> None:
        """Reset internal state and generate a fresh zone layout."""
        self._time = 0.0
        self._zones = _generate_zones(self.width, self.height, count=random.randint(5, 8))
        self._prev_state = FaceState.IDLE

    def on_deactivate(self) -> None:
        self._zones.clear()

    def set_state(self, state: FaceState) -> None:
        self._prev_state = self._current_state
        super().set_state(state)
        # On transition into certain states, reset their timers.
        if state == FaceState.THINKING:
            self._thinking_timer = 0.0
            self._shuffle_timer = 0.0
        elif state == FaceState.HAPPY:
            self._happy_phase = 0.0
        elif state == FaceState.SLEEPING:
            self._sleep_flicker_timer = random.uniform(3.0, 6.0)
            self._sleep_flicker_zone = random.randint(0, max(0, len(self._zones) - 1))

    # ------------------------------------------------------------------
    # Frame rendering
    # ------------------------------------------------------------------

    def draw_frame(self, dt: float) -> Image.Image:
        self._time += dt
        img = Image.new("RGB", (self.width, self.height), BACKGROUND)
        draw = ImageDraw.Draw(img)

        if not self._zones:
            return img

        state = self._current_state

        # Advance per-zone phase.
        for z in self._zones:
            z.phase += dt

        if state == FaceState.IDLE:
            self._update_idle(dt)
            self._draw_zones(draw, self._zones)

        elif state == FaceState.LISTENING:
            self._draw_listening(draw, dt)

        elif state == FaceState.THINKING:
            self._update_thinking(dt)
            self._draw_zones(draw, self._zones)

        elif state == FaceState.SPEAKING:
            self._draw_speaking(draw, dt)

        elif state == FaceState.ERROR:
            self._draw_error(draw, dt)

        elif state == FaceState.HAPPY:
            self._draw_happy(draw, dt)

        elif state == FaceState.SLEEPING:
            self._draw_sleeping(draw, dt)

        else:
            self._draw_zones(draw, self._zones)

        return img

    # ------------------------------------------------------------------
    # State-specific update / draw helpers
    # ------------------------------------------------------------------

    def _update_idle(self, dt: float) -> None:
        """In IDLE, occasionally morph one random zone."""
        for z in self._zones:
            z.morph_timer -= dt
            if z.morph_timer <= 0.0:
                # Morph this zone: change pattern and/or swap colors.
                if random.random() < 0.5:
                    z.pattern = random.choice(ALL_PATTERNS)
                else:
                    z.color1, z.color2 = z.color2, z.color1
                z.morph_timer = random.uniform(2.0, 3.0)

    def _draw_listening(self, draw: ImageDraw.ImageDraw, dt: float) -> None:
        """LISTENING: all zones become aligned vertical stripes, brighter."""
        for z in self._zones:
            c1 = _brighten(z.color1, 1.4)
            c2 = _brighten(z.color2, 1.2)
            _draw_stripes(draw, z.x, z.y, z.width, z.height, c1, c2, stripe_width=2, horizontal=False)

    def _update_thinking(self, dt: float) -> None:
        """THINKING: rapidly shuffle zone patterns and shift colors."""
        self._thinking_timer += dt
        self._shuffle_timer += dt
        if self._shuffle_timer >= self._shuffle_interval:
            self._shuffle_timer -= self._shuffle_interval
            for z in self._zones:
                z.pattern = random.choice(ALL_PATTERNS)
                # Shift colors through palette.
                idx = random.randint(0, len(PALETTE) - 1)
                z.color1 = PALETTE[idx]
                z.color2 = PALETTE[(idx + random.randint(1, len(PALETTE) - 1)) % len(PALETTE)]

    def _draw_speaking(self, draw: ImageDraw.ImageDraw, dt: float) -> None:
        """SPEAKING: patterns pulse with a ~2-second breathing rhythm."""
        self._speaking_phase += dt
        # Breathing cycle: sine wave with 2-second period.
        breath = (math.sin(self._speaking_phase * math.pi) + 1.0) / 2.0  # 0..1
        # Stripe width oscillates between 2 and 5.
        sw = int(2 + breath * 3)

        palette_offset = int(self._speaking_phase * 0.8) % len(PALETTE)
        for i, z in enumerate(self._zones):
            c1 = PALETTE[(palette_offset + i) % len(PALETTE)]
            c2 = PALETTE[(palette_offset + i + 1) % len(PALETTE)]
            # Use the zone's pattern but modulate stripe width.
            self._draw_zone_pattern(draw, z, c1_override=c1, c2_override=c2, stripe_width_override=sw)

    def _draw_error(self, draw: ImageDraw.ImageDraw, dt: float) -> None:
        """ERROR: flash between normal and red, with random glitch frames."""
        self._error_flash_timer += dt
        flash_on = int(self._error_flash_timer * 6) % 2 == 0  # ~3 Hz flash
        glitch = random.random() < 0.15  # 15% chance of glitch per frame

        for z in self._zones:
            if glitch:
                # Random scramble for this frame.
                pat = random.choice(ALL_PATTERNS)
                c1 = random.choice(PALETTE)
                c2 = random.choice(PALETTE)
                self._draw_one_zone(draw, z, pattern_override=pat, c1_override=c1, c2_override=c2)
            elif flash_on:
                _draw_solid(draw, z.x, z.y, z.width, z.height, (255, 0, 0))
            else:
                self._draw_one_zone(draw, z)

    def _draw_happy(self, draw: ImageDraw.ImageDraw, dt: float) -> None:
        """HAPPY: all zones checkerboard with rainbow-cycling colors."""
        self._happy_phase += dt
        for i, z in enumerate(self._zones):
            offset = int(self._happy_phase * 3 + i) % len(PALETTE)
            c1 = PALETTE[offset]
            c2 = PALETTE[(offset + 3) % len(PALETTE)]
            _draw_checkerboard(draw, z.x, z.y, z.width, z.height, c1, c2, cell_size=4)

    # Dark palette for sleeping — no dimming, just dark colors
    _SLEEP_COLORS: list[tuple[int, int, int]] = [
        (20, 25, 50),    # deep navy
        (30, 35, 55),    # dark slate
        (15, 20, 40),    # midnight
        (25, 30, 60),    # dark blue
        (35, 25, 45),    # dark plum
    ]

    def _draw_sleeping(self, draw: ImageDraw.ImageDraw, dt: float) -> None:
        """SLEEPING: dark-palette zones with occasional faint flicker."""
        self._sleep_flicker_timer -= dt
        flicker_active = False
        if self._sleep_flicker_timer <= 0.0:
            if self._sleep_flicker_timer > -0.15:
                flicker_active = True
            else:
                self._sleep_flicker_timer = random.uniform(3.0, 6.0)
                self._sleep_flicker_zone = random.randint(0, max(0, len(self._zones) - 1))

        for i, z in enumerate(self._zones):
            c1 = self._SLEEP_COLORS[i % len(self._SLEEP_COLORS)]
            c2 = self._SLEEP_COLORS[(i + 2) % len(self._SLEEP_COLORS)]
            if flicker_active and i == self._sleep_flicker_zone:
                # Slightly brighter variant for flicker
                c1 = (c1[0] + 25, c1[1] + 25, c1[2] + 30)
                c2 = (c2[0] + 25, c2[1] + 25, c2[2] + 30)
            self._draw_one_zone(draw, z, c1_override=c1, c2_override=c2)

    # ------------------------------------------------------------------
    # Zone drawing dispatch
    # ------------------------------------------------------------------

    def _draw_zones(self, draw: ImageDraw.ImageDraw, zones: List[Zone]) -> None:
        """Draw all zones with their current pattern and colors."""
        for z in zones:
            self._draw_one_zone(draw, z)

    def _draw_one_zone(
        self,
        draw: ImageDraw.ImageDraw,
        z: Zone,
        *,
        pattern_override: PatternType | None = None,
        c1_override: Tuple[int, int, int] | None = None,
        c2_override: Tuple[int, int, int] | None = None,
        stripe_width_override: int | None = None,
    ) -> None:
        """Draw a single zone, optionally overriding its stored properties."""
        pat = pattern_override or z.pattern
        c1 = c1_override or z.color1
        c2 = c2_override or z.color2
        sw = stripe_width_override or 3
        self._draw_zone_pattern(draw, z, pat_override=pat, c1_override=c1, c2_override=c2, stripe_width_override=sw)

    def _draw_zone_pattern(
        self,
        draw: ImageDraw.ImageDraw,
        z: Zone,
        *,
        pat_override: PatternType | None = None,
        c1_override: Tuple[int, int, int] | None = None,
        c2_override: Tuple[int, int, int] | None = None,
        stripe_width_override: int | None = None,
    ) -> None:
        """Dispatch to the correct pattern drawing function."""
        pat = pat_override or z.pattern
        c1 = c1_override or z.color1
        c2 = c2_override or z.color2
        sw = stripe_width_override or 3

        if pat == PatternType.STRIPES_V:
            _draw_stripes(draw, z.x, z.y, z.width, z.height, c1, c2, stripe_width=sw, horizontal=False)
        elif pat == PatternType.STRIPES_H:
            _draw_stripes(draw, z.x, z.y, z.width, z.height, c1, c2, stripe_width=sw, horizontal=True)
        elif pat == PatternType.HATCHES_45:
            _draw_hatches(draw, z.x, z.y, z.width, z.height, c1, c2, angle=45)
        elif pat == PatternType.HATCHES_N45:
            _draw_hatches(draw, z.x, z.y, z.width, z.height, c1, c2, angle=-45)
        elif pat == PatternType.CHECKERBOARD:
            _draw_checkerboard(draw, z.x, z.y, z.width, z.height, c1, c2, cell_size=4)
        elif pat == PatternType.SOLID:
            _draw_solid(draw, z.x, z.y, z.width, z.height, c1)
