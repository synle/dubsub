"""Tests for dubsub.py — CLI argument parsing and validation."""

import sys
from unittest.mock import patch

import pytest


class TestCLIParsing:
    def test_missing_input_exits(self):
        """Running with no args should exit with error."""
        with patch("sys.argv", ["dubsub.py"]):
            with pytest.raises(SystemExit) as exc:
                from dubsub import main
                main()
            assert exc.value.code == 2  # argparse error code

    def test_nonexistent_input_exits(self):
        """Pointing to a missing file should exit with code 1."""
        with patch("sys.argv", ["dubsub.py", "--input", "/nonexistent/video.mp4"]):
            with pytest.raises(SystemExit) as exc:
                from dubsub import main
                main()
            assert exc.value.code == 1

    def test_nonexistent_subs_exits(self, tmp_path):
        """Valid video but missing subtitle file should exit."""
        video = tmp_path / "video.mp4"
        video.write_bytes(b"fake video")

        with patch("sys.argv", [
            "dubsub.py",
            "--input", str(video),
            "--subs", "/nonexistent/subs.srt",
        ]):
            with pytest.raises(SystemExit) as exc:
                from dubsub import main
                main()
            assert exc.value.code == 1
