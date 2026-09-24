"""Player and club insights: form, predictions and improvement recommendations.

Everything here is computed from the club's own stored records (live fixtures and approved
archive scorecards), so every number can be traced back to real games. The assistant chat
uses these results to answer "how is X doing", "predict", "how can X improve" questions,
and the Insights panel on the Assistant page shows them directly.

The analysis gets better automatically as more matches are scored and more archive
scorecards are approved: there is nothing to retrain.
"""

from __future__ import annotations

import re
from datetime import date
from math import sqrt
from typing import Any

try:
    import cricket_brain as _brain
    from cricket_store import (
        build_summary,
        canonical_archive_uploads,
        normalize_name,
        player_name_variants,
        scoped_store_for_club,
    )
except ModuleNotFoundError:  # running as the "app" package
    from app import cricket_brain as _brain
    from app.cricket_store import (
        build_summary,
        canonical_archive_uploads,
        normalize_name,
        player_name_variants,
        scoped_store_for_club,
    )


RECENT_WINDOW = 5
MIN_INNINGS_FOR_FORM = 3
PRIOR_WEIGHT = 3  # how many "average innings" we blend into small samples


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _round(value: float, digits: int = 1) -> float:
    return round(float(value or 0.0), digits)


def _mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def _stdev(values: list[float]) -> float:
    if len(values) < 2:
        return 0.0
    mean = _mean(values)
    return sqrt(sum((value - mean) ** 2 for value in values) / (len(values) - 1))


def _slope(values: list[float]) -> float:
    """Least-squares slope of values over their index (runs per innings)."""
    n = len(values)
    if n < 3:
        return 0.0
    xs = list(range(n))
    mean_x = _mean(xs)
    mean_y = _mean(values)
    denominator = sum((x - mean_x) ** 2 for x in xs)
    if not denominator:
        return 0.0
    return sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, values)) / denominator


def global_store(store: dict[str, Any]) -> dict[str, Any]:
    """Full (all clubs) view of the store, whether we got a chat store or a plain one."""
    if store.get("all_members") or store.get("all_fixtures"):
        return _brain._global_analysis_store(store)
    return store


def _member_label(member: dict[str, Any]) -> str:
    full = str(member.get("full_name") or "").strip()
    name = str(member.get("name") or "").strip()
    return full or name or "Player"


def find_member(store: dict[str, Any], name_or_id: str) -> dict[str, Any] | None:
    key = str(name_or_id or "").strip()
    if not key:
        return None
    members = list(store.get("members") or [])
    for member in members:
        if str(member.get("id") or "") == key:
            return member
    wanted = normalize_name(key)
    for member in members:
        variants = {normalize_name(variant) for variant in player_name_variants(member)}
        variants.add(normalize_name(member.get("name") or ""))
        variants.add(normalize_name(member.get("full_name") or ""))
        if wanted in variants:
            return member
    return None


def find_club(store: dict[str, Any], name_or_id: str) -> dict[str, Any] | None:
    key = str(name_or_id or "").strip()
    if not key:
        return None
    wanted = normalize_name(key)
    for club in store.get("clubs") or []:
        if str(club.get("id") or "") == key:
            return club
        if wanted in {normalize_name(club.get("name") or ""), normalize_name(club.get("short_name") or "")}:
            return club
    return None


# ---------------------------------------------------------------------------
# Player insights
# ---------------------------------------------------------------------------
def _batting_innings(store: dict[str, Any], member: dict[str, Any]) -> list[dict[str, Any]]:
    entries = _brain._player_participation_entries(store, member)
    innings = [entry for entry in entries if int(entry.get("batting_innings") or 0) > 0]
    innings.sort(key=lambda entry: str(entry.get("date") or ""))
    return innings


def _all_player_innings_average(store: dict[str, Any]) -> float:
    """Average runs per innings across every player (the 'prior' for small samples)."""
    totals = [
        (int(row.get("runs") or 0), int(row.get("batting_innings") or 0))
        for row in store.get("member_summary_stats") or []
        if int(row.get("batting_innings") or 0) > 0
    ]
    runs = sum(item[0] for item in totals)
    innings = sum(item[1] for item in totals)
    return runs / innings if innings else 12.0


