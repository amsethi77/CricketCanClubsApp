"""Nov 25 2026 (Dhruvika: "Bowling stats are not correct for the season for a particular club" - Heartlake 2026
showed Dev 3 wickets at the top while Amit S took 10 and Heshad 7 on the scorecards): a club's bowlers get their
wickets from the card's bowling table, the other team's bowlers don't count for the club."""

import json

from app import cricket_store as cs


def _member(name: str, club: str) -> dict:
    return {"id": name, "name": name, "primary_club_id": club, "aliases": []}


def _bat(name: str, how: str = "", bowler: str = "", fielder: str = "") -> dict:
    return {"player": {"name": name}, "runs": 5, "balls": 5, "dismissal": {"type": how or None, "bowler": bowler or None, "fielder": fielder or None}}


def _bowl(name: str, wickets: int) -> dict:
    return {"player": {"name": name}, "overs": 4, "runs_conceded": 20, "wickets": wickets}


CARD = {
    "match": {"date": "2026-07-05", "teams": {"team_1": "Heartlake Cricket Club", "team_2": "Imran XI"}},
    "innings": [
        {"inning_number": 1, "batting_team": "Heartlake Cricket Club", "bowling_team": "Imran XI",
         "batting": [_bat("Amit S", "caught", "Harris", "Ali"), _bat("Heshad", "not out")],
         "bowling": [_bowl("Harris", 1)]},
        {"inning_number": 2, "batting_team": "Imran XI", "bowling_team": "Heartlake Cricket Club",
         "batting": [_bat("Rafae", "caught", "Amit S", "Bim"), _bat("Abbas", "bowled", "Amit S"), _bat("Waqas", "caught and bowled", "Bim", "Bim"),
                     _bat("Navjot", "run out", "", "Heshad")],
         "bowling": [_bowl("Amit S", 2), _bowl("Heshad", 0)]},
    ],
}


def _upload() -> dict:
    return {"id": "card1", "status": "Approved", "club_id": "club-heartlake", "review_template_json": json.dumps(CARD),
            "suggested_performances": [{"player_name": "Amit S", "runs": 5, "balls": 5, "notes": "caught | bowler: Harris | fielder: Ali"},
                                       {"player_name": "Heshad", "runs": 5, "balls": 5, "notes": "not out"}]}


def test_club_bowlers_get_their_wickets_from_the_bowling_table():
    members = [_member(n, "club-heartlake") for n in ("Amit S", "Heshad", "Bim")] + [_member(n, "club-imran") for n in ("Harris", "Ali")]
    club = {"id": "club-heartlake", "name": "Heartlake Cricket Club", "aliases": []}
    rows = {row["player_name"]: row for row in cs.build_combined_player_stats([], [_upload()], members, club)}
    assert rows["Amit S"]["wickets"] == 2
    assert rows["Heshad"]["matches"] == 1  # played (bowled) even with no wicket
    assert rows["Bim"]["wickets"] == 1  # "c & b Bim" with no Bim in the table
    assert rows["Bim"]["catches"] == 2  # caught Rafae + caught and bowled Waqas
    assert rows["Harris"]["wickets"] == 0  # bowled for Imran XI: not a Heartlake wicket
    assert rows["Ali"]["catches"] == 0


def test_without_a_club_every_bowler_keeps_his_wickets():
    members = [_member(n, "x") for n in ("Amit S", "Harris")]
    rows = {row["player_name"]: row for row in cs.build_combined_player_stats([], [_upload()], members)}
    assert rows["Amit S"]["wickets"] == 2 and rows["Harris"]["wickets"] == 1
