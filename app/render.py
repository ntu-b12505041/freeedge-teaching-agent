from __future__ import annotations

import html
import math
import re
import shutil
import subprocess
import textwrap
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont
from PIL import JpegImagePlugin  # noqa: F401 - registers PDF/JPEG writer

from app import config
from app.models import LessonPlan


BG = "#f7f4ec"
INK = "#18202a"
MUTED = "#5b6470"
TEAL = "#147d80"
CORAL = "#d65f4b"
GOLD = "#c59224"
BLUE = "#3d6fb6"
GREEN = "#4f8b4c"


def load_font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    names = ["arialbd.ttf" if bold else "arial.ttf", "segoeuib.ttf" if bold else "segoeui.ttf"]
    for name in names:
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default()


TITLE_FONT = load_font(44, bold=True)
SUBTITLE_FONT = load_font(26)
BODY_FONT = load_font(29)
SMALL_FONT = load_font(20)
TINY_FONT = load_font(16)


def render_slides(plan: LessonPlan, out_dir: Path) -> list[Path]:
    slide_dir = out_dir / "slides"
    slide_dir.mkdir(parents=True, exist_ok=True)
    paths: list[Path] = []
    all_slides = _intro_and_content(plan)
    for idx, slide in enumerate(all_slides):
        img = Image.new("RGB", (config.VIDEO_WIDTH, config.VIDEO_HEIGHT), BG)
        draw = ImageDraw.Draw(img)
        _draw_frame(draw, idx, len(all_slides), plan)
        if idx == 0:
            _draw_intro(draw, plan)
        else:
            _draw_content(draw, slide, idx)
        path = slide_dir / f"slide_{idx:02d}.png"
        img.save(path)
        paths.append(path)
    return paths


def write_slides_pdf(slide_paths: list[Path], out_path: Path) -> None:
    images = [Image.open(path).convert("RGB") for path in slide_paths]
    first, rest = images[0], images[1:]
    first.save(out_path, save_all=True, append_images=rest, resolution=120.0)


def write_vtt(plan: LessonPlan, durations: list[float], out_path: Path) -> None:
    slides = _intro_and_content(plan)
    cursor = 0.0
    lines = ["WEBVTT", ""]
    for slide, duration in zip(slides, durations):
        start = cursor
        end = cursor + duration
        cursor = end
        text = slide.get("narration", slide.get("title", ""))
        text = re.sub(r"\s+", " ", text).strip()
        lines.append(f"{_fmt_time(start)} --> {_fmt_time(end)}")
        lines.append(html.escape(text))
        lines.append("")
    out_path.write_text("\n".join(lines), encoding="utf-8")


def make_video(slide_paths: list[Path], audio_path: Path, durations: list[float], out_path: Path) -> None:
    ffmpeg = _ffmpeg_exe()
    concat_path = out_path.parent / "slides.txt"
    lines: list[str] = []
    for path, duration in zip(slide_paths, durations):
        escaped = str(path.resolve()).replace("\\", "/").replace("'", "'\\''")
        lines.append(f"file '{escaped}'")
        lines.append(f"duration {duration:.3f}")
    last = str(slide_paths[-1].resolve()).replace("\\", "/").replace("'", "'\\''")
    lines.append(f"file '{last}'")
    concat_path.write_text("\n".join(lines), encoding="utf-8")
    cmd = [
        ffmpeg,
        "-y",
        "-f",
        "concat",
        "-safe",
        "0",
        "-i",
        str(concat_path),
        "-i",
        str(audio_path),
        "-vf",
        "format=yuv420p",
        "-r",
        "30",
        "-c:v",
        "libx264",
        "-preset",
        "veryfast",
        "-c:a",
        "aac",
        "-ar",
        "44100",
        "-b:a",
        "160k",
        "-shortest",
        str(out_path),
    ]
    subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)