def player_insights(store: dict[str, Any], member: dict[str, Any]) -> dict[str, Any]:
    store = global_store(store)
    entries = _brain._player_participation_entries(store, member)
    innings = _batting_innings(store, member)
    runs_list = [float(entry.get("runs") or 0) for entry in innings]
    n = len(runs_list)

    matches = len({entry.get("key") for entry in entries})
    total_runs = int(sum(runs_list))
    outs = sum(int(entry.get("outs") or 0) for entry in innings)
    balls_innings = [entry for entry in innings if int(entry.get("balls") or 0) > 0]
    sr_runs = sum(int(entry.get("runs") or 0) for entry in balls_innings)
    balls = sum(int(entry.get("balls") or 0) for entry in balls_innings)
    wickets = sum(int(entry.get("wickets") or 0) for entry in entries)
    catches = sum(int(entry.get("catches") or 0) for entry in entries)
    average = total_runs / outs if outs else (total_runs / n if n else 0.0)
    per_innings = total_runs / n if n else 0.0
    strike_rate = (sr_runs / balls * 100) if balls else None
    highest = int(max(runs_list)) if runs_list else 0

    # Career totals: use the same saved stats the rest of the app shows (Profile, rankings)
    summary_row = next(
        (
            row
            for row in store.get("member_summary_stats") or []
            if str(row.get("member_id") or "") == str(member.get("id") or "")
            or normalize_name(row.get("player_name") or "") == normalize_name(member.get("name") or "")
        ),
        None,
    )
    if summary_row:
        matches = int(summary_row.get("matches") or matches)
        total_runs = int(summary_row.get("runs") or total_runs)
        average = float(summary_row.get("batting_average") or average)
        highest = int(summary_row.get("highest_score") or highest)
        wickets = int(summary_row.get("wickets") or wickets)
        catches = int(summary_row.get("catches") or catches)
        balls = int(summary_row.get("balls") or balls)
        strike_rate = float(summary_row.get("strike_rate") or 0) or strike_rate
        innings_total = int(summary_row.get("batting_innings") or n)
    else:
        innings_total = n
    if balls < 20:
        strike_rate = None  # too few balls recorded to mean anything

    recent = runs_list[-RECENT_WINDOW:]
    recent_avg = _mean(recent)
    prior = _all_player_innings_average(store)

    # Form: recent innings vs the player's own normal level
    if n < MIN_INNINGS_FOR_FORM:
        form = {"label": "Not enough data", "key": "unknown", "detail": f"Only {n} innings recorded so far."}
    else:
        baseline = per_innings or prior
        ratio = recent_avg / baseline if baseline else 1.0
        if ratio >= 1.25:
            form = {"label": "In form", "key": "hot", "detail": f"Averaging {recent_avg:.1f} in the last {len(recent)} innings vs {baseline:.1f} overall."}
        elif ratio <= 0.75:
            form = {"label": "Out of form", "key": "cold", "detail": f"Averaging {recent_avg:.1f} in the last {len(recent)} innings vs {baseline:.1f} overall."}
        else:
            form = {"label": "Steady", "key": "steady", "detail": f"Averaging {recent_avg:.1f} in the last {len(recent)} innings, close to {baseline:.1f} overall."}

    trend_slope = _slope(runs_list[-8:])
    trend = "rising" if trend_slope > 1.5 else "falling" if trend_slope < -1.5 else "flat"

    # Prediction for the next innings: recent-weighted average, blended with the overall
    # player average when there are only a few innings.
    weights = list(range(1, len(recent) + 1))
    weighted_recent = sum(w * r for w, r in zip(weights, recent)) / sum(weights) if recent else prior
    blended = (n * (0.6 * weighted_recent + 0.4 * per_innings) + PRIOR_WEIGHT * prior) / (n + PRIOR_WEIGHT) if n else prior
    spread = _stdev(runs_list) if n >= 3 else max(8.0, blended * 0.8)
    low = max(0, round(blended - 0.6 * spread))
    high = max(low + 2, round(blended + 0.6 * spread))
    chance_25 = (sum(1 for runs in runs_list if runs >= 25) + 1) / (n + 2) if n else 0.2
    chance_50 = (sum(1 for runs in runs_list if runs >= 50) + 0.5) / (n + 2) if n else 0.05
    confidence = "low" if n < 4 else "medium" if n < 10 else "good"

    scores_25_49 = sum(1 for runs in runs_list if 25 <= runs < 50)
    scores_50 = sum(1 for runs in runs_list if runs >= 50)
    low_scores = sum(1 for runs in runs_list if runs < 10)

    recommendations: list[dict[str, str]] = []

    def tip(title: str, why: str, kind: str = "batting") -> None:
        recommendations.append({"title": title, "why": why, "area": kind})

    if n < MIN_INNINGS_FOR_FORM:
        tip(
            "Get more innings on record",
            f"Only {n} innings are recorded. Predictions become reliable after about 5 innings, so upload old scorecards in Archives.",
            "data",
        )
    if n and len(balls_innings) < n / 2:
        tip(
            "Record balls faced",
            f"Balls faced are recorded in only {len(balls_innings)} of {n} innings, so strike rate and tempo can't be judged properly. Ask the scorer to note balls faced.",
            "data",
        )
    if strike_rate is not None and len(balls_innings) >= 2:
        if strike_rate < 90:
            tip("Rotate the strike more", f"Strike rate is {strike_rate:.0f}. Look for quick singles and work the ball into gaps to keep the scoreboard moving.")
        elif strike_rate > 150 and per_innings < 15:
            tip("Build the innings before attacking", f"Strike rate is {strike_rate:.0f} but innings are short ({per_innings:.1f} runs each). Take a few balls to settle before going big.")
    if n >= 4 and low_scores / n >= 0.5:
        tip(
            "Survive the first 10 balls",
            f"{low_scores} of {n} innings ended under 10 runs. Leave wide balls early and focus on getting set in the first overs.",
        )
    if scores_25_49 >= 2 and scores_50 == 0:
        tip(
            "Convert starts into big scores",
            f"Reached 25+ {scores_25_49} times without a fifty. Once set, bat deeper and avoid risky shots between 30 and 50.",
        )
    if form["key"] == "cold":
        tip("Extra net time before the next match", form["detail"] + " A focused net session on the basics usually helps.")
    if form["key"] == "hot":
        tip("Keep them high in the order", form["detail"] + " Give this player more overs at the crease while in form.", "selection")
    if matches >= 3 and wickets == 0:
        tip("Develop a second skill", f"No wickets in {matches} matches. Part-time bowling or keeping makes selection easier.", "all-round")
    if matches >= 4 and catches == 0:
        tip("Fielding drills", f"No catches recorded in {matches} matches. Catching practice adds value even on low-scoring days.", "fielding")
    if matches >= 2 and wickets / max(matches, 1) >= 1:
        tip("Use as a front-line bowler", f"{wickets} wickets in {matches} matches ({wickets / matches:.1f} per match).", "bowling")

    best_position = None
    try:
        best_position = _brain._best_batting_position(store, str(member.get("name") or ""))
    except Exception:
        best_position = None

    timeline = [
        {
            "date": str(entry.get("date") or ""),
            "opponent": str(entry.get("opponent") or ""),
            "runs": int(entry.get("runs") or 0),
            "balls": int(entry.get("balls") or 0),
            "team": str(entry.get("team_label") or ""),
        }
        for entry in innings[-10:]
    ]

    return {
        "player": {
            "id": str(member.get("id") or ""),
            "name": str(member.get("name") or ""),
            "full_name": _member_label(member),
            "role": str(member.get("role") or ""),
            "club": str(member.get("primary_club_name") or ""),
        },
        "career": {
            "matches": matches,
            "innings": innings_total,
            "runs": total_runs,
            "average": _round(average, 2),
            "runs_per_innings": _round(per_innings, 1),
            "strike_rate": _round(strike_rate, 1) if strike_rate is not None else None,
            "highest": highest,
            "fifties": int(summary_row.get("scores_50_plus") or scores_50) if summary_row else scores_50,
            "wickets": wickets,
            "catches": catches,
        },
        "form": {**form, "recent_runs": [int(value) for value in recent], "recent_average": _round(recent_avg), "trend": trend},
        "prediction": {
            "expected_runs": round(blended),
            "range": [int(low), int(high)],
            "chance_25_plus": round(chance_25 * 100),
            "chance_50_plus": round(chance_50 * 100),
            "confidence": confidence,
            "based_on_innings": n,
        },
        "best_position": best_position,
        "recommendations": recommendations[:6],
        "timeline": timeline,
    }


