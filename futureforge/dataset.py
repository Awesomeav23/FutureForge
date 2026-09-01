"""Loading and validating the career dataset.

The four tag vocabularies below are the shared language between the dataset and a
student's answers -- a typo in either one fails loudly at load time instead of
silently scoring 0.
"""
from __future__ import annotations

import json
import os
from typing import Dict, List, Optional, Sequence

from .models import EDUCATION_YEARS, Career

# --- Tag vocabularies (the options a student can pick, per input) -------------

INTEREST_TAGS: Dict[str, str] = {
    "technology": "Computers & technology",
    "building": "Building & fixing things",
    "machines": "Engines, tools & machines",
    "science": "Science & experiments",
    "health": "Medicine & the human body",
    "helping_people": "Helping people directly",
    "teaching": "Teaching & explaining",
    "animals": "Animals",
    "outdoors": "Being outdoors",
    "environment": "Nature & the environment",
    "art_design": "Art & design",
    "performing": "Music, acting & performing",
    "writing": "Writing & storytelling",
    "business": "Business & running things",
    "money_markets": "Money, investing & markets",
    "data_numbers": "Numbers, data & puzzles",
    "law_order": "Law, justice & public safety",
    "food": "Food & cooking",
    "travel": "Travel & moving around",
    "sports": "Sports & fitness",
}

SUBJECT_TAGS: Dict[str, str] = {
    "math": "Math",
    "biology": "Biology",
    "chemistry": "Chemistry",
    "physics": "Physics",
    "computer_science": "Computer science",
    "english": "English / language arts",
    "history": "History / social studies",
    "geography": "Geography",
    "art": "Art",
    "music": "Music",
    "foreign_language": "Foreign language",
    "shop_tech": "Shop / tech ed",
    "business_econ": "Business / economics",
    "psychology": "Psychology",
    "phys_ed": "Physical education",
}

WORK_STYLE_TAGS: Dict[str, str] = {
    "team": "On a team",
    "independent": "Mostly on my own",
    "hands_on": "Hands-on / physical work",
    "desk_work": "At a desk or computer",
    "outdoors_env": "Outdoors or on a job site",
    "travel_frequent": "Traveling or moving around",
    "structured": "Clear routine & procedures",
    "flexible_hours": "Flexible hours",
    "fast_paced": "Fast-paced & high pressure",
    "quiet_focus": "Quiet, focused work",
    "leadership": "Leading other people",
    "customer_facing": "Talking with people all day",
    "remote_possible": "Could work remotely",
    "shift_work": "Nights / weekends OK",
}

VALUE_TAGS: Dict[str, str] = {
    "high_pay": "High pay",
    "job_security": "Job security",
    "work_life_balance": "Work-life balance",
    "helping_others": "Helping others",
    "creativity": "Being creative",
    "autonomy": "Being my own boss day to day",
    "prestige": "Respect & prestige",
    "short_training": "Start earning quickly",
    "entrepreneurship": "Owning a business someday",
    "variety": "Variety, not the same day twice",
    "stay_local": "Staying near home",
    "making_things": "Making something real",
    "public_service": "Serving my community",
    "teamwork_culture": "Close-knit team culture",
}

VOCABULARIES: Dict[str, Dict[str, str]] = {
    "interests": INTEREST_TAGS,
    "subjects": SUBJECT_TAGS,
    "work_style": WORK_STYLE_TAGS,
    "values": VALUE_TAGS,
}

DATA_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "careers.json")


class DatasetError(ValueError):
    """Raised when careers.json does not match the vocabularies or schema."""


def label(dimension: str, tag: str) -> str:
    """Human-readable label for a tag, for the GUI and printed reports."""
    return VOCABULARIES[dimension].get(tag, tag.replace("_", " "))


def _validate(career: Career) -> None:
    if career.education not in EDUCATION_YEARS:
        raise DatasetError("{}: unknown education level {!r}".format(career.id, career.education))
    s = career.salary
    if not (s.low <= s.median <= s.high):
        raise DatasetError("{}: salary must satisfy low <= median <= high".format(career.id))
    for dimension, vocab in VOCABULARIES.items():
        tags = career.tags(dimension)
        if not tags:
            raise DatasetError("{}: no {} tags".format(career.id, dimension))
        unknown = [t for t in tags if t not in vocab]
        if unknown:
            raise DatasetError("{}: unknown {} tags: {}".format(career.id, dimension, unknown))


def load_careers(path: Optional[str] = None) -> List[Career]:
    """Load and validate the dataset. Raises DatasetError on any bad entry."""
    path = path or DATA_PATH
    with open(path, "r") as handle:
        raw = json.load(handle)

    careers = [Career.from_dict(entry) for entry in raw["careers"]]
    if not careers:
        raise DatasetError("dataset is empty")

    seen = set()
    for career in careers:
        if career.id in seen:
            raise DatasetError("duplicate career id: {}".format(career.id))
        seen.add(career.id)
        _validate(career)
    return careers


def dataset_meta(path: Optional[str] = None) -> Dict[str, object]:
    path = path or DATA_PATH
    with open(path, "r") as handle:
        return json.load(handle).get("_meta", {})


def fields(careers: Sequence[Career]) -> List[str]:
    return sorted({c.field for c in careers})
