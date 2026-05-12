# DubSub — Developer Guide

Local AI-powered video dubbing pipeline written in Python 3.12+. Combines Whisper (speech-to-text), Argos Translate (offline translation), and Piper TTS (text-to-speech) — all running on your machine via `ffmpeg`. Dependencies are managed with `uv`; the web UI is served by FastAPI/Uvicorn.

## Quick Start

```bash
# Install system + Python dependencies (Homebrew, ffmpeg, uv, Python deps, models)
./setup.sh                  # default: ja -> en
./setup.sh ja en            # explicit Japanese -> English
./setup.sh zh en es fr      # one source, multiple targets
```

```bash
# Run the CLI pipeline on a video
uv run python dubsub.py --input your_video.mp4 --src-lang ja --dest-lang en

# With existing subtitles (skips Whisper transcription)
uv run python dubsub.py --input your_video.mp4 --subs your_subs.srt --dest-lang en
```

```bash
# Run the web UI (http://localhost:8000)
uv run python webui.py
```

```bash
# Tests + coverage
uv run pytest
uv run pytest --cov=. --cov-report=term-missing

# Format
./format.sh
```
