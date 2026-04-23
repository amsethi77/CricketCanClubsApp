import os
import re
from typing import Any

import httpx

try:
    from cricket_store import (
        build_availability_board,
        build_batting_rankings,
        build_bowling_rankings,
        build_combined_player_stats,
        build_fielding_rankings,
        build_player_pending_stats,
        build_player_stats,
        build_summary,
        canonical_archive_uploads,
        player_name_variants,
    )
except ModuleNotFoundError:
    from app.cricket_store import (
        build_availability_board,
        build_batting_rankings,
        build_bowling_rankings,
        build_combined_player_stats,
        build_fielding_rankings,
        build_player_pending_stats,
        build_player_stats,
        build_summary,
        canonical_archive_uploads,
        player_name_variants,
    )


PREFERRED_OLLAMA_MODELS = [
    "llama3.2:latest",
    "llama3.1:8b",
    "phi4:latest",
    "mistral:latest",
]

MONTH_NAMES = {
    "january": "01",
    "jan": "01",
    "february": "02",
    "feb": "02",
    "march": "03",
    "mar": "03",
    "april": "04",
    "apr": "04",
    "may": "05",
    "june": "06",
    "jun": "06",
    "july": "07",
    "jul": "07",
    "august": "08",
    "aug": "08",
    "september": "09",
    "sep": "09",
    "sept": "09",
    "october": "10",
    "oct": "10",
    "november": "11",
    "nov": "11",
    "december": "12",
    "dec": "12",
}
MONTH_LABELS = {
    "01": "January",
    "02": "February",
    "03": "March",
    "04": "April",
    "05": "May",
    "06": "June",
    "07": "July",
    "08": "August",
    "09": "September",
    "10": "October",
    "11": "November",
    "12": "December",
}

STOP_WORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "both",
    "by",
    "for",
    "from",
    "has",
    "have",
    "how",
    "in",
    "is",
    "many",
    "of",
    "on",
    "or",
    "played",
    "so",
    "the",
    "to",
    "what",
    "which",
    "who",
}


def _ollama_base_url() -> str:
    return os.environ.get("OLLAMA_BASE_URL", "http://127.0.0.1:11434").rstrip("/")


def get_llm_status() -> dict[str, Any]:
    base_url = _ollama_base_url()
    configured_model = os.environ.get("OLLAMA_MODEL")
    try:
        response = httpx.get(f"{base_url}/api/tags", timeout=2.5)
        response.raise_for_status()
        models = [item.get("name", "").strip() for item in response.json().get("models", []) if item.get("name")]
        selected = configured_model if configured_model in models else None
        if not selected:
            for model in PREFERRED_OLLAMA_MODELS:
                if model in models:
                    selected = model
                    break
        if not selected and models:
            selected = models[0]
        return {
            "provider": "ollama" if selected else "heuristic",
            "available": bool(selected),
            "model": selected,
            "base_url": base_url,
        }
    except Exception:
        return {
            "provider": "heuristic",
            "available": True,
            "model": "built-in data assistant",
            "base_url": None,
        }


def _display_name(member: dict[str, Any]) -> str:
    return str(member.get("full_name") or member.get("name") or "").strip()


def _display_name_for_name(name: str, members: list[dict[str, Any]]) -> str:
    for member in members:
        if member.get("name") == name:
            return _display_name(member)
    return str(name or "").strip()


def _ordinal(value: int) -> str:
    if 10 <= value % 100 <= 20:
        suffix = "th"
    else:
        suffix = {1: "st", 2: "nd", 3: "rd"}.get(value % 10, "th")
    return f"{value}{suffix}"


def _query_terms(question: str) -> set[str]:
    return {
        token
        for token in re.findall(r"[a-z0-9]+", question.lower())
        if token and token not in STOP_WORDS and len(token) > 1
    }


def _history_user_messages(history: list[dict[str, str]] | None) -> list[str]:
    if not history:
        return []
    return [
        str(item.get("text", "") or "").strip()
        for item in history
        if str(item.get("role", "") or "").lower() == "user" and str(item.get("text", "") or "").strip()
    ]


def _question_needs_history(question: str, members: list[dict[str, Any]], store: dict[str, Any]) -> bool:
    q = str(question or "").strip()
    lowered = q.lower()
    if not q:
        return False
    if _matched_members(q, members):
        return False
    if _requested_club_terms(q, store):
        return True
    if len(q) <= 40:
        return True
    return any(
        lowered.startswith(prefix)
        for prefix in ["and ", "what about", "how about", "for ", "in ", "his ", "her ", "their ", "that ", "those "]
    ) or any(token in lowered for token in [" his ", " her ", " their ", " that team", " that club", " those matches"])


def _question_year(question: str) -> str:
    match = re.search(r"\b(20\d{2})\b", str(question or ""))
    return match.group(1) if match else ""


def _question_month(question: str) -> str:
    lowered = str(question or "").lower()
    return next((month_number for month_name, month_number in MONTH_NAMES.items() if month_name in lowered), "")


def _recent_question_context(
    history: list[dict[str, str]] | None,
    members: list[dict[str, Any]],
    store: dict[str, Any],
) -> dict[str, Any]:
    entries = history or []
    texts = [str(item.get("text", "") or "").strip() for item in entries if str(item.get("text", "") or "").strip()]
    for message in reversed(texts):
        matched = _matched_members(message, members)
        requested_clubs = _requested_club_terms(message, store)
        year = _question_year(message)
        month = _question_month(message)
        if matched or requested_clubs or year or month:
            return {
                "members": matched,
                "clubs": requested_clubs,
                "year": year,
                "month": month,
            }
    return {"members": [], "clubs": [], "year": "", "month": ""}


def _contextualize_question(
    question: str,
    history: list[dict[str, str]] | None,
    members: list[dict[str, Any]],
    store: dict[str, Any],
) -> str:
    user_messages = _history_user_messages(history)
    if not user_messages or not _question_needs_history(question, members, store):
        return question
    context = _recent_question_context(history, members, store)
    lowered = str(question or "").lower().strip()
    current_members = _matched_members(question, members)
    current_year = _question_year(question)
    current_month = _question_month(question)

    additions: list[str] = []
    if not current_members and context["members"]:
        member_phrase = " and ".join(member["name"] for member in context["members"][:3] if member.get("name"))
        if member_phrase:
            additions.append(f"for {member_phrase}")
    if not current_year and context["year"] and ("month" in lowered or current_month or lowered.startswith("and ") or " so far" in lowered):
        additions.append(f"in {context['year']}")
    if not additions:
        return question
    contextualized = f"{question.strip()} {' '.join(additions)}".strip()
    return contextualized or question


def _matched_members(question: str, members: list[dict[str, Any]]) -> list[dict[str, Any]]:
    q = question.lower().strip()
    candidates: list[tuple[int, int, int, dict[str, Any]]] = []
    for member in members:
        for variant in sorted(player_name_variants(member), key=len, reverse=True):
            if not variant:
                continue
            pattern = re.compile(rf"(?<!\w){re.escape(variant)}(?!\w)")
            for match in pattern.finditer(q):
                candidates.append((match.start(), -(match.end() - match.start()), match.end(), member))

    candidates.sort()
    selected: list[dict[str, Any]] = []
    occupied: list[tuple[int, int]] = []
    seen_names: set[str] = set()
    for start, negative_length, end, member in candidates:
        if any(not (end <= occ_start or start >= occ_end) for occ_start, occ_end in occupied):
            continue
        if member["name"] in seen_names:
            continue
        occupied.append((start, end))
        seen_names.add(member["name"])
        selected.append(member)
    return selected


def _date_matches(date_value: str, query_year: str = "", query_month: str = "") -> bool:
    text = str(date_value or "")
    if not text:
        return False
    if query_year and not text.startswith(query_year):
        return False
    if query_month and len(text) >= 7 and text[5:7] != query_month:
        return False
    return True


def _member_club_terms(member: dict[str, Any]) -> set[str]:
    terms: set[str] = set()
    for club in member.get("club_memberships", []) or []:
        club_name = str(club.get("club_name", "") or "").strip()
        if club_name:
            terms.add(club_name.lower())
    for team in member.get("team_memberships", []) or []:
        if isinstance(team, dict):
            team_name = str(team.get("team_name") or team.get("display_name") or "").strip()
        else:
            team_name = str(team or "").strip()
        if team_name:
            terms.add(team_name.lower())
    primary_team = str(member.get("team_name", "") or "").strip()
    if primary_team:
        terms.add(primary_team.lower())
    return terms


