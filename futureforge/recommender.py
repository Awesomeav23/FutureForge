"""Orchestration: a student profile in, ranked recommendations out."""
from __future__ import annotations

from typing import List, Optional, Sequence

from .dataset import load_careers
from .generator import BaseGenerator, get_generator
from .matching import SalaryScale, rank_careers
from .models import Career, Match, Recommendation, StudentProfile


class Recommender:
    def __init__(
        self,
        careers: Optional[Sequence[Career]] = None,
        generator: Optional[BaseGenerator] = None,
    ) -> None:
        self.careers: List[Career] = list(careers) if careers is not None else load_careers()
        self.scale = SalaryScale(self.careers)
        if generator is None:
            generator, status = get_generator()
        else:
            status = "generator: {}".format(getattr(generator, "source", "custom"))
        self.generator = generator
        self.status = status

    def rank(self, profile: StudentProfile, top_n: int = 5) -> List[Match]:
        return rank_careers(profile, self.careers, top_n=top_n, scale=self.scale)

    def recommend(self, profile: StudentProfile, top_n: int = 5) -> List[Recommendation]:
        """Rank, then write guidance for each of the top matches."""
        matches = self.rank(profile, top_n=top_n)
        titles = [m.career.title for m in matches]
        out: List[Recommendation] = []
        for index, match in enumerate(matches):
            rec = self.generator.generate(profile, match)
            if not rec.related_careers:
                # Neighbours from the ranked list itself -- always something to point at.
                neighbours = [t for i, t in enumerate(titles) if i != index][:2]
                rec = Recommendation(
                    match=rec.match,
                    why_it_fits=rec.why_it_fits,
                    next_steps=rec.next_steps,
                    courses=rec.courses,
                    day_in_the_life=rec.day_in_the_life,
                    related_careers=neighbours,
                    source=rec.source,
                )
            out.append(rec)
        return out
