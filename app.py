#!/usr/bin/env python3
"""
Real-time audio transcription using Deepgram Nova-3.
Captures system audio output (laptop speakers) and transcribes with simultaneous translation.

Uses WebSocket directly (no complex SDK required).
"""

import os
import sys
import subprocess
import asyncio
import json
import websockets
import numpy as np
from datetime import datetime
from deep_translator import GoogleTranslator

# ===========================
# CONFIGURATION
# ===========================

# Monitor device for capturing audio output (e.g. browser, video calls)
DEVICE_NAME = "alsa_output.pci-0000_04_00.6.HiFi__hw_Generic_1__sink.monitor"

# Audio settings
SAMPLE_RATE = 48000
CHANNELS = 2
SILENCE_THRESHOLD = 100  # RMS threshold for silence detection (0-32767)
KEEPALIVE_INTERVAL = 5   # Seconds between keep-alive pings during silence

# Transcription display mode:
#   "both"        - Show original text + English translation
#   "original"    - Show original text only
#   "translation" - Show English translation only
DISPLAY_MODE = "both"

# Deepgram settings
DEEPGRAM_MODEL = "nova-3"
DEEPGRAM_WS_URL = "wss://api.deepgram.com/v1/listen"

# Directory to save transcription files
TRANSCRIPTIONS_DIR = "transcriptions"

# Auto-save interval in seconds
AUTO_SAVE_INTERVAL = 5


# ===========================
# ENVIRONMENT LOADING
# ===========================

def load_env(env_file):
    """Load variables from a .env file into the environment."""
    if not os.path.exists(env_file):
        return
    with open(env_file, 'r') as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                key, _, value = line.partition('=')
                os.environ.setdefault(key.strip(), value.strip())




# ===========================
# API KEY
# ===========================

def check_api_key():
    """Load the Deepgram API key from .env or environment variable."""
    env_file = os.path.join(os.path.dirname(__file__), ".env")
    load_env(env_file)

    api_key = os.getenv("DEEPGRAM_API_KEY")
    if api_key:
        print("API key loaded successfully.")
        return api_key

    print("ERROR: DEEPGRAM_API_KEY is not configured.")
    print("\nTo configure:")
    print("  1. Add your key to the .env file:")
    print("       DEEPGRAM_API_KEY=your-key-here")
    print("  2. Or set an environment variable:")
    print("       export DEEPGRAM_API_KEY='your-key-here'")
    print("\nGet a free API key (USD $200 in credits) at:")
    print("  https://console.deepgram.com/signup")
    sys.exit(1)


# ===========================
# TRANSCRIPTION FORMATTING
# ===========================

def format_transcription(text, language):
    """Format the transcription according to DISPLAY_MODE."""
    if not text or not text.strip():
        return None

    text = text.strip()
    lang_upper = language.upper() if language else "?"

    if DISPLAY_MODE == "original":
        return f"[{lang_upper}] {text}"

    elif DISPLAY_MODE == "translation":
        # Show Portuguese translation; if already Portuguese, show as-is
        if language and language.lower() not in ("pt", "pt-br", "pt-pt"):
            try:
                translator = GoogleTranslator(source='auto', target='pt')
                translated = translator.translate(text)
                return f"[PT] {translated}"
            except Exception:
                return f"[{lang_upper}] {text}"
        else:
            return f"[PT] {text}"

    else:  # "both" — show original alongside Portuguese translation
        if language and language.lower() not in ("pt", "pt-br", "pt-pt"):
            try:
                translator = GoogleTranslator(source='auto', target='pt')
                translated = translator.translate(text)
                return f"[{lang_upper}] {text}\n[PT] {translated}"
            except Exception:
                return f"[{lang_upper}] {text}"
        else:
            return f"[{lang_upper}] {text}"


# ===========================
# AUDIO CAPTURE & STREAMING
# ===========================

