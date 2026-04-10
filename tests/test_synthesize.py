"""Tests for pipeline/synthesize.py — TTS synthesis logic."""

import shutil
import tempfile
from unittest.mock import patch, MagicMock

import pytest

from pipeline.synthesize import _adjust_speed, get_voice_model, VOICE_CATALOG
from pipeline.transcribe import Segment


class TestAdjustSpeed:
    def test_near_1x_copies_file(self, tmp_path):
        """Speed factor close to 1.0 should just copy the file."""
        src = tmp_path / "input.wav"
        dst = tmp_path / "output.wav"
        src.write_bytes(b"fake wav data")

        _adjust_speed(str(src), str(dst), 1.02)

        assert dst.read_bytes() == b"fake wav data"

    def test_exactly_1x_copies_file(self, tmp_path):
        src = tmp_path / "input.wav"
        dst = tmp_path / "output.wav"
        src.write_bytes(b"fake wav data")

        _adjust_speed(str(src), str(dst), 1.0)

        assert dst.read_bytes() == b"fake wav data"


class TestVoiceCatalog:
    def test_catalog_has_common_languages(self):
        for lang in ["en", "ja", "zh", "ko", "es", "fr", "de"]:
            assert lang in VOICE_CATALOG, f"Missing voice for '{lang}'"

    def test_catalog_entries_have_required_fields(self):
        for lang, (filename, hf_path) in VOICE_CATALOG.items():
            assert filename.endswith(".onnx"), f"{lang}: model must be .onnx"
            assert "/" in hf_path, f"{lang}: hf_path must have slashes"

    def test_unsupported_language_raises(self):
        with pytest.raises(RuntimeError, match="No Piper TTS voice"):
            get_voice_model("xx")

    def test_get_voice_model_downloads_if_missing(self, tmp_path):
        """Should call curl to download when model file doesn't exist."""
        model_filename = VOICE_CATALOG["fr"][0]

        def fake_curl(*args, **kwargs):
            """Simulate curl writing the model file."""
            # Find the -o arg to know where to write
            cmd = args[0] if args else kwargs.get("args", [])
            if "-o" in cmd:
                dest = cmd[cmd.index("-o") + 1]
                with open(dest, "wb") as f:
                    f.write(b"fake model")
            return MagicMock(returncode=0)

        with patch("pipeline.synthesize.MODELS_DIR", tmp_path):
            with patch("subprocess.run", side_effect=fake_curl) as mock_run:
                path = get_voice_model("fr")
                assert "fr" in path
                assert mock_run.called


class TestSynthesizeSegments:
    def test_voice_model_not_found(self):
        from pipeline.synthesize import synthesize_segments

        with pytest.raises(FileNotFoundError, match="Voice model not found"):
            synthesize_segments(
                [Segment(start=0, end=1, text="test")],
                "/tmp",
                voice_model="/nonexistent/model.onnx",
            )

    def test_skips_empty_text(self, tmp_path):
        """Segments with empty text should be skipped."""
        from pipeline.synthesize import synthesize_segments

        # Create a fake model file so it passes the file check
        model = tmp_path / "fake.onnx"
        model.write_bytes(b"fake")

        segments = [
            Segment(start=0, end=1, text=""),
            Segment(start=1, end=2, text="   "),
        ]

        with patch("pipeline.synthesize._generate_tts") as mock_tts:
            clips = synthesize_segments(segments, str(tmp_path), str(model))
            mock_tts.assert_not_called()
            assert len(clips) == 0
