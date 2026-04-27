from __future__ import annotations

import logging
import struct
import tempfile
import wave

logger = logging.getLogger(__name__)


class SpeechToText:
    """Transcribe audio using OpenAI Whisper (runs locally on Mac)."""

    def __init__(self, model: str = "base") -> None:
        self._model_name = model
        self._model = None  # lazy-loaded

    def _load_model(self) -> None:
        """Lazy-load the Whisper model on first use."""
        if self._model is not None:
            return
        import whisper

        logger.info("Loading Whisper model '%s' (first run may download it)...", self._model_name)
        self._model = whisper.load_model(self._model_name)
        logger.info("Whisper model loaded")

    def transcribe(self, audio_bytes: bytes, sample_rate: int = 16000) -> str:
        """Transcribe PCM audio bytes to text.

        Args:
            audio_bytes: Raw PCM audio (16-bit signed, mono).
            sample_rate: Sample rate of the audio (default 16kHz).

        Returns:
            The transcription string.
        """
        self._load_model()

        # Write PCM bytes to a temporary WAV file for Whisper
        tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
        try:
            with wave.open(tmp.name, "wb") as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)  # 16-bit
                wf.setframerate(sample_rate)
                wf.writeframes(audio_bytes)

            logger.debug("Transcribing %d bytes of audio from %s", len(audio_bytes), tmp.name)
            result = self._model.transcribe(tmp.name, fp16=False)
        finally:
            import os
            os.unlink(tmp.name)

        text: str = result["text"].strip()
        logger.debug("Transcription: %s", text)
        return text
