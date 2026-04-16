"""Procedural eye renderer for the 64x64 matrix.

Subscribes to face.set_state and audio.amplitude events on the event bus and
drives parameter interpolation toward the current emotion preset. Runs a
fixed-rate async loop which hands each frame to the supplied DisplayBackend.
"""

from __future__ import annotations

import asyncio
import colorsys
import math
import random
import time
from dataclasses import dataclass, replace
from typing import Any

from PIL import Image, ImageDraw

from clod.event_bus import EventBus
from clod.events import AUDIO_AMPLITUDE, FACE_SET_STATE, FaceState
from clod.matrix_backends import DisplayBackend

# Eye-opening geometry in 64x64 space.
EYE_CENTER_X = 32
EYE_CENTER_Y = 32
EYE_MAX_WIDTH = 48  # x spans 8..56
EYE_MAX_HEIGHT = 40  # y spans 12..52
IRIS_RADIUS = 10


@dataclass
class EyeState:
    """Mutable in practice — we build a new dataclass each frame via lerp."""

    lid_top_openness: float  # 0.0 = closed, 1.0 = fully open
    lid_bottom_openness: float
    iris_x: float  # center in 64x64 space
    iris_y: float
    iris_color: tuple[int, int, int]
    pupil_radius: float
    highlight_offset: tuple[float, float]
    lid_angle: float  # radians


EMOTION_PRESETS: dict[FaceState, EyeState] = {
    FaceState.IDLE: EyeState(
        lid_top_openness=0.7,
        lid_bottom_openness=0.7,
        iris_x=32.0,
        iris_y=32.0,
        iris_color=(255, 139, 61),
        pupil_radius=4.0,
        highlight_offset=(-1.5, -1.5),
        lid_angle=0.0,
    ),
    FaceState.LISTENING: EyeState(
        lid_top_openness=1.0,
        lid_bottom_openness=1.0,
        iris_x=32.0,
        iris_y=32.0,
        iris_color=(255, 102, 0),
        pupil_radius=5.5,
        highlight_offset=(-1.5, -1.5),
        lid_angle=0.0,
    ),
    FaceState.THINKING: EyeState(
        lid_top_openness=0.5,
        lid_bottom_openness=0.5,
        iris_x=32.0,
        iris_y=32.0,
        iris_color=(61, 139, 255),
        pupil_radius=2.5,
        highlight_offset=(-1.0, -1.0),
        lid_angle=0.0,
    ),
    FaceState.SPEAKING: EyeState(
        lid_top_openness=0.7,
        lid_bottom_openness=0.7,
        iris_x=32.0,
        iris_y=32.0,
        iris_color=(255, 139, 61),
        pupil_radius=4.0,
        highlight_offset=(-1.5, -1.5),
        lid_angle=0.0,
    ),
    FaceState.ERROR: EyeState(
        lid_top_openness=0.4,
        lid_bottom_openness=0.6,
        iris_x=36.0,
        iris_y=32.0,
        iris_color=(255, 48, 48),
        pupil_radius=3.0,
        highlight_offset=(-1.0, -1.0),
        lid_angle=0.1,
    ),
    FaceState.HAPPY: EyeState(
        lid_top_openness=0.3,
        lid_bottom_openness=0.9,
        iris_x=32.0,
        iris_y=32.0,
        iris_color=(48, 255, 96),
        pupil_radius=5.0,
        highlight_offset=(-1.5, -1.5),
        lid_angle=0.0,
    ),
    FaceState.SLEEPING: EyeState(
        lid_top_openness=0.05,
        lid_bottom_openness=0.05,
        iris_x=32.0,
        iris_y=32.0,
        iris_color=(136, 64, 0),
        pupil_radius=2.0,
        highlight_offset=(-1.0, -1.0),
        lid_angle=0.0,
    ),
}


# -------------------- interpolation helpers --------------------


def lerp_float(a: float, b: float, t: float) -> float:
    return a + (b - a) * t


