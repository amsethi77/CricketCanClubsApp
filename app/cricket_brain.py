import os
import re
import logging
from functools import lru_cache
from math import sqrt
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
PREFERRED_OLLAMA_EMBED_MODELS = [
    "nomic-embed-text",
    "mxbai-embed-large",
    "snowflake-arctic-embed",
    "all-minilm",
]

RAG_TEMPERATURE = float(os.environ.get("OLLAMA_RAG_TEMPERATURE", "0.2"))
FORECAST_TEMPERATURE = float(os.environ.get("OLLAMA_FORECAST_TEMPERATURE", "0.55"))
RAG_TOP_P = float(os.environ.get("OLLAMA_RAG_TOP_P", "0.85"))
FORECAST_TOP_P = float(os.environ.get("OLLAMA_FORECAST_TOP_P", "0.95"))
RAG_TOP_K = int(os.environ.get("OLLAMA_RAG_TOP_K", "40"))
FORECAST_TOP_K = int(os.environ.get("OLLAMA_FORECAST_TOP_K", "50"))
RAG_NUM_PREDICT = int(os.environ.get("OLLAMA_RAG_NUM_PREDICT", "220"))
FORECAST_NUM_PREDICT = int(os.environ.get("OLLAMA_FORECAST_NUM_PREDICT", "260"))
EMBEDDING_MODEL_ENV = os.environ.get("OLLAMA_EMBED_MODEL", "").strip()
CONTEXT_CHUNK_LIMIT = int(os.environ.get("OLLAMA_CONTEXT_CHUNK_LIMIT", "900"))
MAX_CONTEXT_SNIPPETS = int(os.environ.get("OLLAMA_MAX_CONTEXT_SNIPPETS", "12"))
PROFANITY_WORDS = {
    "asshole",
    "bastard",
    "bitch",
    "fuck",
    "fucker",
    "motherfucker",
    "shit",
    "shitty",
    "cunt",
}
CLUB_GENERIC_WORDS = {
    "club",
    "cricket",
    "team",
    "xi",
}

