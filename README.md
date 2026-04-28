# Clod (Claude On Desk)

A desk companion that lets you talk to Claude Code with your voice. Speak a command, and a 64×64 RGB LED matrix reacts in real-time — listening, thinking, speaking — with swappable animated themes.

## Architecture

```
Mac (handles everything):
  Mic/AirPods → Speech-to-Text (Whisper) → Claude Code CLI → Text-to-Speech (say)
  Sends state events to Pi over WiFi ↓

Pi (display only):
  Receives state events → drives 64×64 RGB LED matrix with animated themes
```

Your Mac captures audio, transcribes it, runs Claude Code, speaks the response, and tells the Pi what state to display. The Pi is a pure display device — no audio hardware needed.

## Themes

4 swappable visual themes, each with 7 animated states (idle, listening, thinking, speaking, happy, error, sleeping):

- **Bear** — Radiohead modified bear logo with pixel-level color static effects
- **Particles** — 300 swarming single-pixel atoms with per-state color palettes
- **Character** — Dithered pixel portrait face emerging from probabilistic noise
- **Composition** — Geometric De Stijl zones with pixel-flicker bar animations

Switch themes by sending `theme:next` or `theme:Bear` from the Mac.

## Quick Start

### 1. Pi Setup

Flash Raspberry Pi OS Lite (64-bit) onto a MicroSD card with WiFi and SSH enabled. Boot the Pi, SSH in, then:

```bash
sudo apt update && sudo apt upgrade -y
sudo apt install -y python3-pip python3-venv git
git clone https://github.com/Jgkelle26/claude-hardware.git ~/claude-hardware
cd ~/claude-hardware/software
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

Install the RGB matrix library (takes 10-15 min on Pi Zero 2W):
```bash
sudo apt install -y python3-dev libjpeg62-turbo-dev zlib1g-dev libfreetype6-dev cmake
pip install pillow --no-binary pillow --force-reinstall
pip install git+https://github.com/hzeller/rpi-rgb-led-matrix
```

Run the display:
```bash
sudo /home/pi/claude-hardware/software/.venv/bin/python3 -m clod.pi_main --theme Bear
```

### 2. Mac Setup

```bash
cd ~/claude-hardware/software
python3 -m venv .venv && source .venv/bin/activate
pip install -r mac/requirements.txt
```

Run the orchestrator:
```bash
python -m mac
```

Press Enter to speak, Ctrl+C to quit. The Mac captures your voice, sends it to Claude Code, speaks the response, and updates the Pi's display in real-time.

## Shopping List (Display-Only Build)

| # | Component | Part | Est. Price |
|---|-----------|------|-----------|
| 1 | Board | Raspberry Pi Zero 2W with Pre-Soldered Header | $25 |
| 2 | Storage | 16GB MicroSD Card C10/A1 | $10 |
| 3 | Display | 64×64 RGB LED Matrix Panel, HUB75, P3 (3mm pitch) | $35 |
| 4 | Matrix Adapter | WatangTech RGB Matrix Adapter Board for Pi (HUB75) | $15 |
| 5 | Power Supply | 5V 4A DC Power Supply (5.5×2.1mm barrel jack) | $12 |
| | | **TOTAL** | **~$97** |

## Project Structure

```
claude-hardware/
├── software/
│   ├── mac/               # Mac-side orchestrator (audio, STT, Claude, TTS)
│   │   ├── orchestrator.py    # Main pipeline
│   │   ├── audio.py           # Mic capture with VAD
│   │   ├── stt.py             # Whisper speech-to-text
│   │   ├── claude_runner.py   # Claude Code CLI wrapper
│   │   ├── tts.py             # macOS say command
│   │   └── pi_client.py       # TCP client → Pi
│   ├── clod/              # Pi-side display driver
│   │   ├── pi_main.py        # Entry point
│   │   ├── pi_server.py      # TCP server for state events
│   │   ├── themes/            # Visual themes
│   │   ├── event_bus.py       # Async pub/sub
│   │   └── matrix_backends.py # Mock (Mac) + Real (Pi) backends
│   └── config.yaml
├── CLAUDE.md
└── README.md
```

---

<details>
<summary><strong>Alternative: Full Hardware Build (Pi handles audio)</strong></summary>

If you want all audio on the Pi instead of the Mac, you'll need a USB hub and additional parts:

| # | Component | Part | Est. Price |
|---|-----------|------|-----------|
| 6 | Microphone | USB Mini Microphone | $8 |
| 7 | Sound Card | Sabrent USB External Stereo Sound Adapter | $8 |
| 8 | Amplifier | DEVMO PAM8403 3W Stereo Amp | $7 |
| 9 | Speaker | Gikfun 4Ω 40mm 3W Speaker | $8 |
| 10 | USB Hub | Powered USB Hub | $8 |
| 11 | Button | 12mm Tactile Push Button | $6 |
| 12 | Wiring | Dupont Jumper Wires | $7 |

The Pi Zero 2W has one USB data port. A USB hub lets you connect both the mic and sound card. The Pi captures audio, runs Vosk for STT, SSHes to the Mac for Claude Code, and plays responses through Piper TTS + the PAM8403 amp + speaker.

This approach puts more load on the Pi's limited CPU and RAM but makes the build fully self-contained.

</details>