def lerp_color(
    c1: tuple[int, int, int], c2: tuple[int, int, int], t: float
) -> tuple[int, int, int]:
    """Interpolate two RGB colors through HLS space for smoother transitions."""
    h1, l1, s1 = colorsys.rgb_to_hls(c1[0] / 255.0, c1[1] / 255.0, c1[2] / 255.0)
    h2, l2, s2 = colorsys.rgb_to_hls(c2[0] / 255.0, c2[1] / 255.0, c2[2] / 255.0)

    # Shortest path around the hue wheel.
    dh = h2 - h1
    if dh > 0.5:
        h1 += 1.0
    elif dh < -0.5:
        h2 += 1.0
    h = (lerp_float(h1, h2, t)) % 1.0
    l_ = lerp_float(l1, l2, t)
    s = lerp_float(s1, s2, t)

    r, g, b = colorsys.hls_to_rgb(h, l_, s)
    return (int(round(r * 255)), int(round(g * 255)), int(round(b * 255)))


def lerp_eye_state(current: EyeState, target: EyeState, t: float) -> EyeState:
    return EyeState(
        lid_top_openness=lerp_float(current.lid_top_openness, target.lid_top_openness, t),
        lid_bottom_openness=lerp_float(
            current.lid_bottom_openness, target.lid_bottom_openness, t
        ),
        iris_x=lerp_float(current.iris_x, target.iris_x, t),
        iris_y=lerp_float(current.iris_y, target.iris_y, t),
        iris_color=lerp_color(current.iris_color, target.iris_color, t),
        pupil_radius=lerp_float(current.pupil_radius, target.pupil_radius, t),
        highlight_offset=(
            lerp_float(current.highlight_offset[0], target.highlight_offset[0], t),
            lerp_float(current.highlight_offset[1], target.highlight_offset[1], t),
        ),
        lid_angle=lerp_float(current.lid_angle, target.lid_angle, t),
    )


# -------------------- renderer --------------------


