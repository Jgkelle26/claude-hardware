# Claude Hardware — "Clod" (Claude On Desk)

A physical desk companion that serves as a voice interface to Claude Code. A Raspberry Pi Zero 2W-powered bot with an animated procedural eye on a 128x64 OLED, speaker/mic for voice I/O, and USB connection to the user's Mac for executing Claude Code commands.

## Project Structure

```
claude-hardware/
├── CLAUDE.md              # This file — project conventions
├── README.md              # Project overview and build guide
├── hardware/
│   ├── bom.md             # Bill of materials with links
│   ├── wiring.md          # GPIO pin assignments and wiring diagrams
│   └── enclosure/         # 3D printable STL files and OpenSCAD sources
├── software/
│   ├── clod/              # Main Python package
│   │   ├── __init__.py
│   │   ├── main.py        # Entry point, wires event bus
│   │   ├── event_bus.py   # Async pub/sub system
│   │   ├── audio_capture.py   # ALSA + webrtcvad
│   │   ├── stt_engine.py     # Vosk speech-to-text
│   │   ├── claude_bridge.py  # asyncssh → Mac → claude -p
│   │   ├── tts_engine.py     # piper-tts subprocess
│   │   ├── display_renderer.py  # Procedural eye on SSD1306
│   │   ├── servo_controller.py  # SG90 gesture presets
│   │   ├── state_machine.py     # IDLE→LISTENING→THINKING→SPEAKING
│   │   ├── wake_word.py         # "Hey Claude" detection
│   │   └── config.py           # YAML config loader
│   ├── config.yaml        # Default configuration
│   ├── assets/
│   │   └── sounds/        # Pre-generated WAV sound effects
│   ├── tests/             # pytest tests
│   └── requirements.txt   # Python dependencies
├── setup/
│   ├── setup.sh           # Automated Pi configuration script
│   ├── install_models.sh  # Download Vosk + Piper models
│   └── ssh_setup.sh       # Generate and install SSH keys
└── docs/
    └── architecture.md    # Detailed architecture documentation
```

## Tech Stack

- **Hardware**: Raspberry Pi Zero 2W, SSD1306 OLED (I2C), INMP441 mic (I2S), MAX98357A amp (I2S), SG90 servo (PWM)
- **Language**: Python 3.11+ with asyncio
- **Key libraries**: `vosk`, `sounddevice`, `piper-tts`, `asyncssh`, `webrtcvad`, `adafruit-circuitpython-ssd1306`, `Pillow`, `pigpio`
- **Communication**: USB gadget mode (RNDIS/ECM Ethernet) → SSH to Mac
- **Claude integration**: `claude -p --output-format stream-json` via SSH subprocess

## Conventions

- All inter-module communication goes through the event bus — modules never import each other directly
- Event names use dot notation: `audio.vad_start`, `claude.stream_chunk`, `face.set_state`
- Display rendering targets 20 FPS (50ms per frame) using Pillow → SSD1306
- Eye animation uses parameter interpolation (lerp), not pre-baked sprite frames
- Configuration lives in `config.yaml`, not hardcoded
- Servo power comes from a separate rail, never from Pi's 5V GPIO
- All audio assets are pre-generated WAVs, not synthesized at runtime

## Development

```bash
# On your Mac (development)
cd software && pip install -r requirements.txt
python -m clod.main --mock-hardware   # Test without Pi hardware

# On the Pi
ssh pi@192.168.7.2
cd /home/pi/claude-hardware/software
python -m clod.main

# Run tests
pytest software/tests/
```

## Build Phases

- **Phase 1**: Voice pipeline (mic → STT → Claude via SSH → TTS → speaker)
- **Phase 2**: Display + animated eye character
- **Phase 3**: Servo movement (single-axis nod)
- **Phase 4**: Wake word, idle behaviors, polish

## GitHub Issues

Issues are labeled by phase (`phase-1` through `phase-4`), type (`hardware`, `software`, `design`, `docs`), and priority (`P0-critical`, `P1-important`, `P2-nice-to-have`).
