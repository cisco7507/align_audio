# Align Audio Service

Align Audio Service wraps the `align_first_anchor.py` script in a FastAPI backend and a modern Next.js frontend.

You upload two audio files (in‑house reference and external), the service estimates the best alignment offset, emits a ready‑to‑run FFmpeg command, and shows rich diagnostics (waveforms, similarity curve, spectrograms, residual mismatch).

It’s designed to run on:

- macOS / Linux for development.
- Windows Server 2016 (or later) for deployment (Python + FastAPI + Node, no Docker required).

---

## 1. Algorithm overview

The core logic lives in `align_first_anchor.py` and is wrapped from `app/services/alignment_service.py`.

### 1.1 Inputs

Two audio files:

- **In‑house**: your reference/ground‑truth.
- **External**: the file you want to align to the in‑house timeline.

Key parameters (CLI flags and their API equivalents):

- `--mode` (`external_to_inhouse` | `inhouse_to_external`)
  Which file is shifted.
- `--anchor-mode` (`xcorr` | `content`)
  Anchor detection strategy.
- `--sr` (default `48000`)
  Analysis and output sample rate.
- `--threshold-db` / `--vad-db`
  Simple gating threshold for low‑energy audio.
- `--analysis-sec` (default `30.0`)
  Limit for in‑house analysis window.
- `--max-search` / `--search-max-sec`
  Max ±seconds around zero lag for cross‑correlation (xcorr path).

### 1.2 Anchor modes

1. **xcorr (normalized cross‑correlation)**
   - Uses `estimate_offset_seconds` from `align_first_anchor.py`.
   - Steps:
     - Load both files as mono at `sr`.
     - Apply optional gating (`--threshold-db`).
     - Take the first `analysis-sec` seconds from in‑house; external window is automatically extended by ±`max-search`.
     - Compute FFT‑based normalized cross‑correlation.
     - Find the lag that maximizes similarity.
     - Convert lag to offset in seconds.

2. **content (MFCC-based template search)**
   - Uses `find_content_anchor`.
   - Steps:
     - Take the first `template-sec` of in‑house as a “template.”
     - Compute MFCC, average over time → `v1`.
     - Slide a window over external, hop size `hop-sec`.
     - For each window, compute MFCC, average → `v2`, then cosine similarity `cos(v1, v2)`.
     - First window with `sim >= min-sim` becomes the anchor.
   - Returns the time (seconds) in the external file where the template first matches.

### 1.3 Applying alignment (FFmpeg)

Once an offset is found, `build_align_command` constructs an FFmpeg command:

- If `mode == "external_to_inhouse"`:
  - Positive offset → add leading silence (pad external).
  - Negative offset → trim external’s leading samples.
- If `mode == "inhouse_to_external"`:
  - Same logic, but applied to the in‑house file; offset sign is inverted.

Flags:

- `--out-cmd`: path for the FFmpeg command text file.
- `--out-audio`: if set and `--apply` is passed, FFmpeg produces an aligned WAV at this path.
- `--apply`: run the FFmpeg command immediately.

---

## 2. Installation

### 2.1 macOS / Linux (development)

From the repo root:

```bash
python -m venv .venv
source .venv/bin/activate

pip install -r requirements.txt
```

Install frontend dependencies:

```bash
cd frontend
npm install
cd ..
```

### 2.2 Windows Server 2016

Prerequisites:

- Windows Server 2016 or later.
- Python 3.10+ (64‑bit) installed and on `PATH`.
- Node.js 18+ (LTS).
- `git` for Windows.

From an elevated PowerShell prompt:

```powershell
# Clone repo
git clone https://github.com/<org>/align_audio.git C:\align_audio
cd C:\align_audio

# Create and activate venv
python -m venv .venv
.\.venv\Scripts\activate

# Install backend dependencies
pip install -r requirements.txt

# Install frontend dependencies
cd frontend
npm install
cd ..
```

> Note: On Windows, FFmpeg must be installed and visible on `PATH` for the `--apply` FFmpeg command to succeed.

---

## 3. Running the service

### 3.1 Backend (FastAPI)

