from __future__ import annotations

import asyncio
import logging
import sys

from mac.audio import AudioRecorder
from mac.claude_runner import ClaudeRunner
from mac.pi_client import PiClient
from mac.stt import SpeechToText
from mac.tts import TextToSpeech

logger = logging.getLogger(__name__)


class ClodOrchestrator:
    """Mac-side voice pipeline: mic -> STT -> Claude Code -> TTS -> speaker.

    Sends face state events to the Pi over a socket connection.
    """

    def __init__(self, pi_host: str = "clod.local", pi_port: int = 9999) -> None:
        self._pi = PiClient(host=pi_host, port=pi_port)
        self._recorder = AudioRecorder()
        self._stt = SpeechToText()
        self._claude = ClaudeRunner()
        self._tts = TextToSpeech()

    async def _set_state(self, state: str) -> None:
        """Update the Pi display and print the state to the terminal."""
        print(f"[{state}]")
        await self._pi.send_state(state)

    async def _handle_error(self, context: str, exc: Exception) -> None:
        """Handle an error: log it, notify the Pi, wait, then return to idle."""
        logger.error("%s: %s", context, exc)
        print(f"  Error ({context}): {exc}")
        await self._set_state("error")
        await asyncio.sleep(3)
        await self._set_state("idle")

    async def _wait_for_enter(self) -> None:
        """Wait for the user to press Enter (non-blocking via executor)."""
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, sys.stdin.readline)

    async def run(self) -> None:
        """Main loop: wait for keypress, process voice, respond."""
        # Try connecting to the Pi (non-fatal if it fails)
        await self._pi.connect()
        await self._set_state("idle")

        try:
            while True:
                # Step 1: Wait for Enter keypress (push-to-talk)
                print("Press Enter to speak...")
                await self._wait_for_enter()

                # Step 2: Listen
                await self._set_state("listening")
                try:
                    audio_data = await self._recorder.record_until_silence()
                except Exception as exc:
                    await self._handle_error("Audio recording failed", exc)
                    continue

                if not audio_data:
                    print("  No audio captured.")
                    await self._set_state("idle")
                    continue

                # Step 3: Transcribe (STT)
                await self._set_state("thinking")
                try:
                    transcript = self._stt.transcribe(audio_data)
                except Exception as exc:
                    await self._handle_error("STT failed", exc)
                    continue

                if not transcript:
                    print("  No speech detected.")
                    await self._set_state("idle")
                    continue

                print(f"  You said: {transcript}")

                # Step 4: Send to Claude
                try:
                    response = await self._claude.run(transcript)
                except Exception as exc:
                    await self._handle_error("Claude failed", exc)
                    continue

                print(f"  Claude: {response}")

                # Step 5: Speak the response
                await self._set_state("speaking")
                try:
                    await self._tts.speak(response)
                except Exception as exc:
                    await self._handle_error("TTS failed", exc)
                    continue

                # Step 6: Back to idle
                await self._set_state("idle")

        except KeyboardInterrupt:
            print("\nShutting down...")
        finally:
            await self._set_state("idle")
            await self._pi.disconnect()