logger = logging.getLogger("CricketClubBrain")

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
        embedding_model = _embedding_model_from_tags(models)
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
            "embedding_model": embedding_model,
            "embeddings_available": bool(embedding_model),
            "base_url": base_url,
            "safety": {
                "grounded": True,
                "chunking": True,
                "embeddings": bool(embedding_model),
                "content_filter": True,
                "profanity_filter": True,
            },
        }
    except Exception:
        return {
            "provider": "heuristic",
            "available": True,
            "model": "built-in data assistant",
            "embedding_model": "",
            "embeddings_available": False,
            "base_url": None,
            "safety": {
                "grounded": True,
                "chunking": True,
                "embeddings": False,
                "content_filter": True,
                "profanity_filter": True,
            },
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


def _normalized_name_tokens(value: str) -> tuple[str, ...]:
    tokens = [
        token
        for token in re.findall(r"[a-z0-9]+", str(value or "").lower())
        if token and token not in STOP_WORDS and token not in CLUB_GENERIC_WORDS and len(token) > 1
    ]
    return tuple(tokens)


def _name_matches_requested(candidate: str, requested_values: set[str]) -> bool:
    candidate_tokens = _normalized_name_tokens(candidate)
    if not candidate_tokens:
        return False
    candidate_text = " ".join(candidate_tokens)
    for raw_value in requested_values:
        value_tokens = _normalized_name_tokens(raw_value)
        if not value_tokens:
            continue
        value_text = " ".join(value_tokens)
        if candidate_text == value_text:
            return True
        if candidate_text in value_text or value_text in candidate_text:
            return True
    return False


def _llm_options(mode: str) -> dict[str, Any]:
    if mode == "forecast":
        return {
            "temperature": FORECAST_TEMPERATURE,
            "top_p": FORECAST_TOP_P,
            "top_k": FORECAST_TOP_K,
            "repeat_penalty": 1.08,
            "num_predict": FORECAST_NUM_PREDICT,
        }
    if mode == "rag":
        return {
            "temperature": RAG_TEMPERATURE,
            "top_p": RAG_TOP_P,
            "top_k": RAG_TOP_K,
            "repeat_penalty": 1.05,
            "num_predict": RAG_NUM_PREDICT,
        }
    return {"temperature": RAG_TEMPERATURE, "top_p": RAG_TOP_P, "top_k": RAG_TOP_K, "num_predict": RAG_NUM_PREDICT}


def _contains_profanity(text: str) -> bool:
    lowered = f" {str(text or '').lower()} "
    return any(re.search(rf"(?<!\w){re.escape(word)}(?!\w)", lowered) for word in PROFANITY_WORDS)


def _redact_profanity(text: str) -> str:
    result = str(text or "")
    for word in PROFANITY_WORDS:
        result = re.sub(rf"(?<!\w){re.escape(word)}(?!\w)", "***", result, flags=re.IGNORECASE)
    return result


def _moderated_prompt_response(question: str) -> dict[str, Any] | None:
    if not _contains_profanity(question):
        return None
    return {
        "answer": "Please keep the question cricket-focused and respectful.",
        "mode": "moderated",
        "source_provider": "heuristic",
        "source_label": "Content filter",
    }


def _chunk_text_for_context(text: str, limit: int = CONTEXT_CHUNK_LIMIT) -> list[str]:
    lines = [line.strip() for line in str(text or "").splitlines() if line.strip()]
    if not lines:
        return [str(text or "").strip()] if str(text or "").strip() else []
    chunks: list[str] = []
    current: list[str] = []
    current_length = 0
    for line in lines:
        if current and current_length + len(line) + 1 > limit:
            chunks.append("\n".join(current))
            current = [line]
            current_length = len(line)
            continue
        current.append(line)
        current_length += len(line) + (1 if len(current) > 1 else 0)
    if current:
        chunks.append("\n".join(current))
    return chunks


def _vector_norm(vector: list[float]) -> float:
    return sqrt(sum(value * value for value in vector)) if vector else 0.0


def _cosine_similarity(left: list[float], right: list[float]) -> float:
    if not left or not right or len(left) != len(right):
        return 0.0
    denominator = _vector_norm(left) * _vector_norm(right)
    if not denominator:
        return 0.0
    return sum(x * y for x, y in zip(left, right)) / denominator


def _embedding_model_candidates() -> list[str]:
    candidates: list[str] = []
    if EMBEDDING_MODEL_ENV:
        candidates.append(EMBEDDING_MODEL_ENV)
    candidates.extend(model for model in PREFERRED_OLLAMA_EMBED_MODELS if model not in candidates)
    return candidates


def _embedding_model_from_tags(tags: list[str]) -> str:
    tag_set = {tag.strip() for tag in tags if tag.strip()}
    for candidate in _embedding_model_candidates():
        if candidate in tag_set:
            return candidate
    return ""


@lru_cache(maxsize=2048)
def _ollama_embedding_for_text_cached(base_url: str, embedding_model: str, text: str) -> tuple[float, ...]:
    if not base_url or not embedding_model or not text.strip():
        return ()
    response = httpx.post(
        f"{base_url}/api/embeddings",
        json={"model": embedding_model, "prompt": text},
        timeout=20.0,
    )
    response.raise_for_status()
    embedding = response.json().get("embedding", [])
    if not isinstance(embedding, list):
        return ()
    return tuple(float(value) for value in embedding if isinstance(value, (int, float)))


def _llm_embedding_for_text(text: str, llm_status: dict[str, Any]) -> list[float] | None:
    base_url = str(llm_status.get("base_url") or "").strip()
    embedding_model = str(llm_status.get("embedding_model") or "").strip()
    if not base_url or not embedding_model or not text.strip():
        return None
    try:
        cached = _ollama_embedding_for_text_cached(base_url, embedding_model, text)
        return list(cached) if cached else None
    except Exception:
        return None


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
        if lowered in CLUB_GENERIC_WORDS:
            return
        if lowered in seen:
            return
        if _name_matches_requested(value, {q}):
            seen.add(lowered)
            pattern = re.compile(rf"(?<!\w){re.escape(lowered)}(?!\w)")
            found = pattern.search(q)
            matches.append((found.start() if found else len(matches), lowered))

    clubs = list(store.get("clubs", []) or []) + list(store.get("all_clubs", []) or [])
    teams = list(store.get("teams", []) or []) + list(store.get("all_teams", []) or [])
    for club in clubs:
        consider(club.get("name", ""))
        consider(club.get("short_name", ""))
    for team in teams:
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
                "team_label": "Club",
                "club": "heartlake cricket club",
                "club_label": "Club",
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


def _global_analysis_store(store: dict[str, Any]) -> dict[str, Any]:
    return {
        "club": dict(store.get("focus_club") or store.get("club") or {}),
        "clubs": list(store.get("all_clubs") or store.get("clubs") or []),
        "teams": list(store.get("all_teams") or store.get("teams") or []),
        "members": list(store.get("all_members") or store.get("members") or []),
        "fixtures": list(store.get("all_fixtures") or store.get("fixtures") or []),
        "archive_uploads": list(store.get("all_archive_uploads") or store.get("archive_uploads") or []),
        "member_summary_stats": list(store.get("all_member_summary_stats") or store.get("member_summary_stats") or []),
        "member_year_stats": list(store.get("all_member_year_stats") or store.get("member_year_stats") or []),
        "member_club_stats": list(store.get("all_member_club_stats") or store.get("member_club_stats") or []),
        "club_summary_stats": list(store.get("all_club_summary_stats") or store.get("club_summary_stats") or []),
        "club_year_stats": list(store.get("all_club_year_stats") or store.get("club_year_stats") or []),
        "viewer_profile": dict(store.get("viewer_profile") or {}),
    }


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


def _player_availability_by_club(store: dict[str, Any], player_name: str) -> list[dict[str, Any]]:
    club_lookup = {str(club.get("id") or ""): str(club.get("name") or club.get("short_name") or "").strip() for club in store.get("clubs", []) or []}
    grouped: dict[str, dict[str, int | str]] = {}
    for match in store.get("fixtures", []):
        status = str(match.get("availability_statuses", {}).get(player_name, "") or "").strip()
        if not status:
            continue
        club_id = str(match.get("club_id") or "").strip()
        club_name = club_lookup.get(club_id, str(match.get("club_name") or match.get("club") or club_id or "Unknown club").strip())
        bucket = grouped.setdefault(
            club_id or club_name.lower(),
            {
                "club_name": club_name or "Unknown club",
                "available": 0,
                "maybe": 0,
                "unavailable": 0,
                "no_response": 0,
            },
        )
        if status == "available":
            bucket["available"] = int(bucket["available"]) + 1
        elif status == "maybe":
            bucket["maybe"] = int(bucket["maybe"]) + 1
        elif status == "unavailable":
            bucket["unavailable"] = int(bucket["unavailable"]) + 1
        else:
            bucket["no_response"] = int(bucket["no_response"]) + 1
    return sorted(grouped.values(), key=lambda item: (-int(item["available"]), -int(item["maybe"]), str(item["club_name"])))


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
                f"team: {member.get('team_name', 'Club')}",
                f"teams: {', '.join(team.get('team_name') if isinstance(team, dict) else str(team) for team in (member.get('team_memberships') or [])) or member.get('team_name', 'Club')}",
                f"clubs: {', '.join(club.get('club_name') for club in (member.get('club_memberships') or []) if club.get('club_name')) or store['club'].get('name', 'Club')}",
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
                    f"scorecard: Club {match.get('scorecard', {}).get('heartlake_runs') or '--'}/"
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
                    f"scorecard: Club {archive.get('draft_scorecard', {}).get('heartlake_runs') or '--'}/"
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
            f"[club] {store['club'].get('name', 'Club')}",
            f"live_season: {store['club'].get('season')}",
            f"fixture_count: {summary.get('fixture_count', 0)}",
            f"member_count: {summary.get('member_count', 0)}",
            f"archive_count: {summary.get('archive_count', 0)}",
            f"next_match: {next_match.get('date_label', 'None')} vs {next_match.get('opponent', 'No scheduled opponent')}",
        ]
    )
    return {"kind": "club", "key": "club", "text": text}


