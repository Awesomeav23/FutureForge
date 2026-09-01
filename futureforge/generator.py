"""Narrative generation: the text a student actually reads.

Two interchangeable backends behind one method:

    OpenAIGenerator   -- calls the OpenAI API for guidance written for this student
    TemplateGenerator -- deterministic offline text built from the same match data

The app picks OpenAI when OPENAI_API_KEY is set and the `openai` package is
importable, and otherwise falls back to templates so the GUI, CLI, batch runner and
tests all work with no key and no network. Generated text is cached on disk by
(profile fingerprint, career id) so re-ranking the same student costs nothing.
"""
from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Optional, Tuple

from .dataset import label
from .models import Match, Recommendation, StudentProfile


def _article(word: str) -> str:
    return "an" if word[:1].lower() in "aeiou" else "a"

DEFAULT_MODEL = os.environ.get("FUTUREFORGE_MODEL", "gpt-4o-mini")
CACHE_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".cache", "recommendations.json"
)

SYSTEM_PROMPT = (
    "You are a high school career counselor. You are talking to a 15-18 year old student. "
    "Be concrete, encouraging and honest -- name the real tradeoffs (cost of school, hours, "
    "physical demands) instead of hype. Never invent salary numbers or degree requirements: "
    "use only the ones given to you. Keep every sentence plain enough for a 9th grader."
)


def _labels(dimension: str, tags: List[str]) -> str:
    return ", ".join(label(dimension, t) for t in tags) if tags else "none"


class BaseGenerator:
    """Interface + the shared prompt/context builder."""

    source = "base"

    def generate(self, profile: StudentProfile, match: Match) -> Recommendation:
        raise NotImplementedError

    @staticmethod
    def context(profile: StudentProfile, match: Match) -> Dict[str, Any]:
        career = match.career
        return {
            "student": {
                "name": profile.name,
                "grade": profile.grade,
                "interests": _labels("interests", profile.interests),
                "subjects": _labels("subjects", profile.subjects),
                "work_style": _labels("work_style", profile.work_style),
                "values": _labels("values", profile.values),
                "years_of_school_willing": profile.max_education_years,
                "how_much_pay_matters_1_to_5": profile.salary_priority,
            },
            "career": {
                "title": career.title,
                "field": career.field,
                "description": career.description,
                "education_required": career.education_label,
                "education_note": career.education_note,
                "salary_range": career.salary.formatted(),
                "job_outlook": career.outlook,
            },
            "match": {
                "overall_percent": match.percent,
                "scores": {
                    d.name: {
                        "score": round(d.score, 2),
                        "weight": round(d.weight, 2),
                        "student_overlap": _labels(d.name, d.matched),
                    }
                    for d in match.dimensions
                },
                "needs_more_school_than_student_wanted": match.feasibility < 1.0,
            },
        }


class TemplateGenerator(BaseGenerator):
    """Offline, deterministic, no network. Same shape as the OpenAI output."""

    source = "offline"

    def generate(self, profile: StudentProfile, match: Match) -> Recommendation:
        career = match.career
        interests = match.dimension("interests").matched
        subjects = match.dimension("subjects").matched
        style = match.dimension("work_style").matched
        values = match.dimension("values").matched

        reasons: List[str] = []
        if interests:
            reasons.append("you said you like {}".format(_labels("interests", interests).lower()))
        if subjects:
            reasons.append("your subjects line up ({})".format(_labels("subjects", subjects).lower()))
        if style:
            reasons.append("the day-to-day is {}".format(_labels("work_style", style).lower()))
        if values:
            reasons.append("it fits what matters to you: {}".format(_labels("values", values).lower()))
        why = "{} is a {}% match because {}. {}".format(
            career.title,
            match.percent,
            "; ".join(reasons) if reasons else "it sits closest to the answers you gave",
            career.description,
        )
        if match.feasibility < 1.0:
            why += (
                " Heads up: this one needs about {} years of school after high school, more than the {} "
                "you said you wanted -- worth knowing before you commit.".format(
                    career.education_years, profile.max_education_years
                )
            )

        next_steps = [
            "Look up the exact {} programs near you and what they cost.".format(career.education_label.lower()),
            "Ask to shadow or interview someone working as {} {} for one afternoon.".format(
                _article(career.title), career.title.lower()
            ),
            "Find one club, part-time job or volunteer role that touches this work before you graduate.",
        ]
        if career.education_years <= 2:
            next_steps.append("Check whether your high school offers dual-enrollment credit toward this.")
        else:
            next_steps.append("Map which colleges accept your current GPA into this major, and their aid deadlines.")

        courses = [label("subjects", s) for s in career.subjects]

        day = (
            "Most days as {} {} you are {}. Pay runs {} and the field is projected at {}. "
            "The requirement to get in is: {}.".format(
                _article(career.title),
                career.title.lower(),
                _labels("work_style", career.work_style).lower(),
                career.salary.formatted(),
                career.outlook,
                career.education_note,
            )
        )

        return Recommendation(
            match=match,
            why_it_fits=why,
            next_steps=next_steps,
            courses=courses,
            day_in_the_life=day,
            related_careers=[],  # filled in by the recommender from the ranked list
            source=self.source,
        )