Default config (`app/config.py`):

- `APP_NAME`: `"Align Audio Service"`.
- `MEDIA_ROOT`: `data` (relative to repo root).
- `UPLOAD_DIR_NAME`: `uploads`.
- `RESULTS_DIR_NAME`: `results`.

Run locally (macOS/Linux):

```bash
cd align_audio
source .venv/bin/activate
uvicorn app.main:app --reload --port 8000
```

Run on Windows:

```powershell
cd C:\align_audio
.\.venv\Scripts\activate
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Endpoints (see details below):

- `GET /api/v1/health`
- `POST /api/v1/alignments`
- `GET /api/v1/alignments/{job_id}`
- `GET /api/v1/spectrograms/{job_id}`
- Static media: `/media/...` (served from `data/`).

### 3.2 Frontend (Next.js)

From `frontend/`:

```bash
cd frontend
npm run dev
```

By default, the frontend uses:

```ts
const apiBase = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";
```

To point at a backend on `http://localhost:8001` (for example), set:

```bash
# macOS/Linux
export NEXT_PUBLIC_API_BASE_URL=http://localhost:8001

# Windows PowerShell
$env:NEXT_PUBLIC_API_BASE_URL = "http://localhost:8001"
```

Then:

```bash
npm run dev
```

The UI will be at `http://localhost:3000` (or `3001` if 3000 is taken).

---

## 4. API documentation

### 4.1 `GET /api/v1/health`

**Purpose:** simple health check.

**Response:**

```json
{
  "status": "ok"
}
```

---

### 4.2 `POST /api/v1/alignments`

Create a new alignment job.

**Content‑Type:** `multipart/form-data`

**Fields:**

- `inhouse_file` – file (required).
- `external_file` – file (required).
- `mode` – `external_to_inhouse` | `inhouse_to_external` (default: `external_to_inhouse`).
- `anchor_mode` – `xcorr` | `content` (default: `xcorr`).
- `apply` – `"true"` or `"false"` (controls whether FFmpeg is actually run to produce aligned audio).

> Internally, additional CLI‑style parameters exist (from `align_first_anchor.py`) but are currently fixed at defaults via the service:
>
> - `sr` (sample rate) – default `48000`.
> - `threshold_db` / `vad_db` – optional gating; default is “no gating.”
> - `analysis_sec` – limited to first 30 seconds of in‑house.
> - `max_search` / `search_max_sec` – `60.0` seconds.
> - `template_sec` – `4.0` (content mode).
> - `hop_sec` – `0.1` (content mode).
> - `min_sim` – `0.78` (content mode similarity threshold).
> - `waveform_png`, `similarity_png` – used to generate diagnostics in the results.

**Example (curl):**

```bash
curl -X POST "http://localhost:8000/api/v1/alignments" \
  -F "inhouse_file=@/path/to/inhouse.wav" \
  -F "external_file=@/path/to/external.wav" \
  -F "mode=external_to_inhouse" \
  -F "anchor_mode=xcorr" \
  -F "apply=false"
```

**Response:**

```json
{
  "job_id": "5692dbc0-8fe1-44be-bc9d-0d57c4d52466",
  "status": "queued"
}
```

---

### 4.3 `GET /api/v1/alignments/{job_id}`

Poll job status and retrieve results once completed.

**Example:**

```bash
curl "http://localhost:8000/api/v1/alignments/5692dbc0-8fe1-44be-bc9d-0d57c4d52466"
```

**Response (while running):**

```json
{
  "job_id": "5692dbc0-8fe1-44be-bc9d-0d57c4d52466",
  "status": "running"
}
```

**Response (completed):**

