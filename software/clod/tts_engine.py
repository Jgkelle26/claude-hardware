"""Text-to-speech engine: consumes claude.stream_chunk, plays audio via Piper."""

from __future__ import annotations

import logging
from typing import Any

from clod.event_bus import EventBus

logger = logging.getLogger(__name__)


class TTSEngine:
    """Synthesizes speech with Piper and plays it back, emitting tts.start / tts.end."""

    def __init__(self, bus: EventBus, config: Any) -> None:
        self._bus = bus
        self._config = config

    async def run(self) -> None:
        """Main TTS loop."""
        # TODO: implement
        ...
