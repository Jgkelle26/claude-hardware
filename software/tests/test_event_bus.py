"""Tests for clod.event_bus.EventBus."""

from __future__ import annotations

import pytest

from clod.event_bus import EventBus


@pytest.mark.asyncio
async def test_sync_subscribe_and_emit() -> None:
    bus = EventBus()
    received: list[object] = []

    def cb(payload: object) -> None:
        received.append(payload)

    bus.on("foo.bar", cb)
    await bus.emit("foo.bar", "hello")

    assert received == ["hello"]


@pytest.mark.asyncio
async def test_async_subscribe_and_emit() -> None:
    bus = EventBus()
    received: list[object] = []

    async def cb(payload: object) -> None:
        received.append(payload)

    bus.on("foo.bar", cb)
    await bus.emit("foo.bar", 42)

    assert received == [42]


@pytest.mark.asyncio
async def test_multiple_subscribers_same_event() -> None:
    bus = EventBus()
    a: list[object] = []
    b: list[object] = []

    bus.on("x", lambda p: a.append(p))
    bus.on("x", lambda p: b.append(p))
    await bus.emit("x", 1)

    assert a == [1]
    assert b == [1]


@pytest.mark.asyncio
async def test_wildcard_subscription() -> None:
    bus = EventBus()
    received: list[tuple[str, object]] = []

    def cb(payload: object) -> None:
        received.append(("audio.*", payload))

    bus.on("audio.*", cb)
    await bus.emit("audio.chunk", "c")
    await bus.emit("audio.vad_start", "v")
    await bus.emit("other.event", "o")

    assert received == [("audio.*", "c"), ("audio.*", "v")]


@pytest.mark.asyncio
async def test_emit_with_no_subscribers_does_not_crash() -> None:
    bus = EventBus()
    # Should not raise.
    await bus.emit("nothing.here", {"k": "v"})


@pytest.mark.asyncio
async def test_exception_does_not_break_other_callbacks() -> None:
    bus = EventBus()
    results: list[str] = []

    def bad(_payload: object) -> None:
        raise RuntimeError("boom")

    def good(_payload: object) -> None:
        results.append("good")

    async def also_good(_payload: object) -> None:
        results.append("also_good")

    bus.on("e", bad)
    bus.on("e", good)
    bus.on("e", also_good)

    await bus.emit("e", None)

    assert "good" in results
    assert "also_good" in results
