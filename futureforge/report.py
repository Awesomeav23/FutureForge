"""Report formatting, shared by the CLI, the GUI detail pane, and file export."""
from __future__ import annotations

import json
from typing import List, Sequence

from .dataset import label
from .models import DIMENSION_LABELS, Match, Recommendation, StudentProfile

RULE = "=" * 74


def match_breakdown(match: Match) -> List[str]:
    """The 'why this matched' lines: one per weighted input."""
    lines = []
    for d in match.dimensions:
        matched = ", ".join(label(d.name, t) for t in d.matched) or "no direct overlap"
        lines.append(
            "  {:<22} {:>3}%  (weight {:>2}%)  {}".format(
                DIMENSION_LABELS[d.name], int(round(d.score * 100)), int(round(d.weight * 100)), matched
            )
        )
    if match.feasibility < 1.0:
        lines.append(
            "  {:<22} score reduced {:>2}% -- needs more school than you asked for".format(
                "Schooling check", int(round((1 - match.feasibility) * 100))
            )
        )
    return lines


def format_recommendation(rec: Recommendation, rank: int) -> str:
    career = rec.career
    out = [
        "#{}  {}  --  {}% match".format(rank, career.title, rec.match.percent),
        "    Field:      {}".format(career.field),
        "    Pay:        {}".format(career.salary.formatted()),
        "    Education:  {} -- {}".format(career.education_label, career.education_note),
        "    Outlook:    {}".format(career.outlook),
        "",
        "    Why this fits you",
        "      {}".format(rec.why_it_fits),
        "",
        "    Why it matched",
    ]
    out.extend("    " + line for line in match_breakdown(rec.match))
    out.extend(["", "    What the work is like", "      {}".format(rec.day_in_the_life), "", "    Next steps"])
    out.extend("      - {}".format(s) for s in rec.next_steps)
    out.extend(["", "    Classes to take", "      {}".format(", ".join(rec.courses) or "n/a")])
    if rec.related_careers:
        out.extend(["", "    Also look at", "      {}".format(", ".join(rec.related_careers))])
    return "\n".join(out)


def format_report(profile: StudentProfile, recs: Sequence[Recommendation]) -> str:
    header = [
        RULE,
        "FutureForge -- career matches for {} (grade {})".format(profile.name, profile.grade),
        RULE,
        "Your answers",
        "  Interests:      {}".format(", ".join(label("interests", t) for t in profile.interests) or "-"),
        "  Subjects:       {}".format(", ".join(label("subjects", t) for t in profile.subjects) or "-"),
        "  Work style:     {}".format(", ".join(label("work_style", t) for t in profile.work_style) or "-"),
        "  Priorities:     {}".format(", ".join(label("values", t) for t in profile.values) or "-"),
        "  Years of school you'd do: {}   How much pay matters: {}/5".format(
            profile.max_education_years, profile.salary_priority
        ),
        "",
    ]
    body = [format_recommendation(rec, i + 1) for i, rec in enumerate(recs)]
    return "\n".join(header) + ("\n\n" + ("-" * 74) + "\n\n").join(body) + "\n"


def to_markdown(profile: StudentProfile, recs: Sequence[Recommendation]) -> str:
    lines = ["# Career matches for {}".format(profile.name), ""]
    lines.append("**Grade:** {}  |  **Years of school willing:** {}  |  **Pay priority:** {}/5".format(
        profile.grade, profile.max_education_years, profile.salary_priority))
    lines.append("")
    for i, rec in enumerate(recs, start=1):
        c = rec.career
        lines.extend([
            "## {}. {} ({}% match)".format(i, c.title, rec.match.percent),
            "",
            "| | |",
            "|---|---|",
            "| Field | {} |".format(c.field),
            "| Pay | {} |".format(c.salary.formatted()),
            "| Education | {} |".format(c.education_label),
            "| Requirement | {} |".format(c.education_note),
            "| Outlook | {} |".format(c.outlook),
            "",
            "**Why this fits you.** {}".format(rec.why_it_fits),
            "",
            "**What the work is like.** {}".format(rec.day_in_the_life),
            "",
            "**Next steps**",
            "",
        ])
        lines.extend("- {}".format(s) for s in rec.next_steps)
        lines.extend(["", "**Classes to take:** {}".format(", ".join(rec.courses) or "n/a"), ""])
        if rec.related_careers:
            lines.extend(["**Also look at:** {}".format(", ".join(rec.related_careers)), ""])
    return "\n".join(lines)


def to_json(profile: StudentProfile, recs: Sequence[Recommendation]) -> str:
    return json.dumps(
        {"profile": profile.to_dict(), "recommendations": [r.to_dict() for r in recs]}, indent=2
    )
