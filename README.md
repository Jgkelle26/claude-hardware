# Clod (Claude On Desk)

A Raspberry Pi-powered desk companion that lets you talk to Claude Code with your voice. Press a button (or say "Hey Claude"), speak a command, and a little one-eyed robot thinks, answers, and nods along.

Built around a single procedural eye on a small OLED display inside a 3D-printed cylindrical enclosure. The Pi acts as a thin client — it captures your voice, transcribes it, sends it to your Mac over USB, and Claude Code does the real work. The response streams back, gets spoken aloud, and the eye reacts to every step.

## How It Works

```
You speak → Pi captures audio → Vosk transcribes → SSH to Mac →
Claude Code runs → response streams back → Piper TTS speaks → you hear the answer
```

The eye listens (wide open), thinks (darting around), speaks (micro-squints), and idles (lazy blinking). An optional servo lets the whole body nod and tilt. A translucent orange accent ring glows with status visible from across the room.

## Shopping List

| Component | Part | Est. Price | Phase | Notes |
|-----------|------|-----------|-------|-------|
| Board | Raspberry Pi Zero 2W (with headers) | $15 | 1 | Must be the 2W (has WiFi + enough CPU) |
| Storage | 16GB MicroSD Card (Class 10) | $5 | 1 | |
| Cable | Micro-USB data cable | $3 | 1 | Must be data-capable, not charge-only |
| Microphone | INMP441 I2S MEMS breakout | $4 | 1 | I2S digital mic, much cleaner than USB |
| Speaker | 3W 4-ohm 40mm mini speaker | $3 | 1 | |
| Audio Amp | MAX98357A I2S DAC/Amp breakout | $6 | 1 | Drives the speaker over I2S, no USB needed |
| Button | 12mm tactile push button | $0.50 | 1 | Push-to-talk (replaced by wake word in Phase 4) |
| Wiring | Dupont jumper wires + perfboard | $3 | 1 | |
| Display | SSD1306 1.3" 128x64 I2C OLED | $4 | 2 | Monochrome white — the eye lives here |
| LED | 5mm diffused orange LED + 330-ohm resistor | $0.50 | 2 | Behind the accent ring |
| Enclosure | 3D-printed PLA (~50g) | $2 | 2 | White body, translucent orange accent ring |
| Servo | SG90 micro servo (9g) | $3 | 3 | Single-axis nod/tilt for body language |
| **Total** | | **~$49** | | |

Most parts are available on Amazon, Adafruit, or AliExpress. The Pi Zero 2W can be harder to find in stock — check rpilocator.com.

## Build Phases

- **Phase 1 — "It Speaks"**: Voice pipeline only. Press button, talk, hear Claude's answer.
- **Phase 2 — "It Sees"**: Add the OLED display with the animated eye character and the enclosure.
- **Phase 3 — "It Moves"**: Add the servo for nodding and tilting body language.
- **Phase 4 — "It Lives"**: Wake word, idle behaviors, sound design, easter eggs, reliability.

## Project Structure

```
claude-hardware/
├── hardware/          # BOM, wiring diagrams, 3D print files
├── software/clod/     # Python package (asyncio event bus architecture)
├── setup/             # Pi configuration and install scripts
└── docs/              # Architecture docs
```

See [CLAUDE.md](CLAUDE.md) for development conventions and detailed architecture.
