"""Bear theme -- Radiohead modified bear logo.

A pixel-art rendering of the iconic Radiohead bear on the 64x64 RGB LED
matrix.  The bear is drawn as bright outlines on a dark background with
large round eyes, donut ears, and a zigzag saw-tooth grin.  Animation is
driven by pupil offsets, eye scale, mouth amplitude, and whole-face shift
parameters that lerp smoothly between target values.
"""

from __future__ import annotations

import math
import random
import time
from dataclasses import dataclass, field

from PIL import Image, ImageDraw

from clod.events import FaceState
from clod.themes.base import ThemeRenderer


# ---------------------------------------------------------------------------
# Animatable face parameters
# ---------------------------------------------------------------------------

@dataclass
class BearState:
    """All animatable parameters for the bear face."""

    left_pupil_x: float = 0.0
    left_pupil_y: float = 0.0
    right_pupil_x: float = 0.0
    right_pupil_y: float = 0.0
    left_eye_scale: float = 1.0
    right_eye_scale: float = 1.0
    mouth_offset_y: float = 0.0
    mouth_open: float = 1.0
    face_shift_x: float = 0.0
    face_shift_y: float = 0.0

    def lerp_towards(self, target: BearState, factor: float) -> None:
        """Interpolate every field towards *target* by *factor* (0..1)."""
        for attr in (
            "left_pupil_x", "left_pupil_y",
            "right_pupil_x", "right_pupil_y",
            "left_eye_scale", "right_eye_scale",
            "mouth_offset_y", "mouth_open",
            "face_shift_x", "face_shift_y",
        ):
            cur = getattr(self, attr)
            tgt = getattr(target, attr)
            setattr(self, attr, cur + (tgt - cur) * factor)


# ---------------------------------------------------------------------------
# Per-state color palettes
# ---------------------------------------------------------------------------

STATE_COLORS: dict[FaceState, dict[str, tuple[int, int, int]]] = {
    FaceState.IDLE:      {"bg": (15, 15, 20),   "outline": (220, 220, 230)},
    FaceState.LISTENING: {"bg": (15, 15, 20),   "outline": (255, 255, 255)},
    FaceState.THINKING:  {"bg": (12, 15, 30),   "outline": (100, 160, 255)},
    FaceState.SPEAKING:  {"bg": (20, 15, 15),   "outline": (255, 150, 100)},
    FaceState.ERROR:     {"bg": (20, 8, 8),     "outline": (255, 40, 40)},
    FaceState.HAPPY:     {"bg": (12, 12, 15),   "outline": (255, 255, 255)},
    FaceState.SLEEPING:  {"bg": (10, 10, 12),   "outline": (120, 120, 130)},
}

LISTENING_COLORS: list[tuple[int, int, int]] = [
    (255, 255, 255),   # white
    (60, 240, 255),    # bright cyan
    (255, 220, 50),    # bright yellow
    (255, 100, 200),   # hot pink
    (100, 255, 150),   # bright green
    (0, 0, 0),         # black
]

SPEAKING_COLORS: list[tuple[int, int, int]] = [
    (255, 230, 50),    # yellow
    (180, 80, 255),    # purple
    (255, 255, 255),   # white
]

ERROR_COLORS: list[tuple[int, int, int]] = [
    (255, 40, 40),     # red
    (255, 255, 255),   # white
    (0, 0, 0),         # black
]

THINKING_COLORS: list[tuple[int, int, int]] = [
    (40, 40, 50),      # dark gray (visible but dim)
    (255, 255, 255),   # white
]

IDLE_COLORS: list[tuple[int, int, int]] = [
    (220, 220, 230),   # white
]

import colorsys


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _lerp_color(
    a: tuple[int, int, int],
    b: tuple[int, int, int],
    t: float,
) -> tuple[int, int, int]:
    """Linearly interpolate between two RGB colors."""
    return (
        int(a[0] + (b[0] - a[0]) * t),
        int(a[1] + (b[1] - a[1]) * t),
        int(a[2] + (b[2] - a[2]) * t),
    )


def _clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


# ---------------------------------------------------------------------------
# Theme implementation
# ---------------------------------------------------------------------------

