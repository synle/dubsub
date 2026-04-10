"""Tests for pipeline/compose.py — SRT generation and time formatting."""

import os
import tempfile

from pipeline.compose import _seconds_to_srt_time, _write_srt
from pipeline.transcribe import Segment


class TestSecondsToSrtTime:
    def test_zero(self):
        assert _seconds_to_srt_time(0) == "00:00:00,000"

    def test_simple_seconds(self):
        assert _seconds_to_srt_time(5.0) == "00:00:05,000"

    def test_with_milliseconds(self):
        assert _seconds_to_srt_time(1.234) == "00:00:01,234"

    def test_minutes(self):
        assert _seconds_to_srt_time(65.5) == "00:01:05,500"

    def test_hours(self):
        assert _seconds_to_srt_time(3661.0) == "01:01:01,000"

    def test_large_value(self):
        # 2h 30m 45s + 678ms
        assert _seconds_to_srt_time(9045.0 + 0.678) in ("02:30:45,677", "02:30:45,678")

    def test_fractional_millis(self):
        # Should truncate, not round
        result = _seconds_to_srt_time(1.9999)
        assert result == "00:00:01,999"


class TestWriteSrt:
    def test_writes_valid_srt(self):
        segments = [
            Segment(start=0.0, end=2.5, text="Hello world"),
            Segment(start=3.0, end=5.0, text="How are you?"),
        ]

        with tempfile.NamedTemporaryFile(mode='w', suffix='.srt', delete=False) as f:
            path = f.name

        try:
            _write_srt(segments, path)

            with open(path, 'r', encoding='utf-8') as f:
                content = f.read()

            assert "1\n" in content
            assert "00:00:00,000 --> 00:00:02,500" in content
            assert "Hello world" in content
            assert "2\n" in content
            assert "00:00:03,000 --> 00:00:05,000" in content
            assert "How are you?" in content
        finally:
            os.unlink(path)

    def test_empty_segments(self):
        with tempfile.NamedTemporaryFile(mode='w', suffix='.srt', delete=False) as f:
            path = f.name

        try:
            _write_srt([], path)

            with open(path, 'r', encoding='utf-8') as f:
                content = f.read()

            assert content == ""
        finally:
            os.unlink(path)

    def test_unicode_text(self):
        segments = [
            Segment(start=0.0, end=1.0, text="こんにちは"),
        ]

        with tempfile.NamedTemporaryFile(mode='w', suffix='.srt', delete=False) as f:
            path = f.name

        try:
            _write_srt(segments, path)

            with open(path, 'r', encoding='utf-8') as f:
                content = f.read()

            assert "こんにちは" in content
        finally:
            os.unlink(path)
