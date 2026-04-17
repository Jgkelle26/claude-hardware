"""Character theme — dithered pixel portrait.

A face emerges from probabilistic colored noise on the 64x64 grid.
Up close it looks like colored static; step back and you see a face with
depth, shadows, and highlights — like a halftone print using bold colors.
The face shimmers every frame because each pixel's color is re-rolled
probabilistically, giving it a restless, alive quality.
"""

from __future__ import annotations

import math
import random
import time

from PIL import Image

from clod.events import FaceState
from clod.themes.base import ThemeRenderer

# ---------------------------------------------------------------------------
# Palette variants — selected randomly on each activation
# ---------------------------------------------------------------------------

PALETTE_VARIANTS: list[list[tuple[int, int, int]]] = [
    # Soft classic: muted navy / dusty rose / soft teal / warm white
    [(18, 18, 50), (165, 70, 80), (70, 160, 180), (225, 225, 235)],
    # Warm: deep brown / terracotta / golden / cream
    [(35, 20, 15), (185, 95, 55), (210, 175, 80), (245, 240, 230)],
    # Cool: slate / soft blue / seafoam / ice
    [(20, 28, 55), (75, 110, 170), (120, 195, 180), (220, 235, 245)],
    # Dusk: deep purple / mauve / lavender / soft white
    [(22, 12, 40), (150, 80, 130), (160, 145, 200), (235, 230, 245)],
]

# Brightness-to-color probability thresholds.
# Each row: (navy_cumul, red_cumul, cyan_cumul)  — white is the remainder.
_THRESHOLDS: list[tuple[float, float, float, float]] = [
    # b < 0.15
    (0.15, 0.85, 0.95, 0.99),
    # b < 0.35
    (0.35, 0.40, 0.80, 0.95),
    # b < 0.55
    (0.55, 0.15, 0.50, 0.85),
    # b < 0.75
    (0.75, 0.05, 0.20, 0.60),
    # b >= 0.75
    (1.01, 0.02, 0.07, 0.32),
]


def _pick_color(
    b: float,
    r: float,
    palette: list[tuple[int, int, int]],
) -> tuple[int, int, int]:
    """Given brightness *b* and random float *r*, return a palette color."""
    # Find the right threshold band
    if b < 0.15:
        _, cn, cr, cc = _THRESHOLDS[0]
    elif b < 0.35:
        _, cn, cr, cc = _THRESHOLDS[1]
    elif b < 0.55:
        _, cn, cr, cc = _THRESHOLDS[2]
    elif b < 0.75:
        _, cn, cr, cc = _THRESHOLDS[3]
    else:
        _, cn, cr, cc = _THRESHOLDS[4]

    if r < cn:
        return palette[0]  # navy / shadow
    if r < cr:
        return palette[1]  # red / mid-dark
    if r < cc:
        return palette[2]  # cyan / mid-bright
    return palette[3]      # white / highlight


def _clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


def _gauss(dist: float, sigma: float) -> float:
    """Unnormalized gaussian falloff."""
    return math.exp(-(dist * dist) / (sigma * sigma))


# ---------------------------------------------------------------------------
# Face map builder
# ---------------------------------------------------------------------------

