"""Persistent TTS server using Coqui XTTS v2.

Start this server before running the Clod orchestrator for fast TTS::

    python -m mac.tts_server --voice-sample /path/to/voice.wav --port 8321

The server loads the model once (~15-20s) then handles requests in ~2-4s each.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from http.server import HTTPServer, BaseHTTPRequestHandler


class TTSHandler(BaseHTTPRequestHandler):
    """HTTP request handler that delegates synthesis to a shared TTS model."""

    tts_model: object | None = None  # set on the class after model loading
    voice_sample: str | None = None  # optional path to reference WAV

    # Silence the default per-request log line; we log ourselves.
    def log_message(self, format: str, *args: object) -> None:  # noqa: A002
        print(f"[request] {self.address_string()} - {format % args}")

    # ----- GET /health ------------------------------------------------

    def do_GET(self) -> None:
        if self.path == "/health":
            self._respond_text(200, "ok")
        else:
            self._respond_text(404, "not found")

    # ----- POST /synthesize -------------------------------------------

    def do_POST(self) -> None:
        if self.path != "/synthesize":
            self._respond_text(404, "not found")
            return

        try:
            content_length = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(content_length))
        except (ValueError, json.JSONDecodeError) as exc:
            self._respond_text(400, f"bad request: {exc}")
            return

        text = body.get("text", "").strip()
        if not text:
            self._respond_text(400, "missing or empty 'text' field")
            return

        language = body.get("language", "en")

        print(f"[synth] Generating speech for: {text[:80]!r} (lang={language})")

        try:
            wav_data = self._synthesize(text, language)
        except Exception as exc:
            self._respond_text(500, f"synthesis failed: {exc}")
            return

        self.send_response(200)
        self.send_header("Content-Type", "audio/wav")
        self.send_header("Content-Length", str(len(wav_data)))
        self.end_headers()
        self.wfile.write(wav_data)

    # ----- synthesis helper -------------------------------------------

    def _synthesize(self, text: str, language: str) -> bytes:
        """Run XTTS synthesis and return raw WAV bytes."""
        fd, wav_path = tempfile.mkstemp(suffix=".wav")
        os.close(fd)

        try:
            if self.voice_sample:
                self.tts_model.tts_to_file(  # type: ignore[union-attr]
                    text=text,
                    speaker_wav=self.voice_sample,
                    language=language,
                    file_path=wav_path,
                )
            else:
                self.tts_model.tts_to_file(  # type: ignore[union-attr]
                    text=text,
                    language=language,
                    file_path=wav_path,
                )

            with open(wav_path, "rb") as f:
                return f.read()
        finally:
            try:
                os.unlink(wav_path)
            except OSError:
                pass

    # ----- response helpers -------------------------------------------

    def _respond_text(self, code: int, message: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", "text/plain")
        self.end_headers()
        self.wfile.write(message.encode("utf-8"))


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Persistent TTS server using Coqui XTTS v2",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8321,
        help="Port to listen on (default: 8321)",
    )
    parser.add_argument(
        "--voice-sample",
        type=str,
        default=None,
        help="Path to a WAV file used as the reference voice for cloning",
    )
    args = parser.parse_args()

    # Validate voice sample path early.
    if args.voice_sample and not os.path.isfile(args.voice_sample):
        print(f"Error: voice sample not found: {args.voice_sample}", file=sys.stderr)
        sys.exit(1)

    # ----- Load model (slow — 15-20 s) --------------------------------
    print("Loading XTTS v2 model (this takes ~15-20 seconds)...")
    from TTS.api import TTS  # noqa: E402  (deferred import to keep startup output visible)

    tts = TTS(model_name="tts_models/multilingual/multi-dataset/xtts_v2", gpu=False)
    print("Model loaded!")

    # Attach model + config to the handler class so every request can use it.
    TTSHandler.tts_model = tts
    TTSHandler.voice_sample = args.voice_sample

    # ----- Start server ------------------------------------------------
    server = HTTPServer(("127.0.0.1", args.port), TTSHandler)
    print(f"TTS server running on http://127.0.0.1:{args.port}")
    print("Endpoints: GET /health, POST /synthesize")

    if args.voice_sample:
        print(f"Voice cloning reference: {args.voice_sample}")
    else:
        print("No voice sample provided — using XTTS default voice")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down TTS server.")
        server.server_close()


if __name__ == "__main__":
    main()
