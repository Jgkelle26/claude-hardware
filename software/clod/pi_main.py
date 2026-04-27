"""Clod Pi-side display driver.

Receives state events from the Mac orchestrator over TCP and drives
the 64x64 RGB LED matrix with the active theme.

Run with sudo (required for GPIO access):
    sudo /path/to/venv/python3 -m clod.pi_main

Or with options:
    sudo /path/to/venv/python3 -m clod.pi_main --theme Bear --brightness 30
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import signal
import sys
from typing import Any

from clod.event_bus import EventBus
from clod.matrix_backends import RealMatrixBackend
from clod.pi_server import PiStateServer
from clod.themes import get_all_themes
from clod.themes.theme_manager import ThemeManager

logger = logging.getLogger(__name__)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Clod Pi-side display driver — listens for state events "
        "from the Mac orchestrator and drives the 64x64 RGB LED matrix.",
    )
    parser.add_argument(
        "--theme",
        type=str,
        default="Bear",
        help="Initial theme name (default: Bear)",
    )
    parser.add_argument(
        "--brightness",
        type=int,
        default=30,
        help="LED matrix brightness 1-100 (default: 30)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=9999,
        help="TCP port to listen on (default: 9999)",
    )
    parser.add_argument(
        "--slowdown",
        type=int,
        default=10,
        help="GPIO slowdown factor (default: 10)",
    )
    parser.add_argument(
        "--fps",
        type=int,
        default=20,
        help="Target frames per second (default: 20)",
    )
    return parser.parse_args(argv)


def _select_theme_by_name(theme_manager: ThemeManager, name: str) -> bool:
    """Set the active theme by name.  Returns True if found."""
    for i, theme in enumerate(theme_manager.themes):
        if theme.name.lower() == name.lower():
            if i != theme_manager.active_index:
                theme_manager.themes[theme_manager.active_index].on_deactivate()
                theme_manager.active_index = i
                theme_manager.themes[i].on_activate()
                logger.info("Selected theme %r", theme.name)
            return True
    logger.warning("Theme %r not found", name)
    return False


def _on_theme_switch(theme_manager: ThemeManager) -> Any:
    """Return an event handler for theme.switch events."""

    def handler(payload: Any) -> None:
        if not isinstance(payload, str):
            return
        if payload.lower() == "next":
            theme_manager.next_theme()
            print(f"[Clod] Switched to theme: {theme_manager.current_theme_name}")
        elif payload.lower() == "previous":
            theme_manager.previous_theme()
            print(f"[Clod] Switched to theme: {theme_manager.current_theme_name}")
        else:
            if _select_theme_by_name(theme_manager, payload):
                print(f"[Clod] Switched to theme: {theme_manager.current_theme_name}")
            else:
                print(f"[Clod] Unknown theme: {payload}")

    return handler


async def main(args: argparse.Namespace) -> None:
    """Wire up components and run the display driver."""
    # --- Matrix backend --------------------------------------------------- #
    print(f"[Clod] Initialising 64x64 matrix (brightness={args.brightness}, "
          f"slowdown={args.slowdown})")
    backend = RealMatrixBackend(
        rows=64,
        cols=64,
        brightness=args.brightness,
        hardware_mapping="regular",
        slowdown_gpio=args.slowdown,
    )

    # --- Event bus -------------------------------------------------------- #
    bus = EventBus()

    # --- Theme manager ---------------------------------------------------- #
    theme_manager = ThemeManager(bus, backend, fps=args.fps)

    themes = get_all_themes()
    for theme in themes:
        theme_manager.add_theme(theme)

    # Select the requested initial theme.
    if not _select_theme_by_name(theme_manager, args.theme):
        print(f"[Clod] Warning: theme {args.theme!r} not found, using first available")
        if theme_manager.themes:
            theme_manager.themes[0].on_activate()

    # Listen for theme switch events from the TCP server.
    bus.on("theme.switch", _on_theme_switch(theme_manager))

    print(f"[Clod] Active theme: {theme_manager.current_theme_name}")

    # --- TCP state server ------------------------------------------------- #
    server = PiStateServer(bus, port=args.port)

    # --- Run concurrently ------------------------------------------------- #
    print(f"[Clod] Starting render loop ({args.fps} FPS) and TCP server (port {args.port})")

    try:
        await asyncio.gather(
            theme_manager.run(),
            server.run(),
        )
    finally:
        print("[Clod] Shutting down — clearing matrix")
        backend.close()


def _run() -> None:
    """Entry point: parse args, set up logging, and run the async main."""
    args = parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    )

    loop = asyncio.new_event_loop()

    # Handle Ctrl+C gracefully.
    def _signal_handler() -> None:
        print("\n[Clod] Ctrl+C received — stopping")
        for task in asyncio.all_tasks(loop):
            task.cancel()

    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, _signal_handler)

    try:
        loop.run_until_complete(main(args))
    except asyncio.CancelledError:
        pass
    finally:
        loop.close()
        print("[Clod] Goodbye!")
        sys.exit(0)


if __name__ == "__main__":
    _run()
