# dubsub — Architecture

## High-Level Overview

DubSub is a **local AI-powered video dubbing pipeline**. Despite the name, it is not pub/sub: "Dub" + "Sub(titles)". It takes a foreign-language video, transcribes the speech (or parses a provided subtitle file), translates it, synthesizes dubbed audio in the target language, and re-composes a final video with the dubbed track mixed over the original.

Runtime model:

- **Python 3.12+ monolithic process**, managed by `uv` (`pyproject.toml` + `.venv/`).
- Two entry points, both wrapping the same `pipeline/` package:
  - `dubsub.py` — argparse CLI; synchronous 4-step pipeline run in the foreground.
  - `webui.py` — FastAPI + uvicorn server on `:8000`. Each upload spawns a background `threading.Thread` that executes the same pipeline; stdout is intercepted via an `OutputCapture` shim and streamed to the browser over Server-Sent Events. Job state lives in an in-memory `jobs: dict` (no persistence).
- **All inference runs on the local machine** — no cloud calls. External binaries: `ffmpeg` (system-installed). Local models: OpenAI Whisper (STT), Argos Translate (MT), Piper TTS (synthesis). Models are downloaded on first use into `models/` (Piper) or the library's default cache (Whisper, Argos).
- Working files (extracted audio, per-segment TTS clips) live under `output/work/`; final video at `output/<name>_dubbed.mp4`.

Pipeline (4 stages, executed sequentially by `dubsub.py:main` and `webui.py:run_pipeline`):

```
input video ─┬─► extract audio (ffmpeg) ─► transcribe (Whisper) ──┐
             └─► parse SRT/ASS (pysubs2) ──────────────────────────┤
                                                                   ▼
                                                       translate (Argos)
                                                                   ▼
                                                      synthesize (Piper TTS)
                                                                   ▼
                                                 compose (ffmpeg: mix + burn subs)
                                                                   ▼
                                                          output/*.mp4
```

## Key Directories

- `pipeline/` — the five pipeline stages, one module each. Pure functions; imported lazily by entry points to keep `--help` fast and avoid loading heavy ML deps when unused.
- `tests/` — pytest suite. One `test_<stage>.py` per pipeline module plus `test_cli.py` (argparse smoke) and `test_webui.py` (FastAPI/httpx API tests).
- `.github/workflows/` — CI (`ci.yml`, push to main + manual), PR checks (`pr.yml`), and the release workflow (`release.yml`, manual dispatch).
- `models/piper/` — auto-downloaded Piper voice models (gitignored at runtime).
- `output/` — final dubbed videos and the `output/work/` scratch dir for intermediate audio.
- `uploads/` — Web UI upload staging directory.
- `.vscode/` — debug launch configs.

## Important Files

- `dubsub.py` — CLI entry point. Parses args, validates paths, wires the four pipeline calls. Lazy-imports each `pipeline/*` module per stage. Two branches at Step 1: `--subs` → `segments_from_subtitles`, otherwise `extract_audio` + `transcribe_audio`.
- `webui.py` — FastAPI app. Endpoints for upload, SSE progress stream, and download. Runs the pipeline in a daemon thread with stdout redirected so the same stage prints used by the CLI become browser progress events.
- `pipeline/extract.py` — `extract_audio(video, work_dir)` shells ffmpeg to pull a 16 kHz mono WAV.
- `pipeline/transcribe.py` — `transcribe_audio` (Whisper) and `segments_from_subtitles` (pysubs2). Both return a uniform list of `{start, end, text}` segments — the common shape that flows through the rest of the pipeline.
- `pipeline/translate.py` — `translate_segments`. Ensures the Argos package for `src→dest` is installed, then translates each segment's text in place.
- `pipeline/synthesize.py` — `synthesize_segments` + `VOICE_CATALOG` mapping `dest_lang → (onnx filename, Piper repo path)`. Downloads voice on demand, generates one WAV clip per segment, speed-matches to the original segment duration (capped at 2x).
- `pipeline/compose.py` — `compose_video`. Builds an ffmpeg filter graph that lowers original audio volume, overlays each TTS clip at its `start` timestamp, and (optionally) burns the translated subtitles.
- `pyproject.toml` — project metadata, `>=3.12`, runtime deps (`openai-whisper`, `argostranslate`, `piper-tts`, `pysubs2`, `pydub`, `ffmpeg-python`, `fastapi`, `uvicorn`, `python-multipart`), dev deps (`pytest`, `pytest-cov`, `httpx`). Exposes a `dubsub` console script.
- `setup.sh` — one-shot bootstrap: installs Homebrew ffmpeg + uv, runs `uv sync`, downloads Argos translation packages and Piper voices for the language pair(s) passed as args.
- `format.sh` — formatter invocation.
- `CLAUDE.md`, `DEV.md`, `README.md` — agent / developer / user docs.

## Build & Release Flow

- **Dependency install**: `uv sync --group dev` creates `.venv/` from `pyproject.toml` (no `requirements.txt`, no `uv.lock` committed). System `ffmpeg` is installed separately by `setup.sh` (Homebrew) or CI (`apt-get`).
- **Tests**: `uv run pytest tests/ -v`. `pyproject.toml` pins `testpaths = ["tests"]` and `pythonpath = ["."]` so the top-level `dubsub.py` / `webui.py` and the `pipeline/` package both resolve.
- **CI** (`.github/workflows/ci.yml`): on push to `main`/`master` and manual dispatch. Installs uv + ffmpeg, runs `uv sync --group dev`, runs pytest.
- **PR checks** (`.github/workflows/pr.yml`): same shape as CI, gated on pull requests to `main`.
- **Release** (`.github/workflows/release.yml`): **manual `workflow_dispatch` only**, with required `tag` input (e.g. `v0.1.0`) and optional release notes. Pipeline: checkout → setup-python 3.12 → setup-uv → install ffmpeg → `uv sync --group dev` → run pytest → `tar -czf` a source bundle (`dubsub.py`, `webui.py`, `pipeline/`, `tests/`, `pyproject.toml`, `setup.sh`, `README.md`, `CLAUDE.md`, excluding `.git`, `.venv`, `output`, `uploads`, `models`) into `release-artifacts/` → `softprops/action-gh-release@v2` publishes a non-draft, non-prerelease GitHub Release with the tar as the asset.
- **Versioning**: `version` in `pyproject.toml` (currently `0.1.1`). The release workflow takes the tag from dispatch input — it does **not** read `pyproject.toml` and does **not** fall back to `github.ref_name`, so the tag must be passed explicitly.
- **No published package**: there is no PyPI publish step and no built wheel — releases are source tarballs only.
