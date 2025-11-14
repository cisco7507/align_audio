# Align Audio Service

This project exposes the `align_first_anchor.py` script as a FastAPI microservice
with a small React/Next.js frontend for uploading audio files and visualizing
alignment results.

## Backend (FastAPI)

- App module: `app/main.py`
- Alignment endpoints: `app/routes/alignment.py`
- Core logic wrapper: `app/services/alignment_service.py`

### Running the API locally

1. Create and activate a virtualenv.
2. Install Python dependencies:

```bash
pip install -r requirements.txt
pip install fastapi uvicorn[standard] python-multipart pydantic-settings
```

3. Start the API server:

```bash
uvicorn app.main:app --reload
```

The API will be available at `http://localhost:8000`.

Useful endpoints:

- `GET /api/v1/health` – health check
- `POST /api/v1/alignments` – create an alignment job (multipart/form-data)
- `GET /api/v1/alignments/{job_id}` – poll for job status and results

Media (uploads, results) are served from `/media/...`.

## Frontend (Next.js)

The frontend lives under `frontend/` and is a minimal Next.js app
with a single page at `/` that:

- Accepts two audio uploads (in-house and external)
- Lets you choose basic parameters (anchor mode, mode)
- Calls the FastAPI backend to run an alignment job
- Polls for completion and then shows:
  - Estimated offset
  - Suggested FFmpeg command
  - Waveform overlay and similarity plots
  - Audio players for raw and aligned audio

### Running the frontend

From the `frontend/` directory:

```bash
npm install
npm run dev
```

By default the frontend expects the backend at `http://localhost:8000`.
You can override this via the `NEXT_PUBLIC_API_BASE_URL` environment variable.

## Notes

- This is a first implementation meant for local or small-scale use.
  For production, you may want to:
  - Move from the in-memory job store to Redis or a database
  - Offload heavy work to a worker queue (Celery/RQ/Arq)
  - Store media artifacts in S3 or other object storage
