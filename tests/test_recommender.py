"""End to end through the offline generator -- no API key, no network."""
import json

from futureforge.dataset import load_careers
from futureforge.generator import CachingGenerator, TemplateGenerator, get_generator
from futureforge.models import StudentProfile
from futureforge.recommender import Recommender
from futureforge.report import format_report, to_json, to_markdown

CAREERS = load_careers()
PROFILE = StudentProfile(
    name="Maya",
    grade="11",
    interests=["health", "helping_people"],
    subjects=["biology", "chemistry"],
    work_style=["team", "hands_on"],
    values=["helping_others", "job_security"],
)


def recommender():
    return Recommender(careers=CAREERS, generator=TemplateGenerator())


def test_recommend_returns_complete_records():
    recs = recommender().recommend(PROFILE, top_n=5)
    assert len(recs) == 5
    for rec in recs:
        assert rec.why_it_fits.strip()
        assert rec.day_in_the_life.strip()
        assert rec.next_steps and rec.courses
        assert rec.career.salary.low > 0          # pay range always surfaced
        assert rec.career.education_note.strip()  # degree requirement always surfaced
        assert rec.source == "offline"


def test_related_careers_are_filled_from_the_ranking():
    recs = recommender().recommend(PROFILE, top_n=3)
    assert all(rec.related_careers for rec in recs)
    assert recs[0].career.title not in recs[0].related_careers


def test_explanation_mentions_the_students_own_answers():
    rec = recommender().recommend(PROFILE, top_n=1)[0]
    assert "match because" in rec.why_it_fits
    assert rec.match.matched_tags()


def test_schooling_warning_appears_when_over_the_limit():
    picky = StudentProfile(
        interests=["health", "science"], subjects=["biology"], work_style=["team"],
        values=["prestige"], max_education_years=0,
    )
    recs = recommender().recommend(picky, top_n=20)
    over = [r for r in recs if r.match.feasibility < 1.0]
    assert over, "expected at least one career needing more school than requested"
    assert "more than the 0" in over[0].why_it_fits


def test_reports_render_in_every_format():
    recs = recommender().recommend(PROFILE, top_n=2)
    text = format_report(PROFILE, recs)
    assert "FutureForge" in text and "Why it matched" in text
    assert "## 1." in to_markdown(PROFILE, recs)
    payload = json.loads(to_json(PROFILE, recs))
    assert payload["profile"]["name"] == "Maya"
    assert len(payload["recommendations"]) == 2
    assert payload["recommendations"][0]["career"]["salary"]["median"] > 0


def test_generator_falls_back_to_offline_without_a_key(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    generator, status = get_generator()
    assert "Offline mode" in status
    assert generator.source == "offline"


def test_cache_round_trips(tmp_path):
    cached = CachingGenerator(TemplateGenerator(), path=str(tmp_path / "cache.json"))
    rec = Recommender(careers=CAREERS, generator=cached)
    first = rec.recommend(PROFILE, top_n=2)
    second = rec.recommend(PROFILE, top_n=2)
    assert [r.why_it_fits for r in first] == [r.why_it_fits for r in second]
    assert (tmp_path / "cache.json").exists()
