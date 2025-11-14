#!/usr/bin/env python
"""Simple maintenance script to purge old jobs and uploads/results.

This is intentionally minimal and file-based to match the FastAPI service
storage layout:

    data/
      jobs/<job_id>.json
      uploads/<job_id>/...
      results/<job_id>/...

Retention policy (configurable via constants or env vars):
- JOB_RETENTION_DAYS: delete entire job (JSON + uploads + results) if
  created_at is older than this many days.
- RAW_AUDIO_ONLY_DAYS: remove raw uploads (but keep job JSON and results)
  if has_raw_audio is true and expires_at (or created_at + RAW_AUDIO_ONLY_DAYS)
  is in the past.

Usage examples:

  # Dry run
  python purge_jobs.py --dry-run

  # Actually delete old artifacts
  python purge_jobs.py

On Windows, you can schedule this via Task Scheduler (see README).
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
from pathlib import Path
from typing import Any, Dict, Tuple

# Defaults can be overridden via environment variables
JOB_RETENTION_DAYS = int(os.environ.get("ALIGN_JOB_RETENTION_DAYS", "90"))
RAW_AUDIO_ONLY_DAYS = int(os.environ.get("ALIGN_RAW_AUDIO_ONLY_DAYS", "30"))

MEDIA_ROOT = Path(os.environ.get("ALIGN_MEDIA_ROOT", "data"))
JOBS_DIR = MEDIA_ROOT / "jobs"
UPLOADS_DIR = MEDIA_ROOT / "uploads"
RESULTS_DIR = MEDIA_ROOT / "results"


def parse_iso(ts: str | None) -> dt.datetime | None:
    if not ts:
        return None
    try:
        return dt.datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except Exception:
        return None


def load_job(job_path: Path) -> Dict[str, Any] | None:
    try:
        with job_path.open("r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def purge_job(job_id: str, dry_run: bool = False) -> Tuple[int, int, int]:
    """Delete job JSON + uploads + results for a job_id.

    Returns (jobs_deleted, uploads_deleted, results_deleted) as 0/1 flags.
    """

    jobs_deleted = uploads_deleted = results_deleted = 0

    job_json = JOBS_DIR / f"{job_id}.json"
    uploads = UPLOADS_DIR / job_id
    results = RESULTS_DIR / job_id

    if not dry_run:
        if job_json.is_file():
            job_json.unlink()
            jobs_deleted = 1
        if uploads.is_dir():
            for p in uploads.rglob("*"):
                if p.is_file():
                    p.unlink()
            uploads.rmdir()
            uploads_deleted = 1
        if results.is_dir():
            for p in results.rglob("*"):
                if p.is_file():
                    p.unlink()
            results.rmdir()
            results_deleted = 1

    return jobs_deleted, uploads_deleted, results_deleted


def purge_raw_audio(job_id: str, dry_run: bool = False) -> int:
    """Delete only uploads/<job_id> while leaving job JSON + results.

    Returns 1 if uploads were removed, else 0.
    """

    uploads = UPLOADS_DIR / job_id
    if not uploads.is_dir():
        return 0

    if not dry_run:
        for p in uploads.rglob("*"):
            if p.is_file():
                p.unlink()
        uploads.rmdir()
    return 1


def main() -> None:
    parser = argparse.ArgumentParser(description="Purge old align_audio jobs")
    parser.add_argument("--dry-run", action="store_true", help="Print actions without deleting anything")
    args = parser.parse_args()

    now = dt.datetime.now(dt.timezone.utc)
    job_cutoff = now - dt.timedelta(days=JOB_RETENTION_DAYS)
    raw_cutoff = now - dt.timedelta(days=RAW_AUDIO_ONLY_DAYS)

    total_jobs_deleted = total_uploads_deleted = total_results_deleted = 0
    total_raw_only_deleted = 0

    if not JOBS_DIR.is_dir():
        print(f"No jobs directory found at {JOBS_DIR}")
        return

    for job_json in JOBS_DIR.glob("*.json"):
        job_id = job_json.stem
        job = load_job(job_json)
        if not job:
            continue

        created_at = parse_iso(job.get("created_at"))
        expires_at = parse_iso(job.get("expires_at"))
        has_raw_audio = bool(job.get("has_raw_audio", True))
        pinned = bool(job.get("pinned", False))

        # Skip pinned jobs completely
        if pinned:
            continue

        # Decide if the whole job should be purged
        if created_at and created_at < job_cutoff:
            j, u, r = purge_job(job_id, dry_run=args.dry_run)
            total_jobs_deleted += j
            total_uploads_deleted += u
            total_results_deleted += r
            print(f"[JOB] Purged job {job_id} (older than {JOB_RETENTION_DAYS} days)")
            continue

        # Otherwise, consider raw-audio-only purge
        if has_raw_audio:
            # Prefer explicit expires_at if present; else derive from created_at
            raw_deadline = expires_at or (created_at + dt.timedelta(days=RAW_AUDIO_ONLY_DAYS) if created_at else None)
            if raw_deadline and raw_deadline < raw_cutoff:
                removed = purge_raw_audio(job_id, dry_run=args.dry_run)
                if removed:
                    total_raw_only_deleted += 1
                    print(f"[RAW] Purged raw uploads for {job_id}")

    print("---")
    print(f"Jobs deleted:       {total_jobs_deleted}")
    print(f"Uploads deleted:    {total_uploads_deleted}")
    print(f"Results deleted:    {total_results_deleted}")
    print(f"Raw-only purged:    {total_raw_only_deleted}")
    if args.dry_run:
        print("(dry run) No files were actually removed.")


if __name__ == "__main__":
    main()
