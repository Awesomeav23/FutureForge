"""Behavioral guarantees of the four-input weighted engine."""
from futureforge.dataset import load_careers
from futureforge.matching import SalaryScale, cosine, rank_careers, score_career
from futureforge.models import DEFAULT_WEIGHTS, StudentProfile

CAREERS = load_careers()
SCALE = SalaryScale(CAREERS)


def profile(**kwargs):
    base = dict(
        interests=["health", "helping_people", "science"],
        subjects=["biology", "chemistry"],
        work_style=["team", "hands_on"],
        values=["helping_others", "job_security"],
        max_education_years=4,
        salary_priority=3,
    )
    base.update(kwargs)
    return StudentProfile(**base)


def rank_of(title, matches):
    return [m.career.title for m in matches].index(title)


HEALTH_FIELDS = (
    "Nursing", "Medicine", "Dental", "Allied Health", "Pharmacy",
    "Emergency Medical Services", "Rehabilitation Therapy", "Mental Health",
    "Nutrition & Dietetics", "Fitness & Athletics", "Home & Personal Care",
)

TRADE_FIELDS = (
    "Carpentry & Construction", "Electrical Trades", "Plumbing & HVAC",
    "Welding & Machining", "Automotive & Marine", "Aviation Maintenance",
    "Renewable Energy", "Robotics & Automation",
)


def test_cosine_bounds():
    assert cosine(["a", "b"], ["a", "b"]) == 1.0
    assert cosine(["a"], ["b"]) == 0.0
    assert 0.0 < cosine(["a", "b"], ["b", "c"]) < 1.0
    assert cosine([], ["a"]) == 0.0


def test_scores_stay_in_range():
    p = profile()
    for career in CAREERS:
        match = score_career(p, career, SCALE)
        assert 0.0 <= match.total <= 1.0
        for d in match.dimensions:
            assert 0.0 <= d.score <= 1.0


def test_health_profile_ranks_healthcare_over_software():
    matches = rank_careers(profile(), CAREERS)
    assert rank_of("Registered Nurse", matches) < rank_of("Software Engineer", matches)
    assert matches[0].career.field in HEALTH_FIELDS


def test_trades_profile_ranks_a_trade_first():
    p = profile(
        interests=["building", "machines"],
        subjects=["shop_tech", "math"],
        work_style=["hands_on", "independent"],
        values=["short_training", "making_things"],
        max_education_years=1,
    )
    top = rank_careers(p, CAREERS, top_n=3)
    assert any(m.career.field in TRADE_FIELDS for m in top)


def test_matches_carry_their_explanation():
    match = rank_careers(profile(), CAREERS, top_n=1)[0]
    assert len(match.dimensions) == 4
    assert match.dimension("subjects").matched  # the overlapping tags are recorded
    assert sum(d.weight for d in match.dimensions) == 1.0


def test_reweighting_changes_the_ranking():
    subjects_only = profile(weights={"interests": 0.0, "subjects": 1.0, "work_style": 0.0, "values": 0.0})
    default = profile(weights=dict(DEFAULT_WEIGHTS))
    assert [m.career.id for m in rank_careers(subjects_only, CAREERS, top_n=5)] != [
        m.career.id for m in rank_careers(default, CAREERS, top_n=5)
    ]


def test_zero_weights_fall_back_to_defaults():
    p = profile(weights={d: 0.0 for d in DEFAULT_WEIGHTS})
    assert p.normalized_weights() == DEFAULT_WEIGHTS


def test_schooling_limit_pushes_long_degrees_down():
    """A student who will not do 8 years should not be told to become a doctor."""
    short = profile(interests=["health", "science", "helping_people"], max_education_years=2)
    long = profile(interests=["health", "science", "helping_people"], max_education_years=8)
    short_matches = rank_careers(short, CAREERS)
    long_matches = rank_careers(long, CAREERS)
    assert short_matches[0].career.education_years <= 4
    assert rank_of("Physician (MD/DO)", short_matches) > rank_of("Physician (MD/DO)", long_matches)


def test_salary_priority_shifts_toward_higher_paying_work():
    low = rank_careers(profile(salary_priority=1), CAREERS, top_n=10)
    high = rank_careers(profile(salary_priority=5), CAREERS, top_n=10)

    def weighted(matches):
        # weight by rank -- the same careers can fill the top ten either way, so
        # what moves is their order, not the membership
        return sum(m.career.salary.median / (i + 1) for i, m in enumerate(matches))

    assert weighted(high) > weighted(low)


def test_ranking_is_deterministic():
    p = profile()
    assert [m.career.id for m in rank_careers(p, CAREERS)] == [m.career.id for m in rank_careers(p, CAREERS)]
