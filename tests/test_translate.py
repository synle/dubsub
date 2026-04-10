"""Tests for pipeline/translate.py — translation with mocked Argos."""

from unittest.mock import MagicMock, patch

import pytest

from pipeline.transcribe import Segment
from pipeline.translate import translate_segments


class TestTranslateSegments:
    def _mock_argos(self):
        """Set up mocked Argos Translate that returns reversed text."""
        mock_ja = MagicMock()
        mock_ja.code = "ja"
        mock_en = MagicMock()
        mock_en.code = "en"

        mock_translation = MagicMock()
        mock_translation.translate = lambda text: f"[translated] {text}"

        mock_ja.get_translation.return_value = mock_translation

        return [mock_ja, mock_en]

    @patch("pipeline.translate.argostranslate.translate.get_installed_languages")
    def test_translates_all_segments(self, mock_get_langs):
        mock_get_langs.return_value = self._mock_argos()

        segments = [
            Segment(start=0.0, end=1.0, text="こんにちは"),
            Segment(start=2.0, end=3.0, text="さようなら"),
        ]

        result = translate_segments(segments, "ja", "en")

        assert len(result) == 2
        assert result[0].text == "[translated] こんにちは"
        assert result[1].text == "[translated] さようなら"

    @patch("pipeline.translate.argostranslate.translate.get_installed_languages")
    def test_preserves_timestamps(self, mock_get_langs):
        mock_get_langs.return_value = self._mock_argos()

        segments = [
            Segment(start=1.5, end=4.2, text="test"),
        ]

        result = translate_segments(segments, "ja", "en")

        assert result[0].start == 1.5
        assert result[0].end == 4.2

    @patch("pipeline.translate.argostranslate.translate.get_installed_languages")
    def test_missing_source_language(self, mock_get_langs):
        mock_get_langs.return_value = self._mock_argos()

        with pytest.raises(RuntimeError, match="Source language 'ko' not installed"):
            translate_segments(
                [Segment(start=0, end=1, text="test")],
                "ko", "en"
            )

    @patch("pipeline.translate.argostranslate.translate.get_installed_languages")
    def test_missing_dest_language(self, mock_get_langs):
        mock_get_langs.return_value = self._mock_argos()

        with pytest.raises(RuntimeError, match="Destination language 'fr' not installed"):
            translate_segments(
                [Segment(start=0, end=1, text="test")],
                "ja", "fr"
            )

    @patch("pipeline.translate.argostranslate.translate.get_installed_languages")
    def test_no_translation_model(self, mock_get_langs):
        mock_ja = MagicMock()
        mock_ja.code = "ja"
        mock_en = MagicMock()
        mock_en.code = "en"
        mock_ja.get_translation.return_value = None
        mock_get_langs.return_value = [mock_ja, mock_en]

        with pytest.raises(RuntimeError, match="No translation model found"):
            translate_segments(
                [Segment(start=0, end=1, text="test")],
                "ja", "en"
            )

    @patch("pipeline.translate.argostranslate.translate.get_installed_languages")
    def test_empty_segments(self, mock_get_langs):
        mock_get_langs.return_value = self._mock_argos()

        result = translate_segments([], "ja", "en")
        assert result == []
