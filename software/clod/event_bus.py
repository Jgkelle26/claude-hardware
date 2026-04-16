"""Async pub/sub event bus with wildcard support."""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Callable

logger = logging.getLogger(__name__)


class EventBus:
    """In-process async pub/sub. Supports '<prefix>.*' wildcard subscriptions."""

    def __init__(self) -> None:
        self._subs: dict[str, list[Callable[..., Any]]] = {}

    def on(self, event_type: str, callback: Callable[..., Any]) -> None:
        """Register subscriber. event_type may end in '.*' for wildcard (e.g., 'audio.*')."""
        self._subs.setdefault(event_type, []).append(callback)

    async def emit(self, event_type: str, payload: Any = None) -> None:
        """Emit event to all matching subscribers. Callbacks can be sync or async."""
        callbacks: list[Callable[..., Any]] = []
        for pattern, subs in self._subs.items():
            if self._matches(pattern, event_type):
                callbacks.extend(subs)

        for cb in callbacks:
            try:
                if asyncio.iscoroutinefunction(cb):
                    await cb(payload)
                else:
                    cb(payload)
            except Exception:
                logger.exception(
                    "EventBus callback for %r raised while handling %r",
                    cb,
                    event_type,
                )

    @staticmethod
    def _matches(pattern: str, event_type: str) -> bool:
        if pattern == event_type:
            return True
        if pattern.endswith(".*"):
            prefix = pattern[:-2]
            return event_type == prefix or event_type.startswith(prefix + ".")
        return False
