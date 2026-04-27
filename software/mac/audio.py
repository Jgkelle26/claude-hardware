from __future__ import annotations

import asyncio
import collections
import logging
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
    """Records from the default mic until voice activity stops."""

    def __init__(self, sample_rate: int = 16000, vad_aggressiveness: int = 2) -> None:
        self._sample_rate = sample_rate
        self._vad_aggressiveness = vad_aggressiveness

    async def record_until_silence(self, silence_duration: float = 1.0, max_duration: float = 30.0) -> bytes:
        """Start recording, detect speech, stop after silence_duration of no speech.

        Returns raw PCM audio bytes (16-bit, 16kHz, mono).
        """
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self._record_sync, silence_duration, max_duration)

    def _record_sync(self, silence_duration: float, max_duration: float = 30.0) -> bytes:
        """Blocking recording with VAD-based silence detection."""
        import sounddevice as sd
        import webrtcvad

        vad = webrtcvad.Vad(self._vad_aggressiveness)

        frame_duration_s = FRAME_SAMPLES / self._sample_rate  # 0.03s
        silence_frame_count = int(silence_duration / frame_duration_s)

        recorded_frames: list[bytes] = []
        ring_buffer: Deque[bool] = collections.deque(maxlen=silence_frame_count)
        speech_started = False
        silent_frames_consecutive = 0
        max_frames = int(max_duration / frame_duration_s)

        logger.debug("Opening audio stream at %d Hz", self._sample_rate)

        with sd.InputStream(
            samplerate=self._sample_rate,
            channels=1,
            dtype="int16",
            blocksize=FRAME_SAMPLES,
        ) as stream:
            logger.debug("Recording started, waiting for speech...")

            while True:
                data, overflowed = stream.read(FRAME_SAMPLES)
                if overflowed:
                    logger.debug("Audio buffer overflow")

                # Convert numpy array to raw bytes
                frame_bytes = data.tobytes()

                # Ensure the frame is exactly the right size for VAD
                if len(frame_bytes) != FRAME_BYTES:
                    continue

                is_speech = vad.is_speech(frame_bytes, self._sample_rate)

                if not speech_started:
                    if is_speech:
                        speech_started = True
                        logger.debug("Speech detected, recording...")
                        recorded_frames.append(frame_bytes)
                        ring_buffer.clear()
                        silent_frames_consecutive = 0
                    # Discard frames before speech starts
                    continue

                # Speech has started -- record everything
                recorded_frames.append(frame_bytes)

                if is_speech:
                    silent_frames_consecutive = 0
                else:
                    silent_frames_consecutive += 1

                if silent_frames_consecutive >= silence_frame_count:
                    logger.debug(
                        "Silence detected after %d frames, stopping recording",
                        len(recorded_frames),
                    )
                    break

                if len(recorded_frames) >= max_frames:
                    logger.debug("Max recording duration reached")
                    break

        return b"".join(recorded_frames)
