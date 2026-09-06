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


# Real students answer in correlated ways -- someone drawn to medicine also takes
# biology. Sampling each dimension independently from the full vocabulary invents
# people who like animals, study art, want quiet focus and value entrepreneurship;
# a cohort of those measures noise, not the engine. So each synthetic student
# starts from a coherent archetype and is jittered from there.
ARCHETYPES = (
    {"label": "health & care",
     "interests": ["health", "helping_people", "science"],
     "subjects": ["biology", "chemistry", "psychology"],
     "work_style": ["team", "hands_on", "fast_paced", "structured"],
     "values": ["helping_others", "job_security", "public_service"],
     "education": [2, 2, 4, 4, 6, 8], "salary": [2, 3, 3, 4]},

    {"label": "software & data",
     "interests": ["technology", "data_numbers", "science"],
     "subjects": ["computer_science", "math", "physics"],
     "work_style": ["desk_work", "independent", "remote_possible", "quiet_focus"],
     "values": ["high_pay", "autonomy", "work_life_balance"],
     "education": [2, 4, 4, 4, 6], "salary": [3, 4, 5, 5]},

    {"label": "skilled trades",
     "interests": ["building", "machines", "outdoors"],
     "subjects": ["shop_tech", "math", "physics"],
     "work_style": ["hands_on", "outdoors_env", "independent", "structured"],
     "values": ["short_training", "making_things", "high_pay"],
     "education": [0, 0, 1, 2, 2], "salary": [3, 4, 4, 5]},

    {"label": "business & finance",
     "interests": ["business", "money_markets", "data_numbers"],
     "subjects": ["business_econ", "math", "english"],
     "work_style": ["desk_work", "leadership", "customer_facing", "structured"],
     "values": ["high_pay", "prestige", "entrepreneurship"],
     "education": [2, 4, 4, 6], "salary": [4, 4, 5, 5]},

    {"label": "creative & design",
     "interests": ["art_design", "performing", "writing"],
     "subjects": ["art", "english", "music"],
     "work_style": ["flexible_hours", "independent", "remote_possible", "quiet_focus"],
     "values": ["creativity", "autonomy", "variety"],
     "education": [0, 1, 2, 4, 4], "salary": [1, 2, 2, 3]},

    {"label": "education & social",
     "interests": ["teaching", "helping_people", "writing"],
     "subjects": ["english", "psychology", "history"],
     "work_style": ["team", "customer_facing", "structured", "leadership"],
     "values": ["helping_others", "public_service", "work_life_balance"],
     "education": [4, 4, 6, 6], "salary": [1, 2, 2, 3]},

    {"label": "law & public service",
     "interests": ["law_order", "helping_people", "business"],
     "subjects": ["history", "english", "psychology"],
     "work_style": ["team", "shift_work", "fast_paced", "leadership"],
     "values": ["public_service", "job_security", "prestige"],
     "education": [0, 2, 4, 4, 8], "salary": [2, 3, 3, 4]},

    {"label": "science & environment",
     "interests": ["science", "environment", "data_numbers"],
     "subjects": ["biology", "chemistry", "geography"],
     "work_style": ["quiet_focus", "independent", "outdoors_env", "structured"],
     "values": ["variety", "job_security", "work_life_balance"],
     "education": [4, 4, 6, 8], "salary": [2, 3, 3, 4]},

    {"label": "animals & outdoors",
     "interests": ["animals", "outdoors", "environment"],
     "subjects": ["biology", "geography", "phys_ed"],
     "work_style": ["outdoors_env", "hands_on", "flexible_hours", "independent"],
     "values": ["stay_local", "work_life_balance", "variety"],
     "education": [0, 1, 2, 4, 8], "salary": [1, 2, 2, 3]},

    {"label": "sports & fitness",
     "interests": ["sports", "health", "teaching"],
     "subjects": ["phys_ed", "biology", "psychology"],
     "work_style": ["fast_paced", "team", "customer_facing", "flexible_hours"],
     "values": ["teamwork_culture", "variety", "helping_others"],
     "education": [0, 1, 2, 4], "salary": [2, 2, 3, 4]},

    {"label": "hospitality & food",
     "interests": ["food", "business", "travel"],
     "subjects": ["business_econ", "foreign_language", "art"],
     "work_style": ["fast_paced", "customer_facing", "shift_work", "team"],
     "values": ["creativity", "entrepreneurship", "variety"],
     "education": [0, 0, 1, 2, 4], "salary": [2, 3, 3, 4]},

    {"label": "transport & logistics",
     "interests": ["machines", "travel", "outdoors"],
     "subjects": ["geography", "math", "shop_tech"],
     "work_style": ["travel_frequent", "independent", "shift_work", "structured"],
     "values": ["high_pay", "short_training", "job_security"],
     "education": [0, 1, 2, 2, 4], "salary": [3, 3, 4, 5]},
)


def synthetic_profile(rng: random.Random, index: int) -> StudentProfile:
    """One coherent student: an archetype, sampled down and lightly jittered."""
    archetype = rng.choice(ARCHETYPES)

    def pick(dimension: str, low: int, high: int):
        core = list(archetype[dimension])
        rng.shuffle(core)
        chosen = core[: rng.randint(low, min(high, len(core)))]
        # About a fifth of students carry one answer that cuts against the pattern.
        # Real teenagers do, and it keeps the cohort from collapsing onto twelve
        # points in tag space.
        if rng.random() < 0.2:
            wildcard = rng.choice(list(VOCABULARIES[dimension]))
            if wildcard not in chosen:
                chosen.append(wildcard)
        return chosen

    return StudentProfile(
        name="Student {:03d}".format(index),
        grade=str(rng.choice([9, 10, 11, 12])),
        interests=pick("interests", 2, 3),
        subjects=pick("subjects", 2, 3),
        work_style=pick("work_style", 2, 3),
        values=pick("values", 2, 3),
        max_education_years=rng.choice(archetype["education"]),
        salary_priority=rng.choice(archetype["salary"]),
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
        # Print a sample, not all of them -- the full list is in --out. A cohort
        # this size cannot reach every career, and dumping 200 titles reads like a
        # failure when it is just arithmetic: N students x top_n is a hard ceiling.
        sample = ", ".join(never[:8])
        more = " (+{} more)".format(len(never) - 8) if len(never) > 8 else ""
        print("\nNot surfaced in this cohort ({} of {}): {}{}".format(
            len(never), len(careers), sample, more))
        print("  ceiling: {} students x top {} = {} slots for {} careers".format(
            args.profiles, args.top, args.profiles * args.top, len(careers)))

    if args.out:
        with open(args.out, "w") as handle:
            json.dump({"summary": {"students": args.profiles, "recommendations": total}, "cohort": cohort},
                      handle, indent=1)
        print("\nWrote full cohort to {}".format(args.out))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
