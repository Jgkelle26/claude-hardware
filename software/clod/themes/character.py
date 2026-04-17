"""Character theme — chunky pixel robot with strong personality and expressive animations.

A De Stijl-inspired robot character with rectangular face plate, white eyes
with black pupils, colored hat/mouth/legs, and a full range of emotive
animations driven by :class:`FaceState`.
"""

from __future__ import annotations

import math
import random
import time
from dataclasses import dataclass, field, fields

from PIL import Image, ImageDraw

from clod.events import FaceState
from clod.themes.base import ThemeRenderer

# ---------------------------------------------------------------------------
# Color schemes — randomly selected on each activation
# ---------------------------------------------------------------------------

COLOR_SCHEMES: list[dict[str, tuple[int, int, int]]] = [
    {
        "face": (0, 100, 255),
        "hat": (255, 204, 0),
        "mouth": (0, 180, 80),
        "leg_l": (255, 0, 0),
        "leg_r": (0, 200, 200),
        "accent": (255, 102, 0),
    },
    {
        "face": (255, 204, 0),
        "hat": (0, 200, 200),
        "mouth": (0, 100, 255),
        "leg_l": (0, 100, 255),
        "leg_r": (255, 204, 0),
        "accent": (255, 0, 0),
    },
    {
        "face": (0, 180, 80),
        "hat": (220, 100, 220),
        "mouth": (0, 100, 255),
        "leg_l": (255, 0, 0),
        "leg_r": (0, 200, 200),
        "accent": (255, 204, 0),
    },
    {
        "face": (255, 0, 0),
        "hat": (255, 204, 0),
        "mouth": (0, 100, 255),
        "leg_l": (255, 140, 180),
        "leg_r": (0, 100, 255),
        "accent": (0, 180, 80),
    },
    {
        "face": (255, 204, 0),
        "hat": (0, 180, 80),
        "mouth": (255, 0, 0),
        "leg_l": (255, 140, 180),
        "leg_r": (0, 100, 255),
        "accent": (0, 200, 200),
    },
    {
        "face": (0, 200, 200),
        "hat": (255, 0, 0),
        "mouth": (255, 204, 0),
        "leg_l": (0, 180, 80),
        "leg_r": (255, 0, 0),
        "accent": (0, 100, 255),
    },
]

# Eye / pupil constants
EYE_COLOR: tuple[int, int, int] = (255, 255, 255)
PUPIL_COLOR: tuple[int, int, int] = (0, 0, 0)
BG_COLOR: tuple[int, int, int] = (0, 0, 0)

# ---------------------------------------------------------------------------
# Character anatomy constants (pixel positions on 64x64 canvas)
# ---------------------------------------------------------------------------

# All positions are relative to a horizontally centered character.
CANVAS = 64

# Hat
HAT_WIDTH = 34
HAT_HEIGHT = 4
HAT_Y = 6

# Face plate
FACE_WIDTH = 44
FACE_HEIGHT = 24
FACE_Y = 10

# Eyes (relative to face plate top-left)
EYE_WIDTH = 10
EYE_HEIGHT = 8
EYE_Y = 14  # absolute y of eye top
EYE_LEFT_X = (CANVAS - FACE_WIDTH) // 2 + 5   # 15
EYE_RIGHT_X = (CANVAS + FACE_WIDTH) // 2 - 5 - EYE_WIDTH  # 39

# Pupils
PUPIL_SIZE = 3

# Mouth
MOUTH_WIDTH = 36
MOUTH_HEIGHT = 4
MOUTH_Y = 28

