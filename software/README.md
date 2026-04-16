# Clod Software

Python application for the Clod desk robot. Organized as a single package (`clod/`) using an asyncio event bus pattern.

## Quick Start: Watch the Eye Animate on Your Mac

Before the matrix hardware arrives, you can develop and preview the animated eye on your Mac using the mock backend.

### Prerequisites (macOS)

The demo uses `tkinter` for the preview window. You need a Python interpreter with a working Tcl/Tk 9.0+. On recent macOS (Darwin 26+), the system Python 3.9 and Apple's `/usr/bin/python3` ship with a broken Tcl/Tk that won't launch. Use homebrew Python 3.13 with python-tk:

```bash
brew install python@3.13 python-tk@3.13 tcl-tk
```

Verify tkinter works:
```bash
/opt/homebrew/bin/python3.13 -c "import tkinter; tkinter.Tk().destroy(); print('ok')"
```

### Run the Demo

```bash
cd software/

# Create a virtual environment with homebrew Python 3.13
/opt/homebrew/bin/python3.13 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Run the demo
python -m clod.matrix_demo
```

A window titled "Clod - Mock Matrix Display" will open showing a 512×512 preview (the 64×64 matrix scaled 8x). The eye cycles through all 7 emotion states:
**IDLE → LISTENING → THINKING → SPEAKING → HAPPY → ERROR → SLEEPING → IDLE** (4 seconds per state).

Press `Ctrl+C` in the terminal or close the window to exit.

## Architecture

```
clod/
├── event_bus.py          # Async pub/sub — the backbone
├── events.py             # Event type constants + FaceState/SystemState enums
├── state_machine.py      # Application state orchestrator
├── config.py             # YAML config loader
├── matrix_renderer.py    # Procedural eye renderer (20 FPS, lerp-based)
├── matrix_backends.py    # DisplayBackend ABC + MockMatrixBackend (tkinter) + RealMatrixBackend (Pi)
├── matrix_demo.py        # Standalone: python -m clod.matrix_demo
├── audio_capture.py      # (skeleton) USB mic → PCM chunks + VAD
├── stt_engine.py         # (skeleton) Vosk streaming transcription
├── claude_bridge.py      # (skeleton) SSH to Mac, runs `claude -p`
├── tts_engine.py         # (skeleton) Piper TTS → speaker
├── wake_word.py          # (skeleton, Phase 4) "Hey Claude" detection
├── servo_controller.py   # (skeleton, Phase 3) SG90 gesture presets
└── main.py               # Entry point, wires everything via event bus
```

## Development Workflow

### Running tests
```bash
pytest tests/
```

### Swapping backends on the Pi
When the RGB matrix hardware is connected, `main.py` will use `RealMatrixBackend` instead of `MockMatrixBackend`. The renderer code is identical.

```python
# On Mac (development):
from clod.matrix_backends import MockMatrixBackend
backend = MockMatrixBackend()

# On Pi (production):
from clod.matrix_backends import RealMatrixBackend
backend = RealMatrixBackend(rows=64, cols=64, brightness=30, hardware_mapping="regular")
```

## Pi-Only Dependencies

Some packages only install on the Raspberry Pi (they need ARM-specific builds or hardware):

```bash
# On the Pi, after setup:
pip install -r requirements-pi.txt  # vosk
# Plus manual installs:
#   - piper-tts (binary download from https://github.com/rhasspy/piper/releases)
#   - rpi-rgb-led-matrix (compile from https://github.com/hzeller/rpi-rgb-led-matrix)
```

## Event Bus Contract

All modules communicate via `EventBus`. No direct imports between feature modules.

```python
# Subscribe (sync or async callback)
bus.on("audio.vad_start", on_speech_begins)

# Emit
await bus.emit("claude.stream_chunk", "Hello")

# Wildcards
bus.on("claude.*", on_any_claude_event)
```

See `clod/events.py` for the full list of event types.
