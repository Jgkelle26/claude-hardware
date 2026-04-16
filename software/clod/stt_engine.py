"""Speech-to-text engine: consumes audio.chunk, emits stt.partial / stt.final."""

from __future__ import annotations

import logging
from typing import Any

from clod.event_bus import EventBus

logger = logging.getLogger(__name__)


class STTEngine:
    """Runs Vosk on incoming audio chunks and emits STT events."""

    def __init__(self, bus: EventBus, config: Any) -> None:
        self._bus = bus
        self._config = config

    async def run(self) -> None:
        """Main STT loop."""
        # TODO: implement
        ...
