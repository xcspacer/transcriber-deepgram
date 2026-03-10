# Real-time Audio Transcription & Translation

Captures all audio output from your laptop and produces simultaneous transcriptions with English translation, powered by [Deepgram Nova-3](https://deepgram.com).

## Features

- Captures system audio output in real time (browser, video calls, media players, etc.)
- Transcribes speech in multiple languages automatically
- Translates non-English speech to English simultaneously
- Saves every session as a timestamped JSON file in the `transcriptions/` folder
- Maintains the WebSocket connection during silent periods (keeps-alive automatically)

## Requirements

**System dependencies** (PulseAudio):

```bash
sudo apt install pulseaudio-utils  # Ubuntu/Debian
```

**Python 3.12+** and the packages listed in `requirements.txt`.

## Installation

```bash
# Clone or copy the project folder, then enter it
cd transcriber-deepgram

# Create and activate a virtual environment
python3 -m venv venv
source venv/bin/activate

# Install Python dependencies
pip install -r requirements.txt
```

## Configuration

1. Copy `.env` and add your Deepgram API key:

   ```
   DEEPGRAM_API_KEY=your-key-here
   ```

   Get a free key (USD $200 in credits) at <https://console.deepgram.com/signup>.

2. Optionally, open `app.py` and adjust the settings near the top of the file:

   | Variable             | Default        | Description                                      |
   |----------------------|----------------|--------------------------------------------------|
   | `DEVICE_NAME`        | *(auto-detect)*| Default monitor device if none is selected       |
   | `DISPLAY_MODE`       | `"both"`       | `"both"`, `"original"`, or `"translation"`       |
   | `SILENCE_THRESHOLD`  | `100`          | RMS level below which audio is considered silent |
   | `AUTO_SAVE_INTERVAL` | `5`            | Seconds between automatic JSON saves             |

   **Display modes:**

   - `both` — shows the original text and the English translation side by side *(default)*
   - `original` — shows the detected text only, no translation
   - `translation` — shows the English translation only

## Usage

```bash
source venv/bin/activate
python app.py
```

On launch the script lists all available audio monitor devices and asks you to choose one. Press **Enter** to use the default device detected automatically.

Press **Ctrl+C** to stop. The session is saved immediately on exit.

## Output

Each session produces a JSON file in `transcriptions/`, for example:

```
transcriptions/transcription_2026-03-10_14-30-00.json
```

```json
{
  "session_start": "2026-03-10T14:30:00.000000",
  "session_end":   "2026-03-10T14:45:12.000000",
  "total_transcriptions": 42,
  "model": "nova-3",
  "display_mode": "both",
  "transcriptions": [
    {
      "timestamp": "2026-03-10T14:30:05.123456",
      "language": "pt",
      "text": "Bom dia, como vai?",
      "formatted": "[PT] Bom dia, como vai?\n[EN] Good morning, how are you?"
    }
  ]
}
```

## Troubleshooting

| Problem | Solution |
|---------|----------|
| No devices listed | Ensure PulseAudio is running: `pulseaudio --start` |
| `parec` not found | Install `pulseaudio-utils` |
| API key error | Check that `.env` contains a valid `DEEPGRAM_API_KEY` |
| No transcription output | Verify the correct monitor device is selected and audio is actually playing |