def audio_duration(path: Path) -> float | None:
    ffmpeg = _ffmpeg_exe()
    proc = subprocess.run(
        [ffmpeg, "-i", str(path)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        errors="ignore",
    )
    match = re.search(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)", proc.stderr)
    if not match:
        return None
    hours, minutes, seconds = match.groups()
    return int(hours) * 3600 + int(minutes) * 60 + float(seconds)


def clean_output_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    (path / "slides").mkdir(parents=True, exist_ok=True)


def estimate_durations(plan: LessonPlan, total_duration: float | None = None) -> list[float]:
    slides = _intro_and_content(plan)
    weights = [max(14, len(s.get("narration", "").split())) for s in slides]
    if total_duration is None:
        total_duration = sum(weights) / config.TARGET_WPM * 60
    total_duration = max(total_duration, len(slides) * 5.0)
    raw = [total_duration * w / sum(weights) for w in weights]
    return [max(4.0, duration) for duration in raw]


def narration_text(plan: LessonPlan) -> str:
    parts = [plan.hook]
    parts.extend(slide.narration for slide in plan.slides)
    parts.append("References used: " + "; ".join(plan.references))
    return "\n\n".join(parts)


def _intro_and_content(plan: LessonPlan) -> list[dict[str, object]]:
    intro = {
        "title": plan.title,
        "narration": plan.hook,
        "bullets": plan.learning_goals[:3],
        "visual": "concept_map",
        "check_question": plan.learner_level,
    }
    return [intro] + [slide.model_dump() for slide in plan.slides]


def _draw_frame(draw: ImageDraw.ImageDraw, idx: int, total: int, plan: LessonPlan) -> None:
    draw.rectangle((0, 0, config.VIDEO_WIDTH, 18), fill=TEAL)
    draw.rectangle((0, config.VIDEO_HEIGHT - 42, config.VIDEO_WIDTH, config.VIDEO_HEIGHT), fill="#e6e0d4")
    progress = int(config.VIDEO_WIDTH * (idx + 1) / total)
    draw.rectangle((0, config.VIDEO_HEIGHT - 42, progress, config.VIDEO_HEIGHT), fill=GOLD)
    footer = f"{idx + 1}/{total}  |  AI-generated lesson draft  |  Sources shown in final slide/PDF"
    draw.text((36, config.VIDEO_HEIGHT - 31), footer, fill=INK, font=TINY_FONT)
    draw.text((config.VIDEO_WIDTH - 360, 28), textwrap.shorten(plan.learner_level, 44), fill=MUTED, font=SMALL_FONT)


def _draw_intro(draw: ImageDraw.ImageDraw, plan: LessonPlan) -> None:
    draw.text((72, 82), _wrap_title(plan.title, 28), fill=INK, font=TITLE_FONT, spacing=8)
    draw.text((76, 210), _wrap_text(plan.hook, 50), fill=TEAL, font=SUBTITLE_FONT, spacing=8)
    _draw_goal_panel(draw, plan.learning_goals)
    _draw_visual(draw, "concept_map", (720, 238, 1160, 560))


def _draw_content(draw: ImageDraw.ImageDraw, slide: dict[str, object], idx: int) -> None:
    title = str(slide.get("title", ""))
    draw.text((66, 70), _wrap_title(title, 35), fill=INK, font=TITLE_FONT, spacing=6)
    bullets = [str(item) for item in slide.get("bullets", [])][:5]
    y = 185
    palette = [TEAL, CORAL, BLUE, GREEN, GOLD]
    for i, bullet in enumerate(bullets):
        color = palette[i % len(palette)]
        wrapped = _wrap_text(bullet, 35)
        draw.rounded_rectangle((78, y + 7, 104, y + 33), radius=13, fill=color)
        draw.text((126, y), wrapped, fill=INK, font=BODY_FONT, spacing=7)
        line_count = max(1, wrapped.count("\n") + 1)
        y += max(68, line_count * 38 + 24)
    question = slide.get("check_question")
    if question:
        draw.rounded_rectangle((72, 574, 650, 640), radius=8, outline=TEAL, width=3, fill="#fffaf0")
        draw.text((96, 590), _wrap_text(str(question), 38), fill=TEAL, font=SMALL_FONT, spacing=5)
    _draw_visual(draw, str(slide.get("visual", "concept_map")), (735, 178, 1168, 572))


def _draw_goal_panel(draw: ImageDraw.ImageDraw, goals: list[str]) -> None:
    draw.rounded_rectangle((72, 348, 632, 628), radius=8, fill="#fffaf0", outline="#ddd2bd", width=2)
    draw.text((104, 375), "By the end, you can...", fill=INK, font=SUBTITLE_FONT)
    y = 426
    for goal in goals[:3]:
        wrapped = _wrap_text(goal, 35)
        draw.ellipse((108, y + 8, 126, y + 26), fill=CORAL)
        draw.text((146, y), wrapped, fill=INK, font=SMALL_FONT, spacing=4)
        line_count = max(1, wrapped.count("\n") + 1)
        y += max(52, line_count * 27 + 18)


def _draw_visual(draw: ImageDraw.ImageDraw, visual: str, box: tuple[int, int, int, int]) -> None:
    x1, y1, x2, y2 = box
    draw.rounded_rectangle(box, radius=8, fill="#ffffff", outline="#d8d0c0", width=2)
    cx = (x1 + x2) // 2
    cy = (y1 + y2) // 2
    if visual == "process":
        labels = ["Input", "Rule", "Output"]
        xs = [x1 + 78, cx, x2 - 78]
        for x, label, color in zip(xs, labels, [BLUE, TEAL, CORAL]):
            draw.ellipse((x - 50, cy - 50, x + 50, cy + 50), fill=color)
            draw.text((x - 33, cy - 12), label, fill="white", font=SMALL_FONT)
        draw.line((xs[0] + 55, cy, xs[1] - 55, cy), fill=INK, width=5)
        draw.line((xs[1] + 55, cy, xs[2] - 55, cy), fill=INK, width=5)
    elif visual == "comparison":
        draw.rectangle((x1 + 55, y1 + 70, cx - 18, y2 - 70), fill="#e9f3f3", outline=TEAL, width=3)
        draw.rectangle((cx + 18, y1 + 70, x2 - 55, y2 - 70), fill="#faece7", outline=CORAL, width=3)
        draw.text((x1 + 88, y1 + 96), "Looks similar", fill=TEAL, font=SMALL_FONT)
        draw.text((cx + 56, y1 + 96), "Works different", fill=CORAL, font=SMALL_FONT)
        draw.line((cx, y1 + 55, cx, y2 - 55), fill="#cfc6b4", width=3)
    elif visual == "graph":
        draw.line((x1 + 70, y2 - 70, x2 - 60, y2 - 70), fill=INK, width=4)
        draw.line((x1 + 70, y2 - 70, x1 + 70, y1 + 60), fill=INK, width=4)
        points = []
        for i in range(90):
            t = i / 89
            x = x1 + 85 + t * (x2 - x1 - 170)
            y = cy - math.sin(t * math.pi * 2) * 80 - t * 50
            points.append((x, y))
        draw.line(points, fill=BLUE, width=5)
    elif visual == "worked_example":
        for row in range(3):
            for col in range(3):
                x = x1 + 116 + col * 92
                y = y1 + 86 + row * 72
                draw.rounded_rectangle((x, y, x + 64, y + 44), radius=6, fill="#eef2f6", outline=BLUE)
        draw.text((x1 + 145, y2 - 108), "tiny example -> pattern", fill=INK, font=SMALL_FONT)
    elif visual == "checkpoint":
        for i, color in enumerate([TEAL, GOLD, CORAL]):
            y = y1 + 96 + i * 86
            draw.rounded_rectangle((x1 + 84, y, x2 - 84, y + 48), radius=24, fill=color)
            draw.text((x1 + 126, y + 12), f"Check {i + 1}", fill="white", font=SMALL_FONT)
    else:
        nodes = [(cx, y1 + 86, TEAL, "Core"), (x1 + 110, cy + 50, BLUE, "Known"), (x2 - 110, cy + 50, CORAL, "New")]
        for ax, ay, _, _ in nodes[1:]:
            draw.line((cx, y1 + 136, ax, ay), fill="#b9b0a0", width=5)
        for ax, ay, color, label in nodes:
            draw.ellipse((ax - 58, ay - 58, ax + 58, ay + 58), fill=color)
            draw.text((ax - 32, ay - 12), label, fill="white", font=SMALL_FONT)


def _wrap_title(text: str, width: int) -> str:
    return "\n".join(textwrap.wrap(text, width=width, max_lines=2, placeholder="..."))


def _wrap_text(text: str, width: int) -> str:
    return "\n".join(textwrap.wrap(text, width=width))


def _fmt_time(value: float) -> str:
    hours = int(value // 3600)
    minutes = int((value % 3600) // 60)
    seconds = value % 60
    return f"{hours:02d}:{minutes:02d}:{seconds:06.3f}"


def _ffmpeg_exe() -> str:
    local_tools = sorted((config.ROOT_DIR / "tools" / "ffmpeg").glob("**/ffmpeg.exe"))
    if local_tools:
        return str(local_tools[0])
    try:
        import imageio_ffmpeg

        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception as exc:
        ffmpeg = shutil.which("ffmpeg")
        if ffmpeg:
            return ffmpeg
        raise RuntimeError(
            "ffmpeg is required to create MP4 output. Install imageio-ffmpeg or system ffmpeg."
        ) from exc
