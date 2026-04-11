# DubSub

Local AI-powered video dubbing. Takes any foreign-language video and produces a dubbed version in your target language with translated subtitles. Runs entirely on your machine — no cloud APIs, no subscriptions.

## How It Works

```
Input Video (.mp4, .mkv, .avi, .webm, ...)
     │
     ├── Subtitles provided? → Parse SRT/ASS file
     │         NO ↓
     │   Extract audio (ffmpeg)
     │         ↓
     │   Transcribe speech (Whisper) → source text + timestamps
     │         ↓
     ├─────────┘
     ↓
Translate text (Argos Translate) → target language text
     ↓
Generate speech (Piper TTS) → audio clips, speed-matched to original timing
     ↓
Compose final video (ffmpeg)
  • Original audio lowered to 30%
  • Dubbed speech overlaid at correct timestamps
  • Translated subtitles burned in
     ↓
Output: dubbed video (.mp4)
```

## Components

| Tool | Purpose | Runs Locally |
|------|---------|:------------:|
| [ffmpeg](https://ffmpeg.org/) | Audio extraction, video composition, subtitle burning | Yes |
| [OpenAI Whisper](https://github.com/openai/whisper) | Speech-to-text with timestamps (99 languages) | Yes |
| [Argos Translate](https://github.com/argosopentech/argos-translate) | Neural machine translation (30+ languages) | Yes |
| [Piper TTS](https://github.com/rhasspy/piper) | Text-to-speech synthesis (25+ languages) | Yes |

## Requirements

- macOS (Homebrew) or Linux
- Python 3.12+
- [uv](https://docs.astral.sh/uv/) (fast Python package manager)
- ~500MB disk space for models (per language pair)

## Quick Start

### 1. Setup

```bash
cd dubsub

# Default setup: Japanese → English
./setup.sh

# Or specify your language pair:
./setup.sh ja en          # Japanese → English
./setup.sh zh en          # Chinese → English
./setup.sh ko en          # Korean → English
./setup.sh es en          # Spanish → English

# Multiple destination languages at once:
./setup.sh ja en fr de    # Japanese → English, French, and German
```

The setup script:
1. Installs **ffmpeg** via Homebrew (skips if already installed)
2. Installs **uv** if missing
3. Runs `uv sync` — creates `.venv/` and installs all Python dependencies
4. Downloads the **translation model** for your language pair (~100MB each)
5. Downloads the **TTS voice model** for your destination language (~60MB each)
6. Whisper speech model downloads on first run (~142MB)

### 2. Dub a video

```bash
# Japanese anime, auto-transcribe → English dub
uv run python dubsub.py --input my_anime.mp4

# With an existing subtitle file (faster, skips transcription)
uv run python dubsub.py --input my_anime.mp4 --subs my_anime.srt

# Chinese movie → French dub
uv run python dubsub.py --input movie.mkv --src-lang zh --dest-lang fr

# Korean drama from AVI file → English
uv run python dubsub.py --input drama.avi --src-lang ko --dest-lang en
```

Output is saved to `output/<filename>_dubbed.mp4`.

### 3. Or use the Web UI

If you prefer a browser interface over the command line:

```bash
uv run python webui.py
```

Open **http://localhost:8000** — upload your video, pick languages, and hit Start. Progress streams in real time; download the result when it's done.

## Supported Video Formats

DubSub uses ffmpeg under the hood, so it supports any format ffmpeg can read — which is essentially everything:

| Format | Extension | Notes |
|--------|-----------|-------|
| MP4 | `.mp4` | Most common, works everywhere |
| Matroska | `.mkv` | Common for anime fansubs, supports multiple audio/subtitle tracks |
| AVI | `.avi` | Older format, fully supported |
| WebM | `.webm` | Web video format |
| MOV | `.mov` | Apple QuickTime |
| FLV | `.flv` | Flash video |
| TS | `.ts` | Transport stream (broadcast) |

Output is always `.mp4` (H.264 video + AAC audio) for maximum compatibility.

## Supported Languages

### Source languages (speech recognition)

Whisper supports **99 languages** for speech-to-text. Common ones:

`ja` Japanese, `zh` Chinese, `ko` Korean, `en` English, `es` Spanish, `fr` French, `de` German, `it` Italian, `pt` Portuguese, `ru` Russian, `ar` Arabic, `hi` Hindi, `th` Thai, `vi` Vietnamese, `id` Indonesian, `tr` Turkish, `pl` Polish, `nl` Dutch, `sv` Swedish, `da` Danish, `fi` Finnish, `el` Greek, `cs` Czech, `ro` Romanian, `hu` Hungarian, `uk` Ukrainian

Full list: [Whisper language codes](https://github.com/openai/whisper#available-models-and-languages)

### Destination languages (TTS voices)

Piper TTS has voices for **25+ languages** built in:

| Code | Language | Code | Language |
|------|----------|------|----------|
| `en` | English | `fr` | French |
| `ja` | Japanese | `de` | German |
| `zh` | Chinese | `it` | Italian |
| `ko` | Korean | `pt` | Portuguese |
| `es` | Spanish | `ru` | Russian |
| `pl` | Polish | `uk` | Ukrainian |
| `vi` | Vietnamese | `ar` | Arabic |
| `tr` | Turkish | `nl` | Dutch |
| `cs` | Czech | `fi` | Finnish |
| `el` | Greek | `hu` | Hungarian |
| `da` | Danish | `no` | Norwegian |
| `sv` | Swedish | `ro` | Romanian |
| `ka` | Georgian | `is` | Icelandic |

### Translation (Argos Translate)

Argos supports **30+ language pairs**. To see all available pairs:

```bash
uv run python -c "
import argostranslate.package
argostranslate.package.update_package_index()
for pkg in argostranslate.package.get_available_packages():
    print(f'{pkg.from_code} → {pkg.to_code}')
"
```

### Adding a new language

Adding support for a new language requires at most two things:

**1. Translation model** — just run setup with the new pair:
```bash
./setup.sh <src> <dest>
# e.g., ./setup.sh th en    # Thai → English
```

**2. TTS voice** — if the destination language is already in the voice catalog (`pipeline/synthesize.py` → `VOICE_CATALOG`), it downloads automatically. To add a new voice:

1. Browse the [Piper voice catalog](https://rhasspy.github.io/piper-samples/)
2. Pick a voice and note its path (e.g., `th/th_TH/somevoice/medium/th_TH-somevoice-medium`)
3. Add an entry to `VOICE_CATALOG` in `pipeline/synthesize.py`:
   ```python
   VOICE_CATALOG = {
       ...
       "th": ("th_TH-somevoice-medium.onnx",
              "th/th_TH/somevoice/medium/th_TH-somevoice-medium"),
   }
   ```
4. That's it — the model downloads automatically on first use.

## All CLI Options

```
uv run python dubsub.py --help

Options:
  --input, -i          Input video file — any format ffmpeg supports (required)
  --subs, -s           Subtitle file (SRT, ASS, SSA). Skips transcription.
  --output, -o         Output path (default: output/<name>_dubbed.mp4)
  --src-lang           Source language code (default: ja)
  --dest-lang          Destination language code (default: en)
  --whisper-model      tiny | base | small | medium | large (default: base)
  --original-volume    Original audio volume 0.0-1.0 (default: 0.3)
  --no-subtitles       Don't burn subtitles into the video
```

### Whisper model sizes

| Model | Size | Speed | Accuracy | Best for |
|-------|------|-------|----------|----------|
| tiny | 39MB | Fastest | Lower | Quick test runs |
| base | 142MB | Fast | Good | **Default — good balance** |
| small | 466MB | Medium | Better | Most use cases |
| medium | 1.5GB | Slow | Great | When accuracy matters |
| large | 2.9GB | Slowest | Best | Final production dubs |

## Running Tests

```bash
uv run pytest tests/ -v              # all tests
uv run pytest tests/test_webui.py -v # web UI API tests only
```

## CI / GitHub Actions

Tests run automatically via GitHub Actions:

- **On push to main** — installs deps, runs full test suite. Can also be triggered manually from the Actions tab.
- **On pull requests to main** — same checks, shown as PR status before merge.

## Project Structure

```
dubsub/
├── dubsub.py              # CLI entry point — orchestrates the pipeline
├── webui.py               # Web UI (FastAPI) — browser-based dubbing
├── pipeline/
│   ├── extract.py         # Extract audio from video (ffmpeg)
│   ├── transcribe.py      # Speech-to-text (Whisper) + subtitle parsing
│   ├── translate.py       # Text translation (Argos Translate)
│   ├── synthesize.py      # Text-to-speech + voice catalog (Piper TTS)
│   └── compose.py         # Final video assembly (ffmpeg)
├── tests/                 # Unit tests (pytest + httpx)
├── .github/workflows/
│   ├── ci.yml             # CI on push to main + manual trigger
│   └── pr.yml             # PR checks on pull requests to main
├── .vscode/
│   └── launch.json        # Debug configs (CLI, Web UI, tests)
├── models/
│   └── piper/             # TTS voice models (auto-downloaded)
├── output/                # Default output directory
├── pyproject.toml         # Project config and dependencies (uv)
└── setup.sh               # One-command setup (accepts language args)
```

## Limitations

- **Translation quality**: Argos Translate is good but not Google/DeepL level. Dialogue with slang or cultural references may be rough.
- **Single voice**: Currently uses one voice per language for all characters. Multi-voice support (detecting different speakers) is a future goal.
- **No lip sync**: Audio is time-aligned to original speech segments but doesn't match lip movements. See [Lip Sync](#lip-sync-not-yet-implemented) below.
- **Speed adjustment**: When the translation is longer than the original, speech is sped up (capped at 2x) which can sound unnatural.

## Lip Sync (not yet implemented)

DubSub currently does **time-alignment only** — the TTS is sped up or slowed down to fit the original segment's start/end timestamps. There is no visual lip sync (modifying the character's mouth to match the dubbed audio).

True lip sync is a hard problem that requires:

1. **Face/mouth detection** — locate the speaking character's mouth on each frame. Especially challenging for anime, where faces are stylized drawings rather than real human faces.
2. **Viseme mapping** — map phonemes (speech sounds) to mouth shapes (visemes) frame-by-frame.
3. **Frame manipulation** — redraw or warp the mouth region in each video frame to match the new audio.

### Possible approaches to explore

- **[Wav2Lip](https://github.com/Rudrabha/Wav2Lip)** — generates lip movements from audio. Works well on real-face video; anime results would need testing/fine-tuning.
- **[SadTalker](https://github.com/OpenTalker/SadTalker)** — generates talking head videos from audio + a face image. Could work for static anime portraits.
- **[Video Retalking](https://github.com/OpenTalker/video-retalking)** — audio-driven lip sync editing on real video, potentially adaptable.
- **Custom approach for anime** — anime mouth animation is simpler (typically open/close cycles). A lighter-weight solution could detect mouth state (open/closed) from the audio energy envelope and swap between mouth frames, rather than doing full viseme mapping.

This is planned for a future version. Contributions welcome.

## Future Ideas

- **Lip sync** — see [above](#lip-sync-not-yet-implemented)
- Speaker diarization (who is talking) for multi-voice dubbing
- Voice cloning to match character voice characteristics
- Real-time / streaming mode for live content
- ~~GUI / web interface~~ (done — `webui.py`)
- Batch processing for full series

## License

MIT
