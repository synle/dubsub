"""Tests for webui.py — FastAPI web UI endpoints and helpers."""

import json
import queue
import time
from io import StringIO
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from webui import OutputCapture, app, jobs


@pytest.fixture(autouse=True)
def _clear_jobs():
    """Reset job store between tests."""
    jobs.clear()
    yield
    jobs.clear()


@pytest.fixture()
def client(tmp_path):
    """TestClient with upload/output dirs pointed at tmp_path."""
    with (
        patch("webui.UPLOAD_DIR", tmp_path / "uploads"),
        patch("webui.OUTPUT_DIR", tmp_path / "output"),
    ):
        (tmp_path / "uploads").mkdir()
        (tmp_path / "output").mkdir()
        yield TestClient(app)


# ------------------------------------------------------------------
# OutputCapture unit tests
# ------------------------------------------------------------------

class TestOutputCapture:
    def test_complete_lines_forwarded(self):
        q = queue.Queue()
        cap = OutputCapture(q, StringIO())
        cap.write("hello world\n")
        assert q.get_nowait() == "hello world"

    def test_partial_lines_buffered(self):
        q = queue.Queue()
        cap = OutputCapture(q, StringIO())
        cap.write("partial")
        assert q.empty()
        cap.write(" line\n")
        assert q.get_nowait() == "partial line"

    def test_multiple_lines_in_one_write(self):
        q = queue.Queue()
        cap = OutputCapture(q, StringIO())
        cap.write("line1\nline2\nline3\n")
        assert q.get_nowait() == "line1"
        assert q.get_nowait() == "line2"
        assert q.get_nowait() == "line3"

    def test_blank_lines_skipped(self):
        q = queue.Queue()
        cap = OutputCapture(q, StringIO())
        cap.write("hello\n\n\nworld\n")
        assert q.get_nowait() == "hello"
        assert q.get_nowait() == "world"
        assert q.empty()

    def test_still_writes_to_original(self):
        q = queue.Queue()
        original = StringIO()
        cap = OutputCapture(q, original)
        cap.write("test\n")
        assert original.getvalue() == "test\n"


# ------------------------------------------------------------------
# GET / — index page
# ------------------------------------------------------------------

class TestIndexPage:
    def test_returns_html(self, client):
        resp = client.get("/")
        assert resp.status_code == 200
        assert "text/html" in resp.headers["content-type"]

    def test_contains_form(self, client):
        html = client.get("/").text
        assert "Start Dubbing" in html
        assert 'name="video"' in html
        assert 'name="src_lang"' in html
        assert 'name="dest_lang"' in html

    def test_contains_setup_hint(self, client):
        html = client.get("/").text
        assert "setup.sh" in html


# ------------------------------------------------------------------
# POST /api/jobs — upload and create job
# ------------------------------------------------------------------

