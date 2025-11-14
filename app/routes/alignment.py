from pathlib import Path
from typing import Optional
import uuid
import json

from fastapi import APIRouter, UploadFile, File, Form, BackgroundTasks
from fastapi import HTTPException

from app.models import AlignmentParameters, AlignmentJobResponse, AlignmentResultResponse
from app.services.alignment_service import run_alignment_job
from app.config import settings


router = APIRouter(prefix="/api/v1/alignments", tags=["alignments"])


JOBS_DIR = settings.MEDIA_ROOT / "jobs"
JOBS_DIR.mkdir(parents=True, exist_ok=True)


def _job_path(job_id: str) -> Path:
    return JOBS_DIR / f"{job_id}.json"


def _write_job(job_id: str, data: dict) -> None:
    path = _job_path(job_id)
    path.write_text(json.dumps(data), encoding="utf-8")


def _read_job(job_id: str) -> Optional[dict]:
    path = _job_path(job_id)
    if not path.is_file():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


@router.post("", response_model=AlignmentJobResponse, status_code=202)
async def create_alignment_job(
    background_tasks: BackgroundTasks,
    inhouse_file: UploadFile = File(...),
    external_file: UploadFile = File(...),
    sr: int = Form(48000),
    mode: str = Form("external_to_inhouse"),
    anchor_mode: str = Form("xcorr"),
    prefer_trim: bool = Form(False),
    threshold_db: Optional[float] = Form(None),
    max_search: float = Form(60.0),
    ref_start_sec: float = Form(0.0),
    search_start_sec: float = Form(0.0),
    analysis_sec: float = Form(30.0),
    template_sec: float = Form(4.0),
    hop_sec: float = Form(0.1),
    min_sim: float = Form(0.78),
    generate_waveform_png: bool = Form(True),
    generate_similarity_png: bool = Form(True),
    apply: bool = Form(False),
):
    job_id = str(uuid.uuid4())

    params = AlignmentParameters(
        sr=sr,
        mode=mode,
        anchor_mode=anchor_mode,
        prefer_trim=prefer_trim,
        threshold_db=threshold_db,
        max_search=max_search,
        ref_start_sec=ref_start_sec,
        search_start_sec=search_start_sec,
        analysis_sec=analysis_sec,
        template_sec=template_sec,
        hop_sec=hop_sec,
        min_sim=min_sim,
        generate_waveform_png=generate_waveform_png,
        generate_similarity_png=generate_similarity_png,
        apply=apply,
    )

    media_root = settings.MEDIA_ROOT
    tmp_dir = media_root / "tmp" / job_id
    tmp_dir.mkdir(parents=True, exist_ok=True)

    inhouse_path = tmp_dir / inhouse_file.filename
    external_path = tmp_dir / external_file.filename

    # Persist uploaded files
    with inhouse_path.open("wb") as f:
        f.write(await inhouse_file.read())
    with external_path.open("wb") as f:
        f.write(await external_file.read())

    _write_job(job_id, {"status": "queued", "result": None})

    def _run():
        job_data = _read_job(job_id) or {}
        job_data["status"] = "running"
        _write_job(job_id, job_data)
        try:
            result = run_alignment_job(
                inhouse_src=inhouse_path,
                external_src=external_path,
                params=params,
                job_id=job_id,
            )
            job_data = {
                "status": "completed",
                "result": {
                    "job_id": result.job_id,
                    "offset_sec": result.offset_sec,
                    "ffmpeg_command": result.ffmpeg_command,
                    "inhouse_path": str(result.inhouse_path),
                    "external_path": str(result.external_path),
                    "aligned_audio_path": str(result.aligned_audio_path)
                    if result.aligned_audio_path
                    else None,
                    "waveform_png_path": str(result.waveform_png_path)
                    if result.waveform_png_path
                    else None,
                    "similarity_png_path": str(result.similarity_png_path)
                    if result.similarity_png_path
                    else None,
                    "logs": result.logs,
                },
            }
            _write_job(job_id, job_data)
        except Exception as exc:  # pragma: no cover - safety
            job_data = {"status": "failed", "error": str(exc)}
            _write_job(job_id, job_data)

    background_tasks.add_task(_run)

    return AlignmentJobResponse(job_id=job_id, status="queued")


@router.get("/{job_id}", response_model=AlignmentResultResponse)
async def get_alignment_job(job_id: str):
    job = _read_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    status = job["status"]
    result = job.get("result")

    if status != "completed" or result is None:
        # Partial response while job is running
        return AlignmentResultResponse(job_id=job_id, status=status)

    # Build URLs relative to a /media mount
    def rel(path: Optional[Path]) -> Optional[str]:
        if path is None:
            return None
        # Paths under settings.MEDIA_ROOT become /media/<relative>
        media_root = settings.MEDIA_ROOT
        try:
            rel_path = path.relative_to(media_root)
        except ValueError:
            return None
        return f"/media/{rel_path.as_posix()}"

    return AlignmentResultResponse(
        job_id=result.job_id,
        status=status,
        offset_sec=result.offset_sec,
        ffmpeg_command=result.ffmpeg_command,
        inhouse_url=rel(result.inhouse_path),
        external_url=rel(result.external_path),
        aligned_audio_url=rel(result.aligned_audio_path),
        waveform_png_url=rel(result.waveform_png_path),
        similarity_png_url=rel(result.similarity_png_path),
        logs=result.logs,
    )
