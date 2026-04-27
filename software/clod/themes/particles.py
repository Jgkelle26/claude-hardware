"""Theme C -- Particle Cloud.

A dense cluster of multicolored particles centered on the display that
drift, orbit, scatter, and pulse in response to the robot's state.  Deep
purple background with full-spectrum particle colors.
"""

from __future__ import annotations

import colorsys
import math
import random
import time
from dataclasses import dataclass, field

from PIL import Image

from clod.events import FaceState
from clod.themes.base import ThemeRenderer

# ---------------------------------------------------------------------------
# Background
# ---------------------------------------------------------------------------

_BG_COLOR: tuple[int, int, int] = (8, 10, 18)

# ---------------------------------------------------------------------------
# Palette
# ---------------------------------------------------------------------------


def _generate_palette(n: int = 30) -> list[tuple[int, int, int]]:
    """Full-spectrum bright palette — no dark colors."""
    colors: list[tuple[int, int, int]] = []
    for i in range(n):
        hue = i / n
        r, g, b = colorsys.hls_to_rgb(hue, 0.6, 1.0)
        colors.append((int(r * 255), int(g * 255), int(b * 255)))
    # Add some whites for brightness
    colors.extend([(255, 255, 255)] * 5)
    return colors


_PALETTE: list[tuple[int, int, int]] = _generate_palette()

# Per-state color overrides — applied each frame
_STATE_PALETTES: dict[FaceState, list[tuple[int, int, int]]] = {
    FaceState.IDLE: [
        (120, 50, 200), (160, 80, 255), (90, 30, 170),
        (255, 255, 255), (200, 200, 220),
        (0, 0, 0), (10, 5, 20),
    ],  # purple, white, black
    FaceState.LISTENING: [
        (180, 120, 60), (140, 90, 45), (200, 160, 90),
        (160, 100, 50), (120, 80, 40), (220, 180, 120),
        (100, 70, 35),
    ],  # earth tones — warm browns, tans, clay
    FaceState.THINKING: [
        (80, 60, 255), (120, 80, 255), (60, 40, 200),
        (150, 100, 255), (40, 30, 180),
    ],  # deep purples and indigos
    FaceState.SPEAKING: [
        (255, 200, 50), (255, 150, 30), (255, 100, 20),
        (255, 240, 100), (255, 80, 10),
    ],  # fiery oranges and yellows
    FaceState.ERROR: [
        (255, 30, 30), (255, 60, 60), (200, 0, 0),
        (255, 100, 80), (180, 20, 20),
    ],  # reds
    FaceState.HAPPY: [
        (255, 50, 200), (50, 255, 150), (255, 255, 50),
        (50, 200, 255), (255, 100, 50), (200, 50, 255),
    ],  # rainbow party
    FaceState.SLEEPING: [
        (30, 30, 50), (40, 40, 70), (50, 50, 80),
        (35, 35, 60),
    ],  # dark blues
}

# ---------------------------------------------------------------------------
# Particle dataclass
# ---------------------------------------------------------------------------


@dataclass
class Particle:
    x: float
    y: float
    vx: float
    vy: float
    color: tuple[int, int, int]
    size: int
    home_x: float
    home_y: float
    # Mutable per-particle state used by certain modes
    base_color: tuple[int, int, int] = field(default=(0, 0, 0), repr=False)
    hue_offset: float = 0.0


# ---------------------------------------------------------------------------
# Theme
# ---------------------------------------------------------------------------


