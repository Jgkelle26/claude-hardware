from __future__ import annotations

import asyncio
import collections
import logging
import sys
import threading
from typing import TYPE_CHECKING, Deque

if TYPE_CHECKING:
    import numpy as np
    import sounddevice as sd
    import webrtcvad

logger = logging.getLogger(__name__)

# 30ms frame at 16kHz = 480 samples
FRAME_SAMPLES = 480
FRAME_BYTES = FRAME_SAMPLES * 2  # 16-bit mono


class AudioRecorder:
    """Records from the default mic with manual stop control."""

    def __init__(self, sample_rate: int = 16000) -> None:
        self._sample_rate = sample_rate

    async def record_until_stopped(self, max_duration: float = 60.0) -> bytes:
        """Record audio until the user presses Enter to stop.

        Records everything from the moment this is called until Enter is pressed.
        Returns raw PCM audio bytes (16-bit, 16kHz, mono).
        """
        loop = asyncio.get_running_loop()

        # Use a threading event to signal stop from the Enter key listener
        stop_event = threading.Event()

        def _wait_for_enter() -> None:
            sys.stdin.readline()
            stop_event.set()

        # Start listening for Enter in a background thread
        enter_thread = threading.Thread(target=_wait_for_enter, daemon=True)
        enter_thread.start()

        # Record in executor (blocking)
        audio = await loop.run_in_executor(
            None, self._record_until_event, stop_event, max_duration
        )
        return audio

    def _record_until_event(self, stop_event: threading.Event, max_duration: float) -> bytes:
        """Record audio until stop_event is set or max_duration reached."""
        import sounddevice as sd

        frame_duration_s = FRAME_SAMPLES / self._sample_rate
        max_frames = int(max_duration / frame_duration_s)

        recorded_frames: list[bytes] = []

        with sd.InputStream(
            samplerate=self._sample_rate,
            channels=1,
            dtype="int16",
            blocksize=FRAME_SAMPLES,
        ) as stream:
            while not stop_event.is_set():
                data, overflowed = stream.read(FRAME_SAMPLES)
                if overflowed:
                    logger.debug("Audio buffer overflow")

                frame_bytes = data.tobytes()
                if len(frame_bytes) == FRAME_BYTES:
                    recorded_frames.append(frame_bytes)

                if len(recorded_frames) >= max_frames:
                    logger.debug("Max recording duration reached")
                    break

        logger.debug("Recorded %d frames", len(recorded_frames))
        return b"".join(recorded_frames)

    async def record_until_silence(self, silence_duration: float = 1.0, max_duration: float = 30.0) -> bytes:
        """Legacy: record with VAD-based auto-stop. Kept for compatibility."""
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self._record_vad_sync, silence_duration, max_duration)

    def _record_vad_sync(self, silence_duration: float, max_duration: float) -> bytes:
        """Blocking recording with VAD-based silence detection."""
        import sounddevice as sd
        import webrtcvad

        vad = webrtcvad.Vad(2)
        frame_duration_s = FRAME_SAMPLES / self._sample_rate
        silence_frame_count = int(silence_duration / frame_duration_s)
        max_frames = int(max_duration / frame_duration_s)

        recorded_frames: list[bytes] = []
        speech_started = False
        silent_frames_consecutive = 0

        with sd.InputStream(
            samplerate=self._sample_rate,
            channels=1,
            dtype="int16",
            blocksize=FRAME_SAMPLES,
        ) as stream:
            while True:
                data, overflowed = stream.read(FRAME_SAMPLES)
                frame_bytes = data.tobytes()
                if len(frame_bytes) != FRAME_BYTES:
                    continue

                is_speech = vad.is_speech(frame_bytes, self._sample_rate)

                if not speech_started:
                    if is_speech:
                        speech_started = True
                        recorded_frames.append(frame_bytes)
                        silent_frames_consecutive = 0
                    continue

                recorded_frames.append(frame_bytes)
                if is_speech:
                    silent_frames_consecutive = 0
                else:
                    silent_frames_consecutive += 1

                if silent_frames_consecutive >= silence_frame_count:
                    break
                if len(recorded_frames) >= max_frames:
                    break

        return b"".join(recorded_frames)