# ---------------------------------------------------------------------------
# Club insights
# ---------------------------------------------------------------------------
def _club_record(store: dict[str, Any], club: dict[str, Any]) -> dict[str, Any]:
    club_store = scoped_store_for_club(store, club)
    summary = build_summary(club_store)
    played = int(summary.get("matches_played") or 0)
    won = int(summary.get("matches_won") or 0)
    lost = int(summary.get("matches_lost") or 0)
    return {
        "club_id": str(club.get("id") or ""),
        "club_name": str(club.get("name") or ""),
        "played": played,
        "won": won,
        "lost": lost,
        "win_rate": (won / played) if played else 0.0,
        "smoothed": (won + 1) / (played + 2),
        "store": club_store,
        "summary": summary,
    }


def club_table(store: dict[str, Any]) -> list[dict[str, Any]]:
    store = global_store(store)
    rows = [_club_record(store, club) for club in store.get("clubs") or []]
    rows.sort(key=lambda row: (-row["smoothed"], -row["played"], row["club_name"].lower()))
    for position, row in enumerate(rows, start=1):
        row["rank"] = position
    return rows


def _club_members(store: dict[str, Any], club: dict[str, Any]) -> list[dict[str, Any]]:
    club_id = str(club.get("id") or "")
    members = []
    for member in store.get("members") or []:
        ids = {str(item.get("club_id") or "") for item in member.get("club_memberships") or [] if isinstance(item, dict)}
        ids.add(str(member.get("primary_club_id") or ""))
        if club_id in ids:
            members.append(member)
    return members


def _next_fixture(club_store: dict[str, Any], club: dict[str, Any]) -> dict[str, Any] | None:
    today = date.today().isoformat()
    club_id = str(club.get("id") or "")
    upcoming = [
        fixture
        for fixture in club_store.get("fixtures") or []
        if str(fixture.get("club_id") or club_id) == club_id
        and str(fixture.get("date") or "") >= today
        and str(fixture.get("status") or "").lower() != "completed"
    ]
    upcoming.sort(key=lambda fixture: str(fixture.get("date") or ""))
    return upcoming[0] if upcoming else None


def win_chance(store: dict[str, Any], club_name: str, opponent_name: str) -> dict[str, Any]:
    table = {normalize_name(row["club_name"]): row for row in club_table(store)}
    club_row = table.get(normalize_name(club_name))
    opponent_row = table.get(normalize_name(opponent_name))
    club_strength = club_row["smoothed"] if club_row else 0.5
    opponent_strength = opponent_row["smoothed"] if opponent_row else 0.5
    chance = club_strength / (club_strength + opponent_strength) if (club_strength + opponent_strength) else 0.5
    games = (club_row["played"] if club_row else 0) + (opponent_row["played"] if opponent_row else 0)
    return {
        "club": club_name,
        "opponent": opponent_name,
        "win_chance": round(chance * 100),
        "confidence": "low" if games < 6 else "medium" if games < 16 else "good",
        "opponent_known": bool(opponent_row),
    }


