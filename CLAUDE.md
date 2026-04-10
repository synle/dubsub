# DubSub - Claude Code Instructions

## What This Project Is

A local AI-powered video dubbing pipeline. Takes foreign-language video (default: Japanese) and produces an English-dubbed version with translated subtitles. Everything runs locally — no cloud APIs.

## Tech Stack

- **Python 3.12+** managed by **uv** (virtual env at `.venv/`)
- **ffmpeg** — video/audio extraction and composition
- **OpenAI Whisper** — local speech-to-text (supports 99 languages)
- **Argos Translate** — local neural machine translation
- **Piper TTS** — local text-to-speech synthesis
- **pydub** — audio manipulation (speed adjustment, mixing)
- **pysubs2** — subtitle file parsing (SRT, ASS, SSA)

## Architecture

The pipeline is split into 5 sequential stages in `pipeline/`:

1. `extract.py` — Pull audio from video via ffmpeg (WAV, 16kHz mono)
2. `transcribe.py` — Whisper STT or subtitle file parsing → `Segment(start, end, text)`
3. `translate.py` — Argos Translate each segment's text (ja→en)
4. `synthesize.py` — Piper TTS for each segment, speed-adjusted to fit original timing
5. `compose.py` — Mix dubbed audio over lowered original, burn subtitles, export video

`dubsub.py` is the CLI entry point that orchestrates these stages.

## Key Data Type

`Segment(start: float, end: float, text: str)` — defined in `transcribe.py`, used throughout the pipeline. Timestamps are in seconds.

## Running

```bash
uv run python dubsub.py --input video.mp4                    # auto-transcribe
uv run python dubsub.py --input video.mp4 --subs subs.srt    # with subtitles

# Or activate venv first:
source .venv/bin/activate
python dubsub.py --input video.mp4
```

## Adding dependencies

```bash
uv add <package>    # adds to pyproject.toml and installs
uv sync             # reinstall from pyproject.toml
```

## Conventions

- Default language pair: `ja` (Japanese) → `en` (English), configured via `--src-lang` / `--dest-lang`
- Output goes to `output/` directory
- TTS voice models stored in `models/piper/`
- Working/temp files go in `output/work/`
- Each pipeline module prints progress with `[module_name]` prefix (e.g., `[transcribe]`, `[translate]`)
