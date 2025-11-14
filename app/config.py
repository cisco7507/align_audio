from pathlib import Path
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    APP_NAME: str = "Align Audio Service"
    MEDIA_ROOT: Path = Path("data")
    UPLOAD_DIR_NAME: str = "uploads"
    RESULTS_DIR_NAME: str = "results"

    class Config:
        env_prefix = "ALIGN_"


settings = Settings()