```json
{
  "job_id": "5692dbc0-8fe1-44be-bc9d-0d57c4d52466",
  "status": "completed",
  "offset_sec": -0.534687,
  "ffmpeg_command": "ffmpeg -y -i \"external.wav\" -ac 1 -ar 48000 -af \"adelay=534|534\" -c:a pcm_s16le -rf64 always \"external_aligned.wav\"",
  "inhouse_url": "/media/uploads/5692dbc0-8fe1-44be-bc9d-0d57c4d52466/inhouse/inhouse.wav",
  "external_url": "/media/uploads/5692dbc0-8fe1-44be-bc9d-0d57c4d52466/external/external.wav",
  "aligned_audio_url": "/media/results/5692dbc0-8fe1-44be-bc9d-0d57c4d52466/aligned.wav",
  "waveform_png_url": "/media/results/5692dbc0-8fe1-44be-bc9d-0d57c4d52466/waveform_overlay.png",
  "similarity_png_url": "/media/results/5692dbc0-8fe1-44be-bc9d-0d57c4d52466/similarity.png",
  "alignment_zoom_png_url": "/media/results/5692dbc0-8fe1-44be-bc9d-0d57c4d52466/alignment_zoom.png",
  "spectrogram_inhouse_png_url": "/media/results/5692dbc0-8fe1-44be-bc9d-0d57c4d52466/spectrogram_inhouse.png",
  "spectrogram_external_png_url": "/media/results/...",
  "spectrogram_aligned_png_url": "/media/results/...",
  "residual_rms_png_url": "/media/results/.../residual_rms.png",
  "anchor_candidates_png_url": "/media/results/.../anchor_candidates.png",
  "confidence": 0.92,
  "confidence_label": "HIGH",
  "has_raw_audio": true,
  "created_at": "2025-11-14T17:12:03.542Z",
  "expires_at": "2025-12-14T17:12:03.542Z",
  "pinned": false
}
```

> To display these in the frontend, prepend `NEXT_PUBLIC_API_BASE_URL` (e.g., `http://localhost:8000`) to each `*_url` in the response.

---

### 4.4 `GET /api/v1/spectrograms/{job_id}`

Regenerate spectrograms on demand, including “Longer window” and “High resolution” views.

**Query params:**

- `track`: `inhouse` | `external` | `aligned` (default: `inhouse`).
- `view`: `default` | `long` | `highRes`.

**Behavior:**

- `view=default`:
  - Returns the cached spectrogram PNG if it exists:
    - `spectrogram_inhouse.png`
    - `spectrogram_external.png`
    - `spectrogram_aligned.png`
- `view=long` or `view=highRes`:
  - If raw audio is still available for the job:
    - Load the original audio from `data/uploads/{job_id}/inhouse` or `external`.
    - Compute a new STFT for **up to 5 minutes** of audio:
      - `long`: `n_fft=2048`, `hop_length=512` (moderate resolution).
      - `highRes`: `n_fft=4096`, `hop_length=256` (higher time/frequency resolution).
    - Render a new PNG:
      - `spectrogram_{track}_long.png`
      - `spectrogram_{track}_highRes.png`
  - If raw audio is not available or recomputation fails:
    - Fall back to re‑plotting the cached STFT (short window) with adjusted figure size.

**Example (longer window, in-house):**

```bash
curl -o inhouse_long.png \
  "http://localhost:8000/api/v1/spectrograms/5692dbc0-8fe1-44be-bc9d-0d57c4d52466?track=inhouse&view=long"
```

---

## 5. Flags and parameters not exposed in the UI

The web UI surfaces only:

- `mode` (`external_to_inhouse` / `inhouse_to_external`).
- `anchor_mode` (`xcorr` / `content`).
- `apply` (whether to generate aligned output).

Other CLI flags from `align_first_anchor.py` that currently use defaults in the service:

- `--sr` (`int`, default `48000`).
- `--threshold-db` / `--vad-db` (double; gate threshold).
- `--max-search` / `--search-max-sec` (`float`, default `60.0`).
- `--ref-start-sec` (`float`, default `0.0`).
- `--search-start-sec` (`float`, default `0.0`).
- `--analysis-sec` (`float`, default `30.0`).
- `--template-sec` (`float`, default `4.0`) – content mode.
- `--hop-sec` (`float`, default `0.1`) – content mode.
- `--min-sim` (`float`, default `0.78`) – content mode similarity threshold.
- `--out-cmd`, `--out-audio` – outputs (wrapped by the service).
- `--waveform-png`, `--similarity-png`, `--preview-png` – diagnostics images (wired into the service’s result artifacts).

