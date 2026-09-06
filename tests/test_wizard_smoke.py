"""Headless smoke test for the wizard.

Builds the real GUI and walks all six screens, asserting the widgets each one
depends on actually exist. This catches the class of bug unit tests cannot see --
a screen referencing a widget an earlier screen never created, or a render path
that throws on an empty answer.

Skipped when there is no display (plain `pytest` on a bare CI runner); CI runs it
under xvfb-run so it executes for real.

Deliberately avoids Tk's update() -- it can block indefinitely when no window
manager is present. update_idletasks() is enough to force geometry and run the
render paths.
"""
from __future__ import annotations

import pytest

tk = pytest.importorskip("tkinter")


def _display_available() -> bool:
    try:
        root = tk.Tk()
    except tk.TclError:
        return False
    root.destroy()
    return True


pytestmark = pytest.mark.skipif(
    not _display_available(), reason="no display available for Tk"
)


@pytest.fixture
def app():
    from futureforge.wizard import Wizard, _theme

    root = tk.Tk()
    root.withdraw()  # keep it off screen; we never need it mapped
    _theme(root)
    wizard = Wizard(root)
    root.update_idletasks()
    yield wizard
    root.destroy()


def test_wizard_builds_and_loads_the_dataset(app):
    assert len(app.careers) > 0
    assert app.recommender is not None
    assert app.step == 0


def test_every_question_screen_renders(app):
    from futureforge.wizard import QUESTIONS

    for index in range(1, len(QUESTIONS) + 1):
        app.step = index
        app._render()
        app.master.update_idletasks()
        # the text box the student types into must exist on every question screen
        assert app.entry.winfo_exists()
        assert app.chip_area.winfo_exists()


def test_typing_an_answer_picks_up_tags(app):
    app.step = 1
    app._render()
    app.entry.insert("1.0", "i like biology and helping sick people")
    app._update_picked("interests")
    assert app.picked["interests"], "expected tags from a clear answer"
    assert app.answers["interests"]


def test_empty_answer_picks_up_nothing_and_does_not_raise(app):
    app.step = 1
    app._render()
    app._update_picked("interests")
    assert app.picked["interests"] == []


def test_practical_screen_renders_sliders(app):
    app.step = app.total_steps + 1
    app._render()
    app.master.update_idletasks()
    assert app.years_lbl.winfo_exists()
    assert app.pay_lbl.winfo_exists()
    assert 0 <= app.years <= 8
    assert 1 <= app.pay <= 5


def test_results_screen_renders_from_a_real_ranking(app):
    from futureforge.textmatch import extract

    typed = {
        "interests": "i like biology and helping sick people",
        "subjects": "biology and chemistry",
        "work_style": "on a team, fast paced",
        "values": "helping others and job security",
    }
    for dimension, text in typed.items():
        app.answers[dimension] = text
        app.picked[dimension] = extract(dimension, text)

    app.recommendations = app.recommender.recommend(app.profile(), top_n=5)
    app.step = app.total_steps + 2
    app._render()
    app.master.update_idletasks()

    rows = app.tree.get_children()
    assert len(rows) == 5
    assert app.detail.get("1.0", "end").strip(), "detail pane should not be empty"


def test_results_screen_survives_an_empty_profile(app):
    """A student who skips every question must still reach a results screen."""
    app.recommendations = app.recommender.recommend(app.profile(), top_n=5)
    app.step = app.total_steps + 2
    app._render()
    app.master.update_idletasks()
    assert len(app.tree.get_children()) == 5


def test_navigation_forward_and_back(app):
    app.name_var.set("Maya")
    app.next()                      # intro -> question 1
    assert app.step == 1
    assert app.name == "Maya"
    app.next()                      # question 1 -> 2
    assert app.step == 2
    app.back()
    assert app.step == 1
    app.back()
    assert app.step == 0


def test_jump_only_goes_backwards(app):
    app.step = 3
    app._render()
    app.jump(1)
    assert app.step == 1, "jump should move back to an earlier step"
    app.jump(4)
    assert app.step == 1, "jump must not skip forward past unanswered questions"


def test_restart_clears_every_answer(app):
    app.answers["interests"] = "piano"
    app.picked["interests"] = ["performing"]
    app.recommendations = [object()]
    app.restart()
    assert app.step == 0
    assert app.picked["interests"] == []
    assert app.answers["interests"] == ""
    assert app.recommendations == []


def test_profile_reflects_what_was_picked_up(app):
    app.picked["interests"] = ["health"]
    app.picked["subjects"] = ["biology"]
    app.name = "Sam"
    app.years = 2
    app.pay = 5
    profile = app.profile()
    assert profile.name == "Sam"
    assert profile.interests == ["health"]
    assert profile.max_education_years == 2
    assert profile.salary_priority == 5
    assert sum(profile.normalized_weights().values()) == pytest.approx(1.0)
