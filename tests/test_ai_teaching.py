"""Nov 27 2026 (Dhruvika: "Enable AI training feature after the scorecard has been manually edited ... it should
learn from it and should apply in next or other scorecards"): what the AI learns from a fixed card."""

from app import ai_vision


def _bat(name: str, runs: int) -> dict:
    return {"player": {"name": name}, "runs": runs, "balls": runs + 2, "dismissal": {"type": "bowled", "bowler": "X"}}


def _card(waqas: int, total: int, extras: int | None = 12) -> dict:
    return {"innings": [{"inning_number": 1, "batting_team": "Imran XI", "summary": {"runs": total},
                         "batting": [_bat("Waqas", waqas), _bat("Rafae", 18)], "bowling": [{"player": {"name": "Heshad"}, "wickets": 1}],
                         "extras": {"total": extras}}]}


def test_a_card_that_adds_up_can_teach():
    assert ai_vision.learn_problem(_card(110, 140)) == ""


def test_a_card_that_does_not_add_up_says_why():
    problem = ai_vision.learn_problem(_card(110, 150))
    assert "Imran XI" in problem and "150" in problem
    assert "extras" in ai_vision.learn_problem(_card(110, 140, None))


def test_lessons_say_what_the_ai_read_wrong():
    lessons = ai_vision.correction_lessons(_card(11, 41), _card(110, 140))
    assert any("Waqas" in item and "110" in item and "11" in item for item in lessons)
    assert any("total is 140" in item for item in lessons)
    assert ai_vision.correction_lessons(_card(110, 140), _card(110, 140)) == []


def test_layout_similarity_is_bounded():
    assert ai_vision.layout_similarity([], [1.0]) == 0.0
    same = [0.1, 0.3, 0.2, 0.4] * 2
    assert ai_vision.layout_similarity(same, same) > 0.99
