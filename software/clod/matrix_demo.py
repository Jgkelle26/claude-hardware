"""Standalone demo: cycles themes and face states on the mock matrix display.

Tkinter must run on the main thread, so we start the asyncio event loop in a
background daemon thread and drive the tkinter mainloop on the main thread.

Run from the ``software/`` directory::

    python -m clod.matrix_demo

Press **T** in the window to cycle to the next theme.
"""

from __future__ import annotations

import asyncio
import threading

from clod.event_bus import EventBus
from clod.events import FACE_SET_STATE, FaceState
from clod.matrix_backends import MockMatrixBackend
from clod.themes import (
    CharacterTheme,
    CompositionTheme,
    EtherealTheme,
    ParticleCloudTheme,
    ThemeManager,
)

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


async def _async_main(bus: EventBus, manager: ThemeManager) -> None:
    render_task = asyncio.create_task(manager.run())
    cycle_task = asyncio.create_task(_state_cycler(bus))
    try:
        await asyncio.gather(render_task, cycle_task)
    except asyncio.CancelledError:
        pass
    finally:
        for t in (render_task, cycle_task):
            t.cancel()
        for t in (render_task, cycle_task):
            try:
                await t
            except (asyncio.CancelledError, Exception):
                pass


def _asyncio_runner(
    bus: EventBus,
    manager: ThemeManager,
    loop_holder: list[asyncio.AbstractEventLoop],
) -> None:
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop_holder.append(loop)
    try:
        loop.run_until_complete(_async_main(bus, manager))
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

    manager = ThemeManager(bus, backend)
    manager.add_theme(CompositionTheme())
    manager.add_theme(EtherealTheme())
    manager.add_theme(ParticleCloudTheme())
    manager.add_theme(CharacterTheme())

    print(f"[demo] active theme: {manager.current_theme_name}")
    print(
        "Clod demo running -- press Ctrl+C to exit, T to cycle themes. "
        "Watch the window for emotion state changes."
    )

    # Keyboard binding: T/t cycles to the next theme.
    def _on_key(event: object) -> None:
        # tkinter event objects expose .char
        char = getattr(event, "char", "")
        if char in ("t", "T"):
            manager.next_theme()
            print(f"[demo] theme -> {manager.current_theme_name}")

    backend.root.bind("<Key>", _on_key)

    loop_holder: list[asyncio.AbstractEventLoop] = []
    thread = threading.Thread(
        target=_asyncio_runner,
        args=(bus, manager, loop_holder),
        daemon=True,
    )
    thread.start()

    try:
        backend.mainloop()
    except KeyboardInterrupt:
        print("\n[demo] Ctrl+C received, shutting down.")
    finally:
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
