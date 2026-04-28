"""Configuration loader for the Clod Mac orchestrator."""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from pathlib import Path

import yaml

logger = logging.getLogger(__name__)

CONFIG_PATH = Path.home() / ".clod" / "config.yaml"


@dataclass
class PiConfig:
    host: str = "clod.local"
    port: int = 9999


@dataclass
class TTSConfig:
    voice: str = "en-GB-RyanNeural"
    fallback_voice: str = "Good News"


@dataclass
class STTConfig:
    model: str = "base"


@dataclass
class ClodConfig:
    pi: PiConfig = field(default_factory=PiConfig)
    tts: TTSConfig = field(default_factory=TTSConfig)
    stt: STTConfig = field(default_factory=STTConfig)
    speech_mode: str = "normal"
    default_theme: str = "Bear"
    history_file: str = str(Path.home() / ".clod" / "history.json")
    max_history: int = 10


def load_config(path: Path | None = None) -> ClodConfig:
    """Load config from YAML file. Creates default if missing."""
    config_path = path or CONFIG_PATH

    if not config_path.exists():
        # Create default config
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config = ClodConfig()
        save_config(config, config_path)
        logger.info("Created default config at %s", config_path)
        return config

    with open(config_path) as f:
        data = yaml.safe_load(f) or {}

    # Parse nested configs
    pi = PiConfig(**data.get("pi", {}))
    tts = TTSConfig(**data.get("tts", {}))
    stt = STTConfig(**data.get("stt", {}))

    return ClodConfig(
        pi=pi,
        tts=tts,
        stt=stt,
        speech_mode=data.get("speech_mode", "normal"),
        default_theme=data.get("default_theme", "Bear"),
        history_file=data.get("history_file", str(Path.home() / ".clod" / "history.json")),
        max_history=data.get("max_history", 10),
    )


def save_config(config: ClodConfig, path: Path | None = None) -> None:
    """Save config to YAML file."""
    config_path = path or CONFIG_PATH
    config_path.parent.mkdir(parents=True, exist_ok=True)

    data = {
        "pi": {"host": config.pi.host, "port": config.pi.port},
        "tts": {"voice": config.tts.voice, "fallback_voice": config.tts.fallback_voice},
        "stt": {"model": config.stt.model},
        "speech_mode": config.speech_mode,
        "default_theme": config.default_theme,
        "history_file": config.history_file,
        "max_history": config.max_history,
    }

    with open(config_path, "w") as f:
        yaml.dump(data, f, default_flow_style=False, sort_keys=False)
