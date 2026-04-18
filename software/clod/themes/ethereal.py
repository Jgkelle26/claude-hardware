"""Ethereal theme — a field of cross/plus shapes drifting on a dark canvas."""

from __future__ import annotations

import logging
import math
import random
from dataclasses import dataclass

from PIL import Image

from clod.events import FaceState
from clod.themes.base import ThemeRenderer

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Color palettes
# ---------------------------------------------------------------------------

PALETTE: list[tuple[int, int, int]] = [
    (70, 200, 190),    # teal
    (240, 155, 40),    # warm orange
    (240, 240, 240),   # white
    (170, 170, 175),   # light gray
    (110, 110, 115),   # medium gray
]

BACKGROUND: tuple[int, int, int] = (22, 22, 28)  # deep charcoal

SLEEPING_PALETTE: list[tuple[int, int, int]] = [
    (25, 55, 65),      # deep teal
    (45, 50, 70),      # dark slate blue
    (55, 60, 75),      # dim steel
    (30, 35, 50),      # dark navy
]

THINKING_PALETTE: list[tuple[int, int, int]] = [
    (50, 160, 200),    # electric blue
    (80, 120, 210),    # bright indigo
    (120, 200, 220),   # light cyan
    (200, 220, 240),   # ice white
]

# Cluster centers — shapes spawn around these focal points
# to create dense blocks with negative space between them
_NUM_CLUSTERS: int = 4

# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------


@dataclass
class Shape:
    """A single cross/plus shape on the canvas."""

    x: float               # center position (fractional, 0-63)
    y: float
    vx: float              # velocity px/s
    vy: float
    size: int              # 0=dot, 1=tiny(3x3), 2=small(5x5), 3=medium(7x7)
    color: tuple[int, int, int]
    opacity: float         # 0.0=invisible, 1.0=fully visible
    age: float             # seconds alive
    lifetime: float        # seconds until fade-out begins (-1 = immortal)
    _fading_out: bool = False
    _fade_out_timer: float = 0.0
    _size_boost: int = 0          # temporary size increase for speaking pulse
    _size_boost_timer: float = 0.0


# ---------------------------------------------------------------------------
# Shape drawing — pixel offsets for each cross size
# ---------------------------------------------------------------------------

# Each entry is a list of (dx, dy) offsets from center.

_CROSS_DOT: list[tuple[int, int]] = [
    (0, 0),
]

_CROSS_DOT_2X2: list[tuple[int, int]] = [
    (0, 0), (1, 0), (0, 1), (1, 1),
]

_CROSS_TINY: list[tuple[int, int]] = [
    # .X.
    # XXX
    # .X.
    (0, -1),
    (-1, 0), (0, 0), (1, 0),
    (0, 1),
]

_CROSS_SMALL: list[tuple[int, int]] = [
    # ..X..
    # ..X..
    # XXXXX
    # ..X..
    # ..X..
    (0, -2), (0, -1),
    (-2, 0), (-1, 0), (0, 0), (1, 0), (2, 0),
    (0, 1), (0, 2),
]

_CROSS_MEDIUM: list[tuple[int, int]] = [
    # 2px-wide arms, 7 tall / 7 wide (actually 6 wide, 7 tall with 2px width)
    # Vertical arm: columns -1,0 spanning rows -3 to +3
    # Horizontal arm: rows -1,0 spanning columns -3 to +3
    # Vertical arm (2px wide)
    (-1, -3), (0, -3),
    (-1, -2), (0, -2),
    (-1, -1), (0, -1),
    (-1, 0), (0, 0),
    (-1, 1), (0, 1),
    (-1, 2), (0, 2),
    (-1, 3), (0, 3),
    # Horizontal arm (2px tall) — skip center overlap already drawn
    (-3, -1), (-3, 0),
    (-2, -1), (-2, 0),
    # (-1, -1), (-1, 0) already above
    # (0, -1), (0, 0) already above
    (1, -1), (1, 0),
    (2, -1), (2, 0),
    (3, -1), (3, 0),
]

_CROSS_PATTERNS: list[list[tuple[int, int]]] = [
    _CROSS_DOT,      # size 0 — but we pick dot vs 2x2 at draw time
    _CROSS_TINY,     # size 1
    _CROSS_SMALL,    # size 2
    _CROSS_MEDIUM,   # size 3
]

