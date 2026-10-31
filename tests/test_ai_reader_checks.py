"""AI scorecard reader self-checks (README "How the AI reader learns" -> "Cross-checks", Oct 30 2026).
Runs on the checked answer of worked example 3 (a printed Heartlake vs Toronto CC card): no false alarms on the
right answer, and every typical misread is caught. No AI key needed."""
import copy
import json
import sys
from pathlib import Path

APP = Path(__file__).resolve().parents[1] / "app"
sys.path.insert(0, str(APP))

import ai_vision as av  # noqa: E402

GOOD = json.loads((APP / "ai_examples" / "example_3.json").read_text(encoding="utf-8"))


def card():
    return copy.deepcopy(GOOD)


def test_right_answer_has_no_problems():
    assert av.cross_checks(card()) == []
    assert av.sum_problems(card()) == []


def test_caught_and_bowled_is_one_name():
    for written in ["c & b Singh", "c&b Singh", "C+B Singh", "ct & b Singh", "caught & bowled"]:
        t = card()
        row = t["innings"][0]["batting"][2]
        row["dismissal"] = {"type": "caught", "fielder": None, "bowler": "Singh", "written_as": written}
        av._normalise(t, "test")
        assert row["dismissal"]["type"] == "caught and bowled"
        assert row["dismissal"]["fielder"] == row["dismissal"]["bowler"] == "Singh"


def test_misreads_are_caught():
    cases = [
        (lambda t: t["innings"][0]["bowling"][0].update(runs_conceded=23), "bowlers' runs"),
        (lambda t: t["innings"][0]["bowling"][1].update(overs=1), "overs"),
        (lambda t: t["innings"][1]["bowling"][0].update(wickets=1), "Ishaan has 1"),
        (lambda t: t["innings"][0]["batting"][0]["dismissal"].update(bowler="Kham"), "no bowler with that name"),
        (lambda t: t["innings"][0]["batting"][5].update(sixes=7), "sixes"),
    ]
    for change, word in cases:
        t = card()
        change(t)
        assert any(word in p for p in av.cross_checks(t)), word


def test_empty_bowling_summary_is_fine():
    t = card()
    for row in t["innings"][0]["bowling"]:
        row.update(overs=None, runs_conceded=None, wickets=None)
    assert av.cross_checks(t) == []
