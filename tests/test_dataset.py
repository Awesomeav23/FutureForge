"""The dataset is the product -- if it drifts, every recommendation is wrong."""
from futureforge.dataset import VOCABULARIES, DatasetError, fields, load_careers
from futureforge.models import EDUCATION_YEARS

CAREERS = load_careers()


def test_dataset_covers_the_advertised_scale():
    assert len(CAREERS) >= 50
    assert len(fields(CAREERS)) >= 10


def test_ids_are_unique():
    ids = [c.id for c in CAREERS]
    assert len(ids) == len(set(ids))


def test_every_tag_is_in_a_vocabulary():
    for career in CAREERS:
        for dimension, vocab in VOCABULARIES.items():
            tags = career.tags(dimension)
            assert tags, "{} has no {} tags".format(career.id, dimension)
            assert set(tags) <= set(vocab), "{}: bad {} tags".format(career.id, dimension)


def test_salary_ranges_are_ordered():
    for career in CAREERS:
        s = career.salary
        assert s.low <= s.median <= s.high
        assert s.low > 0


def test_education_levels_are_known():
    for career in CAREERS:
        assert career.education in EDUCATION_YEARS
        assert career.education_note.strip()


def test_bad_data_is_rejected(tmp_path):
    import json
    bad = {"careers": [{
        "id": "x", "title": "X", "field": "F", "education": "bachelor",
        "education_note": "n", "salary": {"low": 1, "median": 2, "high": 3},
        "description": "d", "interests": ["not_a_real_tag"], "subjects": ["math"],
        "work_style": ["team"], "values": ["high_pay"],
    }]}
    path = tmp_path / "bad.json"
    path.write_text(json.dumps(bad))
    try:
        load_careers(str(path))
        assert False, "expected DatasetError"
    except DatasetError as exc:
        assert "unknown interests tags" in str(exc)
