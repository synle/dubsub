"""Tests for pipeline/transcribe.py — Segment dataclass and subtitle parsing."""

import os
import tempfile

import pytest

from pipeline.transcribe import Segment, segments_from_subtitles


class TestSegment:
    def test_creation(self):
        seg = Segment(start=1.0, end=2.5, text="hello")
        assert seg.start == 1.0
        assert seg.end == 2.5
        assert seg.text == "hello"

    def test_duration(self):
        seg = Segment(start=1.0, end=3.5, text="test")
        assert seg.end - seg.start == 2.5

    def test_equality(self):
        a = Segment(start=0.0, end=1.0, text="same")
        b = Segment(start=0.0, end=1.0, text="same")
        assert a == b

    def test_inequality(self):
        a = Segment(start=0.0, end=1.0, text="one")
        b = Segment(start=0.0, end=1.0, text="two")
        assert a != b


class TestSegmentsFromSubtitles:
    def _write_srt(self, content: str) -> str:
        """Helper to write a temporary SRT file."""
        f = tempfile.NamedTemporaryFile(
            mode='w', suffix='.srt', delete=False, encoding='utf-8'
        )
        f.write(content)
        f.close()
        return f.name

    def test_basic_srt(self):
        srt_content = (
            "1\n"
            "00:00:01,000 --> 00:00:03,000\n"
            "Hello world\n"
            "\n"
            "2\n"
            "00:00:04,000 --> 00:00:06,500\n"
            "How are you?\n"
            "\n"
        )
        path = self._write_srt(srt_content)

        try:
            segments = segments_from_subtitles(path)
            assert len(segments) == 2
            assert segments[0].text == "Hello world"
            assert segments[0].start == 1.0
            assert segments[0].end == 3.0
            assert segments[1].text == "How are you?"
            assert segments[1].start == 4.0
            assert segments[1].end == 6.5
        finally:
            os.unlink(path)

    def test_japanese_srt(self):
        srt_content = (
            "1\n"
            "00:00:00,000 --> 00:00:02,000\n"
            "こんにちは\n"
            "\n"
            "2\n"
            "00:00:03,000 --> 00:00:05,000\n"
            "元気ですか？\n"
            "\n"
        )
        path = self._write_srt(srt_content)

        try:
            segments = segments_from_subtitles(path)
            assert len(segments) == 2
            assert segments[0].text == "こんにちは"
            assert segments[1].text == "元気ですか？"
        finally:
            os.unlink(path)

    def test_skips_empty_lines(self):
        srt_content = (
            "1\n"
            "00:00:01,000 --> 00:00:02,000\n"
            "Real line\n"
            "\n"
            "2\n"
            "00:00:03,000 --> 00:00:04,000\n"
            "   \n"
            "\n"
        )
        path = self._write_srt(srt_content)

        try:
            segments = segments_from_subtitles(path)
            assert len(segments) == 1
            assert segments[0].text == "Real line"
        finally:
            os.unlink(path)

    def test_file_not_found(self):
        with pytest.raises(FileNotFoundError):
            segments_from_subtitles("/nonexistent/file.srt")


class TestTranscribeAudio:
    def test_file_not_found(self):
        from pipeline.transcribe import transcribe_audio
        with pytest.raises(FileNotFoundError):
            transcribe_audio("/nonexistent/audio.wav")
