"""Nov 25 2026 (Dhruvika: "Uploaded the second innings scorecard but it uploaded into 1st innings and then swapping
it but it never show me upload score card for any innings"): the other-innings photo goes into the innings the
scorer added it for, and the missing innings is worked out after a swap saved with Edit."""

from app.main import _join_innings_photos, _missing_innings_number, _usable_innings


def _innings(team: str, other: str, number: int, names: list[str]) -> dict:
    return {
        "inning_number": number,
        "batting_team": team,
        "bowling_team": other,
        "summary": {"runs": 10 * len(names), "wickets": 2, "overs": 10},
        "batting": [{"player": {"name": name}, "runs": 10} for name in names],
        "bowling": [],
    }


def _empty(team: str, other: str, number: int) -> dict:
    return {"inning_number": number, "batting_team": team, "bowling_team": other, "summary": {"runs": None}, "batting": [], "bowling": []}


def _card(*innings: dict) -> dict:
    return {"match": {"teams": {"team_1": "Strikers", "team_2": "Heartlake"}}, "innings": list(innings)}


STRIKERS = ["A One", "B Two", "C Three", "D Four"]
HEARTLAKE = ["E Five", "F Six", "G Seven", "H Eight"]


def _order(template: dict) -> list:
    return [(item["inning_number"], item["batting_team"]) for item in _usable_innings(template)]


def test_missing_innings_after_a_swap():
    assert _missing_innings_number(_card(_empty("Strikers", "Heartlake", 1), _innings("Heartlake", "Strikers", 2, HEARTLAKE))) == 1
    assert _missing_innings_number(_card(_innings("Strikers", "Heartlake", 1, STRIKERS), _empty("Heartlake", "Strikers", 2))) == 2
    assert _missing_innings_number(_card(_innings("Strikers", "Heartlake", 1, STRIKERS), _innings("Heartlake", "Strikers", 2, HEARTLAKE))) == 0
    assert _missing_innings_number(_card(_empty("Strikers", "Heartlake", 1))) == 1


def test_photo_goes_into_the_innings_it_was_added_for():
    card = _card(_empty("Strikers", "Heartlake", 1), _innings("Heartlake", "Strikers", 2, HEARTLAKE))
    page = _card(_innings("Strikers", "Heartlake", 1, STRIKERS))
    assert _order(_join_innings_photos(card, page, slot=1)) == [(1, "Strikers"), (2, "Heartlake")]


def test_reader_numbering_does_not_win_over_the_button():
    card = _card(_innings("Strikers", "Heartlake", 1, STRIKERS))
    page = _card(_innings("Heartlake", "Strikers", 1, HEARTLAKE))  # the reader called it the 1st innings
    assert _order(_join_innings_photos(card, page, slot=2)) == [(1, "Strikers"), (2, "Heartlake")]


def test_first_innings_tab_moves_the_cards_innings_to_second():
    card = _card(_innings("Heartlake", "Strikers", 1, HEARTLAKE))
    page = _card(_innings("Strikers", "Heartlake", 2, STRIKERS))
    assert _order(_join_innings_photos(card, page, slot=1)) == [(1, "Strikers"), (2, "Heartlake")]


def test_second_innings_photo_on_an_empty_card_stays_second():
    card = _card(_empty("Strikers", "Heartlake", 1), _empty("Heartlake", "Strikers", 2))
    page = _card(_innings("Heartlake", "Strikers", 1, HEARTLAKE))
    assert _order(_join_innings_photos(card, page, slot=2)) == [(2, "Heartlake")]


def test_without_a_slot_the_old_order_is_kept():
    card = _card(_innings("Heartlake", "Strikers", 2, HEARTLAKE))
    page = _card(_innings("Strikers", "Heartlake", 0, STRIKERS))
    assert _order(_join_innings_photos(card, page)) == [(1, "Strikers"), (2, "Heartlake")]
