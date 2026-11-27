"""Nov 27 2026 (Amit: "Team total must reconcile with batsman runs, extras and applicable penalty runs. Bowling
figures must reconcile with innings totals, accounting for byes and leg-byes. Overs and balls must be interpreted
correctly (4.3 means four overs and three balls ...). Dismissals must be compatible with the bowling figures.")"""

import copy

from app.scorecard_checks import overs_to_balls, reconciliation_problems


def _bat(name, runs, how="bowled", bowler="Heshad"):
    return {"player": {"name": name}, "runs": runs, "dismissal": {"type": how, "bowler": bowler}}


GOOD = {
    "match": {"overs_limit": 35},
    "innings": [{
        "batting_team": "Imran XI", "summary": {"runs": 140, "wickets": 2, "overs": 4.3},
        "batting": [_bat("Waqas", 110), _bat("Rafae", 18, "caught", "Dennis"), {"player": {"name": "Ali"}, "runs": 0, "dismissal": {"type": "not out"}}],
        "bowling": [{"player": {"name": "Heshad"}, "overs": 2.3, "runs_conceded": 70, "wickets": 1},
                    {"player": {"name": "Dennis"}, "overs": 2, "runs_conceded": 64, "wickets": 1}],
        "extras": {"wides": 4, "no_balls": 2, "byes": 4, "leg_byes": 2, "penalties": 0, "total": 12},
    }],
}


def test_overs_are_overs_and_balls():
    assert overs_to_balls("4.3") == 27 and overs_to_balls(4.3) == 27 and overs_to_balls(35) == 210
    assert overs_to_balls("4.6") is None and overs_to_balls("") is None


def test_a_card_that_reconciles_has_no_problems():
    assert reconciliation_problems(GOOD) == []


def test_total_with_penalty_runs():
    card = copy.deepcopy(GOOD)
    card["innings"][0]["extras"].update({"penalties": 5, "total": 17})
    card["innings"][0]["summary"]["runs"] = 145
    card["innings"][0]["bowling"][1]["runs_conceded"] = 64
    assert reconciliation_problems(card) == []  # bowlers: 145 - 4 byes - 2 leg byes - 5 penalty = 134
    card["innings"][0]["summary"]["runs"] = 150
    assert any("batters' runs (128)" in item and "150" in item for item in reconciliation_problems(card))


def test_bowling_against_total_minus_byes_and_leg_byes():
    card = copy.deepcopy(GOOD)
    card["innings"][0]["bowling"][0]["runs_conceded"] = 60
    assert any("bowlers' runs add up to 124" in item and "134" in item for item in reconciliation_problems(card))


def test_impossible_overs_and_overs_against_the_innings():
    card = copy.deepcopy(GOOD)
    card["innings"][0]["bowling"][1]["overs"] = 2.7
    assert any("2.7 overs" in item for item in reconciliation_problems(card))
    card = copy.deepcopy(GOOD)
    card["innings"][0]["summary"]["overs"] = 12
    assert any("bowlers' overs add up to 4.3" in item for item in reconciliation_problems(card))


def test_dismissals_against_bowling_figures():
    card = copy.deepcopy(GOOD)
    card["innings"][0]["bowling"][1]["wickets"] = 2
    assert any("Dennis has 2 wickets" in item for item in reconciliation_problems(card))
    card = copy.deepcopy(GOOD)
    card["innings"][0]["batting"][1]["dismissal"] = {"type": "run out", "bowler": "Dennis"}
    assert any("Dennis has 1 wicket" in item and "run outs don't count" in item for item in reconciliation_problems(card))
