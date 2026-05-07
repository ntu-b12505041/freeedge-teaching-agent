from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class TeachingRequest(BaseModel):
    request_id: str = Field(..., min_length=1)
    course_requirement: str = Field(..., min_length=1)
    student_persona: str = Field(..., min_length=1)


class TeachingResponse(BaseModel):
    video_url: str
    subtitle_url: str | None = None
    supplementary_url: str | list[str] | None = None


class SlidePlan(BaseModel):
    title: str
    narration: str
    bullets: list[str] = Field(default_factory=list)
    visual: str = "concept_map"
    check_question: str | None = None


class LessonPlan(BaseModel):
    title: str
    learner_level: str
    hook: str
    learning_goals: list[str]
    slides: list[SlidePlan]
    references: list[str]
    metadata: dict[str, Any] = Field(default_factory=dict)
