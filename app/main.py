import logging
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.config import settings
from app.routes.alignment import router as alignment_router

logging.basicConfig(level=logging.INFO)

app = FastAPI(title=settings.APP_NAME)

# CORS for local frontend dev
origins = [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Ensure media root exists and mount as /media
media_root: Path = settings.MEDIA_ROOT
media_root.mkdir(parents=True, exist_ok=True)
app.mount("/media", StaticFiles(directory=str(media_root)), name="media")


@app.get("/api/v1/health")
async def health():
    return {"status": "ok"}


app.include_router(alignment_router)