def club_insights(store: dict[str, Any], club: dict[str, Any]) -> dict[str, Any]:
    store = global_store(store)
    table = club_table(store)
    row = next((item for item in table if item["club_id"] == str(club.get("id") or "")), None) or _club_record(store, club)
    club_store = row["store"]

    members = _club_members(store, club)
    players = []
    for member in members:
        info = player_insights(store, member)
        if info["career"]["innings"] or info["career"]["wickets"]:
            players.append(info)
    players.sort(key=lambda info: -info["career"]["runs"])
    total_runs = sum(info["career"]["runs"] for info in players)
    top_two = sum(info["career"]["runs"] for info in players[:2])
    dependence = (top_two / total_runs) if total_runs else 0.0
    wicket_takers = [info for info in players if info["career"]["wickets"] > 0]
    in_form = [info["player"]["name"] for info in players if info["form"]["key"] == "hot"]
    out_of_form = [info["player"]["name"] for info in players if info["form"]["key"] == "cold"]

    next_fixture = _next_fixture(club_store, club)
    next_match = None
    if next_fixture:
        available = [
            name
            for name, status in (next_fixture.get("availability_statuses") or {}).items()
            if str(status or "").lower() == "available"
        ]
        next_match = {
            "date": str(next_fixture.get("date") or ""),
            "opponent": str(next_fixture.get("opponent") or ""),
            "available": len(available),
            **win_chance(store, str(club.get("name") or ""), str(next_fixture.get("opponent") or "")),
        }

    archives = canonical_archive_uploads(club_store.get("archive_uploads") or [])
    approved = sum(1 for item in archives if str(item.get("status") or "").lower() == "approved")
    pending = sum(1 for item in archives if "review" in str(item.get("status") or "").lower() or str(item.get("status") or "").lower() == "pending")

    recommendations: list[dict[str, str]] = []

    def tip(title: str, why: str, area: str) -> None:
        recommendations.append({"title": title, "why": why, "area": area})

    if row["played"] < 5:
        tip(
            "Record more results",
            (
                "No match results are recorded yet, so the club can't be ranked."
                if not row["played"]
                else f"Only {_n(row['played'], 'result')} on record, so the ranking is based on very few games."
            )
            + " Score every match live or upload the scorecard afterwards.",
            "data",
        )
    elif row["win_rate"] < 0.4:
        tip(
            "Focus on winning the close games",
            f"Won {row['won']} of {row['played']} ({row['win_rate'] * 100:.0f}%). Review the last few losses in Scorecards to see whether batting totals or bowling was short.",
            "results",
        )
    if dependence >= 0.6 and len(players) >= 4:
        top_names = ", ".join(info["player"]["name"] for info in players[:2])
        tip(
            "Build batting depth",
            f"{top_names} score {dependence * 100:.0f}% of the club's runs. Give the middle order more time at the crease in friendlies and nets.",
            "batting",
        )
    if len(wicket_takers) < 3 and len(players) >= 5:
        tip(
            "Develop more bowlers",
            f"Only {len(wicket_takers)} players have taken wickets. A wider bowling attack makes the team harder to beat.",
            "bowling",
        )
    if next_match and next_match["available"] < 11:
        tip(
            "Chase availability for the next match",
            f"Only {next_match['available']} players are marked available for {next_match['date']} vs {next_match['opponent']}. Remind the squad to respond.",
            "selection",
        )
    if pending:
        tip(
            "Review pending scorecards",
            f"{pending} uploaded scorecards are waiting for review. Approving them adds their runs and wickets to everyone's stats.",
            "data",
        )
    if out_of_form:
        tip(
            "Support out-of-form players",
            f"{', '.join(out_of_form[:4])} {'is' if len(out_of_form) == 1 else 'are'} below their usual level. Extra net time or a change of batting position can help.",
            "players",
        )
    if in_form:
        tip(
            "Back the in-form players",
            f"{', '.join(in_form[:4])} {'is' if len(in_form) == 1 else 'are'} scoring above their normal level. Give them key roles in the next match.",
            "selection",
        )

    return {
        "club": {"id": row["club_id"], "name": row["club_name"]},
        "record": {
            "played": row["played"],
            "won": row["won"],
            "lost": row["lost"],
            "win_rate": round(row["win_rate"] * 100),
            "rank": row.get("rank"),
            "clubs_ranked": len(table),
        },
        "batting": {
            "total_runs": total_runs,
            "top_scorers": [
                {"name": info["player"]["name"], "runs": info["career"]["runs"], "form": info["form"]["label"]}
                for info in players[:5]
            ],
            "top_two_share": round(dependence * 100),
        },
        "bowling": {
            "wicket_takers": [
                {"name": info["player"]["name"], "wickets": info["career"]["wickets"]}
                for info in sorted(wicket_takers, key=lambda info: -info["career"]["wickets"])[:5]
            ]
        },
        "form": {"in_form": in_form, "out_of_form": out_of_form},
        "next_match": next_match,
        "scorecards": {"approved": approved, "pending": pending},
        "recommendations": recommendations[:6],
    }