# ---------------------------------------------------------------------------
# State configuration
# ---------------------------------------------------------------------------

_STATE_TARGET_COUNT: dict[FaceState, int] = {
    FaceState.IDLE: 65,
    FaceState.LISTENING: 45,
    FaceState.THINKING: 120,
    FaceState.SPEAKING: 60,
    FaceState.ERROR: 30,
    FaceState.HAPPY: 80,
    FaceState.SLEEPING: 20,
}

# Size distribution weights per state: [dot, tiny, small, medium]
_STATE_SIZE_WEIGHTS: dict[FaceState, list[float]] = {
    FaceState.IDLE: [0.20, 0.40, 0.30, 0.10],
    FaceState.LISTENING: [0.10, 0.25, 0.40, 0.25],
    FaceState.THINKING: [0.35, 0.45, 0.15, 0.05],
    FaceState.SPEAKING: [0.20, 0.40, 0.30, 0.10],
    FaceState.ERROR: [0.50, 0.30, 0.15, 0.05],
    FaceState.HAPPY: [0.15, 0.30, 0.35, 0.20],
    FaceState.SLEEPING: [0.50, 0.50, 0.00, 0.00],
}


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------

def _clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


def _weighted_choice(rng: random.Random, weights: list[float]) -> int:
    """Return an index chosen by cumulative weights."""
    r = rng.random()
    cumulative = 0.0
    for i, w in enumerate(weights):
        cumulative += w
        if r <= cumulative:
            return i
    return len(weights) - 1


def _blend_color(
    color: tuple[int, int, int],
    bg: tuple[int, int, int],
    opacity: float,
) -> tuple[int, int, int]:
    """Blend color with background by opacity."""
    inv = 1.0 - opacity
    return (
        int(color[0] * opacity + bg[0] * inv),
        int(color[1] * opacity + bg[1] * inv),
        int(color[2] * opacity + bg[2] * inv),
    )


def _desaturate(
    color: tuple[int, int, int],
    amount: float,
    target: tuple[int, int, int] = (110, 110, 115),
) -> tuple[int, int, int]:
    """Blend a color toward a gray target by *amount* (0=original, 1=fully gray)."""
    inv = 1.0 - amount
    return (
        int(color[0] * inv + target[0] * amount),
        int(color[1] * inv + target[1] * amount),
        int(color[2] * inv + target[2] * amount),
    )


# ---------------------------------------------------------------------------
# Theme implementation
# ---------------------------------------------------------------------------


