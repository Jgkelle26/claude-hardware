# Clod (Claude On Desk)

A Raspberry Pi-powered desk companion that lets you talk to Claude Code with your voice. Press a button (or say "Hey Claude"), speak a command, and a little pixel robot with a giant glowing eye thinks, answers, and reacts on a chunky retro RGB matrix.

Built around a **64×64 RGB LED matrix** that renders a single procedural eye as Clod's face. The Pi acts as a thin client — it captures your voice, transcribes it, sends it to your Mac over USB, and Claude Code does the real work. The response streams back, gets spoken aloud, and the eye reacts to every step in chunky glowing pixels.

## How It Works

```
You speak → Pi captures audio (USB mic) → Vosk transcribes → SSH to Mac →
Claude Code runs → response streams back → Piper TTS speaks → you hear the answer
```

The eye listens (wide open, iris steady), thinks (darts around in figure-8s), speaks (micro-squints synced to TTS), and idles (lazy blinking). Color-coded states let you read its mood from across the room — orange iris idle, bright for listening, blue for thinking, green for happy, red for error.

## Shopping List

All Amazon unless noted.

| # | Component | Part | Est. Price | Phase |
|---|-----------|------|-----------|-------|
| 1 | Board | Raspberry Pi Zero 2W with Pre-Soldered Header (iUniker kit) | $25 | 1 |
| 2 | Storage | 16GB MicroSD Card C10/A1 (2-pack) | $10 | 1 |
| 3 | Display | 64×64 RGB LED Matrix Panel, HUB75, P3 (3mm pitch) | $35 | 1 |
| 4 | Matrix Adapter | WatangTech RGB Matrix Adapter Board for Pi (HUB75, dual power) | $15 | 1 |
| 5 | Power Supply | 5V 4A DC Power Supply (5.5×2.1mm barrel jack) | $12 | 1 |
| 6 | Microphone | USB Mini Microphone (plug-and-play UAC) | $8 | 1 |
| 7 | Sound Card | Sabrent USB External Stereo Sound Adapter | $8 | 1 |
| 8 | Amplifier | DEVMO PAM8403 3W Stereo Amp with volume control | $7 | 1 |
| 9 | Speaker | Gikfun 4Ω 40mm 3W Full Range Speaker (2-pack) | $8 | 1 |
| 10 | Button | 12mm Tactile Push Button (25-pack, Gikfun) | $6 | 1 |
| 11 | Wiring | Dupont Jumper Wires 20cm, M-M/M-F/F-F assortment (120pcs) | $7 | 1 |
| 12 | Servo | SG90 Micro Servo 9g | $3 | 3 |
| | | **TOTAL** | **~$144** | |

The Pi Zero 2W can be hard to find in stock — check [rpilocator.com](https://rpilocator.com) for live inventory if needed.

## Build Phases

- **Phase 1 — "It Speaks + Sees"**: Voice pipeline AND the 64×64 matrix face running together. Press button, talk, hear Claude's answer, watch the eye react.
- **Phase 2 — "It Has a Body"**: 3D-printed enclosure (deferred until core build proves out).
- **Phase 3 — "It Moves"**: SG90 servo for nodding and tilting body language.
- **Phase 4 — "It Lives"**: Wake word ("Hey Claude"), idle behaviors, sound design, easter eggs.

## Project Structure

```
claude-hardware/
├── hardware/          # BOM, wiring diagrams, 3D print files
├── software/clod/     # Python package (asyncio event bus architecture)
├── setup/             # Pi configuration and install scripts
└── docs/              # Architecture docs
```

See [CLAUDE.md](CLAUDE.md) for development conventions and detailed architecture.
