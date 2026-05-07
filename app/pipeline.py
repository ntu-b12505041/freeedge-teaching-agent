from __future__ import annotations

import json
from pathlib import Path

from app import config
from app.lesson_planner import plan_lesson
from app.models import TeachingRequest
from app.render import (
    audio_duration,
    clean_output_dir,
    estimate_durations,
    make_video,
    narration_text,
    render_slides,
    write_slides_pdf,
    write_vtt,
)
from app.tts import synthesize_voiceover


def generate_teaching_assets(req: TeachingRequest) -> dict[str, Path | str | list[str]]:
    safe_id = "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in req.request_id)
    out_dir = config.OUTPUT_DIR / safe_id
    clean_output_dir(out_dir)

    plan = plan_lesson(req)
    (out_dir / "lesson_plan.json").write_text(plan.model_dump_json(indent=2), encoding="utf-8")

    slide_paths = render_slides(plan, out_dir)
    pdf_path = out_dir / "slides.pdf"
    write_slides_pdf(slide_paths, pdf_path)

    audio_path = out_dir / "narration.mp3"
    voice_provider = synthesize_voiceover(narration_text(plan), audio_path)
    if voice_provider in {"silent-fallback", "windows-sapi"}:
        audio_path = audio_path.with_suffix(".wav")

    total_duration = audio_duration(audio_path)
    durations = estimate_durations(plan, total_duration)
    subtitle_path = out_dir / "subtitles.vtt"
    write_vtt(plan, durations, subtitle_path)

    video_path = out_dir / "video.mp4"
    make_video(slide_paths, audio_path, durations, video_path)

    manifest = {
        "request": req.model_dump(),
        "voice_provider": voice_provider,
        "files": {
            "video": str(video_path),
            "subtitle": str(subtitle_path),
            "slides_pdf": str(pdf_path),
            "lesson_plan": str(out_dir / "lesson_plan.json"),
        },
        "planner": plan.metadata,
    }
    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    return {
        "video": video_path,
        "subtitle": subtitle_path,
        "supplementary": [pdf_path],
        "voice_provider": voice_provider,
    }
