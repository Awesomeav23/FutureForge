"""Core data types for FutureForge.

Pure stdlib, no I/O -- the GUI, CLI, batch runner and tests all share these.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

# Education ladder: level -> typical years of school/training after high school.
EDUCATION_YEARS: Dict[str, int] = {
    "high_school": 0,
    "certificate": 1,
    "associate": 2,
    "bachelor": 4,
    "master": 6,
    "doctorate": 8,
}

EDUCATION_LABELS: Dict[str, str] = {
    "high_school": "High school diploma",
    "certificate": "Certificate / apprenticeship",
    "associate": "Associate degree (2 yr)",
    "bachelor": "Bachelor's degree (4 yr)",
    "master": "Master's degree (6 yr)",
    "doctorate": "Doctorate / professional degree (8 yr)",
}

# The four weighted inputs. Weights are defaults; the GUI lets you retune them live.
DIMENSIONS = ("interests", "subjects", "work_style", "values")
DEFAULT_WEIGHTS: Dict[str, float] = {
    "interests": 0.35,
    "subjects": 0.25,
    "work_style": 0.20,
    "values": 0.20,
}

DIMENSION_LABELS = {
    "interests": "What you enjoy",
    "subjects": "School subjects",
    "work_style": "Work style",
    "values": "What matters to you",
}


@dataclass(frozen=True)
class SalaryRange:
    low: int
    median: int
    high: int

    def formatted(self) -> str:
        return "${:,} - ${:,} (median ${:,})".format(self.low, self.high, self.median)

    def to_dict(self) -> Dict[str, int]:
        return {"low": self.low, "median": self.median, "high": self.high}


@dataclass(frozen=True)
class Career:
    id: str
    title: str
    field: str
    education: str
    education_note: str
    salary: SalaryRange
    outlook: str
    description: str
    interests: List[str]
    subjects: List[str]
    work_style: List[str]
    values: List[str]

    @property
    def education_years(self) -> int:
        return EDUCATION_YEARS[self.education]

    @property
    def education_label(self) -> str:
        return EDUCATION_LABELS[self.education]

    def tags(self, dimension: str) -> List[str]:
        return getattr(self, dimension)

    @classmethod
    def from_dict(cls, raw: Dict[str, Any]) -> "Career":
        salary = raw["salary"]
        return cls(
            id=raw["id"],
            title=raw["title"],
            field=raw["field"],
            education=raw["education"],
            education_note=raw["education_note"],
            salary=SalaryRange(salary["low"], salary["median"], salary["high"]),
            outlook=raw.get("outlook", "n/a"),
            description=raw["description"],
            interests=list(raw["interests"]),
            subjects=list(raw["subjects"]),
            work_style=list(raw["work_style"]),
            values=list(raw["values"]),
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "field": self.field,
            "education": self.education,
            "education_note": self.education_note,
            "salary": self.salary.to_dict(),
            "outlook": self.outlook,
            "description": self.description,
            "interests": self.interests,
            "subjects": self.subjects,
            "work_style": self.work_style,
            "values": self.values,
        }


@dataclass
class StudentProfile:
    """The four weighted inputs a student gives us.

    1. interests    2. subjects    3. work_style
    4. values  (+ how many years of school they'll do, + how much pay matters)
    """

    name: str = "Student"
    grade: str = "11"
    interests: List[str] = field(default_factory=list)
    subjects: List[str] = field(default_factory=list)
    work_style: List[str] = field(default_factory=list)
    values: List[str] = field(default_factory=list)
    max_education_years: int = 4
    salary_priority: int = 3  # 1 = pay barely matters, 5 = pay matters a lot
    weights: Dict[str, float] = field(default_factory=lambda: dict(DEFAULT_WEIGHTS))

    def tags(self, dimension: str) -> List[str]:
        return getattr(self, dimension)

    def normalized_weights(self) -> Dict[str, float]:
        raw = {d: max(0.0, float(self.weights.get(d, DEFAULT_WEIGHTS[d]))) for d in DIMENSIONS}
        total = sum(raw.values())
        if total <= 0:
            return dict(DEFAULT_WEIGHTS)
        return {d: v / total for d, v in raw.items()}

    def fingerprint(self) -> str:
        """Stable hash of the answers -- used as a cache key for generated text."""
        payload = json.dumps(self.to_dict(), sort_keys=True).encode("utf-8")
        return hashlib.sha1(payload).hexdigest()[:12]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "grade": self.grade,
            "interests": sorted(self.interests),
            "subjects": sorted(self.subjects),
            "work_style": sorted(self.work_style),
            "values": sorted(self.values),
            "max_education_years": self.max_education_years,
            "salary_priority": self.salary_priority,
            "weights": {d: round(self.normalized_weights()[d], 4) for d in DIMENSIONS},
        }

    @classmethod
    def from_dict(cls, raw: Dict[str, Any]) -> "StudentProfile":
        return cls(
            name=raw.get("name", "Student"),
            grade=str(raw.get("grade", "11")),
            interests=list(raw.get("interests", [])),
            subjects=list(raw.get("subjects", [])),
            work_style=list(raw.get("work_style", [])),
            values=list(raw.get("values", [])),
            max_education_years=int(raw.get("max_education_years", 4)),
            salary_priority=int(raw.get("salary_priority", 3)),
            weights=dict(raw.get("weights") or DEFAULT_WEIGHTS),
        )


@dataclass(frozen=True)
class DimensionScore:
    """One of the four inputs, scored against one career."""

    name: str
    weight: float
    score: float
    matched: List[str]

    @property
    def contribution(self) -> float:
        return self.weight * self.score


@dataclass(frozen=True)
class Match:
    career: Career
    total: float
    dimensions: List[DimensionScore]
    feasibility: float  # 1.0 = fits the student's schooling limit; < 1.0 = over it

    @property
    def percent(self) -> int:
        return int(round(self.total * 100))

    def dimension(self, name: str) -> DimensionScore:
        for d in self.dimensions:
            if d.name == name:
                return d
        raise KeyError(name)

    def matched_tags(self) -> List[str]:
        out: List[str] = []
        for d in self.dimensions:
            out.extend(d.matched)
        return out

    def to_dict(self) -> Dict[str, Any]:
        return {
            "career": self.career.to_dict(),
            "match_percent": self.percent,
            "feasibility": round(self.feasibility, 3),
            "dimensions": [
                {
                    "name": d.name,
                    "weight": round(d.weight, 3),
                    "score": round(d.score, 3),
                    "matched": d.matched,
                }
                for d in self.dimensions
            ],
        }


@dataclass(frozen=True)
class Recommendation:
    """A match plus the guidance text written for this specific student."""

    match: Match
    why_it_fits: str
    next_steps: List[str]
    courses: List[str]
    day_in_the_life: str
    related_careers: List[str]
    source: str  # "openai" or "offline"

    @property
    def career(self) -> Career:
        return self.match.career

    def to_dict(self) -> Dict[str, Any]:
        data = self.match.to_dict()
        data.update(
            {
                "why_it_fits": self.why_it_fits,
                "next_steps": self.next_steps,
                "courses": self.courses,
                "day_in_the_life": self.day_in_the_life,
                "related_careers": self.related_careers,
                "source": self.source,
            }
        )
        return data
