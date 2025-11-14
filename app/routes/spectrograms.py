from pathlib import Path
from typing import Optional

import numpy as np
import librosa
import librosa.display  # type: ignore
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse

from app.config import settings
from app.routes.alignment import _read_job


router = APIRouter(prefix="/api/v1/spectrograms", tags=["spectrograms"])


def _job_results_dir(job_id: str) -> Path:
  return settings.MEDIA_ROOT / settings.RESULTS_DIR_NAME / job_id


@router.get("/{job_id}")
async def regenerate_spectrogram(
  job_id: str,
  track: str = Query("inhouse", pattern="^(inhouse|external|aligned)$"),
  view: str = Query("default", pattern="^(default|long|highRes)$"),
) -> FileResponse:
  """Regenerate a spectrogram image for a job/track.

  default  -> use cached short-window STFT (first ~30s)
  long     -> recompute from raw audio with a longer window (if available)
  highRes  -> recompute from raw audio with higher time/freq resolution (if available)
  """

  job = _read_job(job_id)
  if not job:
    raise HTTPException(status_code=404, detail="Job not found")

  results_dir = _job_results_dir(job_id)

  # Map track to cached STFT/PNG names
  stft_map = {
    "inhouse": (results_dir / "stft_inhouse.npz", results_dir / "spectrogram_inhouse.png"),
    "external": (results_dir / "stft_external.npz", results_dir / "spectrogram_external.png"),
    "aligned": (results_dir / "stft_aligned.npz", results_dir / "spectrogram_aligned.png"),
  }

  if track not in stft_map:
    raise HTTPException(status_code=400, detail="Invalid track")

  stft_path, default_png = stft_map[track]

  # If we only need default view and the PNG exists, return it directly.
  if view == "default" and default_png.is_file():
    return FileResponse(default_png)

  # For long/highRes we try to recompute from raw audio if available.
  has_raw_audio = bool(job.get("has_raw_audio", True))

  audio_root = settings.MEDIA_ROOT / settings.UPLOAD_DIR_NAME / job_id
  if track == "inhouse":
    audio_path = None
    # in-house is stored under uploads/<job_id>/inhouse/<filename>
    inhouse_dir = audio_root / "inhouse"
    if inhouse_dir.is_dir():
      # pick the first file; there should only be one
      files = list(inhouse_dir.glob("*"))
      audio_path = files[0] if files else None
  else:
    # external and aligned share the external file as source
    external_dir = audio_root / "external"
    audio_path = None
    if external_dir.is_dir():
      files = list(external_dir.glob("*"))
      audio_path = files[0] if files else None

  # Fallback: if we don't have raw audio or can't locate it, and a cached
  # STFT exists, just re-plot that STFT with adjusted figure size.
  use_cached_stft_only = not has_raw_audio or audio_path is None

  if view in ("long", "highRes") and not use_cached_stft_only and audio_path is not None:
    # Recompute STFT from raw audio on demand, but cap duration to avoid huge STFTs
    # on very long files that can exhaust memory or stall the worker.
    try:
      y, sr = librosa.load(str(audio_path), sr=None, mono=True)

      # Process at most 5 minutes for long/highRes views.
      MAX_LONG_SEC = 300.0

      if view == "long":
        max_sec = MAX_LONG_SEC
        n_fft = 2048
        hop_length = 512
      else:  # highRes
        max_sec = MAX_LONG_SEC
        n_fft = 4096
        hop_length = 256

      if max_sec is not None:
        y = y[: int(max_sec * sr)]

      S = np.abs(librosa.stft(y, n_fft=n_fft, hop_length=hop_length))
      S_db = librosa.amplitude_to_db(S, ref=np.max)

      if view == "long":
        figsize = (10, 3)
        dpi = 120
      else:  # highRes
        figsize = (12, 4)
        dpi = 160

      out_path = results_dir / f"spectrogram_{track}_{view}.png"
      plt.figure(figsize=figsize)
      librosa.display.specshow(
        S_db,
        sr=sr,
        hop_length=hop_length,
        x_axis="time",
        y_axis="log",
        cmap="magma",
      )
      plt.title(f"Spectrogram ({track}, {view})")
      plt.colorbar(format="%+2.0f dB")
      plt.tight_layout()
      plt.savefig(str(out_path), dpi=dpi)
      plt.close()
      return FileResponse(out_path)
    except Exception:
      # If recompute fails, fall back to cached STFT if available.
      pass

  if not stft_path.is_file():
    raise HTTPException(status_code=404, detail="No cached STFT for this job/track")

  # Re-plot from cached STFT as a fallback (still short-window)
  data = np.load(stft_path)
  S_mag = data["S_mag"]
  sr = int(data["sr"])
  hop_length = int(data["hop_length"])

  if view == "long":
    figsize = (10, 3)
    dpi = 120
  elif view == "highRes":
    figsize = (12, 4)
    dpi = 160
  else:
    figsize = (8, 3)
    dpi = 120

  S_db = librosa.amplitude_to_db(S_mag, ref=np.max)

  out_path = results_dir / f"spectrogram_{track}_{view}.png"
  plt.figure(figsize=figsize)
  librosa.display.specshow(
    S_db,
    sr=sr,
    hop_length=hop_length,
    x_axis="time",
    y_axis="log",
    cmap="magma",
  )
  plt.title(f"Spectrogram ({track}, {view})")
  plt.colorbar(format="%+2.0f dB")
  plt.tight_layout()
  plt.savefig(str(out_path), dpi=dpi)
  plt.close()

  return FileResponse(out_path)
