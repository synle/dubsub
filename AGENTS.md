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
- **FastAPI + Uvicorn** — web UI for browser-based dubbing

## Architecture

The pipeline is split into 5 sequential stages in `pipeline/`:

1. `extract.py` — Pull audio from video via ffmpeg (WAV, 16kHz mono)
2. `transcribe.py` — Whisper STT or subtitle file parsing → `Segment(start, end, text)`
3. `translate.py` — Argos Translate each segment's text (ja→en)
4. `synthesize.py` — Piper TTS for each segment, speed-adjusted to fit original timing
5. `compose.py` — Mix dubbed audio over lowered original, burn subtitles, export video

`dubsub.py` is the CLI entry point that orchestrates these stages.

`webui.py` is the web UI entry point — a single-file FastAPI app with embedded HTML. It runs the same pipeline stages in a background thread, captures stdout via `OutputCapture` to stream real-time progress to the browser using SSE (Server-Sent Events), and serves a download link when done. Uploaded files go to `uploads/`, output to `output/` as usual.

## Key Data Type

`Segment(start: float, end: float, text: str)` — defined in `transcribe.py`, used throughout the pipeline. Timestamps are in seconds.

## Running

```bash
# CLI
uv run python dubsub.py --input video.mp4                    # auto-transcribe
uv run python dubsub.py --input video.mp4 --subs subs.srt    # with subtitles

# Web UI
uv run python webui.py                                        # opens at http://localhost:8000

# Tests
uv run pytest tests/ -v                                       # all tests
uv run pytest tests/test_webui.py -v                          # web UI tests only

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
- `webui.py` is a self-contained single file (HTML embedded as a string, no templates dir)
- Uploaded files go to `uploads/<job_id>/`, working files to `output/work/<job_id>/`

## CI / GitHub Actions

Two workflows in `.github/workflows/`:

- **`ci.yml`** — runs on push to `main`/`master` + manual trigger (`workflow_dispatch`). Installs uv, ffmpeg, deps, runs `pytest`.
- **`pr.yml`** — runs on PRs targeting `main`/`master`. Same steps. PRs show pass/fail before merge.

## VS Code

`.vscode/launch.json` has debug configs for:
- CLI (auto-transcribe, with subtitles, custom args)
- Web UI (`webui.py`)
- Tests (all, web UI only, current file)

## Keeping This File Updated

When making significant changes (new entry points, new pipeline stages, new dependencies, architectural shifts), update this CLAUDE.md file so it stays accurate. This file is the primary context for AI-assisted development — stale info here leads to wrong assumptions in future sessions.