# ---------------------------------------------------------------------------
# Chat answers
# ---------------------------------------------------------------------------
_IMPROVE_WORDS = ("improve", "better", "tips", "tip ", "advice", "advise", "recommend", "suggest", "work on", "weakness", "strength", "coach", "develop", "increase", "boost", "raise", "climb")
_PREDICT_WORDS = ("will win", "who wins", "winner", "beat", "predict", "prediction", "forecast", "projected", "projection", "expect", "chance", "chances", "likely", "probability", "odds", "will score", "next match", "next game", "next innings")
_FORM_WORDS = ("form", "how is", "how's", "how has", "how have", "doing", "performing", "performance", "stats", "statistics", "record", "profile", "about", "summary", "analysis", "analyse", "analyze")
_LEADER_PATTERNS = (
    (re.compile(r"\b(top|most|highest|best|leading)\b.*\b(run|runs|scorer|scorers|batter|batters|batsman|batsmen)\b"), "runs"),
    (re.compile(r"\b(top|most|best|leading)\b.*\b(wicket|wickets|bowler|bowlers)\b"), "wickets"),
    (re.compile(r"\b(rank|ranking|rankings|table|standings|best club|top club|top clubs)\b"), "clubs"),
)


def _has_any(text: str, words: tuple[str, ...]) -> bool:
    return any(word in text for word in words)


def _matched_clubs(question: str, store: dict[str, Any]) -> list[dict[str, Any]]:
    q = f" {normalize_name(question)} "
    found: list[tuple[int, dict[str, Any]]] = []
    for club in store.get("clubs") or []:
        for variant in {club.get("name") or "", club.get("short_name") or ""}:
            variant = normalize_name(variant)
            if len(variant) >= 3 and f" {variant} " in q:
                found.append((-len(variant), club))
                break
    found.sort(key=lambda item: item[0])
    seen: set[str] = set()
    clubs: list[dict[str, Any]] = []
    for _, club in found:
        if club.get("id") not in seen:
            seen.add(club.get("id"))
            clubs.append(club)
    return clubs


def _n(count: int, word: str) -> str:
    """'1 match', '3 matches'."""
    plural = word + ("es" if word.endswith(("ch", "sh", "s", "x")) else "s")
    return f"{count} {word if count == 1 else plural}"


def _bullets(items: list[str]) -> str:
    return "\n".join(f"• {item}" for item in items)


def _player_answer(info: dict[str, Any], intent: str) -> str:
    player = info["player"]["full_name"]
    career = info["career"]
    form = info["form"]
    prediction = info["prediction"]
    lines: list[str] = []
    if intent in ("form", "predict", "improve"):
        sr = f", strike rate {career['strike_rate']}" if career["strike_rate"] is not None else ""
        lines.append(
            f"{player}: {_n(career['runs'], 'run')} in {career['innings']} innings (average {career['average']}{sr}, best {career['highest']}), "
            f"{_n(career['wickets'], 'wicket')} and {_n(career['catches'], 'catch')} in {_n(career['matches'], 'match')}."
        )
        if form["key"] != "unknown":
            recent = ", ".join(str(value) for value in form["recent_runs"])
            lines.append(f"Form: {form['label']}. Last {len(form['recent_runs'])} innings: {recent} (trend {form['trend']}).")
        else:
            lines.append(f"Form: {form['detail']}")
    if intent in ("predict", "form"):
        low, high = prediction["range"]
        lines.append(
            f"Next innings projection: about {prediction['expected_runs']} runs (likely {low}–{high}), "
            f"{prediction['chance_25_plus']}% chance of 25+ and {prediction['chance_50_plus']}% chance of 50+ "
            f"(confidence: {prediction['confidence']}, based on {prediction['based_on_innings']} innings)."
        )
    if intent == "improve" or (intent == "form" and info["recommendations"]):
        tips = info["recommendations"][:4] if intent == "improve" else info["recommendations"][:2]
        if tips:
            lines.append(("How to improve:" if intent == "improve" else "Suggestions:") + "\n" + _bullets([f"{tip['title']}: {tip['why']}" for tip in tips]))
        elif intent == "improve":
            lines.append("No clear weak spots in the recorded data. Keep scoring and recording balls faced so we can spot trends.")
    return "\n\n".join(lines)


def _club_answer(info: dict[str, Any], intent: str) -> str:
    club = info["club"]["name"]
    record = info["record"]
    if record["played"]:
        lines = [
            f"{club}: won {record['won']} of {_n(record['played'], 'recorded result')} ({record['win_rate']}%), "
            f"ranked {record['rank']} of {record['clubs_ranked']} clubs."
        ]
    else:
        lines = [f"{club}: no match results are recorded yet, so it can't be ranked on results."]
    top = info["batting"]["top_scorers"][:3]
    if top:
        lines.append("Top run scorers: " + ", ".join(f"{item['name']} {item['runs']} ({item['form'].lower()})" for item in top) + ".")
    wickets = info["bowling"]["wicket_takers"][:3]
    if wickets:
        lines.append("Leading wicket takers: " + ", ".join(f"{item['name']} {item['wickets']}" for item in wickets) + ".")
    next_match = info.get("next_match")
    if next_match and intent in ("predict", "form", "improve"):
        lines.append(
            f"Next match: {next_match['date']} vs {next_match['opponent']}, estimated {next_match['win_chance']}% win chance "
            f"(confidence: {next_match['confidence']}). {next_match['available']} players available so far."
        )
    elif intent == "predict":
        lines.append("There is no upcoming fixture on record to predict. Add fixtures to get match predictions.")
    tips = info["recommendations"][: (5 if intent == "improve" else 2)]
    if tips:
        lines.append(("How to improve the ranking:" if intent == "improve" else "Suggestions:") + "\n" + _bullets([f"{tip['title']}: {tip['why']}" for tip in tips]))
    return "\n\n".join(lines)


