"""TCP server that receives face state events from the Mac orchestrator.

The Mac sends state names as UTF-8 strings terminated by ``\\n``.
Example: ``"listening\\n"``, ``"thinking\\n"``.

Special commands:
- ``"theme:Bear\\n"`` — switch to the named theme.
- ``"theme:next\\n"`` — cycle to the next theme.
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

from clod.events import FACE_SET_STATE, FaceState

if TYPE_CHECKING:
    from clod.event_bus import EventBus

logger = logging.getLogger(__name__)


class PiStateServer:
    """TCP server that receives face state events from the Mac orchestrator."""

    def __init__(self, bus: EventBus, host: str = "0.0.0.0", port: int = 9999) -> None:
        self.bus = bus
        self.host = host
        self.port = port

    async def run(self) -> None:
        """Start the TCP server and listen for connections."""
        server = await asyncio.start_server(
            self._handle_client, self.host, self.port
        )
        addrs = ", ".join(str(s.getsockname()) for s in server.sockets)
        print(f"[PiStateServer] Listening on {addrs}")
        logger.info("PiStateServer listening on %s", addrs)

        async with server:
            await server.serve_forever()

    async def _handle_client(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        """Handle a single client connection, reading newline-delimited commands."""
        peer = writer.get_extra_info("peername")
        logger.info("Client connected: %s", peer)
        print(f"[PiStateServer] Client connected: {peer}")

        try:
            while True:
                data = await reader.readline()
                if not data:
                    # Connection closed by remote end.
                    break

                line = data.decode("utf-8", errors="replace").strip()
                if not line:
                    continue

                await self._process_line(line)
        except asyncio.CancelledError:
            logger.debug("Client handler cancelled for %s", peer)
        except ConnectionResetError:
            logger.warning("Connection reset by %s", peer)
        except Exception:
            logger.exception("Unexpected error handling client %s", peer)
        finally:
            logger.info("Client disconnected: %s", peer)
            print(f"[PiStateServer] Client disconnected: {peer}")
            writer.close()
            try:
                await writer.wait_closed()
            except Exception:
                pass

    async def _process_line(self, line: str) -> None:
        """Parse a single command line and emit the appropriate event."""
        # Theme switching commands: "theme:<name>" or "theme:next"
        if line.startswith("theme:"):
            theme_arg = line[len("theme:"):]
            logger.info("Theme command received: %r", theme_arg)
            print(f"[PiStateServer] Theme command: {theme_arg}")
            await self.bus.emit("theme.switch", theme_arg)
            return

        # Face state commands
        try:
            state = FaceState(line)
        except ValueError:
            logger.warning("Unknown state received: %r (ignoring)", line)
            return

        logger.info("State received: %s", state.value)
        print(f"[PiStateServer] State: {state.value}")
        await self.bus.emit(FACE_SET_STATE, state)
