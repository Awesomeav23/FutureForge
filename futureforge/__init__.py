"""FutureForge -- career guidance for high school students.

    from futureforge import Recommender, StudentProfile

    rec = Recommender()
    profile = StudentProfile(interests=["technology"], subjects=["math"],
                             work_style=["desk_work"], values=["high_pay"])
    for r in rec.recommend(profile, top_n=5):
        print(r.career.title, r.match.percent, r.career.salary.formatted())
"""
from .dataset import load_careers
from .matching import rank_careers
from .models import Career, Match, Recommendation, StudentProfile
from .recommender import Recommender

__version__ = "1.0.0"
__all__ = [
    "Career",
    "Match",
    "Recommendation",
    "Recommender",
    "StudentProfile",
    "load_careers",
    "rank_careers",
]
