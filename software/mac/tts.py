"""Text-to-speech using Edge TTS (Microsoft neural voices), falling back to macOS say."""

from __future__ import annotations

import asyncio
import logging
import os
import tempfile

logger = logging.getLogger(__name__)


class TextToSpeech:
    """Speak text using Edge TTS (free Microsoft neural voices).

    Falls back to macOS ``say`` command if Edge TTS fails.
    """

    def __init__(self, voice: str | None = None, fallback_voice: str = "Good News") -> None:
        """
        Args:
            voice: Edge TTS voice name, or None to skip Edge TTS and use macOS say
                directly (required for novelty voices like Bubbles that have no
                Edge TTS equivalent). Edge options if set:
                - en-US-AnaNeural (child, high-pitched, silly)
                - en-AU-WilliamNeural (Australian male, goofy lilt)
                - en-GB-RyanNeural (British male, mock-posh)
            fallback_voice: macOS voice. Novelty options: Bubbles, Albert, Bahh,
                Bells, Boing, Cellos, Deranged, Hysterical, Trinoids, Whisper,
                Zarvox, "Good News", "Bad News".
        """
        self._voice = voice
        self._fallback_voice = fallback_voice

    async def speak(self, text: str) -> None:
        """Speak text. Tries Edge TTS first, falls back to macOS say."""
        if not text:
            logger.warning("Empty text passed to TTS, skipping")
            return

        if self._voice is None:
            await self._speak_say(text)
            return

        try:
            await self._speak_edge(text)
        except Exception as exc:
            logger.warning("Edge TTS failed (%s), falling back to macOS say", exc)
            await self._speak_say(text)

    async def _speak_edge(self, text: str) -> None:
        """Speak using Edge TTS — generates audio file then plays it."""
        import edge_tts

        tmp = tempfile.NamedTemporaryFile(suffix=".mp3", delete=False)
        tmp_path = tmp.name
        tmp.close()

        try:
            communicate = edge_tts.Communicate(text, self._voice)
            await communicate.save(tmp_path)

            # Play the audio file
            proc = await asyncio.create_subprocess_exec(
                "afplay", tmp_path,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
            await proc.communicate()
        finally:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass

    async def _speak_say(self, text: str) -> None:
        """Fallback: speak using macOS say command."""
        logger.debug("Speaking with macOS say voice '%s'", self._fallback_voice)
        proc = await asyncio.create_subprocess_exec(
            "say", "-v", self._fallback_voice, text,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await proc.communicate()
        if proc.returncode != 0:
            err_msg = stderr.decode("utf-8", errors="replace").strip()
            logger.error("say command failed (exit %d): %s", proc.returncode, err_msg)
