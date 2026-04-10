"""
Extract audio from video files using ffmpeg.

What this does:
  Takes a video file (MP4, MKV, etc.) and pulls out just the audio track
  as a WAV file. WAV is uncompressed, which is what Whisper needs for
  accurate speech recognition.

How it works:
  Uses ffmpeg under the hood. ffmpeg is the industry-standard tool for
  video/audio processing. The ffmpeg-python library gives us a clean
  Python interface to it.
"""

import os
import subprocess
import ffmpeg


def extract_audio(video_path: str, output_dir: str) -> str:
    """
    Extract the audio track from a video file.

    Args:
        video_path: Path to the input video file
        output_dir: Directory to save the extracted audio

    Returns:
        Path to the extracted WAV file
    """
    if not os.path.isfile(video_path):
        raise FileNotFoundError(f"Video not found: {video_path}")

    os.makedirs(output_dir, exist_ok=True)

    # Name the output file based on the video name
    base_name = os.path.splitext(os.path.basename(video_path))[0]
    audio_path = os.path.join(output_dir, f"{base_name}_audio.wav")

    print(f"[extract] Extracting audio from: {video_path}")
    print(f"[extract] Saving to: {audio_path}")

    # ffmpeg command breakdown:
    #   -i input.mp4        : input file
    #   -vn                  : no video (audio only)
    #   -acodec pcm_s16le   : uncompressed 16-bit WAV
    #   -ar 16000            : 16kHz sample rate (what Whisper expects)
    #   -ac 1                : mono channel (Whisper works best with mono)
    #   -y                   : overwrite output if it exists
    try:
        (
            ffmpeg
            .input(video_path)
            .output(
                audio_path,
                vn=None,          # no video
                acodec='pcm_s16le',  # WAV format
                ar=16000,         # 16kHz for Whisper
                ac=1,             # mono
            )
            .overwrite_output()
            .run(quiet=True)
        )
    except ffmpeg.Error as e:
        raise RuntimeError(f"ffmpeg failed to extract audio: {e.stderr}")

    file_size = os.path.getsize(audio_path) / (1024 * 1024)
    print(f"[extract] Done! Audio file: {file_size:.1f} MB")

    return audio_path


def get_video_duration(video_path: str) -> float:
    """Get the duration of a video in seconds."""
    probe = ffmpeg.probe(video_path)
    duration = float(probe['format']['duration'])
    return duration
