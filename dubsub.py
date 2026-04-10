#!/usr/bin/env python3
"""
DubSub - Local Video Dubbing Pipeline
======================================

Takes a Japanese video and produces an English-dubbed version.

Two modes:
  1. WITH subtitles:  Parse subs → Translate → TTS → Compose
  2. WITHOUT subtitles: Extract audio → Whisper STT → Translate → TTS → Compose

Usage:
  # Auto-transcribe Japanese audio, translate, and dub to English
  python dubsub.py --input anime_episode.mp4

  # Use existing subtitle file (faster, skips transcription)
  python dubsub.py --input anime_episode.mp4 --subs episode.srt

  # Custom output location
  python dubsub.py --input anime_episode.mp4 --output my_dubbed_video.mp4

  # Adjust original audio volume (0.0 = mute, 1.0 = full)
  python dubsub.py --input anime_episode.mp4 --original-volume 0.2
"""

import argparse
import os
import sys
import time


def main():
    parser = argparse.ArgumentParser(
        description="DubSub - Local AI Video Dubbing",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python dubsub.py --input video.mp4
  python dubsub.py --input video.mp4 --subs subtitles.srt
  python dubsub.py --input video.mp4 --src-lang ja --dest-lang en
        """
    )

    parser.add_argument(
        "--input", "-i",
        required=True,
        help="Path to the input video file (MP4, MKV, AVI, etc.)"
    )
    parser.add_argument(
        "--subs", "-s",
        default=None,
        help="Path to subtitle file (SRT, ASS, SSA). If not provided, "
             "audio will be transcribed using Whisper."
    )
    parser.add_argument(
        "--output", "-o",
        default=None,
        help="Output video path (default: output/<input>_dubbed.mp4)"
    )
    parser.add_argument(
        "--src-lang",
        default="ja",
        help="Source language code (default: ja = Japanese)"
    )
    parser.add_argument(
        "--dest-lang",
        default="en",
        help="Destination language code (default: en = English)"
    )
    parser.add_argument(
        "--whisper-model",
        default="base",
        choices=["tiny", "base", "small", "medium", "large"],
        help="Whisper model size (default: base). Larger = more accurate but slower."
    )
    parser.add_argument(
        "--original-volume",
        type=float,
        default=0.3,
        help="Volume of original audio in output (0.0-1.0, default: 0.3)"
    )
    parser.add_argument(
        "--no-subtitles",
        action="store_true",
        help="Don't burn translated subtitles into the video"
    )

    args = parser.parse_args()

    # Validate input
    if not os.path.isfile(args.input):
        print(f"Error: Input file not found: {args.input}")
        sys.exit(1)

    if args.subs and not os.path.isfile(args.subs):
        print(f"Error: Subtitle file not found: {args.subs}")
        sys.exit(1)

    # Set default output path
    if args.output is None:
        base_name = os.path.splitext(os.path.basename(args.input))[0]
        args.output = os.path.join("output", f"{base_name}_dubbed.mp4")

    # Create working directory
    work_dir = os.path.join("output", "work")
    os.makedirs(work_dir, exist_ok=True)

    # =========================================================
    # Pipeline Start
    # =========================================================
    print()
    print("=" * 55)
    print("  DubSub - Local AI Video Dubbing")
    print("=" * 55)
    print(f"  Input:      {args.input}")
    print(f"  Subtitles:  {args.subs or '(auto-transcribe with Whisper)'}")
    print(f"  Languages:  {args.src_lang} → {args.dest_lang}")
    print(f"  Output:     {args.output}")
    print("=" * 55)
    print()

    total_start = time.time()

    # ---------------------------------------------------------
    # Step 1: Get text segments (from subtitles or transcription)
    # ---------------------------------------------------------
    if args.subs:
        # MODE 1: User provided subtitle file
        print("━" * 50)
        print("STEP 1/4: Loading subtitles")
        print("━" * 50)
        from pipeline.transcribe import segments_from_subtitles
        segments = segments_from_subtitles(args.subs)
    else:
        # MODE 2: No subtitles - extract audio and transcribe
        print("━" * 50)
        print("STEP 1/4: Extracting audio & transcribing")
        print("━" * 50)
        from pipeline.extract import extract_audio
        from pipeline.transcribe import transcribe_audio

        audio_path = extract_audio(args.input, work_dir)
        segments = transcribe_audio(
            audio_path,
            language=args.src_lang,
            model_size=args.whisper_model,
        )

    if not segments:
        print("Error: No speech segments found!")
        sys.exit(1)

    print(f"\n  → {len(segments)} segments found\n")

    # ---------------------------------------------------------
    # Step 2: Translate
    # ---------------------------------------------------------
    print("━" * 50)
    print(f"STEP 2/4: Translating ({args.src_lang} → {args.dest_lang})")
    print("━" * 50)
    from pipeline.translate import translate_segments

    translated = translate_segments(segments, args.src_lang, args.dest_lang)
    print(f"\n  → {len(translated)} segments translated\n")

    # ---------------------------------------------------------
    # Step 3: Text-to-Speech
    # ---------------------------------------------------------
    print("━" * 50)
    print("STEP 3/4: Generating dubbed speech (TTS)")
    print("━" * 50)
    from pipeline.synthesize import synthesize_segments

    clips = synthesize_segments(translated, work_dir, dest_lang=args.dest_lang)
    print(f"\n  → {len(clips)} audio clips generated\n")

    # ---------------------------------------------------------
    # Step 4: Compose final video
    # ---------------------------------------------------------
    print("━" * 50)
    print("STEP 4/4: Composing final video")
    print("━" * 50)
    from pipeline.compose import compose_video

    compose_video(
        video_path=args.input,
        clips=clips,
        translated_segments=translated,
        output_path=args.output,
        original_volume=args.original_volume,
        burn_subtitles=not args.no_subtitles,
    )

    # ---------------------------------------------------------
    # Done!
    # ---------------------------------------------------------
    total_time = time.time() - total_start
    minutes = int(total_time // 60)
    seconds = int(total_time % 60)

    print()
    print("=" * 55)
    print("  DONE!")
    print(f"  Output: {args.output}")
    print(f"  Time:   {minutes}m {seconds}s")
    print("=" * 55)
    print()


if __name__ == "__main__":
    main()
