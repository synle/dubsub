"""
Video composition - merge dubbed audio back into the video.

What this does:
  1. Takes all the individual TTS audio clips
  2. Mixes them onto a single audio timeline (matching original timestamps)
  3. Lowers the volume of the original audio (so you still hear music/SFX)
  4. Overlays the dubbed English speech on top
  5. Optionally burns translated subtitles into the video
  6. Exports the final dubbed video

The result:
  A video file where you hear the original background music and
  sound effects at lower volume, with English speech dubbed over
  the dialogue sections, and optional English subtitles.
"""

import os
import subprocess
import tempfile

from pydub import AudioSegment

from pipeline.transcribe import Segment


def compose_video(
    video_path: str,
    clips: list[dict],
    translated_segments: list[Segment],
    output_path: str,
    original_volume: float = 0.3,
    dub_volume: float = 1.0,
    burn_subtitles: bool = True,
):
    """
    Compose the final dubbed video.

    Args:
        video_path:           Path to the original video
        clips:                List of TTS clip dicts from synthesize step
        translated_segments:  Translated segments (for subtitle burning)
        output_path:          Where to save the final video
        original_volume:      Volume of original audio (0.0 to 1.0)
                              0.3 = 30% volume (keeps music/SFX audible)
        dub_volume:           Volume of dubbed speech (0.0 to 1.0)
        burn_subtitles:       Whether to burn subtitles into the video
    """
    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    work_dir = tempfile.mkdtemp(prefix="dubsub_")

    # -------------------------------------------------------
    # Step 1: Get original audio duration and create dub track
    # -------------------------------------------------------
    print("[compose] Building dubbed audio track...")

    # Get video duration to create a matching-length silent base
    duration_ms = _get_duration_ms(video_path)

    # Create a silent audio track the same length as the video
    dubbed_track = AudioSegment.silent(duration=duration_ms, frame_rate=22050)

    # Overlay each TTS clip at its correct timestamp
    for clip in clips:
        if not os.path.isfile(clip["path"]):
            continue

        try:
            tts_audio = AudioSegment.from_wav(clip["path"])

            # Adjust volume
            if dub_volume != 1.0:
                # Convert to dB: 0.5 volume ≈ -6dB, 2.0 volume ≈ +6dB
                import math
                db_change = 20 * math.log10(max(dub_volume, 0.01))
                tts_audio = tts_audio + db_change

            # Position the clip at its start timestamp
            position_ms = int(clip["start"] * 1000)

            # Make sure we don't go past the end
            if position_ms < duration_ms:
                dubbed_track = dubbed_track.overlay(tts_audio, position=position_ms)
        except Exception as e:
            print(f"  [warn] Could not overlay clip at {clip['start']:.1f}s: {e}")

    # Export the dubbed audio track
    dub_audio_path = os.path.join(work_dir, "dubbed_audio.wav")
    dubbed_track.export(dub_audio_path, format="wav")
    print(f"[compose] Dubbed audio track: {os.path.getsize(dub_audio_path) / 1024 / 1024:.1f} MB")

    # -------------------------------------------------------
    # Step 2: Generate subtitle file for burning
    # -------------------------------------------------------
    srt_path = None
    if burn_subtitles and translated_segments:
        srt_path = os.path.join(work_dir, "translated.srt")
        _write_srt(translated_segments, srt_path)
        print(f"[compose] Generated subtitle file: {srt_path}")

    # -------------------------------------------------------
    # Step 3: Use ffmpeg to combine everything
    # -------------------------------------------------------
    print("[compose] Combining video + dubbed audio...")

    # Build the ffmpeg command
    # We use the complex filter to:
    #   1. Take original audio and reduce its volume
    #   2. Mix it with our dubbed audio track
    #   3. Optionally burn subtitles
    #   4. Copy the video stream as-is (no re-encoding)

    vol_filter = f"volume={original_volume}"

    cmd = [
        "ffmpeg", "-y",
        "-i", video_path,           # Input 0: original video
        "-i", dub_audio_path,        # Input 1: dubbed audio
    ]

    # Build the audio filter
    # [0:a] = original audio, [1:a] = dubbed audio
    # amix combines them into one track
    filter_parts = [
        f"[0:a]{vol_filter}[orig];",          # Lower original volume
        "[orig][1:a]amix=inputs=2:duration=first:dropout_transition=2[aout]",
    ]

    if burn_subtitles and srt_path:
        # Add subtitle filter to the video stream
        # We need to escape the path for ffmpeg's subtitle filter
        escaped_srt = srt_path.replace("\\", "/").replace(":", "\\\\:")
        cmd.extend([
            "-filter_complex",
            "".join(filter_parts),
            "-vf", f"subtitles={escaped_srt}:force_style='FontSize=24,PrimaryColour=&H00FFFFFF,OutlineColour=&H00000000,Outline=2'",
        ])
    else:
        cmd.extend([
            "-filter_complex",
            "".join(filter_parts),
        ])

    cmd.extend([
        "-map", "0:v",               # Use video from input 0
        "-map", "[aout]",            # Use our mixed audio
        "-c:v", "libx264",           # Re-encode video (needed for subtitle burn)
        "-preset", "fast",            # Encoding speed
        "-crf", "23",                 # Quality (lower = better, 23 is default)
        "-c:a", "aac",               # AAC audio codec
        "-b:a", "192k",              # Audio bitrate
        output_path,
    ])

    print(f"[compose] Running ffmpeg...")
    result = subprocess.run(cmd, capture_output=True, text=True)

    if result.returncode != 0:
        print(f"[compose] ffmpeg stderr: {result.stderr[-500:]}")
        raise RuntimeError("ffmpeg failed to compose the final video")

    file_size = os.path.getsize(output_path) / (1024 * 1024)
    print(f"[compose] Done! Output: {output_path} ({file_size:.1f} MB)")

    return output_path


def _get_duration_ms(video_path: str) -> int:
    """Get video duration in milliseconds using ffprobe."""
    import ffmpeg as ff
    probe = ff.probe(video_path)
    duration = float(probe['format']['duration'])
    return int(duration * 1000)


def _write_srt(segments: list[Segment], output_path: str):
    """Write segments to an SRT subtitle file."""
    with open(output_path, 'w', encoding='utf-8') as f:
        for i, seg in enumerate(segments, 1):
            # SRT timestamp format: HH:MM:SS,mmm
            start_ts = _seconds_to_srt_time(seg.start)
            end_ts = _seconds_to_srt_time(seg.end)

            f.write(f"{i}\n")
            f.write(f"{start_ts} --> {end_ts}\n")
            f.write(f"{seg.text}\n")
            f.write("\n")


def _seconds_to_srt_time(seconds: float) -> str:
    """Convert seconds to SRT timestamp format (HH:MM:SS,mmm)."""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    millis = int((seconds % 1) * 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"