def _build_face_map(width: int, height: int) -> list[list[float]]:
    """Procedurally generate a 64x64 brightness template of a face.

    Returns a 2-D list indexed as ``[y][x]`` with values in 0.0 .. 1.0.
    """
    cx: float = width / 2.0   # 32
    cy: float = 30.0           # face center y (slightly above middle)

    face_rx: float = 22.0      # face oval x radius
    face_ry: float = 25.0      # face oval y radius

    fmap: list[list[float]] = []
    for y in range(height):
        row: list[float] = []
        for x in range(width):
            # Normalised distance from face center in oval space
            dx: float = (x - cx) / face_rx
            dy: float = (y - cy) / face_ry
            oval_dist: float = math.sqrt(dx * dx + dy * dy)

            # Base face shape — gaussian falloff from center of oval
            face_val: float = _gauss(oval_dist, 0.85)

            if oval_dist > 1.15:
                # Outside face — sparse background
                b = random.uniform(0.0, 0.05)
                row.append(b)
                continue

            # Gradient from face brightness into background at edges
            if oval_dist > 0.85:
                edge_factor = 1.0 - (oval_dist - 0.85) / 0.30
                edge_factor = _clamp(edge_factor, 0.0, 1.0)
                face_val *= edge_factor

            # --- Feature regions ---

            # Forehead (y 8-18): bright
            if 8 <= y <= 18:
                forehead_factor = _gauss(y - 13.0, 6.0) * _gauss(x - cx, 18.0)
                face_val = max(face_val, 0.55 + 0.15 * forehead_factor)

            # Brow ridge (y 18-22): slight shadow
            if 18 <= y <= 22:
                brow_factor = _gauss(y - 20.0, 2.5) * _gauss(x - cx, 16.0)
                face_val = face_val * (1.0 - 0.3 * brow_factor) + 0.35 * brow_factor

            # Eye sockets (y 22-30): dark regions
            left_eye_cx: float = 22.0
            right_eye_cx: float = 42.0
            eye_cy: float = 26.0

            for ecx in (left_eye_cx, right_eye_cx):
                ex_dist = ((x - ecx) / 5.0) ** 2 + ((y - eye_cy) / 3.5) ** 2
                if ex_dist < 1.0:
                    # Inside eye socket
                    socket_depth = (1.0 - ex_dist) * 0.7
                    face_val = face_val * (1.0 - socket_depth) + 0.12 * socket_depth

                    # Eye whites/iris — bright spots inside the sockets
                    iris_dist = ((x - ecx) / 3.0) ** 2 + ((y - eye_cy) / 2.5) ** 2
                    if iris_dist < 1.0:
                        iris_bright = (1.0 - iris_dist)
                        face_val = face_val + iris_bright * 0.75
                        face_val = min(face_val, 0.95)

                    # Pupil center — 3x3ish dark spot
                    pupil_dist = abs(x - ecx) + abs(y - eye_cy)
                    if pupil_dist < 1.8:
                        face_val = 0.0

            # Nose bridge (y 28-38): narrow bright vertical strip
            if 28 <= y <= 38:
                nose_factor = _gauss(x - cx, 3.5) * _gauss(y - 33.0, 6.0)
                face_val = max(face_val, 0.50 + 0.15 * nose_factor)

            # Cheekbones (y 30-38): moderate brightness on sides
            if 30 <= y <= 38:
                for cheek_x in (cx - 12.0, cx + 12.0):
                    cheek_factor = _gauss(x - cheek_x, 5.0) * _gauss(y - 34.0, 4.0)
                    face_val = max(face_val, 0.40 + 0.15 * cheek_factor)

            # Mouth area (y 40-44): dark band
            if 40 <= y <= 44:
                mouth_factor = _gauss(x - cx, 10.0) * _gauss(y - 42.0, 2.5)
                mouth_dark = 0.20 * mouth_factor
                face_val = face_val * (1.0 - mouth_factor) + mouth_dark

            # Chin (y 44-52)
            if 44 <= y <= 52:
                chin_factor = _gauss(x - cx, 14.0) * _gauss(y - 48.0, 5.0)
                face_val = max(face_val, 0.35 + 0.10 * chin_factor)

            # Clamp and add organic noise
            face_val = _clamp(face_val, 0.0, 1.0)
            face_val += random.uniform(-0.05, 0.05)
            face_val = _clamp(face_val, 0.0, 1.0)

            row.append(face_val)
        fmap.append(row)
    return fmap


# ---------------------------------------------------------------------------
# Theme implementation
# ---------------------------------------------------------------------------