def _leaders_answer(store: dict[str, Any], kind: str) -> str:
    if kind == "clubs":
        table = club_table(store)
        rows = [row for row in table if row["played"]][:8]
        if not rows:
            return "No match results are recorded yet, so there is no club ranking."
        return "Club ranking (by results, adjusted for games played):\n" + _bullets(
            [f"{row['rank']}. {row['club_name']}: won {row['won']} of {row['played']} ({row['win_rate'] * 100:.0f}%)" for row in rows]
        )
    stats = sorted(
        store.get("member_summary_stats") or [],
        key=lambda row: -int(row.get("runs" if kind == "runs" else "wickets") or 0),
    )[:5]
    if kind == "runs":
        return "Top run scorers:\n" + _bullets(
            [f"{row.get('full_name') or row.get('player_name')}: {_n(int(row.get('runs') or 0), 'run')} in {_n(int(row.get('matches') or 0), 'match')} (avg {row.get('batting_average', 0)})" for row in stats]
        )
    return "Top wicket takers:\n" + _bullets(
        [f"{row.get('full_name') or row.get('player_name')}: {_n(int(row.get('wickets') or 0), 'wicket')} in {_n(int(row.get('matches') or 0), 'match')}" for row in stats]
    )


def answer(question: str, store: dict[str, Any]) -> dict[str, Any] | None:
    """Return an insights answer for the chat, or None if the question isn't one we handle."""
    text = f" {str(question or '').lower().strip()} "
    full = global_store(store)
    members = _brain._matched_members(question, list(full.get("members") or []))
    clubs = _matched_clubs(question, full)
    if not clubs and re.search(r"\b(my|our|this) (club|team)\b", text):
        focus = store.get("focus_club") or store.get("club") or {}
        if focus.get("id"):
            clubs = [focus]

    wants_improve = _has_any(text, _IMPROVE_WORDS)
    wants_predict = _has_any(text, _PREDICT_WORDS)
    wants_form = _has_any(text, _FORM_WORDS)
    intent = "improve" if wants_improve else "predict" if wants_predict else "form" if wants_form else ""

    if members and intent:
        parts = [_player_answer(player_insights(full, member), intent) for member in members[:3]]
        return {"answer": "\n\n———\n\n".join(parts), "mode": f"insights-player-{intent}"}

    if clubs and intent:
        # "Coca Cola XI vs TP Community" style match prediction
        if len(clubs) >= 2 and wants_predict:
            result = win_chance(full, str(clubs[0].get("name") or ""), str(clubs[1].get("name") or ""))
            return {
                "answer": f"Estimated win chance: {result['club']} {result['win_chance']}% vs {result['opponent']} {100 - result['win_chance']}% "
                f"(confidence: {result['confidence']}). This is based on each club's recorded results.",
                "mode": "insights-matchup",
            }
        parts = [_club_answer(club_insights(full, club), intent) for club in clubs[:2]]
        return {"answer": "\n\n———\n\n".join(parts), "mode": f"insights-club-{intent}"}

    for pattern, kind in _LEADER_PATTERNS:
        if pattern.search(text):
            return {"answer": _leaders_answer(full, kind), "mode": f"insights-leaders-{kind}"}

    return None


# ---------------------------------------------------------------------------
# Best playing XI
# ---------------------------------------------------------------------------
def _is_keeper(member: dict[str, Any]) -> bool:
    return "keep" in str(member.get("role") or "").lower()


def _bowls(member: dict[str, Any]) -> bool:
    role = str(member.get("role") or "").lower()
    style = str(member.get("bowling_style") or "").strip().lower()
    return "bowl" in role or "all-round" in role or "allround" in role or (bool(style) and style not in {"n/a", "na", "none", "-"})


def _order_slot(member: dict[str, Any], info: dict[str, Any]) -> int:
    """Rough batting order preference: openers first, tail last."""
    role = str(member.get("role") or "").lower()
    best = info.get("best_position") or {}
    if best.get("position"):
        return int(best["position"])
    if "open" in role:
        return 1
    if "one down" in role:
        return 3
    if "captain" in role or "batter" in role and "low" not in role:
        return 4
    if "all-round" in role:
        return 6
    if "keep" in role:
        return 7
    if "low order" in role:
        return 8
    if "bowl" in role:
        return 9
    return 7


def _status_for(statuses: dict[str, Any], member: dict[str, Any]) -> str:
    wanted = {normalize_name(variant) for variant in player_name_variants(member)}
    wanted.add(normalize_name(member.get("name") or ""))
    for name, status in (statuses or {}).items():
        if normalize_name(name) in wanted:
            value = str(status or "").strip().lower()
            if value.startswith("avail"):
                return "available"
            if value.startswith("maybe"):
                return "maybe"
            if "not" in value or value.startswith("unavail"):
                return "unavailable"
    return "no response"


