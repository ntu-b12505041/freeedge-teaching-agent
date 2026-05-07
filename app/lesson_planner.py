from __future__ import annotations

import json
import textwrap

from app import config
from app.models import LessonPlan, SlidePlan, TeachingRequest
from app.references import default_references, infer_domain


SYSTEM_PROMPT = """You design concise, accurate educational videos for secondary students.
Return JSON only. Build strong pedagogical scaffolding:
- adapt vocabulary to the student_persona
- avoid unsupported claims
- use brief analogies, Socratic checks, and visual suggestions
- keep narration clear for voiceover
- use English as the main language
- cite only real, general educational references supplied in the prompt
"""


def plan_lesson(req: TeachingRequest) -> LessonPlan:
    if config.OPENAI_API_KEY:
        try:
            return _plan_with_openai(req)
        except Exception as exc:
            fallback = _fallback_plan(req)
            fallback.metadata["planner_warning"] = f"OpenAI planner failed; used fallback. {exc}"
            return fallback
    return _fallback_plan(req)


def _plan_with_openai(req: TeachingRequest) -> LessonPlan:
    from openai import OpenAI

    refs = default_references(req.course_requirement)
    domain = infer_domain(req.course_requirement)
    schema = {
        "title": "short video title",
        "learner_level": "one sentence about assumed level",
        "hook": "one engaging opening question",
        "learning_goals": ["goal 1", "goal 2", "goal 3"],
        "slides": [
            {
                "title": "slide title",
                "narration": "80-130 spoken words",
                "bullets": ["3 to 5 short bullets"],
                "visual": "one of: concept_map, comparison, process, graph, worked_example, checkpoint",
                "check_question": "optional short question",
            }
        ],
        "references": refs,
    }
    prompt = f"""
Course requirement:
{req.course_requirement}

Student persona:
{req.student_persona}

Likely domain: {domain}
Allowed references:
{chr(10).join("- " + r for r in refs)}

Create 7-9 slides. Keep the total narration under about 900 words.
JSON shape:
{json.dumps(schema, ensure_ascii=False)}
"""
    client = OpenAI(api_key=config.OPENAI_API_KEY)
    response = client.chat.completions.create(
        model=config.OPENAI_TEXT_MODEL,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
        response_format={"type": "json_object"},
        temperature=0.35,
    )
    data = json.loads(response.choices[0].message.content or "{}")
    data["references"] = data.get("references") or refs
    data["metadata"] = {"planner": "openai", "model": config.OPENAI_TEXT_MODEL}
    return LessonPlan.model_validate(data)


def _fallback_plan(req: TeachingRequest) -> LessonPlan:
    topic = _clean_topic(req.course_requirement)
    persona = req.student_persona.strip()
    refs = default_references(topic)
    core = textwrap.shorten(topic, width=72, placeholder="...")
    slides = [
        SlidePlan(
            title=f"Why {core} matters",
            narration=(
                f"Let's build {topic} from the ground up. For this learner, I will avoid unnecessary advanced notation "
                f"and start from concrete intuition. The key question is simple: what problem does this idea solve, "
                "and what changes when we understand it?"
            ),
            bullets=["Start from the problem", "Name the new idea", "Connect it to prior knowledge"],
            visual="concept_map",
            check_question="What would be hard to explain without this idea?",
        ),
        SlidePlan(
            title="The mental model",
            narration=(
                "A useful mental model is to treat the concept as a small machine. Inputs go in, a rule acts on them, "
                "and an output becomes easier to reason about. We will track those three pieces: input, rule, and output."
            ),
            bullets=["Input: what we already know", "Rule: the central mechanism", "Output: what becomes clearer"],
            visual="process",
        ),
        SlidePlan(
            title="Step-by-step mechanism",
            narration=(
                f"Now we walk through {topic} one step at a time. First identify the objects involved. Second, describe "
                "how they interact. Third, check whether the result matches common sense. This prevents memorizing words "
                "without understanding the structure."
            ),
            bullets=["Identify the objects", "Describe the interaction", "Check the result"],
            visual="process",
            check_question="Which step is most likely to cause confusion?",
        ),
        SlidePlan(
            title="A concrete example",
            narration=(
                "Examples turn an abstract rule into something testable. We choose small numbers or familiar situations, "
                "because the goal is not to impress the viewer; the goal is to let the viewer predict what happens next."
            ),
            bullets=["Use a tiny example", "Predict before calculating", "Compare prediction with result"],
            visual="worked_example",
        ),
        SlidePlan(
            title="Common trap",
            narration=(
                "A common trap is to copy the final formula or definition while missing the reason behind it. When that "
                "happens, similar-looking problems feel unrelated. The fix is to ask: what stays the same, and what changes?"
            ),
            bullets=["Do not memorize too early", "Look for invariants", "Explain the rule in plain language"],
            visual="comparison",
        ),
        SlidePlan(
            title="Quick checkpoint",
            narration=(
                "Pause and test the idea. If you can explain the mechanism without looking at the slide, apply it to a "
                "new tiny example, and identify one limitation, then you understand more than the vocabulary."
            ),
            bullets=["Explain it aloud", "Try a new tiny case", "Name one limitation"],
            visual="checkpoint",
            check_question="Can you teach the idea in two sentences?",
        ),
        SlidePlan(
            title="Takeaway",
            narration=(
                f"The takeaway is that {topic} is not just a term. It is a tool for organizing a problem so the next "
                f"step becomes visible. For {persona}, the best next move is to practice with small examples before "
                "adding formal notation."
            ),
            bullets=["Core idea", "Why it works", "How to practice next"],
            visual="concept_map",
        ),
    ]
    return LessonPlan(
        title=core,
        learner_level=f"Adapted for: {persona}",
        hook=f"What problem becomes easier once we understand {core}?",
        learning_goals=[
            f"Explain the purpose of {core}.",
            "Trace the mechanism step by step.",
            "Apply the idea to a small example and avoid a common misconception.",
        ],
        slides=slides,
        references=refs,
        metadata={"planner": "fallback"},
    )


def _clean_topic(text: str) -> str:
    topic = text.strip().rstrip(".")
    lowered = topic.lower()
    for prefix in ["explain ", "teach ", "introduce ", "help me understand "]:
        if lowered.startswith(prefix):
            topic = topic[len(prefix) :]
            break
    for suffix in [" to a high school student", " for a high school student"]:
        if topic.lower().endswith(suffix):
            topic = topic[: -len(suffix)]
    return topic.strip().rstrip(".") or text.strip()
