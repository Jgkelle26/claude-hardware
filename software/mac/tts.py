from __future__ import annotations

import asyncio
import logging

logger = logging.getLogger(__name__)


class TextToSpeech:
    """Speak text using macOS built-in say command."""

    async def speak(self, text: str, voice: str = "Samantha") -> None:
        """Speak the text aloud. Blocks until speech is complete.

        Args:
            text: The text to speak.
            voice: macOS voice name (default "Samantha").
        """
        if not text:
            logger.warning("Empty text passed to TTS, skipping")
            return

        logger.debug("Speaking with voice '%s': %s", voice, text[:80])

        proc = await asyncio.create_subprocess_exec(
            "say",
            "-v",
            voice,
            text,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.PIPE,
        )

        _, stderr = await proc.communicate()

        if proc.returncode != 0:
            err_msg = stderr.decode("utf-8", errors="replace").strip()
            logger.error("say command failed (exit %d): %s", proc.returncode, err_msg)
