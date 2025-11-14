#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
align_first_anchor.py

Synchronize two audio files by finding the first common anchor, then
emit an FFmpeg command (and optionally run it) to align one file's
timeline to the other. Supports two anchor modes:

  1) xcorr   : normalized cross-correlation (fast, robust for simple offsets)
  2) content : MFCC template search with sliding window + cosine similarity

You can choose which file to adjust:
  --mode {external_to_inhouse, inhouse_to_external}

And whether to prefer trimming over padding when applying the alignment:
  --prefer-trim  (otherwise padding is preferred when reasonable)

Outputs:
  - An FFmpeg command text file (--out-cmd) that will align the chosen file.
  - Optionally, the aligned audio (--out-audio) if you also pass --apply.
  - Optional waveform overlay PNG (--waveform-png).
  - Optional similarity plot PNG (--similarity-png).

Dependencies (pip):
  numpy, librosa, matplotlib, scipy
"""

import argparse
import os
import sys
import json
import subprocess
from typing import Tuple, Optional

import numpy as np
import scipy.signal as spsig
import librosa
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt


# --------------------------- Utilities ---------------------------

def load_mono(path: str, sr: int) -> Tuple[np.ndarray, int]:
    """Load audio as mono float32 at target sample rate."""
    y, _sr = librosa.load(path, sr=sr, mono=True)
    return y.astype(np.float32), sr


def apply_gate_db(y: np.ndarray, threshold_db: Optional[float]) -> np.ndarray:
    """
    Optional simple gate for analysis-only:
    zero out samples below threshold (dBFS). If threshold_db is None, return y.
    """
    if threshold_db is None:
        return y
    eps = 1e-12
    mag = np.abs(y) + eps
    db = 20.0 * np.log10(mag)
    gated = np.where(db < threshold_db, 0.0, y)
    return gated


def estimate_offset_seconds(a: np.ndarray,
                            b: np.ndarray,
                            sr: int,
                            max_search: Optional[float]) -> Tuple[float, np.ndarray, np.ndarray]:
    """
    Normalized cross-correlation offset estimate using FFT-based correlate.

    Returns: (offset_sec, lags_sec, norm_corr)

    Positive offset means: a leads b (a occurs earlier), so b must be delayed
    by 'offset' to align to a.
    """
    if a.size == 0 or b.size == 0:
        return 0.0, np.array([0.0], dtype=float), np.array([1.0], dtype=float)

    # Zero-mean float32
    a0 = (a - np.mean(a)).astype(np.float32, copy=False)
    b0 = (b - np.mean(b)).astype(np.float32, copy=False)

    # Full correlation via FFT
    corr_full = spsig.correlate(a0, b0, mode="full", method="fft")
    lags_full = np.arange(-b0.size + 1, a0.size, dtype=int)

    # Bound the search window in samples
    if max_search is not None and max_search > 0:
        max_lag = int(max_search * sr)
    else:
        max_lag = min(a0.size, b0.size) - 1

    keep = (lags_full >= -max_lag) & (lags_full <= max_lag)
    corr = corr_full[keep]
    lags = lags_full[keep]

    # Normalize
    denom = np.sqrt(np.sum(a0 * a0) * np.sum(b0 * b0)) + 1e-12
    corr_norm = (corr / denom).astype(np.float32, copy=False)

    # Best lag
    best_idx = int(np.argmax(corr_norm))
    best_lag = int(lags[best_idx])
    offset_sec = -best_lag / float(sr)

    return offset_sec, (lags / float(sr)).astype(np.float32, copy=False), corr_norm


def find_content_anchor(a_an: np.ndarray,
                        b_an: np.ndarray,
                        sr: int,
                        template_sec: float,
                        hop_sec: float,
                        min_sim: float) -> Optional[float]:
    """
    Slide a template from 'a_an' across 'b_an' and return the FIRST b-time (sec)
    where cosine(MFCC_mean(template), MFCC_mean(window)) >= min_sim.
    """
    tmpl_len = int(template_sec * sr)
    if len(a_an) < tmpl_len:
        return None

    tmpl = a_an[:tmpl_len]
    tmpl_mfcc = librosa.feature.mfcc(y=tmpl, sr=sr, n_mfcc=20)
    v1 = np.mean(tmpl_mfcc, axis=1)

    hop = max(1, int(hop_sec * sr))
    last_start = max(0, len(b_an) - tmpl_len)

    for start in range(0, last_start + 1, hop):
        seg = b_an[start:start + tmpl_len]
        seg_mfcc = librosa.feature.mfcc(y=seg, sr=sr, n_mfcc=20)
        v2 = np.mean(seg_mfcc, axis=1)
        sim = np.dot(v1, v2) / (np.linalg.norm(v1) * np.linalg.norm(v2) + 1e-12)
        if sim >= min_sim:
            return start / float(sr)

    return None


def build_waveform_overlay_png(a: np.ndarray, b: np.ndarray, sr: int, out_png: str):
    """Save a dual waveform overlay for quick visual comparison."""
    t_a = np.arange(len(a)) / float(sr)
    t_b = np.arange(len(b)) / float(sr)
    plt.figure(figsize=(12, 4))
    plt.plot(t_a, a, alpha=0.7, label="in-house (raw)")
    plt.plot(t_b, b, alpha=0.7, label="external (raw)")
    plt.title("Waveform overlay (raw timelines)")
    plt.xlabel("Time (s)")
    plt.ylabel("Amplitude")
    plt.legend(loc="upper right")
    plt.tight_layout()
    plt.savefig(out_png, dpi=120)
    plt.close()


def plot_similarity_curve(lags_sec: np.ndarray, corr_norm: np.ndarray, out_png: str):
    """
    Plot normalized similarity vs lag (seconds), lightly downsampled
    for speed and memory safety.
    """
    max_points = 200_000
    if lags_sec.size > max_points:
        step = int(np.ceil(lags_sec.size / float(max_points)))
        lags_sec = lags_sec[::step]
        corr_norm = corr_norm[::step]

    plt.figure(figsize=(10, 3))
    plt.plot(lags_sec, corr_norm)
    plt.title("Similarity vs. Lag (xcorr path)")
    plt.xlabel("Lag (s)  [positive lag = delay applied to external to match in-house]")
    plt.ylabel("Normalized similarity")
    plt.grid(True, alpha=0.3)
    plt.tight_layout()
    plt.savefig(out_png, dpi=120)
    plt.close()


def ffmpeg_time_format(seconds: float) -> str:
    """Format seconds as ffmpeg-friendly decimal seconds."""
    return f"{max(0.0, seconds):.6f}"


def build_align_command(
    inhouse_path: str,
    external_path: str,
    sr: int,
    mode: str,
    offset_sec: float,
    prefer_trim: bool,
    out_audio: Optional[str],
) -> str:
    """
    Build an FFmpeg command to align one file to the other.

    Conventions:
      - offset_sec is the delay you would apply to EXTERNAL to match IN-HOUSE
        if mode == "external_to_inhouse".
      - If mode == "inhouse_to_external", we invert the sign because now IN-HOUSE
        must be shifted to EXTERNAL's timeline.

      Positive offset means "target must be delayed"; negative offset means
      "target must be advanced (trim)".

    prefer_trim:
      True  => try to trim when offset<0 (advance), else pad when offset>0
      False => prefer pad for small offsets too (but still trim if negative).
    """
    if mode not in ("external_to_inhouse", "inhouse_to_external"):
        raise ValueError("mode must be external_to_inhouse or inhouse_to_external")

    if mode == "external_to_inhouse":
        target = external_path
        ref = inhouse_path
        effective_offset = offset_sec
        default_out = "external_aligned.wav"
    else:
        target = inhouse_path
        ref = external_path
        effective_offset = -offset_sec  # invert: now align inhouse to external
        default_out = "inhouse_aligned.wav"

    out_path = out_audio or default_out

    # Decide trim vs pad
    cmd = None
    if effective_offset < -1e-6:
        # Advance target by trimming leading samples
        trim_sec = abs(effective_offset)
        cmd = (
            f'ffmpeg -y -i "{target}" '
            f"-ac 1 -ar {sr} -ss {ffmpeg_time_format(trim_sec)} "
            f'-c:a pcm_s16le -rf64 always "{out_path}"'
        )
    elif effective_offset > 1e-6:
        # Delay target by padding leading silence
        pad_ms = int(round(effective_offset * 1000.0))
        cmd = (
            f'ffmpeg -y -i "{target}" '
            f"-ac 1 -ar {sr} "
            f'-af "adelay={pad_ms}|{pad_ms}" '
            f'-c:a pcm_s16le -rf64 always "{out_path}"'
        )
    else:
        # No shift needed; just rewrap/normalize format
        cmd = (
            f'ffmpeg -y -i "{target}" -ac 1 -ar {sr} '
            f'-c:a pcm_s16le -rf64 always "{out_path}"'
        )

    return cmd


def run_shell(cmd: str) -> int:
    """Run a shell command and return exit code."""
    try:
        completed = subprocess.run(cmd, shell=True)
        return completed.returncode
    except Exception as e:
        print(f"[ERROR] Execution failed: {e}")
        return 1


# --------------------------- Main CLI ---------------------------

def main():
    p = argparse.ArgumentParser(
        description=(
            "Align two audio files by the first common anchor "
            "and emit/apply an FFmpeg alignment."
        )
    )
    p.add_argument("--inhouse", required=True, help="Path to in-house WAV/AIFF/etc.")
    p.add_argument("--external", required=True, help="Path to external WAV/AIFF/etc.")
    p.add_argument("--sr", type=int, default=48000, help="Analysis/output sample rate (Hz).")

    # Direction & behavior
    p.add_argument(
        "--mode",
        choices=["external_to_inhouse", "inhouse_to_external"],
        default="external_to_inhouse",
        help="Which file to shift: external→inhouse (default) or inhouse→external",
    )
    p.add_argument(
        "--prefer-trim",
        action="store_true",
        help="Prefer trimming where possible; otherwise padding when delaying the target",
    )

    # Anchor selection
    p.add_argument(
        "--anchor-mode",
        choices=["xcorr", "content"],
        default="xcorr",
        help="xcorr = normalized cross-correlation; content = MFCC template search",
    )
    p.add_argument(
        "--template-sec",
        type=float,
        default=4.0,
        help="Template length (sec) for content mode",
    )
    p.add_argument(
        "--hop-sec",
        type=float,
        default=0.1,
        help="Hop size (sec) for content mode",
    )
    p.add_argument(
        "--min-sim",
        type=float,
        default=0.78,
        help="Cosine similarity threshold to accept the first anchor in content mode",
    )

    # Search windows & thresholds
    p.add_argument(
        "--threshold-db",
        type=float,
        default=None,
        help="Optional gate (dBFS) for analysis copies",
    )
    p.add_argument(
        "--max-search",
        type=float,
        default=60.0,
        help="Max ±seconds to search around zero lag (xcorr path)",
    )
    p.add_argument(
        "--ref-start-sec",
        type=float,
        default=0.0,
        help="Analysis start of in-house (sec)",
    )
    p.add_argument(
        "--search-start-sec",
        type=float,
        default=0.0,
        help="Analysis start of external (sec)",
    )

    # Aliases for backwards compatibility
    p.add_argument(
        "--vad-db",
        type=float,
        default=None,
        help="Alias of --threshold-db; if set, overrides threshold-db",
    )
    p.add_argument(
        "--search-max-sec",
        type=float,
        default=None,
        help="Alias of --max-search; if set, overrides max-search",
    )
    p.add_argument(
        "--analysis-sec",
        type=float,
        default=30.0,
        help=(
            "Limit analysis to the first N seconds of in-house; "
            "external window is auto-extended by ±max-search."
        ),
    )
    p.add_argument(
        "--preview-png",
        default=None,
        help="Alias of --waveform-png; if set, overrides waveform-png",
    )

    # Outputs
    p.add_argument(
        "--out-cmd",
        default="aligned_cmd.txt",
        help="Where to write the FFmpeg command",
    )
    p.add_argument(
        "--out-audio",
        default=None,
        help="If given with --apply, write aligned WAV here",
    )
    p.add_argument(
        "--waveform-png",
        default=None,
        help="Optional overlay image of raw waveforms",
    )
    p.add_argument(
        "--similarity-png",
        default=None,
        help="Optional similarity-over-lag plot (xcorr path only)",
    )
    p.add_argument(
        "--apply",
        action="store_true",
        help="Run the emitted FFmpeg command immediately",
    )

    args = p.parse_args()

    # Ensure parent dirs for optional image outputs exist
    def _ensure_parent(path: Optional[str]):
        if path:
            d = os.path.dirname(path)
            if d:
                os.makedirs(d, exist_ok=True)

    _ensure_parent(getattr(args, "waveform_png", None))
    _ensure_parent(getattr(args, "similarity_png", None))

    # Normalize flag aliases
    if getattr(args, "vad_db", None) is not None:
        args.threshold_db = args.vad_db
    if getattr(args, "search_max_sec", None) is not None:
        args.max_search = args.search_max_sec
    if getattr(args, "preview_png", None):
        args.waveform_png = args.preview_png

    # Validate files
    for path in (args.inhouse, args.external):
        if not os.path.isfile(path):
            print(f"[ERROR] File not found: {path}")
            sys.exit(2)

    # Load raw audio (for overlays)
    a_raw, sr = load_mono(args.inhouse, args.sr)
    b_raw, sr = load_mono(args.external, args.sr)

    # Optional raw overlay (before alignment)
    if args.waveform_png:
        try:
            build_waveform_overlay_png(a_raw, b_raw, sr, args.waveform_png)
            print(f"[INFO] Saved waveform overlay: {args.waveform_png}")
        except Exception as e:
            print(f"[WARN] Failed to build waveform overlay: {e}")

    # Build analysis copies with start offsets and gating
    a_an = a_raw.copy()
    b_an = b_raw.copy()
    if args.ref_start_sec > 0:
        a_an = a_an[int(args.ref_start_sec * sr):]
    if args.search_start_sec > 0:
        b_an = b_an[int(args.search_start_sec * sr):]

    a_an = apply_gate_db(a_an, args.threshold_db)
    b_an = apply_gate_db(b_an, args.threshold_db)

    # Window the analysis to keep xcorr bounded and fast
    if args.analysis_sec and args.analysis_sec > 0:
        max_ref_samples = int(args.analysis_sec * sr)
        if a_an.size > max_ref_samples:
            a_an = a_an[:max_ref_samples]

    if args.max_search and args.max_search > 0:
        pad = int(args.max_search * sr)
    else:
        pad = min(a_an.size, b_an.size) - 1 if a_an.size and b_an.size else 0

    needed_b_len = a_an.size + 2 * pad
    if b_an.size > needed_b_len:
        b_an = b_an[:needed_b_len]

    print(
        f"[INFO] Analysis sizes (samples): "
        f"in-house={a_an.size}, external={b_an.size}, sr={sr}"
    )

    # ---------- Find first common anchor + optional similarity plot ----------
    lags_sec = None
    corr_norm = None

    if args.anchor_mode == "xcorr":
        offset_sec, lags_sec, corr_norm = estimate_offset_seconds(
            a_an, b_an, sr, args.max_search
        )
        offset_sec += (args.ref_start_sec - args.search_start_sec)
        print(
            "[INFO] XCORR anchor => offset "
            f"(delay external to match in-house) = {offset_sec:.6f} s"
        )
    else:
        best_b = find_content_anchor(
            a_an,
            b_an,
            sr,
            template_sec=args.template_sec,
            hop_sec=args.hop_sec,
            min_sim=args.min_sim,
        )
        if best_b is None:
            print("[WARN] Content anchor not found at threshold; falling back to xcorr.")
            offset_sec, lags_sec, corr_norm = estimate_offset_seconds(
                a_an, b_an, sr, args.max_search
            )
            offset_sec += (args.ref_start_sec - args.search_start_sec)
            print(f"[INFO] Fallback XCORR => offset = {offset_sec:.6f} s")
        else:
            offset_sec = (
                (0.0 + args.ref_start_sec) - (best_b + args.search_start_sec)
            )
            print(
                "[INFO] CONTENT anchor => offset "
                f"(delay external to match in-house) = {offset_sec:.6f} s"
            )
            # Minimal similarity trace so we can still emit a figure if asked
            lags_sec = np.array([0.0, 1.0], dtype=float)
            corr_norm = np.array([1.0, 1.0], dtype=float)

    # Plot similarity if requested and we have arrays
    if args.similarity_png and (lags_sec is not None) and (corr_norm is not None):
        try:
            plot_similarity_curve(lags_sec, corr_norm, args.similarity_png)
            print(f"[INFO] Saved similarity curve: {args.similarity_png}")
        except Exception as e:
            print(f"[WARN] Failed to plot similarity curve: {e}")

    # Build command according to chosen direction and policy
    cmd = build_align_command(
        inhouse_path=args.inhouse,
        external_path=args.external,
        sr=sr,
        mode=args.mode,
        offset_sec=offset_sec,
        prefer_trim=args.prefer_trim,
        out_audio=args.out_audio,
    )

    # Write command to file
    with open(args.out_cmd, "w", encoding="utf-8") as f:
        f.write(cmd + "\n")
    print(f"[INFO] Wrote alignment command to: {args.out_cmd}")
    print(f"[INFO] Suggested:\n{cmd}")

    # Optionally apply
    if args.apply:
        print("[INFO] Applying alignment with FFmpeg...")
        rc = run_shell(cmd)
        if rc != 0:
            print(f"[ERROR] FFmpeg returned non-zero exit code: {rc}")
            sys.exit(rc)
        else:
            print("[INFO] Alignment applied successfully.")

    print("[DONE]")


# --------------------------- Entry ---------------------------

if __name__ == "__main__":
    main()