class TestCreateJob:
    def test_upload_returns_job_id(self, client):
        with patch("webui.threading.Thread") as mock_thread:
            mock_thread.return_value.start = lambda: None
            resp = client.post(
                "/api/jobs",
                files={"video": ("test.mp4", b"fake video", "video/mp4")},
                data={"src_lang": "ja", "dest_lang": "en"},
            )
        assert resp.status_code == 200
        data = resp.json()
        assert "job_id" in data
        assert len(data["job_id"]) == 8

    def test_missing_video_returns_422(self, client):
        resp = client.post("/api/jobs", data={"src_lang": "ja"})
        assert resp.status_code == 422

    def test_saves_video_to_disk(self, client, tmp_path):
        with patch("webui.threading.Thread") as mock_thread:
            mock_thread.return_value.start = lambda: None
            resp = client.post(
                "/api/jobs",
                files={"video": ("my_video.mp4", b"video bytes", "video/mp4")},
            )
        job_id = resp.json()["job_id"]
        saved = tmp_path / "uploads" / job_id / "my_video.mp4"
        assert saved.is_file()
        assert saved.read_bytes() == b"video bytes"

    def test_saves_subtitle_file(self, client, tmp_path):
        with patch("webui.threading.Thread") as mock_thread:
            mock_thread.return_value.start = lambda: None
            resp = client.post(
                "/api/jobs",
                files={
                    "video": ("v.mp4", b"vid", "video/mp4"),
                    "subs": ("s.srt", b"sub content", "application/x-subrip"),
                },
            )
        job_id = resp.json()["job_id"]
        saved = tmp_path / "uploads" / job_id / "s.srt"
        assert saved.is_file()
        assert saved.read_bytes() == b"sub content"

    def test_default_form_values(self, client):
        """When only video is provided, defaults should apply."""
        with patch("webui.threading.Thread") as mock_thread:
            mock_thread.return_value.start = lambda: None
            resp = client.post(
                "/api/jobs",
                files={"video": ("v.mp4", b"vid", "video/mp4")},
            )
        assert resp.status_code == 200

    def test_custom_form_values_passed_to_thread(self, client):
        with patch("webui.threading.Thread") as mock_thread:
            mock_thread.return_value.start = lambda: None
            client.post(
                "/api/jobs",
                files={"video": ("v.mp4", b"vid", "video/mp4")},
                data={
                    "src_lang": "zh",
                    "dest_lang": "fr",
                    "whisper_model": "large",
                    "original_volume": "0.5",
                },
            )
        args = mock_thread.call_args
        # args are positional in the Thread call: (job_id, video_path, subs_path, src, dest, whisper, vol)
        thread_args = args.kwargs.get("args") or args[1].get("args")
        _, _, _, src, dest, whisper, vol = thread_args
        assert src == "zh"
        assert dest == "fr"
        assert whisper == "large"
        assert vol == 0.5


# ------------------------------------------------------------------
# GET /api/jobs/{job_id}/progress — SSE stream
# ------------------------------------------------------------------

class TestJobProgress:
    def test_unknown_job_returns_error_event(self, client):
        resp = client.get("/api/jobs/nonexistent/progress")
        assert resp.status_code == 200
        assert "Job not found" in resp.text

    def test_streams_progress_messages(self, client):
        q = queue.Queue()
        q.put("STEP 1/4: test")
        q.put("some detail")
        q.put(None)  # sentinel
        jobs["abc123"] = {
            "status": "done",
            "progress": q,
            "output_path": "/tmp/out.mp4",
            "error": None,
        }
        resp = client.get("/api/jobs/abc123/progress")
        lines = [l for l in resp.text.split("\n") if l.startswith("data:")]
        payloads = [json.loads(l.removeprefix("data:").strip()) for l in lines]

        types = [p["type"] for p in payloads]
        assert "progress" in types
        assert "done" in types

    def test_streams_error_on_failure(self, client):
        q = queue.Queue()
        q.put("STEP 1/4: start")
        q.put(None)
        jobs["err123"] = {
            "status": "error",
            "progress": q,
            "output_path": None,
            "error": "something broke",
        }
        resp = client.get("/api/jobs/err123/progress")
        assert "something broke" in resp.text


# ------------------------------------------------------------------
# GET /api/jobs/{job_id}/download
# ------------------------------------------------------------------

class TestDownload:
    def test_unknown_job_returns_404(self, client):
        resp = client.get("/api/jobs/nope/download")
        assert resp.status_code == 404

    def test_incomplete_job_returns_404(self, client):
        jobs["wip"] = {
            "status": "running",
            "progress": queue.Queue(),
            "output_path": None,
            "error": None,
        }
        resp = client.get("/api/jobs/wip/download")
        assert resp.status_code == 404

    def test_completed_job_returns_file(self, client, tmp_path):
        outfile = tmp_path / "output" / "result.mp4"
        outfile.parent.mkdir(parents=True, exist_ok=True)
        outfile.write_bytes(b"fake mp4 content")

        jobs["done1"] = {
            "status": "done",
            "progress": queue.Queue(),
            "output_path": str(outfile),
            "error": None,
        }
        resp = client.get("/api/jobs/done1/download")
        assert resp.status_code == 200
        assert resp.content == b"fake mp4 content"
        assert "video/mp4" in resp.headers["content-type"]
