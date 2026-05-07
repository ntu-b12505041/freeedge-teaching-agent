from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles

from app import config
from app.models import TeachingRequest, TeachingResponse
from app.pipeline import generate_teaching_assets


app = FastAPI(title="Teaching Monster Automated Tutor")
config.OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/static", StaticFiles(directory=config.OUTPUT_DIR), name="static")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/")
def root_health() -> dict[str, str]:
    return {"status": "ok", "endpoint": "/generate"}


@app.post("/")
def root_ping() -> dict[str, str]:
    return {"status": "ok", "endpoint": "/generate"}


@app.post("/generate", response_model=TeachingResponse)
@app.post("/api/generate", response_model=TeachingResponse)
def generate(req: TeachingRequest, request: Request) -> TeachingResponse:
    assets = generate_teaching_assets(req)
    base = config.PUBLIC_BASE_URL or str(request.base_url).rstrip("/")
    video = _url_for(base, assets["video"])
    subtitle = _url_for(base, assets["subtitle"])
    supplementary = [_url_for(base, path) for path in assets["supplementary"]]
    return TeachingResponse(video_url=video, subtitle_url=subtitle, supplementary_url=supplementary)


def _url_for(base: str, path: Path | str) -> str:
    rel = Path(path).resolve().relative_to(config.OUTPUT_DIR)
    return f"{base}/static/{rel.as_posix()}"
