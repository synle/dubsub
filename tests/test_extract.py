"""Tests for pipeline/extract.py — audio extraction."""

import pytest

from pipeline.extract import extract_audio


class TestExtractAudio:
    def test_file_not_found(self):
        with pytest.raises(FileNotFoundError):
            extract_audio("/nonexistent/video.mp4", "/tmp")
