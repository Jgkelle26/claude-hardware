from __future__ import annotations

import asyncio
import logging
import sys

from mac.audio import AudioRecorder
from mac.claude_runner import ClaudeRunner
from mac.pi_client import PiClient
from mac.rocky_transform import rocky_transform
from mac.stt import SpeechToText
from mac.tts import TextToSpeech, split_sentences

logger = logging.getLogger(__name__)

EDGE_VOICES = [
    ("en-GB-RyanNeural", "Ryan (British male)"),
    ("en-US-GuyNeural", "Guy (American male)"),
    ("en-US-AriaNeural", "Aria (American female)"),
    ("en-US-JennyNeural", "Jenny (American female)"),
    ("en-GB-SoniaNeural", "Sonia (British female)"),
    ("en-AU-WilliamNeural", "William (Australian male)"),
]

REPLAY_PHRASES = [
    "repeat that",
    "say that again",
    "what did you say",
    "say it again",
    "repeat",
]


def _normalize(text: str) -> str:
    cleaned = "".join(c for c in text.lower() if c.isalnum() or c.isspace())
    return " ".join(cleaned.split())


_NORMALIZED_REPLAY_PHRASES = {_normalize(p) for p in REPLAY_PHRASES}


class ClodOrchestrator:
    """Mac-side voice pipeline: mic -> STT -> Claude Code -> TTS -> speaker.

    Sends face state events to the Pi over a socket connection.
    Supports speech modes: 'normal' and 'rocky'.
    """

    def __init__(
        self,
        pi_host: str = "clod.local",
        pi_port: int = 9999,
        streaming_tts: bool = True,
    ) -> None:
        self._pi = PiClient(host=pi_host, port=pi_port)
        self._recorder = AudioRecorder()
        self._stt = SpeechToText()
        self._claude = ClaudeRunner()
        self._tts = TextToSpeech(voice="en-GB-RyanNeural")
        self._speech_mode: str = "normal"  # "normal" or "rocky"
        self._streaming_tts = streaming_tts
        # Determine initial voice index from current TTS voice
        self._voice_index: int = 0
        for i, (voice_id, _) in enumerate(EDGE_VOICES):
            if voice_id == self._tts._voice:
                self._voice_index = i
                break
        self._last_response: str | None = None

    async def _stream_and_speak(self, transcript: str) -> str:
        """Stream Claude's response, splitting on sentence boundaries and
        speaking each sentence as soon as it arrives. Returns the full raw
        Claude response (pre-speech-mode transform), and records it to history.
        """
        raw_chunks: list[str] = []
        speaking_started = False

        async def claude_chunks():
            async for chunk in self._claude.run_stream(transcript):
                raw_chunks.append(chunk)
                yield chunk

        async def transformed_sentences():
            async for sentence in split_sentences(claude_chunks()):
                yield self._apply_speech_mode(sentence)

        async def announce(sentence: str) -> None:
            nonlocal speaking_started
            if not speaking_started:
                await self._set_state("speaking")
                speaking_started = True
            if self._speech_mode != "normal":
                print(f"  Rocky:  {sentence}")
            else:
                print(f"  Claude: {sentence}")

        await self._tts.speak_stream(transformed_sentences(), on_sentence=announce)

        response = "".join(raw_chunks).strip()
        self._claude._record(transcript, response)
        return response

    async def _replay_last(self) -> None:
        if self._last_response is None:
            print("  Nothing to replay yet.")
            await self._set_state("idle")
            return
        print(f"  Replaying: {self._last_response}")
        await self._set_state("speaking")
        try:
            await self._tts.speak(self._apply_speech_mode(self._last_response))
        except Exception as exc:
            await self._handle_error("TTS failed", exc)
            return
        await self._set_state("idle")

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

    async def _play_sound(self, sound: str) -> None:
        """Play a macOS system sound. Non-blocking."""
        proc = await asyncio.create_subprocess_exec(
            "afplay", f"/System/Library/Sounds/{sound}.aiff",
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        await proc.communicate()

    async def _wait_for_input(self) -> str:
        """Wait for the user to press Enter or type a command.

        Returns the input string (empty string = speak, 'rocky' = toggle mode, etc.)
        """
        loop = asyncio.get_running_loop()
        line = await loop.run_in_executor(None, sys.stdin.readline)
        return line.strip().lower()

    def _apply_speech_mode(self, text: str) -> str:
        """Transform text based on current speech mode."""
        if self._speech_mode == "rocky":
            return rocky_transform(text)
        return text

    async def run(self) -> None:
        """Main loop: wait for keypress, process voice, respond."""
        await self._pi.connect()
        await self._set_state("idle")

        try:
            while True:
                mode_label = f" [{self._speech_mode} mode]" if self._speech_mode != "normal" else ""
                print(f"Enter=speak{mode_label} | 'theme' | 'voice' | 'rocky'/'normal' | 'clear' | 'replay'")
                user_input = await self._wait_for_input()

                # Handle commands
                if user_input == "rocky":
                    self._speech_mode = "rocky"
                    print("  Switched to Rocky mode! Good good good!")
                    continue
                elif user_input == "normal":
                    self._speech_mode = "normal"
                    print("  Switched to normal mode.")
                    continue
                elif user_input == "theme":
                    await self._pi.send_state("theme:next")
                    print("  Theme cycled.")
                    continue
                elif user_input.startswith("theme:"):
                    await self._pi.send_state(user_input)
                    print(f"  Sent: {user_input}")
                    continue
                elif user_input == "clear":
                    self._claude.clear_history()
                    print("  Conversation history cleared.")
                    continue
                elif user_input == "replay":
                    await self._replay_last()
                    continue
                elif user_input == "voice":
                    self._voice_index = (self._voice_index + 1) % len(EDGE_VOICES)
                    voice_id, voice_name = EDGE_VOICES[self._voice_index]
                    self._tts._voice = voice_id
                    print(f"  Voice: {voice_name}")
                    continue
                elif user_input.startswith("voice:"):
                    query = user_input[6:].strip().lower()
                    matched = None
                    for i, (voice_id, voice_name) in enumerate(EDGE_VOICES):
                        if query in voice_id.lower() or query in voice_name.lower():
                            matched = i
                            break
                    if matched is not None:
                        self._voice_index = matched
                        voice_id, voice_name = EDGE_VOICES[matched]
                        self._tts._voice = voice_id
                        print(f"  Voice: {voice_name}")
                    else:
                        names = ", ".join(n for _, n in EDGE_VOICES)
                        print(f"  Unknown voice. Available: {names}")
                    continue

                # Step 2: Listen
                await self._set_state("listening")
                await self._play_sound("Tink")
                print("  🎤 RECORDING — speak now. Press Enter when done.")
                try:
                    audio_data = await self._recorder.record_until_stopped()
                except Exception as exc:
                    await self._handle_error("Audio recording failed", exc)
                    continue

                print("  ⏹  Recording stopped.")
                await self._play_sound("Pop")

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

                # Check for voice commands before sending to Claude
                lower = transcript.lower().strip()
                if _normalize(transcript) in _NORMALIZED_REPLAY_PHRASES:
                    await self._replay_last()
                    continue
                if any(phrase in lower for phrase in [
                    "switch theme", "next theme", "change theme",
                    "switch the theme", "change the theme",
                ]):
                    await self._pi.send_state("theme:next")
                    print("  Theme cycled.")
                    await self._set_state("idle")
                    continue
                elif lower.startswith("theme "):
                    theme_name = transcript[6:].strip()
                    await self._pi.send_state(f"theme:{theme_name}")
                    print(f"  Theme: {theme_name}")
                    await self._set_state("idle")
                    continue

                # Step 4-6: Send to Claude and speak (streaming or batch)
                if self._streaming_tts:
                    try:
                        response = await self._stream_and_speak(transcript)
                    except Exception as exc:
                        await self._handle_error("Claude/TTS failed", exc)
                        continue
                else:
                    try:
                        response = await self._claude.run(transcript)
                    except Exception as exc:
                        await self._handle_error("Claude failed", exc)
                        continue
                    spoken_text = self._apply_speech_mode(response)
                    if self._speech_mode != "normal":
                        print(f"  Claude: {response}")
                        print(f"  Rocky:  {spoken_text}")
                    else:
                        print(f"  Claude: {response}")
                    await self._set_state("speaking")
                    try:
                        await self._tts.speak(spoken_text)
                    except Exception as exc:
                        await self._handle_error("TTS failed", exc)
                        continue

                self._last_response = response

                # Step 7: Back to idle
                await self._set_state("idle")

        except KeyboardInterrupt:
            print("\nShutting down...")
        finally:
            await self._set_state("idle")
            await self._pi.disconnect()
