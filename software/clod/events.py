"""Event type constants and state enums for Clod."""

from enum import Enum

# Audio events
AUDIO_VAD_START = "audio.vad_start"
AUDIO_VAD_END = "audio.vad_end"
AUDIO_CHUNK = "audio.chunk"
AUDIO_AMPLITUDE = "audio.amplitude"

# Speech-to-text events
STT_PARTIAL = "stt.partial"
STT_FINAL = "stt.final"

# Claude bridge events
CLAUDE_REQUEST = "claude.request"
CLAUDE_STREAM_CHUNK = "claude.stream_chunk"
CLAUDE_COMPLETE = "claude.complete"
CLAUDE_ERROR = "claude.error"

# Text-to-speech events
TTS_START = "tts.start"
TTS_END = "tts.end"

# Face / renderer events
FACE_SET_STATE = "face.set_state"

# Servo events
SERVO_GESTURE = "servo.gesture"

# Input events
WAKE_DETECTED = "wake.detected"
BUTTON_PRESSED = "button.pressed"


class FaceState(Enum):
    """Visual face states rendered on the matrix."""

    IDLE = "idle"
    LISTENING = "listening"
    THINKING = "thinking"
    SPEAKING = "speaking"
    ERROR = "error"
    HAPPY = "happy"
    SLEEPING = "sleeping"


class SystemState(Enum):
    """Top-level application states."""

    SLEEPING = "sleeping"
    IDLE = "idle"
    LISTENING = "listening"
    THINKING = "thinking"
    SPEAKING = "speaking"
    ERROR = "error"