class CharacterTheme(ThemeRenderer):
    """Dithered pixel portrait — a face emerging from probabilistic colored noise."""

    def __init__(self, width: int = 64, height: int = 64) -> None:
        super().__init__(width, height)

        # Face brightness template — built in on_activate
        self._face_map: list[list[float]] = []
        self._base_face_map: list[list[float]] = []  # unmodified copy

        # Palette (set in on_activate)
        self._palette: list[tuple[int, int, int]] = PALETTE_VARIANTS[0]
        self._active_palette: list[tuple[int, int, int]] = list(self._palette)

        # Previous frame buffer for shimmer holdover
        self._prev_frame: list[tuple[int, int, int]] = [
            (0, 0, 0) for _ in range(width * height)
        ]

        # Shimmer intensity
        self._shimmer: float = 1.0

        # Time accumulator
        self._time: float = 0.0

        # Blink state
        self._next_blink_at: float = 0.0
        self._blink_started_at: float | None = None

        # Squint state
        self._next_squint_at: float = 0.0
        self._squint_started_at: float | None = None
        self._squint_eye: str = "left"

        # Pupil drift
        self._pupil_offset_x: float = 0.0
        self._pupil_offset_y: float = 0.0
        self._pupil_target_x: float = 0.0
        self._pupil_target_y: float = 0.0
        self._next_drift_at: float = 0.0

        # Speaking mouth phase
        self._speak_phase: float = 0.0

        # Listening face shift
        self._listen_shift: int = 0

        # Error glitch offsets per row
        self._error_offsets: list[int] = [0] * height

        # Sleeping firefly
        self._firefly_pixels: list[tuple[int, int, float]] = []  # (x, y, remaining_life)

        # Thinking scan offset
        self._think_scan_offset: int = 0

    # ------------------------------------------------------------------
    # ThemeRenderer interface
    # ------------------------------------------------------------------

    @property
    def name(self) -> str:
        return "Character"

    def on_activate(self) -> None:
        self._palette = random.choice(PALETTE_VARIANTS)
        self._active_palette = list(self._palette)
        self._base_face_map = _build_face_map(self.width, self.height)
        self._face_map = [row[:] for row in self._base_face_map]
        self._prev_frame = [(0, 0, 0)] * (self.width * self.height)
        self._shimmer = 1.0
        self._time = 0.0
        self._speak_phase = 0.0
        self._listen_shift = 0
        self._error_offsets = [0] * self.height
        self._firefly_pixels = []
        self._think_scan_offset = 0
        self._pupil_offset_x = 0.0
        self._pupil_offset_y = 0.0
        self._pupil_target_x = 0.0
        self._pupil_target_y = 0.0
        now = time.monotonic()
        self._next_blink_at = now + random.uniform(3.0, 7.0)
        self._blink_started_at = None
        self._next_squint_at = now + random.uniform(10.0, 20.0)
        self._squint_started_at = None
        self._next_drift_at = now + random.uniform(1.0, 3.0)

    def on_deactivate(self) -> None:
        self._firefly_pixels = []

    def set_state(self, state: FaceState) -> None:
        super().set_state(state)
        if state == FaceState.SPEAKING:
            self._speak_phase = 0.0
        if state == FaceState.IDLE:
            now = time.monotonic()
            self._next_blink_at = now + random.uniform(3.0, 7.0)
            self._blink_started_at = None
            self._next_squint_at = now + random.uniform(10.0, 20.0)
            self._squint_started_at = None
            self._next_drift_at = now + random.uniform(1.0, 3.0)

    # ------------------------------------------------------------------
    # Frame rendering
    # ------------------------------------------------------------------

    def draw_frame(self, dt: float) -> Image.Image:
        self._time += dt
        now: float = time.monotonic()
        state: FaceState = self._current_state
        w: int = self.width
        h: int = self.height

        # Rebuild the working face map from the base each frame
        face_map: list[list[float]] = [row[:] for row in self._base_face_map]

        # --- Apply state-specific modifications to the face map ---
        self._apply_state_modifiers(face_map, state, now, dt)

        # --- Determine active palette ---
        palette: list[tuple[int, int, int]] = self._get_state_palette(state)

        # --- Determine shimmer ---
        shimmer: float = self._get_state_shimmer(state)
        self._shimmer = shimmer

        # --- Determine brightness multiplier ---
        brightness_mult: float = self._get_brightness_multiplier(state)

        # --- Build the pixel buffer ---
        new_frame: list[tuple[int, int, int]] = list(self._prev_frame)

        for y in range(h):
            # Error state: horizontal glitch offset
            x_offset: int = 0
            if state == FaceState.ERROR:
                x_offset = self._error_offsets[y]

            # Thinking state: scan line dimming
            scan_dim: float = 0.0
            if state == FaceState.THINKING:
                if (y + self._think_scan_offset) % 2 == 0:
                    scan_dim = 0.1

            for x in range(w):
                idx: int = y * w + x

                # Shimmer check — should we re-randomize this pixel?
                if random.random() >= shimmer:
                    # Keep previous color
                    continue

                # Source coordinates (with possible glitch offset)
                sx: int = x - x_offset
                if sx < 0 or sx >= w:
                    # Off-screen due to glitch — use background brightness
                    b = 0.02
                else:
                    b = face_map[y][sx]

                # Apply brightness multiplier
                b = _clamp(b * brightness_mult - scan_dim, 0.0, 1.0)

                # Pick color probabilistically
                r_val: float = random.random()
                color: tuple[int, int, int] = _pick_color(b, r_val, palette)
                new_frame[idx] = color

        self._prev_frame = new_frame

        # Build the image from the flat pixel list
        pixel_bytes: bytearray = bytearray(w * h * 3)
        for i, (cr, cg, cb) in enumerate(new_frame):
            off = i * 3
            pixel_bytes[off] = cr
            pixel_bytes[off + 1] = cg
            pixel_bytes[off + 2] = cb

        img: Image.Image = Image.frombytes("RGB", (w, h), bytes(pixel_bytes))
        return img

    # ------------------------------------------------------------------
    # State modifiers — adjust face_map per state each frame
    # ------------------------------------------------------------------

    def _apply_state_modifiers(
        self,
        face_map: list[list[float]],
        state: FaceState,
        now: float,
        dt: float,
    ) -> None:
        if state == FaceState.IDLE:
            self._apply_idle(face_map, now, dt)
        elif state == FaceState.LISTENING:
            self._apply_listening(face_map, now, dt)
        elif state == FaceState.THINKING:
            self._apply_thinking(face_map, now, dt)
        elif state == FaceState.SPEAKING:
            self._apply_speaking(face_map, now, dt)
        elif state == FaceState.ERROR:
            self._apply_error(face_map, now, dt)
        elif state == FaceState.HAPPY:
            self._apply_happy(face_map, now, dt)
        elif state == FaceState.SLEEPING:
            self._apply_sleeping(face_map, now, dt)

    # --- Eye region helpers ---

    _LEFT_EYE_CX: int = 22
    _RIGHT_EYE_CX: int = 42
    _EYE_CY: int = 26
    _EYE_RX: int = 4   # half-width of eye region
    _EYE_RY: int = 3   # half-height of eye region

    _MOUTH_CX: int = 32
    _MOUTH_CY: int = 42
    _MOUTH_RX: int = 10
    _MOUTH_RY: int = 2

    def _set_eye_region(
        self,
        face_map: list[list[float]],
        ecx: int,
        ecy: int,
        mode: str,
        pupil_ox: float = 0.0,
        pupil_oy: float = 0.0,
    ) -> None:
        """Modify the face_map in an eye region.

        Uses elliptical falloff for a softer, more organic eye shape.
        A dark ring around the bright iris creates negative-space definition.
        *mode*: ``"open"``, ``"closed"``, ``"half"``, ``"bright"``, ``"happy"``
        """
        rx: int = self._EYE_RX + 1  # slightly larger region for soft edges
        ry: int = self._EYE_RY + 1

        for y in range(ecy - ry, ecy + ry + 1):
            for x in range(ecx - rx, ecx + rx + 1):
                if y < 0 or y >= self.height or x < 0 or x >= self.width:
                    continue

                # Elliptical distance from eye center (0 = center, 1 = edge)
                edist = math.sqrt(((x - ecx) / (self._EYE_RX + 0.5)) ** 2
                                  + ((y - ecy) / (self._EYE_RY + 0.5)) ** 2)

                if mode == "closed":
                    # Soft close — gradient from dark center to socket
                    face_map[y][x] = 0.08 + 0.04 * min(edist, 1.0)
                elif mode == "half":
                    # Top half dark, bottom half bright with soft gradient
                    vert_factor = (y - (ecy - 1)) / max(1, self._EYE_RY * 2)
                    vert_factor = _clamp(vert_factor, 0.0, 1.0)
                    face_map[y][x] = 0.08 + 0.70 * vert_factor * _gauss(edist, 0.9)
                elif mode == "happy":
                    # ^_^ crescent — bright arc at bottom, dark above
                    vert_factor = (y - ecy) / max(1, self._EYE_RY)
                    vert_factor = _clamp(vert_factor, 0.0, 1.0)
                    face_map[y][x] = 0.08 + 0.80 * vert_factor * _gauss(edist, 0.9)
                elif mode in ("bright", "open"):
                    # --- Dark socket ring for definition ---
                    # Outer ring (0.7 < edist < 1.1): dark border
                    if edist > 0.7:
                        socket_dark = _clamp((edist - 0.7) / 0.4, 0.0, 1.0) * 0.6
                        face_map[y][x] = 0.10 + 0.05 * (1.0 - socket_dark)
                        continue

                    # --- Iris with soft radial gradient ---
                    iris_glow = _gauss(edist, 0.55)
                    if mode == "bright":
                        base_bright = 0.50 + 0.50 * iris_glow  # 0.50-1.00
                    else:
                        base_bright = 0.35 + 0.55 * iris_glow  # 0.35-0.90

                    face_map[y][x] = min(base_bright, 0.97)

                    # --- Pupil: soft dark spot with gradient ---
                    px = ecx + int(round(pupil_ox))
                    py = ecy + int(round(pupil_oy))
                    pupil_dist = math.sqrt((x - px) ** 2 + (y - py) ** 2)
                    if pupil_dist < 2.5:
                        pupil_dark = _gauss(pupil_dist, 1.5)
                        face_map[y][x] *= (1.0 - pupil_dark * 0.95)

                    # --- Highlight catch-light: tiny bright spot ---
                    hx = px - 1
                    hy = py - 1
                    if x == hx and y == hy:
                        face_map[y][x] = 0.98

    def _set_mouth_region(
        self,
        face_map: list[list[float]],
        brightness: float,
        width_factor: float = 1.0,
    ) -> None:
        """Set mouth region brightness."""
        cx: int = self._MOUTH_CX
        cy: int = self._MOUTH_CY
        rx: int = int(self._MOUTH_RX * width_factor)
        ry: int = self._MOUTH_RY

        for y in range(cy - ry, cy + ry + 1):
            for x in range(cx - rx, cx + rx + 1):
                if 0 <= y < self.height and 0 <= x < self.width:
                    face_map[y][x] = brightness

    # --- Per-state logic ---

    def _apply_idle(
        self,
        face_map: list[list[float]],
        now: float,
        dt: float,
    ) -> None:
        """Normal idle: blinks, pupil drift, occasional squint."""
        # --- Blink ---
        blink_active: bool = False
        if self._blink_started_at is not None:
            elapsed = now - self._blink_started_at
            if elapsed < 0.10:
                blink_active = True
            else:
                self._blink_started_at = None
                self._next_blink_at = now + random.uniform(3.0, 7.0)
        elif now >= self._next_blink_at:
            self._blink_started_at = now
            blink_active = True

        if blink_active:
            self._set_eye_region(face_map, self._LEFT_EYE_CX, self._EYE_CY, "closed")
            self._set_eye_region(face_map, self._RIGHT_EYE_CX, self._EYE_CY, "closed")
            return

        # --- Sarcastic squint ---
        squint_eye: str | None = None
        if self._squint_started_at is not None:
            elapsed = now - self._squint_started_at
            if elapsed < 1.0:
                squint_eye = self._squint_eye
            else:
                self._squint_started_at = None
                self._next_squint_at = now + random.uniform(10.0, 20.0)
        elif now >= self._next_squint_at:
            self._squint_started_at = now
            self._squint_eye = random.choice(["left", "right"])
            squint_eye = self._squint_eye

        # --- Pupil drift ---
        if now >= self._next_drift_at:
            self._pupil_target_x = random.uniform(-2.0, 2.0)
            self._pupil_target_y = random.uniform(-1.5, 1.5)
            self._next_drift_at = now + random.uniform(2.0, 4.0)

        self._pupil_offset_x += (self._pupil_target_x - self._pupil_offset_x) * 0.03
        self._pupil_offset_y += (self._pupil_target_y - self._pupil_offset_y) * 0.03

        # Set eyes
        left_mode = "half" if squint_eye == "left" else "open"
        right_mode = "half" if squint_eye == "right" else "open"
        self._set_eye_region(
            face_map, self._LEFT_EYE_CX, self._EYE_CY, left_mode,
            self._pupil_offset_x, self._pupil_offset_y,
        )
        self._set_eye_region(
            face_map, self._RIGHT_EYE_CX, self._EYE_CY, right_mode,
            self._pupil_offset_x, self._pupil_offset_y,
        )

    def _apply_listening(
        self,
        face_map: list[list[float]],
        now: float,
        dt: float,
    ) -> None:
        """Listening: face leans forward and sways gently, wide bright eyes."""
        # --- Gentle face sway: slower and subtler than speaking ---
        sway_phase: float = self._time * 0.2 * math.tau  # ~0.2 Hz
        sway_amount: float = math.sin(sway_phase) * 2.0  # ±2 pixel shift
        sway_int: int = int(round(sway_amount))

        # Horizontal shift
        if sway_int != 0:
            for y in range(self.height):
                old_row = face_map[y][:]
                for x in range(self.width):
                    sx = x - sway_int
                    if 0 <= sx < self.width:
                        face_map[y][x] = old_row[sx]
                    else:
                        face_map[y][x] = 0.02

        # Depth gradient (near side brighter)
        cx: float = self.width / 2.0
        for y in range(self.height):
            for x in range(self.width):
                if face_map[y][x] > 0.08:
                    dist_from_center = (x - cx) / cx
                    depth_mod = -dist_from_center * sway_amount * 0.03
                    face_map[y][x] = _clamp(face_map[y][x] + depth_mod, 0.0, 1.0)

        # --- Subtle forward lean (shift up 2px) ---
        for y in range(self.height - 2):
            face_map[y] = face_map[y + 2][:]
        face_map[self.height - 2] = [0.0] * self.width
        face_map[self.height - 1] = [0.0] * self.width

        # --- Gentle nod ---
        nod_phase: float = self._time * 0.35 * math.tau
        nod_amount: int = int(round(math.sin(nod_phase) * 1.0))  # ±1 pixel
        if nod_amount > 0:
            for y in range(self.height - 1, nod_amount - 1, -1):
                face_map[y] = face_map[y - nod_amount][:]
            for y in range(nod_amount):
                face_map[y] = [0.02] * self.width

        # Wide open, bright eyes with centered pupils
        self._set_eye_region(face_map, self._LEFT_EYE_CX, self._EYE_CY, "bright", 0.0, 0.0)
        self._set_eye_region(face_map, self._RIGHT_EYE_CX, self._EYE_CY, "bright", 0.0, 0.0)

    def _apply_thinking(
        self,
        face_map: list[list[float]],
        now: float,
        dt: float,
    ) -> None:
        """Thinking: darkened face, pupils up-left, CRT scan lines."""
        # Pupils up-left
        self._set_eye_region(
            face_map, self._LEFT_EYE_CX, self._EYE_CY, "open", -2.0, -1.5,
        )
        self._set_eye_region(
            face_map, self._RIGHT_EYE_CX, self._EYE_CY, "open", -2.0, -1.5,
        )

        # Advance scan line offset
        self._think_scan_offset = int(self._time * 8) % 2

    def _apply_speaking(
        self,
        face_map: list[list[float]],
        now: float,
        dt: float,
    ) -> None:
        """Speaking: face turns left/right, nods, mouth oscillates."""
        self._speak_phase += dt * 3.0 * math.tau  # ~3 Hz

        # --- Face turn: slow horizontal shift simulating rotation ---
        # Slow oscillation (~0.3 Hz) for the turn, separate from mouth
        turn_phase: float = self._time * 0.3 * math.tau
        turn_amount: float = math.sin(turn_phase) * 3.0  # ±3 pixel shift
        turn_int: int = int(round(turn_amount))

        # Shift brightness map horizontally to simulate face turning
        if turn_int != 0:
            for y in range(self.height):
                old_row = face_map[y][:]
                for x in range(self.width):
                    sx = x - turn_int
                    if 0 <= sx < self.width:
                        face_map[y][x] = old_row[sx]
                    else:
                        face_map[y][x] = 0.02

        # --- Depth gradient: near cheek brighter, far cheek darker ---
        # When turned right (positive), left side is "near" (brighter)
        cx: float = self.width / 2.0
        for y in range(self.height):
            for x in range(self.width):
                if face_map[y][x] > 0.08:  # only affect face pixels
                    # Gradient: pixels on the "near" side get brightened
                    dist_from_center = (x - cx) / cx  # -1 to +1
                    depth_mod = -dist_from_center * turn_amount * 0.04
                    face_map[y][x] = _clamp(face_map[y][x] + depth_mod, 0.0, 1.0)

        # --- Subtle vertical nod ---
        nod_phase: float = self._time * 0.5 * math.tau  # ~0.5 Hz
        nod_amount: int = int(round(math.sin(nod_phase) * 1.5))  # ±1-2 pixels
        if nod_amount != 0:
            if nod_amount > 0:
                for y in range(self.height - 1, nod_amount - 1, -1):
                    face_map[y] = face_map[y - nod_amount][:]
                for y in range(nod_amount):
                    face_map[y] = [0.02] * self.width
            else:
                amt = abs(nod_amount)
                for y in range(self.height - amt):
                    face_map[y] = face_map[y + amt][:]
                for y in range(self.height - amt, self.height):
                    face_map[y] = [0.02] * self.width

        # Mouth brightness oscillates 0.20 -> 0.50 -> 0.20
        mouth_b: float = 0.20 + 0.30 * (0.5 + 0.5 * math.sin(self._speak_phase))
        self._set_mouth_region(face_map, mouth_b, 1.0)

        # Eyes normal, pupils track slightly with the turn direction
        pupil_track: float = turn_amount * 0.4
        self._set_eye_region(face_map, self._LEFT_EYE_CX, self._EYE_CY, "open", pupil_track, 0.0)
        self._set_eye_region(face_map, self._RIGHT_EYE_CX, self._EYE_CY, "open", pupil_track, 0.0)

    def _apply_error(
        self,
        face_map: list[list[float]],
        now: float,
        dt: float,
    ) -> None:
        """Error: face dims and destabilizes quietly — something is off.

        No chaotic glitching. Instead the face slowly fades unevenly,
        one eye drifts closed, and a subtle vertical drift makes it
        feel like the signal is weakening.
        """
        # Clear glitch offsets — no horizontal distortion
        for y in range(self.height):
            self._error_offsets[y] = 0

        # Uneven fade — darken random patches across the face
        for y in range(self.height):
            for x in range(self.width):
                if face_map[y][x] > 0.08:
                    # Slow vertical wave that dims parts of the face
                    wave = math.sin((y + self._time * 8) * 0.3) * 0.15
                    face_map[y][x] = _clamp(face_map[y][x] - 0.10 + wave, 0.03, 0.85)

        # One eye slowly closing, the other barely open
        self._set_eye_region(face_map, self._LEFT_EYE_CX, self._EYE_CY, "half", 1.0, 0.5)
        self._set_eye_region(face_map, self._RIGHT_EYE_CX, self._EYE_CY, "open", -0.5, 0.5)

        # Slow downward drift — face sinks 1px
        drift: int = int(math.sin(self._time * 0.5) * 1.5)
        if drift > 0:
            for y in range(self.height - 1, drift - 1, -1):
                face_map[y] = face_map[y - drift][:]
            for y in range(drift):
                face_map[y] = [0.02] * self.width

    def _apply_happy(
        self,
        face_map: list[list[float]],
        now: float,
        dt: float,
    ) -> None:
        """Happy: warm palette, bright face, ^_^ eyes, wide mouth."""
        # ^_^ eyes
        self._set_eye_region(face_map, self._LEFT_EYE_CX, self._EYE_CY, "happy")
        self._set_eye_region(face_map, self._RIGHT_EYE_CX, self._EYE_CY, "happy")

        # Wide bright mouth
        self._set_mouth_region(face_map, 0.50, 1.3)

    def _apply_sleeping(
        self,
        face_map: list[list[float]],
        now: float,
        dt: float,
    ) -> None:
        """Sleeping: low shimmer, dark, eyes closed, firefly sparks."""
        # Eyes closed
        self._set_eye_region(face_map, self._LEFT_EYE_CX, self._EYE_CY, "closed")
        self._set_eye_region(face_map, self._RIGHT_EYE_CX, self._EYE_CY, "closed")

        # Firefly pixels — occasionally spawn one
        if random.random() < 0.02:
            # Pick a random pixel that's inside the face (brightness > 0.1)
            fx = random.randint(10, 53)
            fy = random.randint(5, 55)
            if self._base_face_map[fy][fx] > 0.1:
                self._firefly_pixels.append((fx, fy, 0.5))

        # Update and apply fireflies
        alive: list[tuple[int, int, float]] = []
        for fx, fy, life in self._firefly_pixels:
            new_life = life - dt
            if new_life > 0:
                alive.append((fx, fy, new_life))
                # Brighten this pixel in the face map
                face_map[fy][fx] = min(1.0, face_map[fy][fx] + life * 1.5)
        self._firefly_pixels = alive

    # ------------------------------------------------------------------
    # State-dependent palette, shimmer, brightness
    # ------------------------------------------------------------------

    def _get_state_palette(self, state: FaceState) -> list[tuple[int, int, int]]:
        """Return the active palette, possibly modified by state."""
        p = list(self._palette)
        if state == FaceState.ERROR:
            # Muted, desaturated — something fading out quietly
            p[0] = (25, 20, 20)       # dark warm gray
            p[1] = (140, 80, 50)      # dull amber
            p[2] = (110, 105, 100)    # warm gray
            p[3] = (190, 180, 170)    # faded cream
        elif state == FaceState.HAPPY:
            # Soft warm glow — golden, not harsh
            p[1] = (210, 150, 50)     # soft gold
            p[2] = (230, 210, 100)    # warm yellow
        elif state == FaceState.SLEEPING:
            # Deep midnight blue palette
            p[0] = (8, 10, 35)        # deep midnight
            p[1] = (25, 35, 80)       # dark blue
            p[2] = (50, 70, 130)      # muted blue
            p[3] = (90, 105, 160)     # soft blue-gray
        return p

    def _get_state_shimmer(self, state: FaceState) -> float:
        """Return shimmer intensity for the current state.

        Lower = more stable / coherent face. Higher = more pixel noise.
        Sleeping's calm 0.15 is the baseline feel; other states add subtle
        texture without overwhelming the face shape.
        """
        if state == FaceState.SLEEPING:
            return 0.12
        if state == FaceState.IDLE:
            return 0.20
        if state == FaceState.LISTENING:
            return 0.18
        if state == FaceState.THINKING:
            return 0.30
        if state == FaceState.SPEAKING:
            return 0.25
        if state == FaceState.ERROR:
            return 0.18
        if state == FaceState.HAPPY:
            return 0.28
        return 0.20

    def _get_brightness_multiplier(self, state: FaceState) -> float:
        """Return overall brightness multiplier for the face map."""
        if state == FaceState.LISTENING:
            return 1.2
        if state == FaceState.THINKING:
            return 0.85
        if state == FaceState.SPEAKING:
            # Slight pulse with amplitude
            return 1.0 + 0.15 * self._amplitude
        if state == FaceState.ERROR:
            return 1.0
        if state == FaceState.HAPPY:
            return 1.3
        if state == FaceState.SLEEPING:
            return 0.5
        return 1.0
