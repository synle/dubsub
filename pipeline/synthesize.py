"""
Text-to-Speech synthesis using Piper TTS.

What this does:
  Takes translated text and generates spoken audio for each segment.
  The audio is time-aligned to match the original speech timing.

About Piper TTS:
  - Fast, local text-to-speech engine
  - Uses ONNX neural network models
  - Multiple voices available (we use en_US-amy-medium)
  - Produces natural-sounding speech
  - Runs entirely on CPU, no GPU needed

Time alignment challenge:
  The original Japanese line might be 3 seconds long, but the English
  translation spoken at normal speed might be 4 seconds. We need to
  speed up or slow down the TTS audio to fit the original timing.
  We use pydub + ffmpeg to adjust playback speed without changing pitch
  too much.
"""

import os
import subprocess
import tempfile
from pathlib import Path

from pydub import AudioSegment

from pipeline.transcribe import Segment


SCRIPT_DIR = Path(__file__).resolve().parent.parent
MODELS_DIR = SCRIPT_DIR / "models" / "piper"

# Piper voice models per language.
# Each entry: (model_filename, huggingface download path)
# Full catalog: https://rhasspy.github.io/piper-samples/
VOICE_CATALOG = {
    "en": ("en_US-amy-medium.onnx",
           "en/en_US/amy/medium/en_US-amy-medium"),
    "ja": ("ja_JP-takumi-medium.onnx",
           "ja/ja_JP/takumi/medium/ja_JP-takumi-medium"),
    "zh": ("zh_CN-huayan-medium.onnx",
           "zh/zh_CN/huayan/medium/zh_CN-huayan-medium"),
    "ko": ("ko_KR-kagayaki-medium.onnx",
           "ko/ko_KR/kagayaki/medium/ko_KR-kagayaki-medium"),
    "es": ("es_ES-sharvard-medium.onnx",
           "es/es_ES/sharvard/medium/es_ES-sharvard-medium"),
    "fr": ("fr_FR-siwis-medium.onnx",
           "fr/fr_FR/siwis/medium/fr_FR-siwis-medium"),
    "de": ("de_DE-thorsten-medium.onnx",
           "de/de_DE/thorsten/medium/de_DE-thorsten-medium"),
    "it": ("it_IT-riccardo-x_low.onnx",
           "it/it_IT/riccardo/x_low/it_IT-riccardo-x_low"),
    "pt": ("pt_BR-faber-medium.onnx",
           "pt/pt_BR/faber/medium/pt_BR-faber-medium"),
    "ru": ("ru_RU-denis-medium.onnx",
           "ru/ru_RU/denis/medium/ru_RU-denis-medium"),
    "pl": ("pl_PL-darkman-medium.onnx",
           "pl/pl_PL/darkman/medium/pl_PL-darkman-medium"),
    "uk": ("uk_UA-ukrainian_tts-medium.onnx",
           "uk/uk_UA/ukrainian_tts/medium/uk_UA-ukrainian_tts-medium"),
    "vi": ("vi_VN-vivos-x_low.onnx",
           "vi/vi_VN/vivos/x_low/vi_VN-vivos-x_low"),
    "ar": ("ar_JO-kareem-medium.onnx",
           "ar/ar_JO/kareem/medium/ar_JO-kareem-medium"),
    "tr": ("tr_TR-dfki-medium.onnx",
           "tr/tr_TR/dfki/medium/tr_TR-dfki-medium"),
    "nl": ("nl_NL-mls-medium.onnx",
           "nl/nl_NL/mls/medium/nl_NL-mls-medium"),
    "cs": ("cs_CZ-jirka-medium.onnx",
           "cs/cs_CZ/jirka/medium/cs_CZ-jirka-medium"),
    "fi": ("fi_FI-harri-medium.onnx",
           "fi/fi_FI/harri/medium/fi_FI-harri-medium"),
    "el": ("el_GR-rapunzelina-low.onnx",
           "el/el_GR/rapunzelina/low/el_GR-rapunzelina-low"),
    "hu": ("hu_HU-anna-medium.onnx",
           "hu/hu_HU/anna/medium/hu_HU-anna-medium"),
    "da": ("da_DK-talesyntese-medium.onnx",
           "da/da_DK/talesyntese/medium/da_DK-talesyntese-medium"),
    "no": ("no_NO-talesyntese-medium.onnx",
           "no/no_NO/talesyntese/medium/no_NO-talesyntese-medium"),
    "sv": ("sv_SE-nst-medium.onnx",
           "sv/sv_SE/nst/medium/sv_SE-nst-medium"),
    "ro": ("ro_RO-mihai-medium.onnx",
           "ro/ro_RO/mihai/medium/ro_RO-mihai-medium"),
    "ka": ("ka_GE-natia-medium.onnx",
           "ka/ka_GE/natia/medium/ka_GE-natia-medium"),
    "is": ("is_IS-bui-medium.onnx",
           "is/is_IS/bui/medium/is_IS-bui-medium"),
}

PIPER_HF_BASE = "https://huggingface.co/rhasspy/piper-voices/resolve/main"


