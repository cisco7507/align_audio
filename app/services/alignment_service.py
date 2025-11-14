import logging
import os
import uuid
from pathlib import Path
from typing import Optional, List, Tuple

import numpy as np

from app.config import settings
from app.models import AlignmentParameters

# Import functions from the existing script
from align_first_anchor import (
    load_mono,
    apply_gate_db,
    estimate_offset_seconds,
    find_content_anchor,
    build_waveform_overlay_png,
    plot_similarity_curve,
    build_align_command,
    run_shell,
)

logger = logging.getLogger(__name__)


class AlignmentResult:
    def __init__(
        self,
        job_id: str,
        offset_sec: float,
        ffmpeg_command: str,
        inhouse_path: Path,
        external_path: Path,
        aligned_audio_path: Optional[Path],
        waveform_png_path: Optional[Path],
        similarity_png_path: Optional[Path],
        logs: Optional[List[str]] = None,
    ) -> None:
        self.job_id = job_id
        self.offset_sec = offset_sec
        self.ffmpeg_command = ffmpeg_command
        self.inhouse_path = inhouse_path
        self.external_path = external_path
        self.aligned_audio_path = aligned_audio_path
        self.waveform_png_path = waveform_png_path
        self.similarity_png_path = similarity_png_path
        self.logs = logs or []


def _ensure_dirs(job_id: str) -> Tuple[Path, Path]:
    base = settings.MEDIA_ROOT
    uploads = base / settings.UPLOAD_DIR_NAME / job_id
    results = base / settings.RESULTS_DIR_NAME / job_id
    uploads.mkdir(parents=True, exist_ok=True)
    results.mkdir(parents=True, exist_ok=True)
    return uploads, results


