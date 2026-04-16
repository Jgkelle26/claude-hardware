"""Wake word detector. Emits wake.detected when trigger phrase is heard."""

from __future__ import annotations

import logging
from typing import Any

from clod.event_bus import EventBus

logger = logging.getLogger(__name__)


class WakeWord:
    """Listens for the wake word and emits wake.detected events."""

    def __init__(self, bus: EventBus, config: Any) -> None:
        self._bus = bus
        self._config = config

    async def run(self) -> None:
        """Main wake word detection loop."""
        # TODO: implement
        ...
