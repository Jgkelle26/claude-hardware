# Claude Hardware — "Clod" (Claude On Desk)

A physical desk companion that serves as a voice interface to Claude Code. A Raspberry Pi Zero 2W-powered bot with an animated procedural eye rendered on a 64×64 RGB LED matrix, USB mic + USB sound card audio path, and USB connection to the user's Mac for executing Claude Code commands.

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
│   │   ├── matrix_renderer.py   # Procedural eye on 64x64 RGB matrix
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

- **Hardware**: Raspberry Pi Zero 2W, 64×64 RGB LED matrix (HUB75) via WatangTech adapter, USB mini mic, Sabrent USB sound card, PAM8403 amp, 4Ω 3W speaker, SG90 servo (PWM, Phase 3)
- **Language**: Python 3.11+ with asyncio
- **Key libraries**: `vosk`, `sounddevice`, `piper-tts`, `asyncssh`, `webrtcvad`, `rpi-rgb-led-matrix` (Henner Zeller), `Pillow`, `pigpio`
- **Communication**: USB gadget mode (RNDIS/ECM Ethernet) → SSH to Mac
- **Claude integration**: `claude -p --output-format stream-json` via SSH subprocess
- **Matrix config**: library flag `--led-hardware-mapping=regular` for the WatangTech HUB75 adapter (not `adafruit-hat`)
- **Audio routing**: USB mic → PyAudio/sounddevice → Vosk; Piper → `aplay` → Sabrent USB sound card → PAM8403 → speaker

## Conventions

- All inter-module communication goes through the event bus — modules never import each other directly
- Event names use dot notation: `audio.vad_start`, `claude.stream_chunk`, `face.set_state`
- Matrix rendering targets 20 FPS (50ms per frame) using Pillow → `rpi-rgb-led-matrix`
- Eye animation uses parameter interpolation (lerp), not pre-baked sprite frames
- Iris color and pupil size are part of the parameter set — emotional state drives both shape AND color
- Matrix brightness capped at 30% in config for desk use (panels are painfully bright at full)
- Configuration lives in `config.yaml`, not hardcoded
- HUB75 adapter consumes most GPIO pins — use BCM 27 for push-to-talk button; other GPIO usage must be verified against HUB75 pin allocation before wiring
- Servo power (Phase 3) comes from a separate rail, never from Pi's 5V GPIO
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

- **Phase 1**: Voice pipeline + 64×64 matrix face running together (button → STT → Claude → TTS + animated eye)
- **Phase 2**: Enclosure (deferred — breadboard layout for Phase 1)
- **Phase 3**: Servo movement (single-axis nod)
- **Phase 4**: Wake word, idle behaviors, polish

## GitHub Issues

Issues are labeled by phase (`phase-1` through `phase-4`), type (`hardware`, `software`, `design`, `docs`), and priority (`P0-critical`, `P1-important`, `P2-nice-to-have`).