def _rank_context_snippets(
    question: str,
    snippets: list[dict[str, Any]],
    matched_members: list[dict[str, Any]],
    llm_status: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    query_terms = _query_terms(question)
    matched_names = {member["name"].lower() for member in matched_members}
    matched_full_names = {str(member.get("full_name", "")).lower() for member in matched_members if member.get("full_name")}
    llm_status = llm_status or get_llm_status()
    query_embedding = _llm_embedding_for_text(question, llm_status)

    ranked = []
    for snippet in snippets:
        chunks = _chunk_text_for_context(snippet["text"])
        for chunk_index, chunk_text in enumerate(chunks):
            lowered = chunk_text.lower()
            score = sum(3 for term in query_terms if term in lowered)
            if snippet["kind"] == "player" and any(name in lowered for name in matched_names | matched_full_names):
                score += 50
            if snippet["kind"] == "archive" and ("archive" in query_terms or "scorecard" in query_terms):
                score += 8
            if snippet["kind"] == "fixture" and any(term in query_terms for term in {"availability", "next", "match", "fixture", "captain"}):
                score += 6
            if snippet["kind"] == "club":
                score += 2
            chunk_embedding = _llm_embedding_for_text(chunk_text, llm_status) if query_embedding else None
            if query_embedding and chunk_embedding:
                score += int(_cosine_similarity(query_embedding, chunk_embedding) * 30)
            ranked.append(
                (
                    score,
                    {
                        **snippet,
                        "text": chunk_text,
                        "chunk_index": chunk_index,
                        "chunk_count": len(chunks),
                    },
                )
            )

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
        if len(selected) >= MAX_CONTEXT_SNIPPETS:
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

    analysis_store = _global_analysis_store(store)
    effective_question = _contextualize_question(question, history, analysis_store["members"], analysis_store)
    q = effective_question.lower().strip()
    fixtures = analysis_store["fixtures"]
    members = analysis_store["members"]
    archives = analysis_store["archive_uploads"]
    summary = build_summary(analysis_store)
    player_stats = build_player_stats(fixtures, members)
    pending_player_stats = build_player_pending_stats(archives, members)
    matched_members = _matched_members(effective_question, members)

    snippets = [_club_context_snippet(analysis_store, summary)]
    snippets.extend(_player_context_snippets(analysis_store, members, fixtures, player_stats, pending_player_stats))
    snippets.extend(_fixture_context_snippets(fixtures))
    snippets.extend(_archive_context_snippets(archives))
    selected_snippets = _rank_context_snippets(question, snippets, matched_members, llm_status)
    context = "\n\n".join(snippet["text"] for snippet in selected_snippets)
    grounded_block = grounded_facts.strip()

    system_prompt = (
        "You answer questions about persisted club cricket data using only the supplied context.\n"
        "Rules:\n"
        "- Do not guess or invent facts.\n"
        "- If the answer is not supported by context, say you could not find it in the stored data.\n"
        "- Historical archive scorecards count as confirmed historical match history.\n"
        "- The live 2026 fixture season is separate from the 2025 historical archive season.\n"
        "- The supplied context includes all clubs, teams, fixtures, archives, member stats, and club summary tables unless the question explicitly narrows the scope.\n"
        "- Player identity comes from the persisted member name, full name, and saved aliases in the supplied context.\n"
        "- Treat every stored player the same way; do not assume any one player is special.\n"
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
                "options": _llm_options("rag"),
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
        return _redact_profanity(answer) or None
    except Exception:
        return None


def _prediction_question_intent(question: str) -> bool:
    q = question.lower().strip()
    has_year = bool(re.search(r"\b(20\d{2})\b", q))
    season_context = has_year or any(
        phrase in q
        for phrase in [
            "next season",
            "future season",
            "upcoming season",
            "season outlook",
            "performance outlook",
        ]
    )
    future_phrases = [
        "predict",
        "prediction",
        "forecast",
        "projection",
        "project",
        "future performance",
        "future year",
        "next year",
        "outlook",
        "trend analysis",
        "likely to",
        "expected to",
        "estimate",
        "probability",
        "performance outlook",
        "going to be",
        "going to perform",
        "will perform",
        "will be",
        "will do",
    ]
    return any(
        phrase in q for phrase in future_phrases
    ) or (
        "will" in q
        and any(term in q for term in ["run", "runs", "wicket", "wickets", "catch", "catches", "score", "perform"])
    ) or (
        season_context
        and (
            "performance" in q
            or "perform" in q
            or "going to" in q
            or "how is" in q
            or "how will" in q
        )
    )


def _forecast_rows_for_members(store: dict[str, Any], analysis_store: dict[str, Any], matched_members: list[dict[str, Any]]) -> list[dict[str, Any]]:
    member_year_rows = list(analysis_store.get("member_year_stats") or [])
    member_club_rows = list(analysis_store.get("member_club_stats") or [])
    overall_rows = list(analysis_store.get("member_summary_stats") or [])
    selected_names = {member["name"] for member in matched_members if member.get("name")}
    if selected_names:
        overall_rows = [row for row in overall_rows if row.get("player_name") in selected_names]
        member_year_rows = [row for row in member_year_rows if row.get("player_name") in selected_names]
        member_club_rows = [row for row in member_club_rows if row.get("player_name") in selected_names]
    else:
        top_names = {
            row.get("player_name")
            for row in sorted(
                overall_rows,
                key=lambda item: (
                    -int(item.get("runs", 0) or 0),
                    -int(item.get("matches", 0) or 0),
                    item.get("player_name", ""),
                ),
            )[:5]
            if row.get("player_name")
        }
        if top_names:
            overall_rows = [row for row in overall_rows if row.get("player_name") in top_names]
            member_year_rows = [row for row in member_year_rows if row.get("player_name") in top_names]
            member_club_rows = [row for row in member_club_rows if row.get("player_name") in top_names]

    snippets: list[dict[str, Any]] = []
    for row in overall_rows[:8]:
        member = next((item for item in analysis_store.get("members", []) if item.get("name") == row.get("player_name")), None)
        if not member:
            continue
        year_rows = sorted(
            [item for item in member_year_rows if item.get("player_name") == row.get("player_name")],
            key=lambda item: str(item.get("season_year") or ""),
        )
        club_rows = sorted(
            [item for item in member_club_rows if item.get("player_name") == row.get("player_name")],
            key=lambda item: (str(item.get("club_name") or ""), str(item.get("club_id") or "")),
        )
        recent_year_rows = year_rows[-3:]
        recent_year_text = "; ".join(
            (
                f"{item.get('season_year')}: matches={item.get('matches', 0)}, runs={item.get('runs', 0)}, "
                f"wickets={item.get('wickets', 0)}, catches={item.get('catches', 0)}, "
                f"avg={item.get('batting_average', 0)}, sr={item.get('strike_rate', 0)}, "
                f"highest={item.get('highest_score', '') or 'n/a'}"
            )
            for item in recent_year_rows
        )
        club_text = "; ".join(
            (
                f"{item.get('club_name')}: matches={item.get('matches', 0)}, runs={item.get('runs', 0)}, "
                f"wickets={item.get('wickets', 0)}, catches={item.get('catches', 0)}, "
                f"avg={item.get('batting_average', 0)}, sr={item.get('strike_rate', 0)}, "
                f"highest={item.get('highest_score', '') or 'n/a'}"
            )
            for item in club_rows[:3]
        )
        snippets.append(
            {
                "kind": "forecast-player",
                "key": row.get("player_name", ""),
                "text": "\n".join(
                    [
                        f"[forecast-player] {_display_name(member)}",
                        f"overall: matches={row.get('matches', 0)}, runs={row.get('runs', 0)}, wickets={row.get('wickets', 0)}, catches={row.get('catches', 0)}, avg={row.get('batting_average', 0)}, sr={row.get('strike_rate', 0)}, highest={row.get('highest_score', '') or 'n/a'}",
                        f"milestones: 25+={row.get('scores_25_plus', 0)}, 50+={row.get('scores_50_plus', 0)}, 100+={row.get('scores_100_plus', 0)}",
                        f"clubs: {club_text or 'none'}",
                        f"recent_years: {recent_year_text or 'none'}",
                        f"availability: available={row.get('matches_available', 0)}, maybe={row.get('matches_maybe', 0)}, unavailable={row.get('matches_unavailable', 0)}, no_response={row.get('matches_no_response', 0)}",
                    ]
                ),
            }
        )
    return snippets


def _forecast_answer_is_grounded(answer: str, context: str, question: str) -> bool:
    if not answer.strip():
        return False
    allowed_numbers = set(re.findall(r"\b\d+(?:\.\d+)?\b", f"{context}\n{question}"))
    if not allowed_numbers:
        return True
    for token in re.findall(r"\b\d+(?:\.\d+)?\b", answer):
        if token not in allowed_numbers:
            return False
    return True


def _forecast_answer_needs_grounded_fallback(answer: str) -> bool:
    lowered = answer.lower()
    generic_markers = [
        "cautious forecast",
        "cautious club forecast",
        "cannot justify exact numeric projections",
        "cannot justify exact numbers",
        "cannot provide exact numeric projections",
        "not enough recent trend data",
        "not enough data",
        "cannot find any information",
        "cannot find information",
        "based on the stored records",
        "i can summarize the direction of performance",
        "the provided context only includes fixtures",
        "uncertain how",
        "without recent form data",
        "i cannot predict",
    ]
    return any(marker in lowered for marker in generic_markers)


def _forecast_trend_snippets(rows: list[dict[str, Any]], entity_label: str, value_fields: list[str]) -> str:
    ordered_rows = sorted(
        [row for row in rows if str(row.get("season_year") or "").strip()],
        key=lambda item: str(item.get("season_year") or ""),
        reverse=True,
    )
    if not ordered_rows:
        return ""

    recent_rows = ordered_rows[:3]
    comparison_rows = [
        row
        for row in ordered_rows
        if int(row.get("matches", row.get("fixture_count", 0)) or 0) > 0
    ]
    if not comparison_rows:
        comparison_rows = ordered_rows
    parts: list[str] = []
    for row in recent_rows:
        year = str(row.get("season_year") or "").strip() or "unknown year"
        metrics: list[str] = []
        for field in value_fields:
            value = row.get(field)
            if value in (None, ""):
                continue
            if field in {"batting_average", "strike_rate"}:
                try:
                    metrics.append(f"{field.replace('_', ' ')}={float(value):.2f}")
                except (TypeError, ValueError):
                    continue
            else:
                metrics.append(f"{field.replace('_', ' ')}={value}")
        if metrics:
            parts.append(f"{year}: " + ", ".join(metrics))
        else:
            parts.append(year)

    latest = recent_rows[0]
    latest_year = str(latest.get("season_year") or "").strip() or "the latest year"
    latest_matches = int(latest.get("matches", latest.get("fixture_count", 0)) or 0)
    if latest_matches == 0 and len(comparison_rows) > 0:
        trend_bits: list[str] = [f"{latest_year} currently has no confirmed matches yet"]
        reference = comparison_rows[0]
        reference_year = str(reference.get("season_year") or "").strip() or "the latest observed year"
        reference_matches = int(reference.get("matches", reference.get("fixture_count", 0)) or 0)
        reference_runs = int(reference.get("runs", reference.get("total_runs", 0)) or 0)
        if reference_matches:
            trend_bits.append(f"the latest observed scored season is {reference_year} with {reference_runs} runs across {reference_matches} confirmed match(es)")
        if len(comparison_rows) > 1:
            prior = comparison_rows[1]
            prior_year = str(prior.get("season_year") or "").strip() or "the prior observed year"
            prior_runs = int(prior.get("runs", prior.get("total_runs", 0)) or 0)
            prior_matches = int(prior.get("matches", prior.get("fixture_count", 0)) or 0)
            if prior_runs != reference_runs:
                direction = "up" if reference_runs > prior_runs else "down"
                trend_bits.append(
                    f"that puts the observed trend {direction} from {prior_runs} in {prior_year} across {prior_matches} match(es)"
                )
        return f"{entity_label} recent trend: " + "; ".join(trend_bits) + ". Year-by-year data: " + "; ".join(parts) + "."

    latest = recent_rows[0]
    previous = recent_rows[1] if len(recent_rows) > 1 else {}
    trend_bits: list[str] = []
    latest_runs = int(latest.get("runs", 0) or 0)
    previous_runs = int(previous.get("runs", 0) or 0)
    if len(recent_rows) > 1 and latest_runs != previous_runs:
        direction = "up" if latest_runs > previous_runs else "down"
        trend_bits.append(f"runs are trending {direction} from {previous_runs} in {previous.get('season_year', 'the prior year')} to {latest_runs} in {latest.get('season_year', 'the latest year')}")
    latest_matches = int(latest.get("matches", 0) or 0)
    if latest_matches:
        trend_bits.append(f"{latest_matches} confirmed match(es) in {latest.get('season_year', 'the latest year')}")
    latest_avg = latest.get("batting_average")
    if latest_avg not in (None, ""):
        try:
            trend_bits.append(f"batting average {float(latest_avg):.2f}")
        except (TypeError, ValueError):
            pass
    latest_sr = latest.get("strike_rate")
    if latest_sr not in (None, ""):
        try:
            trend_bits.append(f"strike rate {float(latest_sr):.2f}")
        except (TypeError, ValueError):
            pass

    trend_text = "; ".join(trend_bits)
    if trend_text:
        return f"{entity_label} recent trend: {trend_text}. Year-by-year data: " + "; ".join(parts) + "."
    return f"{entity_label} recent year-by-year data: " + "; ".join(parts) + "."


def _forecast_fallback_answer(question: str, matched_members: list[dict[str, Any]], requested_clubs: list[str], analysis_store: dict[str, Any]) -> str:
    member = matched_members[0] if matched_members else None
    member_names = ", ".join(_display_name(member_item) for member_item in matched_members[:2] if member_item.get("name"))
    requested_club_names = ", ".join(
        str(club).strip()
        for club in requested_clubs
        if str(club).strip()
    )
    requested_clubs_lower = {item.strip().lower() for item in requested_clubs if str(item).strip()}
    clubs = [
        club
        for club in (analysis_store.get("clubs") or [])
        if str(club.get("name") or club.get("short_name") or club.get("id") or "").strip()
        and (
            not requested_clubs_lower
            or str(club.get("id") or "").strip().lower() in requested_clubs_lower
            or str(club.get("name") or "").strip().lower() in requested_clubs_lower
            or str(club.get("short_name") or "").strip().lower() in requested_clubs_lower
        )
    ]
    club = clubs[0] if clubs else None
    if member:
        display_name = _display_name(member)
        rows = [
            row
            for row in (analysis_store.get("member_year_stats") or [])
            if str(row.get("player_name") or "").strip() == str(member.get("name") or "").strip()
        ]
        trend = _forecast_trend_snippets(
            rows,
            f"{display_name}'s performance",
            ["matches", "runs", "batting_average", "strike_rate", "wickets", "catches", "highest_score", "scores_25_plus", "scores_50_plus", "scores_100_plus"],
        )
        if trend:
            latest_year = max((str(row.get("season_year") or "") for row in rows if str(row.get("season_year") or "").strip()), default="")
            if latest_year:
                return (
                    f"{display_name}'s 2026 outlook should be read from the latest stored trend data rather than a guessed projection. "
                    f"{trend} This suggests the safest expectation is that his 2026 performance should follow the same upward or steady trajectory if his opportunities stay similar."
                )
            return trend
        return (
            f"{display_name}'s forecast is still too thin for a numeric projection, but the stored data does not show any sign of a collapse."
        )
    if club:
        club_label = str(club.get("name") or club.get("short_name") or club.get("id") or "the requested club").strip()
        club_id = str(club.get("id") or "").strip()
        rows = [
            row
            for row in (analysis_store.get("club_year_stats") or [])
            if str(row.get("club_id") or "").strip().lower() == club_id.lower()
        ]
        trend = _forecast_trend_snippets(
            rows,
            f"{club_label}'s performance",
            ["fixture_count", "archive_count", "total_runs", "total_wickets", "total_catches", "highest_score", "scores_25_plus", "scores_50_plus", "scores_100_plus"],
        )
        if trend:
            return (
                f"{club_label}'s 2026 outlook should stay club-focused and grounded in the stored year-by-year record. "
                f"{trend} This is a cautious projection based on the latest available club trend data."
            )
        return f"{club_label}'s forecast is too thin for a numeric projection from the stored club records."
    if member_names or requested_club_names:
        label = member_names or requested_club_names or "the requested subject"
        return f"{label} does not have enough stored year-by-year trend data for a stronger forecast."
    return (
        "Based on the stored records, I can only give a cautious qualitative forecast. "
        "The current data is not strong enough for exact numeric projections."
    )


def _provisional_captain_candidate(
    analysis_store: dict[str, Any],
    requested_clubs: list[str],
    ranking_source_records: list[dict[str, Any]],
    availability_board: list[dict[str, Any]],
) -> dict[str, Any] | None:
    if not requested_clubs:
        return None

    club_members = [
        member
        for member in analysis_store.get("members", [])
        if member.get("name") and any(term in _member_club_terms(member) for term in requested_clubs)
    ]
    if not club_members:
        return None

    club_member_names = {member["name"] for member in club_members}
    candidates = [record for record in ranking_source_records if record.get("player_name") in club_member_names]
    if not candidates:
        return None

    availability_by_name = {item["player_name"]: item for item in availability_board}

    def _score(record: dict[str, Any]) -> tuple[int, int, int, int, int]:
        availability = availability_by_name.get(str(record.get("player_name") or ""), {})
        return (
            int(availability.get("matches_available", 0) or 0),
            int(record.get("runs", 0) or 0),
            int(record.get("wickets", 0) or 0),
            int(record.get("catches", 0) or 0),
            int(record.get("matches", 0) or 0),
        )

    return max(candidates, key=_score)


def _forecast_club_snippets(
    store: dict[str, Any],
    analysis_store: dict[str, Any],
    requested_clubs: list[str],
    include_player_names: bool = True,
) -> list[dict[str, Any]]:
    club_year_rows = list(analysis_store.get("club_year_stats") or [])
    club_summary_rows = list(analysis_store.get("club_summary_stats") or [])
    clubs = list(analysis_store.get("clubs") or [])
    target_clubs = []
    if requested_clubs:
        requested_set = set(requested_clubs)
        for club in clubs:
            names = {
                str(club.get("id") or "").strip(),
                str(club.get("name") or "").strip(),
                str(club.get("short_name") or "").strip(),
            }
            if any(_name_matches_requested(name, requested_set) for name in names):
                target_clubs.append(club)
    elif store.get("focus_club"):
        target_id = str(store["focus_club"].get("id") or "").strip().lower()
        target_clubs = [club for club in clubs if str(club.get("id") or "").strip().lower() == target_id]
    if not target_clubs:
        target_clubs = clubs[:5]

    snippets: list[dict[str, Any]] = []
    for club in target_clubs:
        club_id = str(club.get("id") or "").strip()
        club_name = str(club.get("name") or "").strip()
        if not club_id or not club_name:
            continue
        summary_row = next((row for row in club_summary_rows if str(row.get("club_id") or "").strip().lower() == club_id.lower()), {})
        year_rows = sorted(
            [row for row in club_year_rows if str(row.get("club_id") or "").strip().lower() == club_id.lower()],
            key=lambda item: str(item.get("season_year") or ""),
        )
        recent_year_rows = year_rows[-3:]
        year_parts = []
        for item in recent_year_rows:
            bits = [
                f"{item.get('season_year')}: matches={item.get('matches_played', 0)}, wins={item.get('matches_won', 0)}, "
                f"losses={item.get('matches_lost', 0)}, nr={item.get('matches_nr', 0)}, runs={item.get('total_runs', 0)}, "
                f"wickets={item.get('total_wickets', 0)}, catches={item.get('total_catches', 0)}"
            ]
            if include_player_names:
                bits.append(f"top_batter={item.get('top_batter', '')} ({item.get('top_batter_runs', 0)})")
            bits.append(
                f"milestones=25+:{item.get('scores_25_plus', 0)} 50+:{item.get('scores_50_plus', 0)} 100+:{item.get('scores_100_plus', 0)}"
            )
            year_parts.append(", ".join(bits))
        year_text = "; ".join(year_parts)
        top_batter_text = (
            f"top_batter: {summary_row.get('top_batter', '')} ({summary_row.get('top_batter_runs', 0)})"
            if include_player_names
            else "top_batter: hidden for club-only forecast"
        )
        snippets.append(
            {
                "kind": "forecast-club",
                "key": club_id,
                "text": "\n".join(
                    [
                        f"[forecast-club] {club_name}",
                        f"season: {club.get('season') or 'unknown'}",
                        f"overall: matches_played={summary_row.get('matches_played', 0)}, wins={summary_row.get('matches_won', 0)}, losses={summary_row.get('matches_lost', 0)}, nr={summary_row.get('matches_nr', 0)}, runs={summary_row.get('total_runs', 0)}, wickets={summary_row.get('total_wickets', 0)}, catches={summary_row.get('total_catches', 0)}, highest_score={summary_row.get('highest_score', '') or 'n/a'}",
                        top_batter_text,
                        f"milestones: 25+={summary_row.get('scores_25_plus', 0)}, 50+={summary_row.get('scores_50_plus', 0)}, 100+={summary_row.get('scores_100_plus', 0)}",
                        f"recent_years: {year_text or 'none'}",
                    ]
                ),
            }
        )
    return snippets


def _forecast_answer(question: str, store: dict[str, Any], history: list[dict[str, str]] | None = None) -> str | None:
    llm_status = get_llm_status()
    if not llm_status.get("available") or llm_status.get("provider") != "ollama" or not llm_status.get("model"):
        return None

    analysis_store = _global_analysis_store(store)
    effective_question = _contextualize_question(question, history, analysis_store["members"], analysis_store)
    matched_members = _matched_members(effective_question, analysis_store["members"])
    requested_clubs = _requested_club_terms(effective_question, store)
    club_only_request = bool(requested_clubs) and not matched_members
    summary = build_summary(analysis_store)
    overview_lines = [
        f"[forecast-overview] club={analysis_store['club'].get('name', 'Club')}",
        f"current_season={analysis_store['club'].get('season') or 'unknown'}",
        f"fixture_count={summary.get('fixture_count', 0)}",
        f"member_count={summary.get('member_count', 0)}",
        f"archive_count={summary.get('archive_count', 0)}",
        f"completed_matches={summary.get('completed_matches', 0)}",
        f"live_matches={summary.get('live_matches', 0)}",
    ]
    if club_only_request:
        overview_lines.extend(
            [
                "batting_leader=hidden for club-only forecast",
                "wicket_leader=hidden for club-only forecast",
                "fielding_leader=hidden for club-only forecast",
                "availability_leader=hidden for club-only forecast",
            ]
        )
    else:
        overview_lines.extend(
            [
                f"batting_leader={summary.get('batting_leader', '')} ({summary.get('batting_leader_runs', 0)})",
                f"wicket_leader={summary.get('wicket_leader', '')} ({summary.get('wicket_leader_count', 0)})",
                f"fielding_leader={summary.get('fielding_leader', '')} ({summary.get('fielding_leader_count', 0)})",
                f"availability_leader={summary.get('availability_leader', '')}",
            ]
        )
    snippets = [
        {
            "kind": "forecast-club-overview",
            "key": "overview",
            "text": "\n".join(overview_lines),
        }
    ]
    snippets.extend(_forecast_club_snippets(store, analysis_store, requested_clubs, include_player_names=not club_only_request))
    if matched_members and not club_only_request:
        snippets.extend(_forecast_rows_for_members(store, analysis_store, matched_members))
    elif not requested_clubs:
        snippets.extend(_forecast_rows_for_members(store, analysis_store, matched_members))
    selected_snippets = _rank_context_snippets(question, snippets, matched_members, llm_status)
    context = "\n\n".join(snippet["text"] for snippet in selected_snippets)

    system_prompt = (
        "You are a cricket performance forecaster using only the supplied stored context.\n"
        "Rules:\n"
        "- Do not guess beyond the supplied trends and summaries.\n"
        "- Make it clear that forecasts are projections, not certainties.\n"
        "- Do not invent exact future numbers, ranges, averages, or match counts unless those exact numbers are explicitly present in the supplied context.\n"
        "- Use the recent year-by-year club and player records to infer likely current and future performance.\n"
        "- If a player is named, focus on that player and mention club-specific differences only when they exist in the context.\n"
        "- If a club is named, focus on that club and do not introduce unrelated player names unless they are explicitly relevant to that club context.\n"
        "- If a club is named, answer at club level first and keep player details out unless the question explicitly asks about players.\n"
        "- If a club is not named, compare the key clubs and players in the supplied context.\n"
        "- For future years, project conservatively from the latest available year data and current availability patterns.\n"
        "- Mention the factors used: recent form, batting average, strike rate, wickets, catches, availability, and milestone counts.\n"
        "- If the data is too thin, say so plainly.\n"
        "- Keep the answer concise, practical, and directly actionable for the club."
    )

    try:
        response = httpx.post(
            f"{_ollama_base_url()}/api/chat",
            json={
                "model": llm_status["model"],
                "stream": False,
                "options": _llm_options("forecast"),
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {
                        "role": "user",
                        "content": (
                            f"Forecast question: {effective_question}\n\n"
                            f"Context:\n{context}\n\n"
                            "Return a grounded forecast for the club and/or player performance in current and future years."
                        ),
                    },
                ],
            },
            timeout=45.0,
        )
        response.raise_for_status()
        answer = response.json().get("message", {}).get("content", "").strip()
        if not answer:
            return _forecast_fallback_answer(effective_question, matched_members, requested_clubs, analysis_store)
        if _forecast_answer_needs_grounded_fallback(answer):
            logger.info(
                "forecast answer replaced with grounded fallback question=%s answer=%s",
                effective_question[:200],
                answer[:300],
            )
            return _forecast_fallback_answer(effective_question, matched_members, requested_clubs, analysis_store)
        if not _forecast_answer_is_grounded(answer, context, effective_question):
            logger.warning(
                "forecast answer rejected due to ungrounded numbers question=%s answer=%s",
                effective_question[:200],
                answer[:300],
            )
            return _forecast_fallback_answer(effective_question, matched_members, requested_clubs, analysis_store)
        if club_only_request:
            answer_lower = answer.lower()
            if any(
                member_name in answer_lower
                for member_name in (
                    token
                    for member in analysis_store.get("members", [])
                    for token in {
                        str(member.get("name") or "").strip().lower(),
                        str(member.get("full_name") or "").strip().lower(),
                    }
                    if token
                )
            ):
                logger.warning(
                    "forecast answer rejected due to club-only player leakage question=%s answer=%s",
                    effective_question[:200],
                    answer[:300],
                )
                return _forecast_fallback_answer(effective_question, matched_members, requested_clubs, analysis_store)
        return _redact_profanity(answer)
    except Exception:
        return _forecast_fallback_answer(effective_question, matched_members, requested_clubs, analysis_store)


def _prefer_heuristic_answer(question: str) -> bool:
    q = question.lower().strip()
    has_year = bool(re.search(r"\b(20\d{2})\b", q))
    total_score_terms = any(
        term in q
        for term in [
            "total score",
            "total runs",
            "overall score",
            "score total",
            "score across",
            "across all clubs",
        ]
    )
    captain_recommendation = "captain" in q and any(term in q for term in ["should", "who", "best", "recommend", "provisional"])
    year_score_followup = has_year and not total_score_terms and any(
        phrase in q
        for phrase in [
            "how was",
            "how did",
            "what was",
            "score in",
            "runs in",
            "score for",
            "performance in",
        ]
    )
    if year_score_followup:
        return True
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
        "total score",
        "overall score",
        "score across",
        "across all clubs",
        "batting average",
        "average",
        "strike rate",
        "economy",
        "bowling economy",
        "show stats",
        "search",
        "scorecard",
        "scorecards",
        "mention",
        "mentions",
        "follow",
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
        "captain",
        "batters",
        "batter",
        "next match",
        "who is available",
        "availability",
    ]
    return captain_recommendation or any(pattern in q for pattern in exact_patterns)


