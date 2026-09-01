#!/usr/bin/env python3
"""Run a whole cohort through the engine and report coverage.

This is what backs the "500+ recommendations across 50+ career fields" claim with
something reproducible: build N synthetic student profiles from the tag
vocabularies, recommend for each, and count what actually came out.

    python3 scripts/batch_demo.py --profiles 100 --top 5
    python3 scripts/batch_demo.py --profiles 100 --out cohort.json
"""
from __future__ import annotations

import argparse
import json
import os
import random
import sys
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from futureforge.dataset import VOCABULARIES, fields, load_careers  # noqa: E402
from futureforge.generator import TemplateGenerator  # noqa: E402
from futureforge.models import StudentProfile  # noqa: E402
from futureforge.recommender import Recommender  # noqa: E402


def synthetic_profile(rng: random.Random, index: int) -> StudentProfile:
    def pick(dimension: str, low: int, high: int):
        tags = list(VOCABULARIES[dimension])
        return rng.sample(tags, rng.randint(low, min(high, len(tags))))

    return StudentProfile(
        name="Student {:03d}".format(index),
        grade=str(rng.choice([9, 10, 11, 12])),
        interests=pick("interests", 2, 5),
        subjects=pick("subjects", 2, 4),
        work_style=pick("work_style", 2, 4),
        values=pick("values", 2, 4),
        max_education_years=rng.choice([0, 1, 2, 4, 4, 6, 8]),
        salary_priority=rng.randint(1, 5),
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Batch cohort run + coverage report.")
    parser.add_argument("--profiles", type=int, default=100, help="how many students to simulate")
    parser.add_argument("--top", type=int, default=5, help="recommendations per student")
    parser.add_argument("--seed", type=int, default=7, help="RNG seed (runs are reproducible)")
    parser.add_argument("--out", help="write the full cohort result to this JSON file")
    parser.add_argument("--use-openai", action="store_true", help="use the OpenAI generator (costs money)")
    args = parser.parse_args()

    careers = load_careers()
    generator = None if args.use_openai else TemplateGenerator()
    recommender = Recommender(careers=careers, generator=generator)
    rng = random.Random(args.seed)

    recommended = Counter()
    by_field = Counter()
    education = Counter()
    total = 0
    cohort = []

    for index in range(1, args.profiles + 1):
        profile = synthetic_profile(rng, index)
        recs = recommender.recommend(profile, top_n=args.top)
        total += len(recs)
        for rec in recs:
            recommended[rec.career.title] += 1
            by_field[rec.career.field] += 1
            education[rec.career.education] += 1
        cohort.append({"profile": profile.to_dict(), "recommendations": [r.to_dict() for r in recs]})
        if index % 25 == 0:
            print("  ...{} students, {} recommendations".format(index, total))

    print("\n" + "=" * 70)
    print("FutureForge batch run")
    print("=" * 70)
    print("Students simulated:        {}".format(args.profiles))
    print("Recommendations produced:  {}".format(total))
    print("Careers in dataset:        {} across {} fields".format(len(careers), len(fields(careers))))
    print("Distinct careers surfaced: {} ({:.0f}% of the dataset)".format(
        len(recommended), 100.0 * len(recommended) / len(careers)))
    print("Fields surfaced:           {} of {}".format(len(by_field), len(fields(careers))))

    print("\nRecommendations by field")
    for field, count in by_field.most_common():
        print("  {:<20} {:>5}  {}".format(field, count, "#" * int(40.0 * count / max(by_field.values()))))

    print("\nRecommendations by education level")
    for level, count in education.most_common():
        print("  {:<14} {:>5}".format(level, count))

    print("\nMost-recommended careers")
    for title, count in recommended.most_common(10):
        print("  {:<34} {:>4}".format(title, count))

    never = [c.title for c in careers if c.title not in recommended]
    if never:
        print("\nNever recommended ({}): {}".format(len(never), ", ".join(never)))

    if args.out:
        with open(args.out, "w") as handle:
            json.dump({"summary": {"students": args.profiles, "recommendations": total}, "cohort": cohort},
                      handle, indent=1)
        print("\nWrote full cohort to {}".format(args.out))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
