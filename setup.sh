#!/usr/bin/env bash
# ============================================================
# DubSub Setup Script
# Installs all dependencies for fully-local video dubbing
# Uses uv for fast Python package management
#
# Usage:
#   ./setup.sh                    # Default: ja → en
#   ./setup.sh ja en              # Japanese → English
#   ./setup.sh zh fr              # Chinese → French
#   ./setup.sh ko en es fr de     # Korean source + multiple targets
# ============================================================
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

# Parse language args (default: ja → en)
SRC_LANG="${1:-ja}"
shift 2>/dev/null || true
DEST_LANGS=("${@:-en}")
if [ ${#DEST_LANGS[@]} -eq 0 ]; then
    DEST_LANGS=("en")
fi

echo "========================================="
echo "  DubSub - Local Video Dubbing Setup"
echo "========================================="
echo "  Source language:      $SRC_LANG"
echo "  Destination language: ${DEST_LANGS[*]}"
echo ""

# ----------------------------------------------------------
# 1. Check for Homebrew (macOS package manager)
# ----------------------------------------------------------
if ! command -v brew &> /dev/null; then
    echo "[!] Homebrew not found. Installing..."
    /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
else
    echo "[OK] Homebrew found"
fi

# ----------------------------------------------------------
# 2. Install ffmpeg (video/audio Swiss Army knife)
#    Extracts audio from video, merges audio tracks,
#    burns subtitles, adjusts playback speed, etc.
# ----------------------------------------------------------
if ! command -v ffmpeg &> /dev/null; then
    echo "[*] Installing ffmpeg..."
    brew install ffmpeg
else
    echo "[OK] ffmpeg found at $(which ffmpeg)"
fi

# ----------------------------------------------------------
# 3. Check for uv (fast Python package manager)
# ----------------------------------------------------------
if ! command -v uv &> /dev/null; then
    echo "[!] uv not found. Installing via Homebrew..."
    brew install uv
else
    echo "[OK] uv found ($(uv --version))"
fi

# ----------------------------------------------------------
# 4. Install Python dependencies via uv
# ----------------------------------------------------------
echo ""
echo "[*] Installing Python dependencies via uv..."
echo "    - openai-whisper  : Speech-to-text (any language)"
echo "    - argostranslate  : Offline translation (30+ languages)"
echo "    - piper-tts       : Text-to-speech (25+ languages)"
echo "    - ffmpeg-python   : Python bindings for ffmpeg"
echo "    - pysubs2         : Subtitle file parser"
echo "    - pydub           : Audio manipulation"
echo ""

uv sync --group dev

echo ""
echo "[OK] All Python dependencies installed"

# ----------------------------------------------------------
# 5. Download translation models for requested language pairs
# ----------------------------------------------------------
echo ""
for DEST in "${DEST_LANGS[@]}"; do
    echo "[*] Downloading translation model ($SRC_LANG → $DEST)..."
    uv run python -c "
import argostranslate.package
import argostranslate.translate

argostranslate.package.update_package_index()
available = argostranslate.package.get_available_packages()

pkg = next((p for p in available if p.from_code == '$SRC_LANG' and p.to_code == '$DEST'), None)
if pkg:
    print(f'  Downloading: {pkg}')
    download_path = pkg.download()
    argostranslate.package.install_from_path(download_path)
    print('  [OK] $SRC_LANG → $DEST translation model installed')
else:
    print('  [!] Could not find $SRC_LANG → $DEST package.')
    print('  Available source languages:')
    for p in sorted(set(p.from_code for p in available)):
        print(f'    {p}')
"
done

# ----------------------------------------------------------
# 6. Download TTS voice models for destination languages
#    Voice models are auto-downloaded on first run too,
#    but pre-downloading avoids delays during dubbing.
# ----------------------------------------------------------
echo ""
for DEST in "${DEST_LANGS[@]}"; do
    echo "[*] Downloading Piper TTS voice for '$DEST'..."
    uv run python -c "
from pipeline.synthesize import get_voice_model, VOICE_CATALOG
if '$DEST' in VOICE_CATALOG:
    get_voice_model('$DEST')
    print('  [OK] Voice model for $DEST downloaded')
else:
    supported = ', '.join(sorted(VOICE_CATALOG.keys()))
    print(f'  [!] No voice for $DEST. Supported: {supported}')
"
done

echo ""
echo "[*] Whisper model will download on first run (~142MB for 'base')"
echo "    Pre-download with: uv run python -c \"import whisper; whisper.load_model('base')\""

echo ""
echo "========================================="
echo "  Setup complete!"
echo "========================================="
echo ""
echo "Usage:"
echo ""
echo "  # Dub a video (source: $SRC_LANG → dest: ${DEST_LANGS[0]}):"
echo "  uv run python dubsub.py --input your_video.mp4 --src-lang $SRC_LANG --dest-lang ${DEST_LANGS[0]}"
echo ""
echo "  # With existing subtitles (faster):"
echo "  uv run python dubsub.py --input your_video.mp4 --subs your_subs.srt --dest-lang ${DEST_LANGS[0]}"
echo ""
echo "  Output goes to output/ directory"
echo ""
