from pathlib import Path

import numpy as np
import soundfile as sf
from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def _write_dummy_wav(path: Path, sr: int = 8000, seconds: float = 1.0) -> None:
    t = np.linspace(0, seconds, int(sr * seconds), endpoint=False)
    # Simple sine tone at 440 Hz
    x = 0.1 * np.sin(2 * np.pi * 440.0 * t).astype("float32")
    sf.write(path, x, sr)


def test_health_endpoint():
    resp = client.get("/api/v1/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_alignment_job_lifecycle(tmp_path: Path):
    inhouse_path = tmp_path / "inhouse.wav"
    external_path = tmp_path / "external.wav"
    _write_dummy_wav(inhouse_path)
    _write_dummy_wav(external_path)

    with inhouse_path.open("rb") as f_in, external_path.open("rb") as f_ex:
        files = {
            "inhouse_file": ("inhouse.wav", f_in, "audio/wav"),
            "external_file": ("external.wav", f_ex, "audio/wav"),
        }
        data = {
            "mode": "external_to_inhouse",
            "anchor_mode": "xcorr",
            "apply": "false",
        }
        resp = client.post("/api/v1/alignments", files=files, data=data)

    assert resp.status_code == 202
    payload = resp.json()
    job_id = payload["job_id"]
    assert payload["status"] == "queued"

    # Poll until completed or failed (with timeout)
    for _ in range(40):
        r2 = client.get(f"/api/v1/alignments/{job_id}")
        assert r2.status_code == 200
        body = r2.json()
        if body["status"] in {"completed", "failed"}:
            break
    else:
        raise AssertionError("Job did not complete in time")

    assert body["status"] == "completed"
    assert body["offset_sec"] is not None
    assert isinstance(body["offset_sec"], float)
    assert body["ffmpeg_command"]
    # URLs should be relative to /media
    assert body["inhouse_url"].startswith("/media/")
    assert body["external_url"].startswith("/media/")
