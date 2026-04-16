"""Bridge to Claude Code running on the Mac via SSH."""

from __future__ import annotations

import logging
from typing import Any

from clod.event_bus import EventBus

logger = logging.getLogger(__name__)


class ClaudeBridge:
    """Forwards stt.final transcripts to Claude Code over SSH and streams replies back."""

    def __init__(self, bus: EventBus, config: Any) -> None:
        self._bus = bus
        self._config = config

    async def run(self) -> None:
        """Main bridge loop."""
        # TODO: implement
        ...