# Legs
LEG_WIDTH = 4
LEG_HEIGHT = 14
LEG_Y = 34
LEG_LEFT_X = (CANVAS // 2) - 12
LEG_RIGHT_X = (CANVAS // 2) + 8

# Centered x helpers
FACE_X = (CANVAS - FACE_WIDTH) // 2
HAT_X = (CANVAS - HAT_WIDTH) // 2
MOUTH_X = (CANVAS - MOUTH_WIDTH) // 2


# ---------------------------------------------------------------------------
# Animated character state
# ---------------------------------------------------------------------------

@dataclass
class CharacterState:
    """All animatable parameters for the character."""

    left_pupil_x: float = 0.0      # offset from eye center, -3..+3
    left_pupil_y: float = 0.0      # offset from eye center, -2..+2
    right_pupil_x: float = 0.0
    right_pupil_y: float = 0.0
    left_eye_height: float = 1.0   # 1.0 = full, 0.0 = closed
    right_eye_height: float = 1.0
    mouth_width: float = 1.0       # 0.5 = narrow, 1.0 = normal, 1.2 = wide
    mouth_y_offset: float = 0.0    # 0 = normal, +2 = dropped (surprised)
    body_y_offset: float = 0.0     # 0 = normal, -2 = bouncing up
    left_leg_angle: float = 0.0    # -0.3..0.3 radians
    right_leg_angle: float = 0.0
    hat_y_offset: float = 0.0      # 0 = normal, -2 = popped up


# Per-state target presets
_STATE_TARGETS: dict[FaceState, CharacterState] = {
    FaceState.IDLE: CharacterState(
        left_pupil_x=0.0, left_pupil_y=0.0,
        right_pupil_x=0.0, right_pupil_y=0.0,
        left_eye_height=1.0, right_eye_height=1.0,
        mouth_width=1.0, mouth_y_offset=0.0,
        body_y_offset=0.0,
        left_leg_angle=0.0, right_leg_angle=0.0,
        hat_y_offset=0.0,
    ),
    FaceState.LISTENING: CharacterState(
        left_pupil_x=0.0, left_pupil_y=0.0,
        right_pupil_x=0.0, right_pupil_y=0.0,
        left_eye_height=1.0, right_eye_height=1.0,
        mouth_width=1.0, mouth_y_offset=0.0,
        body_y_offset=0.0,
        left_leg_angle=0.0, right_leg_angle=0.0,
        hat_y_offset=0.0,
    ),
    FaceState.THINKING: CharacterState(
        left_pupil_x=-2.0, left_pupil_y=-1.5,
        right_pupil_x=-2.0, right_pupil_y=-1.5,
        left_eye_height=0.7, right_eye_height=1.0,
        mouth_width=0.8, mouth_y_offset=0.0,
        body_y_offset=-1.0,
        left_leg_angle=0.15, right_leg_angle=-0.1,
        hat_y_offset=0.0,
    ),
    FaceState.SPEAKING: CharacterState(
        left_pupil_x=0.0, left_pupil_y=0.0,
        right_pupil_x=0.0, right_pupil_y=0.0,
        left_eye_height=1.0, right_eye_height=1.0,
        mouth_width=1.0, mouth_y_offset=0.0,
        body_y_offset=0.0,
        left_leg_angle=0.0, right_leg_angle=0.0,
        hat_y_offset=0.0,
    ),
    FaceState.ERROR: CharacterState(
        left_pupil_x=2.0, left_pupil_y=0.0,
        right_pupil_x=-2.0, right_pupil_y=0.0,
        left_eye_height=0.5, right_eye_height=1.0,
        mouth_width=0.7, mouth_y_offset=3.0,
        body_y_offset=2.0,
        left_leg_angle=0.25, right_leg_angle=-0.25,
        hat_y_offset=0.0,
    ),
    FaceState.HAPPY: CharacterState(
        left_pupil_x=0.0, left_pupil_y=0.0,
        right_pupil_x=0.0, right_pupil_y=0.0,
        left_eye_height=0.3, right_eye_height=0.3,
        mouth_width=1.2, mouth_y_offset=0.0,
        body_y_offset=0.0,
        left_leg_angle=0.0, right_leg_angle=0.0,
        hat_y_offset=-2.0,
    ),
    FaceState.SLEEPING: CharacterState(
        left_pupil_x=0.0, left_pupil_y=0.0,
        right_pupil_x=0.0, right_pupil_y=0.0,
        left_eye_height=0.1, right_eye_height=0.1,
        mouth_width=0.6, mouth_y_offset=0.0,
        body_y_offset=1.0,
        left_leg_angle=0.1, right_leg_angle=-0.1,
        hat_y_offset=0.0,
    ),
}


# ---------------------------------------------------------------------------
# Sleep Z particle
# ---------------------------------------------------------------------------

@dataclass
class _ZParticle:
    """A tiny 'z' that floats upward from the sleeping character."""

    x: float
    y: float
    age: float = 0.0
    lifetime: float = 2.5


# ---------------------------------------------------------------------------
# Interpolation helpers
# ---------------------------------------------------------------------------

def _lerp(a: float, b: float, t: float) -> float:
    """Linear interpolation."""
    return a + (b - a) * t


def _clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


def _lerp_state(current: CharacterState, target: CharacterState, t: float) -> CharacterState:
    """Interpolate all fields between two CharacterState instances."""
    kwargs: dict[str, float] = {}
    for f in fields(CharacterState):
        cur_val = getattr(current, f.name)
        tgt_val = getattr(target, f.name)
        kwargs[f.name] = _lerp(cur_val, tgt_val, t)
    return CharacterState(**kwargs)


# ---------------------------------------------------------------------------
# Theme implementation
# ---------------------------------------------------------------------------

class CharacterTheme(ThemeRenderer):
    """Chunky pixel robot character with personality-driven animations."""

    def __init__(self, width: int = 64, height: int = 64) -> None:
        super().__init__(width, height)
        self._colors: dict[str, tuple[int, int, int]] = COLOR_SCHEMES[0]
        self._state = CharacterState()
        self._target = CharacterState()
        self._time: float = 0.0

        # Blink tracking
        self._next_blink_at: float = 0.0
        self._blink_started_at: float | None = None

        # Sarcastic squint tracking
        self._next_squint_at: float = 0.0
        self._squint_started_at: float | None = None
        self._squint_eye: str = "left"  # which eye squints

        # Idle pupil drift target
        self._drift_target_x: float = 0.0
        self._drift_target_y: float = 0.0
        self._next_drift_at: float = 0.0

        # Speaking mouth cycle
        self._speak_phase: float = 0.0

        # Happy bounce / leg kick
        self._happy_phase: float = 0.0

        # Sleep Z particles
        self._z_particles: list[_ZParticle] = []
        self._next_z_at: float = 0.0

        # Sleep flutter
        self._next_flutter_at: float = 0.0
        self._flutter_started_at: float | None = None

        self._reset_timers()

    # ------------------------------------------------------------------
    # ThemeRenderer interface
    # ------------------------------------------------------------------

    @property
    def name(self) -> str:
        return "Character"

    def on_activate(self) -> None:
        self._colors = random.choice(COLOR_SCHEMES)
        self._state = CharacterState()
        self._target = CharacterState()
        self._time = 0.0
        self._z_particles = []
        self._speak_phase = 0.0
        self._happy_phase = 0.0
        self._reset_timers()

    def on_deactivate(self) -> None:
        self._z_particles = []

    def set_state(self, state: FaceState) -> None:
        super().set_state(state)
        self._target = CharacterState(
            **{f.name: getattr(_STATE_TARGETS[state], f.name) for f in fields(CharacterState)}
        )
        # Reset speak phase on entering speaking
        if state == FaceState.SPEAKING:
            self._speak_phase = 0.0
        if state == FaceState.HAPPY:
            self._happy_phase = 0.0
        if state == FaceState.IDLE:
            self._reset_timers()

    # ------------------------------------------------------------------
    # Drawing
    # ------------------------------------------------------------------

    def draw_frame(self, dt: float) -> Image.Image:
        now = time.monotonic()
        self._time += dt

        # 1. Smooth interpolation toward target
        self._state = _lerp_state(self._state, self._target, 0.10)

        # 2. Apply state-specific behaviours
        self._apply_idle_behaviours(now, dt)
        self._apply_speaking_behaviours(dt)
        self._apply_happy_behaviours(dt)
        self._apply_sleeping_behaviours(now, dt)
        self._apply_idle_bounce(dt)

        # 3. Render
        img = Image.new("RGB", (self.width, self.height), BG_COLOR)
        draw = ImageDraw.Draw(img)

        by = int(round(self._state.body_y_offset))

        self._draw_hat(draw, by)
        self._draw_face(draw, by)
        self._draw_eyes(draw, by)
        self._draw_mouth(draw, by)
        self._draw_legs(draw, by)

        # Sleep Z particles on top
        if self._current_state == FaceState.SLEEPING:
            self._draw_z_particles(draw, dt)

        return img

    # ------------------------------------------------------------------
    # State-specific behaviour updates
    # ------------------------------------------------------------------

    def _reset_timers(self) -> None:
        now = time.monotonic()
        self._next_blink_at = now + random.uniform(3.0, 7.0)
        self._blink_started_at = None
        self._next_squint_at = now + random.uniform(10.0, 20.0)
        self._squint_started_at = None
        self._next_drift_at = now + random.uniform(1.0, 3.0)
        self._drift_target_x = 0.0
        self._drift_target_y = 0.0
        self._next_z_at = now + random.uniform(0.5, 1.5)
        self._next_flutter_at = now + random.uniform(4.0, 8.0)
        self._flutter_started_at = None

    def _apply_idle_behaviours(self, now: float, dt: float) -> None:
        """Blink, pupil drift, and sarcastic squint for IDLE state."""
        if self._current_state != FaceState.IDLE:
            self._blink_started_at = None
            self._squint_started_at = None
            return

        # --- Blink ---
        if self._blink_started_at is not None:
            elapsed = now - self._blink_started_at
            if elapsed < 0.10:
                # Eyes closed during blink
                self._state.left_eye_height = 0.0
                self._state.right_eye_height = 0.0
            else:
                # Blink done
                self._blink_started_at = None
                self._next_blink_at = now + random.uniform(3.0, 7.0)
        elif now >= self._next_blink_at:
            self._blink_started_at = now
            self._state.left_eye_height = 0.0
            self._state.right_eye_height = 0.0

        # --- Sarcastic squint ---
        if self._squint_started_at is not None:
            elapsed = now - self._squint_started_at
            if elapsed < 1.0:
                if self._squint_eye == "left":
                    self._state.left_eye_height = _lerp(
                        self._state.left_eye_height, 0.5, 0.15,
                    )
                else:
                    self._state.right_eye_height = _lerp(
                        self._state.right_eye_height, 0.5, 0.15,
                    )
            else:
                self._squint_started_at = None
                self._next_squint_at = now + random.uniform(10.0, 20.0)
        elif now >= self._next_squint_at:
            self._squint_started_at = now
            self._squint_eye = random.choice(["left", "right"])

        # --- Pupil drift ---
        if now >= self._next_drift_at:
            self._drift_target_x = random.uniform(-2.0, 2.0)
            self._drift_target_y = random.uniform(-1.5, 1.5)
            self._next_drift_at = now + random.uniform(2.0, 4.0)

        self._state.left_pupil_x = _lerp(self._state.left_pupil_x, self._drift_target_x, 0.03)
        self._state.left_pupil_y = _lerp(self._state.left_pupil_y, self._drift_target_y, 0.03)
        self._state.right_pupil_x = _lerp(self._state.right_pupil_x, self._drift_target_x, 0.03)
        self._state.right_pupil_y = _lerp(self._state.right_pupil_y, self._drift_target_y, 0.03)

    def _apply_idle_bounce(self, dt: float) -> None:
        """Gentle body bounce and leg sway in IDLE."""
        if self._current_state != FaceState.IDLE:
            return
        # Body bounce: +-1px at ~0.5Hz
        bounce = math.sin(self._time * math.pi) * 1.0
        self._state.body_y_offset = _lerp(self._state.body_y_offset, bounce, 0.08)
        # Leg sway: gentle alternating angles
        self._state.left_leg_angle = _lerp(
            self._state.left_leg_angle,
            math.sin(self._time * 1.2) * 0.1,
            0.06,
        )
        self._state.right_leg_angle = _lerp(
            self._state.right_leg_angle,
            math.sin(self._time * 1.2 + math.pi) * 0.1,
            0.06,
        )

    def _apply_speaking_behaviours(self, dt: float) -> None:
        """Mouth pulse and body bounce during SPEAKING."""
        if self._current_state != FaceState.SPEAKING:
            return
        self._speak_phase += dt * 3.0 * math.tau  # ~3Hz
        # Mouth width oscillates 0.8 -> 1.2 -> 0.8
        mouth_target = 1.0 + 0.2 * math.sin(self._speak_phase)
        self._state.mouth_width = _lerp(self._state.mouth_width, mouth_target, 0.2)
        # Slight body bounce with speech
        bounce = math.sin(self._speak_phase * 0.5) * 0.8
        self._state.body_y_offset = _lerp(self._state.body_y_offset, bounce, 0.1)

    def _apply_happy_behaviours(self, dt: float) -> None:
        """Rapid bounce and alternating leg kicks during HAPPY."""
        if self._current_state != FaceState.HAPPY:
            return
        self._happy_phase += dt * 2.0 * math.tau  # ~2Hz
        # Body bounce +-2px
        self._state.body_y_offset = math.sin(self._happy_phase) * 2.0
        # Alternating leg kicks
        self._state.left_leg_angle = math.sin(self._happy_phase) * 0.3
        self._state.right_leg_angle = math.sin(self._happy_phase + math.pi) * 0.3

    def _apply_sleeping_behaviours(self, now: float, dt: float) -> None:
        """Eye flutter and Z particle spawning during SLEEPING."""
        if self._current_state != FaceState.SLEEPING:
            self._z_particles = []
            return

        # Eye flutter
        if self._flutter_started_at is not None:
            elapsed = now - self._flutter_started_at
            if elapsed < 0.15:
                self._state.left_eye_height = 0.2
                self._state.right_eye_height = 0.2
            else:
                self._flutter_started_at = None
                self._next_flutter_at = now + random.uniform(4.0, 8.0)
        elif now >= self._next_flutter_at:
            self._flutter_started_at = now

        # Spawn Z particles
        if now >= self._next_z_at:
            self._z_particles.append(_ZParticle(
                x=float(CANVAS // 2 + 18 + random.randint(-2, 2)),
                y=float(FACE_Y - 2),
            ))
            self._next_z_at = now + random.uniform(1.0, 2.0)

        # Update existing particles
        alive: list[_ZParticle] = []
        for zp in self._z_particles:
            zp.age += dt
            zp.y -= dt * 6.0  # float upward
            zp.x += math.sin(zp.age * 2.0) * dt * 3.0  # gentle sway
            if zp.age < zp.lifetime and zp.y > 0:
                alive.append(zp)
        self._z_particles = alive

    # ------------------------------------------------------------------
    # Rendering helpers
    # ------------------------------------------------------------------

    def _draw_hat(self, draw: ImageDraw.ImageDraw, by: int) -> None:
        y = HAT_Y + by + int(round(self._state.hat_y_offset))
        x = HAT_X
        draw.rectangle([x, y, x + HAT_WIDTH - 1, y + HAT_HEIGHT - 1], fill=self._colors["hat"])

    def _draw_face(self, draw: ImageDraw.ImageDraw, by: int) -> None:
        y = FACE_Y + by
        draw.rectangle([FACE_X, y, FACE_X + FACE_WIDTH - 1, y + FACE_HEIGHT - 1], fill=self._colors["face"])

    def _draw_eyes(self, draw: ImageDraw.ImageDraw, by: int) -> None:
        is_happy = self._current_state == FaceState.HAPPY
        self._draw_single_eye(
            draw, EYE_LEFT_X, EYE_Y + by,
            self._state.left_eye_height,
            self._state.left_pupil_x, self._state.left_pupil_y,
            is_happy,
        )
        self._draw_single_eye(
            draw, EYE_RIGHT_X, EYE_Y + by,
            self._state.right_eye_height,
            self._state.right_pupil_x, self._state.right_pupil_y,
            is_happy,
        )

    def _draw_single_eye(
        self,
        draw: ImageDraw.ImageDraw,
        ex: int,
        ey: int,
        height_factor: float,
        pupil_ox: float,
        pupil_oy: float,
        happy: bool,
    ) -> None:
        """Draw one eye with its pupil."""
        if height_factor < 0.05:
            # Eye fully closed — draw thin slit
            mid_y = ey + EYE_HEIGHT // 2
            draw.rectangle([ex, mid_y, ex + EYE_WIDTH - 1, mid_y], fill=EYE_COLOR)
            return

        actual_h = max(1, int(round(EYE_HEIGHT * _clamp(height_factor, 0.0, 1.2))))

        if happy and height_factor < 0.5:
            # Happy crescent: thin filled bar at the BOTTOM of the eye area (^_^ shape)
            crescent_h = max(1, min(actual_h, 3))
            cy = ey + EYE_HEIGHT - crescent_h
            draw.rectangle([ex, cy, ex + EYE_WIDTH - 1, cy + crescent_h - 1], fill=EYE_COLOR)
            return

        # Normal eye: white rectangle, vertically centered in the eye area
        y_offset = (EYE_HEIGHT - actual_h) // 2
        ey_top = ey + y_offset
        draw.rectangle([ex, ey_top, ex + EYE_WIDTH - 1, ey_top + actual_h - 1], fill=EYE_COLOR)

        # Pupil: 3x3 black square centered in eye + offset, clamped inside
        eye_cx = ex + EYE_WIDTH // 2
        eye_cy = ey_top + actual_h // 2
        px = int(round(eye_cx + pupil_ox)) - PUPIL_SIZE // 2
        py = int(round(eye_cy + pupil_oy)) - PUPIL_SIZE // 2

        # Clamp pupil inside the eye rectangle
        px = int(_clamp(px, ex, ex + EYE_WIDTH - PUPIL_SIZE))
        py = int(_clamp(py, ey_top, ey_top + actual_h - PUPIL_SIZE))

        # Only draw pupil if the eye is open enough
        if actual_h >= PUPIL_SIZE:
            draw.rectangle([px, py, px + PUPIL_SIZE - 1, py + PUPIL_SIZE - 1], fill=PUPIL_COLOR)

    def _draw_mouth(self, draw: ImageDraw.ImageDraw, by: int) -> None:
        w = max(4, int(round(MOUTH_WIDTH * self._state.mouth_width)))
        x = (CANVAS - w) // 2
        y = MOUTH_Y + by + int(round(self._state.mouth_y_offset))

        # During speaking, cycle between mouth color and accent color
        if self._current_state == FaceState.SPEAKING:
            cycle = math.sin(self._speak_phase) * 0.5 + 0.5  # 0..1
            mc = self._colors["mouth"]
            ac = self._colors["accent"]
            color = (
                int(mc[0] + (ac[0] - mc[0]) * cycle),
                int(mc[1] + (ac[1] - mc[1]) * cycle),
                int(mc[2] + (ac[2] - mc[2]) * cycle),
            )
        else:
            color = self._colors["mouth"]

        draw.rectangle([x, y, x + w - 1, y + MOUTH_HEIGHT - 1], fill=color)

    def _draw_legs(self, draw: ImageDraw.ImageDraw, by: int) -> None:
        self._draw_single_leg(
            draw, LEG_LEFT_X, LEG_Y + by,
            self._state.left_leg_angle, self._colors["leg_l"],
        )
        self._draw_single_leg(
            draw, LEG_RIGHT_X, LEG_Y + by,
            self._state.right_leg_angle, self._colors["leg_r"],
        )

    def _draw_single_leg(
        self,
        draw: ImageDraw.ImageDraw,
        lx: int,
        ly: int,
        angle: float,
        color: tuple[int, int, int],
    ) -> None:
        """Draw a leg as a polygon with the bottom offset by angle."""
        # Top is fixed; bottom shifts horizontally by angle * height
        bottom_shift = int(round(angle * LEG_HEIGHT))
        # Four corners of the leg polygon
        top_left = (lx, ly)
        top_right = (lx + LEG_WIDTH - 1, ly)
        bottom_right = (lx + LEG_WIDTH - 1 + bottom_shift, ly + LEG_HEIGHT - 1)
        bottom_left = (lx + bottom_shift, ly + LEG_HEIGHT - 1)
        draw.polygon([top_left, top_right, bottom_right, bottom_left], fill=color)

    def _draw_z_particles(self, draw: ImageDraw.ImageDraw, dt: float) -> None:
        """Draw small 'z' zigzag pixels floating upward."""
        for zp in self._z_particles:
            # Fade based on age
            alpha = 1.0 - (zp.age / zp.lifetime)
            brightness = int(_clamp(alpha * 255, 0, 255))
            if brightness < 20:
                continue
            color = (brightness, brightness, brightness)
            ix = int(round(zp.x))
            iy = int(round(zp.y))
            # Draw a tiny 'z' shape: 3 pixels in a zigzag
            # Top-right, center, bottom-left
            if 0 <= ix + 1 < CANVAS and 0 <= iy < CANVAS:
                draw.point((ix + 1, iy), fill=color)
            if 0 <= ix < CANVAS and 0 <= iy + 1 < CANVAS:
                draw.point((ix, iy + 1), fill=color)
            if 0 <= ix + 1 < CANVAS and 0 <= iy + 2 < CANVAS:
                draw.point((ix + 1, iy + 2), fill=color)