def best_xi(store: dict[str, Any], club: dict[str, Any]) -> dict[str, Any]:
    """Suggest the strongest XI for the next fixture from available players."""
    store = global_store(store)
    club_store = scoped_store_for_club(store, club)
    fixture = _next_fixture(club_store, club)
    statuses = dict((fixture or {}).get("availability_statuses") or {})

    candidates: list[dict[str, Any]] = []
    for member in _club_members(store, club):
        info = player_insights(store, member)
        career = info["career"]
        matches = max(career["matches"], 1)
        batting_value = float(info["prediction"]["expected_runs"]) if career["innings"] else 5.0
        wickets_per_match = career["wickets"] / matches
        bowling_value = wickets_per_match * 18 + (6 if _bowls(member) else 0)
        fielding_value = (career["catches"] / matches) * 6 + (8 if _is_keeper(member) else 0)
        form_bonus = {"hot": 4, "cold": -3}.get(info["form"]["key"], 0)
        status = _status_for(statuses, member) if fixture else "available"
        candidates.append(
            {
                "member": member,
                "info": info,
                "status": status,
                "batting": batting_value,
                "bowling": bowling_value,
                "score": batting_value + bowling_value + fielding_value + form_bonus,
                "keeper": _is_keeper(member),
                "bowler": _bowls(member) or career["wickets"] > 0,
            }
        )

    pool = [c for c in candidates if c["status"] == "available"]
    reserves = [c for c in candidates if c["status"] in ("maybe", "no response")]
    using_all = False
    if not fixture:
        using_all = True
    elif len(pool) < 11:
        pool = pool + sorted(reserves, key=lambda c: (c["status"] != "maybe", -c["score"]))[: 11 - len(pool)]

    chosen: list[dict[str, Any]] = []

    def take(candidate: dict[str, Any], reason: str) -> None:
        if candidate not in chosen and len(chosen) < 11:
            candidate["reason"] = reason
            chosen.append(candidate)

    def why(candidate: dict[str, Any]) -> str:
        career = candidate["info"]["career"]
        parts = []
        if candidate["keeper"]:
            parts.append("keeps wicket")
        if career["innings"]:
            parts.append(f"projects ~{candidate['info']['prediction']['expected_runs']} runs")
        if career["wickets"]:
            parts.append(_n(career["wickets"], "wicket"))
        elif candidate["bowler"]:
            parts.append("bowling option")
        if candidate["info"]["form"]["key"] == "hot":
            parts.append("in form")
        return ", ".join(parts).capitalize() if parts else "Squad player"

    keepers = sorted([c for c in pool if c["keeper"]], key=lambda c: -c["score"])
    if keepers:
        take(keepers[0], why(keepers[0]))
    for candidate in sorted([c for c in pool if c["bowler"]], key=lambda c: -c["bowling"])[:5]:
        take(candidate, why(candidate))
    for candidate in sorted(pool, key=lambda c: -c["batting"]):
        if len(chosen) >= 11:
            break
        take(candidate, why(candidate))

    chosen.sort(key=lambda c: (_order_slot(c["member"], c["info"]), -c["batting"]))
    xi = [
        {
            "order": index + 1,
            "name": c["info"]["player"]["full_name"],
            "short_name": c["info"]["player"]["name"],
            "role": str(c["member"].get("role") or "Player") or "Player",
            "status": c["status"],
            "form": c["info"]["form"]["label"],
            "reason": c["reason"],
        }
        for index, c in enumerate(chosen)
    ]
    left_out = [
        c["info"]["player"]["full_name"]
        for c in sorted(pool, key=lambda c: -c["score"])
        if c not in chosen
    ][:4]
    bowling_options = sum(1 for c in chosen if c["bowler"])
    notes = []
    if fixture and len([c for c in candidates if c["status"] == "available"]) < 11:
        notes.append(
            f"Only {len([c for c in candidates if c['status'] == 'available'])} players are marked available, so the XI includes players who said Maybe or haven't replied."
        )
    if len(candidates) < 11:
        notes.append(f"The squad only has {len(candidates)} registered players. Add more players to pick a full XI.")
    if bowling_options < 5:
        notes.append(f"Only {bowling_options} bowling option{'' if bowling_options == 1 else 's'} in this XI. Consider adding a part-time bowler.")
    if not any(c["keeper"] for c in chosen):
        notes.append("No specialist wicket keeper is available. Pick someone to keep.")
    return {
        "club": {"id": str(club.get("id") or ""), "name": str(club.get("name") or "")},
        "fixture": (
            {"date": str(fixture.get("date") or ""), "opponent": str(fixture.get("opponent") or ""), "id": str(fixture.get("id") or "")}
            if fixture
            else None
        ),
        "based_on": "availability" if fixture else "all players (no upcoming fixture)",
        "xi": xi,
        "left_out": left_out,
        "notes": notes,
        "squad_size": len(candidates),
    }


