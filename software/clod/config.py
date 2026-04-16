"""Config loader. Parses config.yaml into nested dataclasses."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import yaml


@dataclass
class MacSsh:
    host: str
    user: str
    key_path: str


@dataclass
class Vosk:
    model_path: str


@dataclass
class Piper:
    voice_model: str
    speaker_id: int


@dataclass
class Matrix:
    rows: int
    cols: int
    brightness: int
    hardware_mapping: str
    slowdown_gpio: int


@dataclass
class Audio:
    input_device: str
    output_device: str
    sample_rate: int
    vad_aggressiveness: int
    vad_silence_ms: int


@dataclass
class Gpio:
    button_pin: int
    servo_pin: Optional[int]


@dataclass
class Behavior:
    wake_word_enabled: bool
    idle_sleep_minutes: int
    personality_quirks: bool


@dataclass
class Config:
    mac_ssh: MacSsh
    vosk: Vosk
    piper: Piper
    matrix: Matrix
    audio: Audio
    gpio: Gpio
    behavior: Behavior


def load_config(path: str = "config.yaml") -> Config:
    """Load YAML config and return a populated Config dataclass."""
    with open(path, "r") as f:
        raw = yaml.safe_load(f)

    return Config(
        mac_ssh=MacSsh(**raw["mac_ssh"]),
        vosk=Vosk(**raw["vosk"]),
        piper=Piper(**raw["piper"]),
        matrix=Matrix(**raw["matrix"]),
        audio=Audio(**raw["audio"]),
        gpio=Gpio(**raw["gpio"]),
        behavior=Behavior(**raw["behavior"]),
    )