class OpenAIGenerator(BaseGenerator):
    """Calls the OpenAI API; falls back to templates on any error."""

    source = "openai"

    def __init__(self, model: Optional[str] = None, api_key: Optional[str] = None) -> None:
        from openai import OpenAI  # imported lazily so the app runs without the package

        self.model = model or DEFAULT_MODEL
        self.client = OpenAI(api_key=api_key or os.environ.get("OPENAI_API_KEY"))
        self._fallback = TemplateGenerator()

    def generate(self, profile: StudentProfile, match: Match) -> Recommendation:
        prompt = (
            "Here is a student's questionnaire and one career our matching engine ranked for them:\n\n"
            + json.dumps(self.context(profile, match), indent=2)
            + "\n\nWrite guidance for this specific student. Respond with JSON only, with keys:\n"
            '  "why_it_fits": 2-3 sentences tying the career to THEIR answers,\n'
            '  "next_steps": 3-4 concrete actions they can take this school year,\n'
            '  "courses": 3-5 high school classes to take,\n'
            '  "day_in_the_life": one short paragraph on what the work is actually like,\n'
            '  "related_careers": 2 adjacent job titles worth a look.\n'
            "Quote the salary range and education requirement exactly as given."
        )
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                response_format={"type": "json_object"},
                temperature=0.7,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": prompt},
                ],
            )
            data = json.loads(response.choices[0].message.content)
            return Recommendation(
                match=match,
                why_it_fits=str(data["why_it_fits"]).strip(),
                next_steps=[str(s) for s in data.get("next_steps", [])],
                courses=[str(c) for c in data.get("courses", [])],
                day_in_the_life=str(data.get("day_in_the_life", "")).strip(),
                related_careers=[str(r) for r in data.get("related_careers", [])],
                source=self.source,
            )
        except Exception as exc:  # noqa: BLE001 -- a demo must never crash mid-presentation
            fallback = self._fallback.generate(profile, match)
            return Recommendation(
                match=fallback.match,
                why_it_fits=fallback.why_it_fits,
                next_steps=fallback.next_steps,
                courses=fallback.courses,
                day_in_the_life=fallback.day_in_the_life,
                related_careers=fallback.related_careers,
                source="offline (OpenAI call failed: {})".format(type(exc).__name__),
            )


class CachingGenerator(BaseGenerator):
    """Wraps a generator with a small JSON disk cache keyed by (profile, career)."""

    def __init__(self, inner: BaseGenerator, path: str = CACHE_PATH) -> None:
        self.inner = inner
        self.path = path
        self._cache: Dict[str, Dict[str, Any]] = {}
        if os.path.exists(path):
            try:
                with open(path, "r") as handle:
                    self._cache = json.load(handle)
            except (ValueError, OSError):
                self._cache = {}

    @property
    def source(self) -> str:  # type: ignore[override]
        return self.inner.source

    def generate(self, profile: StudentProfile, match: Match) -> Recommendation:
        key = "{}:{}:{}".format(profile.fingerprint(), match.career.id, self.inner.source)
        cached = self._cache.get(key)
        if cached:
            return Recommendation(
                match=match,
                why_it_fits=cached["why_it_fits"],
                next_steps=cached["next_steps"],
                courses=cached["courses"],
                day_in_the_life=cached["day_in_the_life"],
                related_careers=cached["related_careers"],
                source=cached["source"],
            )

        result = self.inner.generate(profile, match)
        self._cache[key] = {
            "why_it_fits": result.why_it_fits,
            "next_steps": result.next_steps,
            "courses": result.courses,
            "day_in_the_life": result.day_in_the_life,
            "related_careers": result.related_careers,
            "source": result.source,
        }
        self._flush()
        return result

    def _flush(self) -> None:
        try:
            os.makedirs(os.path.dirname(self.path), exist_ok=True)
            with open(self.path, "w") as handle:
                json.dump(self._cache, handle, indent=1)
        except OSError:
            pass  # a read-only checkout should not break the app


def openai_available() -> bool:
    if not os.environ.get("OPENAI_API_KEY"):
        return False
    try:
        import openai  # noqa: F401
    except ImportError:
        return False
    return True


def get_generator(prefer_openai: bool = True, cache: bool = True) -> Tuple[BaseGenerator, str]:
    """Return (generator, human-readable status line for the UI)."""
    if prefer_openai and openai_available():
        generator: BaseGenerator = OpenAIGenerator()
        status = "AI mode - guidance written by OpenAI ({})".format(DEFAULT_MODEL)
    else:
        generator = TemplateGenerator()
        if not os.environ.get("OPENAI_API_KEY"):
            status = "Offline mode - set OPENAI_API_KEY for AI-written guidance"
        else:
            status = "Offline mode - `pip install openai` for AI-written guidance"
    if cache:
        generator = CachingGenerator(generator)
    return generator, status