class EtherealTheme(ThemeRenderer):
    """Ethereal — a drifting field of cross/plus shapes on charcoal."""

    def __init__(self, width: int = 64, height: int = 64) -> None:
        super().__init__(width, height)
        self._shapes: list[Shape] = []
        self._time: float = 0.0
        self._rng: random.Random = random.Random(42)
        self._next_idle_swap: float = 0.0
        self._speaking_wave_timer: float = 0.0
        self._happy_emit_timer: float = 0.0
        self._sleeping_firefly_timer: float = 0.0
        self._sleeping_firefly_idx: int = -1
        # Cluster focal points — regenerated on activate
        self._clusters: list[tuple[float, float]] = []

    # ------------------------------------------------------------------
    # ThemeRenderer interface
    # ------------------------------------------------------------------

    @property
    def name(self) -> str:
        return "Ethereal"

    def set_state(self, state: FaceState) -> None:
        prev = self._current_state
        super().set_state(state)
        if state != prev:
            self._on_state_change(prev, state)

    def on_activate(self) -> None:
        """Spawn initial shapes clustered around focal points."""
        self._shapes = []
        self._time = 0.0
        self._next_idle_swap = self._rng.uniform(1.0, 2.5)
        self._speaking_wave_timer = 0.0
        self._happy_emit_timer = 0.0
        self._sleeping_firefly_timer = 0.0
        self._sleeping_firefly_idx = -1

        # Generate cluster centers — spread across the canvas
        self._clusters = [
            (self._rng.uniform(8, 56), self._rng.uniform(8, 56))
            for _ in range(_NUM_CLUSTERS)
        ]

        count = self._rng.randint(55, 70)
        weights = _STATE_SIZE_WEIGHTS[FaceState.IDLE]
        for _ in range(count):
            self._shapes.append(self._spawn_shape(weights, PALETTE))

    def on_deactivate(self) -> None:
        self._shapes = []

    def draw_frame(self, dt: float) -> Image.Image:
        self._time += dt
        state = self._current_state

        # --- Physics & lifecycle ---
        self._update_shapes(dt, state)

        # --- State-specific behaviors ---
        self._apply_state_behavior(dt, state)

        # --- Manage population ---
        self._manage_population(dt, state)

        # --- Render ---
        return self._render()

    # ------------------------------------------------------------------
    # State change handler
    # ------------------------------------------------------------------

    def _on_state_change(self, prev: FaceState, new: FaceState) -> None:
        """React to state transitions."""
        if new == FaceState.HAPPY:
            self._happy_emit_timer = 0.0
        if new == FaceState.THINKING:
            # Regenerate cluster centers for a fresh arrangement
            self._clusters = [
                (self._rng.uniform(10, 54), self._rng.uniform(10, 54))
                for _ in range(_NUM_CLUSTERS)
            ]
        if new == FaceState.SLEEPING:
            self._sleeping_firefly_timer = self._rng.uniform(2.0, 5.0)
            self._sleeping_firefly_idx = -1

    # ------------------------------------------------------------------
    # Shape spawning
    # ------------------------------------------------------------------

    def _spawn_shape(
        self,
        size_weights: list[float],
        palette: list[tuple[int, int, int]],
        x: float | None = None,
        y: float | None = None,
        vx: float | None = None,
        vy: float | None = None,
        lifetime: float = -1.0,
        clustered: bool = True,
    ) -> Shape:
        """Create a new shape. By default, places near a random cluster center."""
        if x is None and clustered and self._clusters:
            # Pick a random cluster center, gaussian scatter around it
            cx, cy = self._rng.choice(self._clusters)
            x = cx + self._rng.gauss(0, 8)
            y = cy + self._rng.gauss(0, 8)
            x = x % 64.0
            y = y % 64.0
        elif x is None:
            x = self._rng.uniform(0.0, 63.0)
        if y is None:
            y = self._rng.uniform(0.0, 63.0)
        if vx is None:
            vx = self._rng.uniform(-0.6, 0.6)
        if vy is None:
            vy = self._rng.uniform(-0.6, 0.6)
        size = _weighted_choice(self._rng, size_weights)
        color = palette[self._rng.randint(0, len(palette) - 1)]
        if lifetime < 0:
            lifetime = self._rng.uniform(5.0, 15.0)
        return Shape(
            x=x, y=y, vx=vx, vy=vy,
            size=size, color=color,
            opacity=0.0,  # fade in from 0
            age=0.0, lifetime=lifetime,
        )

    # ------------------------------------------------------------------
    # Physics & lifecycle update
    # ------------------------------------------------------------------

    def _update_shapes(self, dt: float, state: FaceState) -> None:
        """Advance positions, handle fading, remove dead shapes."""
        to_remove: list[int] = []
        for i, s in enumerate(self._shapes):
            s.age += dt

            # Fade in (first 0.15s — snappy)
            if s.age < 0.15 and not s._fading_out:
                s.opacity = min(1.0, s.age / 0.15)

            # Check lifetime — begin fade out
            if s.lifetime > 0 and s.age >= s.lifetime and not s._fading_out:
                s._fading_out = True
                s._fade_out_timer = 0.0

            # Fade out over 0.25s — smooth but quick
            if s._fading_out:
                s._fade_out_timer += dt
                s.opacity = max(0.0, 1.0 - s._fade_out_timer / 0.25)
                if s.opacity <= 0.0:
                    to_remove.append(i)
                    continue

            # Size boost decay (speaking pulse)
            if s._size_boost_timer > 0:
                s._size_boost_timer -= dt
                if s._size_boost_timer <= 0:
                    s._size_boost = 0
                    s._size_boost_timer = 0.0

            # Move
            s.x += s.vx * dt
            s.y += s.vy * dt

            # Wrap at edges
            s.x = s.x % 64.0
            s.y = s.y % 64.0

        # Remove dead shapes (iterate in reverse to keep indices valid)
        for i in reversed(to_remove):
            self._shapes.pop(i)

    # ------------------------------------------------------------------
    # State-specific behaviors
    # ------------------------------------------------------------------

    def _apply_state_behavior(self, dt: float, state: FaceState) -> None:
        if state == FaceState.IDLE:
            self._behavior_idle(dt)
        elif state == FaceState.LISTENING:
            self._behavior_listening(dt)
        elif state == FaceState.THINKING:
            self._behavior_thinking(dt)
        elif state == FaceState.SPEAKING:
            self._behavior_speaking(dt)
        elif state == FaceState.ERROR:
            self._behavior_error(dt)
        elif state == FaceState.HAPPY:
            self._behavior_happy(dt)
        elif state == FaceState.SLEEPING:
            self._behavior_sleeping(dt)

    def _behavior_idle(self, dt: float) -> None:
        """Gentle breathing and occasional shape swap."""
        # Breathing: opacity oscillates 0.90 - 1.0 (no dimming, subtle)
        breath = 0.90 + 0.10 * (math.sin(self._time * 1.5) + 1.0) / 2.0
        for s in self._shapes:
            if not s._fading_out and s.age >= 0.15:
                s.opacity = breath

        # Frequent swap: fade one out, spawn one elsewhere (faster turnover)
        self._next_idle_swap -= dt
        if self._next_idle_swap <= 0:
            self._next_idle_swap = self._rng.uniform(1.0, 2.0)
            # Mark a random non-fading shape for death
            candidates = [s for s in self._shapes if not s._fading_out]
            if candidates:
                victim = self._rng.choice(candidates)
                victim._fading_out = True
                victim._fade_out_timer = 0.0

    def _behavior_listening(self, dt: float) -> None:
        """Pull shapes toward center, dampen velocities, shift to white/gray."""
        cx, cy = 32.0, 32.0
        for s in self._shapes:
            # Gentle pull toward center
            s.vx += (cx - s.x) * 0.01 * dt * 60.0
            s.vy += (cy - s.y) * 0.01 * dt * 60.0
            # Dampen
            s.vx *= (1.0 - 0.5 * dt)
            s.vy *= (1.0 - 0.5 * dt)

    def _behavior_thinking(self, dt: float) -> None:
        """Processing — shapes converge into clusters then scatter and reform.

        Uses THINKING_PALETTE (electric blues). Shapes pull toward the
        nearest cluster center, creating dense blocks that assemble and
        rearrange. Periodically the cluster targets shift, causing shapes
        to break apart and reassemble elsewhere — like thoughts forming.
        """
        # Shift cluster targets every 2-3 seconds to create reassembly
        if int(self._time * 0.4) != int((self._time - dt) * 0.4):
            # Move one random cluster center to a new position
            if self._clusters:
                idx = self._rng.randint(0, len(self._clusters) - 1)
                self._clusters[idx] = (
                    self._rng.uniform(6, 58),
                    self._rng.uniform(6, 58),
                )

        for s in self._shapes:
            # Find nearest cluster center
            best_dist = 999.0
            best_cx, best_cy = 32.0, 32.0
            for ccx, ccy in self._clusters:
                d = math.sqrt((s.x - ccx) ** 2 + (s.y - ccy) ** 2)
                if d < best_dist:
                    best_dist = d
                    best_cx, best_cy = ccx, ccy

            dx = best_cx - s.x
            dy = best_cy - s.y
            dist = math.sqrt(dx * dx + dy * dy) + 0.01

            # Strong pull toward nearest cluster — shapes assemble
            pull_strength = 0.25
            s.vx += (dx / dist) * pull_strength * dt * 60.0
            s.vy += (dy / dist) * pull_strength * dt * 60.0

            # Add slight tangential swirl for visual interest
            tx = -dy / dist
            ty = dx / dist
            s.vx += tx * 0.08 * dt * 60.0
            s.vy += ty * 0.08 * dt * 60.0

            # When very close to cluster center, jitter to avoid collapse
            if dist < 5.0:
                s.vx += self._rng.uniform(-0.5, 0.5) * dt * 60.0
                s.vy += self._rng.uniform(-0.5, 0.5) * dt * 60.0

            # Speed cap
            speed = math.sqrt(s.vx * s.vx + s.vy * s.vy)
            max_speed = 2.5
            if speed > max_speed:
                s.vx = s.vx / speed * max_speed
                s.vy = s.vy / speed * max_speed

    def _behavior_speaking(self, dt: float) -> None:
        """Pulsing wave radiating from center every ~1s."""
        self._speaking_wave_timer += dt
        if self._speaking_wave_timer >= 1.0:
            self._speaking_wave_timer -= 1.0
            # Launch a wave: boost shapes near each radial distance band
            cx, cy = 32.0, 32.0
            wave_radius = 0.0  # starts at center
            # We encode the wave as size boosts applied right now
            # based on distance — shapes close to center get boosted first,
            # farther shapes get boosted with a delay (encoded in _size_boost_timer)
            amp = max(0.3, self._amplitude)
            for s in self._shapes:
                dx = s.x - cx
                dy = s.y - cy
                dist = math.sqrt(dx * dx + dy * dy)
                # Delay = dist / wave_speed; wave takes ~0.5s to cross 32px
                delay = dist / 64.0  # 0 at center, 0.5 at edge
                boost = 1 if self._rng.random() < amp else 0
                if boost and s.size < 3:
                    s._size_boost = 1
                    s._size_boost_timer = 0.2 + delay

    def _behavior_error(self, dt: float) -> None:
        """Shapes drift outward from center and desaturate."""
        cx, cy = 32.0, 32.0
        for s in self._shapes:
            s.vx += (s.x - cx) * 0.005 * dt * 60.0
            s.vy += (s.y - cy) * 0.005 * dt * 60.0
            # Gentle speed cap
            speed = math.sqrt(s.vx * s.vx + s.vy * s.vy)
            if speed > 0.4:
                s.vx = s.vx / speed * 0.4
                s.vy = s.vy / speed * 0.4

    def _behavior_happy(self, dt: float) -> None:
        """Fireworks — continuous emission from bottom, shapes arc upward."""
        self._happy_emit_timer += dt
        # Emit a batch from the bottom every 0.15s
        if self._happy_emit_timer >= 0.15:
            self._happy_emit_timer -= 0.15
            bright_palette = [PALETTE[0], PALETTE[1], PALETTE[2]]  # teal, orange, white
            weights = [0.15, 0.30, 0.35, 0.20]
            emit_count = self._rng.randint(3, 6)
            for _ in range(emit_count):
                # Spawn from bottom edge, random x
                spawn_x = self._rng.uniform(8.0, 56.0)
                angle = self._rng.uniform(-0.8, 0.8)  # fan upward, slight spread
                speed = self._rng.uniform(3.0, 6.0)
                s = self._spawn_shape(
                    weights, bright_palette,
                    x=spawn_x,
                    y=62.0 + self._rng.uniform(0, 2),
                    vx=math.sin(angle) * speed * 0.5,
                    vy=-speed,  # upward
                    lifetime=self._rng.uniform(2.0, 4.0),
                    clustered=False,
                )
                self._shapes.append(s)

        # Apply gravity — shapes arc and slow down as they rise
        for s in self._shapes:
            s.vy += 1.5 * dt  # gentle gravity pulls back down
            s.vx *= (1.0 - 0.5 * dt)  # horizontal drag

    def _behavior_sleeping(self, dt: float) -> None:
        """Very slow, sparse, occasional firefly flash."""
        # Nearly stop all motion
        for s in self._shapes:
            s.vx *= (1.0 - 2.0 * dt)
            s.vy *= (1.0 - 2.0 * dt)

        # Firefly effect — one shape brightens to white briefly
        self._sleeping_firefly_timer -= dt
        if self._sleeping_firefly_timer <= 0:
            self._sleeping_firefly_timer = self._rng.uniform(3.0, 6.0)
            if self._shapes:
                self._sleeping_firefly_idx = self._rng.randint(
                    0, len(self._shapes) - 1
                )
            else:
                self._sleeping_firefly_idx = -1

    # ------------------------------------------------------------------
    # Population management
    # ------------------------------------------------------------------

    def _manage_population(self, dt: float, state: FaceState) -> None:
        """Spawn or despawn shapes to match the target count for the current state."""
        target = _STATE_TARGET_COUNT.get(state, 50)
        alive = [s for s in self._shapes if not s._fading_out]
        count = len(alive)

        if count < target:
            # Spawn new shapes to fill gap (up to 5 per frame — faster turnover)
            if state == FaceState.SLEEPING:
                palette = SLEEPING_PALETTE
            elif state == FaceState.THINKING:
                palette = THINKING_PALETTE
            else:
                palette = PALETTE
            weights = _STATE_SIZE_WEIGHTS.get(state, [0.20, 0.40, 0.30, 0.10])
            to_spawn = min(target - count, 5)
            for _ in range(to_spawn):
                s = self._spawn_shape(weights, palette)
                # For thinking, use faster velocities
                if state == FaceState.THINKING:
                    s.vx = self._rng.uniform(-1.2, 1.2)
                    s.vy = self._rng.uniform(-1.2, 1.2)
                elif state == FaceState.SLEEPING:
                    s.vx = self._rng.uniform(-0.02, 0.02)
                    s.vy = self._rng.uniform(-0.02, 0.02)
                elif state == FaceState.LISTENING:
                    # Bias toward white/light gray
                    if self._rng.random() < 0.5:
                        s.color = self._rng.choice(PALETTE[2:4])
                elif state == FaceState.HAPPY:
                    # Brighter colors
                    if self._rng.random() < 0.5:
                        s.color = self._rng.choice(PALETTE[:3])
                self._shapes.append(s)
        elif count > target:
            # Mark oldest non-fading shapes for fadeout
            surplus = count - target
            alive_sorted = sorted(alive, key=lambda s: s.age, reverse=True)
            for s in alive_sorted[:surplus]:
                s._fading_out = True
                s._fade_out_timer = 0.0

    # ------------------------------------------------------------------
    # Rendering
    # ------------------------------------------------------------------

    def _render(self) -> Image.Image:
        """Draw all shapes to a bytearray buffer and return a PIL Image."""
        bg = BACKGROUND
        # Initialize buffer with background color
        buf = bytearray(64 * 64 * 3)
        for i in range(64 * 64):
            offset = i * 3
            buf[offset] = bg[0]
            buf[offset + 1] = bg[1]
            buf[offset + 2] = bg[2]

        state = self._current_state

        for idx, s in enumerate(self._shapes):
            if s.opacity < 0.01:
                continue

            # Determine effective color
            color = s.color
            opacity = s.opacity

            # State-specific color modifications
            if state == FaceState.ERROR:
                color = _desaturate(color, 0.5)
            elif state == FaceState.SLEEPING:
                # Firefly effect
                if idx == self._sleeping_firefly_idx:
                    # Pulse to white over 0.5s then fade back
                    pulse_phase = self._sleeping_firefly_timer
                    # Timer counts down, so just after reset it's large.
                    # The firefly is the shape at this index; make it bright
                    # for a brief window. We use the timer value to create a pulse:
                    # timer goes from ~5 down to 0; firefly is "on" when timer is
                    # in the last 0.5s before it resets... but timer resets at 0.
                    # Instead, track it with a simple brightness boost based on age.
                    time_since_chosen = self._sleeping_firefly_timer
                    # Since timer counts down and we pick a new firefly when it hits 0,
                    # the firefly should glow throughout its period. Use a sine pulse.
                    glow = max(0.0, math.sin(self._time * 4.0))
                    if glow > 0.5:
                        color = (240, 240, 240)
                        opacity = 1.0

            # Blend with background
            drawn = _blend_color(color, bg, opacity)

            # Determine draw size (with boost for speaking)
            draw_size = min(3, s.size + s._size_boost)

            cx = int(s.x)
            cy = int(s.y)

            # Get pixel offsets for this size
            if draw_size == 0:
                # Dots: alternate between 1x1 and 2x2
                if (cx + cy) % 2 == 0:
                    pixels = _CROSS_DOT
                else:
                    pixels = _CROSS_DOT_2X2
            else:
                pixels = _CROSS_PATTERNS[draw_size]

            # Draw pixels
            r, g, b = drawn
            for dx, dy in pixels:
                px = cx + dx
                py = cy + dy
                # Clip to canvas
                if 0 <= px < 64 and 0 <= py < 64:
                    off = (py * 64 + px) * 3
                    buf[off] = r
                    buf[off + 1] = g
                    buf[off + 2] = b

        return Image.frombytes("RGB", (64, 64), bytes(buf))