def get_voice_model(lang: str) -> str:
    """
    Get the path to the Piper voice model for a language.
    Downloads it automatically if not present.

    Args:
        lang: Language code (e.g., "en", "ja", "fr")

    Returns:
        Path to the .onnx voice model file

    Raises:
        RuntimeError: If the language has no voice in the catalog
    """
    if lang not in VOICE_CATALOG:
        supported = ", ".join(sorted(VOICE_CATALOG.keys()))
        raise RuntimeError(
            f"No Piper TTS voice available for '{lang}'. "
            f"Supported languages: {supported}"
        )

    model_filename, hf_path = VOICE_CATALOG[lang]
    model_path = MODELS_DIR / model_filename
    config_path = MODELS_DIR / f"{model_filename}.json"

    if not model_path.is_file():
        print(f"[synthesize] Downloading voice model for '{lang}'...")
        os.makedirs(MODELS_DIR, exist_ok=True)

        for suffix, dest in [(".onnx", model_path), (".onnx.json", config_path)]:
            url = f"{PIPER_HF_BASE}/{hf_path}{suffix}"
            subprocess.run(
                ["curl", "-L", "-o", str(dest), url],
                check=True,
            )
        print(f"[synthesize] Voice model downloaded: {model_filename}")

    return str(model_path)


def synthesize_segments(
    segments: list[Segment],
    output_dir: str,
    voice_model: str = None,
    dest_lang: str = "en",
) -> list[dict]:
    """
    Generate TTS audio for each translated segment.

    Args:
        segments:     List of translated Segments
        output_dir:   Directory to save individual audio clips
        voice_model:  Path to Piper ONNX voice model (overrides dest_lang)
        dest_lang:    Destination language code — used to pick voice model

    Returns:
        List of dicts with keys: path, start, end, duration
        Each dict represents one audio clip ready for mixing.
    """
    if voice_model is None:
        voice_model = get_voice_model(dest_lang)

    if not os.path.isfile(voice_model):
        raise FileNotFoundError(
            f"Voice model not found: {voice_model}\n"
            f"Run setup.sh to download it."
        )

    clips_dir = os.path.join(output_dir, "clips")
    os.makedirs(clips_dir, exist_ok=True)

    print(f"[synthesize] Generating TTS for {len(segments)} segments")
    print(f"[synthesize] Voice model: {os.path.basename(voice_model)}")

    clips = []

    for i, seg in enumerate(segments):
        if not seg.text.strip():
            continue

        clip_path = os.path.join(clips_dir, f"clip_{i:04d}.wav")
        adjusted_path = os.path.join(clips_dir, f"clip_{i:04d}_adjusted.wav")

        # Generate raw TTS audio using Piper
        _generate_tts(seg.text, clip_path, voice_model)

        # Time-align: adjust speed to fit the original segment duration
        target_duration = seg.end - seg.start
        actual_duration = _get_audio_duration(clip_path)

        if actual_duration > 0 and target_duration > 0:
            speed_factor = actual_duration / target_duration
            # Clamp speed factor to reasonable range (0.5x to 2.0x)
            speed_factor = max(0.5, min(2.0, speed_factor))
            _adjust_speed(clip_path, adjusted_path, speed_factor)
            final_path = adjusted_path
        else:
            final_path = clip_path

        clips.append({
            "path": final_path,
            "start": seg.start,
            "end": seg.end,
            "text": seg.text,
            "duration": target_duration,
        })

        if (i + 1) % 10 == 0 or (i + 1) == len(segments):
            print(f"[synthesize] Progress: {i + 1}/{len(segments)}")

    print(f"[synthesize] Generated {len(clips)} audio clips")
    return clips


def _generate_tts(text: str, output_path: str, voice_model: str):
    """Generate speech audio from text using Piper."""
    # Piper reads text from stdin and writes WAV to the output file
    result = subprocess.run(
        [
            "piper",
            "--model", voice_model,
            "--output_file", output_path,
        ],
        input=text,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"Piper TTS failed: {result.stderr}")


def _get_audio_duration(audio_path: str) -> float:
    """Get duration of an audio file in seconds."""
    try:
        audio = AudioSegment.from_wav(audio_path)
        return len(audio) / 1000.0  # pydub uses milliseconds
    except Exception:
        return 0.0


def _adjust_speed(input_path: str, output_path: str, speed_factor: float):
    """
    Adjust audio playback speed using ffmpeg's atempo filter.

    atempo filter accepts values between 0.5 and 100.0.
    For extreme speed changes, we chain multiple atempo filters.

    speed_factor > 1.0 = faster (TTS is too long, speed it up)
    speed_factor < 1.0 = slower (TTS is too short, slow it down)
    """
    if abs(speed_factor - 1.0) < 0.05:
        # Close enough to 1.0, just copy
        import shutil
        shutil.copy2(input_path, output_path)
        return

    # Build atempo filter chain
    # atempo only accepts 0.5-100.0, so for < 0.5 we chain them
    filters = []
    remaining = speed_factor
    while remaining > 2.0:
        filters.append("atempo=2.0")
        remaining /= 2.0
    while remaining < 0.5:
        filters.append("atempo=0.5")
        remaining /= 0.5
    filters.append(f"atempo={remaining:.4f}")

    filter_str = ",".join(filters)

    subprocess.run(
        [
            "ffmpeg", "-y",
            "-i", input_path,
            "-filter:a", filter_str,
            "-acodec", "pcm_s16le",
            "-ar", "22050",
            output_path,
        ],
        capture_output=True,
        check=True,
    )
