"""
DubSub Web UI
=============
Simple FastAPI interface for the video dubbing pipeline.
Provides file upload, real-time progress streaming via SSE, and download.

Run with:
    uv run python webui.py
"""

import asyncio
import io
import json
import os
import queue
import sys
import threading
import time
import uuid
from pathlib import Path

from fastapi import FastAPI, File, Form, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, StreamingResponse
import uvicorn

app = FastAPI(title="DubSub")

UPLOAD_DIR = Path("uploads")
OUTPUT_DIR = Path("output")

# In-memory job store
jobs: dict = {}


class OutputCapture(io.TextIOBase):
    """Intercepts stdout writes and forwards complete lines to a queue."""

    def __init__(self, progress_queue: queue.Queue, original):
        self.queue = progress_queue
        self.original = original
        self._buffer = ""

    def write(self, text):
        self.original.write(text)
        self._buffer += text
        while "\n" in self._buffer:
            line, self._buffer = self._buffer.split("\n", 1)
            stripped = line.strip()
            if stripped:
                self.queue.put(stripped)
        return len(text)

    def flush(self):
        self.original.flush()


def run_pipeline(job_id: str, video_path: str, subs_path: str | None,
                 src_lang: str, dest_lang: str, whisper_model: str,
                 original_volume: float):
    """Run the full dubbing pipeline in a background thread."""
    job = jobs[job_id]
    progress: queue.Queue = job["progress"]

    # Capture stdout so pipeline print() calls stream to the client
    capture = OutputCapture(progress, sys.__stdout__)
    sys.stdout = capture

    try:
        work_dir = str(OUTPUT_DIR / "work" / job_id)
        os.makedirs(work_dir, exist_ok=True)

        stem = Path(video_path).stem
        output_path = str(OUTPUT_DIR / f"{stem}_{job_id}_dubbed.mp4")

        total_start = time.time()

        # -- Step 1: Get segments --
        progress.put("STEP 1/4: Getting text segments...")
        if subs_path:
            from pipeline.transcribe import segments_from_subtitles
            segments = segments_from_subtitles(subs_path)
        else:
            from pipeline.extract import extract_audio
            from pipeline.transcribe import transcribe_audio
            audio_path = extract_audio(video_path, work_dir)
            segments = transcribe_audio(audio_path, language=src_lang,
                                        model_size=whisper_model)

        if not segments:
            raise RuntimeError("No speech segments found in the input.")

        progress.put(f"  Found {len(segments)} segments")

        # -- Step 2: Translate --
        progress.put(f"STEP 2/4: Translating ({src_lang} -> {dest_lang})...")
        from pipeline.translate import translate_segments
        translated = translate_segments(segments, src_lang, dest_lang)
        progress.put(f"  {len(translated)} segments translated")

        # -- Step 3: TTS --
        progress.put("STEP 3/4: Generating dubbed speech (TTS)...")
        from pipeline.synthesize import synthesize_segments
        clips = synthesize_segments(translated, work_dir, dest_lang=dest_lang)
        progress.put(f"  {len(clips)} audio clips generated")

        # -- Step 4: Compose --
        progress.put("STEP 4/4: Composing final video...")
        from pipeline.compose import compose_video
        compose_video(
            video_path=video_path,
            clips=clips,
            translated_segments=translated,
            output_path=output_path,
            original_volume=original_volume,
            burn_subtitles=True,
        )

        elapsed = time.time() - total_start
        minutes, seconds = int(elapsed // 60), int(elapsed % 60)
        progress.put(f"Done! Completed in {minutes}m {seconds}s")

        job["status"] = "done"
        job["output_path"] = output_path

    except Exception as e:
        job["status"] = "error"
        job["error"] = str(e)
        progress.put(f"ERROR: {e}")
    finally:
        sys.stdout = sys.__stdout__
        progress.put(None)  # sentinel — signals end of stream


# ---------------------------------------------------------------------------
# API endpoints
# ---------------------------------------------------------------------------

@app.post("/api/jobs")
async def create_job(
    video: UploadFile = File(...),
    subs: UploadFile | None = File(None),
    src_lang: str = Form("ja"),
    dest_lang: str = Form("en"),
    whisper_model: str = Form("base"),
    original_volume: float = Form(0.3),
):
    job_id = uuid.uuid4().hex[:8]

    # Save uploaded video
    upload_dir = UPLOAD_DIR / job_id
    upload_dir.mkdir(parents=True, exist_ok=True)

    video_path = str(upload_dir / video.filename)
    with open(video_path, "wb") as f:
        while chunk := await video.read(1024 * 1024):
            f.write(chunk)

    # Save subtitle file if provided
    subs_path = None
    if subs and subs.filename:
        subs_path = str(upload_dir / subs.filename)
        with open(subs_path, "wb") as f:
            while chunk := await subs.read(1024 * 1024):
                f.write(chunk)

    # Create job record
    jobs[job_id] = {
        "status": "running",
        "progress": queue.Queue(),
        "output_path": None,
        "error": None,
    }

    # Run pipeline in background thread
    threading.Thread(
        target=run_pipeline,
        args=(job_id, video_path, subs_path, src_lang, dest_lang,
              whisper_model, original_volume),
        daemon=True,
    ).start()

    return {"job_id": job_id}


@app.get("/api/jobs/{job_id}/progress")
async def job_progress(job_id: str):
    if job_id not in jobs:
        return StreamingResponse(
            iter([f"data: {json.dumps({'type': 'error', 'message': 'Job not found'})}\n\n"]),
            media_type="text/event-stream",
        )

    async def event_stream():
        job = jobs[job_id]
        while True:
            try:
                msg = job["progress"].get_nowait()
                if msg is None:
                    # Pipeline finished
                    if job["status"] == "error":
                        yield f"data: {json.dumps({'type': 'error', 'message': job['error']})}\n\n"
                    else:
                        yield f"data: {json.dumps({'type': 'done'})}\n\n"
                    return
                yield f"data: {json.dumps({'type': 'progress', 'message': msg})}\n\n"
            except queue.Empty:
                # Send a keep-alive comment so the connection doesn't drop
                yield ": heartbeat\n\n"
                await asyncio.sleep(0.5)

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@app.get("/api/jobs/{job_id}/download")
async def download(job_id: str):
    job = jobs.get(job_id)
    if not job or job["status"] != "done" or not job["output_path"]:
        return HTMLResponse("Job not ready", status_code=404)
    return FileResponse(
        job["output_path"],
        media_type="video/mp4",
        filename=Path(job["output_path"]).name,
    )


# ---------------------------------------------------------------------------
# Frontend — single embedded HTML page
# ---------------------------------------------------------------------------

@app.get("/", response_class=HTMLResponse)
async def index():
    return HTML_PAGE


HTML_PAGE = """\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>DubSub</title>
<style>
  :root {
    --bg: #0f1117; --surface: #1a1d2e; --border: #2a2d3e;
    --text: #e0e0e0; --muted: #888; --accent: #e94560;
    --accent-hover: #d13a54; --success: #4ecca3;
  }
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body {
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    background: var(--bg); color: var(--text);
    display: flex; justify-content: center; padding: 2rem 1rem;
    min-height: 100vh;
  }
  .container { max-width: 660px; width: 100%; }
  h1 { font-size: 1.6rem; margin-bottom: 0.25rem; }
  .tagline { color: var(--muted); margin-bottom: 1.8rem; font-size: 0.95rem; }
  .form-group { margin-bottom: 1rem; }
  label { display: block; margin-bottom: 0.3rem; font-size: 0.85rem; color: var(--muted); }
  input[type="file"], input[type="text"], input:not([type]), select {
    width: 100%; padding: 0.55rem 0.6rem;
    background: var(--surface); border: 1px solid var(--border);
    color: var(--text); border-radius: 6px; font-size: 0.9rem;
  }
  input[type="file"] { cursor: pointer; }
  select { appearance: auto; }
  .row { display: flex; gap: 1rem; }
  .row > .form-group { flex: 1; }
  .hint {
    font-size: 0.78rem; color: #666; margin-top: 0.3rem;
  }
  .hint code {
    background: var(--surface); padding: 0.15rem 0.4rem; border-radius: 3px;
    font-size: 0.78rem;
  }
  .range-wrap { display: flex; align-items: center; gap: 0.6rem; }
  .range-wrap input[type="range"] { flex: 1; accent-color: var(--accent); }
  .range-wrap .val {
    font-family: monospace; font-size: 0.85rem; min-width: 2.2rem; text-align: right;
  }
  button[type="submit"] {
    background: var(--accent); color: #fff; border: none;
    padding: 0.75rem 1.6rem; border-radius: 6px;
    cursor: pointer; font-size: 0.95rem; font-weight: 600;
    width: 100%; margin-top: 0.6rem; transition: background 0.15s;
  }
  button[type="submit"]:hover { background: var(--accent-hover); }
  button[type="submit"]:disabled { background: #444; cursor: not-allowed; }

  /* Progress section */
  #progress-section { display: none; margin-top: 2rem; }
  #progress-section h2 { font-size: 1.1rem; margin-bottom: 0.6rem; }
  #progress-log {
    background: #090b10; border: 1px solid var(--border); border-radius: 6px;
    padding: 0.8rem 1rem; font-family: "SF Mono", "Fira Code", "Consolas", monospace;
    font-size: 0.8rem; line-height: 1.6; height: 360px;
    overflow-y: auto; white-space: pre-wrap; word-break: break-word;
  }
  .line { color: #aaa; }
  .line.step { color: var(--accent); font-weight: 700; }
  .line.done { color: var(--success); font-weight: 700; }
  .line.error { color: #ff6b6b; font-weight: 700; }

  #download-btn {
    display: none; margin-top: 1rem; text-align: center;
  }
  #download-btn a {
    display: inline-block; background: var(--success); color: #0f1117;
    text-decoration: none; font-weight: 700; font-size: 0.95rem;
    padding: 0.7rem 2rem; border-radius: 6px; transition: background 0.15s;
  }
  #download-btn a:hover { background: #3db890; }
</style>
</head>
<body>
<div class="container">
  <h1>DubSub</h1>
  <p class="tagline">Local AI-powered video dubbing</p>

  <form id="form">
    <div class="form-group">
      <label for="video">Video file</label>
      <input id="video" type="file" name="video" accept="video/*" required>
    </div>
    <div class="form-group">
      <label for="subs">Subtitle file <span style="color:#666">(optional &mdash; skips transcription)</span></label>
      <input id="subs" type="file" name="subs" accept=".srt,.ass,.ssa">
    </div>
    <div class="row">
      <div class="form-group">
        <label for="src_lang">Source language</label>
        <input id="src_lang" name="src_lang" list="src-langs" value="ja" placeholder="e.g. ja">
        <datalist id="src-langs">
          <option value="ja">Japanese</option>
          <option value="zh">Chinese</option>
          <option value="ko">Korean</option>
          <option value="en">English</option>
          <option value="fr">French</option>
          <option value="de">German</option>
          <option value="es">Spanish</option>
          <option value="pt">Portuguese</option>
          <option value="ru">Russian</option>
          <option value="it">Italian</option>
          <option value="ar">Arabic</option>
          <option value="hi">Hindi</option>
          <option value="th">Thai</option>
          <option value="vi">Vietnamese</option>
          <option value="id">Indonesian</option>
          <option value="tr">Turkish</option>
          <option value="pl">Polish</option>
          <option value="nl">Dutch</option>
          <option value="sv">Swedish</option>
          <option value="uk">Ukrainian</option>
        </datalist>
      </div>
      <div class="form-group">
        <label for="dest_lang">Destination language</label>
        <input id="dest_lang" name="dest_lang" list="dest-langs" value="en" placeholder="e.g. en">
        <datalist id="dest-langs">
          <option value="en">English</option>
          <option value="ja">Japanese</option>
          <option value="zh">Chinese</option>
          <option value="ko">Korean</option>
          <option value="fr">French</option>
          <option value="de">German</option>
          <option value="es">Spanish</option>
          <option value="pt">Portuguese</option>
          <option value="ru">Russian</option>
          <option value="it">Italian</option>
          <option value="ar">Arabic</option>
          <option value="pl">Polish</option>
          <option value="uk">Ukrainian</option>
          <option value="vi">Vietnamese</option>
          <option value="tr">Turkish</option>
          <option value="nl">Dutch</option>
          <option value="cs">Czech</option>
          <option value="fi">Finnish</option>
          <option value="el">Greek</option>
          <option value="hu">Hungarian</option>
          <option value="da">Danish</option>
          <option value="no">Norwegian</option>
          <option value="sv">Swedish</option>
          <option value="ro">Romanian</option>
          <option value="ka">Georgian</option>
          <option value="is">Icelandic</option>
        </datalist>
      </div>
    </div>
    <p class="hint">Language pair must be set up first: <code>./setup.sh &lt;src&gt; &lt;dest&gt;</code></p>
    <div class="row">
      <div class="form-group">
        <label for="whisper_model">Whisper model</label>
        <select id="whisper_model" name="whisper_model">
          <option value="tiny">Tiny (fastest)</option>
          <option value="base" selected>Base (balanced)</option>
          <option value="small">Small</option>
          <option value="medium">Medium</option>
          <option value="large">Large (most accurate)</option>
        </select>
      </div>
      <div class="form-group">
        <label>Original audio volume</label>
        <div class="range-wrap">
          <input type="range" name="original_volume" min="0" max="1" step="0.05" value="0.30">
          <span class="val" id="vol-val">0.30</span>
        </div>
      </div>
    </div>
    <button type="submit">Start Dubbing</button>
  </form>

  <div id="progress-section">
    <h2>Progress</h2>
    <div id="progress-log"></div>
    <div id="download-btn"><a href="#">Download dubbed video</a></div>
  </div>
</div>

<script>
const form     = document.getElementById('form');
const logEl    = document.getElementById('progress-log');
const section  = document.getElementById('progress-section');
const dlBtn    = document.getElementById('download-btn');
const volRange = document.querySelector('[name=original_volume]');
const volVal   = document.getElementById('vol-val');

volRange.addEventListener('input', () => volVal.textContent = parseFloat(volRange.value).toFixed(2));

function addLine(text, cls) {
  const d = document.createElement('div');
  d.className = 'line' + (cls ? ' ' + cls : '');
  d.textContent = text;
  logEl.appendChild(d);
  logEl.scrollTop = logEl.scrollHeight;
}

form.addEventListener('submit', async (e) => {
  e.preventDefault();
  const btn = form.querySelector('button[type=submit]');
  btn.disabled = true;
  btn.textContent = 'Uploading...';
  section.style.display = 'block';
  logEl.innerHTML = '';
  dlBtn.style.display = 'none';

  const fd = new FormData(form);

  try {
    const res = await fetch('/api/jobs', { method: 'POST', body: fd });
    if (!res.ok) throw new Error('Upload failed: ' + res.statusText);
    const { job_id } = await res.json();

    btn.textContent = 'Processing...';
    addLine('Upload complete. Pipeline started.', 'step');

    /* Stream progress via SSE (using fetch + ReadableStream for clean close) */
    const sse = await fetch('/api/jobs/' + job_id + '/progress');
    const reader = sse.body.getReader();
    const decoder = new TextDecoder();
    let buf = '';

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buf += decoder.decode(value, { stream: true });

      const parts = buf.split('\\n');
      buf = parts.pop();

      for (const part of parts) {
        const trimmed = part.trim();
        if (!trimmed || trimmed.startsWith(':')) continue;        /* skip heartbeats */
        if (!trimmed.startsWith('data:')) continue;

        let payload;
        try { payload = JSON.parse(trimmed.slice(5).trim()); } catch { continue; }

        if (payload.type === 'progress') {
          let cls = '';
          if (payload.message.startsWith('STEP')) cls = 'step';
          else if (payload.message.startsWith('Done!')) cls = 'done';
          else if (payload.message.startsWith('ERROR')) cls = 'error';
          addLine(payload.message, cls);
        } else if (payload.type === 'done') {
          addLine('Video ready for download.', 'done');
          dlBtn.style.display = 'block';
          dlBtn.querySelector('a').href = '/api/jobs/' + job_id + '/download';
          break;
        } else if (payload.type === 'error') {
          addLine('Error: ' + payload.message, 'error');
          break;
        }
      }
    }
  } catch (err) {
    addLine('Error: ' + err.message, 'error');
  } finally {
    btn.disabled = false;
    btn.textContent = 'Start Dubbing';
  }
});
</script>
</body>
</html>
"""


if __name__ == "__main__":
    UPLOAD_DIR.mkdir(exist_ok=True)
    OUTPUT_DIR.mkdir(exist_ok=True)
    print("\n  DubSub Web UI: http://localhost:8000\n")
    uvicorn.run(app, host="0.0.0.0", port=8000)
