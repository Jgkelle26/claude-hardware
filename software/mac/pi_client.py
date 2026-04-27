from __future__ import annotations

import asyncio
import logging

logger = logging.getLogger(__name__)


class PiClient:
    """Sends face state strings to the Pi's display server over TCP."""

    def __init__(self, host: str = "clod.local", port: int = 9999) -> None:
        self._host = host
        self._port = port
        self._reader: asyncio.StreamReader | None = None
        self._writer: asyncio.StreamWriter | None = None
        self._connected = False

    async def connect(self) -> None:
        """Connect to Pi. Non-blocking, retries on failure."""
        if self._connected:
            return
        try:
            self._reader, self._writer = await asyncio.wait_for(
                asyncio.open_connection(self._host, self._port),
                timeout=5.0,
            )
            self._connected = True
            logger.info("Connected to Pi at %s:%d", self._host, self._port)
        except (OSError, asyncio.TimeoutError) as exc:
            logger.warning("Could not connect to Pi at %s:%d: %s", self._host, self._port, exc)
            self._connected = False

    async def send_state(self, state: str) -> None:
        """Send a state string like 'idle', 'listening', 'thinking', 'speaking', 'error'.

        If the Pi is unreachable, logs a warning and continues.
        Attempts to reconnect automatically if the connection was lost.
        """
        if not self._connected:
            await self.connect()
        if not self._connected or self._writer is None:
            logger.warning("Pi not connected, skipping state send: %s", state)
            return
        try:
            message = f"{state}\n".encode("utf-8")
            self._writer.write(message)
            await self._writer.drain()
            logger.debug("Sent state to Pi: %s", state)
        except (OSError, ConnectionResetError) as exc:
            logger.warning("Failed to send state '%s' to Pi: %s", state, exc)
            self._connected = False
            self._writer = None
            self._reader = None

    async def disconnect(self) -> None:
        """Close the connection to the Pi."""
        if self._writer is not None:
            try:
                self._writer.close()
                await self._writer.wait_closed()
            except OSError:
                pass
        self._writer = None
        self._reader = None
        self._connected = False
        logger.info("Disconnected from Pi")
