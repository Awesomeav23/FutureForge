#!/usr/bin/env python3
"""Validate data/careers.json before it can break the app.

The dataset is hand-edited and 500+ entries deep. A single mistyped tag makes
load_careers() raise at startup, which kills the app for everyone -- so this runs
in CI on every push, and is worth running locally before committing a dataset edit:

    python3 scripts/validate_dataset.py

Reports every problem it finds rather than stopping at the first, and exits
non-zero if there are any.
"""
from __future__ import annotations

import collections
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from futureforge.dataset import DATA_PATH, VOCABULARIES  # noqa: E402
from futureforge.models import DIMENSIONS, EDUCATION_YEARS  # noqa: E402

REQUIRED_TEXT = ("id", "title", "field", "education_note", "description", "outlook")


def validate(path: str = DATA_PATH) -> list:
    """Return a list of human-readable problems; empty means the file is good."""
    problems = []

    try:
        with open(path, "r") as handle:
            data = json.load(handle)
    except FileNotFoundError:
        return ["%s: file not found" % path]
    except ValueError as exc:
        return ["%s: invalid JSON -- %s" % (path, exc)]

    if "careers" not in data:
        return ["%s: no 'careers' key" % path]
    careers = data["careers"]
    if not careers:
        return ["%s: 'careers' is empty" % path]

    ids = collections.Counter(c.get("id") for c in careers)
    titles = collections.Counter(c.get("title") for c in careers)
    for cid, count in ids.items():
        if count > 1:
            problems.append("duplicate id %r appears %d times" % (cid, count))
    for title, count in titles.items():
        if count > 1:
            problems.append("duplicate title %r appears %d times" % (title, count))

    for index, career in enumerate(careers):
        who = career.get("id") or career.get("title") or "entry #%d" % index

        for key in REQUIRED_TEXT:
            value = career.get(key)
            if not isinstance(value, str) or not value.strip():
                problems.append("%s: %s is missing or empty" % (who, key))

        education = career.get("education")
        if education not in EDUCATION_YEARS:
            problems.append("%s: education %r is not one of %s"
                            % (who, education, sorted(EDUCATION_YEARS)))

        salary = career.get("salary")
        if not isinstance(salary, dict):
            problems.append("%s: salary is missing" % who)
        else:
            missing = [k for k in ("low", "median", "high") if k not in salary]
            if missing:
                problems.append("%s: salary missing %s" % (who, ", ".join(missing)))
            else:
                low, median, high = salary["low"], salary["median"], salary["high"]
                if not all(isinstance(v, int) for v in (low, median, high)):
                    problems.append("%s: salary values must be integers" % who)
                elif not low <= median <= high:
                    problems.append("%s: salary out of order (%s/%s/%s)"
                                    % (who, low, median, high))
                elif low <= 0:
                    problems.append("%s: salary low must be positive" % who)

        for dimension in DIMENSIONS:
            tags = career.get(dimension)
            if not isinstance(tags, list) or not tags:
                problems.append("%s: %s must be a non-empty list" % (who, dimension))
                continue
            vocab = VOCABULARIES[dimension]
            for tag in tags:
                if tag not in vocab:
                    problems.append("%s: unknown %s tag %r" % (who, dimension, tag))
            if len(set(tags)) != len(tags):
                problems.append("%s: %s has duplicate tags" % (who, dimension))

    # _meta counts are quoted in the README and shown in the UI, so keep them true
    fields = {c.get("field") for c in careers}
    meta = data.get("_meta", {})
    if "careers" in meta and meta["careers"] != len(careers):
        problems.append("_meta.careers says %s but there are %d"
                        % (meta["careers"], len(careers)))
    if "fields" in meta and meta["fields"] != len(fields):
        problems.append("_meta.fields says %s but there are %d"
                        % (meta["fields"], len(fields)))

    return problems


def main() -> int:
    problems = validate()
    with open(DATA_PATH) as handle:
        careers = json.load(handle)["careers"]
    fields = {c.get("field") for c in careers}

    if problems:
        print("FAIL  %d problem(s) in %s\n" % (len(problems), DATA_PATH))
        for problem in problems:
            print("  - %s" % problem)
        return 1

    print("OK  %d careers across %d fields" % (len(careers), len(fields)))
    print("    tags validated against %d vocabulary entries"
          % sum(len(v) for v in VOCABULARIES.values()))
    return 0


if __name__ == "__main__":
    sys.exit(main())