class BearTheme(ThemeRenderer):
    """Radiohead modified-bear logo rendered as animated pixel art."""

    def __init__(self, width: int = 64, height: int = 64) -> None:
        super().__init__(width, height)

        # Animation state
        self._current: BearState = BearState()
        self._target: BearState = BearState()

        # Smooth color transitions
        self._current_bg: tuple[int, int, int] = STATE_COLORS[FaceState.IDLE]["bg"]
        self._current_outline: tuple[int, int, int] = STATE_COLORS[FaceState.IDLE]["outline"]

        # Timing
        self._time: float = 0.0

        # Idle behaviour bookkeeping
        self._idle_pupil_target_x: float = 0.0
        self._idle_pupil_target_y: float = 0.0
        self._idle_next_pupil_change: float = 0.0
        self._idle_next_blink: float = 0.0
        self._idle_blinking: bool = False
        self._idle_blink_end: float = 0.0

        # Sleeping flutter bookkeeping
        self._sleep_next_flutter: float = 0.0
        self._sleep_flutter_end: float = 0.0

    # ------------------------------------------------------------------
    # ThemeRenderer interface
    # ------------------------------------------------------------------

    @property
    def name(self) -> str:
        return "Bear"

    def on_activate(self) -> None:
        self._current = BearState()
        self._target = BearState()
        self._current_bg = STATE_COLORS[FaceState.IDLE]["bg"]
        self._current_outline = STATE_COLORS[FaceState.IDLE]["outline"]
        self._time = 0.0
        self._idle_next_pupil_change = 0.0
        self._idle_next_blink = random.uniform(2.0, 5.0)
        self._idle_blinking = False
        self._sleep_next_flutter = random.uniform(4.0, 8.0)

    def on_deactivate(self) -> None:
        pass

    def set_state(self, state: FaceState) -> None:
        super().set_state(state)

    # ------------------------------------------------------------------
    # Frame rendering
    # ------------------------------------------------------------------

    def draw_frame(self, dt: float) -> Image.Image:
        self._time += dt
        t: float = self._time
        state: FaceState = self._current_state

        # --- Update target BearState based on current FaceState ---
        self._update_target(state, t, dt)

        # --- Lerp current towards target ---
        self._current.lerp_towards(self._target, min(1.0, 10.0 * dt))

        # --- Lerp colors ---
        colors = STATE_COLORS.get(state, STATE_COLORS[FaceState.IDLE])
        target_bg = colors["bg"]
        color_lerp = min(1.0, 5.0 * dt)
        self._current_bg = _lerp_color(self._current_bg, target_bg, color_lerp)

        target_outline = colors["outline"]
        self._current_outline = _lerp_color(self._current_outline, target_outline, color_lerp)

        # --- Draw ---
        return self._draw_frame(self._current)

    # ------------------------------------------------------------------
    # Target state updaters per FaceState
    # ------------------------------------------------------------------

    def _update_target(self, state: FaceState, t: float, dt: float) -> None:
        tgt = self._target

        if state == FaceState.IDLE:
            self._update_idle(tgt, t, dt)
        elif state == FaceState.LISTENING:
            self._update_listening(tgt, t)
        elif state == FaceState.THINKING:
            self._update_thinking(tgt, t)
        elif state == FaceState.SPEAKING:
            self._update_speaking(tgt, t)
        elif state == FaceState.ERROR:
            self._update_error(tgt, t)
        elif state == FaceState.HAPPY:
            self._update_happy(tgt, t)
        elif state == FaceState.SLEEPING:
            self._update_sleeping(tgt, t, dt)

    # --- IDLE ---

    def _update_idle(self, tgt: BearState, t: float, dt: float) -> None:
        # Pupils drift to random target every 2-4 seconds
        if t >= self._idle_next_pupil_change:
            self._idle_pupil_target_x = random.uniform(-2.5, 2.5)
            self._idle_pupil_target_y = random.uniform(-2.0, 2.0)
            self._idle_next_pupil_change = t + random.uniform(2.0, 4.0)

        tgt.left_pupil_x = self._idle_pupil_target_x
        tgt.left_pupil_y = self._idle_pupil_target_y
        tgt.right_pupil_x = self._idle_pupil_target_x
        tgt.right_pupil_y = self._idle_pupil_target_y

        # Blinking
        if not self._idle_blinking and t >= self._idle_next_blink:
            self._idle_blinking = True
            self._idle_blink_end = t + 0.1
        if self._idle_blinking:
            tgt.left_eye_scale = 0.0
            tgt.right_eye_scale = 0.0
            if t >= self._idle_blink_end:
                self._idle_blinking = False
                self._idle_next_blink = t + random.uniform(3.0, 7.0)
        else:
            tgt.left_eye_scale = 1.0
            tgt.right_eye_scale = 1.0

        # Subtle body bounce
        tgt.face_shift_y = math.sin(t * math.tau * 0.5) * 1.0
        tgt.face_shift_x = 0.0

        tgt.mouth_open = 1.0
        tgt.mouth_offset_y = 0.0

    # --- LISTENING ---

    def _update_listening(self, tgt: BearState, t: float) -> None:
        tgt.left_pupil_x = 0.0
        tgt.left_pupil_y = 0.0
        tgt.right_pupil_x = 0.0
        tgt.right_pupil_y = 0.0
        tgt.left_eye_scale = 1.1
        tgt.right_eye_scale = 1.1
        tgt.face_shift_y = -2.0
        tgt.face_shift_x = math.sin(t * math.tau * 0.2) * 2.0
        tgt.mouth_open = 1.0
        tgt.mouth_offset_y = 0.0

    # --- THINKING ---

    def _update_thinking(self, tgt: BearState, t: float) -> None:
        tgt.left_pupil_x = -2.0
        tgt.left_pupil_y = -1.5
        tgt.right_pupil_x = -2.0
        tgt.right_pupil_y = -1.5
        tgt.left_eye_scale = 0.85
        tgt.right_eye_scale = 1.0
        tgt.face_shift_x = math.sin(t * math.tau * 0.3) * 3.0
        tgt.face_shift_y = math.sin(t * math.tau * 0.15) * 1.0
        tgt.mouth_open = 1.0
        tgt.mouth_offset_y = 0.0

    # --- SPEAKING ---

    def _update_speaking(self, tgt: BearState, t: float) -> None:
        # Mouth oscillates at ~3 Hz between 0.6 and 1.0
        mouth_phase = math.sin(t * math.tau * 3.0)
        tgt.mouth_open = 0.8 + 0.2 * mouth_phase

        # Also modulate with amplitude if available
        tgt.mouth_open = _clamp(
            tgt.mouth_open + self._amplitude * 0.3, 0.4, 1.2,
        )

        # Face turns left/right
        turn = math.sin(t * math.tau * 0.3) * 3.0
        tgt.face_shift_x = turn
        tgt.face_shift_y = math.sin(t * math.tau * 0.5) * 1.0

        # Pupils track face turn
        tgt.left_pupil_x = turn * 0.3
        tgt.right_pupil_x = turn * 0.3
        tgt.left_pupil_y = 0.0
        tgt.right_pupil_y = 0.0

        tgt.left_eye_scale = 1.0
        tgt.right_eye_scale = 1.0
        tgt.mouth_offset_y = 0.0

    # --- ERROR ---

    def _update_error(self, tgt: BearState, t: float) -> None:
        tgt.left_eye_scale = 0.6
        tgt.right_eye_scale = 1.0
        tgt.left_pupil_x = 2.0
        tgt.left_pupil_y = 0.0
        tgt.right_pupil_x = -2.0
        tgt.right_pupil_y = 0.0
        tgt.mouth_offset_y = 2.0
        tgt.mouth_open = 0.4
        tgt.face_shift_x = 0.0
        tgt.face_shift_y = math.sin(t * math.tau * 0.2) * 1.0 + 1.0

    # --- HAPPY ---

    def _update_happy(self, tgt: BearState, t: float) -> None:
        tgt.left_eye_scale = 0.3
        tgt.right_eye_scale = 0.3
        tgt.left_pupil_x = 0.0
        tgt.left_pupil_y = 0.0
        tgt.right_pupil_x = 0.0
        tgt.right_pupil_y = 0.0
        tgt.mouth_open = 1.2
        tgt.mouth_offset_y = 0.0
        tgt.face_shift_x = 0.0
        tgt.face_shift_y = math.sin(t * math.tau * 2.0) * 2.0

    # --- SLEEPING ---

    def _update_sleeping(self, tgt: BearState, t: float, dt: float) -> None:
        tgt.left_eye_scale = 0.1
        tgt.right_eye_scale = 0.1
        tgt.left_pupil_x = 0.0
        tgt.left_pupil_y = 0.0
        tgt.right_pupil_x = 0.0
        tgt.right_pupil_y = 0.0
        tgt.mouth_open = 0.1
        tgt.mouth_offset_y = 0.0
        # Gentle bob — stays within the safe area
        tgt.face_shift_x = math.sin(t * 0.3) * 3.0
        tgt.face_shift_y = math.cos(t * 0.2) * 2.5

        # Occasional eye flutter
        if t >= self._sleep_next_flutter:
            tgt.left_eye_scale = 0.2
            tgt.right_eye_scale = 0.2
            self._sleep_flutter_end = t + 0.15
            self._sleep_next_flutter = t + random.uniform(5.0, 10.0)
        if t < getattr(self, "_sleep_flutter_end", 0.0):
            tgt.left_eye_scale = 0.2
            tgt.right_eye_scale = 0.2

    # ------------------------------------------------------------------
    # Drawing
    # ------------------------------------------------------------------

    def _draw_frame(self, st: BearState) -> Image.Image:
        img = Image.new("RGB", (self.width, self.height), self._current_bg)
        draw = ImageDraw.Draw(img)

        # Scale factor — makes bear smaller and keeps it away from edges
        S = 0.8
        # Clamp shift so the bear stays within safe area
        max_shift = 4
        sx = int(round(_clamp(st.face_shift_x, -max_shift, max_shift)))
        sy = int(round(_clamp(st.face_shift_y, -max_shift, max_shift)))
        color = self._current_outline

        # --- Depth gradient for face turns ---
        # Near side gets brighter outline; we compute two colors.
        turn = st.face_shift_x
        bright_boost = min(40, int(abs(turn) * 8))
        if turn > 0:
            # Face turned right -- left side is "near"
            color_near = tuple(min(255, c + bright_boost) for c in color)
            color_far = tuple(max(0, c - bright_boost // 2) for c in color)
        elif turn < 0:
            color_near = tuple(min(255, c + bright_boost) for c in color)
            color_far = tuple(max(0, c - bright_boost // 2) for c in color)
        else:
            color_near = color
            color_far = color

        # We'll use a helper to pick per-element color based on x position
        def _side_color(x: int) -> tuple[int, int, int]:
            cx = 32 + sx
            if turn > 0.5:
                # Near side = left
                t_val = _clamp((cx - x) / 30.0, 0.0, 1.0)
            elif turn < -0.5:
                # Near side = right
                t_val = _clamp((x - cx) / 30.0, 0.0, 1.0)
            else:
                return color
            return _lerp_color(color_far, color_near, t_val)

        hcx, hcy = 32 + sx, int(36 * S + 32 * (1 - S)) + sy
        hr = int(22 * S)

        # Scaled positions relative to center (32, 32)
        def sc(val: float) -> int:
            return int(32 + (val - 32) * S)

        # --- Ears (drawn first, then head covers the overlap) ---
        for ear_x in (15, 49):
            ex = sc(ear_x) + sx
            ey = sc(13) + sy
            ear_r_out = int(10 * S)
            ear_r_in = int(6 * S)
            ear_color = _side_color(ex)
            draw.ellipse(
                [ex - ear_r_out, ey - ear_r_out, ex + ear_r_out, ey + ear_r_out],
                outline=ear_color, width=2,
            )
            draw.ellipse(
                [ex - ear_r_in, ey - ear_r_in, ex + ear_r_in, ey + ear_r_in],
                outline=ear_color, width=2,
            )

        # --- Head circle (filled bg to cover ear overlap, then outline) ---
        draw.ellipse(
            [hcx - hr, hcy - hr, hcx + hr, hcy + hr],
            fill=self._current_bg, outline=color, width=2,
        )

        # --- Eyes ---
        for eye_cx, scale, px, py in [
            (22, st.left_eye_scale, st.left_pupil_x, st.left_pupil_y),
            (42, st.right_eye_scale, st.right_pupil_x, st.right_pupil_y),
        ]:
            ecx = sc(eye_cx) + sx
            ecy = sc(33) + sy
            eye_color = _side_color(ecx)

            if scale < 0.15:
                closed_r = int(8 * S)
                draw.line(
                    [(ecx - closed_r, ecy), (ecx + closed_r, ecy)],
                    fill=eye_color, width=2,
                )
            elif scale < 0.4:
                arc_r = int((10 * scale + 3) * S)
                draw.arc(
                    [ecx - arc_r, ecy - arc_r, ecx + arc_r, ecy + arc_r],
                    start=10, end=170, fill=eye_color, width=2,
                )
            else:
                er = int(10 * scale * S)
                draw.ellipse(
                    [ecx - er, ecy - er, ecx + er, ecy + er],
                    outline=eye_color, width=2,
                )
                bar_half_w = max(1, int(2 * S))
                bar_half_h = int(6 * min(scale, 1.0) * S)
                pcx = ecx + int(round(px * S))
                pcy = ecy + int(round(py * S))
                draw.rounded_rectangle(
                    [pcx - bar_half_w, pcy - bar_half_h,
                     pcx + bar_half_w, pcy + bar_half_h],
                    radius=2,
                    fill=eye_color,
                )

        # --- Upper lip line and mouth ---
        lip_y = sc(43) + sy + int(round(st.mouth_offset_y * 0.5 * S))
        lip_start_x = sc(12) + sx
        lip_end_x = sc(52) + sx
        lip_mid_x = 32 + sx
        lip_sag = int(2 * st.mouth_open * S)
        lip_bottom = lip_y + lip_sag

        if self._current_state != FaceState.SLEEPING:
            draw.line(
                [(lip_start_x, lip_y), (lip_mid_x, lip_bottom), (lip_end_x, lip_y)],
                fill=color, width=2,
            )

        mouth_top = lip_bottom + 2
        mouth_amp = int(6 * st.mouth_open * S)

        if mouth_amp < 1:
            draw.line(
                [(sc(14) + sx, mouth_top), (sc(50) + sx, mouth_top)],
                fill=color, width=2,
            )
        elif self._current_state != FaceState.SLEEPING:
            num_teeth = 6
            mouth_width = int(36 * S)
            tooth_width = mouth_width // num_teeth
            start_x = sc(14) + sx
            points: list[tuple[int, int]] = []
            for i in range(num_teeth + 1):
                x = start_x + i * tooth_width
                if i % 2 == 0:
                    y = mouth_top  # peaks touch just below lip
                else:
                    y = mouth_top + mouth_amp  # valleys extend down
                points.append((x, y))
            draw.line(points, fill=color, width=2)

        # --- Pixel-level color static for LISTENING, HAPPY, SPEAKING ---
        if self._current_state in (FaceState.IDLE, FaceState.LISTENING, FaceState.HAPPY, FaceState.SPEAKING, FaceState.ERROR, FaceState.THINKING):
            img = self._apply_pixel_static(img)

        return img

    def _apply_pixel_static(self, img: Image.Image) -> Image.Image:
        """Replace each bear pixel with a random color — TV static effect."""
        pixels = img.load()
        bg = self._current_bg
        state = self._current_state
        w, h = img.size

        for y in range(h):
            for x in range(w):
                r, g, b = pixels[x, y]
                # Skip background pixels
                if abs(r - bg[0]) < 10 and abs(g - bg[1]) < 10 and abs(b - bg[2]) < 10:
                    continue

                # This pixel is part of the bear — give it a random color
                if state == FaceState.HAPPY:
                    # Full rainbow — random hue, high saturation
                    hue = random.random()
                    cr, cg, cb = colorsys.hls_to_rgb(hue, 0.55, 1.0)
                    pixels[x, y] = (int(cr * 255), int(cg * 255), int(cb * 255))
                elif state == FaceState.LISTENING:
                    pixels[x, y] = random.choice(LISTENING_COLORS)
                elif state == FaceState.SPEAKING:
                    pixels[x, y] = random.choice(SPEAKING_COLORS)
                elif state == FaceState.ERROR:
                    pixels[x, y] = random.choice(ERROR_COLORS)
                elif state == FaceState.THINKING:
                    pixels[x, y] = random.choice(THINKING_COLORS)
                elif state == FaceState.IDLE:
                    pixels[x, y] = random.choice(IDLE_COLORS)

        return img