class ParticleCloudTheme(ThemeRenderer):
    """Particle cloud theme -- multicolored dots that coalesce and scatter."""

    # -- abstract property ------------------------------------------------
    @property
    def name(self) -> str:  # noqa: D401
        return "Particles"

    # -- lifecycle --------------------------------------------------------

    def __init__(self, width: int = 64, height: int = 64) -> None:
        super().__init__(width, height)
        self._particles: list[Particle] = []
        self._time: float = 0.0
        self._breathing_phase: float = 0.0
        self._speak_timer: float = 0.0
        self._error_freeze_timer: float = 0.0
        self._happy_burst_done: bool = False
        self._prev_state: FaceState = FaceState.IDLE
        self._firefly_index: int = -1
        self._firefly_timer: float = 0.0

    def on_activate(self) -> None:
        """Spawn the particle field."""
        self._particles = self._spawn_particles(count=300)
        self._time = 0.0
        self._breathing_phase = 0.0
        self._speak_timer = 0.0
        self._error_freeze_timer = 0.0
        self._happy_burst_done = False
        self._prev_state = FaceState.IDLE
        self._firefly_index = -1
        self._firefly_timer = 0.0

    def on_deactivate(self) -> None:
        self._particles.clear()

    # -- state transitions ------------------------------------------------

    def set_state(self, state: FaceState) -> None:
        prev = self._current_state
        super().set_state(state)
        if state != prev:
            self._prev_state = prev
            # Reset per-state timers
            if state == FaceState.SPEAKING:
                self._speak_timer = 0.0
            if state == FaceState.ERROR:
                self._error_freeze_timer = 0.0
            if state == FaceState.HAPPY:
                self._happy_burst_done = False

    # -- drawing ----------------------------------------------------------

    def draw_frame(self, dt: float) -> Image.Image:
        self._time += dt

        # Physics
        self._simulate(dt)

        # Render
        img = Image.new("RGB", (self.width, self.height), _BG_COLOR)
        pixels = img.load()
        assert pixels is not None

        state_palette = _STATE_PALETTES.get(self._current_state, _PALETTE)

        for p in self._particles:
            # Recolor from state palette each frame for shimmer
            color = random.choice(state_palette)
            # HAPPY: also rotate hue for extra chaos
            if self._current_state == FaceState.HAPPY:
                color = self._rotated_color(p)
            # SLEEPING firefly flash
            if (
                self._current_state == FaceState.SLEEPING
                and self._firefly_index >= 0
                and p is self._particles[self._firefly_index]
            ):
                brightness = max(0.0, 1.0 - abs(self._firefly_timer - 1.0))
                wr = int(255 * brightness + color[0] * (1.0 - brightness))
                wg = int(255 * brightness + color[1] * (1.0 - brightness))
                wb = int(255 * brightness + color[2] * (1.0 - brightness))
                color = (min(wr, 255), min(wg, 255), min(wb, 255))

            ix, iy = int(p.x), int(p.y)
            # Breathe: some particles pulse to 2px based on a wave
            pulse = math.sin(self._time * 3.0 + p.home_x * 0.5) > 0.5
            draw_size = 2 if pulse else 1

            if draw_size == 1:
                if 0 <= ix < self.width and 0 <= iy < self.height:
                    pixels[ix, iy] = color
            else:
                # 2px: draw center + one neighbor (not a full block — stays tiny)
                if 0 <= ix < self.width and 0 <= iy < self.height:
                    pixels[ix, iy] = color
                nx, ny = ix + 1, iy
                if 0 <= nx < self.width and 0 <= ny < self.height:
                    pixels[nx, ny] = color

        return img

    # -- simulation -------------------------------------------------------

    def _simulate(self, dt: float) -> None:
        state = self._current_state
        cx, cy = self.width / 2.0, self.height / 2.0

        # Per-state bookkeeping
        self._breathing_phase += dt
        if state == FaceState.SPEAKING:
            self._speak_timer += dt
        if state == FaceState.ERROR:
            self._error_freeze_timer += dt
        if state == FaceState.SLEEPING:
            self._firefly_timer += dt
            if self._firefly_timer > 2.0:
                self._firefly_timer = 0.0
                if self._particles:
                    self._firefly_index = random.randint(0, len(self._particles) - 1)
                else:
                    self._firefly_index = -1
        if state == FaceState.HAPPY:
            for p in self._particles:
                p.hue_offset += dt * 0.1  # slow rotation

        # ERROR freeze: zero velocity for 200ms windows
        error_frozen = False
        if state == FaceState.ERROR:
            cycle = self._error_freeze_timer % 0.7
            if cycle > 0.5:
                error_frozen = True

        for p in self._particles:
            if error_frozen:
                p.vx = 0.0
                p.vy = 0.0
                continue

            # 1. Apply velocity
            p.x += p.vx * dt
            p.y += p.vy * dt

            # 2. State-dependent force
            fx, fy = self._state_force(p, state, cx, cy, dt)
            p.vx += fx * dt
            p.vy += fy * dt

            # 3. Drag — light so swarm stays fast
            drag = 0.99
            if state == FaceState.SLEEPING:
                drag = 0.92
            p.vx *= drag
            p.vy *= drag

            # 4. Soft bounce at edges
            self._bounce(p)

            # 5. Jitter — swarming energy
            jitter_scale = 2.0
            if state == FaceState.SLEEPING:
                jitter_scale = 0.1
            p.vx += random.gauss(0, jitter_scale)
            p.vy += random.gauss(0, jitter_scale)

    def _state_force(
        self,
        p: Particle,
        state: FaceState,
        cx: float,
        cy: float,
        dt: float,
    ) -> tuple[float, float]:
        """Return (fx, fy) force for the current state."""

        dx_home = p.home_x - p.x
        dy_home = p.home_y - p.y
        dx_center = cx - p.x
        dy_center = cy - p.y
        dist_center = math.sqrt(dx_center * dx_center + dy_center * dy_center) or 0.001

        if state == FaceState.IDLE:
            # Gravity toward home — fast return
            fx = dx_home * 0.15
            fy = dy_home * 0.15
            # Breathing pulse: outward push every ~3 seconds
            breath = math.sin(self._breathing_phase * (2.0 * math.pi / 3.0))
            if breath > 0.7:
                outward = (breath - 0.7) * 3.0  # ramp
                nx = -dx_center / dist_center
                ny = -dy_center / dist_center
                fx += nx * outward * 0.5
                fy += ny * outward * 0.5
            return (fx, fy)

        if state == FaceState.LISTENING:
            fx = dx_center * 0.25
            fy = dy_center * 0.25
            # Amplitude pushes outward
            if self._amplitude > 0.01 and dist_center > 0.5:
                nx = -dx_center / dist_center
                ny = -dy_center / dist_center
                push = self._amplitude * 2.0
                fx += nx * push
                fy += ny * push
            return (fx, fy)

        if state == FaceState.THINKING:
            # Split into four tight clusters in corners
            corners = [(10.0, 10.0), (54.0, 10.0), (10.0, 54.0), (54.0, 54.0)]
            # Assign particle to a corner based on its home position quadrant
            if p.home_x < 32:
                best_cx = 10.0 if p.home_y < 32 else 10.0
                best_cy = 10.0 if p.home_y < 32 else 54.0
            else:
                best_cx = 54.0 if p.home_y < 32 else 54.0
                best_cy = 10.0 if p.home_y < 32 else 54.0
            dx_corner = best_cx - p.x
            dy_corner = best_cy - p.y
            dist_corner = math.sqrt(dx_corner ** 2 + dy_corner ** 2) + 0.01
            # Very strong pull — pack them tight
            fx = dx_corner * 0.6
            fy = dy_corner * 0.6
            # Orbit within the cluster for swarming feel
            tx = -dy_corner / dist_corner
            ty = dx_corner / dist_corner
            fx += tx * 2.0
            fy += ty * 2.0
            return (fx, fy)

        if state == FaceState.SPEAKING:
            # Strong pull to center — swarm crammed into a tight ball
            fx = dx_center * 0.5
            fy = dy_center * 0.5
            # Jitter keeps them buzzing even when packed tight
            return (fx, fy)

        if state == FaceState.ERROR:
            # Strong outward flee
            if dist_center > 0.5:
                nx = -dx_center / dist_center
                ny = -dy_center / dist_center
                return (nx * 12.0, ny * 12.0)
            return (0.0, 0.0)

        if state == FaceState.HAPPY:
            if not self._happy_burst_done:
                # Initial burst outward
                self._happy_burst_done = True
                for pp in self._particles:
                    ddx = pp.x - cx
                    ddy = pp.y - cy
                    dd = math.sqrt(ddx * ddx + ddy * ddy) or 0.001
                    pp.vx += (ddx / dd) * 15.0
                    pp.vy += (ddy / dd) * 15.0
            # Gentle drift back + swirl
            tx = -dy_center / dist_center
            ty = dx_center / dist_center
            fx = dx_center * 0.01 + tx * 0.3
            fy = dy_center * 0.01 + ty * 0.3
            return (fx, fy)

        if state == FaceState.SLEEPING:
            # Pull to bottom of screen — gravity + slight spread along x
            target_y = 58.0
            target_x = p.home_x  # spread along original x positions
            dx_t = target_x - p.x
            dy_t = target_y - p.y
            fx = dx_t * 0.05
            fy = dy_t * 0.15  # stronger downward pull
            return (fx, fy)

        # Fallback: drift toward home
        return (dx_home * 0.02, dy_home * 0.02)

    # -- helpers ----------------------------------------------------------

    @staticmethod
    def _bounce(p: Particle) -> None:
        """Soft bounce off edges with 50% energy loss."""
        if p.x < 0:
            p.x = 0.0
            p.vx = -p.vx * 0.5
        elif p.x > 63:
            p.x = 63.0
            p.vx = -p.vx * 0.5
        if p.y < 0:
            p.y = 0.0
            p.vy = -p.vy * 0.5
        elif p.y > 63:
            p.y = 63.0
            p.vy = -p.vy * 0.5

    @staticmethod
    def _rotated_color(p: Particle) -> tuple[int, int, int]:
        """Rotate a particle's base colour through the hue wheel."""
        bc = p.base_color
        # Convert base to HLS, shift hue, convert back
        r, g, b = bc[0] / 255.0, bc[1] / 255.0, bc[2] / 255.0
        # Skip near-black (dark accent particles)
        if r + g + b < 0.15:
            return bc
        h, l, s = colorsys.rgb_to_hls(r, g, b)
        h = (h + p.hue_offset) % 1.0
        rr, gg, bb = colorsys.hls_to_rgb(h, l, s)
        return (int(rr * 255), int(gg * 255), int(bb * 255))

    def _spawn_particles(self, count: int = 200) -> list[Particle]:
        """Create the initial particle field with Gaussian distribution."""
        cx, cy = self.width / 2.0, self.height / 2.0
        sigma = 20.0
        particles: list[Particle] = []
        for _ in range(count):
            x = random.gauss(cx, sigma)
            y = random.gauss(cy, sigma)
            # Clamp to canvas
            x = max(0.0, min(float(self.width - 1), x))
            y = max(0.0, min(float(self.height - 1), y))
            vx = random.uniform(-5.0, 5.0)
            vy = random.uniform(-5.0, 5.0)
            color = random.choice(_PALETTE)
            # All single pixel
            size = 1
            p = Particle(
                x=x,
                y=y,
                vx=vx,
                vy=vy,
                color=color,
                size=size,
                home_x=x,
                home_y=y,
                base_color=color,
                hue_offset=random.random(),
            )
            particles.append(p)
        return particles
