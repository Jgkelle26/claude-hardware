from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = (
    "You are Clod, a voice assistant on a desk robot. "
    "Respond in 1-3 short spoken sentences. No markdown, no bullet points, "
    "no code blocks, no lists. Be conversational and concise. "
    "If asked for code or detailed info, give a brief spoken summary only."
)


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
        """Run Claude Code with conversation context.

        Maintains a rolling history of the last MAX_HISTORY exchanges
        so Claude has context from previous voice interactions.
        """
        full_prompt = self._build_prompt(prompt)
        logger.debug("Running Claude with prompt (%d chars, %d history entries)",
                      len(full_prompt), len(self._history))

        proc = await asyncio.create_subprocess_exec(
            "claude",
            "-p",
            "--output-format",
            "text",
            "--dangerously-skip-permissions",
            full_prompt,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        try:
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()
            raise RuntimeError(f"Claude timed out after {timeout}s")

        if proc.returncode != 0:
            err_msg = stderr.decode("utf-8", errors="replace").strip()
            raise RuntimeError(f"Claude exited with code {proc.returncode}: {err_msg}")

        response = stdout.decode("utf-8", errors="replace").strip()
        logger.debug("Claude response length: %d chars", len(response))

        # Save to history
        self._history.append({"user": prompt, "assistant": response})
        if len(self._history) > self._max_history:
            self._history = self._history[-self._max_history:]
        self._save_history()

        return response

    def clear_history(self) -> None:
        """Reset conversation history and delete the history file."""
        self._history.clear()
        if self._history_file:
            path = Path(self._history_file)
            if path.exists():
                path.unlink()
