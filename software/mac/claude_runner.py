from __future__ import annotations

import asyncio
import logging

logger = logging.getLogger(__name__)


class ClaudeRunner:
    """Executes Claude Code CLI and captures the response."""

    async def run(self, prompt: str, timeout: float = 60.0) -> str:
        """Run ``claude -p --output-format text "<prompt>"`` and return the response text.

        Args:
            prompt: The text prompt to send to Claude.
            timeout: Maximum seconds to wait for a response.

        Returns:
            The text output from Claude.

        Raises:
            RuntimeError: If the command fails or times out.
        """
        logger.debug("Running Claude with prompt: %s", prompt[:80])

        proc = await asyncio.create_subprocess_exec(
            "claude",
            "-p",
            "--output-format",
            "text",
            prompt,
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
        return response
