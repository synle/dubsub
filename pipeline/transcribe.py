"""
Speech-to-text transcription using OpenAI Whisper.

What this does:
  Takes an audio file and converts speech to text WITH timestamps.
  This is critical because we need to know exactly WHEN each line
  is spoken so we can time-align the dubbed audio.

About Whisper:
  - Made by OpenAI, but runs 100% locally (no API calls)
  - Supports 99 languages including Japanese
  - Returns word-level and segment-level timestamps
  - Models range from 'tiny' (39MB) to 'large' (2.9GB)
  - We use 'base' (142MB) as a good speed/accuracy tradeoff

How segments work:
  Whisper breaks audio into segments like:
    [0.0s - 3.2s] "こんにちは、元気ですか？"
    [3.5s - 6.1s] "今日はいい天気ですね。"
  Each segment has a start time, end time, and the spoken text.
"""

import os
from dataclasses import dataclass

import whisper


@dataclass
class Segment:
    """A single segment of transcribed speech."""
    start: float   # Start time in seconds
    end: float     # End time in seconds
    text: str      # The transcribed text


def transcribe_audio(
    audio_path: str,
    language: str = "ja",
    model_size: str = "base"
) -> list[Segment]:
    """
    Transcribe audio to text with timestamps.

    Args:
        audio_path:  Path to WAV audio file
        language:    Language code (e.g., "ja" for Japanese)
        model_size:  Whisper model size: tiny, base, small, medium, large

    Returns:
        List of Segment objects with start/end times and text
    """
    if not os.path.isfile(audio_path):
        raise FileNotFoundError(f"Audio file not found: {audio_path}")

    print(f"[transcribe] Loading Whisper model: {model_size}")
    print(f"[transcribe] (First run will download the model - ~142MB for 'base')")

    # Load the Whisper model - downloads automatically on first use
    # Models are cached at ~/.cache/whisper/
    model = whisper.load_model(model_size)

    print(f"[transcribe] Transcribing audio ({language})...")
    print(f"[transcribe] This may take a while depending on video length...")

    # Run transcription
    # - language="ja" tells Whisper to expect Japanese
    # - verbose=False suppresses per-segment console output
    result = model.transcribe(
        audio_path,
        language=language,
        verbose=False,
    )

    # Convert Whisper's output to our Segment format
    segments = []
    for seg in result["segments"]:
        segments.append(Segment(
            start=seg["start"],
            end=seg["end"],
            text=seg["text"].strip(),
        ))

    print(f"[transcribe] Found {len(segments)} segments")
    # Show first few for preview
    for seg in segments[:5]:
        print(f"  [{seg.start:.1f}s - {seg.end:.1f}s] {seg.text}")
    if len(segments) > 5:
        print(f"  ... and {len(segments) - 5} more")

    return segments


def segments_from_subtitles(sub_path: str) -> list[Segment]:
    """
    Parse a subtitle file (SRT, ASS, SSA) into Segments.

    This is used when the user provides their own subtitle file,
    so we skip the Whisper transcription step entirely.

    Args:
        sub_path: Path to subtitle file (.srt, .ass, .ssa)

    Returns:
        List of Segment objects
    """
    import pysubs2

    if not os.path.isfile(sub_path):
        raise FileNotFoundError(f"Subtitle file not found: {sub_path}")

    print(f"[transcribe] Loading subtitles from: {sub_path}")

    subs = pysubs2.load(sub_path)
    segments = []

    for line in subs:
        # pysubs2 times are in milliseconds, convert to seconds
        # Skip comment lines and empty lines
        if line.is_comment or not line.text.strip():
            continue

        # Clean up subtitle text (remove formatting tags like {\i1} etc.)
        clean_text = line.plaintext.strip()
        if not clean_text:
            continue

        segments.append(Segment(
            start=line.start / 1000.0,
            end=line.end / 1000.0,
            text=clean_text,
        ))

    print(f"[transcribe] Loaded {len(segments)} subtitle lines")
    for seg in segments[:5]:
        print(f"  [{seg.start:.1f}s - {seg.end:.1f}s] {seg.text}")
    if len(segments) > 5:
        print(f"  ... and {len(segments) - 5} more")

    return segments