If you need to expose any of these via the API in future, the natural place is `AlignmentParameters` (in `app/models.py`) and the corresponding request payload for `/api/v1/alignments`.

---

## 6. Storage layout and periodic purge

The backend keeps per‑job data under `MEDIA_ROOT` (default `data/`):

```text
data/
  jobs/
    <job_id>.json          # job metadata and result paths
  uploads/
    <job_id>/
      inhouse/
        <original inhouse file>
      external/
        <original external file>
  results/
    <job_id>/
      aligned.wav          # if apply=true
      waveform_overlay.png
      similarity.png
      alignment_zoom.png
      spectrogram_inhouse.png
      spectrogram_external.png
      spectrogram_aligned.png
      spectrogram_inhouse_long.png
      ...
      residual_rms.png
      anchor_candidates.png
      stft_inhouse.npz
      stft_external.npz
      stft_aligned.npz
      residual_envelope.npy
```

### 6.1 Retention metadata

Each job JSON in `data/jobs/` may include:

- `has_raw_audio`: whether original uploads are still present.
- `created_at`: job creation time (UTC).
- `expires_at`: when raw audio is scheduled to be purged.
- `pinned`: whether the job is exempt from automatic purge.

### 6.2 Purge script (`purge_jobs.py`)

A small maintenance helper is included at `purge_jobs.py` in the repo root. It implements:

- `JOB_RETENTION_DAYS` (env: `ALIGN_JOB_RETENTION_DAYS`, default `90`):
  delete entire jobs (JSON + uploads + results) older than this many days.
- `RAW_AUDIO_ONLY_DAYS` (env: `ALIGN_RAW_AUDIO_ONLY_DAYS`, default `30`):
  if a job is newer than `JOB_RETENTION_DAYS` but raw audio is expired,
  delete only `data/uploads/{job_id}` while keeping job JSON and results.

Usage examples:

```bash
# Dry run
python purge_jobs.py --dry-run

# Actually delete old artifacts
python purge_jobs.py
```

You can override paths and retention via environment variables:

```bash
export ALIGN_MEDIA_ROOT=/path/to/media
export ALIGN_JOB_RETENTION_DAYS=120
export ALIGN_RAW_AUDIO_ONLY_DAYS=45
python purge_jobs.py
```

### 6.3 Scheduling purge

- **Windows Task Scheduler**

  Create a basic task that runs daily and executes a command similar to:

  ```powershell
  cd C:\align_audio
  .\.venv\Scripts\activate
  python purge_jobs.py
  ```

  You can wrap this in a one‑line PowerShell script (e.g., `scripts\run_purge.ps1`) and point the task at that script.

- **cron (Linux/macOS)**

  Add a crontab entry (adjust paths as needed):

  ```bash
  0 3 * * * cd /opt/align_audio && /opt/align_audio/.venv/bin/python purge_jobs.py >> purge.log 2>&1
  ```

---

## 7. CI and Windows 2016

To run tests on a Windows runner (Server 2016‑class environment), you can create `.github/workflows/ci.yml` in the repo root with a Windows job, for example:

```yaml
name: CI

on:
  push:
    branches: ["main", "copilot-test"]
  pull_request:

jobs:
  backend-tests-windows:
    runs-on: windows-latest  # for Windows Server 2016, use a self-hosted runner labeled accordingly
    defaults:
      run:
        shell: pwsh

    steps:
      - name: Check out repo
        uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.10"

      - name: Install dependencies
        run: |
          python -m venv .venv
          .\.venv\Scripts\Activate.ps1
          pip install --upgrade pip
          pip install -r requirements.txt
          pip install pytest

      - name: Run backend tests
        run: |
          .\.venv\Scripts\Activate.ps1
          pytest
```

If you have an actual Windows Server 2016 host, you can:

- Register it as a **self‑hosted runner** in GitHub Actions.
- Label it (e.g., `windows-2016`).
- Change `runs-on` accordingly:

```yaml
runs-on: [self-hosted, windows-2016]
```

This ensures your alignment service is continuously validated on the same platform you intend to deploy to.

