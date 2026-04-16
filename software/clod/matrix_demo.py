"""Standalone demo: cycles the procedural eye through all FaceState values.

Tkinter must run on the main thread, so we start the asyncio event loop in a
background daemon thread and drive the tkinter mainloop on the main thread.

Run from the `software/` directory:

    python -m clod.matrix_demo
"""

from __future__ import annotations

import asyncio
import threading

from clod.event_bus import EventBus
from clod.events import FACE_SET_STATE, FaceState
from clod.matrix_backends import MockMatrixBackend
from clod.matrix_renderer import MatrixRenderer

STATE_SEQUENCE: list[FaceState] = [
    FaceState.IDLE,
    FaceState.LISTENING,
    FaceState.THINKING,
    FaceState.SPEAKING,
    FaceState.HAPPY,
    FaceState.ERROR,
    FaceState.SLEEPING,
]

SECONDS_PER_STATE = 4.0


async def _state_cycler(bus: EventBus) -> None:
    i = 0
    while True:
        state = STATE_SEQUENCE[i % len(STATE_SEQUENCE)]
        print(f"[demo] state -> {state.value}")
        await bus.emit(FACE_SET_STATE, state)
        await asyncio.sleep(SECONDS_PER_STATE)
        i += 1


async def _async_main(bus: EventBus, renderer: MatrixRenderer) -> None:
    render_task = asyncio.create_task(renderer.run())
    cycle_task = asyncio.create_task(_state_cycler(bus))
    try:
        await asyncio.gather(render_task, cycle_task)
    except asyncio.CancelledError:
        pass
    finally:
        for t in (render_task, cycle_task):
            t.cancel()
        # Swallow cancellations.
        for t in (render_task, cycle_task):
            try:
                await t
            except (asyncio.CancelledError, Exception):
                pass


def _asyncio_runner(
    bus: EventBus,
    renderer: MatrixRenderer,
    loop_holder: list[asyncio.AbstractEventLoop],
) -> None:
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop_holder.append(loop)
    try:
        loop.run_until_complete(_async_main(bus, renderer))
    except Exception:
        pass
    finally:
        try:
            loop.close()
        except Exception:
            pass


def main() -> None:
    bus = EventBus()
    backend = MockMatrixBackend()
    renderer = MatrixRenderer(bus, backend)

    print(
        "Clod demo running — press Ctrl+C to exit. "
        "Watch the window for emotion state changes."
    )

    loop_holder: list[asyncio.AbstractEventLoop] = []
    thread = threading.Thread(
        target=_asyncio_runner,
        args=(bus, renderer, loop_holder),
        daemon=True,
    )
    thread.start()

    try:
        backend.mainloop()
    except KeyboardInterrupt:
        print("\n[demo] Ctrl+C received, shutting down.")
    finally:
        # Stop asyncio loop if it's still running.
        if loop_holder:
            loop = loop_holder[0]
            try:
                for task in asyncio.all_tasks(loop):
                    loop.call_soon_threadsafe(task.cancel)
            except Exception:
                pass
        backend.close()


if __name__ == "__main__":
    main()
