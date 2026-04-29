"""Text-to-speech using Edge TTS (Microsoft neural voices), falling back to macOS say."""

from __future__ import annotations

import asyncio
import logging
import os
import re
import tempfile
from typing import AsyncIterator, Awaitable, Callable

logger = logging.getLogger(__name__)

_SENTENCE_BOUNDARY = re.compile(r"(?<=[.!?])\s+")


async def split_sentences(chunks: AsyncIterator[str]) -> AsyncIterator[str]:
    """Yield complete sentences from an async stream of text chunks."""
    buf = ""
    async for chunk in chunks:
        buf += chunk
        parts = _SENTENCE_BOUNDARY.split(buf)
        for part in parts[:-1]:
            stripped = part.strip()
            if stripped:
                yield stripped
        buf = parts[-1]
    tail = buf.strip()
    if tail:
        yield tail


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
        tmp_path = await self._synth_edge(text)
        try:
            await self._play(tmp_path)
        finally:
            self._unlink(tmp_path)

    async def _synth_edge(self, text: str) -> str:
        """Synthesize text to a temp mp3 file via Edge TTS. Returns path."""
        import edge_tts

        tmp = tempfile.NamedTemporaryFile(suffix=".mp3", delete=False)
        tmp_path = tmp.name
        tmp.close()
        try:
            communicate = edge_tts.Communicate(text, self._voice)
            await communicate.save(tmp_path)
        except Exception:
            self._unlink(tmp_path)
            raise
        return tmp_path

    async def _play(self, path: str) -> None:
        proc = await asyncio.create_subprocess_exec(
            "afplay", path,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        await proc.communicate()

    @staticmethod
    def _unlink(path: str) -> None:
        try:
            os.unlink(path)
        except OSError:
            pass

    async def speak_stream(
        self,
        sentences: AsyncIterator[str],
        on_sentence: Callable[[str], Awaitable[None]] | None = None,
    ) -> str:
        """Speak sentences as they arrive. Synth and playback overlap.

        Returns the full concatenated text that was actually spoken (raw, before
        any per-sentence transformation by ``on_sentence``).

        ``on_sentence`` is called once per sentence with the raw text *before*
        synthesis — used by callers to log what's being spoken in real time.
        If the caller wants per-sentence text transformation (e.g. rocky mode),
        they should transform sentences upstream before passing them in.
        """
        if self._voice is None:
            return await self._speak_stream_say(sentences, on_sentence)

        queue: asyncio.Queue[tuple[str, str] | None] = asyncio.Queue(maxsize=2)
        spoken: list[str] = []
        synth_failed: list[Exception] = []

        async def producer() -> None:
            try:
                async for sentence in sentences:
                    if not sentence:
                        continue
                    spoken.append(sentence)
                    if on_sentence is not None:
                        await on_sentence(sentence)
                    try:
                        path = await self._synth_edge(sentence)
                    except Exception as exc:
                        synth_failed.append(exc)
                        await queue.put(("say", sentence))
                        continue
                    await queue.put(("file", path))
            finally:
                await queue.put(None)

        async def consumer() -> None:
            while True:
                item = await queue.get()
                if item is None:
                    return
                kind, payload = item
                if kind == "file":
                    try:
                        await self._play(payload)
                    finally:
                        self._unlink(payload)
                else:
                    await self._speak_say(payload)

        await asyncio.gather(producer(), consumer())

        if synth_failed:
            logger.warning("Edge TTS failed on %d sentence(s); used say fallback",
                           len(synth_failed))
        return " ".join(spoken)

    async def _speak_stream_say(
        self,
        sentences: AsyncIterator[str],
        on_sentence: Callable[[str], Awaitable[None]] | None,
    ) -> str:
        spoken: list[str] = []
        async for sentence in sentences:
            if not sentence:
                continue
            spoken.append(sentence)
            if on_sentence is not None:
                await on_sentence(sentence)
            await self._speak_say(sentence)
        return " ".join(spoken)

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
