"""The weighted matching engine.

Scores a student against every career on four independently weighted inputs:

    1. interests    2. school subjects    3. work style    4. priorities/values

Dimensions 1-3 are cosine similarity over binary tag sets. Dimension 4 blends the
student's value tags with how much pay matters to them and how many years of school
they are willing to do. A global feasibility multiplier then pushes careers that
need more schooling than the student wants down the list without hiding them.

Pure functions over the models -- no I/O, no network, no globals.
"""
from __future__ import annotations

import math
from typing import Dict, List, Optional, Sequence

from .models import DIMENSIONS, Career, DimensionScore, Match, StudentProfile

# Dimension 4 internals: value-tag overlap dominates, then pay fit, then schooling fit.
VALUE_TAG_SHARE = 0.60
SALARY_SHARE = 0.25
EDUCATION_SHARE = 0.15

# How hard to penalize schooling beyond what the student said they would do.
EDUCATION_FIT_DECAY = 0.25   # per extra year, inside dimension 4
FEASIBILITY_DECAY = 0.08     # per extra year, applied to the whole score
FEASIBILITY_FLOOR = 0.50     # never zero a career out -- keep it visible, just lower


def cosine(student_tags: Sequence[str], career_tags: Sequence[str]) -> float:
    """Cosine similarity of two binary tag sets: |A n B| / sqrt(|A| * |B|)."""
    a, b = set(student_tags), set(career_tags)
    if not a or not b:
        return 0.0
    return len(a & b) / math.sqrt(len(a) * len(b))


def overlap(student_tags: Sequence[str], career_tags: Sequence[str]) -> List[str]:
    """The specific tags that matched -- this is what makes a result explainable."""
    return [t for t in career_tags if t in set(student_tags)]


class SalaryScale:
    """Percentile rank of each career's median salary within the dataset."""

    def __init__(self, careers: Sequence[Career]) -> None:
        self._medians = sorted(c.salary.median for c in careers)

    def percentile(self, career: Career) -> float:
        if len(self._medians) < 2:
            return 0.5
        below = sum(1 for m in self._medians if m < career.salary.median)
        return below / (len(self._medians) - 1)


def salary_fit(career: Career, profile: StudentProfile, scale: SalaryScale) -> float:
    """1..5 salary priority slides the score from 'neutral' to 'pay percentile'."""
    priority = min(5, max(1, int(profile.salary_priority)))
    pull = (priority - 1) / 4.0  # 0.0 at "pay barely matters", 1.0 at "pay matters a lot"
    return 0.5 + (scale.percentile(career) - 0.5) * pull


def education_fit(career: Career, profile: StudentProfile) -> float:
    """1.0 if the career fits their schooling limit, decaying past it."""
    excess = max(0, career.education_years - int(profile.max_education_years))
    return max(0.0, 1.0 - EDUCATION_FIT_DECAY * excess)


def feasibility(career: Career, profile: StudentProfile) -> float:
    excess = max(0, career.education_years - int(profile.max_education_years))
    return max(FEASIBILITY_FLOOR, 1.0 - FEASIBILITY_DECAY * excess)


def score_career(
    profile: StudentProfile,
    career: Career,
    scale: SalaryScale,
) -> Match:
    """Score one career against one student on all four inputs."""
    weights = profile.normalized_weights()
    dimensions: List[DimensionScore] = []

    for dimension in DIMENSIONS:
        tag_score = cosine(profile.tags(dimension), career.tags(dimension))
        if dimension == "values":
            score = (
                VALUE_TAG_SHARE * tag_score
                + SALARY_SHARE * salary_fit(career, profile, scale)
                + EDUCATION_SHARE * education_fit(career, profile)
            )
        else:
            score = tag_score
        dimensions.append(
            DimensionScore(
                name=dimension,
                weight=weights[dimension],
                score=min(1.0, max(0.0, score)),
                matched=overlap(profile.tags(dimension), career.tags(dimension)),
            )
        )

    weighted = sum(d.contribution for d in dimensions)
    penalty = feasibility(career, profile)
    return Match(
        career=career,
        total=min(1.0, max(0.0, weighted * penalty)),
        dimensions=dimensions,
        feasibility=penalty,
    )


def rank_careers(
    profile: StudentProfile,
    careers: Sequence[Career],
    top_n: Optional[int] = None,
    scale: Optional[SalaryScale] = None,
) -> List[Match]:
    """Score every career and return them best-first (ties broken by title)."""
    scale = scale or SalaryScale(careers)
    matches = [score_career(profile, career, scale) for career in careers]
    matches.sort(key=lambda m: (-m.total, m.career.title))
    return matches[:top_n] if top_n else matches
