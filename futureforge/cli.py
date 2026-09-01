"""Command-line interface.

    python3 -m futureforge.cli                          # interactive questionnaire
    python3 -m futureforge.cli --profile student.json   # scripted run
    python3 -m futureforge.cli --profile s.json --json  # machine-readable output
"""
from __future__ import annotations

import argparse
import json
import sys
from typing import Dict, List

from .dataset import VOCABULARIES, fields, load_careers
from .generator import TemplateGenerator, get_generator
from .models import DIMENSIONS, StudentProfile
from .recommender import Recommender
from .report import format_report, to_json, to_markdown


def _ask_multi(dimension: str, prompt: str) -> List[str]:
    vocab = list(VOCABULARIES[dimension].items())
    print("\n" + prompt)
    for index, (_tag, text) in enumerate(vocab, start=1):
        print("  {:>2}. {}".format(index, text))
    raw = input("Numbers, separated by commas (Enter to skip): ").strip()
    chosen: List[str] = []
    for piece in raw.replace(" ", "").split(","):
        if piece.isdigit() and 1 <= int(piece) <= len(vocab):
            chosen.append(vocab[int(piece) - 1][0])
    return chosen


def _ask_int(prompt: str, low: int, high: int, default: int) -> int:
    raw = input("{} [{}-{}, default {}]: ".format(prompt, low, high, default)).strip()
    if raw.isdigit() and low <= int(raw) <= high:
        return int(raw)
    return default


def interactive_profile() -> StudentProfile:
    print("=" * 74)
    print("FutureForge -- let's find some careers that fit you.")
    print("=" * 74)
    name = input("Your name: ").strip() or "Student"
    grade = input("Grade [9-12, default 11]: ").strip() or "11"
    profile = StudentProfile(name=name, grade=grade)
    profile.interests = _ask_multi("interests", "1. What do you actually enjoy?")
    profile.subjects = _ask_multi("subjects", "2. Which classes do you like or do well in?")
    profile.work_style = _ask_multi("work_style", "3. How do you want to spend your workday?")
    profile.values = _ask_multi("values", "4. What matters most in a job?")
    print()
    profile.max_education_years = _ask_int("Years of school after high school you'd do", 0, 8, 4)
    profile.salary_priority = _ask_int("How much does high pay matter", 1, 5, 3)
    return profile


def main(argv: List[str] = None) -> int:
    parser = argparse.ArgumentParser(prog="futureforge", description="Career matches for high school students.")
    parser.add_argument("--profile", help="path to a student profile JSON file")
    parser.add_argument("--top", type=int, default=5, help="how many careers to return (default 5)")
    parser.add_argument("--json", action="store_true", help="print JSON instead of a text report")
    parser.add_argument("--markdown", action="store_true", help="print a markdown report")
    parser.add_argument("--offline", action="store_true", help="force template guidance, skip OpenAI")
    parser.add_argument("--list-fields", action="store_true", help="list the career fields in the dataset and exit")
    args = parser.parse_args(argv)

    careers = load_careers()
    if args.list_fields:
        print("{} careers across {} fields:".format(len(careers), len(fields(careers))))
        for field in fields(careers):
            titles = [c.title for c in careers if c.field == field]
            print("  {:<20} {:>2}  {}".format(field, len(titles), ", ".join(titles)))
        return 0

    if args.profile:
        with open(args.profile) as handle:
            profile = StudentProfile.from_dict(json.load(handle))
    else:
        profile = interactive_profile()

    generator = TemplateGenerator() if args.offline else get_generator()[0]
    recommender = Recommender(careers=careers, generator=generator)
    if not args.json and not args.markdown:
        print("\n{}\n".format(recommender.status), file=sys.stderr)
    recs = recommender.recommend(profile, top_n=args.top)

    if args.json:
        print(to_json(profile, recs))
    elif args.markdown:
        print(to_markdown(profile, recs))
    else:
        print(format_report(profile, recs))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