def run_alignment_job(
    inhouse_src: Path,
    external_src: Path,
    params: AlignmentParameters,
    job_id: Optional[str] = None,
) -> AlignmentResult:
    """Core wrapper that mirrors the CLI behavior but returns structured data.

    This function operates entirely on paths and parameters and writes any
    derived artifacts under a job-specific directory.
    """

    job_id = job_id or str(uuid.uuid4())
    uploads_dir, results_dir = _ensure_dirs(job_id)

    logs: List[str] = []

    def log(msg: str) -> None:
        logger.info(msg)
        logs.append(msg)

    # Copy input files into uploads dir (for stable URLs)
    inhouse_path = uploads_dir / "inhouse" / inhouse_src.name
    external_path = uploads_dir / "external" / external_src.name
    inhouse_path.parent.mkdir(parents=True, exist_ok=True)
    external_path.parent.mkdir(parents=True, exist_ok=True)

    if inhouse_src != inhouse_path:
        inhouse_path.write_bytes(inhouse_src.read_bytes())
    if external_src != external_path:
        external_path.write_bytes(external_src.read_bytes())

    # Load raw audio
    a_raw, sr = load_mono(str(inhouse_path), params.sr)
    b_raw, sr = load_mono(str(external_path), params.sr)

    # Optional raw overlay
    waveform_png_path: Optional[Path] = None
    if params.generate_waveform_png:
        waveform_png_path = results_dir / "waveform_overlay.png"
        try:
            build_waveform_overlay_png(a_raw, b_raw, sr, str(waveform_png_path))
            log(f"Saved waveform overlay: {waveform_png_path}")
        except Exception as e:  # pragma: no cover - visualization failure
            log(f"[WARN] Failed to build waveform overlay: {e}")

    # Build analysis copies with start offsets and gating
    a_an = a_raw.copy()
    b_an = b_raw.copy()
    if params.ref_start_sec > 0:
        a_an = a_an[int(params.ref_start_sec * sr) :]
    if params.search_start_sec > 0:
        b_an = b_an[int(params.search_start_sec * sr) :]

    a_an = apply_gate_db(a_an, params.threshold_db)
    b_an = apply_gate_db(b_an, params.threshold_db)

    # Window the analysis
    if params.analysis_sec and params.analysis_sec > 0:
        max_ref_samples = int(params.analysis_sec * sr)
        if a_an.size > max_ref_samples:
            a_an = a_an[:max_ref_samples]

    if params.max_search and params.max_search > 0:
        pad = int(params.max_search * sr)
    else:
        pad = min(a_an.size, b_an.size) - 1 if a_an.size and b_an.size else 0

    needed_b_len = a_an.size + 2 * pad
    if b_an.size > needed_b_len:
        b_an = b_an[:needed_b_len]

    log(
        f"Analysis sizes (samples): in-house={a_an.size}, external={b_an.size}, sr={sr}"
    )

    # Find anchor
    lags_sec = None
    corr_norm = None
    if params.anchor_mode == "xcorr":
        offset_sec, lags_sec, corr_norm = estimate_offset_seconds(
            a_an, b_an, sr, params.max_search
        )
        offset_sec += (params.ref_start_sec - params.search_start_sec)
        log(
            f"XCORR anchor => offset (delay external to match in-house) = {offset_sec:.6f} s"
        )
    else:
        best_b = find_content_anchor(
            a_an,
            b_an,
            sr,
            template_sec=params.template_sec,
            hop_sec=params.hop_sec,
            min_sim=params.min_sim,
        )
        if best_b is None:
            log("[WARN] Content anchor not found at threshold; falling back to xcorr.")
            offset_sec, lags_sec, corr_norm = estimate_offset_seconds(
                a_an, b_an, sr, params.max_search
            )
            offset_sec += (params.ref_start_sec - params.search_start_sec)
            log(f"Fallback XCORR => offset = {offset_sec:.6f} s")
        else:
            offset_sec = (
                (0.0 + params.ref_start_sec) - (best_b + params.search_start_sec)
            )
            log(
                "CONTENT anchor => offset (delay external to match in-house) "
                f"= {offset_sec:.6f} s"
            )
            # Minimal similarity trace so we can still emit a figure if asked
            lags_sec = np.array([0.0, 1.0], dtype=float)
            corr_norm = np.array([1.0, 1.0], dtype=float)

    # Similarity plot
    similarity_png_path: Optional[Path] = None
    if params.generate_similarity_png and (lags_sec is not None) and (
        corr_norm is not None
    ):
        similarity_png_path = results_dir / "similarity_curve.png"
        try:
            plot_similarity_curve(lags_sec, corr_norm, str(similarity_png_path))
            log(f"Saved similarity curve: {similarity_png_path}")
        except Exception as e:  # pragma: no cover
            log(f"[WARN] Failed to plot similarity curve: {e}")

    # Build FFmpeg command
    out_audio_path: Optional[Path] = None
    if params.apply:
        out_audio_path = results_dir / "aligned.wav"
        out_audio_str: Optional[str] = str(out_audio_path)
    else:
        out_audio_str = None

    cmd = build_align_command(
        inhouse_path=str(inhouse_path),
        external_path=str(external_path),
        sr=sr,
        mode=params.mode,
        offset_sec=offset_sec,
        prefer_trim=params.prefer_trim,
        out_audio=out_audio_str,
    )

    log(f"Suggested FFmpeg command: {cmd}")

    aligned_audio_path: Optional[Path] = None
    if params.apply and out_audio_path is not None:
        log("Applying alignment with FFmpeg...")
        rc = run_shell(cmd)
        if rc != 0:
            log(f"[ERROR] FFmpeg returned non-zero exit code: {rc}")
        else:
            aligned_audio_path = out_audio_path
            log("Alignment applied successfully.")

    return AlignmentResult(
        job_id=job_id,
        offset_sec=offset_sec,
        ffmpeg_command=cmd,
        inhouse_path=inhouse_path,
        external_path=external_path,
        aligned_audio_path=aligned_audio_path,
        waveform_png_path=waveform_png_path,
        similarity_png_path=similarity_png_path,
        logs=logs,
    )