class MatrixRenderer:
    def __init__(self, bus: EventBus, backend: DisplayBackend, fps: int = 20) -> None:
        self.bus = bus
        self.backend = backend
        self.fps = fps

        self.current_state: EyeState = replace(EMOTION_PRESETS[FaceState.IDLE])
        self.target_state: EyeState = replace(EMOTION_PRESETS[FaceState.IDLE])
        self._current_face: FaceState = FaceState.IDLE

        # Idle-blink bookkeeping
        self._idle_since: float = time.monotonic()
        self._next_blink_at: float = time.monotonic() + random.uniform(3.0, 7.0)
        self._blink_started_at: float | None = None

        # Audio amplitude for LISTENING pulse
        self._audio_amplitude: float = 0.0

        bus.on(FACE_SET_STATE, self._on_face_set_state)
        bus.on(AUDIO_AMPLITUDE, self._on_audio_amplitude)

    # ---- event handlers ----

    def _on_face_set_state(self, payload: Any) -> None:
        if isinstance(payload, FaceState):
            face = payload
        elif isinstance(payload, str):
            try:
                face = FaceState(payload)
            except ValueError:
                return
        else:
            return
        self._current_face = face
        self.target_state = replace(EMOTION_PRESETS[face])
        if face == FaceState.IDLE:
            self._idle_since = time.monotonic()
            self._next_blink_at = time.monotonic() + random.uniform(3.0, 7.0)

    def _on_audio_amplitude(self, payload: Any) -> None:
        try:
            self._audio_amplitude = max(0.0, min(1.0, float(payload)))
        except (TypeError, ValueError):
            return

    # ---- main loop ----

    async def run(self) -> None:
        frame_period = 1.0 / self.fps
        while True:
            start = time.monotonic()

            # 5% per frame toward target (smooth).
            self.current_state = lerp_eye_state(
                self.current_state, self.target_state, 0.05
            )

            render_state = self._apply_transient_modulation(self.current_state, start)

            image = self._draw_frame(render_state)
            self.backend.render(image)

            elapsed = time.monotonic() - start
            sleep_for = frame_period - elapsed
            if sleep_for > 0:
                await asyncio.sleep(sleep_for)
            else:
                # Yield even if we blew the frame budget.
                await asyncio.sleep(0)

    def _apply_transient_modulation(self, state: EyeState, now: float) -> EyeState:
        """Overlay blinks and audio-driven pulses on top of the interpolated state."""
        mod = state

        # Audio pulse during LISTENING: expand pupil with amplitude.
        if self._current_face == FaceState.LISTENING and self._audio_amplitude > 0:
            pulse = self._audio_amplitude * 1.5
            mod = replace(mod, pupil_radius=mod.pupil_radius + pulse)

        # Idle blink.
        if self._current_face == FaceState.IDLE:
            if self._blink_started_at is not None:
                if now - self._blink_started_at < 0.1:
                    mod = replace(mod, lid_top_openness=0.0, lid_bottom_openness=0.0)
                else:
                    self._blink_started_at = None
                    self._next_blink_at = now + random.uniform(3.0, 7.0)
            else:
                if (
                    now - self._idle_since > 1.0
                    and now >= self._next_blink_at
                ):
                    self._blink_started_at = now
                    mod = replace(mod, lid_top_openness=0.0, lid_bottom_openness=0.0)
        else:
            # Cancel any in-progress blink when we leave idle.
            self._blink_started_at = None

        return mod

    # ---- drawing ----

    def _draw_frame(self, state: EyeState) -> Image.Image:
        w = self.backend.width
        h = self.backend.height
        image = Image.new("RGB", (w, h), (0, 0, 0))
        draw = ImageDraw.Draw(image)

        # Eye-opening vertical extents driven by lid openness.
        top_y = EYE_CENTER_Y - (EYE_MAX_HEIGHT / 2) * state.lid_top_openness
        bottom_y = EYE_CENTER_Y + (EYE_MAX_HEIGHT / 2) * state.lid_bottom_openness
        left_x = EYE_CENTER_X - EYE_MAX_WIDTH / 2
        right_x = EYE_CENTER_X + EYE_MAX_WIDTH / 2

        # If eye is effectively closed, just draw a thin line.
        if (bottom_y - top_y) < 1.5:
            mid_y = EYE_CENTER_Y
            draw.line(
                [(left_x + 4, mid_y), (right_x - 4, mid_y)],
                fill=state.iris_color,
                width=1,
            )
            return image

        # Build a mask for the eye opening (white = visible).
        mask = Image.new("L", (w, h), 0)
        mask_draw = ImageDraw.Draw(mask)

        is_happy_crescent = self._current_face == FaceState.HAPPY
        if is_happy_crescent:
            # Crescent ^_^ shape: a filled ellipse only below a curved upper arc.
            # Use an ellipse bounded by the lid extents; crescent effect comes
            # from the top lid being nearly closed (pushing top_y near center).
            mask_draw.chord(
                [left_x, top_y, right_x, bottom_y + (bottom_y - EYE_CENTER_Y)],
                start=180,
                end=360,
                fill=255,
            )
        else:
            mask_draw.ellipse([left_x, top_y, right_x, bottom_y], fill=255)

        # Optional asymmetric tilt: rotate the mask around eye center.
        if abs(state.lid_angle) > 0.001:
            mask = mask.rotate(
                math.degrees(state.lid_angle),
                resample=Image.BILINEAR,
                center=(EYE_CENTER_X, EYE_CENTER_Y),
            )

        # Iris (filled circle).
        ix, iy = state.iris_x, state.iris_y
        draw.ellipse(
            [ix - IRIS_RADIUS, iy - IRIS_RADIUS, ix + IRIS_RADIUS, iy + IRIS_RADIUS],
            fill=state.iris_color,
        )

        # Pupil (black).
        pr = max(0.5, state.pupil_radius)
        draw.ellipse([ix - pr, iy - pr, ix + pr, iy + pr], fill=(0, 0, 0))

        # Highlight: 2x2 white square at offset.
        hx = ix + state.highlight_offset[0]
        hy = iy + state.highlight_offset[1]
        draw.rectangle([hx, hy, hx + 1, hy + 1], fill=(255, 255, 255))

        # Composite: keep eye pixels where mask is white, else black.
        black = Image.new("RGB", (w, h), (0, 0, 0))
        image = Image.composite(image, black, mask)
        return image
