"""Quick Bear theme demo on Mac."""
import asyncio
import threading
from clod.event_bus import EventBus
from clod.events import FACE_SET_STATE, FaceState
from clod.matrix_backends import MockMatrixBackend
from clod.themes.bear import BearTheme
from clod.themes.theme_manager import ThemeManager

bus = EventBus()
backend = MockMatrixBackend()
manager = ThemeManager(bus, backend)
manager.add_theme(BearTheme())

STATES = [FaceState.IDLE, FaceState.LISTENING, FaceState.THINKING,
          FaceState.SPEAKING, FaceState.HAPPY, FaceState.ERROR, FaceState.SLEEPING]

async def run():
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

print("Bear demo — watch the window. Ctrl+C to exit.")
t = threading.Thread(target=runner, daemon=True)
t.start()
backend.mainloop()
