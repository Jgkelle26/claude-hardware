"""Quick Particles theme demo on Mac."""
import asyncio
import threading
from clod.event_bus import EventBus
from clod.events import FACE_SET_STATE, FaceState
from clod.matrix_backends import MockMatrixBackend
from clod.themes.particles import ParticleCloudTheme
from clod.themes.theme_manager import ThemeManager

bus = EventBus()
backend = MockMatrixBackend()
manager = ThemeManager(bus, backend)

theme = ParticleCloudTheme()
manager.add_theme(theme)

# Force initialization
theme.on_activate()
theme.set_state(FaceState.IDLE)

STATES = [FaceState.IDLE, FaceState.LISTENING, FaceState.THINKING,
          FaceState.SPEAKING, FaceState.HAPPY, FaceState.ERROR, FaceState.SLEEPING]

async def run():
    # Emit initial state
    await bus.emit(FACE_SET_STATE, FaceState.IDLE)
    i = 0
    while True:
        state = STATES[i % len(STATES)]
        print(f"state -> {state.value}")
        await bus.emit(FACE_SET_STATE, state)
        await asyncio.sleep(4.0)
        i += 1

async def main():
    await asyncio.gather(manager.run(), run())

def runner():
    asyncio.run(main())

print("Particles demo — watch the window. Ctrl+C to exit.")
t = threading.Thread(target=runner, daemon=True)
t.start()
backend.mainloop()
