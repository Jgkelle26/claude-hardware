"""Clod application entry point."""

from __future__ import annotations

import argparse
import asyncio
import logging
import signal
from typing import Awaitable

from clod.audio_capture import AudioCapture
from clod.claude_bridge import ClaudeBridge
from clod.config import load_config
from clod.event_bus import EventBus
from clod.servo_controller import ServoController
from clod.state_machine import StateMachine
from clod.stt_engine import STTEngine
from clod.tts_engine import TTSEngine
from clod.wake_word import WakeWord

logger = logging.getLogger(__name__)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Clod desk robot.")
    parser.add_argument(
        "--mock-hardware",
        action="store_true",
        help="Use mock hardware backends (no-op placeholder).",
    )
    parser.add_argument(
        "--config",
        default="config.yaml",
        help="Path to config.yaml.",
    )
    return parser.parse_args()


async def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    args = _parse_args()
    config = load_config(args.config)

    bus = EventBus()
    state_machine = StateMachine(bus)
    _ = state_machine  # retained so its subscriptions stay live

    audio_capture = AudioCapture(bus, config.audio)
    stt = STTEngine(bus, config.vosk)
    tts = TTSEngine(bus, config.piper)
    claude = ClaudeBridge(bus, config.mac_ssh)
    wake = WakeWord(bus, config.behavior)
    servo = ServoController(bus, config.gpio)

    tasks: list[Awaitable[None]] = [
        audio_capture.run(),
        stt.run(),
        tts.run(),
        claude.run(),
        wake.run(),
        servo.run(),
    ]

    try:
        from clod.matrix_renderer import MatrixRenderer
        from clod.matrix_backends import MockMatrixBackend

        backend = MockMatrixBackend(config.matrix)
        renderer = MatrixRenderer(bus, config.matrix, backend)
        tasks.append(renderer.run())
    except ImportError as exc:
        logger.warning("Matrix renderer unavailable; continuing without it: %s", exc)

    running_tasks = [asyncio.create_task(t) for t in tasks]

    loop = asyncio.get_running_loop()
    stop_event = asyncio.Event()

    def _request_shutdown() -> None:
        logger.info("Shutdown signal received; cancelling tasks.")
        stop_event.set()

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, _request_shutdown)
        except NotImplementedError:
            # Signal handlers aren't available on some platforms (e.g. Windows).
            pass

    gather_task = asyncio.gather(*running_tasks, return_exceptions=True)
    stop_waiter = asyncio.create_task(stop_event.wait())

    done, _pending = await asyncio.wait(
        [gather_task, stop_waiter],
        return_when=asyncio.FIRST_COMPLETED,
    )

    if stop_waiter in done:
        for t in running_tasks:
            t.cancel()
        await asyncio.gather(*running_tasks, return_exceptions=True)


if __name__ == "__main__":
    asyncio.run(main())
