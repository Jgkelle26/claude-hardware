from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
from typing import AsyncIterator

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = (
    "You are Clod, a voice assistant on a desk robot. "
    "Respond in 1-3 short spoken sentences. No markdown, no bullet points, "
    "no code blocks, no lists. Be conversational and concise. "
    "If asked for code or detailed info, give a brief spoken summary only."
)


def _extract_text(obj: dict) -> list[str]:
    """Pull assistant text out of a stream-json event. Tolerant of schema drift."""
    if not isinstance(obj, dict):
        return []
    out: list[str] = []
    # Final result event has full text in `result`.
    if obj.get("type") == "result" and isinstance(obj.get("result"), str):
        # Only emit result text if no prior assistant chunks emitted it. Caller
        # de-dupes by accumulating; we skip result here since assistant events
        # already carry the text.
        return []
    # Assistant events: message.content[*].text
    msg = obj.get("message")
    if isinstance(msg, dict):
        content = msg.get("content")
        if isinstance(content, list):
            for item in content:
                if isinstance(item, dict) and item.get("type") == "text":
                    text = item.get("text")
                    if isinstance(text, str):
                        out.append(text)
    # Partial-message events (when --include-partial-messages is set):
    # event.delta.text
    delta = obj.get("delta")
    if isinstance(delta, dict):
        text = delta.get("text")
        if isinstance(text, str):
            out.append(text)
    return out


class ClaudeRunner:
    """Executes Claude Code CLI with conversation history."""

    def __init__(self, history_file: str | None = None, max_history: int = 10) -> None:
        self._history_file = history_file
        self._max_history = max_history
        self._history: list[dict[str, str]] = []
        if history_file:
            self._load_history()

    def _load_history(self) -> None:
        """Load conversation history from JSON file if it exists."""
        if not self._history_file:
            return
        path = Path(self._history_file)
        if path.exists():
            try:
                with open(path) as f:
                    data = json.load(f)
                if isinstance(data, list):
                    self._history = data[-self._max_history:]
                    logger.info("Loaded %d history entries from %s", len(self._history), path)
            except Exception:
                logger.warning("Failed to load history from %s", path, exc_info=True)

    def _save_history(self) -> None:
        """Save conversation history to JSON file."""
        if not self._history_file:
            return
        path = Path(self._history_file)
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            with open(path, "w") as f:
                json.dump(self._history, f, indent=2)
            logger.debug("Saved %d history entries to %s", len(self._history), path)
        except Exception:
            logger.warning("Failed to save history to %s", path, exc_info=True)

    def _build_prompt(self, user_message: str) -> str:
        """Build a prompt that includes conversation history."""
        parts: list[str] = [SYSTEM_PROMPT, ""]

        if self._history:
            parts.append("Here is our conversation so far:\n")
            for entry in self._history:
                parts.append(f"User: {entry['user']}")
                parts.append(f"Assistant: {entry['assistant']}\n")

        parts.append(f"User: {user_message}")

        if self._history:
            parts.append("\nRespond to the latest message, using the conversation history for context.")

        return "\n".join(parts)

    async def run(self, prompt: str, timeout: float = 60.0) -> str:
        """Run Claude Code with conversation context. Returns full response."""
        chunks: list[str] = []
        async for chunk in self.run_stream(prompt, timeout=timeout):
            chunks.append(chunk)
        response = "".join(chunks).strip()
        self._record(prompt, response)
        return response

    async def run_stream(
        self, prompt: str, timeout: float = 60.0
    ) -> AsyncIterator[str]:
        """Run Claude Code and yield text chunks as they arrive.

        Caller is responsible for accumulating the full response. History is
        NOT saved here — call _record() after consuming the stream.
        """
        full_prompt = self._build_prompt(prompt)
        logger.debug("Running Claude (stream) with prompt (%d chars, %d history)",
                     len(full_prompt), len(self._history))

        proc = await asyncio.create_subprocess_exec(
            "claude",
            "-p",
            "--output-format",
            "stream-json",
            "--verbose",
            "--dangerously-skip-permissions",
            full_prompt,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        async def read_lines() -> AsyncIterator[str]:
            assert proc.stdout is not None
            while True:
                line = await proc.stdout.readline()
                if not line:
                    return
                text = line.decode("utf-8", errors="replace").strip()
                if not text:
                    continue
                try:
                    obj = json.loads(text)
                except json.JSONDecodeError:
                    logger.debug("Skipping non-JSON line: %r", text[:80])
                    continue
                for piece in _extract_text(obj):
                    if piece:
                        yield piece

        try:
            async with asyncio.timeout(timeout):
                async for piece in read_lines():
                    yield piece
                rc = await proc.wait()
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()
            raise RuntimeError(f"Claude timed out after {timeout}s")

        if rc != 0:
            stderr = await proc.stderr.read() if proc.stderr else b""
            err_msg = stderr.decode("utf-8", errors="replace").strip()
            raise RuntimeError(f"Claude exited with code {rc}: {err_msg}")

    def _record(self, prompt: str, response: str) -> None:
        self._history.append({"user": prompt, "assistant": response})
        if len(self._history) > self._max_history:
            self._history = self._history[-self._max_history:]
        self._save_history()

    def clear_history(self) -> None:
        """Reset conversation history and delete the history file."""
        self._history.clear()
        if self._history_file:
            path = Path(self._history_file)
            if path.exists():
                path.unlink()