def _heuristic_answer(question: str, store: dict[str, Any], history: list[dict[str, str]] | None = None) -> dict[str, Any]:
    effective_question = _contextualize_question(question, history, store["members"], store)
    q = effective_question.lower().strip()
    summary = build_summary(store)
    fixtures = store["fixtures"]
    members = store["members"]
    analysis_store = _global_analysis_store(store)
    analysis_fixtures = analysis_store["fixtures"]
    analysis_members = analysis_store["members"]
    analysis_archives = canonical_archive_uploads(analysis_store["archive_uploads"])
    availability_board = build_availability_board(members, fixtures)
    player_stats = build_player_stats(fixtures, members)
    pending_player_stats = build_player_pending_stats(store.get("archive_uploads", []), members)
    global_availability_board = build_availability_board(analysis_members, analysis_fixtures)
    global_player_stats = build_player_stats(analysis_fixtures, analysis_members)
    global_pending_player_stats = build_player_pending_stats(analysis_archives, analysis_members)
    combined_records = _combined_player_records(members, player_stats, pending_player_stats, availability_board)
    global_combined_records = _combined_player_records(
        analysis_members,
        global_player_stats,
        global_pending_player_stats,
        global_availability_board,
    )
    next_match = next((match for match in fixtures if match["status"] != "Completed"), fixtures[0] if fixtures else {})
    matched_members = _matched_members(effective_question, analysis_members)
    matched_member = matched_members[0] if matched_members else None
    requested_clubs = _requested_club_terms(effective_question, store)
    requested_club_label = _requested_club_label(requested_clubs, store)
    club_member_names = {
        member["name"]
        for member in analysis_members
        if requested_clubs and any(term in _member_club_terms(member) for term in requested_clubs)
    }
    ranking_source_records = (
        [item for item in global_combined_records if item["player_name"] in club_member_names]
        if requested_clubs
        else global_combined_records
    )
    matched_stats = None
    matched_pending = None
    matched_entries: list[dict[str, Any]] = []
    matched_filtered_entries: list[dict[str, Any]] = []
    if matched_member:
        matched_stats = next(
            (item for item in global_player_stats if item["player_name"] == matched_member["name"]),
            {"player_name": matched_member["name"], "runs": 0, "wickets": 0, "catches": 0, "matches": 0},
        )
        matched_pending = next(
            (item for item in global_pending_player_stats if item["player_name"] == matched_member["name"]),
            {"player_name": matched_member["name"], "runs": 0, "wickets": 0, "catches": 0, "matches": 0},
        )
        matched_entries = _player_participation_entries(analysis_store, matched_member)
        matched_filtered_entries = _filter_entries_for_requested_clubs(matched_entries, requested_clubs)
    stored_matches = (matched_stats or {}).get("matches", 0) + (matched_pending or {}).get("matches", 0)
    stored_runs = (matched_stats or {}).get("runs", 0) + (matched_pending or {}).get("runs", 0)
    filtered_totals = _aggregate_entries(matched_filtered_entries) if matched_filtered_entries else {"matches": 0, "runs": 0, "balls": 0, "wickets": 0, "catches": 0}
    global_totals = _aggregate_entries(matched_entries) if matched_entries else {"matches": 0, "runs": 0, "balls": 0, "wickets": 0, "catches": 0}
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
    search_stats_intent = ("search" in q and "stats" in q) or "show stats" in q
    scorecard_mentions_intent = "scorecard" in q and any(term in q for term in ["mention", "mentions", "which", "show"])
    follow_intent = "follow" in q
    total_score_intent = any(
        term in q
        for term in [
            "total score",
            "total runs",
            "overall score",
            "runs total",
            "score total",
        ]
    ) or ("score" in q and "total" in q)
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
            combined_record = next((item for item in global_combined_records if item["player_name"] == matched_member["name"]), None)
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
            combined_record = next((item for item in global_combined_records if item["player_name"] == matched_member["name"]), None)
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
    elif matched_member and search_stats_intent:
        display_name = _display_name(matched_member)
        if requested_clubs:
            scope_text = f" for {requested_club_label}"
            answer = (
                f"{display_name}'s stats{scope_text}: {filtered_totals['matches']} match(es), {filtered_totals['runs']} runs, "
                f"{filtered_totals['wickets']} wickets, {filtered_totals['catches']} catches."
            )
        else:
            clubs = sorted(
                {
                    str(club.get("club_name") or "").strip()
                    for club in matched_member.get("club_memberships", []) or []
                    if str(club.get("club_name") or "").strip()
                }
            )
            clubs_text = ", ".join(clubs) if clubs else "no club memberships stored"
            answer = (
                f"{display_name}'s stats across all clubs: {stored_matches} match(es), {stored_runs} runs, "
                f"{(matched_stats or {}).get('wickets', 0) + (matched_pending or {}).get('wickets', 0)} wickets, "
                f"{(matched_stats or {}).get('catches', 0) + (matched_pending or {}).get('catches', 0)} catches. "
                f"Clubs: {clubs_text}."
            )
    elif matched_member and scorecard_mentions_intent:
        display_name = _display_name(matched_member)
        archive_mentions = [
            item
            for item in matched_entries
            if str(item.get("key", "")).startswith("archive:")
            and (not query_year or _date_matches(item.get("date", ""), query_year, query_month))
        ]
        if requested_clubs:
            archive_mentions = [
                item
                for item in matched_filtered_entries
                if str(item.get("key", "")).startswith("archive:")
                and (not query_year or _date_matches(item.get("date", ""), query_year, query_month))
            ]
        if archive_mentions:
            mentions = []
            for item in archive_mentions[:5]:
                date_label = item.get("date", "") or "unknown date"
                opponent = item.get("opponent", "") or "unknown opponent"
                club_label = item.get("club_label", "") or item.get("team_label", "") or "unknown club"
                mentions.append(f"{date_label} vs {opponent} ({club_label})")
            scope = f" for {requested_club_label}" if requested_clubs else " across all clubs"
            if query_year:
                scope += f" in {query_year}"
            answer = f"I found {len(archive_mentions)} scorecard(s){scope} mentioning {display_name}: " + "; ".join(mentions) + "."
        else:
            answer = f"I could not find any stored scorecards mentioning {display_name}."
    elif matched_member and follow_intent:
        display_name = _display_name(matched_member)
        answer = (
            f"Use the Follow button on {display_name}'s profile to add them to your watchlist. "
            "Chat can read the stored data, but following a player is saved from the player or clubs page."
        )
    elif matched_member and total_score_intent:
        display_name = _display_name(matched_member)
        scope_entries = matched_filtered_entries if requested_clubs else matched_entries
        if query_year or query_month:
            scope_entries = [item for item in scope_entries if _date_matches(item.get("date", ""), query_year, query_month)]
        scoped_totals = _aggregate_entries(scope_entries) if scope_entries else {"matches": 0, "runs": 0, "balls": 0, "wickets": 0, "catches": 0}
        if scoped_totals["matches"]:
            scope_bits = []
            if requested_clubs:
                scope_bits.append(f"for {requested_club_label}")
            else:
                scope_bits.append("across all clubs")
            if query_year:
                scope_bits.append(f"in {query_year}")
            if query_month:
                month_label = next(name.title() for name, value in MONTH_NAMES.items() if value == query_month)
                scope_bits.append(f"in {month_label}")
            scope_text = " ".join(scope_bits)
            answer = (
                f"{display_name}'s total score {scope_text} is {scoped_totals['runs']} runs across "
                f"{scoped_totals['matches']} confirmed match(es)."
            )
        else:
            answer = f"I could not find a scored match for {display_name} in the stored records."
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
            if query_year or query_month:
                scope_entries = [item for item in matched_entries if _date_matches(item.get("date", ""), query_year, query_month)]
                scoped_totals = _aggregate_entries(scope_entries) if scope_entries else {"matches": 0, "runs": 0, "balls": 0, "wickets": 0, "catches": 0}
                if scoped_totals["matches"]:
                    scope_bits = ["across all clubs"]
                    if query_year:
                        scope_bits.append(f"in {query_year}")
                    if query_month:
                        month_label = next(name.title() for name, value in MONTH_NAMES.items() if value == query_month)
                        scope_bits.append(f"in {month_label}")
                    scope_text = " ".join(scope_bits)
                    answer = (
                        f"{display_name} has {scoped_totals['runs']} runs {scope_text}, with "
                        f"{scoped_totals['wickets']} wickets and {scoped_totals['catches']} catches across {scoped_totals['matches']} confirmed match(es)."
                    )
                else:
                    answer = f"I could not find a scored match for {display_name} in the stored records."
            else:
                answer = (
                    f"{display_name} has {stored_runs} runs across {stored_matches} confirmed match(es) in the stored records. "
                    f"Live fixture records account for {matched_stats['runs']} runs, {matched_stats['wickets']} wickets, and {matched_stats['catches']} catches; "
                    f"confirmed historical scorecards account for {matched_pending['runs']} additional runs from {matched_pending['matches']} match(es)."
                )
    elif matched_member and any(keyword in q for keyword in ["availability", "available", "maybe", "unavailable"]):
        analysis_store = _global_analysis_store(store)
        display_name = _display_name(matched_member)
        club_availability = _player_availability_by_club(analysis_store, matched_member["name"])
        if club_availability:
            known_clubs = {
                str(club.get("name") or club.get("short_name") or "").strip()
                for club in analysis_store.get("clubs", [])
                if str(club.get("name") or club.get("short_name") or "").strip()
            }
            seen_clubs = {str(item["club_name"]).strip() for item in club_availability if str(item["club_name"]).strip()}
            parts: list[str] = []
            for item in club_availability:
                club_label = item["club_name"]
                if int(item["available"]) > 0:
                    parts.append(f"{int(item['available'])} game{'s' if int(item['available']) != 1 else ''} available for {club_label}")
                if int(item["maybe"]) > 0:
                    parts.append(f"{int(item['maybe'])} game{'s' if int(item['maybe']) != 1 else ''} maybe for {club_label}")
                if int(item["unavailable"]) > 0:
                    parts.append(f"{int(item['unavailable'])} game{'s' if int(item['unavailable']) != 1 else ''} unavailable for {club_label}")
            if not parts:
                parts.append("no recorded availability yet")
            missing_clubs = [club_name for club_name in sorted(known_clubs) if club_name not in seen_clubs]
            if missing_clubs:
                parts.append("no recorded availability yet for " + ", ".join(missing_clubs))
            answer = (
                f"{display_name}'s 2026 availability across all clubs is "
                + "; ".join(parts)
                + "."
            )
        else:
            answer = f"No fixture availability is stored yet for {display_name} across the stored clubs."
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
        if any(term in q for term in ["should", "who", "best", "recommend", "provisional"]):
            candidate = _provisional_captain_candidate(
                analysis_store,
                requested_clubs,
                ranking_source_records,
                global_availability_board,
            )
            if candidate:
                candidate_name = _display_name_for_name(str(candidate.get("player_name") or ""), analysis_members)
                if requested_clubs:
                    answer = (
                        f"A provisional captain recommendation for {requested_club_label} in 2026 is {candidate_name}. "
                        "That suggestion is based on availability and overall contribution in the stored records."
                    )
                else:
                    answer = (
                        f"A provisional captain recommendation from the stored records is {candidate_name}. "
                        "That suggestion is based on availability and overall contribution in the stored records."
                    )
            elif requested_clubs:
                answer = (
                    f"I could not find enough stored data to recommend a captain for {requested_club_label} yet. "
                    "Use the Match Setup form to lock in captain, toss, venue, and scorer details."
                )
            else:
                answer = (
                    f"{summary['matches_without_captain']} fixtures still need a club captain assigned. "
                    "Use the Match Setup form to lock in captain, toss, venue, and scorer details."
                )
        else:
            answer = (
                f"{summary['matches_without_captain']} fixtures still need a club captain assigned. "
                "Use the Match Setup form to lock in captain, toss, venue, and scorer details."
            )
    elif "score" in q or "scorecard" in q:
        completed = [match for match in fixtures if match["status"] == "Completed" or match["heartlake_score"]]
        if completed:
            latest = completed[-1]
            answer = (
                f"The latest scored match is {latest['date_label']} vs {latest['opponent']}: "
                f"Club {latest['heartlake_score'] or '--'} and Opponent {latest['opponent_score'] or '--'}. "
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
            f"There are {summary['commentary_count']} saved text and voice scoring entries. "
            "Voice scoring is stored as transcript text, so it can be persisted with each match locally."
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
    llm_status = get_llm_status()
    effective_question = _contextualize_question(question, history, store["members"], store)
    moderated = _moderated_prompt_response(effective_question)
    if moderated:
        moderated["session_id"] = session_id or ""
        moderated["llm"] = llm_status
        logger.info(
            "chat.answer source=%s mode=%s question=%s answer=%s",
            moderated["source_provider"],
            moderated.get("mode", ""),
            question[:200],
            str(moderated.get("answer", ""))[:300],
        )
        return moderated
    if _prediction_question_intent(effective_question):
        forecast = _forecast_answer(question, store, history=history)
        if forecast:
            model_name = str(llm_status.get("model") or "Ollama").strip()
            result = {
                "answer": forecast,
                "mode": "forecast",
                "session_id": session_id or "",
                "llm": llm_status,
                "source_provider": "ollama",
                "source_label": f"Ollama: {model_name}",
            }
            logger.info(
                "chat.answer source=%s mode=%s question=%s answer=%s",
                result["source_provider"],
                result.get("mode", ""),
                question[:200],
                str(result.get("answer", ""))[:300],
            )
            return result
        heuristic_forecast = _heuristic_answer(question, store, history=history)
        result = {
            **heuristic_forecast,
            "session_id": session_id or "",
            "llm": llm_status,
            "source_provider": "heuristic",
            "source_label": "Heuristic fallback",
        }
        logger.info(
            "chat.answer source=%s mode=%s question=%s answer=%s",
            result["source_provider"],
            result.get("mode", ""),
            question[:200],
            str(result.get("answer", ""))[:300],
        )
        return result
    prefer_grounded = _prefer_heuristic_answer(effective_question)
    grounded = _heuristic_answer(question, store, history=history) if prefer_grounded else None
    if grounded:
        result = {
            **grounded,
            "session_id": session_id or "",
            "llm": llm_status,
            "source_provider": "heuristic",
            "source_label": "Heuristic fallback",
        }
        logger.info(
            "chat.answer source=%s mode=%s question=%s answer=%s",
            result["source_provider"],
            result.get("mode", ""),
            question[:200],
            str(result.get("answer", ""))[:300],
        )
        return result
    grounded_facts = ""
    rag_answer = _rag_answer(question, store, grounded_facts=grounded_facts, history=history)
    if rag_answer:
        model_name = str(llm_status.get("model") or "Ollama").strip()
        result = {
            "answer": rag_answer,
            "mode": "grounded-rag" if grounded_facts else "rag",
            "session_id": session_id or "",
            "llm": llm_status,
            "source_provider": "ollama",
            "source_label": f"Ollama: {model_name}",
        }
        logger.info(
            "chat.answer source=%s mode=%s question=%s answer=%s",
            result["source_provider"],
            result.get("mode", ""),
            question[:200],
            str(result.get("answer", ""))[:300],
        )
        return result
    fallback = _heuristic_answer(question, store, history=history)
    result = {
        **fallback,
        "session_id": session_id or "",
        "llm": llm_status,
        "source_provider": "heuristic",
        "source_label": "Heuristic fallback",
    }
    logger.info(
        "chat.answer source=%s mode=%s question=%s answer=%s",
        result["source_provider"],
        result.get("mode", ""),
        question[:200],
        str(result.get("answer", ""))[:300],
    )
    return result