# ---------------------------------------------------------------------------
# Season outlook
# ---------------------------------------------------------------------------
def season_outlook(store: dict[str, Any], club: dict[str, Any]) -> dict[str, Any]:
    store = global_store(store)
    table = club_table(store)
    row = next((item for item in table if item["club_id"] == str(club.get("id") or "")), None) or _club_record(store, club)
    club_store = row["store"]
    today = date.today().isoformat()
    club_id = str(club.get("id") or "")
    remaining = sorted(
        [
            fixture
            for fixture in club_store.get("fixtures") or []
            if str(fixture.get("club_id") or club_id) == club_id
            and str(fixture.get("date") or "") >= today
            and str(fixture.get("status") or "").lower() != "completed"
        ],
        key=lambda fixture: str(fixture.get("date") or ""),
    )
    games = []
    expected_wins = 0.0
    for fixture in remaining:
        chance = win_chance(store, str(club.get("name") or ""), str(fixture.get("opponent") or ""))
        expected_wins += chance["win_chance"] / 100
        games.append({"date": str(fixture.get("date") or ""), "opponent": str(fixture.get("opponent") or ""), "win_chance": chance["win_chance"]})

    projected_played = row["played"] + len(remaining)
    projected_won = row["won"] + expected_wins
    projected_rate = projected_won / projected_played if projected_played else 0.0
    others = [item for item in table if item["club_id"] != row["club_id"] and item["played"]]
    projected_rank = 1 + sum(1 for item in others if item["win_rate"] > projected_rate)

    members = _club_members(store, club)
    players = [player_insights(store, member) for member in members]
    batters = sorted(
        [info for info in players if info["career"]["innings"]],
        key=lambda info: -(info["career"]["runs"] + len(remaining) * info["prediction"]["expected_runs"]),
    )[:5]
    return {
        "club": {"id": row["club_id"], "name": row["club_name"]},
        "so_far": {"played": row["played"], "won": row["won"], "lost": row["lost"]},
        "remaining_games": len(remaining),
        "fixtures": games[:10],
        "projected": {
            "wins": round(projected_won, 1),
            "played": projected_played,
            "win_rate": round(projected_rate * 100),
            "rank": projected_rank if projected_played else None,
            "clubs": len(table),
        },
        "top_batters": [
            {
                "name": info["player"]["full_name"],
                "runs_so_far": info["career"]["runs"],
                "projected_season_runs": info["career"]["runs"] + len(remaining) * info["prediction"]["expected_runs"],
            }
            for info in batters
        ],
    }


# ---------------------------------------------------------------------------
# Chat answers for XI / outlook
# ---------------------------------------------------------------------------
_XI_WORDS = ("playing xi", "playing 11", "playing eleven", "best xi", "best 11", "best eleven", "best team", "team selection", "select the team", "pick the team", "who should play", "which players should play", "lineup", "line up", "line-up", "batting order", "squad for")
_OUTLOOK_WORDS = ("season outlook", "rest of the season", "end of the season", "end of season", "this season", "season projection", "how many wins", "how many games will", "finish the season", "where will", "final ranking", "final position")


def _xi_answer(result: dict[str, Any]) -> str:
    fixture = result.get("fixture")
    head = (
        f"Suggested XI for {result['club']['name']} vs {fixture['opponent']} on {fixture['date']}:"
        if fixture
        else f"There's no upcoming fixture on record for {result['club']['name']}, so this is the strongest XI on current stats:"
    )
    lines = [head, _bullets([f"{p['order']}. {p['name']} ({p['role']}): {p['reason']}" + ("" if p["status"] == "available" else f" [{p['status']}]") for p in result["xi"]])]
    if result["left_out"]:
        lines.append("Next in line: " + ", ".join(result["left_out"]) + ".")
    if result["notes"]:
        lines.append(_bullets(result["notes"]))
    lines.append("Picked from projected runs, wickets per match, keeping, catches and current form. The captain should still make the final call.")
    return "\n\n".join(lines)


def _outlook_answer(result: dict[str, Any]) -> str:
    club = result["club"]["name"]
    so_far = result["so_far"]
    projected = result["projected"]
    if not result["remaining_games"]:
        text = f"{club} has no remaining fixtures on record"
        text += f" (record so far: won {so_far['won']} of {so_far['played']})." if so_far["played"] else "."
        return text + " Add the rest of the season's fixtures to get a season outlook."
    lines = [
        f"{club} season outlook: {so_far['won']} wins from {so_far['played']} so far, {_n(result['remaining_games'], 'game')} left.",
        f"Projected finish: about {projected['wins']} wins from {projected['played']} ({projected['win_rate']}%)"
        + (f", around position {projected['rank']} of {projected['clubs']} clubs." if projected["rank"] else "."),
    ]
    if result["fixtures"]:
        lines.append("Win chance by game:\n" + _bullets([f"{g['date']} vs {g['opponent']}: {g['win_chance']}%" for g in result["fixtures"][:6]]))
    if result["top_batters"]:
        lines.append("Projected top run scorers: " + ", ".join(f"{b['name']} ~{b['projected_season_runs']}" for b in result["top_batters"][:3]) + ".")
    return "\n\n".join(lines)


_base_answer = answer


def answer(question: str, store: dict[str, Any]) -> dict[str, Any] | None:  # noqa: F811 - extends the answer above
    text = f" {str(question or '').lower().strip()} "
    if _has_any(text, _XI_WORDS) or _has_any(text, _OUTLOOK_WORDS):
        full = global_store(store)
        clubs = _matched_clubs(question, full)
        if not clubs:
            focus = store.get("focus_club") or store.get("club") or {}
            if focus.get("id"):
                clubs = [focus]
        if clubs:
            club = find_club(full, str(clubs[0].get("id") or "")) or clubs[0]
            if _has_any(text, _XI_WORDS):
                return {"answer": _xi_answer(best_xi(full, club)), "mode": "insights-best-xi"}
            return {"answer": _outlook_answer(season_outlook(full, club)), "mode": "insights-season-outlook"}
    return _base_answer(question, store)
