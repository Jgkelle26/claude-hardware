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

_BG_COLOR: tuple[int, int, int] = (40, 20, 80)

# ---------------------------------------------------------------------------
# Palette
# ---------------------------------------------------------------------------


def _generate_palette(n: int = 30) -> list[tuple[int, int, int]]:
    """Full-spectrum palette plus dark accents for contrast."""
    colors: list[tuple[int, int, int]] = []
    for i in range(n):
        hue = i / n
        r, g, b = colorsys.hls_to_rgb(hue, 0.5, 0.9)
        colors.append((int(r * 255), int(g * 255), int(b * 255)))
    # Dark / black particles for visual contrast
    colors.extend([(0, 0, 0)] * 5)
    colors.extend([(40, 40, 40)] * 3)
    return colors


_PALETTE: list[tuple[int, int, int]] = _generate_palette()

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
        self._particles = self._spawn_particles(count=200)
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

        for p in self._particles:
            color = p.color
            # HAPPY: slowly rotate hue
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
            if p.size == 1:
                if 0 <= ix < self.width and 0 <= iy < self.height:
                    pixels[ix, iy] = color
            else:
                for ox in range(p.size):
                    for oy in range(p.size):
                        px, py = ix + ox, iy + oy
                        if 0 <= px < self.width and 0 <= py < self.height:
                            pixels[px, py] = color

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
                self._firefly_index = random.randint(0, len(self._particles) - 1)
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

            # 3. Drag
            drag = 0.98
            if state == FaceState.SLEEPING:
                drag = 0.95  # heavier drag for calm sleep
            p.vx *= drag
            p.vy *= drag

            # 4. Soft bounce at edges
            self._bounce(p)

            # 5. Jitter (tiny for sleeping)
            jitter_scale = 0.3
            if state == FaceState.SLEEPING:
                jitter_scale = 0.03
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
            # Gentle gravity toward home
            fx = dx_home * 0.02
            fy = dy_home * 0.02
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
            fx = dx_center * 0.05
            fy = dy_center * 0.05
            # Amplitude pushes outward
            if self._amplitude > 0.01 and dist_center > 0.5:
                nx = -dx_center / dist_center
                ny = -dy_center / dist_center
                push = self._amplitude * 2.0
                fx += nx * push
                fy += ny * push
            return (fx, fy)

        if state == FaceState.THINKING:
            # Orbit: tangential force perpendicular to center vector
            # Tangent direction (90 deg CCW): (-dy, dx)
            tx = -dy_center / dist_center
            ty = dx_center / dist_center
            # Edge particles orbit faster
            speed_factor = 0.5 + dist_center * 0.05
            fx = tx * speed_factor
            fy = ty * speed_factor
            # Mild inward pull to keep swirl coherent
            fx += dx_center * 0.01
            fy += dy_center * 0.01
            return (fx, fy)

        if state == FaceState.SPEAKING:
            # Rhythmic outward pulse every 0.5s
            cycle = self._speak_timer % 0.5
            if cycle < 0.1:
                # Impulse outward
                if dist_center > 0.5:
                    nx = -dx_center / dist_center
                    ny = -dy_center / dist_center
                    return (nx * 3.0, ny * 3.0)
            # Otherwise gentle pull back
            return (dx_center * 0.02, dy_center * 0.02)

        if state == FaceState.ERROR:
            # Strong outward flee
            if dist_center > 0.5:
                nx = -dx_center / dist_center
                ny = -dy_center / dist_center
                return (nx * 5.0, ny * 5.0)
            return (0.0, 0.0)

        if state == FaceState.HAPPY:
            if not self._happy_burst_done:
                # Initial burst outward
                self._happy_burst_done = True
                for pp in self._particles:
                    ddx = pp.x - cx
                    ddy = pp.y - cy
                    dd = math.sqrt(ddx * ddx + ddy * ddy) or 0.001
                    pp.vx += (ddx / dd) * 8.0
                    pp.vy += (ddy / dd) * 8.0
            # Gentle drift back + swirl
            tx = -dy_center / dist_center
            ty = dx_center / dist_center
            fx = dx_center * 0.01 + tx * 0.3
            fy = dy_center * 0.01 + ty * 0.3
            return (fx, fy)

        if state == FaceState.SLEEPING:
            # Very strong pull toward home
            fx = dx_home * 0.08
            fy = dy_home * 0.08
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
        sigma = 12.0
        particles: list[Particle] = []
        for _ in range(count):
            x = random.gauss(cx, sigma)
            y = random.gauss(cy, sigma)
            # Clamp to canvas
            x = max(0.0, min(float(self.width - 1), x))
            y = max(0.0, min(float(self.height - 1), y))
            vx = random.uniform(-0.5, 0.5)
            vy = random.uniform(-0.5, 0.5)
            color = random.choice(_PALETTE)
            size = 2 if random.random() < 0.2 else 1
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