async def stream_audio(api_key, transcriptions, start_time, filepath, device_name):
    """Capture audio from the selected device and stream it to Deepgram via WebSocket."""

    url = (
        f"{DEEPGRAM_WS_URL}"
        f"?model={DEEPGRAM_MODEL}"
        f"&smart_format=true"
        f"&language=multi"
        f"&encoding=linear16"
        f"&sample_rate={SAMPLE_RATE}"
        f"&channels={CHANNELS}"
    )

    headers = {"Authorization": f"Token {api_key}"}

    print("Connecting to Deepgram...")

    keep_running = True

    try:
        async with websockets.connect(url, additional_headers=headers) as ws:
            print(f"Connected to Deepgram {DEEPGRAM_MODEL}")
            print(f"Device  : {device_name}")
            print(f"Mode    : {DISPLAY_MODE}")
            print(f"Silence : threshold={SILENCE_THRESHOLD} RMS")
            print(f"Save    : every {AUTO_SAVE_INTERVAL}s -> {filepath}")
            print("\nListening... (Ctrl+C to stop)\n")
            print("=" * 70)

            audio_process = subprocess.Popen(
                [
                    'parec',
                    '--device', device_name,
                    '--rate', str(SAMPLE_RATE),
                    '--channels', str(CHANNELS),
                    '--format', 's16le',
                    '--raw'
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )

            async def send_audio():
                nonlocal keep_running
                try:
                    chunk_size = 8192
                    last_status = None
                    last_keepalive = asyncio.get_event_loop().time()
                    sound_chunks = 0

                    while True:
                        data = audio_process.stdout.read(chunk_size)
                        if not data:
                            break

                        # Calculate RMS to detect silence vs sound
                        audio_array = np.frombuffer(data, dtype=np.int16)
                        audio_float = audio_array.astype(np.float64)
                        rms = np.sqrt(np.mean(audio_float ** 2))

                        if np.isnan(rms) or np.isinf(rms):
                            rms = 0

                        if rms > SILENCE_THRESHOLD:
                            await ws.send(data)
                            sound_chunks += 1
                            last_keepalive = asyncio.get_event_loop().time()

                            if last_status != "sound":
                                print("Detecting audio — transcribing...", end="\r")
                                last_status = "sound"
                        else:
                            # Keep sending silent audio to maintain the WebSocket connection.
                            # Deepgram closes the connection after ~10 s without data.
                            await ws.send(data)

                            if last_status != "silence" and sound_chunks > 0:
                                print("Silence — connection kept alive...  ", end="\r")
                                last_status = "silence"

                            current_time = asyncio.get_event_loop().time()
                            if current_time - last_keepalive >= KEEPALIVE_INTERVAL:
                                await ws.send(json.dumps({"type": "KeepAlive"}))
                                last_keepalive = current_time

                        await asyncio.sleep(0.01)

                except Exception as e:
                    print(f"\nError sending audio: {e}")
                finally:
                    keep_running = False
                    try:
                        await ws.send(json.dumps({"type": "CloseStream"}))
                    except Exception:
                        pass

            async def receive_transcripts():
                try:
                    async for message in ws:
                        try:
                            data = json.loads(message)

                            if data.get("type") != "Results":
                                continue

                            channel = data.get("channel", {})
                            alternatives = channel.get("alternatives", [])

                            if not alternatives:
                                continue

                            transcript = alternatives[0].get("transcript", "").strip()

                            if not transcript:
                                continue

                            # Detect language from metadata or alternatives
                            detected_language = None
                            if "metadata" in data:
                                detected_language = data["metadata"].get("model_info", {}).get("language")

                            if not detected_language and alternatives:
                                detected_language = alternatives[0].get("languages", [None])[0]

                            formatted = format_transcription(transcript, detected_language)

                            if formatted:
                                print(" " * 80, end="\r")  # Clear status line
                                print(formatted)
                                print("-" * 70)

                                transcriptions.append({
                                    "timestamp": datetime.now().isoformat(),
                                    "language": detected_language,
                                    "text": transcript,
                                    "formatted": formatted,
                                })

                        except json.JSONDecodeError:
                            continue
                        except Exception as e:
                            print(f"Error processing message: {e}")
                            continue

                except websockets.exceptions.ConnectionClosed:
                    print("\nDeepgram connection closed.")
                except Exception as e:
                    print(f"\nError receiving transcriptions: {e}")

            async def auto_save():
                nonlocal keep_running
                try:
                    while keep_running:
                        await asyncio.sleep(AUTO_SAVE_INTERVAL)
                        if transcriptions:
                            save_transcriptions(transcriptions, start_time, filepath, silent=True)
                except asyncio.CancelledError:
                    pass
                except Exception as e:
                    print(f"\nAuto-save error: {e}")

            await asyncio.gather(
                send_audio(),
                receive_transcripts(),
                auto_save()
            )

            audio_process.terminate()
            audio_process.wait()

    except asyncio.CancelledError:
        pass
    except websockets.exceptions.InvalidHandshake as e:
        print(f"\nConnection rejected: {e}")
        print("Please verify that your API key is correct.")
    except Exception as e:
        print(f"\nUnexpected error: {e}")
        import traceback
        traceback.print_exc()


# ===========================
# SAVE & MAIN
# ===========================

def save_transcriptions(transcriptions, start_time, filepath, silent=False):
    """
    Save transcriptions to a JSON file.

    Args:
        transcriptions: List of transcription entries.
        start_time:     Session start datetime.
        filepath:       Full path to the output file.
        silent:         If True, suppress console output (used for auto-save).
    """
    if not transcriptions:
        if not silent:
            print("No transcriptions to save.")
        return

    os.makedirs(TRANSCRIPTIONS_DIR, exist_ok=True)

    data = {
        "session_start": start_time.isoformat(),
        "session_end": datetime.now().isoformat(),
        "total_transcriptions": len(transcriptions),
        "model": DEEPGRAM_MODEL,
        "display_mode": DISPLAY_MODE,
        "auto_save_interval": AUTO_SAVE_INTERVAL,
        "transcriptions": transcriptions,
    }

    try:
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        if not silent:
            print(f"\nTranscriptions saved to: {filepath}")
            print(f"Total entries: {len(transcriptions)}")
    except Exception as e:
        if not silent:
            print(f"\nFailed to save file: {e}")


async def main():
    api_key = check_api_key()
    device_name = DEVICE_NAME

    transcriptions = []
    start_time = datetime.now()

    os.makedirs(TRANSCRIPTIONS_DIR, exist_ok=True)

    filename = f"transcription_{start_time.strftime('%Y-%m-%d_%H-%M-%S')}.json"
    filepath = os.path.join(TRANSCRIPTIONS_DIR, filename)
    print(f"Output file: {filepath}\n")

    try:
        await stream_audio(api_key, transcriptions, start_time, filepath, device_name)
    except (KeyboardInterrupt, asyncio.CancelledError):
        print("\n\nCapture stopped.")
    except Exception as e:
        print(f"\nFatal error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        save_transcriptions(transcriptions, start_time, filepath, silent=False)


if __name__ == "__main__":
    print("Deepgram Nova-3 — Real-time Audio Transcription & Translation")
    print("=" * 70)
    asyncio.run(main())
