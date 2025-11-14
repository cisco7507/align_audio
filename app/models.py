from pydantic import BaseModel, Field
from typing import Optional, List


class AlignmentParameters(BaseModel):
    sr: int = 48000
    mode: str = Field(
        "external_to_inhouse",
        pattern=r"^(external_to_inhouse|inhouse_to_external)$",
    )
    anchor_mode: str = Field("xcorr", pattern=r"^(xcorr|content)$")
    prefer_trim: bool = False
    threshold_db: Optional[float] = None
    max_search: float = 60.0
    ref_start_sec: float = 0.0
    search_start_sec: float = 0.0
    analysis_sec: float = 30.0
    template_sec: float = 4.0
    hop_sec: float = 0.1
    min_sim: float = 0.78
    generate_waveform_png: bool = True
    generate_similarity_png: bool = True
    apply: bool = False


class AlignmentJobResponse(BaseModel):
    job_id: str
    status: str


class AlignmentResultResponse(BaseModel):
    job_id: str
    status: str
    offset_sec: Optional[float] = None
    ffmpeg_command: Optional[str] = None
    inhouse_url: Optional[str] = None
    external_url: Optional[str] = None
    aligned_audio_url: Optional[str] = None
    waveform_png_url: Optional[str] = None
    similarity_png_url: Optional[str] = None
    logs: List[str] = []