def _requested_club_terms(question: str, store: dict[str, Any]) -> list[str]:
    q = question.lower().strip()
    matches: list[tuple[int, str]] = []
    seen: set[str] = set()

    def consider(raw_value: str) -> None:
        value = str(raw_value or "").strip()
        if not value:
            return
        lowered = value.lower()
        if lowered in seen:
            return
        pattern = re.compile(rf"(?<!\w){re.escape(lowered)}(?!\w)")
        found = pattern.search(q)
        if found:
            seen.add(lowered)
            matches.append((found.start(), lowered))

    for club in store.get("clubs", []) or []:
        consider(club.get("name", ""))
        consider(club.get("short_name", ""))
    for team in store.get("teams", []) or []:
        consider(team.get("name", ""))
        consider(team.get("display_name", ""))

    matches.sort()
    return [value for _, value in matches]


def _archive_team_pair(upload: dict[str, Any]) -> tuple[str, str]:
    live_summary = str(upload.get("draft_scorecard", {}).get("live_summary", "") or "")
    batting_match = re.search(r"Batting team:\s*([^|]+)", live_summary, flags=re.IGNORECASE)
    bowling_match = re.search(r"Bowling team:\s*([^|]+)", live_summary, flags=re.IGNORECASE)
    batting_team = batting_match.group(1).strip() if batting_match else ""
    bowling_team = bowling_match.group(1).strip() if bowling_match else ""
    return batting_team, bowling_team


def _batting_status_from_notes(notes: str) -> dict[str, bool]:
    lowered = str(notes or "").lower()
    did_not_bat = any(tag in lowered for tag in ["did_not_bat", "did not bat", "dnb"])
    not_out = any(tag in lowered for tag in ["not_out", "not out"])
    out = (
        not did_not_bat
        and not not_out
        and (
            "unknown" in lowered
            or any(
            tag in lowered
            for tag in [
                "bowled",
                "caught",
                "lbw",
                "stumped",
                "run_out",
                "run out",
                "hit wicket",
                "retired_out",
                "retired out",
            ]
            )
        )
    )
    known = did_not_bat or not_out or out
    return {"did_not_bat": did_not_bat, "not_out": not_out, "out": out, "known": known}


def _apply_batting_entry_totals(bucket: dict[str, Any], performance: dict[str, Any]) -> None:
    notes = str(performance.get("notes", "") or "")
    status = _batting_status_from_notes(notes)
    runs = int(performance.get("runs", 0) or 0)
    balls = int(performance.get("balls", 0) or 0)
    fours = int(performance.get("fours", 0) or 0)
    sixes = int(performance.get("sixes", 0) or 0)
    batted = not status["did_not_bat"] and (
        runs > 0 or balls > 0 or fours > 0 or sixes > 0 or status["known"]
    )
    if not batted:
        return
    bucket["batting_innings"] += 1
    if status["known"]:
        bucket["dismissal_known_innings"] += 1
    if status["out"]:
        bucket["outs"] += 1


def _player_participation_entries(store: dict[str, Any], member: dict[str, Any]) -> list[dict[str, Any]]:
    player_name = member["name"]
    entries: list[dict[str, Any]] = []
    team_terms = _member_club_terms(member)
    player_variants = {variant.lower() for variant in player_name_variants(member)}
    default_team = str(member.get("team_name", "") or "").strip()
    default_club = str((member.get("club_memberships") or [{}])[0].get("club_name", "") or "").strip()

    for match in store.get("fixtures", []):
        relevant = [item for item in match.get("performances", []) if item.get("player_name") == player_name]
        if not relevant:
            continue
        totals = {
            "runs": sum(int(item.get("runs", 0) or 0) for item in relevant),
            "balls": sum(int(item.get("balls", 0) or 0) for item in relevant),
            "wickets": sum(int(item.get("wickets", 0) or 0) for item in relevant),
            "catches": sum(int(item.get("catches", 0) or 0) for item in relevant),
            "batting_innings": 0,
            "dismissal_known_innings": 0,
            "outs": 0,
        }
        for item in relevant:
            _apply_batting_entry_totals(totals, item)
        entries.append(
            {
                "key": f"fixture:{match.get('id', '')}",
                "date": str(match.get("date", "") or ""),
                "month": str(match.get("date", "") or "")[:7],
                "team": "heartlake",
                "team_label": "Heartlake",
                "club": "heartlake cricket club",
                "club_label": "Heartlake Cricket Club",
                "opponent": str(match.get("opponent", "") or ""),
                **totals,
            }
        )

    for upload in canonical_archive_uploads(store.get("archive_uploads", [])):
        batting_team, bowling_team = _archive_team_pair(upload)
        archive_date = str(upload.get("archive_date", "") or "")
        archive_key = f"archive:{upload.get('id', '')}"
        totals = {"runs": 0, "balls": 0, "wickets": 0, "catches": 0}
        totals.update({"batting_innings": 0, "dismissal_known_innings": 0, "outs": 0})
        represented_team = ""
        represented_club = ""

        for performance in upload.get("suggested_performances", []):
            notes = str(performance.get("notes", "") or "")
            lowered_notes = notes.lower()
            if performance.get("player_name") == player_name:
                totals["runs"] += int(performance.get("runs", 0) or 0)
                totals["balls"] += int(performance.get("balls", 0) or 0)
                totals["wickets"] += int(performance.get("wickets", 0) or 0)
                totals["catches"] += int(performance.get("catches", 0) or 0)
                _apply_batting_entry_totals(totals, performance)
                if batting_team:
                    represented_team = batting_team
                    represented_club = batting_team

            fielder_match = re.search(r"fielder:\s*([^|]+)", notes, flags=re.IGNORECASE)
            if fielder_match and fielder_match.group(1).strip().lower() in player_variants:
                totals["catches"] += 1
                if bowling_team:
                    represented_team = bowling_team
                    represented_club = bowling_team

            bowler_match = re.search(r"bowler:\s*([^|]+)", notes, flags=re.IGNORECASE)
            if (
                bowler_match
                and bowler_match.group(1).strip().lower() in player_variants
                and not any(tag in lowered_notes for tag in ["run_out", "run out", "not_out", "not out", "retired"])
            ):
                totals["wickets"] += 1
                if bowling_team:
                    represented_team = bowling_team
                    represented_club = bowling_team

        if not any(totals.values()):
            continue

        normalized_team = represented_team.lower().strip()
        normalized_club = represented_club.lower().strip()
        if not normalized_team and default_team:
            normalized_team = default_team.lower()
        if not normalized_club and default_club:
            normalized_club = default_club.lower()
        if normalized_team and normalized_team not in team_terms and normalized_club not in team_terms:
            if default_team:
                normalized_team = default_team.lower()
            if default_club:
                normalized_club = default_club.lower()

        entries.append(
            {
                "key": archive_key,
                "date": archive_date,
                "month": archive_date[:7],
                "team": normalized_team,
                "team_label": represented_team or default_team,
                "club": normalized_club,
                "club_label": represented_club or default_club,
                "opponent": _archive_opponent_name(upload),
                **totals,
            }
        )

    deduped: dict[str, dict[str, Any]] = {}
    for entry in entries:
        deduped[entry["key"]] = entry
    return sorted(deduped.values(), key=lambda item: (item.get("date", ""), item.get("key", "")))


def _filter_entries_for_requested_clubs(entries: list[dict[str, Any]], requested_clubs: list[str]) -> list[dict[str, Any]]:
    if not requested_clubs:
        return list(entries)
    filtered = []
    for entry in entries:
        haystack = {
            str(entry.get("team", "") or "").lower(),
            str(entry.get("team_label", "") or "").lower(),
            str(entry.get("club", "") or "").lower(),
            str(entry.get("club_label", "") or "").lower(),
        }
        if any(term in haystack for term in requested_clubs):
            filtered.append(entry)
    return filtered


def _aggregate_entries(entries: list[dict[str, Any]]) -> dict[str, Any]:
    batting_innings = sum(int(item.get("batting_innings", 0) or 0) for item in entries)
    dismissal_known_innings = sum(int(item.get("dismissal_known_innings", 0) or 0) for item in entries)
    outs = sum(int(item.get("outs", 0) or 0) for item in entries)
    runs = sum(int(item.get("runs", 0) or 0) for item in entries)
    if batting_innings and dismissal_known_innings == batting_innings and outs > 0:
        average_denominator = outs
    elif batting_innings:
        average_denominator = batting_innings
    else:
        average_denominator = 0
    return {
        "matches": len(entries),
        "runs": runs,
        "balls": sum(int(item.get("balls", 0) or 0) for item in entries),
        "wickets": sum(int(item.get("wickets", 0) or 0) for item in entries),
        "catches": sum(int(item.get("catches", 0) or 0) for item in entries),
        "batting_innings": batting_innings,
        "dismissal_known_innings": dismissal_known_innings,
        "outs": outs,
        "batting_average": round((runs / average_denominator), 2) if average_denominator else 0.0,
    }


