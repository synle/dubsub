"""
Offline translation using Argos Translate.

What this does:
  Translates text from one language to another, completely offline.
  No internet connection or API keys needed after setup.

About Argos Translate:
  - Open-source, runs locally
  - Uses neural machine translation models
  - Supports 30+ languages
  - Models are ~100MB each (downloaded during setup)
  - Quality is decent - not Google Translate level, but good
    enough for dubbing where you hear the translation spoken

How it works:
  1. During setup.sh, we downloaded the ja→en translation model
  2. Here we load that model and translate each text segment
  3. Each segment is translated independently (no cross-segment context)
"""

from pipeline.transcribe import Segment

import argostranslate.translate


def translate_segments(
    segments: list[Segment],
    src_lang: str = "ja",
    dest_lang: str = "en",
) -> list[Segment]:
    """
    Translate all segments from source to destination language.

    Args:
        segments:   List of transcribed Segments with original text
        src_lang:   Source language code (e.g., "ja")
        dest_lang:  Destination language code (e.g., "en")

    Returns:
        New list of Segments with translated text (same timestamps)
    """
    print(f"[translate] Translating {len(segments)} segments: {src_lang} → {dest_lang}")

    # Get the installed translation languages
    installed_languages = argostranslate.translate.get_installed_languages()

    # Find source and destination language objects
    src = next((l for l in installed_languages if l.code == src_lang), None)
    dest = next((l for l in installed_languages if l.code == dest_lang), None)

    if src is None:
        raise RuntimeError(
            f"Source language '{src_lang}' not installed. "
            f"Available: {[l.code for l in installed_languages]}. "
            f"Run setup.sh to install language models."
        )
    if dest is None:
        raise RuntimeError(
            f"Destination language '{dest_lang}' not installed. "
            f"Available: {[l.code for l in installed_languages]}. "
            f"Run setup.sh to install language models."
        )

    # Get the translation function for this language pair
    translation = src.get_translation(dest)
    if translation is None:
        raise RuntimeError(
            f"No translation model found for {src_lang} → {dest_lang}. "
            f"Run setup.sh to install it."
        )

    translated_segments = []
    for i, seg in enumerate(segments):
        # Translate the text
        translated_text = translation.translate(seg.text)

        translated_segments.append(Segment(
            start=seg.start,
            end=seg.end,
            text=translated_text,
        ))

        # Progress indicator every 10 segments
        if (i + 1) % 10 == 0 or (i + 1) == len(segments):
            print(f"[translate] Progress: {i + 1}/{len(segments)}")

    # Show some examples
    print(f"[translate] Translation examples:")
    for orig, trans in zip(segments[:3], translated_segments[:3]):
        print(f"  {orig.text}")
        print(f"  → {trans.text}")
        print()

    return translated_segments