def _requested_club_label(requested_clubs: list[str], store: dict[str, Any]) -> str:
    if not requested_clubs:
        return ""
    target = requested_clubs[0]
    for club in store.get("clubs", []) or []:
        for value in [club.get("name", ""), club.get("short_name", "")]:
            if str(value or "").strip().lower() == target:
                return str(value).strip()
    for team in store.get("teams", []) or []:
        for value in [team.get("name", ""), team.get("display_name", "")]:
            if str(value or "").strip().lower() == target:
                return str(value).strip()
    return requested_clubs[0]


def _combined_player_records(
    members: list[dict[str, Any]],
    player_stats: list[dict[str, Any]],
    pending_player_stats: list[dict[str, Any]],
    availability_board: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    stats_by_player = {item["player_name"]: item for item in player_stats}
    pending_by_player = {item["player_name"]: item for item in pending_player_stats}
    availability_by_player = {item["player_name"]: item for item in availability_board}
    records = []
    for member in members:
        stats = stats_by_player.get(
            member["name"],
            {"runs": 0, "wickets": 0, "catches": 0, "matches": 0, "batting_average": 0.0, "strike_rate": 0.0},
        )
        pending = pending_by_player.get(
            member["name"],
            {"runs": 0, "wickets": 0, "catches": 0, "matches": 0},
        )
        availability = availability_by_player.get(
            member["name"],
            {"matches_available": 0, "matches_maybe": 0, "matches_unavailable": 0, "matches_no_response": 0},
        )
        combined_matches = int(stats.get("matches", 0) or 0) + int(pending.get("matches", 0) or 0)
        combined_runs = int(stats.get("runs", 0) or 0) + int(pending.get("runs", 0) or 0)
        combined_balls = int(stats.get("balls", 0) or 0) + int(pending.get("balls", 0) or 0)
        combined_wickets = int(stats.get("wickets", 0) or 0) + int(pending.get("wickets", 0) or 0)
        combined_catches = int(stats.get("catches", 0) or 0) + int(pending.get("catches", 0) or 0)
        batting_innings = int(stats.get("batting_innings", 0) or 0) + int(pending.get("batting_innings", 0) or 0)
        dismissal_known_innings = int(stats.get("dismissal_known_innings", 0) or 0) + int(pending.get("dismissal_known_innings", 0) or 0)
        outs = int(stats.get("outs", 0) or 0) + int(pending.get("outs", 0) or 0)
        if batting_innings and dismissal_known_innings == batting_innings and outs > 0:
            average_denominator = outs
        elif batting_innings:
            average_denominator = batting_innings
        else:
            average_denominator = 0
        records.append(
            {
                "player_name": member["name"],
                "display_name": _display_name(member),
                "runs": combined_runs,
                "balls": combined_balls,
                "wickets": combined_wickets,
                "catches": combined_catches,
                "matches": combined_matches,
                "batting_innings": batting_innings,
                "dismissal_known_innings": dismissal_known_innings,
                "outs": outs,
                "live_matches": int(stats.get("matches", 0) or 0),
                "historical_matches": int(pending.get("matches", 0) or 0),
                "batting_average": round((combined_runs / average_denominator), 2) if average_denominator else 0.0,
                "strike_rate": round((combined_runs / combined_balls) * 100, 2) if combined_balls else 0.0,
                "matches_available": int(availability.get("matches_available", 0) or 0),
                "matches_maybe": int(availability.get("matches_maybe", 0) or 0),
                "matches_unavailable": int(availability.get("matches_unavailable", 0) or 0),
                "matches_no_response": int(availability.get("matches_no_response", 0) or 0),
            }
        )
    return records


def _historical_batting_positions(store: dict[str, Any], player_name: str) -> list[dict[str, Any]]:
    positions: list[dict[str, Any]] = []
    for archive in store.get("archive_uploads", []):
        for index, row in enumerate(archive.get("suggested_performances", []), start=1):
            if row.get("player_name") != player_name:
                continue
            positions.append(
                {
                    "position": index,
                    "runs": int(row.get("runs", 0) or 0),
                    "file_name": archive.get("file_name", ""),
                    "archive_date": archive.get("archive_date", ""),
                }
            )
    positions.sort(key=lambda item: (item["archive_date"] or "9999-99-99", item["file_name"], item["position"]))
    return positions


def _best_batting_position(store: dict[str, Any], player_name: str) -> dict[str, Any] | None:
    positions = _historical_batting_positions(store, player_name)
    if not positions:
        return None

    summary_by_position: dict[int, dict[str, Any]] = {}
    for item in positions:
        position = item["position"]
        bucket = summary_by_position.setdefault(position, {"position": position, "innings": 0, "runs": 0})
        bucket["innings"] += 1
        bucket["runs"] += item["runs"]

    ranked = []
    for bucket in summary_by_position.values():
        innings = bucket["innings"] or 1
        ranked.append(
            {
                "position": bucket["position"],
                "innings": bucket["innings"],
                "runs": bucket["runs"],
                "average_runs": bucket["runs"] / innings,
            }
        )

    ranked.sort(key=lambda item: (-item["average_runs"], -item["runs"], -item["innings"], item["position"]))
    return ranked[0]


def _archive_opponent_name(upload: dict[str, Any]) -> str:
    live_summary = str(upload.get("draft_scorecard", {}).get("live_summary", "") or "")
    batting_match = re.search(r"Batting team:\s*([^|]+)", live_summary, flags=re.IGNORECASE)
    bowling_match = re.search(r"Bowling team:\s*([^|]+)", live_summary, flags=re.IGNORECASE)
    batting_team = batting_match.group(1).strip() if batting_match else ""
    bowling_team = bowling_match.group(1).strip() if bowling_match else ""
    if batting_team.lower().startswith("heartlake") and bowling_team:
        return bowling_team
    if bowling_team.lower().startswith("heartlake") and batting_team:
        return batting_team
    return bowling_team or batting_team


def _best_score_opponent(store: dict[str, Any], player_name: str) -> dict[str, Any] | None:
    best: dict[str, Any] | None = None

    for upload in store.get("archive_uploads", []):
        opponent = _archive_opponent_name(upload)
        archive_date = str(upload.get("archive_date", "") or "")
        for row in upload.get("suggested_performances", []):
            if row.get("player_name") != player_name:
                continue
            candidate = {
                "runs": int(row.get("runs", 0) or 0),
                "balls": int(row.get("balls", 0) or 0),
                "opponent": opponent,
                "date": archive_date,
                "source": upload.get("file_name", ""),
            }
            if (
                best is None
                or candidate["runs"] > best["runs"]
                or (candidate["runs"] == best["runs"] and candidate["balls"] > best["balls"])
                or (candidate["runs"] == best["runs"] and candidate["date"] < best["date"])
            ):
                best = candidate

    for match in store.get("fixtures", []):
        opponent = str(match.get("opponent", "") or "")
        match_date = str(match.get("date", "") or "")
        for row in match.get("performances", []):
            if row.get("player_name") != player_name:
                continue
            candidate = {
                "runs": int(row.get("runs", 0) or 0),
                "balls": int(row.get("balls", 0) or 0),
                "opponent": opponent,
                "date": match_date,
                "source": match.get("id", ""),
            }
            if (
                best is None
                or candidate["runs"] > best["runs"]
                or (candidate["runs"] == best["runs"] and candidate["balls"] > best["balls"])
                or (candidate["runs"] == best["runs"] and candidate["date"] < best["date"])
            ):
                best = candidate

    return best


def _best_score_details(store: dict[str, Any], player_name: str) -> dict[str, Any] | None:
    return _best_score_opponent(store, player_name)


def _player_context_snippets(
    store: dict[str, Any],
    members: list[dict[str, Any]],
    fixtures: list[dict[str, Any]],
    player_stats: list[dict[str, Any]],
    pending_player_stats: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    stats_by_player = {item["player_name"]: item for item in player_stats}
    pending_by_player = {item["player_name"]: item for item in pending_player_stats}
    archives_by_id = {item.get("id"): item for item in store.get("archive_uploads", [])}
    snippets: list[dict[str, Any]] = []

    for member in members:
        stats = stats_by_player.get(member["name"], {"matches": 0, "runs": 0, "wickets": 0, "catches": 0})
        pending = pending_by_player.get(member["name"], {"matches": 0, "runs": 0, "sources": []})
        participation_entries = _player_participation_entries(store, member)
        combined_batting_innings = int(stats.get("batting_innings", 0) or 0) + int(pending.get("batting_innings", 0) or 0)
        combined_dismissal_known_innings = int(stats.get("dismissal_known_innings", 0) or 0) + int(pending.get("dismissal_known_innings", 0) or 0)
        combined_outs = int(stats.get("outs", 0) or 0) + int(pending.get("outs", 0) or 0)
        combined_runs = int(stats.get("runs", 0) or 0) + int(pending.get("runs", 0) or 0)
        if combined_batting_innings and combined_dismissal_known_innings == combined_batting_innings and combined_outs > 0:
            average_denominator = combined_outs
        elif combined_batting_innings:
            average_denominator = combined_batting_innings
        else:
            average_denominator = 0
        combined_batting_average = round((combined_runs / average_denominator), 2) if average_denominator else 0.0
        year_counts: dict[str, int] = {}
        month_counts: dict[str, int] = {}
        for entry in participation_entries:
            year_key = str(entry.get("date", ""))[:4]
            month_key = str(entry.get("date", ""))[:7]
            if year_key:
                year_counts[year_key] = year_counts.get(year_key, 0) + 1
            if month_key:
                month_counts[month_key] = month_counts.get(month_key, 0) + 1

        archive_source_bits = []
        for source in pending.get("sources", []):
            archive = archives_by_id.get(source.get("archive_id"))
            archive_date = archive.get("archive_date", "") if archive else ""
            archive_source_bits.append(
                f"{source.get('file_name', '')}@{archive_date or 'unknown-date'} runs={source.get('runs', 0)}"
            )

        snippet_text = "\n".join(
            [
                f"[player] {_display_name(member)}",
                f"aliases: {', '.join(member.get('aliases', [])) or 'none'}",
                f"team: {member.get('team_name', 'Heartlake')}",
                f"teams: {', '.join(team.get('team_name') if isinstance(team, dict) else str(team) for team in (member.get('team_memberships') or [])) or member.get('team_name', 'Heartlake')}",
                f"clubs: {', '.join(club.get('club_name') for club in (member.get('club_memberships') or []) if club.get('club_name')) or store['club'].get('name', 'Heartlake Cricket Club')}",
                f"age: {member.get('age') or 'unknown'}",
                f"role: {member.get('role') or 'unknown'}",
                f"phone: {member.get('phone') or 'unknown'}",
                f"batting_style: {member.get('batting_style') or 'unknown'}",
                f"bowling_style: {member.get('bowling_style') or 'unknown'}",
                f"notes: {member.get('notes') or 'none'}",
                f"live_matches: {stats.get('matches', 0)}",
                f"historical_archive_matches: {pending.get('matches', 0)}",
                f"confirmed_matches_so_far: {len(participation_entries)}",
                f"live_runs: {stats.get('runs', 0)}",
                f"historical_archive_runs: {pending.get('runs', 0)}",
                f"confirmed_runs_so_far: {stats.get('runs', 0) + pending.get('runs', 0)}",
                f"live_balls: {stats.get('balls', 0)}",
                f"historical_archive_balls: {pending.get('balls', 0)}",
                f"confirmed_balls_so_far: {stats.get('balls', 0) + pending.get('balls', 0)}",
                f"confirmed_batting_average_so_far: {combined_batting_average}",
                (
                    f"confirmed_strike_rate_so_far: "
                    f"{round((((stats.get('runs', 0) + pending.get('runs', 0)) / (stats.get('balls', 0) + pending.get('balls', 0))) * 100), 2) if (stats.get('balls', 0) + pending.get('balls', 0)) else 0.0}"
                ),
                f"year_match_counts: {', '.join(f'{key}={value}' for key, value in sorted(year_counts.items())) or 'none'}",
                f"month_match_counts: {', '.join(f'{key}={value}' for key, value in sorted(month_counts.items())) or 'none'}",
                f"historical_scorecards: {'; '.join(archive_source_bits) or 'none'}",
            ]
        )
        snippets.append({"kind": "player", "key": member["name"], "text": snippet_text})
    return snippets


def _fixture_context_snippets(fixtures: list[dict[str, Any]]) -> list[dict[str, Any]]:
    snippets: list[dict[str, Any]] = []
    for match in fixtures:
        snippet_text = "\n".join(
            [
                f"[fixture] {match.get('date_label')} | date={match.get('date')} | opponent={match.get('opponent')}",
                f"status: {match.get('status')}",
                f"captain: {match.get('heartlake_captain') or 'unassigned'}",
                f"availability: {', '.join(match.get('availability', [])) or 'none'}",
                (
                    f"scorecard: Heartlake {match.get('scorecard', {}).get('heartlake_runs') or '--'}/"
                    f"{match.get('scorecard', {}).get('heartlake_wickets') or '--'} "
                    f"Opponent {match.get('scorecard', {}).get('opponent_runs') or '--'}/"
                    f"{match.get('scorecard', {}).get('opponent_wickets') or '--'}"
                ),
                f"result: {match.get('scorecard', {}).get('result') or match.get('result') or 'TBD'}",
            ]
        )
        snippets.append({"kind": "fixture", "key": match.get("id", ""), "text": snippet_text})
    return snippets


def _archive_context_snippets(archives: list[dict[str, Any]]) -> list[dict[str, Any]]:
    snippets: list[dict[str, Any]] = []
    for archive in archives:
        player_bits = [
            f"{item.get('player_name')} {item.get('runs', 0)}"
            for item in archive.get("suggested_performances", [])[:18]
            if item.get("player_name")
        ]
        snippet_text = "\n".join(
            [
                f"[archive] {archive.get('file_name')} | archive_date={archive.get('archive_date') or 'unknown'} | year={archive.get('archive_year') or 'unknown'}",
                f"status: {archive.get('status')}",
                f"season: {archive.get('season')}",
                f"summary: {archive.get('extracted_summary')}",
                (
                    f"scorecard: Heartlake {archive.get('draft_scorecard', {}).get('heartlake_runs') or '--'}/"
                    f"{archive.get('draft_scorecard', {}).get('heartlake_wickets') or '--'} "
                    f"Opponent {archive.get('draft_scorecard', {}).get('opponent_runs') or '--'}/"
                    f"{archive.get('draft_scorecard', {}).get('opponent_wickets') or '--'}"
                ),
                f"players: {'; '.join(player_bits) or 'none'}",
            ]
        )
        snippets.append({"kind": "archive", "key": archive.get("id", ""), "text": snippet_text})
    return snippets


def _club_context_snippet(store: dict[str, Any], summary: dict[str, Any]) -> dict[str, Any]:
    fixtures = store.get("fixtures", [])
    next_match = next((match for match in fixtures if match["status"] != "Completed"), fixtures[0] if fixtures else {})
    text = "\n".join(
        [
            f"[club] {store['club'].get('name', 'Heartlake Cricket Club')}",
            f"live_season: {store['club'].get('season')}",
            f"fixture_count: {summary.get('fixture_count', 0)}",
            f"member_count: {summary.get('member_count', 0)}",
            f"archive_count: {summary.get('archive_count', 0)}",
            f"next_match: {next_match.get('date_label', 'None')} vs {next_match.get('opponent', 'No scheduled opponent')}",
        ]
    )
    return {"kind": "club", "key": "club", "text": text}


def _rank_context_snippets(question: str, snippets: list[dict[str, Any]], matched_members: list[dict[str, Any]]) -> list[dict[str, Any]]:
    query_terms = _query_terms(question)
    matched_names = {member["name"].lower() for member in matched_members}
    matched_full_names = {str(member.get("full_name", "")).lower() for member in matched_members if member.get("full_name")}

    ranked = []
    for snippet in snippets:
        text = snippet["text"].lower()
        score = sum(3 for term in query_terms if term in text)
        if snippet["kind"] == "player" and any(name in text for name in matched_names | matched_full_names):
            score += 50
        if snippet["kind"] == "archive" and ("archive" in query_terms or "scorecard" in query_terms):
            score += 8
        if snippet["kind"] == "fixture" and any(term in query_terms for term in {"availability", "next", "match", "fixture", "captain"}):
            score += 6
        if snippet["kind"] == "club":
            score += 2
        ranked.append((score, snippet))

    ranked.sort(key=lambda item: item[0], reverse=True)
    selected: list[dict[str, Any]] = []
    total_chars = 0
    for score, snippet in ranked:
        if score <= 0 and selected:
            continue
        text = snippet["text"]
        if total_chars + len(text) > 12000 and selected:
            continue
        selected.append(snippet)
        total_chars += len(text)
        if len(selected) >= 12:
            break
    return selected or [snippet for _, snippet in ranked[:8]]


def _rag_answer_is_safe(
    answer: str,
    members: list[dict[str, Any]],
    matched_members: list[dict[str, Any]],
    grounded_facts: str,
) -> bool:
    text = str(answer or "").strip().lower()
    grounded_text = str(grounded_facts or "").strip().lower()
    if not text:
        return False
    if "best score was against" in grounded_text:
        if any(char.isdigit() for char in text):
            return False
        if "best score was against" not in text:
            return False
    if grounded_facts and len(matched_members) == 1:
        allowed_member = matched_members[0]
        allowed_terms = {
            _display_name(allowed_member).lower(),
            str(allowed_member.get("name", "")).lower(),
            str(allowed_member.get("full_name", "")).lower(),
        }
        for member in members:
            if member.get("name") == allowed_member.get("name"):
                continue
            candidate_terms = {
                _display_name(member).lower(),
                str(member.get("name", "")).lower(),
                str(member.get("full_name", "")).lower(),
            }
            for term in candidate_terms:
                if term and term not in allowed_terms and term in text:
                    return False
    return True


def _rag_answer(question: str, store: dict[str, Any], grounded_facts: str = "", history: list[dict[str, str]] | None = None) -> str | None:
    llm_status = get_llm_status()
    if not llm_status.get("available") or llm_status.get("provider") != "ollama" or not llm_status.get("model"):
        return None

    effective_question = _contextualize_question(question, history, store["members"], store)
    q = effective_question.lower().strip()
    fixtures = store["fixtures"]
    members = store["members"]
    summary = build_summary(store)
    player_stats = build_player_stats(fixtures, members)
    pending_player_stats = build_player_pending_stats(store.get("archive_uploads", []), members)
    matched_members = _matched_members(effective_question, members)

    snippets = [_club_context_snippet(store, summary)]
    snippets.extend(_player_context_snippets(store, members, fixtures, player_stats, pending_player_stats))
    snippets.extend(_fixture_context_snippets(fixtures))
    snippets.extend(_archive_context_snippets(store.get("archive_uploads", [])))
    selected_snippets = _rank_context_snippets(question, snippets, matched_members)
    context = "\n\n".join(snippet["text"] for snippet in selected_snippets)
    grounded_block = grounded_facts.strip()

    system_prompt = (
        "You answer questions about persisted Heartlake cricket data using only the supplied context.\n"
        "Rules:\n"
        "- Do not guess or invent facts.\n"
        "- If the answer is not supported by context, say you could not find it in the stored data.\n"
        "- Historical archive scorecards count as confirmed historical match history.\n"
        "- The live 2026 fixture season is separate from the 2025 historical archive season.\n"
        "- Player identity comes from the persisted member name, full name, and saved aliases in the supplied context.\n"
        "- Unless the question explicitly names a club or team, player totals and match counts should include all stored clubs and teams.\n"
        "- In answers, refer to players by full name whenever a full name is available.\n"
        "- When authoritative grounded facts are provided, treat them as the primary answer source and do not contradict them.\n"
        "- If grounded facts already answer the question, restate only those facts and do not add extra players, comparisons, or side calculations.\n"
        "- If a question asks about a year or month, filter strictly by the provided date fields.\n"
        "- For multiple players, answer all of them.\n"
        "- Keep the answer concise and directly responsive."
    )

    try:
        response = httpx.post(
            f"{_ollama_base_url()}/api/chat",
            json={
                "model": llm_status["model"],
                "stream": False,
                "options": {"temperature": 0},
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {
                        "role": "user",
                        "content": (
                            f"Question: {effective_question}\n\n"
                            + (f"Grounded facts from live persisted data:\n{grounded_block}\n\n" if grounded_block else "")
                            + f"Context:\n{context}"
                        ),
                    },
                ],
            },
            timeout=45.0,
        )
        response.raise_for_status()
        answer = response.json().get("message", {}).get("content", "").strip()
        if not _rag_answer_is_safe(answer, members, matched_members, grounded_facts):
            return None
        return answer or None
    except Exception:
        return None


def _prefer_heuristic_answer(question: str) -> bool:
    q = question.lower().strip()
    exact_patterns = [
        "how many matches",
        "matches played",
        "match played",
        "played how many",
        "appearances",
        "which months",
        "what months",
        "in which month",
        "in which months",
        "full name",
        "real name",
        "alias",
        "aliases",
        "age",
        "how old",
        "phone",
        "mobile",
        "number",
        "lives",
        "live in",
        "address",
        "batting order",
        "best batting order",
        "batting position",
        "best position",
        "most reliable",
        "reliable player",
        "top ranked",
        "rank in the team",
        "rank in team",
        "ranking in the team",
        "ranking in team",
        "what rank",
        "top 5",
        "most games",
        "most wicket",
        "is this rag",
        "from llm",
        "what model",
        "which llm",
        "how many runs",
        "total runs",
        "batting average",
        "average",
        "strike rate",
        "economy",
        "bowling economy",
        "which team was it against",
        "what team was it against",
        "best score",
        "highest score",
        "best score against",
        "highest score against",
        "against which team",
        "how many wickets",
        "how many catches",
        "most catches",
        "number of catches",
        "taken most",
        "rarely available",
        "consistent",
        "batters",
        "batter",
        "next match",
        "who is available",
        "availability",
    ]
    return any(pattern in q for pattern in exact_patterns)


def _heuristic_answer(question: str, store: dict[str, Any], history: list[dict[str, str]] | None = None) -> dict[str, Any]:
    effective_question = _contextualize_question(question, history, store["members"], store)
    q = effective_question.lower().strip()
    summary = build_summary(store)
    fixtures = store["fixtures"]
    members = store["members"]
    availability_board = build_availability_board(members, fixtures)
    player_stats = build_player_stats(fixtures, members)
    pending_player_stats = build_player_pending_stats(store.get("archive_uploads", []), members)
    combined_records = _combined_player_records(members, player_stats, pending_player_stats, availability_board)
    next_match = next((match for match in fixtures if match["status"] != "Completed"), fixtures[0] if fixtures else {})
    matched_members = _matched_members(effective_question, members)
    matched_member = matched_members[0] if matched_members else None
    requested_clubs = _requested_club_terms(effective_question, store)
    requested_club_label = _requested_club_label(requested_clubs, store)
    club_member_names = {
        member["name"]
        for member in members
        if requested_clubs and any(term in _member_club_terms(member) for term in requested_clubs)
    }
    ranking_source_records = (
        [item for item in combined_records if item["player_name"] in club_member_names]
        if requested_clubs
        else combined_records
    )
    matched_stats = None
    matched_pending = None
    matched_entries: list[dict[str, Any]] = []
    matched_filtered_entries: list[dict[str, Any]] = []
    if matched_member:
        matched_stats = next(
            (item for item in player_stats if item["player_name"] == matched_member["name"]),
            {"player_name": matched_member["name"], "runs": 0, "wickets": 0, "catches": 0, "matches": 0},
        )
        matched_pending = next(
            (item for item in pending_player_stats if item["player_name"] == matched_member["name"]),
            {"player_name": matched_member["name"], "runs": 0, "wickets": 0, "catches": 0, "matches": 0},
        )
        matched_entries = _player_participation_entries(store, matched_member)
        matched_filtered_entries = _filter_entries_for_requested_clubs(matched_entries, requested_clubs)
    stored_matches = (matched_stats or {}).get("matches", 0) + (matched_pending or {}).get("matches", 0)
    stored_runs = (matched_stats or {}).get("runs", 0) + (matched_pending or {}).get("runs", 0)
    filtered_totals = _aggregate_entries(matched_filtered_entries) if matched_filtered_entries else {"matches": 0, "runs": 0, "balls": 0, "wickets": 0, "catches": 0}
    year_match = re.search(r"\b(20\d{2})\b", q)
    query_year = year_match.group(1) if year_match else ""
    query_month = next((month_number for month_name, month_number in MONTH_NAMES.items() if month_name in q), "")

    player_match_intent = any(
        phrase in q
        for phrase in [
            "how many matches",
            "matches played",
            "match played",
            "played how many",
            "appearances",
            "innings",
        ]
    ) or ("played" in q and "match" in q)
    asks_for_months = "which months" in q or "what months" in q or "in which month" in q or "in which months" in q
    if asks_for_months and matched_members:
        player_match_intent = True
    age_intent = "how old" in q or ("age" in q and "average" not in q)
    phone_intent = any(term in q for term in ["phone", "mobile", "contact number", "phone number"])
    location_intent = any(term in q for term in ["where", "lives", "live in", "address", "city"])
    batting_order_intent = any(term in q for term in ["batting order", "batting position", "bats in the team", "bats in"])
    best_batting_order_intent = "best batting order" in q or ("best position" in q and "bat" in q)
    rank_intent = "rank" in q or "ranking" in q
    batting_average_intent = "batting average" in q
    strike_rate_intent = "strike rate" in q
    bowling_economy_intent = "bowling economy" in q or ("economy" in q and "bowl" in q)
    meta_rag_intent = "is this rag" in q or ("rag" in q and "llm" in q) or "from llm" in q
    model_intent = "what model" in q or "which llm" in q
    best_score_opponent_intent = (
        ("against" in q or "opponent" in q or "opposite team" in q)
        and any(term in q for term in ["best", "highest", "top", "made the best score", "best score", "highest score"])
    ) or "which team was it against" in q or "what team was it against" in q
    best_score_intent = any(
        term in q
        for term in [
            "best score",
            "highest score",
            "top score",
            "his best score",
            "her best score",
            "their best score",
        ]
    )

    top_batters = sorted(
        [item for item in ranking_source_records if item["runs"] > 0],
        key=lambda item: (-item["runs"], -item["matches"], -item["strike_rate"], item["player_name"]),
    )
    top_bowlers = sorted(
        [item for item in ranking_source_records if item["wickets"] > 0],
        key=lambda item: (-item["wickets"], -item["matches"], item["player_name"]),
    )
    top_fielders = sorted(
        [item for item in ranking_source_records if item["catches"] > 0],
        key=lambda item: (-item["catches"], -item["matches"], item["player_name"]),
    )
    reliable_players = sorted(
        ranking_source_records,
        key=lambda item: (
            -item["matches_available"],
            -item["matches"],
            -item["runs"],
            item["matches_no_response"],
            item["player_name"],
        ),
    )
    consistent_players = sorted(
        [item for item in ranking_source_records if item["matches"] > 0],
        key=lambda item: (
            -item["matches"],
            -item["matches_available"],
            -item["runs"],
            item["player_name"],
        ),
    )
    rarely_available_players = sorted(
        ranking_source_records,
        key=lambda item: (
            item["matches_available"],
            -item["matches_unavailable"],
            -item["matches_no_response"],
            item["player_name"],
        ),
    )

    batting_rank_by_player = {item["player_name"]: index for index, item in enumerate(top_batters, start=1)}
    bowling_rank_by_player = {item["player_name"]: index for index, item in enumerate(top_bowlers, start=1)}
    fielding_rank_by_player = {item["player_name"]: index for index, item in enumerate(top_fielders, start=1)}

    if meta_rag_intent:
        llm_status = get_llm_status()
        model_name = llm_status.get("model") or "no local model"
        answer = (
            f"This uses a grounded local RAG flow. The app reads live persisted data from SQLite first, "
            f"builds grounded facts and retrieval context, and then sends that context to the local LLM `{model_name}` for the final response."
        )
    elif model_intent:
        llm_status = get_llm_status()
        model_name = llm_status.get("model") or "no local model"
        answer = f"The current local LLM is `{model_name}`."
    elif matched_member and ("full name" in q or "real name" in q):
        full_name = matched_member.get("full_name") or matched_member["name"]
        answer = f"The full name is {full_name}."
    elif matched_member and ("alias" in q or "aliases" in q):
        display_name = _display_name(matched_member)
        aliases = ", ".join(matched_member.get("aliases", [])) or "none"
        answer = f"Saved aliases for {display_name} are {aliases}."
    elif matched_member and age_intent:
        display_name = _display_name(matched_member)
        age = matched_member.get("age")
        if age:
            answer = f"{display_name} is {age} years old."
        else:
            answer = f"I could not find the age of {display_name} in the stored data."
    elif matched_member and phone_intent:
        display_name = _display_name(matched_member)
        phone = str(matched_member.get("phone", "") or "").strip()
        if phone:
            answer = f"{display_name}'s phone number is {phone}."
        else:
            answer = f"I could not find a phone number for {display_name} in the stored data."
    elif matched_member and location_intent:
        display_name = _display_name(matched_member)
        answer = f"I could not find an address or city for {display_name} in the stored data."
    elif len(matched_members) > 1 and (batting_order_intent or best_batting_order_intent):
        summaries = []
        for member in matched_members:
            display_name = _display_name(member)
            positions = _historical_batting_positions(store, member["name"])
            if not positions:
                summaries.append(f"{display_name}: no reviewed historical batting positions stored")
                continue
            if best_batting_order_intent:
                best = _best_batting_position(store, member["name"])
                summaries.append(
                    f"{display_name}: best at number {best['position']} with {best['runs']} runs from {best['innings']} innings"
                )
            else:
                ordered_positions = ", ".join(str(item["position"]) for item in positions)
                summaries.append(f"{display_name}: batted at {ordered_positions}")
        answer = "; ".join(summaries) + "."
    elif matched_member and best_batting_order_intent:
        display_name = _display_name(matched_member)
        best = _best_batting_position(store, matched_member["name"])
        if best:
            answer = (
                f"{display_name}'s best batting order from reviewed historical scorecards is number {best['position']}, "
                f"with {best['runs']} runs across {best['innings']} innings there."
            )
        else:
            answer = f"I could not find reviewed historical batting positions for {display_name} in the stored data."
    elif matched_member and batting_order_intent:
        display_name = _display_name(matched_member)
        positions = _historical_batting_positions(store, matched_member["name"])
        if positions:
            details = "; ".join(
                f"{item['archive_date'] or 'unknown date'}: number {item['position']} ({item['runs']} runs)"
                for item in positions
            )
            answer = f"{display_name} has batted in these reviewed historical positions: {details}."
        else:
            answer = f"I could not find reviewed historical batting positions for {display_name} in the stored data."
    elif matched_member and best_score_opponent_intent:
        display_name = _display_name(matched_member)
        best = _best_score_opponent(store, matched_member["name"])
        if best and best.get("opponent"):
            answer = f"{display_name}'s best score was against {best['opponent']}."
        elif best:
            answer = f"I found {display_name}'s best score, but I could not find the opponent in the stored records."
        else:
            answer = f"I could not find a scored innings for {display_name} in the stored records."
    elif matched_member and best_score_intent:
        display_name = _display_name(matched_member)
        best = _best_score_details(store, matched_member["name"])
        if best:
            if best.get("opponent") and best.get("date"):
                answer = f"{display_name}'s best score is {best['runs']} against {best['opponent']} on {best['date']}."
            elif best.get("opponent"):
                answer = f"{display_name}'s best score is {best['runs']} against {best['opponent']}."
            else:
                answer = f"{display_name}'s best score is {best['runs']}."
        else:
            answer = f"I could not find a scored innings for {display_name} in the stored records."
    elif matched_member and batting_average_intent:
        display_name = _display_name(matched_member)
        if requested_clubs:
            matches = int(filtered_totals.get("matches", 0) or 0)
            batting_average = float(filtered_totals.get("batting_average", 0.0) or 0.0)
        else:
            combined_record = next((item for item in combined_records if item["player_name"] == matched_member["name"]), None)
            batting_average = float((combined_record or {}).get("batting_average", 0.0) or 0.0)
            matches = int((combined_record or {}).get("matches", 0) or 0)
        if matches:
            scope = f" for {requested_club_label}" if requested_clubs else ""
            answer = f"{display_name}'s batting average{scope} is {batting_average:.2f}."
        else:
            scope = f" for {requested_club_label}" if requested_clubs else ""
            answer = f"I could not calculate a batting average for {display_name}{scope} from the stored records yet."
    elif matched_member and strike_rate_intent:
        display_name = _display_name(matched_member)
        if requested_clubs:
            balls = int(filtered_totals.get("balls", 0) or 0)
            strike_rate = round((filtered_totals.get("runs", 0) / balls) * 100, 2) if balls else 0.0
        else:
            combined_record = next((item for item in combined_records if item["player_name"] == matched_member["name"]), None)
            strike_rate = float((combined_record or {}).get("strike_rate", 0.0) or 0.0)
            balls = int((combined_record or {}).get("balls", 0) or 0)
        if balls:
            scope = f" for {requested_club_label}" if requested_clubs else ""
            answer = f"{display_name}'s strike rate{scope} is {strike_rate:.2f}."
        else:
            scope = f" for {requested_club_label}" if requested_clubs else ""
            answer = f"I could not calculate a strike rate for {display_name}{scope} from the stored records yet."
    elif matched_member and bowling_economy_intent:
        display_name = _display_name(matched_member)
        answer = f"I could not calculate a bowling economy for {display_name} because bowling overs and runs conceded are not stored yet."
    elif matched_member and rank_intent and not any(term in q for term in ["run", "bat", "wicket", "bowl", "catch", "field"]):
        display_name = _display_name(matched_member)
        batting_rank = batting_rank_by_player.get(matched_member["name"])
        bowling_rank = bowling_rank_by_player.get(matched_member["name"])
        scope = f" in {requested_club_label}" if requested_clubs else ""
        if batting_rank and bowling_rank:
            answer = (
                f"{display_name} is ranked {_ordinal(batting_rank)} in batting{scope} and "
                f"{_ordinal(bowling_rank)} in bowling{scope}."
            )
        elif batting_rank:
            answer = (
                f"{display_name} is ranked {_ordinal(batting_rank)} in batting{scope}. "
                f"{display_name} does not have a bowling rank yet."
            )
        elif bowling_rank:
            answer = (
                f"{display_name} does not have a batting rank yet. "
                f"{display_name} is ranked {_ordinal(bowling_rank)} in bowling{scope}."
            )
        else:
            answer = f"{display_name} does not have a batting or bowling rank yet."
    elif matched_member and rank_intent and ("run" in q or "bat" in q):
        display_name = _display_name(matched_member)
        rank = batting_rank_by_player.get(matched_member["name"])
        if rank:
            scope = f" in {requested_club_label}" if requested_clubs else " in the team"
            answer = f"{display_name} is ranked {_ordinal(rank)}{scope} for runs."
        else:
            answer = f"{display_name} does not have a batting rank yet."
    elif matched_member and rank_intent and ("wicket" in q or "bowl" in q):
        display_name = _display_name(matched_member)
        rank = bowling_rank_by_player.get(matched_member["name"])
        if rank:
            scope = f" in {requested_club_label}" if requested_clubs else " in the team"
            answer = f"{display_name} is ranked {_ordinal(rank)}{scope} for wickets."
        else:
            answer = f"{display_name} does not have a bowling rank yet."
    elif matched_member and rank_intent and ("catch" in q or "field" in q):
        display_name = _display_name(matched_member)
        rank = fielding_rank_by_player.get(matched_member["name"])
        if rank:
            scope = f" in {requested_club_label}" if requested_clubs else " in the team"
            answer = f"{display_name} is ranked {_ordinal(rank)}{scope} for catches."
        else:
            answer = f"{display_name} does not have a fielding rank yet."
    elif age_intent or phone_intent or location_intent or batting_order_intent or best_batting_order_intent or best_score_opponent_intent or batting_average_intent or strike_rate_intent or bowling_economy_intent:
        answer = "Please mention the player name so I can answer from the stored records."
    elif len(matched_members) > 1 and player_match_intent:
        summaries = []
        total_matches = 0
        for member in matched_members:
            display_name = _display_name(member)
            entries = _filter_entries_for_requested_clubs(_player_participation_entries(store, member), requested_clubs)
            if query_year or query_month:
                entries = [item for item in entries if _date_matches(item.get("date", ""), query_year, query_month)]
            match_count = len(entries)
            total_matches += match_count
            summaries.append(f"{display_name}: {match_count}")

        if query_month and query_year:
            month_label = next(name.title() for name, value in MONTH_NAMES.items() if value == query_month)
            answer = (
                f"Match counts in {month_label} {query_year}: " + "; ".join(summaries) + f". Total: {total_matches}."
            )
        elif query_year:
            if asks_for_months:
                month_summaries = []
                for member in matched_members:
                    months_found: set[str] = set()
                    entries = _filter_entries_for_requested_clubs(_player_participation_entries(store, member), requested_clubs)
                    for entry in entries:
                        if str(entry.get("date", "")).startswith(query_year):
                            month_value = str(entry.get("date", ""))[5:7]
                            if month_value:
                                months_found.add(month_value)
                    display_name = _display_name(member)
                    month_list = ", ".join(MONTH_LABELS[month] for month in sorted(months_found)) or "none"
                    month_summaries.append(f"{display_name}: {month_list}")
                scope = f" for {requested_club_label}" if requested_clubs else ""
                answer = f"Match counts in {query_year}{scope}: " + "; ".join(summaries) + ". Months: " + "; ".join(month_summaries) + "."
            else:
                scope = f" for {requested_club_label}" if requested_clubs else ""
                answer = f"Match counts in {query_year}{scope}: " + "; ".join(summaries) + f". Total: {total_matches}."
        else:
            scope = f" for {requested_club_label}" if requested_clubs else ""
            answer = f"Match counts so far{scope}: " + "; ".join(summaries) + f". Total: {total_matches}."
    elif matched_member and player_match_intent:
        display_name = _display_name(matched_member)
        entries = matched_filtered_entries if requested_clubs else matched_entries
        if query_year or query_month:
            filtered_by_date = [item for item in entries if _date_matches(item.get("date", ""), query_year, query_month)]
            matches_filtered = len(filtered_by_date)
            months_found = {str(item.get("date", ""))[5:7] for item in filtered_by_date if str(item.get("date", ""))[5:7]}
            if query_month and query_year:
                month_label = next(name.title() for name, value in MONTH_NAMES.items() if value == query_month)
                scope = f" for {requested_club_label}" if requested_clubs else ""
                answer = f"{display_name} has played {matches_filtered} match(es){scope} in {month_label} {query_year}."
            elif query_month:
                month_label = next(name.title() for name, value in MONTH_NAMES.items() if value == query_month)
                scope = f" for {requested_club_label}" if requested_clubs else ""
                answer = f"{display_name} has played {matches_filtered} match(es){scope} in {month_label}."
            else:
                if asks_for_months and months_found:
                    month_list = ", ".join(MONTH_LABELS[month] for month in sorted(months_found))
                    scope = f" for {requested_club_label}" if requested_clubs else ""
                    answer = f"{display_name} has played {matches_filtered} match(es){scope} in {query_year}, in {month_list}."
                else:
                    scope = f" for {requested_club_label}" if requested_clubs else ""
                    answer = f"{display_name} has played {matches_filtered} match(es){scope} in {query_year}."
        else:
            total_matches = filtered_totals["matches"] if requested_clubs else stored_matches
            if asks_for_months:
                months_found = {str(item.get("date", ""))[5:7] for item in entries if str(item.get("date", ""))[5:7]}
                month_list = ", ".join(MONTH_LABELS[month] for month in sorted(months_found)) or "none"
                scope = f" for {requested_club_label}" if requested_clubs else ""
                answer = f"{display_name} has played {total_matches} confirmed match(es){scope} so far, in {month_list}."
            else:
                scope = f" for {requested_club_label}" if requested_clubs else ""
                answer = f"{display_name} has played {total_matches} confirmed match(es){scope} so far."
    elif ("top ranked" in q and "run" in q) or "top scorer" in q or ("most" in q and "run" in q):
        leader = top_batters[0] if top_batters else None
        if leader:
            scope = f" in {requested_club_label}" if requested_clubs else ""
            answer = (
                f"{leader['display_name']} is the top ranked batter{scope} with {leader['runs']} confirmed runs across "
                f"{leader['matches']} match(es)."
            )
        else:
            answer = "No batting runs are stored yet."
    elif ("most wicket" in q) or ("most wickets" in q) or ("who has got most wicket" in q) or ("who has the most wicket" in q):
        leader = top_bowlers[0] if top_bowlers else None
        if leader:
            scope = f" for {requested_club_label}" if requested_clubs else ""
            answer = (
                f"{leader['display_name']} has the most wickets{scope} with {leader['wickets']} across {leader['matches']} match(es)."
            )
        else:
            answer = "No wicket figures are stored yet."
    elif ("most number of catches" in q) or ("most catches" in q):
        leader = top_fielders[0] if top_fielders else None
        if leader:
            scope = f" for {requested_club_label}" if requested_clubs else ""
            answer = (
                f"{leader['display_name']} has taken the most catches{scope} with {leader['catches']} across {leader['matches']} match(es)."
            )
        else:
            answer = "No catch figures are stored yet."
    elif ("top 5" in q and ("bat" in q or "run" in q)) or ("top five" in q and ("bat" in q or "run" in q)):
        leaders = top_batters[:5]
        if leaders:
            prefix = f"Top 5 batters in {requested_club_label} by confirmed runs: " if requested_clubs else "Top 5 batters by confirmed runs: "
            answer = prefix + "; ".join(
                f"{index}. {item['display_name']} - {item['runs']} runs"
                for index, item in enumerate(leaders, start=1)
            ) + "."
        else:
            answer = "No batting runs are stored yet."
    elif matched_member and any(keyword in q for keyword in ["run", "runs", "score", "performance", "wicket", "player"]):
        display_name = _display_name(matched_member)
        if requested_clubs:
            answer = (
                f"{display_name} has {filtered_totals['runs']} runs, {filtered_totals['wickets']} wickets, and {filtered_totals['catches']} catches "
                f"across {filtered_totals['matches']} confirmed match(es) for {requested_club_label}."
            )
        else:
            answer = (
                f"{display_name} has {stored_runs} runs across {stored_matches} confirmed match(es) in the stored records. "
                f"Live fixture records account for {matched_stats['runs']} runs, {matched_stats['wickets']} wickets, and {matched_stats['catches']} catches; "
                f"confirmed historical scorecards account for {matched_pending['runs']} additional runs from {matched_pending['matches']} match(es)."
            )
    elif matched_member:
        display_name = _display_name(matched_member)
        if requested_clubs:
            answer = (
                f"{display_name} currently has {filtered_totals['matches']} confirmed match(es), {filtered_totals['runs']} runs, "
                f"{filtered_totals['wickets']} wickets, and {filtered_totals['catches']} catches for {requested_club_label}."
            )
        else:
            answer = (
                f"{display_name} currently has {stored_matches} confirmed match(es) and {stored_runs} confirmed runs in the stored records."
            )
    elif "most reliable" in q or "reliable player" in q:
        leader = reliable_players[0] if reliable_players else None
        if leader:
            answer = (
                f"{leader['display_name']} is the most reliable player right now, based on "
                f"{leader['matches_available']} current availability confirmation(s) and {leader['matches']} confirmed match(es) in the stored records."
            )
        else:
            answer = "I could not identify a reliable player from the stored records yet."
    elif "rarely available" in q:
        leaders = rarely_available_players[:5]
        answer = "Players who are rarely available right now: " + "; ".join(
            f"{item['display_name']} - {item['matches_available']} yes, {item['matches_unavailable']} no, {item['matches_no_response']} no response"
            for item in leaders
        ) + "."
    elif "consistent" in q and ("last year" in q or "playing most games" in q or "most games" in q):
        leaders = consistent_players[:5]
        if leaders:
            answer = (
                "Based on confirmed 2025 match history plus current 2026 availability, the most consistent players are: "
                + "; ".join(
                    f"{item['display_name']} - {item['matches']} matches, {item['matches_available']} current availability confirmation(s)"
                    for item in leaders
                )
                + "."
            )
        else:
            answer = "I could not find enough historical match data for a consistency ranking yet."
    elif "next" in q and ("match" in q or "fixture" in q):
        if next_match:
            answer = (
                f"The next match is {next_match['date_label']} against {next_match['opponent']} at "
                f"{next_match['details'].get('venue', store['club']['home_ground'])}. "
                f"{len(next_match['availability'])} players are currently marked available."
            )
        else:
            answer = f"{store['club'].get('name', 'This club')} does not have a scheduled fixture stored yet."
    elif "availability" in q or "available" in q:
        if fixtures:
            lowest = min(fixtures, key=lambda item: len(item["availability"]))
            availability_leader = _display_name_for_name(summary["availability_leader"], members)
            answer = (
                f"{availability_leader} has the strongest availability track so far. "
                f"The leanest fixture is {lowest['date_label']} vs {lowest['opponent']} with "
                f"{len(lowest['availability'])} confirmed players."
            )
        else:
            answer = f"No fixture availability is stored yet for {store['club'].get('name', 'this club')}."
    elif "captain" in q:
        answer = (
            f"{summary['matches_without_captain']} fixtures still need a Heartlake captain assigned. "
            "Use the Match Setup form to lock in captain, toss, venue, and scorer details."
        )
    elif "score" in q or "scorecard" in q:
        completed = [match for match in fixtures if match["status"] == "Completed" or match["heartlake_score"]]
        if completed:
            latest = completed[-1]
            answer = (
                f"The latest scored match is {latest['date_label']} vs {latest['opponent']}: "
                f"Heartlake {latest['heartlake_score'] or '--'} and Opponent {latest['opponent_score'] or '--'}. "
                f"Result: {latest['scorecard']['result']}."
            )
        else:
            answer = (
                "No completed scorecards are in the website yet. Use Live Scoring or upload a scorecard image to recover one."
            )
    elif "player" in q or "roster" in q or "member" in q:
        roster = ", ".join(_display_name(member) for member in members)
        answer = (
            f"The current roster is {roster}. There are {summary['member_count']} stored player profiles."
            if roster
            else f"No player profiles are stored yet for {store['club'].get('name', 'this club')}."
        )
    elif "runs" in q or "batting" in q:
        if top_batters:
            leader = top_batters[0]
            answer = (
                f"{leader['display_name']} leads the batting charts with {leader['runs']} confirmed runs across "
                f"{leader['matches']} match(es)."
            )
        else:
            answer = "No player batting entries have been recorded yet."
    elif "wicket" in q or "bowling" in q:
        wicket_leader = top_bowlers[0] if top_bowlers else None
        if wicket_leader and wicket_leader["wickets"] > 0:
            answer = (
                f"{wicket_leader['display_name']} leads the bowling chart with {wicket_leader['wickets']} wickets."
            )
        else:
            answer = "No bowling figures are stored yet."
    elif "commentary" in q or "voice" in q:
        answer = (
            f"There are {summary['commentary_count']} saved commentary entries. "
            "Voice commentary is stored as transcript text, so it can be persisted with each match locally."
        )
    elif "archive" in q or "image" in q or "ocr" in q:
        answer = (
            f"There are {summary['archive_count']} uploaded scorecard images ready for review. "
            "Upload a picture, review the draft scorecard, then apply it to a match to restore the online record."
        )
    elif "whatsapp" in q:
        answer = (
            "Each match can launch a WhatsApp coordination message for captains and players using the club number. "
            "It is built for local testing first and can later be wired to deeper messaging automation."
        )
    elif "visiting" in q or "opponent" in q or "teams" in q:
        if summary["visiting_team_count"]:
            answer = (
                f"{store['club'].get('name', 'This club')} has {summary['visiting_team_count']} visiting teams on the calendar. "
                f"The most frequent one is {summary['most_common_opponent']} with {summary['most_common_opponent_count']} fixtures."
            )
        else:
            answer = f"No visiting-team fixtures are stored yet for {store['club'].get('name', 'this club')}."
    else:
        top_available = _display_name_for_name(availability_board[0]["player_name"], members) if availability_board else "the roster"
        if next_match:
            answer = (
                f"{store['club'].get('name', 'This club')} has {summary['fixture_count']} fixtures planned for {store['club']['season']}. "
                f"The next match is {next_match['date_label']} vs {next_match['opponent']}, and {top_available} currently has the strongest availability record. "
                "Ask about scorecards, captains, players, commentary, archive uploads, or visiting teams."
            )
        else:
            answer = (
                f"{store['club'].get('name', 'This club')} has {summary['fixture_count']} fixtures planned for {store['club']['season']}. "
                "No upcoming fixtures are stored yet. Ask about players, archive scorecards, rankings, or club stats."
            )

    return {"answer": answer, "mode": "heuristic"}


def answer_question(
    question: str,
    store: dict[str, Any],
    history: list[dict[str, str]] | None = None,
    session_id: str | None = None,
) -> dict[str, Any]:
    effective_question = _contextualize_question(question, history, store["members"], store)
    prefer_grounded = _prefer_heuristic_answer(effective_question)
    grounded = _heuristic_answer(question, store, history=history) if prefer_grounded else None
    if grounded:
        return {**grounded, "session_id": session_id or ""}
    grounded_facts = ""
    rag_answer = _rag_answer(question, store, grounded_facts=grounded_facts, history=history)
    if rag_answer:
        return {"answer": rag_answer, "mode": "grounded-rag" if grounded_facts else "rag", "session_id": session_id or ""}
    fallback = _heuristic_answer(question, store, history=history)
    return {**fallback, "session_id": session_id or ""}
