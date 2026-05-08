import base64
import hashlib
import json
import logging
import os
import re
import shutil
import sqlite3
import subprocess
import uuid
from collections import Counter, defaultdict
from datetime import datetime, timezone
from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

import httpx

try:
    from llm_registry import prompt_documents, prompt_manifest, build_prompt
except ModuleNotFoundError:
    from app.llm_registry import prompt_documents, prompt_manifest, build_prompt


BASE_DIR = Path(__file__).resolve().parent
REPO_DIR = BASE_DIR.parent
DATA_ROOT = Path(os.getenv("CRICKETCLUBAPP_DATA_ROOT", str(BASE_DIR / "data")))
DATA_FILE = Path(os.getenv("CRICKETCLUBAPP_SEED_FILE", str(BASE_DIR / "data" / "seed.json")))
CANONICAL_DATABASE_NAME = "cricketclubapp.db"
DATABASE_FILE = Path(os.getenv("CRICKETCLUBAPP_DATABASE_FILE", str(DATA_ROOT / CANONICAL_DATABASE_NAME)))
CACHE_FILE = Path(os.getenv("CRICKETCLUBAPP_CACHE_FILE", str(DATA_ROOT / "store_cache.json")))
DASHBOARD_CACHE_FILE = Path(os.getenv("CRICKETCLUBAPP_DASHBOARD_CACHE_FILE", str(DATA_ROOT / "dashboard_cache.json")))
UPLOAD_DIR = Path(os.getenv("CRICKETCLUBAPP_UPLOAD_DIR", str(BASE_DIR / "uploads")))
DUPLICATE_DIR = Path(os.getenv("CRICKETCLUBAPP_DUPLICATE_DIR", str(DATA_ROOT / "duplicates")))
LEGACY_UPLOAD_DIR = DATA_ROOT / "uploads"
VISION_OCR_SCRIPT = REPO_DIR / "tools" / "vision_ocr.swift"
DATA_ROOT.mkdir(parents=True, exist_ok=True)
UPLOAD_DIR.mkdir(exist_ok=True)
DUPLICATE_DIR.mkdir(exist_ok=True)
if LEGACY_UPLOAD_DIR != UPLOAD_DIR:
    LEGACY_UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".heic", ".heif", ".webp"}
CURRENT_ARCHIVE_YEAR = "2025"
CURRENT_ARCHIVE_SEASON_LABEL = f"{CURRENT_ARCHIVE_YEAR} Season"
ARCHIVE_METADATA_FIELDS = (
    ("kMDItemContentCreationDate", "metadata-content-created"),
    ("kMDItemFSCreationDate", "metadata-file-created"),
    ("kMDItemFSContentChangeDate", "metadata-file-updated"),
)

DEFAULT_MEMBER_FIELDS = {
    "full_name": "",
    "team_name": "Club",
    "aliases": [],
    "gender": "",
    "phone": "",
    "email": "",
    "picture_url": "",
    "jersey_number": "",
    "notes": "",
    "batting_style": "",
    "bowling_style": "",
}

DEFAULT_VIEWER_PROFILE = {
    "id": "local-viewer",
    "display_name": "",
    "mobile": "",
    "email": "",
    "primary_club_id": "club-heartlake",
    "primary_club_name": "Club",
    "selected_season_year": str(datetime.utcnow().year),
    "followed_player_names": [],
}

VISION_LLM_MODEL_PREFERENCES = [
    "qwen3-vl:8b",
    "qwen3-vl:latest",
    "qwen3-vl:4b",
    "qwen3-vl:2b",
    "qwen3-vl",
    "qwen2.5vl:7b",
    "qwen2.5vl:latest",
    "gemma3:12b",
    "gemma3:4b",
    "llama3.2-vision",
]

TEXT_LLM_MODEL_PREFERENCES = [
    "llama3.2:latest",
    "llama3.1:8b",
    "mistral:latest",
    "phi4:latest",
    "qwen2.5:latest",
    "qwen2.5:7b",
]

logger = logging.getLogger("CricketClubStore")

if not logger.handlers:
    app_env = str(
        os.getenv("APP_ENV")
        or os.getenv("ENVIRONMENT")
        or os.getenv("AZURE_ENVIRONMENT")
        or os.getenv("WEBSITE_INSTANCE_ID")
        or "local"
    ).strip().lower()
    log_level = logging.DEBUG if app_env in {"local", "dev", "development", "debug", ""} else logging.ERROR
    logger.setLevel(log_level)


_STORE_CACHE_SIGNATURE: tuple[int, int] | None = None
_STORE_CACHE_PAYLOAD: dict[str, Any] | None = None
_DASHBOARD_CACHE: dict[tuple[str, str, str], dict[str, Any]] = {}


def _database_signature() -> tuple[int, int]:
    try:
        stat_result = DATABASE_FILE.stat()
        return stat_result.st_mtime_ns, stat_result.st_size
    except FileNotFoundError:
        return 0, 0


def _store_cache_signature(store: dict[str, Any]) -> str:
    signature = store.get("_cache_signature")
    if isinstance(signature, str) and signature:
        return signature
    return "unknown-store"


def now_iso() -> str:
    return datetime.utcnow().isoformat(timespec="seconds") + "Z"


def member_initials(name: str) -> str:
    parts = [part[0] for part in name.split() if part]
    return "".join(parts[:2]).upper() or "HC"


def parse_score_pair(value: str) -> tuple[str, str]:
    if not value:
        return "", ""
    match = re.match(r"\s*(\d+)\s*/\s*(\d+)\s*$", str(value))
    if not match:
        return "", ""
    return match.group(1), match.group(2)


def compose_score(runs: str, wickets: str) -> str:
    if runs and wickets:
        return f"{runs}/{wickets}"
    if runs:
        return runs
    return ""


def _season_label_for_year(year: str) -> str:
    clean = str(year or "").strip()
    return f"{clean} Season" if clean else ""


def fixture_season_year(fixture: dict[str, Any]) -> str:
    explicit = str(fixture.get("season_year") or "").strip()
    if re.match(r"20\d{2}$", explicit):
        return explicit
    explicit_label = str(fixture.get("season") or "").strip()
    match = re.search(r"(20\d{2})", explicit_label)
    if match:
        return match.group(1)
    date_value = str(fixture.get("date") or "").strip()
    if re.match(r"20\d{2}", date_value):
        return date_value[:4]
    return ""


def fixture_season_label(fixture: dict[str, Any]) -> str:
    explicit = str(fixture.get("season") or "").strip()
    if explicit:
        return explicit
    return _season_label_for_year(fixture_season_year(fixture))


def club_season_year(club: dict[str, Any]) -> str:
    season_label = str(club.get("season") or "").strip()
    match = re.search(r"(20\d{2})", season_label)
    if match:
        return match.group(1)
    return str(datetime.utcnow().year)


def _current_season_label() -> str:
    return f"{datetime.utcnow().year} Season"


def _dashboard_season_years(store: dict[str, Any]) -> list[str]:
    years: set[str] = set()
    current_year = int(datetime.utcnow().year)
    for fixture in store.get("fixtures", []):
        season_year = fixture_season_year(fixture)
        if season_year and season_year.isdigit() and int(season_year) <= current_year:
            years.add(season_year)
    for archive in store.get("archive_uploads", []):
        archive_year = str(archive.get("archive_year", "") or "").strip()
        archive_date = str(archive.get("archive_date", "") or "").strip()
        if re.match(r"20\d{2}$", archive_year) and int(archive_year) <= current_year:
            years.add(archive_year)
        elif re.match(r"20\d{2}", archive_date) and int(archive_date[:4]) <= current_year:
            years.add(archive_date[:4])
    if not years:
        years.add(str(current_year))
    return sorted(years, reverse=True)


def _resolve_dashboard_season_year(store: dict[str, Any], requested: str = "") -> str:
    available_years = _dashboard_season_years(store)
    current_year = str(datetime.utcnow().year)
    requested_year = str(requested or store.get("viewer_profile", {}).get("selected_season_year") or "").strip()
    if requested_year and requested_year in available_years:
        return requested_year
    if current_year in available_years:
        return current_year
    return available_years[0] if available_years else current_year


def _display_club_season(store: dict[str, Any], club: dict[str, Any]) -> str:
    fixtures = _club_owned_fixtures(store, club)
    fixture_years = sorted(
        {
            fixture_season_year(fixture)
            for fixture in fixtures
            if fixture_season_year(fixture)
        }
    )
    if fixture_years:
        return f"{fixture_years[-1]} Season"
    season_label = str(club.get("season") or "").strip()
    match = re.search(r"(20\d{2})", season_label)
    if match and match.group(1) == str(datetime.utcnow().year):
        return season_label
    return _current_season_label()


def _parse_mdls_datetime(raw_value: str) -> datetime | None:
    text = str(raw_value or "").strip()
    if not text or text == "(null)":
        return None
    for pattern in ("%Y-%m-%d %H:%M:%S %z", "%Y-%m-%d %H:%M:%S"):
        try:
            parsed = datetime.strptime(text, pattern)
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return parsed.astimezone(timezone.utc)
        except ValueError:
            continue
    return None


def _iso_datetime(value: datetime) -> str:
    return value.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _iso_date_from_datetime(value: datetime) -> str:
    return value.astimezone(timezone.utc).strftime("%Y-%m-%d")


def image_datetime_from_metadata(path: Path) -> tuple[str, str]:
    if not path.is_file():
        return "", ""
    if shutil.which("mdls"):
        for field_name, source_name in ARCHIVE_METADATA_FIELDS:
            try:
                result = subprocess.run(
                    ["mdls", "-raw", "-name", field_name, str(path)],
                    check=True,
                    capture_output=True,
                    text=True,
                    timeout=4,
                )
            except Exception:
                continue
            parsed = _parse_mdls_datetime(result.stdout)
            if parsed:
                return _iso_datetime(parsed), source_name
    try:
        stat = path.stat()
        fallback_dt = datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc)
        return _iso_datetime(fallback_dt), "filesystem-modified"
    except Exception:
        return "", ""


def _normalize_date_parts(day: int, month: int, year: int) -> str:
    if year < 100:
        year += 2000
    try:
        parsed = datetime(year, month, day, tzinfo=timezone.utc)
    except ValueError:
        return ""
    if parsed.year < 2000 or parsed.year > 2035:
        return ""
    return parsed.strftime("%Y-%m-%d")


def force_archive_year(value: str, year: str = CURRENT_ARCHIVE_YEAR) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    match = re.match(r"(\d{4})-(\d{2})-(\d{2})$", text)
    if not match:
        return text
    month = int(match.group(2))
    day = int(match.group(3))
    return _normalize_date_parts(day, month, int(year)) or ""


def parse_scorecard_date_text(text: str) -> str:
    raw = str(text or "").strip()
    if not raw:
        return ""

    label_patterns = [
        r"date[^0-9a-zA-Z]{0,12}(\d{1,2})[/-](\d{1,2})[/-](\d{2,4})",
        r"date[^0-9a-zA-Z]{0,12}(\d{4})[/-](\d{1,2})[/-](\d{1,2})",
    ]
    for pattern in label_patterns:
        match = re.search(pattern, raw, flags=re.IGNORECASE)
        if not match:
            continue
        parts = match.groups()
        values = [int(part) for part in parts]
        if len(parts[0]) == 4:
            iso = _normalize_date_parts(values[2], values[1], values[0])
        else:
            iso = _normalize_date_parts(values[0], values[1], values[2])
        if iso:
            return iso

    month_name_match = re.search(
        r"date[^0-9a-zA-Z]{0,12}(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\s+(\d{1,2}),?\s+(\d{2,4})",
        raw,
        flags=re.IGNORECASE,
    )
    if month_name_match:
        month_lookup = {
            "jan": 1,
            "feb": 2,
            "mar": 3,
            "apr": 4,
            "may": 5,
            "jun": 6,
            "jul": 7,
            "aug": 8,
            "sep": 9,
            "oct": 10,
            "nov": 11,
            "dec": 12,
        }
        month = month_lookup[month_name_match.group(1).lower()[:3]]
        iso = _normalize_date_parts(int(month_name_match.group(2)), month, int(month_name_match.group(3)))
        if iso:
            return iso

    iso_match = re.search(r"\b(20\d{2})[/-](\d{1,2})[/-](\d{1,2})\b", raw)
    if iso_match:
        iso = _normalize_date_parts(int(iso_match.group(3)), int(iso_match.group(2)), int(iso_match.group(1)))
        if iso:
            return iso

    return ""


def refresh_archive_dates(item: dict[str, Any], scorecard_text: str = "") -> dict[str, Any]:
    normalized = dict(item)
    scorecard_date = str(normalized.get("scorecard_date") or "").strip()
    explicit_archive_date = str(normalized.get("archive_date") or "").strip()
    explicit_archive_year = str(normalized.get("archive_year") or "").strip()
    explicit_archive_source = str(normalized.get("archive_date_source") or "").strip()
    explicit_season = str(normalized.get("season") or "").strip()
    if scorecard_text:
        extracted_date = parse_scorecard_date_text(scorecard_text)
        if extracted_date:
            scorecard_date = extracted_date
            normalized["scorecard_date"] = extracted_date

    photo_taken_at = str(normalized.get("photo_taken_at") or "").strip()
    photo_date_source = str(normalized.get("photo_date_source") or "").strip()
    resolved_path = resolve_existing_upload_path(normalized.get("file_path", ""), normalized.get("file_name", ""))
    file_path = resolved_path or Path(normalized.get("file_path") or "")
    if resolved_path:
        normalized["file_path"] = str(resolved_path)
        normalized["preview_url"] = f"/uploads/{resolved_path.name}"
    if file_path.is_file() and not photo_taken_at:
        photo_taken_at, photo_date_source = image_datetime_from_metadata(file_path)
        if photo_taken_at:
            normalized["photo_taken_at"] = photo_taken_at
            normalized["photo_date_source"] = photo_date_source

    preferred_date = ""
    preferred_source = ""
    preferred_year = ""
    preferred_season = ""

    if re.match(r"20\d{2}-\d{2}-\d{2}$", scorecard_date):
        preferred_date = scorecard_date
        preferred_source = "scorecard"
        preferred_year = scorecard_date[:4]
        preferred_season = f"{preferred_year} Season"
    elif not preferred_date and re.match(r"20\d{2}-\d{2}-\d{2}$", photo_taken_at[:10] if photo_taken_at else ""):
        preferred_date = photo_taken_at[:10]
        preferred_source = photo_date_source or "metadata"
        preferred_year = photo_taken_at[:4]
        preferred_season = f"{preferred_year} Season"
    elif re.match(r"20\d{2}-\d{2}-\d{2}$", explicit_archive_date):
        preferred_date = explicit_archive_date
        preferred_year = explicit_archive_year or explicit_archive_date[:4]
        preferred_source = explicit_archive_source or "manual-season"
        preferred_season = explicit_season or f"{preferred_year} Season"
    elif re.match(r"20\d{2}$", explicit_archive_year):
        preferred_year = explicit_archive_year
        preferred_season = explicit_season or f"{preferred_year} Season"
    elif not preferred_source:
        preferred_source = "assumed-2025-season"
        preferred_year = CURRENT_ARCHIVE_YEAR
        preferred_season = CURRENT_ARCHIVE_SEASON_LABEL

    normalized["archive_date"] = preferred_date
    normalized["archive_year"] = preferred_year or CURRENT_ARCHIVE_YEAR
    normalized["archive_date_source"] = preferred_source
    normalized["season"] = preferred_season or CURRENT_ARCHIVE_SEASON_LABEL
    return normalized


def default_match_details() -> dict[str, str]:
    return {
        "venue": "Club Grounds",
        "match_type": "T20 Friendly",
        "scheduled_time": "10:00 AM",
        "overs": "20",
        "toss_winner": "",
        "toss_decision": "",
        "weather": "",
        "umpires": "",
        "scorer": "",
        "whatsapp_thread": "",
        "notes": "",
    }


def default_scorecard(result: str = "TBD") -> dict[str, str]:
    return {
        "heartlake_runs": "",
        "heartlake_wickets": "",
        "heartlake_overs": "",
        "opponent_runs": "",
        "opponent_wickets": "",
        "opponent_overs": "",
        "result": result or "TBD",
        "live_summary": "",
    }


def _scorebook_team_defaults(fixture: dict[str, Any]) -> tuple[str, str]:
    heartlake_team = str(fixture.get("club_name") or fixture.get("team_name") or fixture.get("club_short_name") or "Club").strip() or "Club"
    opponent_team = str(fixture.get("visiting_team") or fixture.get("opponent") or "Opponent").strip() or "Opponent"
    return heartlake_team, opponent_team


def default_innings_scorebook(
    inning_number: int,
    batting_team: str,
    bowling_team: str,
    overs_limit: int | str = 20,
    target_runs: int | None = None,
) -> dict[str, Any]:
    try:
        overs_value = max(1, int(float(overs_limit or 20)))
    except (TypeError, ValueError):
        overs_value = 20
    return {
        "inning_number": inning_number,
        "batting_team": str(batting_team or "").strip(),
        "bowling_team": str(bowling_team or "").strip(),
        "overs_limit": overs_value,
        "status": "Not started",
        "target_runs": int(target_runs) if target_runs else None,
        "batters": [{"slot_number": slot, "player_name": ""} for slot in range(1, 12)],
        "bowlers": [{"slot_number": slot, "player_name": ""} for slot in range(1, 12)],
        "balls": [],
    }


def default_match_scorebook(fixture: dict[str, Any]) -> dict[str, Any]:
    heartlake_team, opponent_team = _scorebook_team_defaults(fixture)
    overs_limit = str((fixture.get("details", {}) or {}).get("overs") or "20").strip() or "20"
    return {
        "innings": [
            default_innings_scorebook(1, heartlake_team, opponent_team, overs_limit),
            default_innings_scorebook(2, opponent_team, heartlake_team, overs_limit),
        ]
    }


def _normalize_scorebook_slots(entries: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    raw_entries = entries if isinstance(entries, list) else []
    for slot in range(1, 12):
        raw = raw_entries[slot - 1] if slot - 1 < len(raw_entries) and isinstance(raw_entries[slot - 1], dict) else {}
        normalized.append(
            {
                "slot_number": slot,
                "player_name": re.sub(r"\s+", " ", str(raw.get("player_name", "") or "").strip()),
            }
        )
    return normalized


def normalize_scorebook_ball(entry: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(entry)
    normalized.setdefault("id", str(uuid.uuid4())[:8])
    normalized.setdefault("over_number", 1)
    normalized.setdefault("ball_number", 1)
    normalized.setdefault("striker", "")
    normalized.setdefault("non_striker", "")
    normalized.setdefault("bowler", "")
    normalized.setdefault("runs_bat", 0)
    normalized.setdefault("extras_type", "none")
    normalized.setdefault("extras_runs", 0)
    normalized.setdefault("wicket", False)
    normalized.setdefault("wicket_type", "")
    normalized.setdefault("wicket_player", "")
    normalized.setdefault("fielder", "")
    normalized.setdefault("commentary", "")
    normalized.setdefault("created_at", now_iso())
    normalized["over_number"] = max(1, int(normalized.get("over_number", 1) or 1))
    normalized["ball_number"] = max(1, int(normalized.get("ball_number", 1) or 1))
    normalized["runs_bat"] = max(0, int(normalized.get("runs_bat", 0) or 0))
    normalized["extras_runs"] = max(0, int(normalized.get("extras_runs", 0) or 0))
    normalized["wicket"] = bool(normalized.get("wicket"))
    normalized["extras_type"] = str(normalized.get("extras_type", "none") or "none").strip().lower()
    if normalized["extras_type"] not in {"none", "wide", "no_ball", "bye", "leg_bye"}:
        normalized["extras_type"] = "none"
    for key in ["striker", "non_striker", "bowler", "wicket_type", "wicket_player", "fielder", "commentary"]:
        normalized[key] = re.sub(r"\s+", " ", str(normalized.get(key, "") or "").strip())
    if not normalized["wicket"]:
        normalized["wicket_type"] = ""
        normalized["wicket_player"] = ""
        normalized["fielder"] = ""
    return normalized


def normalize_innings_scorebook(entry: dict[str, Any], default_inning: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(default_inning)
    normalized.update(dict(entry or {}))
    normalized["inning_number"] = int(normalized.get("inning_number", default_inning.get("inning_number", 1)) or 1)
    normalized["batting_team"] = re.sub(r"\s+", " ", str(normalized.get("batting_team", "") or "").strip())
    normalized["bowling_team"] = re.sub(r"\s+", " ", str(normalized.get("bowling_team", "") or "").strip())
    try:
        normalized["overs_limit"] = max(1, int(float(normalized.get("overs_limit", default_inning.get("overs_limit", 20)) or 20)))
    except (TypeError, ValueError):
        normalized["overs_limit"] = int(default_inning.get("overs_limit", 20) or 20)
    target_runs = normalized.get("target_runs")
    normalized["target_runs"] = int(target_runs) if str(target_runs or "").strip() else None
    normalized["status"] = str(normalized.get("status", "Not started") or "Not started").strip() or "Not started"
    normalized["batters"] = _normalize_scorebook_slots(normalized.get("batters"))
    normalized["bowlers"] = _normalize_scorebook_slots(normalized.get("bowlers"))
    normalized["balls"] = [normalize_scorebook_ball(item) for item in normalized.get("balls", []) if isinstance(item, dict)]
    return normalized


def normalize_match_scorebook(scorebook: dict[str, Any] | None, fixture: dict[str, Any]) -> dict[str, Any]:
    default_scorebook = default_match_scorebook(fixture)
    innings = scorebook.get("innings", []) if isinstance(scorebook, dict) else []
    normalized_innings = []
    for index in range(2):
        raw = innings[index] if index < len(innings) and isinstance(innings[index], dict) else {}
        normalized_innings.append(normalize_innings_scorebook(raw, default_scorebook["innings"][index]))
    return {"innings": normalized_innings}


def _delivery_is_legal(ball: dict[str, Any]) -> bool:
    return str(ball.get("extras_type", "none") or "none") not in {"wide", "no_ball"}


def _over_string_from_legal_balls(legal_balls: int) -> str:
    overs = legal_balls // 6
    balls = legal_balls % 6
    return f"{overs}.{balls}"


def summarize_innings_scorebook(innings: dict[str, Any]) -> dict[str, Any]:
    batters = {
        item["player_name"]: {"player_name": item["player_name"], "runs": 0, "balls": 0, "fours": 0, "sixes": 0, "status": "not_batted"}
        for item in innings.get("batters", [])
        if item.get("player_name")
    }
    bowlers = {
        item["player_name"]: {"player_name": item["player_name"], "legal_balls": 0, "maidens": 0, "runs_conceded": 0, "wickets": 0}
        for item in innings.get("bowlers", [])
        if item.get("player_name")
    }
    over_bowler_runs: dict[tuple[str, int], int] = defaultdict(int)
    total_runs = 0
    wickets = 0
    extras = 0
    legal_balls = 0

    for ball in innings.get("balls", []):
        striker = str(ball.get("striker", "") or "").strip()
        bowler = str(ball.get("bowler", "") or "").strip()
        wicket_player = str(ball.get("wicket_player", "") or "").strip()
        runs_bat = int(ball.get("runs_bat", 0) or 0)
        extras_runs = int(ball.get("extras_runs", 0) or 0)
        extras_type = str(ball.get("extras_type", "none") or "none")
        total_runs += runs_bat + extras_runs
        extras += extras_runs
        if _delivery_is_legal(ball):
            legal_balls += 1
        if striker:
            batter = batters.setdefault(
                striker,
                {"player_name": striker, "runs": 0, "balls": 0, "fours": 0, "sixes": 0, "status": "not_batted"},
            )
            batter["runs"] += runs_bat
            batter["status"] = "batting"
            if _delivery_is_legal(ball):
                batter["balls"] += 1
            if runs_bat == 4:
                batter["fours"] += 1
            if runs_bat == 6:
                batter["sixes"] += 1
        if bowler:
            bowler_bucket = bowlers.setdefault(
                bowler,
                {"player_name": bowler, "legal_balls": 0, "maidens": 0, "runs_conceded": 0, "wickets": 0},
            )
            bowler_bucket["runs_conceded"] += runs_bat + extras_runs
            if _delivery_is_legal(ball):
                bowler_bucket["legal_balls"] += 1
            over_bowler_runs[(bowler, int(ball.get("over_number", 1) or 1))] += runs_bat + extras_runs
            if ball.get("wicket") and wicket_player and str(ball.get("wicket_type", "") or "").lower() not in {"run_out", "retired_hurt"}:
                bowler_bucket["wickets"] += 1
        if ball.get("wicket") and wicket_player:
            wickets += 1
            batter = batters.setdefault(
                wicket_player,
                {"player_name": wicket_player, "runs": 0, "balls": 0, "fours": 0, "sixes": 0, "status": "not_batted"},
            )
            batter["status"] = "out" if str(ball.get("wicket_type", "") or "").lower() != "retired_hurt" else "retired"

    striker_names = {
        str(ball.get("striker", "") or "").strip()
        for ball in innings.get("balls", [])
        if str(ball.get("striker", "") or "").strip()
    }
    non_striker_names = {
        str(ball.get("non_striker", "") or "").strip()
        for ball in innings.get("balls", [])
        if str(ball.get("non_striker", "") or "").strip()
    }
    for name in striker_names | non_striker_names:
        batter = batters.setdefault(
            name,
            {"player_name": name, "runs": 0, "balls": 0, "fours": 0, "sixes": 0, "status": "not_batted"},
        )
        if batter["status"] == "not_batted":
            batter["status"] = "batting"

    for (bowler_name, _), over_runs in over_bowler_runs.items():
        bowler_bucket = bowlers.get(bowler_name)
        if bowler_bucket and over_runs == 0:
            bowler_bucket["maidens"] += 1

    batting_rows = sorted(
        batters.values(),
        key=lambda item: next(
            (slot.get("slot_number", 99) for slot in innings.get("batters", []) if slot.get("player_name") == item["player_name"]),
            99,
        ),
    )
    bowling_rows = sorted(
        [
            {
                **row,
                "overs": _over_string_from_legal_balls(int(row.get("legal_balls", 0) or 0)),
                "economy": round(
                    (int(row.get("runs_conceded", 0) or 0) / (int(row.get("legal_balls", 0) or 0) / 6)),
                    2,
                )
                if int(row.get("legal_balls", 0) or 0)
                else 0.0,
            }
            for row in bowlers.values()
        ],
        key=lambda item: next(
            (slot.get("slot_number", 99) for slot in innings.get("bowlers", []) if slot.get("player_name") == item["player_name"]),
            99,
        ),
    )
    return {
        "runs": total_runs,
        "wickets": wickets,
        "extras": extras,
        "legal_balls": legal_balls,
        "overs": _over_string_from_legal_balls(legal_balls),
        "batting": batting_rows,
        "bowling": bowling_rows,
    }


def _is_heartlake_side(team_name: str) -> bool:
    return "heartlake" in str(team_name or "").strip().lower()


def rebuild_fixture_performances_from_scorebook(match: dict[str, Any]) -> None:
    manual_rows = [item for item in match.get("performances", []) if str(item.get("source", "") or "") != "scorebook"]
    aggregated: dict[str, dict[str, Any]] = {}
    for innings in (match.get("scorebook", {}) or {}).get("innings", []):
        summary = summarize_innings_scorebook(innings)
        for batter in summary["batting"]:
            name = str(batter.get("player_name", "") or "").strip()
            if not name:
                continue
            row = aggregated.setdefault(
                name,
                normalize_performance({"player_name": name, "source": "scorebook", "notes": "Auto-generated from innings scorebook."}),
            )
            row["runs"] += int(batter.get("runs", 0) or 0)
            row["balls"] += int(batter.get("balls", 0) or 0)
            row["fours"] += int(batter.get("fours", 0) or 0)
            row["sixes"] += int(batter.get("sixes", 0) or 0)
            if batter.get("status") == "out":
                existing = str(row.get("notes", "") or "")
                row["notes"] = (existing + " | out").strip(" |")
        for bowler in summary["bowling"]:
            name = str(bowler.get("player_name", "") or "").strip()
            if not name:
                continue
            row = aggregated.setdefault(
                name,
                normalize_performance({"player_name": name, "source": "scorebook", "notes": "Auto-generated from innings scorebook."}),
            )
            row["wickets"] += int(bowler.get("wickets", 0) or 0)
            existing = str(row.get("notes", "") or "")
            row["notes"] = (existing + f" | overs: {bowler.get('overs', '0.0')} | econ: {bowler.get('economy', 0.0)}").strip(" |")
        for ball in innings.get("balls", []):
            fielder = str(ball.get("fielder", "") or "").strip()
            if fielder and ball.get("wicket") and str(ball.get("wicket_type", "") or "").lower() == "caught":
                row = aggregated.setdefault(
                    fielder,
                    normalize_performance({"player_name": fielder, "source": "scorebook", "notes": "Auto-generated from innings scorebook."}),
                )
                row["catches"] += 1
    match["performances"] = manual_rows + list(aggregated.values())


def sync_fixture_scorecard_from_scorebook(match: dict[str, Any]) -> None:
    innings = (match.get("scorebook", {}) or {}).get("innings", [])
    if not innings:
        return
    scorecard = dict(match.get("scorecard", {}))
    summaries = [summarize_innings_scorebook(item) for item in innings]
    for innings_row, summary in zip(innings, summaries):
        has_scoring = bool((innings_row.get("balls") or []))
        if not has_scoring:
            continue
        batting_team = str(innings_row.get("batting_team", "") or "").strip()
        runs = str(summary.get("runs", ""))
        wickets = str(summary.get("wickets", ""))
        overs = str(summary.get("overs", ""))
        if _is_heartlake_side(batting_team):
            scorecard["heartlake_runs"] = runs
            scorecard["heartlake_wickets"] = wickets
            scorecard["heartlake_overs"] = overs
        else:
            scorecard["opponent_runs"] = runs
            scorecard["opponent_wickets"] = wickets
            scorecard["opponent_overs"] = overs
    heartlake_runs = int(scorecard.get("heartlake_runs") or 0)
    opponent_runs = int(scorecard.get("opponent_runs") or 0)
    if heartlake_runs and opponent_runs:
        if heartlake_runs > opponent_runs:
            scorecard["result"] = "Club won"
        elif opponent_runs > heartlake_runs:
            scorecard["result"] = f"{match.get('opponent') or 'Opponent'} won"
        else:
            scorecard["result"] = "Match tied"
    match["scorecard"] = default_scorecard(scorecard.get("result", "TBD")) | scorecard
    match["heartlake_score"] = compose_score(match["scorecard"]["heartlake_runs"], match["scorecard"]["heartlake_wickets"])
    match["opponent_score"] = compose_score(match["scorecard"]["opponent_runs"], match["scorecard"]["opponent_wickets"])
    rebuild_fixture_performances_from_scorebook(match)


def normalize_member(member: dict[str, Any]) -> dict[str, Any]:
    member = dict(member)
    member.setdefault("id", str(uuid.uuid4())[:8])
    member.setdefault("picture", member_initials(member.get("name", "")))
    for key, value in DEFAULT_MEMBER_FIELDS.items():
        member.setdefault(key, value)
    if isinstance(member.get("aliases"), str):
        member["aliases"] = [alias.strip() for alias in member["aliases"].split(",") if alias.strip()]
    member["name"] = re.sub(r"\s+", " ", str(member.get("name", "")).strip())
    member["full_name"] = re.sub(r"\s+", " ", str(member.get("full_name", "")).strip())
    gender = str(member.get("gender", "") or "").strip().lower()
    if gender in {"m", "male"}:
        gender = "Male"
    elif gender in {"f", "female"}:
        gender = "Female"
    else:
        gender = ""
    member["gender"] = gender
    aliases = []
    seen_aliases: set[str] = set()
    for alias in member.get("aliases", []):
        clean_alias = re.sub(r"\s+", " ", str(alias).strip())
        if not clean_alias:
            continue
        alias_key = clean_alias.lower()
        if alias_key in seen_aliases:
            continue
        seen_aliases.add(alias_key)
        aliases.append(clean_alias)
    member["aliases"] = aliases
    return member


def normalize_name(name: str) -> str:
    return re.sub(r"\s+", " ", str(name or "").strip()).lower()


def canonical_phone(value: str) -> str:
    digits = re.sub(r"\D", "", str(value or ""))
    if len(digits) == 11 and digits.startswith("1"):
        return digits
    if len(digits) == 10:
        return f"1{digits}"
    return digits


def player_name_variants(member: dict[str, Any]) -> set[str]:
    member_name = str(member.get("name", "")).strip()
    variants = {member_name.lower()}
    full_name = str(member.get("full_name", "")).strip().lower()
    if full_name:
        variants.add(full_name)
    for alias in member.get("aliases", []):
        text = str(alias).strip().lower()
        if text:
            variants.add(text)
    normalized_variants = set()
    for item in variants:
        if not item:
            continue
        normalized_variants.add(item)
        normalized_phrase = _normalized_phrase(item)
        if normalized_phrase:
            normalized_variants.add(normalized_phrase)
    return normalized_variants


def resolve_member_name(store: dict[str, Any], raw_name: str) -> str:
    target = str(raw_name or "").strip().lower()
    if not target:
        return str(raw_name or "").strip()
    normalized_target = _normalized_phrase(target)
    for member in store["members"]:
        variants = player_name_variants(member)
        if target in variants or (normalized_target and normalized_target in variants):
            return member["name"]
    return str(raw_name or "").strip()


def archive_batting_team_name(upload: dict[str, Any]) -> str:
    summary = str(upload.get("draft_scorecard", {}).get("live_summary", "") or "").strip()
    match = re.search(r"Batting team:\s*([^|]+)", summary, flags=re.IGNORECASE)
    if match:
        return match.group(1).strip()
    return ""


def archive_bowling_team_name(upload: dict[str, Any]) -> str:
    summary = str(upload.get("draft_scorecard", {}).get("live_summary", "") or "").strip()
    match = re.search(r"Bowling team:\s*([^|]+)", summary, flags=re.IGNORECASE)
    if match:
        return match.group(1).strip()
    return ""


def _archive_team_names_from_payload(payload: dict[str, Any]) -> list[str]:
    names: list[str] = []

    def add(value: Any) -> None:
        text = str(value or "").strip()
        if text:
            names.append(text)

    def inspect(candidate: Any) -> None:
        if not isinstance(candidate, dict):
            return
        for key in ("batting_team", "bowling_team", "home_team", "visitor_team", "opponent", "club_name"):
            add(candidate.get(key))
        teams = candidate.get("teams")
        if isinstance(teams, dict):
            for key in ("batting", "bowling", "home", "visitor", "club_a", "club_b"):
                add(teams.get(key))
        if isinstance(teams, list):
            for item in teams:
                add(item)
        innings = candidate.get("innings")
        if isinstance(innings, list):
            for inning in innings[:2]:
                if isinstance(inning, dict):
                    add(inning.get("batting_team"))
                    add(inning.get("bowling_team"))

    inspect(payload)
    inspect(payload.get("match"))
    inspect(payload.get("info"))
    if isinstance(payload.get("info"), dict):
        inspect(payload["info"].get("match"))
    return _dedupe_nonempty_strings(names)


def archive_batting_team_is_focus_club(upload: dict[str, Any], club_name: str, club_short_name: str = "") -> bool:
    batting_team = archive_batting_team_name(upload).lower()
    candidates = {
        str(club_name or "").strip().lower(),
        str(club_short_name or "").strip().lower(),
    }
    candidates = {item for item in candidates if item}
    return bool(batting_team and batting_team in candidates)


def _archive_json_payload(upload: dict[str, Any]) -> dict[str, Any] | None:
    raw = str(upload.get("raw_extracted_text") or "").strip()
    if not raw:
        return None
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) else None


def _archive_json_innings_count(payload: dict[str, Any]) -> int:
    candidates: list[Any] = []
    if isinstance(payload.get("innings"), list):
        candidates.append(payload.get("innings"))
    match = payload.get("match")
    if isinstance(match, dict) and isinstance(match.get("innings"), list):
        candidates.append(match.get("innings"))
    info = payload.get("info")
    if isinstance(info, dict):
        match_info = info.get("match")
        if isinstance(match_info, dict) and isinstance(match_info.get("innings"), list):
            candidates.append(match_info.get("innings"))
    for innings_list in candidates:
        if len([item for item in innings_list if isinstance(item, dict)]) >= 2:
            return len([item for item in innings_list if isinstance(item, dict)])
    return 0


def archive_has_persisted_json(upload: dict[str, Any]) -> bool:
    payload = _archive_json_payload(upload)
    if not payload:
        return False
    return _archive_json_innings_count(payload) >= 2


def archive_has_partial_json(upload: dict[str, Any]) -> bool:
    payload = _archive_json_payload(upload)
    if not payload:
        return False
    return _archive_json_innings_count(payload) == 1


def _archive_context_signature(upload: dict[str, Any]) -> str:
    payload = _archive_json_payload(upload)
    if payload:
        innings_count = _archive_json_innings_count(payload)
        sources = [f"json:{innings_count}"]
        team_names = _archive_team_names_from_payload(payload)
        if team_names:
            sources.append("|".join(name.lower() for name in team_names[:4]))
        return "|".join(sources)
    summary_bits = [
        archive_batting_team_name(upload).strip().lower(),
        archive_bowling_team_name(upload).strip().lower(),
        str(upload.get("club_name") or "").strip().lower(),
        str(upload.get("draft_scorecard", {}).get("live_summary", "") or "").strip().lower(),
    ]
    return "|".join(bit for bit in summary_bits if bit)


def _dedupe_nonempty_strings(values: list[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for value in values:
        clean = str(value or "").strip()
        if not clean:
            continue
        key = clean.lower()
        if key in seen:
            continue
        seen.add(key)
        ordered.append(clean)
    return ordered


def _coerce_archive_string_list(value: Any) -> list[str]:
    if value is None:
        return []
    items: list[Any]
    if isinstance(value, list):
        items = value
    elif isinstance(value, tuple):
        items = list(value)
    elif isinstance(value, dict):
        items = list(value.values())
    else:
        text = str(value or "").strip()
        if not text:
            return []
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            parsed = None
        if isinstance(parsed, list):
            items = parsed
        elif isinstance(parsed, dict):
            items = list(parsed.values())
        else:
            items = re.split(r"[,\n;|]", text)
    return _dedupe_nonempty_strings([str(item or "").strip() for item in items])


def _club_reference_matches(club: dict[str, Any], identifier: str) -> bool:
    clean = str(identifier or "").strip().lower()
    if not clean:
        return False
    identifiers = {
        str(club.get("id") or "").strip().lower(),
        str(club.get("name") or "").strip().lower(),
        str(club.get("short_name") or "").strip().lower(),
    }
    return clean in {item for item in identifiers if item}


def _resolve_club_reference(clubs: list[dict[str, Any]], identifier: str) -> dict[str, Any] | None:
    clean = str(identifier or "").strip().lower()
    if not clean:
        return None
    return next((club for club in clubs if _club_reference_matches(club, clean)), None)


def _archive_fixture_clubs(archive: dict[str, Any], clubs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    related: list[dict[str, Any]] = []
    seen: set[str] = set()

    def add_club(club: dict[str, Any] | None) -> None:
        if not club:
            return
        club_id = str(club.get("id") or "").strip().lower()
        if club_id and club_id in seen:
            return
        if club_id:
            seen.add(club_id)
        related.append(club)

    add_club(_resolve_club_reference(clubs, str(archive.get("club_id") or "")))
    add_club(_resolve_club_reference(clubs, str(archive.get("club_name") or "")))

    # A single scorecard upload should stay with its primary club unless the
    # archive itself clearly contains two club innings or an applied match link.
    payload = _archive_json_payload(archive)
    multi_club_archive = _archive_json_innings_count(payload) >= 2 if payload else False

    for fixture_id in {str(archive.get("match_id") or "").strip(), str(archive.get("applied_to_match_id") or "").strip()}:
        if not fixture_id:
            continue
        fixture = next((item for item in archive.get("_fixtures", []) if str(item.get("id") or "").strip() == fixture_id), None)
        if not fixture:
            continue
        add_club(_resolve_club_reference(clubs, str(fixture.get("club_id") or "")))
        add_club(_resolve_club_reference(clubs, str(fixture.get("club_name") or "")))
        if multi_club_archive or str(archive.get("applied_to_match_id") or "").strip():
            add_club(_resolve_club_reference(clubs, str(fixture.get("opponent") or fixture.get("visiting_team") or "")))

    batting_team = archive_batting_team_name(archive)
    bowling_team = archive_bowling_team_name(archive)
    add_club(_resolve_club_reference(clubs, batting_team))
    if multi_club_archive:
        add_club(_resolve_club_reference(clubs, bowling_team))

    if payload:
        if multi_club_archive:
            for team_name in _archive_team_names_from_payload(payload):
                add_club(_resolve_club_reference(clubs, team_name))
        else:
            add_club(_resolve_club_reference(clubs, batting_team))

    return related


def archive_club_context(
    archive: dict[str, Any],
    clubs: list[dict[str, Any]],
    members: list[dict[str, Any]] | None = None,
    fixtures: list[dict[str, Any]] | None = None,
) -> tuple[list[str], list[str]]:
    logger.debug(
        "Archive club context requested → archive_id=%s club_id=%s club_name=%s",
        str(archive.get("id") or ""),
        str(archive.get("club_id") or ""),
        str(archive.get("club_name") or ""),
    )
    working = dict(archive)
    working["_members"] = list(members or [])
    working["_fixtures"] = list(fixtures or [])
    related = _archive_fixture_clubs(working, clubs)
    club_ids = _dedupe_nonempty_strings([str(club.get("id") or "").strip() for club in related])
    club_names = _dedupe_nonempty_strings(
        [
            str(club.get("name") or club.get("short_name") or "").strip()
            for club in related
        ]
    )
    return club_ids, club_names


def archive_belongs_to_club(
    archive: dict[str, Any],
    club: dict[str, Any],
    clubs: list[dict[str, Any]] | None = None,
    members: list[dict[str, Any]] | None = None,
    fixtures: list[dict[str, Any]] | None = None,
) -> bool:
    if not club:
        return False
    logger.debug(
        "Archive belongs check → archive_id=%s club_id=%s club_name=%s",
        str(archive.get("id") or ""),
        str(club.get("id") or ""),
        str(club.get("name") or ""),
    )
    club_id = str(club.get("id") or "").strip().lower()
    club_name = str(club.get("name") or "").strip().lower()
    club_short_name = str(club.get("short_name") or "").strip().lower()
    club_ids, club_names = archive_club_context(archive, clubs or [], members, fixtures)
    archive_club_ids = {str(item or "").strip().lower() for item in club_ids if str(item or "").strip()}
    archive_club_names = {str(item or "").strip().lower() for item in club_names if str(item or "").strip()}
    if club_id and club_id in archive_club_ids:
        return True
    if club_name and club_name in archive_club_names:
        return True
    if club_short_name and club_short_name in archive_club_names:
        return True
    archive_club_id = str(archive.get("club_id") or "").strip().lower()
    archive_club_name = str(archive.get("club_name") or "").strip().lower()
    if club_id and archive_club_id == club_id:
        return True
    if club_name and archive_club_name in {club_name, club_short_name}:
        return True
    if club_short_name and archive_club_name == club_short_name:
        return True
    return False


def ensure_member_record(
    store: dict[str, Any],
    raw_name: str,
    *,
    team_name: str = "Club",
    note: str = "",
) -> tuple[str, bool]:
    canonical_name = resolve_member_name(store, raw_name)
    if any(member.get("name") == canonical_name for member in store.get("members", [])):
        return canonical_name, False

    clean_name = re.sub(r"\s+", " ", str(raw_name or "").strip(" -")).strip()
    if not clean_name:
        return canonical_name, False

    member = {
        "id": str(uuid.uuid4())[:8],
        "name": clean_name,
        "full_name": "",
        "team_name": team_name or "Club",
        "aliases": [],
        "age": 0,
        "role": "Player",
        "batting_style": "",
        "bowling_style": "",
        "notes": note or "Auto-added from reviewed scorecard.",
        "picture": member_initials(clean_name),
        "picture_url": "",
        "phone": "",
        "email": "",
        "jersey_number": "",
    }
    store.setdefault("members", []).append(member)
    return clean_name, True


def auto_register_players_from_archive(
    store: dict[str, Any],
    upload: dict[str, Any],
    *,
    match_id: str = "",
    club_id: str = "",
) -> list[str]:
    club = next(
        (item for item in store.get("clubs", []) if str(item.get("id") or "").strip() == str(club_id or upload.get("club_id") or "").strip()),
        store.get("club", {}),
    )
    club_name = str(upload.get("club_name") or club.get("name") or store.get("club", {}).get("name") or "").strip()
    club_short_name = str(club.get("short_name") or club_name).strip()
    team_name = club_short_name or club_name or "Club"

    if club_name and not archive_batting_team_is_focus_club(upload, club_name, club_short_name):
        return []

    new_members: list[str] = []
    source_note = f"Auto-added from reviewed scorecard {upload.get('file_name', '').strip()}.".strip()

    for performance in upload.get("suggested_performances", []):
        raw_name = str(performance.get("player_name", "") or "").strip()
        if not raw_name:
            continue
        canonical_name, created = ensure_member_record(
            store,
            raw_name,
            team_name=team_name,
            note=source_note,
        )
        performance["player_name"] = canonical_name
        if created:
            new_members.append(canonical_name)

    return new_members


def build_availability_defaults(members: list[dict[str, Any]], raw_availability: list[str]) -> tuple[dict[str, str], dict[str, str]]:
    statuses: dict[str, str] = {}
    notes: dict[str, str] = {}
    for label in raw_availability:
        text = str(label).strip()
        if not text:
            continue
        if "(+2 guests)" in text or "+2" in text or "bringing 2 guests" in text.lower():
            base_name = text.split("(")[0].replace("+2", "").strip()
            statuses[base_name] = "available"
            notes[base_name] = "bringing 2 guests"
            continue
        statuses[text] = "available"
    return statuses, notes


def normalize_commentary(entry: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(entry)
    normalized.setdefault("id", str(uuid.uuid4())[:8])
    normalized.setdefault("mode", "text")
    normalized.setdefault("text", "")
    normalized.setdefault("created_at", now_iso())
    return normalized


def normalize_performance(entry: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(entry)
    normalized.setdefault("id", str(uuid.uuid4())[:8])
    normalized.setdefault("player_name", "")
    normalized.setdefault("runs", 0)
    normalized.setdefault("balls", 0)
    normalized.setdefault("wickets", 0)
    normalized.setdefault("catches", 0)
    normalized.setdefault("fours", 0)
    normalized.setdefault("sixes", 0)
    normalized.setdefault("notes", "")
    normalized.setdefault("source", "manual")
    normalized.setdefault("archive_upload_id", "")
    return normalized


def _scorecard_template_player_entry(
    name: str = "",
    member_id: str = "",
    *,
    runs: int | None = None,
    balls: int | None = None,
    fours: int | None = None,
    sixes: int | None = None,
    strike_rate: float | int | None = None,
    dismissal_type: str | None = None,
    fielder: str | None = None,
    bowler: str | None = None,
) -> dict[str, Any]:
    return {
        "player": {
            "name": name or None,
            "normalized_name": normalize_name(name) if name else None,
            "member_id": member_id or None,
        },
        "runs": runs,
        "balls": balls,
        "fours": fours,
        "sixes": sixes,
        "strike_rate": strike_rate,
        "dismissal": {
            "type": dismissal_type,
            "fielder": fielder,
            "bowler": bowler,
        },
    }


def _scorecard_template_bowler_entry(name: str = "") -> dict[str, Any]:
    return {
        "player": {
            "name": name or None,
            "normalized_name": normalize_name(name) if name else None,
        },
        "overs": None,
        "runs_conceded": None,
        "wickets": None,
        "economy": None,
    }


def scorecard_template_from_archive(archive: dict[str, Any]) -> dict[str, Any]:
    draft = dict(archive.get("draft_scorecard") or default_scorecard())
    suggested = [dict(item) for item in archive.get("suggested_performances", []) if isinstance(item, dict)]
    batting_team = str(draft.get("batting_team") or draft.get("heartlake_team") or archive.get("batting_team") or "").strip() or None
    bowling_team = str(draft.get("bowling_team") or archive.get("bowling_team") or "").strip() or None
    batting_players = []
    for item in suggested[:10]:
        player_name = str(item.get("player_name") or item.get("name") or "").strip()
        runs = item.get("runs")
        balls = item.get("balls")
        fours = item.get("fours")
        sixes = item.get("sixes")
        strike_rate = None
        if balls not in (None, "", 0):
            try:
                strike_rate = round((float(runs or 0) / float(balls or 0)) * 100, 2)
            except Exception:
                strike_rate = None
        batting_players.append(
            _scorecard_template_player_entry(
                player_name,
                str(item.get("member_id") or "").strip(),
                runs=int(runs or 0) if str(runs or "").strip() != "" else None,
                balls=int(balls or 0) if str(balls or "").strip() != "" else None,
                fours=int(fours or 0) if str(fours or "").strip() != "" else None,
                sixes=int(sixes or 0) if str(sixes or "").strip() != "" else None,
                strike_rate=strike_rate,
                dismissal_type=None,
                fielder=None,
                bowler=None,
            )
        )
    while len(batting_players) < 10:
        batting_players.append(_scorecard_template_player_entry())
    batting_players.append(_scorecard_template_player_entry(dismissal_type="did_not_bat"))

    second_innings_players = [_scorecard_template_player_entry() for _ in range(10)]
    second_innings_players.append(_scorecard_template_player_entry(dismissal_type="did_not_bat"))

    first_runs = draft.get("heartlake_runs")
    first_wickets = draft.get("heartlake_wickets")
    first_overs = draft.get("heartlake_overs")
    second_runs = draft.get("opponent_runs")
    second_wickets = draft.get("opponent_wickets")
    second_overs = draft.get("opponent_overs")
    return {
        "meta": {
            "source": archive.get("ocr_engine") or archive.get("source") or None,
            "processed_by": archive.get("reviewed_by") or archive.get("ocr_pipeline") or None,
            "confidence": archive.get("confidence") or None,
            "status": "template",
            "created_at": archive.get("created_at") or None,
            "updated_at": archive.get("ocr_processed_at") or archive.get("updated_at") or None,
        },
        "match": {
            "match_id": archive.get("match_id") or None,
            "match_type": "club",
            "format": archive.get("match_format") or None,
            "date": archive.get("archive_date") or archive.get("scorecard_date") or archive.get("photo_taken_at") or None,
            "venue": archive.get("venue") or None,
            "teams": {
                "team_1": batting_team,
                "team_2": bowling_team,
            },
            "overs_limit": archive.get("overs_limit") or None,
        },
        "innings": [
            {
                "inning_number": 1,
                "batting_team": batting_team,
                "bowling_team": bowling_team,
                "summary": {
                    "runs": int(first_runs) if str(first_runs or "").strip() else None,
                    "wickets": int(first_wickets) if str(first_wickets or "").strip() else None,
                    "overs": first_overs if first_overs not in ("", None) else None,
                    "balls": archive.get("inning_1_balls") or None,
                },
                "batting": batting_players,
                "bowling": [_scorecard_template_bowler_entry()],
                "extras": {
                    "wides": None,
                    "no_balls": None,
                    "byes": None,
                    "leg_byes": None,
                    "penalties": None,
                    "total": None,
                },
            },
            {
                "inning_number": 2,
                "batting_team": bowling_team,
                "bowling_team": batting_team,
                "summary": {
                    "runs": int(second_runs) if str(second_runs or "").strip() else None,
                    "wickets": int(second_wickets) if str(second_wickets or "").strip() else None,
                    "overs": second_overs if second_overs not in ("", None) else None,
                    "balls": archive.get("inning_2_balls") or None,
                },
                "batting": second_innings_players,
                "bowling": [_scorecard_template_bowler_entry()],
                "extras": {
                    "wides": None,
                    "no_balls": None,
                    "byes": None,
                    "leg_byes": None,
                    "penalties": None,
                    "total": None,
                },
            },
        ],
        "validation": {
            "inning_1_total": int(first_runs) if str(first_runs or "").strip() else None,
            "inning_2_total": int(second_runs) if str(second_runs or "").strip() else None,
            "expected_result": draft.get("result") or None,
            "is_consistent": None,
            "notes": "Template preserved for admin review.",
        },
    }


def _merge_scorecard_template_payload(base: Any, overlay: Any) -> Any:
    if isinstance(base, dict) and isinstance(overlay, dict):
        merged = dict(base)
        for key, value in overlay.items():
            if key not in merged:
                merged[key] = deepcopy(value)
                continue
            merged[key] = _merge_scorecard_template_payload(merged[key], value)
        return merged
    if isinstance(base, list) and isinstance(overlay, list):
        if not base:
            return deepcopy(overlay)
        merged_list: list[Any] = []
        for index in range(max(len(base), len(overlay))):
            if index < len(base) and index < len(overlay):
                merged_list.append(_merge_scorecard_template_payload(base[index], overlay[index]))
            elif index < len(base):
                merged_list.append(deepcopy(base[index]))
            else:
                merged_list.append(deepcopy(overlay[index]))
        return merged_list
    if base in (None, "", [], {}):
        return deepcopy(overlay)
    return deepcopy(base)


def _review_candidate_archive_entries(
    store: dict[str, Any] | None,
    archive: dict[str, Any] | None,
    limit: int = 8,
) -> list[dict[str, Any]]:
    if not isinstance(store, dict):
        return []
    archive_id = str((archive or {}).get("id") or "").strip()
    archive_date = str((archive or {}).get("archive_date") or (archive or {}).get("scorecard_date") or "").strip()
    archive_family = str((archive or {}).get("family_key") or "").strip()
    archive_club_ids = set(_coerce_archive_string_list((archive or {}).get("club_ids")))
    archive_club_id = str((archive or {}).get("club_id") or "").strip()
    archive_club_name = str((archive or {}).get("club_name") or "").strip().lower()
    candidates: list[dict[str, Any]] = []
    for candidate in canonical_archive_uploads(store.get("archive_uploads", [])):
        candidate_id = str(candidate.get("id") or "").strip()
        if not candidate_id or candidate_id == archive_id:
            continue
        candidate_club_ids = _coerce_archive_string_list(candidate.get("club_ids"))
        same_club = bool(
            archive_club_ids.intersection(candidate_club_ids)
            or (archive_club_id and archive_club_id in candidate_club_ids)
            or (archive_club_name and archive_club_name in str(candidate.get("club_name") or "").strip().lower())
        )
        same_date = bool(archive_date and str(candidate.get("archive_date") or candidate.get("scorecard_date") or "").strip() == archive_date)
        same_family = bool(archive_family and str(candidate.get("family_key") or "").strip() == archive_family)
        same_match = bool(
            str(candidate.get("match_id") or "").strip()
            and str(candidate.get("match_id") or "").strip() == str((archive or {}).get("match_id") or "").strip()
        )
        if not (same_family or same_match or same_date or same_club):
            continue
        candidates.append(
            {
                "id": candidate_id,
                "file_name": candidate.get("file_name") or "",
                "club_id": candidate.get("club_id") or "",
                "club_name": candidate.get("club_name") or "",
                "archive_date": candidate.get("archive_date") or "",
                "season": candidate.get("season") or "",
                "status": candidate.get("status") or "",
                "family_key": candidate.get("family_key") or "",
                "extracted_summary": candidate.get("extracted_summary") or "",
                "has_template": bool(candidate.get("extraction_template")),
            }
        )
        if len(candidates) >= limit:
            break
    return candidates


def _review_llm_prompt(
    template: dict[str, Any],
    review_text: str,
    archive: dict[str, Any] | None = None,
    candidate_archives: list[dict[str, Any]] | None = None,
) -> str:
    archive_bits = []
    if isinstance(archive, dict):
        for key in ("file_name", "club_name", "club_id", "archive_date", "season"):
            value = str(archive.get(key) or "").strip()
            if value:
                archive_bits.append(f"{key}: {value}")
    archive_text = "\n".join(archive_bits) or "No archive metadata provided."
    candidate_text = json.dumps(candidate_archives or [], indent=2)[:8000]
    return (
        "You are reviewing a cricket scorecard JSON for admin approval before it can be published.\n"
        "Return JSON only.\n"
        "Keep the same scorecard schema with meta, match, innings, and validation.\n"
        "Preserve every existing non-empty value exactly as-is.\n"
        "Only fill missing or null fields when the value is directly supported by the provided review JSON.\n"
        "Do not remove keys, do not rename keys, and do not invent player names or scores.\n"
        "If the review JSON contains both innings, keep both innings objects.\n"
        "If the archive appears to belong with a companion archive or the other club, report that in review_assessment.\n"
        "If one innings is missing but a companion archive clearly carries the other innings, combine the evidence in the returned template.\n"
        "Never mix unrelated clubs or unrelated matches.\n"
        "If a field is uncertain, leave it null.\n"
        "Use the review JSON as the main source of truth.\n\n"
        f"Archive metadata:\n{archive_text}\n\n"
        f"Candidate archives:\n{candidate_text}\n\n"
        f"Current template JSON:\n{json.dumps(template, indent=2)[:20000]}\n\n"
        f"Review JSON:\n{str(review_text or '')[:20000]}\n"
    )


def review_scorecard_template_with_llm(
    template: dict[str, Any],
    review_text: str,
    *,
    archive: dict[str, Any] | None = None,
    store: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], str, str, dict[str, Any]]:
    model = preferred_text_llm_model()
    if not model:
        return template, "LLM review unavailable: no local Ollama text model was found.", "", {}
    candidate_archives = _review_candidate_archive_entries(store, archive)
    try:
        response = httpx.post(
            f"{_ollama_base_url()}/api/chat",
            json={
                "model": model,
                "stream": False,
                "options": {"temperature": 0},
                "messages": [
                    {
                        "role": "user",
                        "content": _review_llm_prompt(template, review_text, archive, candidate_archives),
                    }
                ],
            },
            timeout=300.0,
        )
        response.raise_for_status()
        payload = response.json()
        content = str(payload.get("message", {}).get("content", "") or "").strip()
        parsed = _extract_json_payload(content)
        if not isinstance(parsed, dict):
            return template, content or "LLM review returned text but no JSON could be parsed.", model, {}
        assessment = parsed.get("review_assessment") if isinstance(parsed.get("review_assessment"), dict) else {}
        if not _is_scorecard_template_payload(parsed) and isinstance(parsed.get("extraction_template"), dict):
            parsed = parsed["extraction_template"]
        if not _is_scorecard_template_payload(parsed):
            return template, content or "LLM review returned JSON, but not the expected scorecard template.", model, assessment
        merged = _merge_scorecard_template_payload(template, parsed)
        if store and archive and isinstance(assessment, dict):
            companion_ids = [
                str(item).strip()
                for item in assessment.get("possible_companion_archive_ids", [])
                if str(item).strip()
            ]
            for companion_id in companion_ids[:2]:
                companion = next(
                    (
                        item
                        for item in canonical_archive_uploads(store.get("archive_uploads", []))
                        if str(item.get("id") or "").strip() == companion_id
                    ),
                    None,
                )
                if not companion:
                    continue
                companion_template = companion.get("extraction_template")
                if not isinstance(companion_template, dict):
                    companion_template = scorecard_template_from_archive(companion)
                merged = _merge_scorecard_template_payload(merged, companion_template)
        if _is_scorecard_template_payload(merged):
            return merged, content, model, assessment
    except Exception:
        return template, "LLM review failed while contacting the local model.", model, {}
    return template, "LLM review completed.", model, {}


def normalize_archive(item: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(item)
    normalized.setdefault("id", str(uuid.uuid4())[:8])
    normalized.setdefault("club_ids", _coerce_archive_string_list(normalized.get("club_ids")))
    normalized.setdefault("club_names", _coerce_archive_string_list(normalized.get("club_names")))
    normalized.setdefault("club_id", "")
    normalized.setdefault("club_name", "")
    normalized.setdefault("status", "Pending review")
    normalized.setdefault("confidence", "Pending")
    normalized.setdefault("created_at", now_iso())
    normalized.setdefault("preview_url", "")
    normalized.setdefault("file_name", "")
    normalized.setdefault("file_path", "")
    normalized.setdefault("file_hash", "")
    normalized.setdefault("file_size", 0)
    normalized.setdefault("source", "upload")
    normalized.setdefault("match_id", "")
    normalized.setdefault("applied_to_match_id", "")
    normalized.setdefault("scorecard_date", "")
    normalized.setdefault("photo_taken_at", "")
    normalized.setdefault("photo_date_source", "")
    normalized.setdefault("archive_date", "")
    normalized.setdefault("archive_year", "")
    normalized.setdefault("archive_date_source", "")
    normalized.setdefault("raw_extracted_text", "")
    normalized.setdefault("ocr_engine", "")
    normalized.setdefault("ocr_processed_at", "")
    normalized.setdefault("ocr_pipeline", "")
    normalized.setdefault("suggested_performances", [])
    normalized.setdefault("draft_scorecard", default_scorecard())
    normalized.setdefault("extraction_template", scorecard_template_from_archive(normalized))
    normalized.setdefault("review_template_json", "")
    normalized.setdefault("review_source_json", "")
    normalized.setdefault("review_llm_model", "")
    normalized.setdefault("review_llm_notes", "")
    normalized.setdefault("review_llm_assessment", {})
    if not str(normalized.get("review_template_json") or "").strip():
        template = normalized.get("extraction_template")
        if isinstance(template, dict):
            normalized["review_template_json"] = json.dumps(template, indent=2)
    normalized.setdefault("family_key", "")
    normalized.setdefault("family_variant_count", 1)
    normalized.setdefault("family_hidden_count", 0)
    normalized.setdefault("family_hidden_files", [])
    normalized["club_ids"] = _dedupe_nonempty_strings(
        _coerce_archive_string_list(normalized.get("club_ids")) + ([str(normalized.get("club_id") or "").strip()] if normalized.get("club_id") else [])
    )
    normalized["club_names"] = _dedupe_nonempty_strings(
        _coerce_archive_string_list(normalized.get("club_names")) + ([str(normalized.get("club_name") or "").strip()] if normalized.get("club_name") else [])
    )
    if not normalized.get("club_id") and normalized["club_ids"]:
        normalized["club_id"] = normalized["club_ids"][0]
    if not normalized.get("club_name") and normalized["club_names"]:
        normalized["club_name"] = normalized["club_names"][0]
    normalized.setdefault(
        "extracted_summary",
        "Draft created from uploaded scorecard image. Review values before publishing online.",
    )
    normalized = refresh_archive_dates(normalized, normalized.get("raw_extracted_text", ""))
    normalized["family_key"] = archive_family_key(normalized)
    return normalized


def archive_family_stem(file_name: str) -> str:
    stem = Path(file_name or "").stem.lower().strip()
    if not stem:
        return ""
    stem = stem.replace("_", " ").replace("-", " ")
    stem = re.sub(r"\s+", " ", stem).strip()
    tokens = stem.split(" ")
    if tokens and tokens[-1] == "copy":
        tokens = tokens[:-1]
    if len(tokens) >= 3 and tokens[-1].isdigit() and any(token.isdigit() for token in tokens[:-1]):
        tokens = tokens[:-1]
    stem = " ".join(tokens).strip()
    return re.sub(r"\s+", "_", stem)


def archive_family_key(item: dict[str, Any]) -> str:
    stem = archive_family_stem(str(item.get("file_name", "") or ""))
    if not stem:
        stem = str(item.get("id", "") or "")
    archive_date = str(item.get("archive_date", "") or "").strip()
    scorecard_date = str(item.get("scorecard_date", "") or "").strip()
    photo_taken_at = str(item.get("photo_taken_at", "") or "").strip()
    created_at = str(item.get("created_at", "") or "").strip()
    family_date = archive_date or scorecard_date or photo_taken_at[:10] or created_at[:10]
    return f"{stem}|{family_date}|{_archive_context_signature(item)}"


def archive_review_priority(item: dict[str, Any]) -> tuple[int, int, str, str]:
    normalized = normalize_archive(item)
    status = str(normalized.get("status", "") or "").lower()
    confidence = str(normalized.get("confidence", "") or "").lower()
    engine = str(normalized.get("ocr_engine", "") or "").lower()
    draft = normalized.get("draft_scorecard", {}) or {}
    has_structured_score = any(draft.get(field) not in ("", None, 0) for field in (
        "heartlake_runs",
        "heartlake_wickets",
        "heartlake_overs",
        "opponent_runs",
        "opponent_wickets",
        "opponent_overs",
    ))
    has_players = bool(normalized.get("suggested_performances"))
    priority = 0
    if status == "applied to match":
        priority += 100
    if engine == "manual-import" or "imported review" in confidence:
        priority += 80
    if has_players:
        priority += 20
    if has_structured_score:
        priority += 15
    if normalized.get("raw_extracted_text"):
        priority += 5
    processed_at = str(normalized.get("ocr_processed_at", "") or "")
    created_at = str(normalized.get("created_at", "") or "")
    return (priority, 1 if processed_at else 0, processed_at or created_at, normalized.get("id", ""))


def canonical_archive_uploads(archive_uploads: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in archive_uploads:
        normalized = normalize_archive(item)
        grouped[normalized["family_key"]].append(normalized)

    canonical: list[dict[str, Any]] = []
    for family_items in grouped.values():
        chosen = max(family_items, key=archive_review_priority)
        siblings = sorted(
            [item.get("file_name", "") for item in family_items if item.get("id") != chosen.get("id") and item.get("file_name")],
            key=str.lower,
        )
        chosen = dict(chosen)
        chosen["family_variant_count"] = len(family_items)
        chosen["family_hidden_count"] = len(siblings)
        chosen["family_hidden_files"] = siblings
        canonical.append(chosen)
    return sorted(canonical, key=lambda item: (item.get("created_at", ""), item.get("id", "")))


def normalize_duplicate(item: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(item)
    normalized.setdefault("id", str(uuid.uuid4())[:8])
    normalized.setdefault("created_at", now_iso())
    normalized.setdefault("reason", "duplicate file hash")
    normalized.setdefault("source", "upload")
    normalized.setdefault("review_dir", "")
    normalized.setdefault("original_file_name", "")
    normalized.setdefault("original_file_path", "")
    normalized.setdefault("original_review_path", "")
    normalized.setdefault("duplicate_file_name", "")
    normalized.setdefault("duplicate_file_path", "")
    normalized.setdefault("duplicate_review_path", "")
    normalized.setdefault("original_review_url", "")
    normalized.setdefault("duplicate_review_url", "")
    normalized.setdefault("file_hash", "")
    normalized.setdefault("status", "Pending manual review")
    if not normalized.get("original_review_url"):
        normalized["original_review_url"] = review_url_for_path(normalized.get("original_review_path", ""))
    if not normalized.get("duplicate_review_url"):
        normalized["duplicate_review_url"] = review_url_for_path(normalized.get("duplicate_review_path", ""))
    return normalized


def review_url_for_path(path_string: str) -> str:
    if not path_string:
        return ""
    try:
        relative = Path(path_string).resolve().relative_to(DUPLICATE_DIR.resolve())
    except Exception:
        return ""
    return "/duplicates/" + "/".join(relative.parts)


def resolve_existing_upload_path(path_string: str, file_name: str = "") -> Path | None:
    direct = Path(path_string or "")
    if direct.is_file():
        return direct

    candidate_names = []
    if file_name:
        candidate_names.append(file_name)
    if direct.name:
        candidate_names.append(direct.name)

    seen: set[str] = set()
    for candidate in candidate_names:
        clean = str(candidate or "").strip()
        if not clean or clean.lower() in seen:
            continue
        seen.add(clean.lower())
        for root in (UPLOAD_DIR, LEGACY_UPLOAD_DIR):
            exact = root / clean
            if exact.is_file():
                return exact
        stem = Path(clean).stem.lower()
        if not stem:
            continue
        for root in (UPLOAD_DIR, LEGACY_UPLOAD_DIR):
            for existing in root.iterdir():
                if existing.is_file() and existing.stem.lower() == stem:
                    return existing
    return None


def _ollama_base_url() -> str:
    return os.environ.get("OLLAMA_BASE_URL", "http://127.0.0.1:11434").rstrip("/")


def available_ollama_models() -> list[str]:
    try:
        response = httpx.get(f"{_ollama_base_url()}/api/tags", timeout=4.0)
        response.raise_for_status()
        return [item.get("name", "").strip() for item in response.json().get("models", []) if item.get("name")]
    except Exception:
        return []


def preferred_vision_llm_model() -> str:
    configured = os.environ.get("ARCHIVE_VISION_MODEL", "").strip()
    models = available_ollama_models()
    if configured and configured in models:
        return configured
    for candidate in VISION_LLM_MODEL_PREFERENCES:
        if candidate in models:
            return candidate
    return ""


def preferred_text_llm_model() -> str:
    configured = (
        os.environ.get("ARCHIVE_REVIEW_MODEL", "").strip()
        or os.environ.get("ARCHIVE_TEXT_MODEL", "").strip()
        or os.environ.get("OLLAMA_MODEL", "").strip()
    )
    models = available_ollama_models()
    if configured and configured in models:
        return configured
    for candidate in TEXT_LLM_MODEL_PREFERENCES:
        if candidate in models:
            return candidate
    return ""


def local_ocr_available() -> bool:
    return bool(shutil.which("tesseract") and shutil.which("sips"))


def vision_ocr_available() -> bool:
    return VISION_OCR_SCRIPT.is_file() and bool(shutil.which("swift"))


def clean_ocr_lines(text: str) -> list[str]:
    return [re.sub(r"\s+", " ", line).strip() for line in text.splitlines() if line.strip()]


def _normalized_phrase(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(value or "").lower()).strip()


def extract_text_from_image(path: Path) -> str:
    if not path.is_file():
        return ""
    vision_candidate = ""
    if vision_ocr_available():
        try:
            vision_result = subprocess.run(
                ["swift", str(VISION_OCR_SCRIPT), str(path)],
                check=True,
                capture_output=True,
                text=True,
                timeout=40,
            )
            vision_candidate = vision_result.stdout.strip()
        except Exception:
            pass
    if not local_ocr_available():
        return vision_candidate
    with TemporaryDirectory() as temp_dir:
        png_path = Path(temp_dir) / "ocr-source.png"
        jpg_path = Path(temp_dir) / "ocr-source.jpg"
        try:
            subprocess.run(
                ["sips", "-s", "format", "png", str(path), "--out", str(png_path)],
                check=True,
                capture_output=True,
                text=True,
                timeout=8,
            )
            subprocess.run(
                ["sips", "-Z", "2600", str(png_path), "--out", str(png_path)],
                check=True,
                capture_output=True,
                text=True,
                timeout=8,
            )
            subprocess.run(
                ["sips", "-s", "format", "jpeg", str(path), "--out", str(jpg_path)],
                check=True,
                capture_output=True,
                text=True,
                timeout=8,
            )
            subprocess.run(
                ["sips", "-Z", "2600", str(jpg_path), "--out", str(jpg_path)],
                check=True,
                capture_output=True,
                text=True,
                timeout=8,
            )

            tesseract_candidates: list[str] = []
            for source_path in [png_path, jpg_path]:
                for psm in ["6", "11"]:
                    result = subprocess.run(
                        [
                            "tesseract",
                            str(source_path),
                            "stdout",
                            "--psm",
                            psm,
                            "-c",
                            "preserve_interword_spaces=1",
                        ],
                        check=True,
                        capture_output=True,
                        text=True,
                        timeout=12,
                    )
                    text = result.stdout.strip()
                    if text:
                        tesseract_candidates.append(text)

            best_tesseract = max(tesseract_candidates, key=score_ocr_candidate) if tesseract_candidates else ""
            if vision_candidate and best_tesseract:
                vision_score = score_ocr_candidate(vision_candidate)
                tesseract_score = score_ocr_candidate(best_tesseract)
                if vision_score >= int(tesseract_score * 0.75):
                    return vision_candidate
                return best_tesseract
            if vision_candidate:
                return vision_candidate
            if best_tesseract:
                return best_tesseract
            return ""
        except Exception:
            return vision_candidate


def _canonical_member_name(members: list[dict[str, Any]], raw_name: str) -> str:
    target = str(raw_name or "").strip().lower()
    if not target:
        return str(raw_name or "").strip()
    for member in members:
        if target in player_name_variants(member):
            return member["name"]
    return str(raw_name or "").strip()


def _extract_json_object(text: str) -> dict[str, Any] | None:
    raw = str(text or "").strip()
    if not raw:
        return None
    candidates = [raw]
    fenced = re.findall(r"```(?:json)?\s*(\{.*?\})\s*```", raw, flags=re.DOTALL)
    candidates.extend(fenced)
    start = raw.find("{")
    end = raw.rfind("}")
    if start != -1 and end != -1 and end > start:
        candidates.append(raw[start : end + 1])
    for candidate in candidates:
        try:
            payload = json.loads(candidate)
            if isinstance(payload, dict):
                return payload
        except Exception:
            continue
    return None


def _extract_json_payload(text: str) -> dict[str, Any] | None:
    raw = str(text or "").strip()
    if not raw:
        return None
    object_payload = _extract_json_object(raw)
    if object_payload is not None:
        return object_payload
    candidates = [raw]
    fenced = re.findall(r"```(?:json)?\s*(\[.*?\])\s*```", raw, flags=re.DOTALL)
    candidates.extend(fenced)
    start = raw.find("[")
    end = raw.rfind("]")
    if start != -1 and end != -1 and end > start:
        candidates.append(raw[start : end + 1])
    for candidate in candidates:
        try:
            payload = json.loads(candidate)
            if isinstance(payload, list):
                return {"batting": payload}
        except Exception:
            continue
    return None


def _is_scorecard_template_payload(payload: Any) -> bool:
    return (
        isinstance(payload, dict)
        and isinstance(payload.get("meta"), dict)
        and isinstance(payload.get("match"), dict)
        and isinstance(payload.get("innings"), list)
        and isinstance(payload.get("validation"), dict)
    )


def _safe_int(value: Any) -> int | None:
    if value in (None, "", "null"):
        return None
    try:
        return int(float(str(value).strip()))
    except Exception:
        return None


def _safe_float(value: Any) -> float | None:
    if value in (None, "", "null"):
        return None
    try:
        return float(str(value).strip())
    except Exception:
        return None


def _image_path_for_llm(path: Path, temp_dir: Path) -> Path:
    if path.suffix.lower() in {".png", ".jpg", ".jpeg"}:
        return path
    converted = temp_dir / f"{path.stem}.png"
    subprocess.run(
        ["sips", "-s", "format", "png", str(path), "--out", str(converted)],
        check=True,
        capture_output=True,
        text=True,
        timeout=12,
    )
    return converted


def _vision_prompt(members: list[dict[str, Any]], ocr_hint: str) -> str:
    roster_labels = []
    for member in members:
        aliases = ", ".join(member.get("aliases", []))
        full_name = str(member.get("full_name", "")).strip()
        label = member["name"]
        if full_name:
            label += f" ({full_name})"
        if aliases:
            label += f" aliases: {aliases}"
        roster_labels.append(label)
    roster_text = "; ".join(roster_labels[:40])
    trimmed_hint = ocr_hint[:4000] if ocr_hint else "No OCR hint available."
    return (
        "Extract the visible batting innings from this cricket scorecard image.\n"
        "Use the image as primary evidence. The OCR hint may be noisy.\n"
        "Rules:\n"
        "- Return JSON only.\n"
        "- Do not guess.\n"
        "- If a value is unreadable, use null.\n"
        "- Keep batting rows separate.\n"
        "- Normalize player names to the closest exact roster name or saved alias only when the match is clear.\n"
        "Schema:\n"
        '{"batting_team": string | null, "bowling_team": string | null, "total_runs": number | null, "wickets": number | null, "overs": number | null, "extras_total": number | null, "batting": [{"name": string, "runs": number | null, "balls": number | null}]}\n'
        f"Roster hints: {roster_text}\n"
        f"OCR hint:\n{trimmed_hint}\n"
    )


def _vision_payload_is_usable(payload: dict[str, Any], members: list[dict[str, Any]], ocr_hint: str) -> bool:
    total_runs = _safe_int(payload.get("total_runs"))
    wickets = _safe_int(payload.get("wickets"))
    overs = _safe_float(payload.get("overs"))
    batting_rows = payload.get("batting", []) if isinstance(payload.get("batting"), list) else []

    if wickets is not None and wickets > 10:
        return False
    if overs is not None and overs > 50:
        return False
    if total_runs is None and not batting_rows:
        return False

    runs_sum = 0
    matched_names = 0
    hint_text = _normalized_phrase(ocr_hint)
    for row in batting_rows:
        if not isinstance(row, dict):
            continue
        name = str(row.get("name") or "").strip()
        if not name:
            continue
        row_runs = _safe_int(row.get("runs"))
        if row_runs is not None:
            runs_sum += row_runs
        normalized_name = _normalized_phrase(name)
        if normalized_name and normalized_name in hint_text:
            matched_names += 1
            continue
        canonical = _canonical_member_name(members, name)
        if canonical != name or normalized_name in {_normalized_phrase(canonical)}:
            matched_names += 1

    if total_runs is not None and runs_sum and runs_sum > total_runs + 40:
        return False
    if batting_rows and matched_names < max(1, len(batting_rows) // 2):
        return False
    return True


def extract_scorecard_with_vision_llm(path: Path, members: list[dict[str, Any]]) -> dict[str, Any] | None:
    model = preferred_vision_llm_model()
    if not model or not path.is_file():
        return None
    ocr_hint = extract_text_from_image(path)
    with TemporaryDirectory() as temp_dir_name:
        temp_dir = Path(temp_dir_name)
        try:
            llm_image = _image_path_for_llm(path, temp_dir)
        except Exception:
            return None
        image_b64 = base64.b64encode(llm_image.read_bytes()).decode("ascii")
        try:
            response = httpx.post(
                f"{_ollama_base_url()}/api/chat",
                json={
                    "model": model,
                    "stream": False,
                    "options": {"temperature": 0},
                    "messages": [
                        {
                            "role": "user",
                            "content": _vision_prompt(members, ocr_hint),
                            "images": [image_b64],
                        }
                    ],
                },
                timeout=300.0,
            )
            response.raise_for_status()
            payload = response.json()
        except Exception:
            return None
    content = payload.get("message", {}).get("content", "")
    parsed = _extract_json_payload(content)
    if not parsed:
        return None
    if not _vision_payload_is_usable(parsed, members, ocr_hint):
        return None
    return {
        "model": model,
        "content": content,
        "payload": parsed,
        "ocr_hint": ocr_hint,
    }


def draft_from_llm_extraction(extracted: dict[str, Any], members: list[dict[str, Any]]) -> tuple[dict[str, str], list[dict[str, Any]], str]:
    payload = extracted.get("payload", {})
    match = payload.get("match", {}) if isinstance(payload, dict) else {}
    innings_list = match.get("innings", []) if isinstance(match, dict) else []
    innings = innings_list[0] if innings_list and isinstance(innings_list[0], dict) else {}
    teams = match.get("teams", {}) if isinstance(match, dict) else {}
    if innings:
        batting_team = str(
            innings.get("batting_team")
            or teams.get("batting")
            or ""
        ).strip()
        bowling_team = str(teams.get("bowling") or "").strip()
        total_runs = _safe_int(innings.get("total_runs"))
        wickets = _safe_int(innings.get("wickets"))
        overs = _safe_float(innings.get("overs"))
        extras = innings.get("extras", {}) if isinstance(innings.get("extras"), dict) else {}
        extras_total = _safe_int(extras.get("total"))
        batting_rows = innings.get("batting", []) if isinstance(innings.get("batting"), list) else []
        did_not_bat = [str(name).strip() for name in innings.get("did_not_bat", []) if str(name).strip()]
    else:
        batting_team = str(payload.get("batting_team") or "").strip()
        bowling_team = str(payload.get("bowling_team") or "").strip()
        total_runs = _safe_int(payload.get("total_runs"))
        wickets = _safe_int(payload.get("wickets"))
        overs = _safe_float(payload.get("overs"))
        extras_total = _safe_int(payload.get("extras_total"))
        batting_rows = payload.get("batting", []) if isinstance(payload.get("batting"), list) else []
        did_not_bat = []

    draft = default_scorecard("Recovered from local vision model review")
    if batting_team.lower().startswith("heartlake") or bowling_team:
        if batting_team.lower().startswith("heartlake"):
            if total_runs is not None:
                draft["heartlake_runs"] = str(total_runs)
            if wickets is not None:
                draft["heartlake_wickets"] = str(wickets)
            if overs is not None:
                draft["heartlake_overs"] = str(overs)
        else:
            if total_runs is not None:
                draft["opponent_runs"] = str(total_runs)
            if wickets is not None:
                draft["opponent_wickets"] = str(wickets)
            if overs is not None:
                draft["opponent_overs"] = str(overs)

    summary_parts = []
    if batting_team:
        summary_parts.append(f"Batting team: {batting_team}")
    if bowling_team:
        summary_parts.append(f"Bowling team: {bowling_team}")
    if extras_total is not None:
        summary_parts.append(f"Extras: {extras_total}")
    if did_not_bat:
        summary_parts.append(f"Did not bat: {', '.join(did_not_bat)}")
    draft["live_summary"] = " | ".join(summary_parts)

    suggestions: list[dict[str, Any]] = []
    for entry in batting_rows:
        if not isinstance(entry, dict):
            continue
        raw_name = str(entry.get("name") or "").strip()
        runs = _safe_int(entry.get("runs"))
        if not raw_name or runs is None:
            continue
        canonical_name = _canonical_member_name(members, raw_name)
        suggestions.append(
            {
                "player_name": canonical_name,
                "runs": runs,
                "balls": _safe_int(entry.get("balls")) or 0,
                "wickets": 0,
                "catches": 0,
                "fours": _safe_int(entry.get("fours")) or 0,
                "sixes": _safe_int(entry.get("sixes")) or 0,
                "notes": f"Local vision model extracted {raw_name}"[:180],
                "source": "local-vision-llm",
                "confidence": "medium",
            }
        )

    raw_debug = (
        f"Model: {extracted.get('model', '')}\n\n"
        f"Model response:\n{extracted.get('content', '')}\n\n"
        f"OCR hint:\n{extracted.get('ocr_hint', '')}"
    )
    return draft, suggestions, raw_debug


def score_ocr_candidate(text: str) -> int:
    lowered = text.lower()
    keywords = [
        "total",
        "extras",
        "batsman",
        "bowler",
        "runs",
        "overs",
        "venue",
        "date",
        "how out",
    ]
    keyword_score = sum(25 for keyword in keywords if keyword in lowered)
    pair_score = 18 * len(score_pairs_from_text(text))
    line_score = min(len(clean_ocr_lines(text)) * 2, 60)
    digit_score = min(sum(char.isdigit() for char in text), 80)
    return keyword_score + pair_score + line_score + digit_score


def score_pairs_from_text(text: str) -> list[tuple[str, str]]:
    pairs: list[tuple[str, str]] = []
    seen: set[tuple[str, str]] = set()
    blocked_keywords = {
        "date",
        "venue",
        "toss",
        "time",
        "umpires",
        "scorers",
        "capts",
        "home",
        "run rate",
        "scoring rate",
        "over no",
        "minutes",
    }
    for line in clean_ocr_lines(text):
        lowered = line.lower()
        if any(keyword in lowered for keyword in blocked_keywords):
            continue
        for runs, wickets in re.findall(r"(?<!\d)(\d{2,3})\s*[-/]\s*(\d{1,2})(?!\d)", line):
            if int(wickets) > 10 or int(runs) > 350 or int(runs) < 20:
                continue
            pair = (runs, wickets)
            if pair in seen:
                continue
            seen.add(pair)
            pairs.append(pair)
    return pairs


def result_from_ocr_text(text: str) -> str:
    for line in clean_ocr_lines(text):
        lowered = line.lower()
        if "won by" in lowered or "lost by" in lowered or "match tied" in lowered or "draw" in lowered:
            return line[:160]
    return "Recovered from OCR review"


def draft_from_ocr_text(text: str, match_id: str = "") -> dict[str, str]:
    draft = default_scorecard(result_from_ocr_text(text) if text else "Pending review")
    if not text:
        if match_id:
            draft["result"] = "Linked to scheduled match, awaiting manual review"
        return draft
    lines = clean_ocr_lines(text)
    labeled_candidates: list[tuple[int, tuple[str, str], str]] = []
    score_keywords = {
        "s. total": 90,
        "g. total": 90,
        "total extras": 25,
        "extras": 20,
        "fall of wkt": 40,
        "score": 35,
        "total": 35,
        "outgoing bat": 20,
    }
    for idx, _line in enumerate(lines):
        window = " ".join(lines[max(0, idx - 1) : idx + 2])
        pairs = score_pairs_from_text(window)
        if not pairs:
            continue
        lowered_window = window.lower()
        weight = 0
        for keyword, points in score_keywords.items():
            if keyword in lowered_window:
                weight += points
        if "date" in lowered_window or "venue" in lowered_window or "umpires" in lowered_window or "scorers" in lowered_window:
            weight -= 60
        if "overs in" in lowered_window or "wickets in" in lowered_window or "minutes" in lowered_window:
            weight -= 50
        for pair in pairs:
            labeled_candidates.append((weight, pair, lowered_window))

    labeled_candidates.sort(key=lambda item: (-item[0], -int(item[1][0])))
    chosen_pairs: list[tuple[tuple[str, str], str]] = []
    for weight, pair, context in labeled_candidates:
        if weight <= 0:
            continue
        if not any(existing_pair == pair for existing_pair, _ in chosen_pairs):
            chosen_pairs.append((pair, context))
    if not chosen_pairs:
        chosen_pairs = [(pair, "") for pair in score_pairs_from_text(text)]

    if chosen_pairs:
        draft["heartlake_runs"], draft["heartlake_wickets"] = chosen_pairs[0][0]
        draft["heartlake_wickets"] = str(int(draft["heartlake_wickets"]))
    if len(chosen_pairs) > 1:
        opponent_context_keywords = {
            "opponent",
            "2nd innings",
            "second innings",
            "target",
            "chase",
            "away",
            "visitor",
            "visiting",
        }
        second_pair, second_context = chosen_pairs[1]
        if any(keyword in second_context for keyword in opponent_context_keywords):
            draft["opponent_runs"], draft["opponent_wickets"] = second_pair
            draft["opponent_wickets"] = str(int(draft["opponent_wickets"]))
    overs = re.findall(r"(?<!\d)(\d{1,2}(?:\.\d)?)\s*(?:overs?|ovs?)(?!\d)", text, flags=re.IGNORECASE)
    if overs:
        draft["heartlake_overs"] = overs[0]
    if len(overs) > 1:
        draft["opponent_overs"] = overs[1]
    return draft


def extract_player_suggestions(text: str, members: list[dict[str, Any]]) -> list[dict[str, Any]]:
    suggestions: list[dict[str, Any]] = []
    seen_players: set[str] = set()

    def add_suggestion(player_name: str, runs: int, balls: int, line: str, source: str) -> None:
        canonical_name = str(player_name or "").strip()
        if not canonical_name:
            return
        normalized_name = _normalized_phrase(canonical_name)
        if not normalized_name or normalized_name in seen_players:
            return
        suggestions.append(
            {
                "player_name": canonical_name,
                "runs": max(0, int(runs or 0)),
                "balls": max(0, int(balls or 0)),
                "wickets": 0,
                "catches": 0,
                "fours": 0,
                "sixes": 0,
                "notes": f"OCR suggested from archive line: {line[:120]}",
                "source": source,
                "confidence": "low" if source == "ocr-suggested" else "heuristic",
            }
        )
        seen_players.add(normalized_name)

    def fallback_row_from_line(line: str) -> tuple[str, int, int]:
        lowered = line.lower()
        if any(keyword in lowered for keyword in ("date", "venue", "toss", "umpire", "scorer", "overs", "innings", "result")):
            return "", 0, 0
        numbers = [int(value) for value in re.findall(r"(?<!\d)(\d{1,3})(?!\d)", line)]
        numbers = [value for value in numbers if value <= 200]
        if not numbers:
            return "", 0, 0
        tokens = re.split(r"\s+", line.strip())
        name_tokens: list[str] = []
        for token in tokens:
            if re.search(r"\d", token):
                break
            clean = re.sub(r"[^A-Za-z'.-]", "", token).strip()
            if not clean or clean.lower() in {"not", "out", "did", "bat", "didn't", "dnb"}:
                continue
            name_tokens.append(clean)
        candidate_name = re.sub(r"\s+", " ", " ".join(name_tokens)).strip(" -.,")
        if len(candidate_name) < 2:
            return "", 0, 0
        runs = numbers[0]
        balls = numbers[1] if len(numbers) > 1 and numbers[1] <= 120 else 0
        return candidate_name, runs, balls

    for line in clean_ocr_lines(text):
        normalized_line = _normalized_phrase(line)
        if not normalized_line:
            continue
        numbers = [int(value) for value in re.findall(r"(?<!\d)(\d{1,3})(?!\d)", line)]
        numbers = [value for value in numbers if value <= 200]
        matched = False
        for member in members:
            member_key = normalize_name(member["name"])
            if member_key in seen_players:
                continue
            variants = {_normalized_phrase(value) for value in player_name_variants(member)}
            variants = {value for value in variants if value}
            if not variants or not any(variant in normalized_line for variant in variants):
                continue
            if not numbers:
                break
            runs = numbers[0]
            balls = numbers[1] if len(numbers) > 1 and numbers[1] <= 120 else 0
            add_suggestion(member["name"], runs, balls, line, "ocr-suggested")
            matched = True
            break
        if matched:
            continue
        fallback_name, fallback_runs, fallback_balls = fallback_row_from_line(line)
        if fallback_name and fallback_runs:
            add_suggestion(fallback_name, fallback_runs, fallback_balls, line, "ocr-fallback")
    return suggestions


def enrich_archive_record(item: dict[str, Any], members: list[dict[str, Any]]) -> dict[str, Any]:
    normalized = normalize_archive(item)
    file_path = Path(normalized.get("file_path") or "")
    if not file_path.is_file():
        return normalized
    if normalized.get("ocr_processed_at"):
        return normalized

    llm_extraction = extract_scorecard_with_vision_llm(file_path, members)
    normalized["ocr_processed_at"] = now_iso()
    if llm_extraction:
        draft, suggestions, raw_debug = draft_from_llm_extraction(llm_extraction, members)
        normalized["draft_scorecard"] = draft
        normalized["suggested_performances"] = suggestions
        normalized["raw_extracted_text"] = raw_debug[:12000]
        normalized["ocr_engine"] = llm_extraction.get("model", "vision-llm")
        normalized["ocr_pipeline"] = (
            "Local vision-language extraction with Ollama image input, roster-aware JSON prompt, and OCR hint fallback"
        )
        normalized["confidence"] = "Vision LLM draft"
        normalized["extracted_summary"] = (
            f"Local vision model generated a reviewable scorecard draft and "
            f"{len(suggestions)} player batting lines."
        )
        return refresh_archive_dates(normalized, normalized["raw_extracted_text"])

    text = extract_text_from_image(file_path)
    if text:
        draft = draft_from_ocr_text(text, normalized.get("match_id", ""))
        filename_draft = parse_scorecard_draft_from_name(normalized.get("file_name", ""), normalized.get("match_id", ""))
        if not draft.get("heartlake_runs") and filename_draft.get("heartlake_runs"):
            draft["heartlake_runs"] = filename_draft["heartlake_runs"]
            draft["heartlake_wickets"] = filename_draft["heartlake_wickets"]
        if not draft.get("opponent_runs") and filename_draft.get("opponent_runs"):
            draft["opponent_runs"] = filename_draft["opponent_runs"]
            draft["opponent_wickets"] = filename_draft["opponent_wickets"]
        normalized["draft_scorecard"] = draft
        normalized["suggested_performances"] = extract_player_suggestions(text, members)
        normalized["raw_extracted_text"] = text[:12000]
        normalized["ocr_engine"] = "vision+tesseract" if vision_ocr_available() else "tesseract"
        normalized["ocr_pipeline"] = (
            "Apple Vision OCR first, then converted PNG/JPG OCR fallback with best candidate selection"
            if vision_ocr_available()
            else "converted to PNG/JPG via sips, then best OCR candidate selected"
        )
        normalized["confidence"] = "OCR draft"
        normalized["extracted_summary"] = (
            f"Local OCR generated a reviewable scorecard draft and "
            f"{len(normalized['suggested_performances'])} player score suggestions."
        )
    else:
        normalized["draft_scorecard"] = parse_scorecard_draft_from_name(
            normalized.get("file_name", ""),
            normalized.get("match_id", ""),
        )
        normalized["ocr_engine"] = "filename-fallback"
        normalized["ocr_pipeline"] = "converted image OCR failed, filename fallback only"
        normalized["confidence"] = "Filename draft"
        normalized["extracted_summary"] = (
            "Image was converted for OCR first, but OCR could not confidently read it, so a filename-based draft was stored for manual review."
        )
    return refresh_archive_dates(normalized, normalized.get("raw_extracted_text", ""))


def reset_archive_extraction(item: dict[str, Any]) -> dict[str, Any]:
    normalized = normalize_archive(item)
    normalized["raw_extracted_text"] = ""
    normalized["ocr_engine"] = ""
    normalized["ocr_processed_at"] = ""
    normalized["ocr_pipeline"] = ""
    normalized["suggested_performances"] = []
    normalized["draft_scorecard"] = parse_scorecard_draft_from_name(
        normalized.get("file_name", ""),
        normalized.get("match_id", ""),
    )
    normalized["confidence"] = "Pending"
    normalized["extracted_summary"] = "Awaiting one-at-a-time OCR review."
    return normalized


def extract_archive_by_id(store: dict[str, Any], upload_id: str) -> dict[str, Any]:
    logger.debug("Extract archive requested → upload_id=%s", upload_id)
    members = store["members"]
    for index, item in enumerate(store.get("archive_uploads", [])):
        if item.get("id") != upload_id:
            continue
        extracted = enrich_archive_record(reset_archive_extraction(item), members)
        extracted["extraction_template"] = scorecard_template_from_archive(extracted)
        store["archive_uploads"][index] = extracted
        logger.debug(
            "Extract archive complete → upload_id=%s file=%s club_id=%s suggested=%s",
            upload_id,
            extracted.get("file_name", ""),
            extracted.get("club_id", ""),
            len(extracted.get("suggested_performances", []) or []),
        )
        return extracted
    raise ValueError("Archive upload not found.")


def reset_score_data(store: dict[str, Any]) -> dict[str, Any]:
    preserved_archives = []
    preserved_archive_ids: set[str] = set()
    for item in store.get("archive_uploads", []):
        normalized = normalize_archive(item)
        if normalized.get("ocr_engine") == "manual-import" or normalized.get("status") == "Applied to match":
            preserved_archives.append(normalized)
            if normalized.get("status") == "Applied to match" and normalized.get("id"):
                preserved_archive_ids.add(normalized["id"])
        else:
            preserved_archives.append(reset_archive_extraction(normalized))
    for fixture in store.get("fixtures", []):
        fixture["performances"] = [
            entry
            for entry in fixture.get("performances", [])
            if entry.get("archive_upload_id") in preserved_archive_ids
        ]
    store["archive_uploads"] = preserved_archives
    return store


def available_labels(statuses: dict[str, str], notes: dict[str, str]) -> list[str]:
    labels = []
    for player_name, status in statuses.items():
        if status != "available":
            continue
        note = notes.get(player_name, "").strip()
        labels.append(f"{player_name} ({note})" if note else player_name)
    return labels


def normalize_fixture(fixture: dict[str, Any], members: list[dict[str, Any]]) -> dict[str, Any]:
    normalized = dict(fixture)
    normalized.setdefault("id", str(uuid.uuid4())[:8])
    normalized.setdefault("club_id", "")
    normalized.setdefault("club_name", "")
    normalized["season_year"] = fixture_season_year(normalized)
    normalized["season"] = fixture_season_label(normalized)
    normalized.setdefault("visiting_team", normalized.get("opponent", "Visiting Team"))
    normalized.setdefault("status", "Scheduled")
    normalized.setdefault("heartlake_captain", "")

    raw_availability = normalized.get("availability_seed")
    if raw_availability is None:
        raw_availability = normalized.get("availability", [])
    normalized["availability_seed"] = list(raw_availability or [])
    availability_statuses = dict(normalized.get("availability_statuses", {}))
    availability_notes = dict(normalized.get("availability_notes", {}))
    selected_lineup_source = normalized.get("selected_playing_xi_member_ids")
    if selected_lineup_source is None:
        selected_lineup_source = normalized.get("selected_playing_xi", [])
    if isinstance(selected_lineup_source, str):
        selected_lineup_source = [item.strip() for item in selected_lineup_source.split(",") if item.strip()]
    member_name_to_id = {str(member.get("name") or "").strip(): str(member.get("id") or "").strip() for member in members}
    member_id_to_name = {str(member.get("id") or "").strip(): str(member.get("name") or "").strip() for member in members}
    selected_member_ids: list[str] = []
    for item in list(selected_lineup_source or []):
        raw_value = str(item or "").strip()
        if not raw_value:
            continue
        member_id = raw_value if raw_value in member_id_to_name else member_name_to_id.get(raw_value, "")
        if member_id and member_id not in selected_member_ids:
            selected_member_ids.append(member_id)
    if not availability_statuses:
        availability_statuses, default_notes = build_availability_defaults(members, raw_availability)
        availability_notes = availability_notes or default_notes

    heartlake_runs, heartlake_wickets = parse_score_pair(normalized.get("heartlake_score", ""))
    opponent_runs, opponent_wickets = parse_score_pair(normalized.get("opponent_score", ""))
    scorecard = dict(normalized.get("scorecard", {}))
    default_result = normalized.get("result", "TBD")
    merged_scorecard = default_scorecard(default_result)
    merged_scorecard.update(scorecard)
    merged_scorecard.setdefault("heartlake_runs", heartlake_runs)
    merged_scorecard.setdefault("heartlake_wickets", heartlake_wickets)
    merged_scorecard.setdefault("opponent_runs", opponent_runs)
    merged_scorecard.setdefault("opponent_wickets", opponent_wickets)
    if not merged_scorecard["heartlake_runs"] and heartlake_runs:
        merged_scorecard["heartlake_runs"] = heartlake_runs
    if not merged_scorecard["heartlake_wickets"] and heartlake_wickets:
        merged_scorecard["heartlake_wickets"] = heartlake_wickets
    if not merged_scorecard["opponent_runs"] and opponent_runs:
        merged_scorecard["opponent_runs"] = opponent_runs
    if not merged_scorecard["opponent_wickets"] and opponent_wickets:
        merged_scorecard["opponent_wickets"] = opponent_wickets

    details = default_match_details()
    details.update(normalized.get("details", {}))

    normalized["details"] = details
    normalized["scorecard"] = merged_scorecard
    normalized["availability_statuses"] = availability_statuses
    normalized["availability_notes"] = availability_notes
    normalized["availability"] = available_labels(availability_statuses, availability_notes)
    normalized["selected_playing_xi_member_ids"] = selected_member_ids
    normalized["selected_playing_xi"] = [
        member_id_to_name.get(member_id, member_id)
        for member_id in selected_member_ids
        if member_id_to_name.get(member_id, member_id)
    ]
    normalized["heartlake_score"] = compose_score(
        merged_scorecard["heartlake_runs"],
        merged_scorecard["heartlake_wickets"],
    )
    normalized["opponent_score"] = compose_score(
        merged_scorecard["opponent_runs"],
        merged_scorecard["opponent_wickets"],
    )
    normalized["result"] = merged_scorecard["result"]
    normalized["performances"] = [normalize_performance(item) for item in normalized.get("performances", [])]
    normalized["commentary"] = [normalize_commentary(item) for item in normalized.get("commentary", [])]
    normalized["scorebook"] = normalize_match_scorebook(normalized.get("scorebook"), normalized)
    sync_fixture_scorecard_from_scorebook(normalized)
    return normalized


def normalize_viewer_profile(profile: dict[str, Any] | None, club: dict[str, Any], members: list[dict[str, Any]]) -> dict[str, Any]:
    normalized = dict(DEFAULT_VIEWER_PROFILE)
    if isinstance(profile, dict):
        normalized.update({key: value for key, value in profile.items() if value is not None})
    normalized["primary_club_id"] = str(
        normalized.get("primary_club_id")
        or club.get("id")
        or DEFAULT_VIEWER_PROFILE["primary_club_id"]
    ).strip()
    normalized["primary_club_name"] = str(
        normalized.get("primary_club_name")
        or club.get("name")
        or DEFAULT_VIEWER_PROFILE["primary_club_name"]
    ).strip()
    followed = normalized.get("followed_player_names", [])
    if isinstance(followed, str):
        followed = [item.strip() for item in followed.split(",") if item.strip()]
    member_names = {member.get("name", "") for member in members}
    normalized["followed_player_names"] = [
        name for name in dict.fromkeys(str(name or "").strip() for name in followed) if name and name in member_names
    ]
    normalized["mobile"] = canonical_phone(normalized.get("mobile", ""))
    normalized["email"] = str(normalized.get("email", "") or "").strip()
    normalized["display_name"] = str(normalized.get("display_name", "") or "").strip()
    selected_season_year = str(normalized.get("selected_season_year", "") or "").strip()
    if not re.match(r"20\d{2}$", selected_season_year):
        selected_season_year = str(datetime.utcnow().year)
    normalized["selected_season_year"] = selected_season_year
    return normalized


def member_in_club(member: dict[str, Any], club_id: str = "", club_name: str = "") -> bool:
    target_id = str(club_id or "").strip().lower()
    target_name = str(club_name or "").strip().lower()
    memberships = member.get("club_memberships") or _member_club_memberships(member)
    for membership in memberships:
        membership_id = str(membership.get("club_id") or "").strip().lower()
        membership_name = str(membership.get("club_name") or "").strip().lower()
        if target_id and membership_id and membership_id == target_id:
            return True
        if target_name and membership_name and membership_name == target_name:
            return True
    primary_club_id = str(member.get("primary_club_id") or "").strip().lower()
    if target_id and primary_club_id and primary_club_id == target_id:
        return True
    primary_team_name = str(member.get("team_name") or "").strip().lower()
    if target_name and primary_team_name == target_name:
        return True
    return False


def normalize_store(store: dict[str, Any]) -> dict[str, Any]:
    logger.debug(
        "Normalizing store → members=%s fixtures=%s archives=%s duplicates=%s",
        len(store.get("members", []) or []),
        len(store.get("fixtures", []) or []),
        len(store.get("archive_uploads", []) or []),
        len(store.get("duplicate_uploads", []) or []),
    )
    normalized = dict(store)
    club = dict(normalized.get("club", {}))
    club.setdefault("id", "club-heartlake")
    club.setdefault("name", "Club")
    club.setdefault("short_name", "Club")
    club.setdefault("city", "Brampton")
    club.setdefault("country", "Canada")
    club.setdefault("season", _current_season_label())
    club.setdefault("home_ground", "Club Grounds")
    club.setdefault("whatsapp_number", "14165550123")
    club.setdefault("about", "Club cricket operations")
    normalized["club"] = club
    clubs = [dict(item) for item in normalized.get("clubs", []) if isinstance(item, dict)]
    if not any(str(item.get("id") or "").strip() == club["id"] for item in clubs):
        clubs.insert(0, dict(club))
    normalized["clubs"] = clubs

    members = [normalize_member(item) for item in normalized.get("members", [])]
    normalized["members"] = members
    fixtures = [normalize_fixture(item, members) for item in normalized.get("fixtures", [])]
    normalized["fixtures"] = fixtures
    normalized["archive_uploads"] = [normalize_archive(item) for item in normalized.get("archive_uploads", [])]
    for archive in normalized["archive_uploads"]:
        if archive_has_persisted_json(archive) and str(archive.get("status") or "").strip().lower() not in {"approved", "applied to match", "deleted"}:
            archive["status"] = "Approved"
            archive["confidence"] = archive.get("confidence") or "Persisted JSON"
    normalized["duplicate_uploads"] = [normalize_duplicate(item) for item in normalized.get("duplicate_uploads", [])]
    insights = dict(normalized.get("insights", {}))
    insights.setdefault("free_llm_mode", "heuristic")
    insights["ocr_status"] = "local OCR enabled" if local_ocr_available() else "filename-only draft review"
    insights["voice_commentary_status"] = "browser speech-to-text capture"
    normalized["insights"] = insights
    existing_teams = [dict(item) for item in normalized.get("teams", [])]
    if not any(team.get("name") == "Club" for team in existing_teams):
        existing_teams.insert(
            0,
            {
                "name": "Club",
                "type": "club",
                "display_name": club.get("name", "Club"),
            },
        )
    known_team_names = {team.get("name") for team in existing_teams}
    for member in members:
        team_name = member.get("team_name", "Club") or "Club"
        if team_name not in known_team_names:
            existing_teams.append(
                {
                    "name": team_name,
                    "type": "team",
                    "display_name": team_name,
                }
            )
            known_team_names.add(team_name)
    for fixture in fixtures:
        team_name = fixture.get("visiting_team") or fixture.get("opponent")
        if team_name and team_name not in known_team_names:
            existing_teams.append(
                {
                    "name": team_name,
                    "type": "visiting",
                    "display_name": team_name,
                }
            )
            known_team_names.add(team_name)
    normalized["teams"] = existing_teams
    normalized["viewer_profile"] = normalize_viewer_profile(normalized.get("viewer_profile"), club, members)
    return normalized


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def parse_scorecard_draft_from_name(file_name: str, match_id: str | None = None) -> dict[str, str]:
    draft = default_scorecard("Pending review")
    pattern = re.findall(r"(\d{2,3})[-_/](\d{1,2})", file_name)
    if len(pattern) >= 2:
        draft["heartlake_runs"], draft["heartlake_wickets"] = pattern[0]
        draft["opponent_runs"], draft["opponent_wickets"] = pattern[1]
        draft["result"] = "Recovered from filename pattern"
    elif match_id:
        draft["result"] = "Linked to scheduled match, awaiting manual review"
    return draft


def archive_record_from_file(
    path: Path,
    season: str,
    match_id: str = "",
    source: str = "filesystem",
    club_id: str = "",
    club_name: str = "",
    club_ids: list[str] | None = None,
    club_names: list[str] | None = None,
) -> dict[str, Any]:
    logger.debug(
        "Archive record from file → path=%s season=%s match_id=%s source=%s club_id=%s club_name=%s",
        str(path),
        season,
        match_id,
        source,
        club_id,
        club_name,
    )
    associated_ids = _dedupe_nonempty_strings(_coerce_archive_string_list(club_ids) + ([club_id] if club_id else []))
    associated_names = _dedupe_nonempty_strings(_coerce_archive_string_list(club_names) + ([club_name] if club_name else []))
    record = {
        "id": str(uuid.uuid4())[:8],
        "club_id": club_id,
        "club_name": club_name,
        "club_ids": associated_ids,
        "club_names": associated_names,
        "file_name": path.name,
        "file_path": str(path),
        "preview_url": f"/uploads/{path.name}",
        "file_hash": file_sha256(path),
        "file_size": path.stat().st_size,
        "match_id": match_id,
        "season": season,
        "status": "Ready for review",
        "confidence": "Draft only",
        "created_at": now_iso(),
        "source": source,
        "raw_extracted_text": "",
        "ocr_engine": "",
        "ocr_processed_at": "",
        "suggested_performances": [],
        "draft_scorecard": parse_scorecard_draft_from_name(path.name, match_id),
        "extracted_summary": "Image available locally. Review the draft scorecard, then apply it to a match to restore online records.",
    }
    return refresh_archive_dates(record)


def _duplicate_bundle_dir() -> Path:
    bundle_dir = DUPLICATE_DIR / f"{datetime.utcnow().strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:8]}"
    bundle_dir.mkdir(parents=True, exist_ok=True)
    return bundle_dir


def _copy_for_review(source_path: Path, target_path: Path) -> None:
    shutil.copy2(source_path, target_path)


def create_duplicate_record_from_paths(
    *,
    original_path: Path,
    duplicate_path: Path,
    file_hash: str,
    source: str,
    reason: str = "duplicate file hash",
) -> dict[str, Any]:
    review_dir = _duplicate_bundle_dir()
    original_review_path = review_dir / f"original_{original_path.name}"
    duplicate_review_path = review_dir / f"duplicate_{duplicate_path.name}"
    _copy_for_review(original_path, original_review_path)
    _copy_for_review(duplicate_path, duplicate_review_path)
    return {
        "id": str(uuid.uuid4())[:8],
        "created_at": now_iso(),
        "reason": reason,
        "source": source,
        "review_dir": str(review_dir),
        "original_file_name": original_path.name,
        "original_file_path": str(original_path),
        "original_review_path": str(original_review_path),
        "original_review_url": review_url_for_path(str(original_review_path)),
        "duplicate_file_name": duplicate_path.name,
        "duplicate_file_path": str(duplicate_path),
        "duplicate_review_path": str(duplicate_review_path),
        "duplicate_review_url": review_url_for_path(str(duplicate_review_path)),
        "file_hash": file_hash,
        "status": "Pending manual review",
    }


def create_duplicate_record_from_bytes(
    *,
    original_path: Path,
    duplicate_file_name: str,
    duplicate_content: bytes,
    file_hash: str,
    source: str,
    reason: str = "duplicate file hash",
) -> dict[str, Any]:
    review_dir = _duplicate_bundle_dir()
    original_review_path = review_dir / f"original_{original_path.name}"
    duplicate_review_name = Path(duplicate_file_name or "duplicate-upload").name
    duplicate_review_path = review_dir / f"duplicate_{duplicate_review_name}"
    _copy_for_review(original_path, original_review_path)
    duplicate_review_path.write_bytes(duplicate_content)
    return {
        "id": str(uuid.uuid4())[:8],
        "created_at": now_iso(),
        "reason": reason,
        "source": source,
        "review_dir": str(review_dir),
        "original_file_name": original_path.name,
        "original_file_path": str(original_path),
        "original_review_path": str(original_review_path),
        "original_review_url": review_url_for_path(str(original_review_path)),
        "duplicate_file_name": duplicate_review_name,
        "duplicate_file_path": "",
        "duplicate_review_path": str(duplicate_review_path),
        "duplicate_review_url": review_url_for_path(str(duplicate_review_path)),
        "file_hash": file_hash,
        "status": "Pending manual review",
    }


def _connection() -> sqlite3.Connection:
    DATABASE_FILE.parent.mkdir(exist_ok=True)
    connection = sqlite3.connect(DATABASE_FILE, timeout=60)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA journal_mode = WAL")
    connection.execute("PRAGMA synchronous = NORMAL")
    connection.execute("PRAGMA busy_timeout = 60000")
    return connection


def _slug_token(value: str, fallback: str = "item") -> str:
    text = re.sub(r"[^a-z0-9]+", "-", str(value or "").strip().lower()).strip("-")
    return text or fallback


def _club_row_id(club: dict[str, Any]) -> str:
    explicit = str(club.get("id", "") or "").strip()
    if explicit:
        return explicit
    return f"club-{_slug_token(club.get('short_name') or club.get('name') or 'heartlake', 'club')}"


def _team_row_id(team: dict[str, Any], club_id: str = "") -> str:
    explicit = str(team.get("id", "") or "").strip()
    if explicit:
        return explicit
    club_token = _slug_token(club_id, "") if club_id else ""
    team_token = _slug_token(team.get("name") or team.get("display_name") or "team", "team")
    return f"team-{club_token + '-' if club_token else ''}{team_token}"


def _member_team_memberships(member: dict[str, Any]) -> list[dict[str, Any]]:
    memberships: list[dict[str, Any]] = []
    seen: set[str] = set()
    primary_team = str(member.get("team_name") or "Club").strip()

    def append_membership(
        team_name: str,
        *,
        is_primary: bool = False,
        club_id: str = "",
        club_name: str = "",
        team_type: str = "",
        display_name: str = "",
    ) -> None:
        clean_name = str(team_name or "").strip()
        if not clean_name:
            return
        key = clean_name.lower()
        if key in seen:
            for existing in memberships:
                if existing["team_name"].lower() == key:
                    existing["is_primary"] = existing["is_primary"] or is_primary
                    if club_id and not existing.get("club_id"):
                        existing["club_id"] = club_id
                    if club_name and not existing.get("club_name"):
                        existing["club_name"] = club_name
                    if team_type and not existing.get("team_type"):
                        existing["team_type"] = team_type
                    if display_name and not existing.get("display_name"):
                        existing["display_name"] = display_name
            return
        seen.add(key)
        membership = {"team_name": clean_name, "is_primary": bool(is_primary)}
        if club_id:
            membership["club_id"] = str(club_id).strip()
        if club_name:
            membership["club_name"] = str(club_name).strip()
        if team_type:
            membership["team_type"] = str(team_type).strip()
        if display_name:
            membership["display_name"] = str(display_name).strip()
        memberships.append(membership)

    append_membership(
        primary_team,
        is_primary=True,
        club_id=str(member.get("primary_club_id") or "").strip(),
        club_name=str(member.get("primary_club_name") or "").strip(),
        display_name=str(member.get("primary_club_name") or member.get("team_name") or primary_team).strip(),
        team_type="club" if str(member.get("primary_club_id") or "").strip() else "",
    )
    for raw in member.get("team_memberships", []) or member.get("memberships", []) or []:
        if isinstance(raw, str):
            append_membership(raw, is_primary=str(raw).strip() == primary_team)
            continue
        if isinstance(raw, dict):
            append_membership(
                raw.get("team_name") or raw.get("name") or raw.get("display_name") or "",
                is_primary=bool(raw.get("is_primary")),
                club_id=str(raw.get("club_id") or "").strip(),
                club_name=str(raw.get("club_name") or "").strip(),
                team_type=str(raw.get("team_type") or "").strip(),
                display_name=str(raw.get("display_name") or "").strip(),
            )
    return memberships


def _member_club_memberships(member: dict[str, Any], default_club_name: str = "") -> list[dict[str, Any]]:
    grouped: dict[str, dict[str, Any]] = {}
    memberships = member.get("team_memberships", []) or []
    for raw in memberships:
        if not isinstance(raw, dict):
            continue
        club_name = str(raw.get("club_name") or "").strip()
        if not club_name and default_club_name and raw.get("is_primary"):
            club_name = default_club_name
        if not club_name:
            continue
        key = club_name.lower()
        entry = grouped.setdefault(
            key,
            {
                "club_id": str(raw.get("club_id") or "").strip(),
                "club_name": club_name,
                "teams": [],
            },
        )
        team_name = str(raw.get("team_name") or raw.get("display_name") or "").strip()
        if team_name and team_name not in entry["teams"]:
            entry["teams"].append(team_name)
    return sorted(grouped.values(), key=lambda item: item["club_name"])


def _schema_tables() -> str:
    return """
    CREATE TABLE IF NOT EXISTS clubs (
      id TEXT PRIMARY KEY,
      name TEXT NOT NULL,
      short_name TEXT,
      city TEXT,
      country TEXT,
      season TEXT,
      home_ground TEXT,
      whatsapp_number TEXT,
      about TEXT
    );

    CREATE TABLE IF NOT EXISTS teams (
      id TEXT PRIMARY KEY,
      club_id TEXT,
      name TEXT NOT NULL,
      type TEXT,
      display_name TEXT,
      FOREIGN KEY (club_id) REFERENCES clubs(id) ON DELETE SET NULL
    );

    CREATE TABLE IF NOT EXISTS app_user_profile (
      id INTEGER PRIMARY KEY CHECK (id = 1),
      display_name TEXT,
      mobile TEXT,
      email TEXT,
      primary_club_id TEXT,
      selected_season_year TEXT,
      FOREIGN KEY (primary_club_id) REFERENCES clubs(id) ON DELETE SET NULL
    );

    CREATE TABLE IF NOT EXISTS app_followed_players (
      user_id INTEGER NOT NULL DEFAULT 1,
      member_id TEXT NOT NULL,
      PRIMARY KEY (user_id, member_id),
      FOREIGN KEY (member_id) REFERENCES members(id) ON DELETE CASCADE
    );

    CREATE TABLE IF NOT EXISTS members (
      id TEXT PRIMARY KEY,
      name TEXT NOT NULL,
      full_name TEXT,
      gender TEXT,
      age INTEGER,
      role TEXT,
      batting_style TEXT,
      bowling_style TEXT,
      picture TEXT,
      notes TEXT,
      phone TEXT,
      email TEXT,
      picture_url TEXT,
      jersey_number TEXT
    );

    CREATE TABLE IF NOT EXISTS member_aliases (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      member_id TEXT NOT NULL,
      alias TEXT NOT NULL,
      UNIQUE(member_id, alias),
      FOREIGN KEY (member_id) REFERENCES members(id) ON DELETE CASCADE
    );

    CREATE TABLE IF NOT EXISTS team_memberships (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      member_id TEXT NOT NULL,
      team_id TEXT NOT NULL,
      is_primary INTEGER NOT NULL DEFAULT 0,
      UNIQUE(member_id, team_id),
      FOREIGN KEY (member_id) REFERENCES members(id) ON DELETE CASCADE,
      FOREIGN KEY (team_id) REFERENCES teams(id) ON DELETE CASCADE
    );

    CREATE TABLE IF NOT EXISTS fixtures (
      id TEXT PRIMARY KEY,
      club_id TEXT,
      date TEXT,
      date_label TEXT,
      opponent TEXT,
      visiting_team TEXT,
      opponent_team_id TEXT,
      heartlake_captain_member_id TEXT,
      heartlake_captain_name TEXT,
      status TEXT,
      heartlake_score TEXT,
      opponent_score TEXT,
      result TEXT,
      venue TEXT,
      match_type TEXT,
      scheduled_time TEXT,
      overs TEXT,
      toss_winner TEXT,
      toss_decision TEXT,
      weather TEXT,
      umpires TEXT,
      scorer TEXT,
      whatsapp_thread TEXT,
      notes TEXT,
      availability_seed_json TEXT,
      created_by_user_id INTEGER,
      created_at TEXT,
      updated_by_user_id INTEGER,
      updated_at TEXT,
      FOREIGN KEY (club_id) REFERENCES clubs(id) ON DELETE SET NULL,
      FOREIGN KEY (opponent_team_id) REFERENCES teams(id) ON DELETE SET NULL,
      FOREIGN KEY (heartlake_captain_member_id) REFERENCES members(id) ON DELETE SET NULL
    );

    CREATE TABLE IF NOT EXISTS fixture_scorecards (
      fixture_id TEXT PRIMARY KEY,
      heartlake_runs TEXT,
      heartlake_wickets TEXT,
      heartlake_overs TEXT,
      opponent_runs TEXT,
      opponent_wickets TEXT,
      opponent_overs TEXT,
      result TEXT,
      live_summary TEXT,
      FOREIGN KEY (fixture_id) REFERENCES fixtures(id) ON DELETE CASCADE
    );

    CREATE TABLE IF NOT EXISTS fixture_availability (
      fixture_id TEXT NOT NULL,
      member_id TEXT NOT NULL,
      status TEXT,
      note TEXT,
      PRIMARY KEY (fixture_id, member_id),
      FOREIGN KEY (fixture_id) REFERENCES fixtures(id) ON DELETE CASCADE,
      FOREIGN KEY (member_id) REFERENCES members(id) ON DELETE CASCADE
    );

    CREATE TABLE IF NOT EXISTS fixture_playing_xi (
      fixture_id TEXT NOT NULL,
      member_id TEXT NOT NULL,
      slot_number INTEGER NOT NULL DEFAULT 0,
      PRIMARY KEY (fixture_id, member_id),
      FOREIGN KEY (fixture_id) REFERENCES fixtures(id) ON DELETE CASCADE,
      FOREIGN KEY (member_id) REFERENCES members(id) ON DELETE CASCADE
    );

    CREATE TABLE IF NOT EXISTS fixture_performances (
      id TEXT PRIMARY KEY,
      fixture_id TEXT NOT NULL,
      member_id TEXT,
      player_name TEXT,
      runs INTEGER,
      balls INTEGER,
      wickets INTEGER,
      catches INTEGER,
      fours INTEGER,
      sixes INTEGER,
      notes TEXT,
      source TEXT,
      archive_upload_id TEXT,
      FOREIGN KEY (fixture_id) REFERENCES fixtures(id) ON DELETE CASCADE,
      FOREIGN KEY (member_id) REFERENCES members(id) ON DELETE SET NULL
    );

    CREATE TABLE IF NOT EXISTS fixture_commentary (
      id TEXT PRIMARY KEY,
      fixture_id TEXT NOT NULL,
      mode TEXT,
      text TEXT,
      created_at TEXT,
      FOREIGN KEY (fixture_id) REFERENCES fixtures(id) ON DELETE CASCADE
    );

    CREATE TABLE IF NOT EXISTS fixture_scorebook_innings (
      fixture_id TEXT NOT NULL,
      inning_number INTEGER NOT NULL,
      batting_team TEXT,
      bowling_team TEXT,
      overs_limit INTEGER,
      status TEXT,
      target_runs INTEGER,
      PRIMARY KEY (fixture_id, inning_number),
      FOREIGN KEY (fixture_id) REFERENCES fixtures(id) ON DELETE CASCADE
    );

    CREATE TABLE IF NOT EXISTS fixture_scorebook_batters (
      fixture_id TEXT NOT NULL,
      inning_number INTEGER NOT NULL,
      slot_number INTEGER NOT NULL,
      player_name TEXT,
      PRIMARY KEY (fixture_id, inning_number, slot_number),
      FOREIGN KEY (fixture_id, inning_number) REFERENCES fixture_scorebook_innings(fixture_id, inning_number) ON DELETE CASCADE
    );

    CREATE TABLE IF NOT EXISTS fixture_scorebook_bowlers (
      fixture_id TEXT NOT NULL,
      inning_number INTEGER NOT NULL,
      slot_number INTEGER NOT NULL,
      player_name TEXT,
      PRIMARY KEY (fixture_id, inning_number, slot_number),
      FOREIGN KEY (fixture_id, inning_number) REFERENCES fixture_scorebook_innings(fixture_id, inning_number) ON DELETE CASCADE
    );

    CREATE TABLE IF NOT EXISTS fixture_scorebook_balls (
      id TEXT PRIMARY KEY,
      fixture_id TEXT NOT NULL,
      inning_number INTEGER NOT NULL,
      over_number INTEGER,
      ball_number INTEGER,
      striker TEXT,
      non_striker TEXT,
      bowler TEXT,
      runs_bat INTEGER,
      extras_type TEXT,
      extras_runs INTEGER,
      wicket INTEGER,
      wicket_type TEXT,
      wicket_player TEXT,
      fielder TEXT,
      commentary TEXT,
      created_at TEXT,
      FOREIGN KEY (fixture_id, inning_number) REFERENCES fixture_scorebook_innings(fixture_id, inning_number) ON DELETE CASCADE
    );

    CREATE TABLE IF NOT EXISTS archives (
      id TEXT PRIMARY KEY,
      club_id TEXT,
      club_ids TEXT,
      club_names TEXT,
      match_id TEXT,
      applied_to_match_id TEXT,
      season TEXT,
      status TEXT,
      confidence TEXT,
      created_at TEXT,
      preview_url TEXT,
      file_name TEXT,
      file_path TEXT,
      file_hash TEXT,
      file_size INTEGER,
      source TEXT,
      scorecard_date TEXT,
      photo_taken_at TEXT,
      photo_date_source TEXT,
      archive_date TEXT,
      archive_year TEXT,
      archive_date_source TEXT,
      raw_extracted_text TEXT,
      ocr_engine TEXT,
      ocr_processed_at TEXT,
      ocr_pipeline TEXT,
      extracted_summary TEXT,
      review_template_json TEXT,
      review_source_json TEXT,
      review_llm_model TEXT,
      review_llm_notes TEXT,
      review_llm_assessment TEXT,
      FOREIGN KEY (club_id) REFERENCES clubs(id) ON DELETE SET NULL
    );

    CREATE TABLE IF NOT EXISTS archive_scorecards (
      archive_id TEXT PRIMARY KEY,
      heartlake_runs TEXT,
      heartlake_wickets TEXT,
      heartlake_overs TEXT,
      opponent_runs TEXT,
      opponent_wickets TEXT,
      opponent_overs TEXT,
      result TEXT,
      live_summary TEXT,
      FOREIGN KEY (archive_id) REFERENCES archives(id) ON DELETE CASCADE
    );

    CREATE TABLE IF NOT EXISTS archive_performances (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      archive_id TEXT NOT NULL,
      member_id TEXT,
      player_name TEXT,
      runs INTEGER,
      balls INTEGER,
      wickets INTEGER,
      catches INTEGER,
      fours INTEGER,
      sixes INTEGER,
      notes TEXT,
      source TEXT,
      confidence TEXT,
      FOREIGN KEY (archive_id) REFERENCES archives(id) ON DELETE CASCADE,
      FOREIGN KEY (member_id) REFERENCES members(id) ON DELETE SET NULL
    );

    CREATE TABLE IF NOT EXISTS duplicate_uploads (
      id TEXT PRIMARY KEY,
      created_at TEXT,
      reason TEXT,
      source TEXT,
      review_dir TEXT,
      original_file_name TEXT,
      original_file_path TEXT,
      original_review_path TEXT,
      original_review_url TEXT,
      duplicate_file_name TEXT,
      duplicate_file_path TEXT,
      duplicate_review_path TEXT,
      duplicate_review_url TEXT,
      file_hash TEXT,
      status TEXT
    );

    CREATE TABLE IF NOT EXISTS app_insights (
      id INTEGER PRIMARY KEY CHECK (id = 1),
      free_llm_mode TEXT,
      ocr_status TEXT,
      voice_commentary_status TEXT
    );

    CREATE TABLE IF NOT EXISTS member_summary_stats (
      member_id TEXT PRIMARY KEY,
      player_name TEXT NOT NULL,
      full_name TEXT,
      matches INTEGER,
      batting_innings INTEGER,
      outs INTEGER,
      runs INTEGER,
      balls INTEGER,
      batting_average REAL,
      strike_rate REAL,
      wickets INTEGER,
      catches INTEGER,
      fours INTEGER,
      sixes INTEGER,
      highest_score INTEGER,
      scores_25_plus INTEGER,
      scores_50_plus INTEGER,
      scores_100_plus INTEGER,
      last_game_date TEXT,
      last_opponent TEXT,
      next_game_date TEXT,
      next_opponent TEXT,
      updated_at TEXT,
      FOREIGN KEY (member_id) REFERENCES members(id) ON DELETE CASCADE
    );

    CREATE TABLE IF NOT EXISTS member_year_stats (
      member_id TEXT NOT NULL,
      season_year TEXT NOT NULL,
      player_name TEXT NOT NULL,
      full_name TEXT,
      matches INTEGER,
      batting_innings INTEGER,
      outs INTEGER,
      runs INTEGER,
      balls INTEGER,
      batting_average REAL,
      strike_rate REAL,
      wickets INTEGER,
      catches INTEGER,
      fours INTEGER,
      sixes INTEGER,
      highest_score INTEGER,
      scores_25_plus INTEGER,
      scores_50_plus INTEGER,
      scores_100_plus INTEGER,
      updated_at TEXT,
      PRIMARY KEY (member_id, season_year),
      FOREIGN KEY (member_id) REFERENCES members(id) ON DELETE CASCADE
    );

    CREATE TABLE IF NOT EXISTS member_club_stats (
      member_id TEXT NOT NULL,
      club_id TEXT NOT NULL,
      player_name TEXT NOT NULL,
      full_name TEXT,
      club_name TEXT,
      matches INTEGER,
      batting_innings INTEGER,
      outs INTEGER,
      runs INTEGER,
      balls INTEGER,
      batting_average REAL,
      strike_rate REAL,
      wickets INTEGER,
      catches INTEGER,
      fours INTEGER,
      sixes INTEGER,
      highest_score INTEGER,
      scores_25_plus INTEGER,
      scores_50_plus INTEGER,
      scores_100_plus INTEGER,
      updated_at TEXT,
      PRIMARY KEY (member_id, club_id),
      FOREIGN KEY (member_id) REFERENCES members(id) ON DELETE CASCADE,
      FOREIGN KEY (club_id) REFERENCES clubs(id) ON DELETE CASCADE
    );

    CREATE TABLE IF NOT EXISTS club_summary_stats (
      club_id TEXT PRIMARY KEY,
      club_name TEXT NOT NULL,
      season_year TEXT,
      member_count INTEGER,
      team_count INTEGER,
      fixture_count INTEGER,
      archive_count INTEGER,
      total_runs INTEGER,
      total_wickets INTEGER,
      total_catches INTEGER,
      highest_score INTEGER,
      top_batter TEXT,
      top_batter_runs INTEGER,
      scores_25_plus INTEGER,
      scores_50_plus INTEGER,
      scores_100_plus INTEGER,
      updated_at TEXT,
      FOREIGN KEY (club_id) REFERENCES clubs(id) ON DELETE CASCADE
    );

    CREATE TABLE IF NOT EXISTS club_year_stats (
      club_id TEXT NOT NULL,
      season_year TEXT NOT NULL,
      club_name TEXT NOT NULL,
      member_count INTEGER,
      fixture_count INTEGER,
      archive_count INTEGER,
      total_runs INTEGER,
      total_wickets INTEGER,
      total_catches INTEGER,
      highest_score INTEGER,
      top_batter TEXT,
      top_batter_runs INTEGER,
      scores_25_plus INTEGER,
      scores_50_plus INTEGER,
      scores_100_plus INTEGER,
      updated_at TEXT,
      PRIMARY KEY (club_id, season_year),
      FOREIGN KEY (club_id) REFERENCES clubs(id) ON DELETE CASCADE
    );

    CREATE TABLE IF NOT EXISTS llm_documents (
      id TEXT PRIMARY KEY,
      doc_type TEXT NOT NULL,
      source_id TEXT,
      club_id TEXT,
      season_year TEXT,
      title TEXT,
      content TEXT,
      content_hash TEXT,
      embedding_model TEXT,
      embedding_json TEXT,
      source_json TEXT,
      updated_at TEXT
    );

    CREATE TABLE IF NOT EXISTS llm_query_cache (
      id TEXT PRIMARY KEY,
      question TEXT NOT NULL,
      answer TEXT NOT NULL,
      mode TEXT,
      source_provider TEXT,
      source_label TEXT,
      prompt_name TEXT,
      context_hash TEXT,
      created_at TEXT,
      updated_at TEXT
    );

    CREATE INDEX IF NOT EXISTS idx_member_aliases_alias ON member_aliases(alias);
    CREATE INDEX IF NOT EXISTS idx_team_memberships_member ON team_memberships(member_id);
    CREATE INDEX IF NOT EXISTS idx_team_memberships_team ON team_memberships(team_id);
    CREATE INDEX IF NOT EXISTS idx_fixtures_date ON fixtures(date);
    CREATE INDEX IF NOT EXISTS idx_fixture_playing_xi_fixture ON fixture_playing_xi(fixture_id, slot_number);
    CREATE INDEX IF NOT EXISTS idx_fixture_performances_member ON fixture_performances(member_id);
    CREATE INDEX IF NOT EXISTS idx_fixture_scorebook_balls_fixture ON fixture_scorebook_balls(fixture_id, inning_number);
    CREATE INDEX IF NOT EXISTS idx_archive_performances_member ON archive_performances(member_id);
    CREATE INDEX IF NOT EXISTS idx_archives_file_hash ON archives(file_hash);
    CREATE INDEX IF NOT EXISTS idx_member_summary_stats_name ON member_summary_stats(player_name);
    CREATE INDEX IF NOT EXISTS idx_member_year_stats_year ON member_year_stats(season_year);
    CREATE INDEX IF NOT EXISTS idx_member_club_stats_club ON member_club_stats(club_id);
    CREATE INDEX IF NOT EXISTS idx_club_summary_stats_name ON club_summary_stats(club_name);
    CREATE INDEX IF NOT EXISTS idx_club_year_stats_year ON club_year_stats(season_year);
    CREATE INDEX IF NOT EXISTS idx_llm_documents_type ON llm_documents(doc_type);
    CREATE INDEX IF NOT EXISTS idx_llm_documents_source ON llm_documents(source_id);
    CREATE INDEX IF NOT EXISTS idx_llm_documents_club ON llm_documents(club_id);
    CREATE INDEX IF NOT EXISTS idx_llm_query_cache_question ON llm_query_cache(question);
    CREATE INDEX IF NOT EXISTS idx_llm_query_cache_context ON llm_query_cache(context_hash);
    """


def _relational_tables_have_data(connection: sqlite3.Connection) -> bool:
    try:
        row = connection.execute("SELECT 1 FROM clubs LIMIT 1").fetchone()
        return row is not None
    except sqlite3.OperationalError:
        return False


def _legacy_state_from_connection(connection: sqlite3.Connection) -> dict[str, Any]:
    table = connection.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'app_state'"
    ).fetchone()
    if table:
        row = connection.execute("SELECT state_json FROM app_state WHERE id = 1").fetchone()
        if row and row["state_json"]:
            return json.loads(row["state_json"])
    with open(DATA_FILE, "r", encoding="utf-8") as handle:
        return json.load(handle)


def _clear_relational_state(connection: sqlite3.Connection) -> None:
    for table_name in [
        "app_followed_players",
        "app_user_profile",
        "fixture_scorebook_balls",
        "fixture_scorebook_bowlers",
        "fixture_scorebook_batters",
        "fixture_scorebook_innings",
        "fixture_commentary",
        "fixture_performances",
        "fixture_availability",
        "fixture_scorecards",
        "fixtures",
        "fixture_playing_xi",
        "archive_performances",
        "archive_scorecards",
        "archives",
        "duplicate_uploads",
        "club_year_stats",
        "club_summary_stats",
        "member_club_stats",
        "member_year_stats",
        "member_summary_stats",
        "llm_query_cache",
        "llm_documents",
        "team_memberships",
        "member_aliases",
        "members",
        "teams",
        "clubs",
        "app_insights",
    ]:
        connection.execute(f"DELETE FROM {table_name}")


def _normalized_clubs(store: dict[str, Any]) -> tuple[list[dict[str, Any]], str]:
    normalized = normalize_store(store)
    primary = dict(normalized.get("club", {}))
    candidates = [primary]
    for club in normalized.get("clubs", []):
        if isinstance(club, dict):
            candidates.append(dict(club))

    clubs: list[dict[str, Any]] = []
    seen: set[str] = set()
    primary_id = ""
    for candidate in candidates:
        if not candidate:
            continue
        row = {
            "id": _club_row_id(candidate),
            "name": candidate.get("name") or primary.get("name") or "Club",
            "short_name": candidate.get("short_name") or primary.get("short_name") or "Club",
            "city": candidate.get("city") or primary.get("city") or "Brampton",
            "country": candidate.get("country") or primary.get("country") or "Canada",
            "season": candidate.get("season") or primary.get("season") or "2026 Summer Season",
            "home_ground": candidate.get("home_ground") or primary.get("home_ground") or "Club Grounds",
            "whatsapp_number": candidate.get("whatsapp_number") or primary.get("whatsapp_number") or "",
            "about": candidate.get("about") or primary.get("about") or "",
        }
        if row["id"] in seen:
            continue
        seen.add(row["id"])
        clubs.append(row)
        if not primary_id:
            primary_id = row["id"]
    return clubs, primary_id


def _write_relational_state(connection: sqlite3.Connection, store: dict[str, Any]) -> None:
    normalized = normalize_store(store)
    clubs, primary_club_id = _normalized_clubs(normalized)
    viewer_profile = normalize_viewer_profile(normalized.get("viewer_profile"), normalized.get("club", {}), normalized.get("members", []))
    members = normalized.get("members", [])
    fixtures = normalized.get("fixtures", [])
    archives = normalized.get("archive_uploads", [])
    duplicates = normalized.get("duplicate_uploads", []) or []
    teams = list(normalized.get("teams", []))

    team_names_seen = {str(team.get("name") or "").strip().lower() for team in teams}
    for member in members:
        for membership in _member_team_memberships(member):
            team_name = membership["team_name"]
            if team_name.lower() not in team_names_seen:
                teams.append({"name": team_name, "type": "team", "display_name": team_name})
                team_names_seen.add(team_name.lower())

    club_name_to_id = {
        str(club["name"]).strip().lower(): club["id"]
        for club in clubs
    }
    club_name_to_id.update(
        {
            str(club["short_name"]).strip().lower(): club["id"]
            for club in clubs
            if str(club.get("short_name", "")).strip()
        }
    )

    team_rows: list[dict[str, Any]] = []
    team_name_to_id: dict[str, str] = {}
    for team in teams:
        name = str(team.get("name") or team.get("display_name") or "").strip()
        if not name:
            continue
        raw_club_key = str(team.get("club_name") or team.get("club") or team.get("club_id") or "").strip().lower()
        resolved_club_id = club_name_to_id.get(raw_club_key, "")
        if not resolved_club_id and team.get("type") == "club":
            resolved_club_id = primary_club_id
        row = {
            "id": _team_row_id(team, resolved_club_id),
            "club_id": resolved_club_id or None,
            "name": name,
            "type": str(team.get("type") or "team"),
            "display_name": str(team.get("display_name") or name),
        }
        if name.lower() in team_name_to_id:
            continue
        team_rows.append(row)
        team_name_to_id[name.lower()] = row["id"]

    member_name_to_id = {str(member.get("name") or "").strip(): str(member.get("id") or "") for member in members}

    with connection:
        connection.executescript(_schema_tables())
        auth_user_links = [
            dict(row)
            for row in connection.execute(
                "SELECT id, member_id, primary_club_id FROM app_users"
            ).fetchall()
        ]
        auth_session_links = [
            dict(row)
            for row in connection.execute(
                "SELECT token, current_club_id FROM app_auth_sessions"
            ).fetchall()
        ]
        player_season_availability_links = [
            dict(row)
            for row in connection.execute(
                """
                SELECT user_id, club_id, status, note, updated_at
                FROM app_player_season_availability
                """
            ).fetchall()
        ]
        _clear_relational_state(connection)

        connection.executemany(
            """
            INSERT INTO clubs (id, name, short_name, city, country, season, home_ground, whatsapp_number, about)
            VALUES (:id, :name, :short_name, :city, :country, :season, :home_ground, :whatsapp_number, :about)
            """,
            clubs,
        )

        connection.execute(
            """
            INSERT INTO app_user_profile (id, display_name, mobile, email, primary_club_id, selected_season_year)
            VALUES (1, ?, ?, ?, ?, ?)
            """,
            (
                viewer_profile.get("display_name", ""),
                viewer_profile.get("mobile", ""),
                viewer_profile.get("email", ""),
                viewer_profile.get("primary_club_id", primary_club_id or ""),
                viewer_profile.get("selected_season_year", str(datetime.utcnow().year)),
            ),
        )

        if normalized.get("insights"):
            connection.execute(
                """
                INSERT INTO app_insights (id, free_llm_mode, ocr_status, voice_commentary_status)
                VALUES (1, ?, ?, ?)
                """,
                (
                    normalized["insights"].get("free_llm_mode", ""),
                    normalized["insights"].get("ocr_status", ""),
                    normalized["insights"].get("voice_commentary_status", ""),
                ),
            )

        connection.executemany(
            """
            INSERT INTO teams (id, club_id, name, type, display_name)
            VALUES (:id, :club_id, :name, :type, :display_name)
            """,
            team_rows,
        )

        for member in members:
            connection.execute(
                """
                INSERT INTO members (
                  id, name, full_name, gender, age, role, batting_style, bowling_style, picture, notes,
                  phone, email, picture_url, jersey_number
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    member.get("id", ""),
                    member.get("name", ""),
                    member.get("full_name", ""),
                    member.get("gender", ""),
                    int(member.get("age", 0) or 0),
                    member.get("role", ""),
                    member.get("batting_style", ""),
                    member.get("bowling_style", ""),
                    member.get("picture", ""),
                    member.get("notes", ""),
                    member.get("phone", ""),
                    member.get("email", ""),
                    member.get("picture_url", ""),
                    member.get("jersey_number", ""),
                ),
            )
            for alias in member.get("aliases", []):
                clean_alias = str(alias or "").strip()
                if not clean_alias:
                    continue
                connection.execute(
                    "INSERT INTO member_aliases (member_id, alias) VALUES (?, ?)",
                    (member.get("id", ""), clean_alias),
                )
            for membership in _member_team_memberships(member):
                team_id = team_name_to_id.get(membership["team_name"].lower())
                if not team_id:
                    continue
                connection.execute(
                    """
                    INSERT INTO team_memberships (member_id, team_id, is_primary)
                    VALUES (?, ?, ?)
                    """,
                    (member.get("id", ""), team_id, 1 if membership["is_primary"] else 0),
                )

        for player_name in viewer_profile.get("followed_player_names", []):
            member_id = member_name_to_id.get(player_name)
            if not member_id:
                continue
            connection.execute(
                """
                INSERT INTO app_followed_players (user_id, member_id)
                VALUES (1, ?)
                """,
                (member_id,),
            )

        for fixture in fixtures:
            details = fixture.get("details", {})
            captain_name = str(fixture.get("heartlake_captain", "") or "").strip()
            captain_member_id = member_name_to_id.get(captain_name, "")
            opponent_team_id = team_name_to_id.get(str(fixture.get("visiting_team") or fixture.get("opponent") or "").strip().lower())
            availability_seed = fixture.get("availability_seed")
            if availability_seed is None:
                availability_seed = fixture.get("availability", [])
            connection.execute(
                """
                INSERT INTO fixtures (
                  id, club_id, date, date_label, opponent, visiting_team, opponent_team_id,
                  heartlake_captain_member_id, heartlake_captain_name, status, heartlake_score, opponent_score,
                  result, venue, match_type, scheduled_time, overs, toss_winner, toss_decision, weather,
                  umpires, scorer, whatsapp_thread, notes, availability_seed_json,
                  created_by_user_id, created_at, updated_by_user_id, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    fixture.get("id", ""),
                    fixture.get("club_id") or primary_club_id or None,
                    fixture.get("date", ""),
                    fixture.get("date_label", ""),
                    fixture.get("opponent", ""),
                    fixture.get("visiting_team", ""),
                    opponent_team_id,
                    captain_member_id or None,
                    captain_name,
                    fixture.get("status", ""),
                    fixture.get("heartlake_score", ""),
                    fixture.get("opponent_score", ""),
                    fixture.get("result", ""),
                    details.get("venue", ""),
                    details.get("match_type", ""),
                    details.get("scheduled_time", ""),
                    details.get("overs", ""),
                    details.get("toss_winner", ""),
                    details.get("toss_decision", ""),
                    details.get("weather", ""),
                    details.get("umpires", ""),
                    details.get("scorer", ""),
                    details.get("whatsapp_thread", ""),
                    details.get("notes", ""),
                    json.dumps(list(availability_seed or [])),
                    fixture.get("created_by_user_id") or None,
                    fixture.get("created_at") or None,
                    fixture.get("updated_by_user_id") or None,
                    fixture.get("updated_at") or None,
                ),
            )

            scorecard = fixture.get("scorecard", {})
            connection.execute(
                """
                INSERT INTO fixture_scorecards (
                  fixture_id, heartlake_runs, heartlake_wickets, heartlake_overs,
                  opponent_runs, opponent_wickets, opponent_overs, result, live_summary
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    fixture.get("id", ""),
                    scorecard.get("heartlake_runs", ""),
                    scorecard.get("heartlake_wickets", ""),
                    scorecard.get("heartlake_overs", ""),
                    scorecard.get("opponent_runs", ""),
                    scorecard.get("opponent_wickets", ""),
                    scorecard.get("opponent_overs", ""),
                    scorecard.get("result", ""),
                    scorecard.get("live_summary", ""),
                ),
            )

            availability_statuses = fixture.get("availability_statuses", {})
            availability_notes = fixture.get("availability_notes", {})
            for member_name, status in availability_statuses.items():
                member_id = member_name_to_id.get(member_name)
                if not member_id:
                    continue
                connection.execute(
                    """
                    INSERT INTO fixture_availability (fixture_id, member_id, status, note)
                    VALUES (?, ?, ?, ?)
                    """,
                    (
                        fixture.get("id", ""),
                        member_id,
                        status,
                        availability_notes.get(member_name, ""),
                    ),
                )

            selected_playing_xi = fixture.get("selected_playing_xi_member_ids")
            if selected_playing_xi is None:
                selected_playing_xi = fixture.get("selected_playing_xi", [])
            if isinstance(selected_playing_xi, str):
                selected_playing_xi = [item.strip() for item in selected_playing_xi.split(",") if item.strip()]
            for slot_number, player_identifier in enumerate(list(selected_playing_xi or []), start=1):
                player_key = str(player_identifier or "").strip()
                if not player_key:
                    continue
                member_id = player_key if player_key in member_name_to_id.values() else member_name_to_id.get(player_key, "")
                if not member_id:
                    continue
                connection.execute(
                    """
                    INSERT INTO fixture_playing_xi (fixture_id, member_id, slot_number)
                    VALUES (?, ?, ?)
                    """,
                    (
                        fixture.get("id", ""),
                        member_id,
                        slot_number,
                    ),
                )

            for performance in fixture.get("performances", []):
                connection.execute(
                    """
                    INSERT INTO fixture_performances (
                      id, fixture_id, member_id, player_name, runs, balls, wickets, catches,
                      fours, sixes, notes, source, archive_upload_id
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        performance.get("id", str(uuid.uuid4())[:8]),
                        fixture.get("id", ""),
                        member_name_to_id.get(performance.get("player_name", "")) or None,
                        performance.get("player_name", ""),
                        int(performance.get("runs", 0) or 0),
                        int(performance.get("balls", 0) or 0),
                        int(performance.get("wickets", 0) or 0),
                        int(performance.get("catches", 0) or 0),
                        int(performance.get("fours", 0) or 0),
                        int(performance.get("sixes", 0) or 0),
                        performance.get("notes", ""),
                        performance.get("source", ""),
                        performance.get("archive_upload_id", ""),
                    ),
                )

            for commentary in fixture.get("commentary", []):
                connection.execute(
                    """
                    INSERT INTO fixture_commentary (id, fixture_id, mode, text, created_at)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        commentary.get("id", str(uuid.uuid4())[:8]),
                        fixture.get("id", ""),
                        commentary.get("mode", "text"),
                        commentary.get("text", ""),
                        commentary.get("created_at", now_iso()),
                    ),
                )

            for innings in (fixture.get("scorebook", {}) or {}).get("innings", []):
                connection.execute(
                    """
                    INSERT INTO fixture_scorebook_innings (
                      fixture_id, inning_number, batting_team, bowling_team, overs_limit, status, target_runs
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        fixture.get("id", ""),
                        int(innings.get("inning_number", 1) or 1),
                        innings.get("batting_team", ""),
                        innings.get("bowling_team", ""),
                        int(innings.get("overs_limit", 20) or 20),
                        innings.get("status", "Not started"),
                        int(innings.get("target_runs")) if str(innings.get("target_runs", "") or "").strip() else None,
                    ),
                )
                for batter in innings.get("batters", []):
                    connection.execute(
                        """
                        INSERT INTO fixture_scorebook_batters (fixture_id, inning_number, slot_number, player_name)
                        VALUES (?, ?, ?, ?)
                        """,
                        (
                            fixture.get("id", ""),
                            int(innings.get("inning_number", 1) or 1),
                            int(batter.get("slot_number", 1) or 1),
                            batter.get("player_name", ""),
                        ),
                    )
                for bowler in innings.get("bowlers", []):
                    connection.execute(
                        """
                        INSERT INTO fixture_scorebook_bowlers (fixture_id, inning_number, slot_number, player_name)
                        VALUES (?, ?, ?, ?)
                        """,
                        (
                            fixture.get("id", ""),
                            int(innings.get("inning_number", 1) or 1),
                            int(bowler.get("slot_number", 1) or 1),
                            bowler.get("player_name", ""),
                        ),
                    )
                for ball in innings.get("balls", []):
                    connection.execute(
                        """
                        INSERT INTO fixture_scorebook_balls (
                          id, fixture_id, inning_number, over_number, ball_number, striker, non_striker,
                          bowler, runs_bat, extras_type, extras_runs, wicket, wicket_type, wicket_player,
                          fielder, commentary, created_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            ball.get("id", str(uuid.uuid4())[:8]),
                            fixture.get("id", ""),
                            int(innings.get("inning_number", 1) or 1),
                            int(ball.get("over_number", 1) or 1),
                            int(ball.get("ball_number", 1) or 1),
                            ball.get("striker", ""),
                            ball.get("non_striker", ""),
                            ball.get("bowler", ""),
                            int(ball.get("runs_bat", 0) or 0),
                            ball.get("extras_type", "none"),
                            int(ball.get("extras_runs", 0) or 0),
                            1 if ball.get("wicket") else 0,
                            ball.get("wicket_type", ""),
                            ball.get("wicket_player", ""),
                            ball.get("fielder", ""),
                            ball.get("commentary", ""),
                            ball.get("created_at", now_iso()),
                        ),
                    )

        for archive in archives:
            connection.execute(
                """
                INSERT INTO archives (
                  id, club_id, club_ids, club_names, match_id, applied_to_match_id, season, status, confidence, created_at,
                  preview_url, file_name, file_path, file_hash, file_size, source, scorecard_date,
                  photo_taken_at, photo_date_source, archive_date, archive_year, archive_date_source,
                  raw_extracted_text, ocr_engine, ocr_processed_at, ocr_pipeline, extracted_summary,
                  review_template_json, review_source_json, review_llm_model, review_llm_notes, review_llm_assessment
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    archive.get("id", ""),
                    archive.get("club_id") or primary_club_id or None,
                    json.dumps(_coerce_archive_string_list(archive.get("club_ids")) or ([archive.get("club_id", "")] if archive.get("club_id") else [])),
                    json.dumps(_coerce_archive_string_list(archive.get("club_names")) or ([archive.get("club_name", "")] if archive.get("club_name") else [])),
                    archive.get("match_id", ""),
                    archive.get("applied_to_match_id", ""),
                    archive.get("season", ""),
                    archive.get("status", ""),
                    archive.get("confidence", ""),
                    archive.get("created_at", ""),
                    archive.get("preview_url", ""),
                    archive.get("file_name", ""),
                    archive.get("file_path", ""),
                    archive.get("file_hash", ""),
                    int(archive.get("file_size", 0) or 0),
                    archive.get("source", ""),
                    archive.get("scorecard_date", ""),
                    archive.get("photo_taken_at", ""),
                    archive.get("photo_date_source", ""),
                    archive.get("archive_date", ""),
                    archive.get("archive_year", ""),
                    archive.get("archive_date_source", ""),
                    archive.get("raw_extracted_text", ""),
                    archive.get("ocr_engine", ""),
                    archive.get("ocr_processed_at", ""),
                    archive.get("ocr_pipeline", ""),
                    archive.get("extracted_summary", ""),
                    archive.get("review_template_json", ""),
                    archive.get("review_source_json", ""),
                    archive.get("review_llm_model", ""),
                    archive.get("review_llm_notes", ""),
                    json.dumps(archive.get("review_llm_assessment") or {}, indent=2) if isinstance(archive.get("review_llm_assessment"), dict) else str(archive.get("review_llm_assessment") or ""),
                ),
            )
            draft = archive.get("draft_scorecard", {})
            connection.execute(
                """
                INSERT INTO archive_scorecards (
                  archive_id, heartlake_runs, heartlake_wickets, heartlake_overs,
                  opponent_runs, opponent_wickets, opponent_overs, result, live_summary
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    archive.get("id", ""),
                    draft.get("heartlake_runs", ""),
                    draft.get("heartlake_wickets", ""),
                    draft.get("heartlake_overs", ""),
                    draft.get("opponent_runs", ""),
                    draft.get("opponent_wickets", ""),
                    draft.get("opponent_overs", ""),
                    draft.get("result", ""),
                    draft.get("live_summary", ""),
                ),
            )
            for performance in archive.get("suggested_performances", []):
                connection.execute(
                    """
                    INSERT INTO archive_performances (
                      archive_id, member_id, player_name, runs, balls, wickets, catches,
                      fours, sixes, notes, source, confidence
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        archive.get("id", ""),
                        member_name_to_id.get(performance.get("player_name", "")) or None,
                        performance.get("player_name", ""),
                        int(performance.get("runs", 0) or 0),
                        int(performance.get("balls", 0) or 0),
                        int(performance.get("wickets", 0) or 0),
                        int(performance.get("catches", 0) or 0),
                        int(performance.get("fours", 0) or 0),
                        int(performance.get("sixes", 0) or 0),
                        performance.get("notes", ""),
                        performance.get("source", ""),
                        performance.get("confidence", ""),
                    ),
                )

        for duplicate in duplicates:
            connection.execute(
                """
                INSERT INTO duplicate_uploads (
                  id, created_at, reason, source, review_dir, original_file_name, original_file_path,
                  original_review_path, original_review_url, duplicate_file_name, duplicate_file_path,
                  duplicate_review_path, duplicate_review_url, file_hash, status
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    duplicate.get("id", ""),
                    duplicate.get("created_at", ""),
                    duplicate.get("reason", ""),
                    duplicate.get("source", ""),
                    duplicate.get("review_dir", ""),
                    duplicate.get("original_file_name", ""),
                    duplicate.get("original_file_path", ""),
                    duplicate.get("original_review_path", ""),
                    duplicate.get("original_review_url", ""),
                    duplicate.get("duplicate_file_name", ""),
                    duplicate.get("duplicate_file_path", ""),
                    duplicate.get("duplicate_review_path", ""),
                    duplicate.get("duplicate_review_url", ""),
                    duplicate.get("file_hash", ""),
                    duplicate.get("status", ""),
                ),
            )

        for user_link in auth_user_links:
            connection.execute(
                """
                UPDATE app_users
                SET member_id = ?, primary_club_id = ?
                WHERE id = ?
                """,
                (
                    user_link.get("member_id") or None,
                    user_link.get("primary_club_id") or None,
                    int(user_link.get("id") or 0),
                ),
            )

        for session_link in auth_session_links:
            connection.execute(
                """
                UPDATE app_auth_sessions
                SET current_club_id = ?
                WHERE token = ?
                """,
                (
                    session_link.get("current_club_id") or None,
                    session_link.get("token", ""),
                ),
            )

        for availability_link in player_season_availability_links:
            if not availability_link.get("user_id") or not availability_link.get("club_id"):
                continue
            connection.execute(
                """
                INSERT INTO app_player_season_availability (user_id, club_id, status, note, updated_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(user_id, club_id) DO UPDATE SET
                  status = excluded.status,
                  note = excluded.note,
                  updated_at = excluded.updated_at
                """,
                (
                    int(availability_link.get("user_id") or 0),
                    availability_link.get("club_id", ""),
                    availability_link.get("status", ""),
                    availability_link.get("note", ""),
                    availability_link.get("updated_at", ""),
                ),
            )

        summary_rows, year_rows, club_rows = _build_materialized_member_stats(normalized)
        club_summary_rows, club_year_rows = _build_materialized_club_stats(normalized)
        connection.executemany(
            """
            INSERT INTO member_summary_stats (
              member_id, player_name, full_name, matches, batting_innings, outs, runs, balls,
              batting_average, strike_rate, wickets, catches, fours, sixes, highest_score,
              scores_25_plus, scores_50_plus, scores_100_plus,
              last_game_date, last_opponent, next_game_date, next_opponent, updated_at
            ) VALUES (
              :member_id, :player_name, :full_name, :matches, :batting_innings, :outs, :runs, :balls,
              :batting_average, :strike_rate, :wickets, :catches, :fours, :sixes, :highest_score,
              :scores_25_plus, :scores_50_plus, :scores_100_plus,
              :last_game_date, :last_opponent, :next_game_date, :next_opponent, :updated_at
            )
            """,
            summary_rows,
        )
        connection.executemany(
            """
            INSERT INTO member_year_stats (
              member_id, season_year, player_name, full_name, matches, batting_innings, outs, runs, balls,
              batting_average, strike_rate, wickets, catches, fours, sixes, highest_score,
              scores_25_plus, scores_50_plus, scores_100_plus, updated_at
            ) VALUES (
              :member_id, :season_year, :player_name, :full_name, :matches, :batting_innings, :outs, :runs, :balls,
              :batting_average, :strike_rate, :wickets, :catches, :fours, :sixes, :highest_score,
              :scores_25_plus, :scores_50_plus, :scores_100_plus, :updated_at
            )
            """,
            year_rows,
        )
        connection.executemany(
            """
            INSERT INTO member_club_stats (
              member_id, club_id, player_name, full_name, club_name, matches, batting_innings, outs, runs, balls,
              batting_average, strike_rate, wickets, catches, fours, sixes, highest_score,
              scores_25_plus, scores_50_plus, scores_100_plus, updated_at
            ) VALUES (
              :member_id, :club_id, :player_name, :full_name, :club_name, :matches, :batting_innings, :outs, :runs, :balls,
              :batting_average, :strike_rate, :wickets, :catches, :fours, :sixes, :highest_score,
              :scores_25_plus, :scores_50_plus, :scores_100_plus, :updated_at
            )
            """,
            club_rows,
        )
        connection.executemany(
            """
            INSERT INTO club_summary_stats (
              club_id, club_name, season_year, member_count, team_count, fixture_count, archive_count,
              total_runs, total_wickets, total_catches, highest_score, top_batter, top_batter_runs,
              scores_25_plus, scores_50_plus, scores_100_plus, updated_at
            ) VALUES (
              :club_id, :club_name, :season_year, :member_count, :team_count, :fixture_count, :archive_count,
              :total_runs, :total_wickets, :total_catches, :highest_score, :top_batter, :top_batter_runs,
              :scores_25_plus, :scores_50_plus, :scores_100_plus, :updated_at
            )
            """,
            club_summary_rows,
        )
        connection.executemany(
            """
            INSERT INTO club_year_stats (
              club_id, season_year, club_name, member_count, fixture_count, archive_count, total_runs,
              total_wickets, total_catches, highest_score, top_batter, top_batter_runs,
              scores_25_plus, scores_50_plus, scores_100_plus, updated_at
            ) VALUES (
              :club_id, :season_year, :club_name, :member_count, :fixture_count, :archive_count, :total_runs,
              :total_wickets, :total_catches, :highest_score, :top_batter, :top_batter_runs,
              :scores_25_plus, :scores_50_plus, :scores_100_plus, :updated_at
            )
            """,
            club_year_rows,
        )


def _read_relational_state(connection: sqlite3.Connection) -> dict[str, Any]:
    clubs_rows = connection.execute("SELECT * FROM clubs ORDER BY name").fetchall()
    teams_rows = connection.execute("SELECT * FROM teams ORDER BY display_name, name").fetchall()
    viewer_profile_row = connection.execute("SELECT * FROM app_user_profile WHERE id = 1").fetchone()
    app_users_rows = connection.execute("SELECT member_id, primary_club_id FROM app_users").fetchall()
    members_rows = connection.execute("SELECT * FROM members ORDER BY name").fetchall()
    alias_rows = connection.execute("SELECT member_id, alias FROM member_aliases ORDER BY alias").fetchall()
    followed_rows = connection.execute("SELECT member_id FROM app_followed_players WHERE user_id = 1").fetchall()
    membership_rows = connection.execute(
        """
        SELECT tm.member_id, tm.team_id, tm.is_primary, t.name AS team_name, t.display_name, t.type, t.club_id
        FROM team_memberships tm
        JOIN teams t ON t.id = tm.team_id
        ORDER BY tm.member_id, tm.is_primary DESC, t.name
        """
    ).fetchall()
    fixtures_rows = connection.execute("SELECT * FROM fixtures ORDER BY date, id").fetchall()
    fixture_scorecard_rows = connection.execute("SELECT * FROM fixture_scorecards").fetchall()
    fixture_availability_rows = connection.execute("SELECT * FROM fixture_availability").fetchall()
    fixture_playing_xi_rows = connection.execute(
        "SELECT * FROM fixture_playing_xi ORDER BY fixture_id, slot_number, member_id"
    ).fetchall()
    fixture_performance_rows = connection.execute("SELECT * FROM fixture_performances ORDER BY fixture_id, id").fetchall()
    fixture_commentary_rows = connection.execute("SELECT * FROM fixture_commentary ORDER BY fixture_id, created_at, id").fetchall()
    fixture_scorebook_innings_rows = connection.execute(
        "SELECT * FROM fixture_scorebook_innings ORDER BY fixture_id, inning_number"
    ).fetchall()
    fixture_scorebook_batter_rows = connection.execute(
        "SELECT * FROM fixture_scorebook_batters ORDER BY fixture_id, inning_number, slot_number"
    ).fetchall()
    fixture_scorebook_bowler_rows = connection.execute(
        "SELECT * FROM fixture_scorebook_bowlers ORDER BY fixture_id, inning_number, slot_number"
    ).fetchall()
    fixture_scorebook_ball_rows = connection.execute(
        "SELECT * FROM fixture_scorebook_balls ORDER BY fixture_id, inning_number, over_number, ball_number, created_at, id"
    ).fetchall()
    archive_rows = connection.execute("SELECT * FROM archives ORDER BY created_at, id").fetchall()
    archive_scorecard_rows = connection.execute("SELECT * FROM archive_scorecards").fetchall()
    archive_performance_rows = connection.execute("SELECT * FROM archive_performances ORDER BY archive_id, id").fetchall()
    duplicate_rows = connection.execute("SELECT * FROM duplicate_uploads ORDER BY created_at, id").fetchall()
    insights_row = connection.execute("SELECT * FROM app_insights WHERE id = 1").fetchone()
    member_summary_rows = connection.execute("SELECT * FROM member_summary_stats ORDER BY player_name").fetchall()
    member_year_rows = connection.execute(
        "SELECT * FROM member_year_stats ORDER BY season_year DESC, player_name"
    ).fetchall()
    member_club_rows = connection.execute(
        "SELECT * FROM member_club_stats ORDER BY club_name, player_name"
    ).fetchall()
    club_summary_rows = connection.execute("SELECT * FROM club_summary_stats ORDER BY club_name").fetchall()
    club_year_rows = connection.execute(
        "SELECT * FROM club_year_stats ORDER BY season_year DESC, club_name"
    ).fetchall()
    llm_document_rows = connection.execute("SELECT * FROM llm_documents ORDER BY doc_type, title, id").fetchall()
    llm_query_cache_rows = connection.execute("SELECT * FROM llm_query_cache ORDER BY created_at DESC, id DESC").fetchall()

    club_dicts = [dict(row) for row in clubs_rows]
    club_by_id = {str(club["id"]): club for club in club_dicts if str(club.get("id") or "").strip()}
    primary_club = next(
        (
            club
            for club in club_dicts
            if str(club.get("id", "")).strip() == "club-heartlake"
            or str(club.get("short_name", "")).strip().lower() == "heartlake"
            or str(club.get("name", "")).strip().lower() == "heartlake cricket club"
        ),
        club_dicts[0] if club_dicts else {},
    )
    club_id_to_name = {row["id"]: row["name"] for row in club_dicts}

    team_dicts = []
    team_id_to_row: dict[str, dict[str, Any]] = {}
    for row in teams_rows:
        team = {
            "id": row["id"],
            "name": row["name"],
            "type": row["type"],
            "display_name": row["display_name"],
        }
        if row["club_id"]:
            team["club_id"] = row["club_id"]
            team["club_name"] = club_id_to_name.get(row["club_id"], "")
        team_dicts.append(team)
        team_id_to_row[row["id"]] = team

    aliases_by_member: dict[str, list[str]] = defaultdict(list)
    for row in alias_rows:
        aliases_by_member[row["member_id"]].append(row["alias"])

    primary_club_by_member: dict[str, str] = {
        str(row["member_id"] or "").strip(): str(row["primary_club_id"] or "").strip()
        for row in app_users_rows
        if str(row["member_id"] or "").strip() and str(row["primary_club_id"] or "").strip()
    }

    memberships_by_member: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in membership_rows:
        memberships_by_member[row["member_id"]].append(
            {
                "team_id": row["team_id"],
                "team_name": row["team_name"],
                "display_name": row["display_name"],
                "team_type": row["type"],
                "club_id": row["club_id"],
                "club_name": club_id_to_name.get(row["club_id"], ""),
                "is_primary": bool(row["is_primary"]),
            }
        )

    members = []
    member_id_to_name: dict[str, str] = {}
    for row in members_rows:
        memberships = list(memberships_by_member.get(row["id"], []))
        primary_club_id = primary_club_by_member.get(row["id"], "")
        primary_club_row = club_by_id.get(primary_club_id, {}) if primary_club_id else {}
        primary_club_name = str(primary_club_row.get("name") or "").strip()
        primary_club_short_name = str(primary_club_row.get("short_name") or "").strip()
        primary_team_name = primary_club_short_name or primary_club_name or "Club"
        if primary_club_id and not any(str(item.get("club_id") or "").strip() == primary_club_id for item in memberships):
            existing_club_ids = {
                str(item.get("club_id") or "").strip()
                for item in memberships
                if str(item.get("club_id") or "").strip()
            }
            if len(existing_club_ids) <= 1:
                memberships = [
                    item
                    for item in memberships
                    if str(item.get("club_id") or "").strip() == primary_club_id
                ]
            team_id = ""
            team_row = None
            synthetic_team_id = f"team-{primary_club_id}-{_slug_token(primary_team_name, 'team')}"
            team_row = team_id_to_row.get(synthetic_team_id)
            if team_row:
                team_id = str(team_row.get("id") or synthetic_team_id)
                if primary_club_id and not str(team_row.get("club_id") or "").strip():
                    team_row["club_id"] = primary_club_id
                if primary_club_name and not str(team_row.get("club_name") or "").strip():
                    team_row["club_name"] = primary_club_name
            else:
                existing_team = next(
                    (
                        team
                        for team in team_dicts
                        if str(team.get("name") or "").strip().lower() == primary_team_name.lower()
                        or str(team.get("display_name") or "").strip().lower() == primary_team_name.lower()
                    ),
                    None,
                )
                if existing_team:
                    team_id = str(existing_team.get("id") or synthetic_team_id)
                    existing_team["club_id"] = primary_club_id
                    existing_team["club_name"] = primary_club_name
                else:
                    team_id = synthetic_team_id
                    synthetic_team = {
                        "id": synthetic_team_id,
                        "name": primary_team_name,
                        "display_name": primary_club_name or primary_team_name,
                        "type": "club",
                        "club_id": primary_club_id,
                        "club_name": primary_club_name,
                    }
                    team_dicts.append(synthetic_team)
                    team_id_to_row[synthetic_team_id] = synthetic_team
            memberships.insert(
                0,
                {
                    "team_id": team_id,
                    "team_name": primary_team_name,
                    "display_name": primary_club_name or primary_team_name,
                    "team_type": "club",
                    "club_id": primary_club_id,
                    "club_name": primary_club_name,
                    "is_primary": True,
                },
            )
        primary_membership = next((item for item in memberships if item["is_primary"]), memberships[0] if memberships else None)
        member = {
            "id": row["id"],
            "name": row["name"],
            "full_name": row["full_name"] or "",
            "gender": row["gender"] or "",
            "team_name": primary_membership["team_name"] if primary_membership else "Club",
            "team_memberships": memberships,
            "primary_club_id": primary_club_id or (primary_membership.get("club_id") if primary_membership else ""),
            "primary_club_name": primary_club_name or (primary_membership.get("club_name") if primary_membership else ""),
            "age": int(row["age"] or 0),
            "role": row["role"] or "",
            "batting_style": row["batting_style"] or "",
            "bowling_style": row["bowling_style"] or "",
            "picture": row["picture"] or member_initials(row["name"] or ""),
            "notes": row["notes"] or "",
            "phone": row["phone"] or "",
            "email": row["email"] or "",
            "picture_url": row["picture_url"] or "",
            "jersey_number": row["jersey_number"] or "",
            "aliases": aliases_by_member.get(row["id"], []),
        }
        member["club_memberships"] = _member_club_memberships(member, primary_club.get("name", ""))
        members.append(member)
        member_id_to_name[row["id"]] = row["name"]

    followed_player_names = [
        member_id_to_name.get(row["member_id"], "")
        for row in followed_rows
        if member_id_to_name.get(row["member_id"], "")
    ]
    viewer_profile = normalize_viewer_profile(
        dict(viewer_profile_row) if viewer_profile_row else {},
        primary_club,
        members,
    )
    if not viewer_profile.get("primary_club_id"):
        viewer_profile["primary_club_id"] = primary_club.get("id", "club-heartlake")
    if not viewer_profile.get("primary_club_name"):
        viewer_profile["primary_club_name"] = primary_club.get("name", "Club")
    viewer_profile["followed_player_names"] = followed_player_names

    scorecard_by_fixture = {row["fixture_id"]: dict(row) for row in fixture_scorecard_rows}
    availability_by_fixture: dict[str, list[sqlite3.Row]] = defaultdict(list)
    for row in fixture_availability_rows:
        availability_by_fixture[row["fixture_id"]].append(row)
    playing_xi_by_fixture: dict[str, list[sqlite3.Row]] = defaultdict(list)
    for row in fixture_playing_xi_rows:
        playing_xi_by_fixture[row["fixture_id"]].append(row)
    performances_by_fixture: dict[str, list[sqlite3.Row]] = defaultdict(list)
    for row in fixture_performance_rows:
        performances_by_fixture[row["fixture_id"]].append(row)
    commentary_by_fixture: dict[str, list[sqlite3.Row]] = defaultdict(list)
    for row in fixture_commentary_rows:
        commentary_by_fixture[row["fixture_id"]].append(row)
    innings_by_fixture: dict[str, list[sqlite3.Row]] = defaultdict(list)
    for row in fixture_scorebook_innings_rows:
        innings_by_fixture[row["fixture_id"]].append(row)
    batters_by_innings: dict[tuple[str, int], list[sqlite3.Row]] = defaultdict(list)
    for row in fixture_scorebook_batter_rows:
        batters_by_innings[(row["fixture_id"], int(row["inning_number"] or 1))].append(row)
    bowlers_by_innings: dict[tuple[str, int], list[sqlite3.Row]] = defaultdict(list)
    for row in fixture_scorebook_bowler_rows:
        bowlers_by_innings[(row["fixture_id"], int(row["inning_number"] or 1))].append(row)
    balls_by_innings: dict[tuple[str, int], list[sqlite3.Row]] = defaultdict(list)
    for row in fixture_scorebook_ball_rows:
        balls_by_innings[(row["fixture_id"], int(row["inning_number"] or 1))].append(row)

    fixtures = []
    for row in fixtures_rows:
        availability_statuses: dict[str, str] = {}
        availability_notes: dict[str, str] = {}
        for availability in availability_by_fixture.get(row["id"], []):
            member_name = member_id_to_name.get(availability["member_id"], "")
            if not member_name:
                continue
            availability_statuses[member_name] = availability["status"] or ""
            if availability["note"]:
                availability_notes[member_name] = availability["note"]
        selected_playing_xi_member_ids = [
            str(item["member_id"] or "").strip()
            for item in playing_xi_by_fixture.get(row["id"], [])
            if str(item["member_id"] or "").strip()
        ]
        selected_playing_xi = [
            member_id_to_name.get(member_id, "")
            for member_id in selected_playing_xi_member_ids
            if member_id_to_name.get(member_id, "")
        ]

        performances = []
        for performance in performances_by_fixture.get(row["id"], []):
            performances.append(
                {
                    "id": performance["id"],
                    "player_name": performance["player_name"] or member_id_to_name.get(performance["member_id"], ""),
                    "runs": int(performance["runs"] or 0),
                    "balls": int(performance["balls"] or 0),
                    "wickets": int(performance["wickets"] or 0),
                    "catches": int(performance["catches"] or 0),
                    "fours": int(performance["fours"] or 0),
                    "sixes": int(performance["sixes"] or 0),
                    "notes": performance["notes"] or "",
                    "source": performance["source"] or "manual",
                    "archive_upload_id": performance["archive_upload_id"] or "",
                }
            )

        commentary = []
        for item in commentary_by_fixture.get(row["id"], []):
            commentary.append(
                {
                    "id": item["id"],
                    "mode": item["mode"] or "text",
                    "text": item["text"] or "",
                    "created_at": item["created_at"] or now_iso(),
                }
            )

        scorebook_innings = []
        for innings_row in innings_by_fixture.get(row["id"], []):
            inning_number = int(innings_row["inning_number"] or 1)
            scorebook_innings.append(
                {
                    "inning_number": inning_number,
                    "batting_team": innings_row["batting_team"] or "",
                    "bowling_team": innings_row["bowling_team"] or "",
                    "overs_limit": int(innings_row["overs_limit"] or 20),
                    "status": innings_row["status"] or "Not started",
                    "target_runs": int(innings_row["target_runs"]) if innings_row["target_runs"] is not None else None,
                    "batters": [
                        {
                            "slot_number": int(item["slot_number"] or 1),
                            "player_name": item["player_name"] or "",
                        }
                        for item in batters_by_innings.get((row["id"], inning_number), [])
                    ],
                    "bowlers": [
                        {
                            "slot_number": int(item["slot_number"] or 1),
                            "player_name": item["player_name"] or "",
                        }
                        for item in bowlers_by_innings.get((row["id"], inning_number), [])
                    ],
                    "balls": [
                        {
                            "id": item["id"],
                            "over_number": int(item["over_number"] or 1),
                            "ball_number": int(item["ball_number"] or 1),
                            "striker": item["striker"] or "",
                            "non_striker": item["non_striker"] or "",
                            "bowler": item["bowler"] or "",
                            "runs_bat": int(item["runs_bat"] or 0),
                            "extras_type": item["extras_type"] or "none",
                            "extras_runs": int(item["extras_runs"] or 0),
                            "wicket": bool(item["wicket"]),
                            "wicket_type": item["wicket_type"] or "",
                            "wicket_player": item["wicket_player"] or "",
                            "fielder": item["fielder"] or "",
                            "commentary": item["commentary"] or "",
                            "created_at": item["created_at"] or now_iso(),
                        }
                        for item in balls_by_innings.get((row["id"], inning_number), [])
                    ],
                }
            )

        scorecard = scorecard_by_fixture.get(row["id"], {})
        availability_seed = json.loads(row["availability_seed_json"]) if row["availability_seed_json"] else []
        fixtures.append(
            {
                "id": row["id"],
                "club_id": row["club_id"] or "",
                "club_name": club_id_to_name.get(row["club_id"], ""),
                "date": row["date"] or "",
                "date_label": row["date_label"] or "",
                "opponent": row["opponent"] or "",
                "visiting_team": row["visiting_team"] or row["opponent"] or "",
                "heartlake_captain": row["heartlake_captain_name"] or member_id_to_name.get(row["heartlake_captain_member_id"], ""),
                "availability_seed": availability_seed,
                "availability_statuses": availability_statuses,
                "availability_notes": availability_notes,
                "availability": available_labels(availability_statuses, availability_notes),
                "selected_playing_xi_member_ids": selected_playing_xi_member_ids,
                "selected_playing_xi": selected_playing_xi,
                "heartlake_score": row["heartlake_score"] or "",
                "opponent_score": row["opponent_score"] or "",
                "result": row["result"] or "TBD",
                "status": row["status"] or "Scheduled",
                "created_by_user_id": int(row["created_by_user_id"]) if row["created_by_user_id"] is not None else None,
                "created_at": row["created_at"] or "",
                "updated_by_user_id": int(row["updated_by_user_id"]) if row["updated_by_user_id"] is not None else None,
                "updated_at": row["updated_at"] or "",
                "commentary": commentary,
                "details": {
                    "venue": row["venue"] or "",
                    "match_type": row["match_type"] or "",
                    "scheduled_time": row["scheduled_time"] or "",
                    "overs": row["overs"] or "",
                    "toss_winner": row["toss_winner"] or "",
                    "toss_decision": row["toss_decision"] or "",
                    "weather": row["weather"] or "",
                    "umpires": row["umpires"] or "",
                    "scorer": row["scorer"] or "",
                    "whatsapp_thread": row["whatsapp_thread"] or "",
                    "notes": row["notes"] or "",
                },
                "scorecard": {
                    "heartlake_runs": scorecard.get("heartlake_runs", "") or "",
                    "heartlake_wickets": scorecard.get("heartlake_wickets", "") or "",
                    "heartlake_overs": scorecard.get("heartlake_overs", "") or "",
                    "opponent_runs": scorecard.get("opponent_runs", "") or "",
                    "opponent_wickets": scorecard.get("opponent_wickets", "") or "",
                    "opponent_overs": scorecard.get("opponent_overs", "") or "",
                    "result": scorecard.get("result", row["result"] or "TBD") or "TBD",
                    "live_summary": scorecard.get("live_summary", "") or "",
                },
                "performances": performances,
                "scorebook": {"innings": scorebook_innings},
            }
        )

    scorecard_by_archive = {row["archive_id"]: dict(row) for row in archive_scorecard_rows}
    performances_by_archive: dict[str, list[sqlite3.Row]] = defaultdict(list)
    for row in archive_performance_rows:
        performances_by_archive[row["archive_id"]].append(row)

    archive_uploads = []
    for row in archive_rows:
        row_keys = set(row.keys())
        suggested_performances = []
        for performance in performances_by_archive.get(row["id"], []):
            suggested_performances.append(
                {
                    "player_name": performance["player_name"] or member_id_to_name.get(performance["member_id"], ""),
                    "runs": int(performance["runs"] or 0),
                    "balls": int(performance["balls"] or 0),
                    "wickets": int(performance["wickets"] or 0),
                    "catches": int(performance["catches"] or 0),
                    "fours": int(performance["fours"] or 0),
                    "sixes": int(performance["sixes"] or 0),
                    "notes": performance["notes"] or "",
                    "source": performance["source"] or "",
                    "confidence": performance["confidence"] or "",
                }
            )
        draft = scorecard_by_archive.get(row["id"], {})
        club_ids = _coerce_archive_string_list(row["club_ids"] if "club_ids" in row_keys else [])
        club_names = _coerce_archive_string_list(row["club_names"] if "club_names" in row_keys else [])
        archive_uploads.append(
            {
                "id": row["id"],
                "club_id": row["club_id"] or "",
                "club_name": club_id_to_name.get(row["club_id"], ""),
                "club_ids": club_ids,
                "club_names": club_names,
                "match_id": row["match_id"] or "",
                "applied_to_match_id": row["applied_to_match_id"] or "",
                "season": row["season"] or "",
                "status": row["status"] or "",
                "confidence": row["confidence"] or "",
                "created_at": row["created_at"] or "",
                "preview_url": row["preview_url"] or "",
                "file_name": row["file_name"] or "",
                "file_path": row["file_path"] or "",
                "file_hash": row["file_hash"] or "",
                "file_size": int(row["file_size"] or 0),
                "source": row["source"] or "",
                "scorecard_date": row["scorecard_date"] or "",
                "photo_taken_at": row["photo_taken_at"] or "",
                "photo_date_source": row["photo_date_source"] or "",
                "archive_date": row["archive_date"] or "",
                "archive_year": row["archive_year"] or "",
                "archive_date_source": row["archive_date_source"] or "",
                "raw_extracted_text": row["raw_extracted_text"] or "",
                "ocr_engine": row["ocr_engine"] or "",
                "ocr_processed_at": row["ocr_processed_at"] or "",
                "ocr_pipeline": row["ocr_pipeline"] or "",
                "draft_scorecard": {
                    "heartlake_runs": draft.get("heartlake_runs", "") or "",
                    "heartlake_wickets": draft.get("heartlake_wickets", "") or "",
                    "heartlake_overs": draft.get("heartlake_overs", "") or "",
                    "opponent_runs": draft.get("opponent_runs", "") or "",
                    "opponent_wickets": draft.get("opponent_wickets", "") or "",
                    "opponent_overs": draft.get("opponent_overs", "") or "",
                    "result": draft.get("result", "") or "",
                    "live_summary": draft.get("live_summary", "") or "",
                },
                "suggested_performances": suggested_performances,
                "extracted_summary": row["extracted_summary"] or "",
                "review_template_json": row["review_template_json"] or "",
                "review_source_json": row["review_source_json"] or "",
                "review_llm_model": row["review_llm_model"] or "",
                "review_llm_notes": row["review_llm_notes"] or "",
                "review_llm_assessment": json.loads(row["review_llm_assessment"]) if row["review_llm_assessment"] else {},
            }
        )
    for archive in archive_uploads:
        club_ids, club_names = archive_club_context(archive, club_dicts, members, fixtures)
        if club_ids:
            archive["club_ids"] = club_ids
            archive["club_id"] = archive.get("club_id") or club_ids[0]
        if club_names:
            archive["club_names"] = club_names
            archive["club_name"] = archive.get("club_name") or club_names[0]
        inferred_club = _resolve_archive_club(archive, club_dicts)
        if inferred_club and not archive.get("club_id"):
            archive["club_id"] = inferred_club.get("id", archive.get("club_id", ""))
        if inferred_club and not archive.get("club_name"):
            archive["club_name"] = inferred_club.get("name", archive.get("club_name", ""))

    duplicate_uploads = [dict(row) for row in duplicate_rows]
    insights = dict(insights_row) if insights_row else {}
    insights.pop("id", None)
    member_summary_stats = [dict(row) for row in member_summary_rows]
    member_year_stats = [dict(row) for row in member_year_rows]
    member_club_stats = [dict(row) for row in member_club_rows]
    club_summary_stats = [dict(row) for row in club_summary_rows]
    club_year_stats = [dict(row) for row in club_year_rows]
    llm_documents = [dict(row) for row in llm_document_rows]
    llm_query_cache = [dict(row) for row in llm_query_cache_rows]

    store = {
        "club": {key: primary_club.get(key, "") for key in ["id", "name", "short_name", "city", "country", "season", "home_ground", "whatsapp_number", "about"]},
        "clubs": [
            {key: club.get(key, "") for key in ["id", "name", "short_name", "city", "country", "season", "home_ground", "whatsapp_number", "about"]}
            for club in club_dicts
        ],
        "members": members,
        "fixtures": fixtures,
        "archive_uploads": archive_uploads,
        "duplicate_uploads": duplicate_uploads,
        "teams": team_dicts,
        "insights": insights,
        "member_summary_stats": member_summary_stats,
        "member_year_stats": member_year_stats,
        "member_club_stats": member_club_stats,
        "club_summary_stats": club_summary_stats,
        "club_year_stats": club_year_stats,
        "llm_documents": llm_documents,
        "llm_query_cache": llm_query_cache,
        "viewer_profile": viewer_profile,
    }
    return store


def _llm_document_id(doc_type: str, source_id: str) -> str:
    digest = hashlib.sha256(f"{doc_type}:{source_id}".encode("utf-8")).hexdigest()
    return f"llm-{digest[:16]}"


def _llm_document_record(
    doc_type: str,
    source_id: str,
    title: str,
    content: str,
    *,
    club_id: str = "",
    season_year: str = "",
    source_json: Any = None,
    embedding_model: str = "",
    embedding_json: str = "",
) -> dict[str, Any]:
    normalized_title = str(title or "").strip()
    normalized_content = str(content or "").strip()
    return {
        "id": _llm_document_id(doc_type, source_id),
        "doc_type": str(doc_type or "").strip(),
        "source_id": str(source_id or "").strip(),
        "club_id": str(club_id or "").strip(),
        "season_year": str(season_year or "").strip(),
        "title": normalized_title[:300],
        "content": normalized_content[:20000],
        "content_hash": hashlib.sha256(normalized_content.encode("utf-8")).hexdigest() if normalized_content else "",
        "embedding_model": str(embedding_model or "").strip(),
        "embedding_json": str(embedding_json or "").strip(),
        "source_json": json.dumps(source_json or {}, ensure_ascii=False)[:12000] if not isinstance(source_json, str) else str(source_json)[:12000],
        "updated_at": now_iso(),
    }


def build_llm_documents(store: dict[str, Any]) -> list[dict[str, Any]]:
    normalized = normalize_store(store)
    club = dict(normalized.get("club") or {})
    members = list(normalized.get("members") or [])
    fixtures = list(normalized.get("fixtures") or [])
    archives = canonical_archive_uploads(normalized.get("archive_uploads", []))
    summary = build_summary(normalized)
    documents: list[dict[str, Any]] = []

    for prompt in prompt_documents():
        documents.append(
            _llm_document_record(
                prompt["doc_type"],
                prompt["source_id"],
                prompt["title"],
                prompt["content"],
                source_json=prompt.get("source_json", {}),
            )
        )

    club_text = "\n".join(
        [
            f"Club: {club.get('name', 'Club')}",
            f"Season: {club.get('season') or 'unknown'}",
            f"Members: {summary.get('member_count', 0)}",
            f"Fixtures: {summary.get('fixture_count', 0)}",
            f"Archives: {summary.get('archive_count', 0)}",
            f"Batting leader: {summary.get('batting_leader', '')} ({summary.get('batting_leader_runs', 0)})",
            f"Wicket leader: {summary.get('wicket_leader', '')} ({summary.get('wicket_leader_count', 0)})",
            f"Fielding leader: {summary.get('fielding_leader', '')} ({summary.get('fielding_leader_count', 0)})",
        ]
    )
    documents.append(
        _llm_document_record(
            "club",
            str(club.get("id") or "club").strip(),
            f"{club.get('name', 'Club')} summary",
            club_text,
            club_id=str(club.get("id") or ""),
            season_year=str(club.get("season") or "")[:4],
            source_json={"club": club, "summary": summary},
        )
    )

    member_summary_rows = {str(row.get("player_name") or ""): row for row in normalized.get("member_summary_stats", []) or []}
    member_year_rows: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in normalized.get("member_year_stats", []) or []:
        member_year_rows[str(row.get("player_name") or "")].append(row)
    member_club_rows: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in normalized.get("member_club_stats", []) or []:
        member_club_rows[str(row.get("player_name") or "")].append(row)

    for member in members:
        name = str(member.get("name") or "").strip()
        summary_row = dict(member_summary_rows.get(name) or {})
        lines = [
            f"Player: {member.get('full_name') or name}",
            f"Known as: {name}",
            f"Club memberships: {', '.join(item.get('club_name', '') for item in member.get('club_memberships', []) or [] if item.get('club_name')) or 'none'}",
            f"Age: {member.get('age', '')}",
            f"Role: {member.get('role', '')}",
            f"Summary: runs={summary_row.get('runs', 0)}, matches={summary_row.get('matches', 0)}, avg={summary_row.get('batting_average', 0)}, strike_rate={summary_row.get('strike_rate', 0)}, wickets={summary_row.get('wickets', 0)}, catches={summary_row.get('catches', 0)}, highest_score={summary_row.get('highest_score', '')}",
        ]
        for row in member_year_rows.get(name, [])[:4]:
            lines.append(
                f"Year {row.get('season_year')}: runs={row.get('runs', 0)}, matches={row.get('matches', 0)}, avg={row.get('batting_average', 0)}, wickets={row.get('wickets', 0)}, catches={row.get('catches', 0)}"
            )
        for row in member_club_rows.get(name, [])[:4]:
            lines.append(
                f"Club {row.get('club_name')}: runs={row.get('runs', 0)}, matches={row.get('matches', 0)}, avg={row.get('batting_average', 0)}, wickets={row.get('wickets', 0)}, catches={row.get('catches', 0)}"
            )
        documents.append(
            _llm_document_record(
                "member",
                str(member.get("id") or name),
                f"{member.get('full_name') or name} profile",
                "\n".join(lines),
                club_id=str(member.get("primary_club_id") or ""),
                source_json={"member": member, "summary": summary_row},
            )
        )

    for fixture in fixtures:
        scorecard = fixture.get("scorecard", {}) or {}
        performances = "; ".join(
            f"{item.get('player_name')}: runs={item.get('runs', 0)}, wickets={item.get('wickets', 0)}, catches={item.get('catches', 0)}"
            for item in fixture.get("performances", [])[:18]
            if item.get("player_name")
        ) or "none"
        content = "\n".join(
            [
                f"Fixture: {fixture.get('date_label') or fixture.get('date')}",
                f"Club: {fixture.get('club_name')}",
                f"Opponent: {fixture.get('opponent')}",
                f"Status: {fixture.get('status')}",
                f"Scorecard: {scorecard.get('heartlake_runs') or '--'}/{scorecard.get('heartlake_wickets') or '--'} vs {scorecard.get('opponent_runs') or '--'}/{scorecard.get('opponent_wickets') or '--'}",
                f"Result: {scorecard.get('result') or fixture.get('result') or 'TBD'}",
                f"Availability: {', '.join(fixture.get('availability', [])) or 'none'}",
                f"Performances: {performances}",
            ]
        )
        documents.append(
            _llm_document_record(
                "fixture",
                str(fixture.get("id") or ""),
                f"Fixture vs {fixture.get('opponent') or 'Opponent'}",
                content,
                club_id=str(fixture.get("club_id") or ""),
                season_year=str(fixture.get("date") or "")[:4],
                source_json={"fixture": fixture},
            )
        )

    for archive in archives:
        draft = archive.get("draft_scorecard", {}) or {}
        performances = "; ".join(
            f"{item.get('player_name')}: runs={item.get('runs', 0)}, wickets={item.get('wickets', 0)}, catches={item.get('catches', 0)}"
            for item in archive.get("suggested_performances", [])[:18]
            if item.get("player_name")
        ) or "none"
        content = "\n".join(
            [
                f"Archive: {archive.get('file_name')}",
                f"Club: {archive.get('club_name')}",
                f"Season: {archive.get('season')}",
                f"Archive date: {archive.get('archive_date') or archive.get('scorecard_date') or archive.get('photo_taken_at') or 'unknown'}",
                f"Status: {archive.get('status')}",
                f"Summary: {archive.get('extracted_summary') or ''}",
                f"Draft scorecard: {draft.get('heartlake_runs') or '--'}/{draft.get('heartlake_wickets') or '--'} vs {draft.get('opponent_runs') or '--'}/{draft.get('opponent_wickets') or '--'}",
                f"Suggested performances: {performances}",
            ]
        )
        documents.append(
            _llm_document_record(
                "archive",
                str(archive.get("id") or ""),
                f"Archive {archive.get('file_name') or archive.get('id')}",
                content,
                club_id=str(archive.get("club_id") or ""),
                season_year=str(archive.get("archive_year") or archive.get("season") or "")[:4],
                source_json={"archive": archive},
            )
        )
    return documents


def refresh_llm_document_index(connection: sqlite3.Connection, store: dict[str, Any]) -> list[dict[str, Any]]:
    documents = build_llm_documents(store)
    llm_status = {}
    try:
        from app.cricket_brain import get_llm_status as _get_llm_status
    except ModuleNotFoundError:
        from cricket_brain import get_llm_status as _get_llm_status
    try:
        llm_status = _get_llm_status()
    except Exception:
        llm_status = {}
    embedding_model = str(llm_status.get("embedding_model") or "").strip()
    if embedding_model and llm_status.get("embeddings_available"):
        try:
            from app.cricket_brain import _llm_embedding_for_text as _embedding_for_text
        except ModuleNotFoundError:
            from cricket_brain import _llm_embedding_for_text as _embedding_for_text
        for document in documents:
            embedding = _embedding_for_text(document["content"], llm_status) or []
            document["embedding_model"] = embedding_model
            document["embedding_json"] = json.dumps(embedding, ensure_ascii=False)
    with connection:
        connection.execute("DELETE FROM llm_documents")
        connection.executemany(
            """
            INSERT INTO llm_documents (
              id, doc_type, source_id, club_id, season_year, title, content, content_hash,
              embedding_model, embedding_json, source_json, updated_at
            ) VALUES (:id, :doc_type, :source_id, :club_id, :season_year, :title, :content, :content_hash,
              :embedding_model, :embedding_json, :source_json, :updated_at)
            """,
            documents,
        )
        connection.execute("DELETE FROM llm_query_cache")
    return documents


def ensure_database() -> None:
    with _connection() as connection:
        connection.executescript(_schema_tables())
        existing_fixture_columns = {
            row[1]
            for row in connection.execute("PRAGMA table_info(fixtures)").fetchall()
        }
        for column_name, ddl in [
            ("created_by_user_id", "ALTER TABLE fixtures ADD COLUMN created_by_user_id INTEGER"),
            ("created_at", "ALTER TABLE fixtures ADD COLUMN created_at TEXT"),
            ("updated_by_user_id", "ALTER TABLE fixtures ADD COLUMN updated_by_user_id INTEGER"),
            ("updated_at", "ALTER TABLE fixtures ADD COLUMN updated_at TEXT"),
        ]:
            if column_name not in existing_fixture_columns:
                try:
                    connection.execute(ddl)
                except sqlite3.OperationalError as exc:
                    if "duplicate column name" not in str(exc).lower():
                        raise
        existing_columns = {
            row[1]
            for row in connection.execute("PRAGMA table_info(members)").fetchall()
        }
        if "gender" not in existing_columns:
            try:
                connection.execute("ALTER TABLE members ADD COLUMN gender TEXT")
            except sqlite3.OperationalError as exc:
                if "duplicate column name" not in str(exc).lower():
                    raise
        existing_profile_columns = {
            row[1]
            for row in connection.execute("PRAGMA table_info(app_user_profile)").fetchall()
        }
        if "selected_season_year" not in existing_profile_columns:
            try:
                connection.execute("ALTER TABLE app_user_profile ADD COLUMN selected_season_year TEXT")
            except sqlite3.OperationalError as exc:
                if "duplicate column name" not in str(exc).lower():
                    raise
        existing_club_columns = {
            row[1]
            for row in connection.execute("PRAGMA table_info(clubs)").fetchall()
        }
        if "country" not in existing_club_columns:
            try:
                connection.execute("ALTER TABLE clubs ADD COLUMN country TEXT")
            except sqlite3.OperationalError as exc:
                if "duplicate column name" not in str(exc).lower():
                    raise
        existing_archive_columns = {
            row[1]
            for row in connection.execute("PRAGMA table_info(archives)").fetchall()
        }
        for column_name, ddl in [
            ("club_ids", "ALTER TABLE archives ADD COLUMN club_ids TEXT"),
            ("club_names", "ALTER TABLE archives ADD COLUMN club_names TEXT"),
            ("review_template_json", "ALTER TABLE archives ADD COLUMN review_template_json TEXT"),
            ("review_source_json", "ALTER TABLE archives ADD COLUMN review_source_json TEXT"),
            ("review_llm_model", "ALTER TABLE archives ADD COLUMN review_llm_model TEXT"),
            ("review_llm_notes", "ALTER TABLE archives ADD COLUMN review_llm_notes TEXT"),
            ("review_llm_assessment", "ALTER TABLE archives ADD COLUMN review_llm_assessment TEXT"),
        ]:
            if column_name not in existing_archive_columns:
                try:
                    connection.execute(ddl)
                except sqlite3.OperationalError as exc:
                    if "duplicate column name" not in str(exc).lower():
                        raise
        for table_name, required_columns in {
            "member_summary_stats": [
                ("scores_25_plus", "ALTER TABLE member_summary_stats ADD COLUMN scores_25_plus INTEGER"),
                ("scores_50_plus", "ALTER TABLE member_summary_stats ADD COLUMN scores_50_plus INTEGER"),
                ("scores_100_plus", "ALTER TABLE member_summary_stats ADD COLUMN scores_100_plus INTEGER"),
            ],
            "member_year_stats": [
                ("scores_25_plus", "ALTER TABLE member_year_stats ADD COLUMN scores_25_plus INTEGER"),
                ("scores_50_plus", "ALTER TABLE member_year_stats ADD COLUMN scores_50_plus INTEGER"),
                ("scores_100_plus", "ALTER TABLE member_year_stats ADD COLUMN scores_100_plus INTEGER"),
            ],
            "member_club_stats": [
                ("scores_25_plus", "ALTER TABLE member_club_stats ADD COLUMN scores_25_plus INTEGER"),
                ("scores_50_plus", "ALTER TABLE member_club_stats ADD COLUMN scores_50_plus INTEGER"),
                ("scores_100_plus", "ALTER TABLE member_club_stats ADD COLUMN scores_100_plus INTEGER"),
            ],
            "club_summary_stats": [
                ("scores_25_plus", "ALTER TABLE club_summary_stats ADD COLUMN scores_25_plus INTEGER"),
                ("scores_50_plus", "ALTER TABLE club_summary_stats ADD COLUMN scores_50_plus INTEGER"),
                ("scores_100_plus", "ALTER TABLE club_summary_stats ADD COLUMN scores_100_plus INTEGER"),
            ],
            "club_year_stats": [
                ("scores_25_plus", "ALTER TABLE club_year_stats ADD COLUMN scores_25_plus INTEGER"),
                ("scores_50_plus", "ALTER TABLE club_year_stats ADD COLUMN scores_50_plus INTEGER"),
                ("scores_100_plus", "ALTER TABLE club_year_stats ADD COLUMN scores_100_plus INTEGER"),
            ],
        }.items():
            existing_columns = {
                row[1]
                for row in connection.execute(f"PRAGMA table_info({table_name})").fetchall()
            }
            for column_name, ddl in required_columns:
                if column_name not in existing_columns:
                    try:
                        connection.execute(ddl)
                    except sqlite3.OperationalError as exc:
                        if "duplicate column name" not in str(exc).lower():
                            raise
        if not _relational_tables_have_data(connection):
            legacy_store = _legacy_state_from_connection(connection)
            _write_relational_state(connection, legacy_store)


def sync_uploads_in_store(store: dict[str, Any]) -> bool:
    logger.debug(
        "Sync uploads started → archive_uploads=%s upload_dir=%s",
        len(store.get("archive_uploads", []) or []),
        UPLOAD_DIR,
    )
    season = store["club"]["season"]
    changed = False
    existing_hashes: dict[str, dict[str, Any]] = {}
    existing_paths: dict[str, dict[str, Any]] = {}
    existing_duplicate_keys = {
        (item.get("file_hash", ""), item.get("duplicate_file_name", "").lower())
        for item in store.get("duplicate_uploads", [])
    }

    for item in store["archive_uploads"]:
        path = Path(item.get("file_path") or "")
        if not item.get("file_hash") and path.is_file():
            item["file_hash"] = file_sha256(path)
            item["file_size"] = path.stat().st_size
            changed = True
        if item.get("file_hash"):
            existing_hashes[item["file_hash"]] = item
        if item.get("file_name"):
            existing_paths[item["file_name"].lower()] = item

    for path in sorted(UPLOAD_DIR.iterdir()):
        if not path.is_file():
            continue
        if path.suffix.lower() not in IMAGE_EXTENSIONS:
            continue
        file_hash = file_sha256(path)
        duplicate_key = (file_hash, path.name.lower())
        matched_item = existing_hashes.get(file_hash)
        if matched_item and Path(matched_item.get("file_path") or "") != path:
            if duplicate_key not in existing_duplicate_keys:
                store["duplicate_uploads"].append(
                    create_duplicate_record_from_paths(
                        original_path=Path(matched_item["file_path"]),
                        duplicate_path=path,
                        file_hash=file_hash,
                        source="filesystem",
                    )
                )
                existing_duplicate_keys.add(duplicate_key)
                changed = True
            if path.exists():
                path.unlink()
                changed = True
            continue
        if path.name.lower() in existing_paths and Path(existing_paths[path.name.lower()].get("file_path") or "") != path:
            if duplicate_key not in existing_duplicate_keys:
                store["duplicate_uploads"].append(
                    create_duplicate_record_from_paths(
                        original_path=Path(existing_paths[path.name.lower()]["file_path"]),
                        duplicate_path=path,
                        file_hash=file_hash,
                        source="filesystem",
                        reason="duplicate file name",
                    )
                )
                existing_duplicate_keys.add(duplicate_key)
                changed = True
            if path.exists():
                path.unlink()
                changed = True
            continue
        if file_hash in existing_hashes or path.name.lower() in existing_paths:
            continue
        record = archive_record_from_file(path, season, source="filesystem")
        store["archive_uploads"].append(record)
        existing_hashes[file_hash] = record
        existing_paths[path.name.lower()] = record
        changed = True

    return changed


def _write_text_atomic(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(dir=str(path.parent)) as temp_dir:
        temp_path = Path(temp_dir) / path.name
        temp_path.write_text(content, encoding="utf-8")
        temp_path.replace(path)


def load_store() -> dict[str, Any]:
    logger.debug("Load store requested → database=%s cache=%s", DATABASE_FILE, CACHE_FILE)
    global _STORE_CACHE_SIGNATURE, _STORE_CACHE_PAYLOAD
    try:
        ensure_database()
    except sqlite3.DatabaseError as exc:
        # Azure has occasionally booted with a stale schema bootstrap artifact even
        # though the backing database file is still readable. Treat schema refresh
        # failures as non-fatal so sign-in and read-only flows can continue.
        logger.warning("Database bootstrap skipped during load because the store is still readable: %s", exc)

    current_signature = _database_signature()
    if _STORE_CACHE_PAYLOAD is not None and _STORE_CACHE_SIGNATURE == current_signature:
        logger.debug(
            "Load store served from memory cache → members=%s fixtures=%s archives=%s",
            len(_STORE_CACHE_PAYLOAD.get("members", []) or []),
            len(_STORE_CACHE_PAYLOAD.get("fixtures", []) or []),
            len(_STORE_CACHE_PAYLOAD.get("archive_uploads", []) or []),
        )
        return deepcopy(_STORE_CACHE_PAYLOAD)

    try:
        with _connection() as connection:
            raw_store = _read_relational_state(connection)
    except sqlite3.DatabaseError as exc:
        logger.warning("Database read failed during load; falling back to cache: %s", exc)
        if CACHE_FILE.exists():
            cached_store = json.loads(CACHE_FILE.read_text(encoding="utf-8"))
            store = normalize_store(cached_store)
            store["_cache_signature"] = f"{current_signature[0]}:{current_signature[1]}"
            _STORE_CACHE_SIGNATURE = current_signature
            _STORE_CACHE_PAYLOAD = deepcopy(store)
            logger.debug(
                "Load store cache fallback complete → members=%s fixtures=%s archives=%s",
                len(store.get("members", []) or []),
                len(store.get("fixtures", []) or []),
                len(store.get("archive_uploads", []) or []),
            )
            return store
        raise

    store = normalize_store(raw_store)
    store["_cache_signature"] = f"{current_signature[0]}:{current_signature[1]}"

    # ✅ cache only, NO DB writes
    _write_text_atomic(CACHE_FILE, json.dumps(store, indent=2))
    _STORE_CACHE_SIGNATURE = current_signature
    _STORE_CACHE_PAYLOAD = deepcopy(store)
    if _DASHBOARD_CACHE:
        _DASHBOARD_CACHE.clear()
    logger.debug(
        "Load store complete → members=%s fixtures=%s archives=%s",
        len(store.get("members", []) or []),
        len(store.get("fixtures", []) or []),
        len(store.get("archive_uploads", []) or []),
    )

    return store


def save_store(store: dict[str, Any]) -> None:
    logger.debug(
        "Save store requested → members=%s fixtures=%s archives=%s duplicates=%s",
        len(store.get("members", []) or []),
        len(store.get("fixtures", []) or []),
        len(store.get("archive_uploads", []) or []),
        len(store.get("duplicate_uploads", []) or []),
    )
    global _STORE_CACHE_SIGNATURE, _STORE_CACHE_PAYLOAD
    normalized = normalize_store(store)
    sync_uploads_in_store(normalized)
    ensure_database()
    with _connection() as connection:
        _write_relational_state(connection, normalized)
        llm_documents = refresh_llm_document_index(connection, normalized)
    _STORE_CACHE_SIGNATURE = _database_signature()
    normalized["llm_documents"] = llm_documents
    normalized["_cache_signature"] = f"{_STORE_CACHE_SIGNATURE[0]}:{_STORE_CACHE_SIGNATURE[1]}"
    _write_text_atomic(CACHE_FILE, json.dumps(normalized, indent=2))
    _STORE_CACHE_PAYLOAD = deepcopy(normalized)
    if _DASHBOARD_CACHE:
        _DASHBOARD_CACHE.clear()
    logger.debug("Save store complete.")


def get_match_or_404(store: dict[str, Any], match_id: str) -> dict[str, Any]:
    for match in store["fixtures"]:
        if match["id"] == match_id:
            return match
    raise ValueError("Match not found.")


def get_archive_or_404(store: dict[str, Any], upload_id: str) -> dict[str, Any]:
    for item in store["archive_uploads"]:
        if item["id"] == upload_id:
            return item
    raise ValueError("Archive upload not found.")


def build_visiting_teams(fixtures: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for match in fixtures:
        grouped[match["visiting_team"]].append(match)
    cards = []
    for team_name, matches in grouped.items():
        upcoming = sorted(matches, key=lambda item: item["date"])[0]
        cards.append(
            {
                "name": team_name,
                "fixture_count": len(matches),
                "next_date": upcoming["date_label"],
                "captain_assigned_count": sum(1 for item in matches if item.get("heartlake_captain")),
            }
        )
    return sorted(cards, key=lambda item: (-item["fixture_count"], item["name"]))


def build_availability_board(members: list[dict[str, Any]], fixtures: list[dict[str, Any]]) -> list[dict[str, Any]]:
    board = []
    for member in members:
        row = {
            "player_name": member["name"],
            "matches_available": 0,
            "matches_maybe": 0,
            "matches_unavailable": 0,
            "matches_no_response": 0,
            "by_match": [],
        }
        for match in fixtures:
            status = match["availability_statuses"].get(member["name"], "no response")
            row["by_match"].append(
                {
                    "match_id": match["id"],
                    "date_label": match["date_label"],
                    "opponent": match["opponent"],
                    "status": status,
                }
            )
            if status == "available":
                row["matches_available"] += 1
            elif status == "maybe":
                row["matches_maybe"] += 1
            elif status == "unavailable":
                row["matches_unavailable"] += 1
            else:
                row["matches_no_response"] += 1
        board.append(row)
    return sorted(board, key=lambda item: (-item["matches_available"], item["player_name"]))


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


def _apply_batting_sample(bucket: dict[str, Any], performance: dict[str, Any]) -> None:
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


def _finalize_batting_metrics(bucket: dict[str, Any]) -> None:
    balls = int(bucket.get("balls", 0) or 0)
    batting_innings = int(bucket.get("batting_innings", 0) or 0)
    dismissal_known_innings = int(bucket.get("dismissal_known_innings", 0) or 0)
    outs = int(bucket.get("outs", 0) or 0)
    if batting_innings and dismissal_known_innings == batting_innings and outs > 0:
        denominator = outs
    elif batting_innings:
        denominator = batting_innings
    else:
        denominator = 0
    bucket["batting_average"] = round((bucket["runs"] / denominator), 2) if denominator else 0.0
    bucket["strike_rate"] = round((bucket["runs"] / balls) * 100, 2) if balls else 0.0


def build_player_stats(fixtures: list[dict[str, Any]], members: list[dict[str, Any]]) -> list[dict[str, Any]]:
    member_names = {member["name"] for member in members}
    stats = {
        member["name"]: {
            "player_name": member["name"],
            "runs": 0,
            "balls": 0,
            "wickets": 0,
            "catches": 0,
            "fours": 0,
            "sixes": 0,
            "matches": 0,
            "batting_innings": 0,
            "dismissal_known_innings": 0,
            "outs": 0,
            "batting_average": 0.0,
            "strike_rate": 0.0,
            "wickets_per_match": 0.0,
            "catches_per_match": 0.0,
        }
        for member in members
    }
    played_tracker: dict[str, set[str]] = defaultdict(set)
    for match in fixtures:
        for performance in match.get("performances", []):
            name = _canonical_member_name(members, performance["player_name"])
            if name not in member_names:
                name = str(performance.get("player_name") or "").strip()
            stats.setdefault(
                name,
                {
                    "player_name": name,
                    "runs": 0,
                    "balls": 0,
                    "wickets": 0,
                    "catches": 0,
                    "fours": 0,
                    "sixes": 0,
                    "matches": 0,
                    "batting_innings": 0,
                    "dismissal_known_innings": 0,
                    "outs": 0,
                    "batting_average": 0.0,
                    "strike_rate": 0.0,
                    "wickets_per_match": 0.0,
                    "catches_per_match": 0.0,
                },
            )
            stats[name]["runs"] += int(performance.get("runs", 0) or 0)
            stats[name]["balls"] += int(performance.get("balls", 0) or 0)
            stats[name]["wickets"] += int(performance.get("wickets", 0) or 0)
            stats[name]["catches"] += int(performance.get("catches", 0) or 0)
            stats[name]["fours"] += int(performance.get("fours", 0) or 0)
            stats[name]["sixes"] += int(performance.get("sixes", 0) or 0)
            _apply_batting_sample(stats[name], performance)
            played_tracker[name].add(match["id"])
    for name, played in played_tracker.items():
        stats[name]["matches"] = len(played)
    for item in stats.values():
        matches = int(item["matches"] or 0)
        _finalize_batting_metrics(item)
        item["wickets_per_match"] = round((item["wickets"] / matches), 2) if matches else 0.0
        item["catches_per_match"] = round((item["catches"] / matches), 2) if matches else 0.0
    return sorted(
        stats.values(),
        key=lambda item: (-item["runs"], -item["batting_average"], -item["strike_rate"], item["player_name"]),
    )


def _assign_rank(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    ranked = []
    for index, row in enumerate(rows, start=1):
        ranked.append({**row, "rank": index})
    return ranked


def build_batting_rankings(player_stats: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = [item for item in player_stats if item.get("matches") or item.get("runs") or item.get("balls")]
    rows.sort(
        key=lambda item: (
            -int(item.get("runs", 0) or 0),
            -float(item.get("batting_average", 0) or 0),
            -float(item.get("strike_rate", 0) or 0),
            -int(item.get("matches", 0) or 0),
            item.get("player_name", ""),
        )
    )
    return _assign_rank(rows)


def build_bowling_rankings(player_stats: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = [item for item in player_stats if int(item.get("wickets", 0) or 0) > 0]
    rows.sort(
        key=lambda item: (
            -int(item.get("wickets", 0) or 0),
            -float(item.get("wickets_per_match", 0) or 0),
            -int(item.get("matches", 0) or 0),
            item.get("player_name", ""),
        )
    )
    return _assign_rank(rows)


def build_fielding_rankings(player_stats: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = [item for item in player_stats if int(item.get("catches", 0) or 0) > 0]
    rows.sort(
        key=lambda item: (
            -int(item.get("catches", 0) or 0),
            -float(item.get("catches_per_match", 0) or 0),
            -int(item.get("matches", 0) or 0),
            item.get("player_name", ""),
        )
    )
    return _assign_rank(rows)


def build_player_pending_stats(archive_uploads: list[dict[str, Any]], members: list[dict[str, Any]]) -> list[dict[str, Any]]:
    member_names = {member["name"] for member in members}
    canonical_uploads = canonical_archive_uploads(archive_uploads)
    stats = {
        member["name"]: {
            "player_name": member["name"],
            "runs": 0,
            "balls": 0,
            "wickets": 0,
            "catches": 0,
            "matches": 0,
            "batting_innings": 0,
            "dismissal_known_innings": 0,
            "outs": 0,
            "batting_average": 0.0,
            "strike_rate": 0.0,
            "sources": [],
        }
        for member in members
    }
    played_tracker: dict[str, set[str]] = defaultdict(set)
    for upload in canonical_uploads:
        status = str(upload.get("status") or "").strip().lower()
        if status.startswith("pending") or status == "applied to match":
            continue
        archive_key = upload.get("id") or upload.get("file_name", "")
        for performance in upload.get("suggested_performances", []):
            name = _canonical_member_name(members, performance.get("player_name", ""))
            if not name or name not in member_names:
                continue
            stats.setdefault(
                name,
                {
                    "player_name": name,
                    "runs": 0,
                    "balls": 0,
                    "wickets": 0,
                    "catches": 0,
                    "matches": 0,
                    "batting_innings": 0,
                    "dismissal_known_innings": 0,
                    "outs": 0,
                    "batting_average": 0.0,
                    "strike_rate": 0.0,
                    "sources": [],
                },
            )
            stats[name]["runs"] += int(performance.get("runs", 0) or 0)
            stats[name]["balls"] += int(performance.get("balls", 0) or 0)
            stats[name]["wickets"] += int(performance.get("wickets", 0) or 0)
            stats[name]["catches"] += int(performance.get("catches", 0) or 0)
            _apply_batting_sample(stats[name], performance)
            notes = str(performance.get("notes", "") or "")
            lowered_notes = notes.lower()
            fielder_match = re.search(r"fielder:\s*([^|]+)", notes, flags=re.IGNORECASE)
            if fielder_match:
                fielder_name = _canonical_member_name(members, fielder_match.group(1).strip())
                if fielder_name not in member_names:
                    fielder_name = ""
                if fielder_name:
                    stats.setdefault(
                        fielder_name,
                        {
                            "player_name": fielder_name,
                            "runs": 0,
                            "balls": 0,
                            "wickets": 0,
                            "catches": 0,
                            "matches": 0,
                            "batting_innings": 0,
                            "dismissal_known_innings": 0,
                            "outs": 0,
                            "batting_average": 0.0,
                            "strike_rate": 0.0,
                            "sources": [],
                        },
                    )
                    stats[fielder_name]["catches"] += 1
                    played_tracker[fielder_name].add(archive_key)
            bowler_match = re.search(r"bowler:\s*([^|]+)", notes, flags=re.IGNORECASE)
            if bowler_match and not any(tag in lowered_notes for tag in ["run_out", "run out", "not_out", "not out", "retired"]):
                bowler_name = _canonical_member_name(members, bowler_match.group(1).strip())
                if bowler_name not in member_names:
                    bowler_name = ""
                if bowler_name:
                    stats.setdefault(
                        bowler_name,
                        {
                            "player_name": bowler_name,
                            "runs": 0,
                            "balls": 0,
                            "wickets": 0,
                            "catches": 0,
                            "matches": 0,
                            "batting_innings": 0,
                            "dismissal_known_innings": 0,
                            "outs": 0,
                            "batting_average": 0.0,
                            "strike_rate": 0.0,
                            "sources": [],
                        },
                    )
                    stats[bowler_name]["wickets"] += 1
                    played_tracker[bowler_name].add(archive_key)
            stats[name]["sources"].append(
                {
                    "archive_id": upload.get("id", ""),
                    "file_name": upload.get("file_name", ""),
                    "runs": int(performance.get("runs", 0) or 0),
                    "balls": int(performance.get("balls", 0) or 0),
                    "wickets": int(performance.get("wickets", 0) or 0),
                    "catches": int(performance.get("catches", 0) or 0),
                    "confidence": performance.get("confidence", "low"),
                    "notes": performance.get("notes", ""),
                }
            )
            played_tracker[name].add(archive_key)
    for name, played in played_tracker.items():
        stats[name]["matches"] = len(played)
    for item in stats.values():
        _finalize_batting_metrics(item)
    return sorted(stats.values(), key=lambda item: (-item["runs"], -item["wickets"], item["player_name"]))


def build_combined_player_stats(
    fixtures: list[dict[str, Any]],
    archive_uploads: list[dict[str, Any]],
    members: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    live_stats = build_player_stats(fixtures, members)
    pending_stats = build_player_pending_stats(archive_uploads, members)
    live_by_name = {item["player_name"]: item for item in live_stats}
    pending_by_name = {item["player_name"]: item for item in pending_stats}
    all_names = sorted(set(live_by_name) | set(pending_by_name) | {member["name"] for member in members})
    combined: list[dict[str, Any]] = []
    for name in all_names:
        live = live_by_name.get(name, {})
        pending = pending_by_name.get(name, {})
        runs = int(live.get("runs", 0) or 0) + int(pending.get("runs", 0) or 0)
        balls = int(live.get("balls", 0) or 0) + int(pending.get("balls", 0) or 0)
        wickets = int(live.get("wickets", 0) or 0) + int(pending.get("wickets", 0) or 0)
        catches = int(live.get("catches", 0) or 0) + int(pending.get("catches", 0) or 0)
        matches = int(live.get("matches", 0) or 0) + int(pending.get("matches", 0) or 0)
        batting_innings = int(live.get("batting_innings", 0) or 0) + int(pending.get("batting_innings", 0) or 0)
        dismissal_known_innings = int(live.get("dismissal_known_innings", 0) or 0) + int(pending.get("dismissal_known_innings", 0) or 0)
        outs = int(live.get("outs", 0) or 0) + int(pending.get("outs", 0) or 0)
        row = {
            "player_name": name,
            "runs": runs,
            "balls": balls,
            "wickets": wickets,
            "catches": catches,
            "fours": int(live.get("fours", 0) or 0),
            "sixes": int(live.get("sixes", 0) or 0),
            "matches": matches,
            "batting_innings": batting_innings,
            "dismissal_known_innings": dismissal_known_innings,
            "outs": outs,
            "batting_average": 0.0,
            "strike_rate": 0.0,
            "wickets_per_match": round((wickets / matches), 2) if matches else 0.0,
            "catches_per_match": round((catches / matches), 2) if matches else 0.0,
        }
        _finalize_batting_metrics(row)
        combined.append(row)
    return sorted(
        combined,
        key=lambda item: (-item["runs"], -item["wickets"], -item["catches"], item["player_name"]),
    )


def _member_stat_hints(member: dict[str, Any]) -> set[str]:
    return {
        hint
        for hint in (
            str(member.get("name") or "").strip().lower(),
            str(member.get("full_name") or "").strip().lower(),
            str(member.get("phone") or "").strip().lower(),
            str(member.get("email") or "").strip().lower(),
            *(str(alias or "").strip().lower() for alias in member.get("aliases", [])),
        )
        if hint
    }


def _highest_score_for_member(
    fixtures: list[dict[str, Any]],
    archive_uploads: list[dict[str, Any]],
    member: dict[str, Any],
    *,
    year: str | None = None,
    club_id: str | None = None,
) -> int | None:
    aliases = _member_stat_hints(member)
    highest: int | None = None

    def consider(performance_name: str, runs_value: Any) -> None:
        nonlocal highest
        if str(performance_name or "").strip().lower() not in aliases:
            return
        runs = int(runs_value or 0)
        highest = runs if highest is None else max(highest, runs)

    for fixture in fixtures:
        if year and fixture_season_year(fixture) != str(year).strip():
            continue
        if club_id and str(fixture.get("club_id") or "").strip() != str(club_id).strip():
            continue
        for performance in fixture.get("performances", []) or []:
            consider(performance.get("player_name") or "", performance.get("runs") or 0)

    for archive in canonical_archive_uploads(archive_uploads):
        archive_year = str(archive.get("archive_year") or "").strip()
        archive_date = str(archive.get("archive_date") or "").strip()
        archive_year_value = archive_year[:4] if re.match(r"20\d{2}", archive_year) else (archive_date[:4] if re.match(r"20\d{2}", archive_date) else "")
        if year and archive_year_value != str(year).strip():
            continue
        if club_id:
            club_match = str(club_id).strip().lower()
            archive_club_ids = {str(item or "").strip().lower() for item in _coerce_archive_string_list(archive.get("club_ids"))}
            archive_club_id = str(archive.get("club_id") or "").strip().lower()
            if club_match not in archive_club_ids and archive_club_id != club_match:
                continue
        for performance in archive.get("suggested_performances", []) or []:
            consider(performance.get("player_name") or "", performance.get("runs") or 0)
    return highest


def _batting_milestones(
    fixtures: list[dict[str, Any]],
    archive_uploads: list[dict[str, Any]],
    member: dict[str, Any],
    *,
    year: str | None = None,
    club_id: str | None = None,
) -> dict[str, int]:
    aliases = _member_stat_hints(member)
    milestones = {"scores_25_plus": 0, "scores_50_plus": 0, "scores_100_plus": 0}

    def consider(performance_name: str, runs_value: Any) -> None:
        if str(performance_name or "").strip().lower() not in aliases:
            return
        runs = int(runs_value or 0)
        if 25 < runs < 50:
            milestones["scores_25_plus"] += 1
        elif 50 < runs < 100:
            milestones["scores_50_plus"] += 1
        elif 100 < runs < 199:
            milestones["scores_100_plus"] += 1

    for fixture in fixtures:
        if year and fixture_season_year(fixture) != str(year).strip():
            continue
        if club_id and str(fixture.get("club_id") or "").strip() != str(club_id).strip():
            continue
        for performance in fixture.get("performances", []) or []:
            consider(performance.get("player_name") or "", performance.get("runs") or 0)

    for archive in canonical_archive_uploads(archive_uploads):
        archive_year = str(archive.get("archive_year") or "").strip()
        archive_date = str(archive.get("archive_date") or "").strip()
        archive_year_value = archive_year[:4] if re.match(r"20\d{2}", archive_year) else (archive_date[:4] if re.match(r"20\d{2}", archive_date) else "")
        if year and archive_year_value != str(year).strip():
            continue
        if club_id:
            club_match = str(club_id).strip().lower()
            archive_club_ids = {str(item or "").strip().lower() for item in _coerce_archive_string_list(archive.get("club_ids"))}
            archive_club_id = str(archive.get("club_id") or "").strip().lower()
            if club_match not in archive_club_ids and archive_club_id != club_match:
                continue
        for performance in archive.get("suggested_performances", []) or []:
            consider(performance.get("player_name") or "", performance.get("runs") or 0)

    return milestones


def _player_stat_bucket(
    row: dict[str, Any],
    member: dict[str, Any],
    highest_score: int | None,
    *,
    full_name: str = "",
    milestones: dict[str, int] | None = None,
) -> dict[str, Any]:
    name = str(row.get("player_name") or member.get("name") or "").strip()
    milestone_values = milestones or {}
    return {
        "member_id": str(member.get("id") or "").strip(),
        "player_name": name,
        "full_name": str(full_name or member.get("full_name") or name).strip(),
        "matches": int(row.get("matches", 0) or 0),
        "batting_innings": int(row.get("batting_innings", 0) or 0),
        "outs": int(row.get("outs", 0) or 0),
        "runs": int(row.get("runs", 0) or 0),
        "balls": int(row.get("balls", 0) or 0),
        "batting_average": round(float(row.get("batting_average", 0) or 0), 2),
        "strike_rate": round(float(row.get("strike_rate", 0) or 0), 2),
        "wickets": int(row.get("wickets", 0) or 0),
        "catches": int(row.get("catches", 0) or 0),
        "fours": int(row.get("fours", 0) or 0),
        "sixes": int(row.get("sixes", 0) or 0),
        "highest_score": highest_score,
        "scores_25_plus": int(milestone_values.get("scores_25_plus", 0) or 0),
        "scores_50_plus": int(milestone_values.get("scores_50_plus", 0) or 0),
        "scores_100_plus": int(milestone_values.get("scores_100_plus", 0) or 0),
        "updated_at": now_iso(),
    }


def _build_materialized_member_stats(store: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    members = list(store.get("members", []))
    fixtures = list(store.get("fixtures", []))
    archives = canonical_archive_uploads(store.get("archive_uploads", []))

    overall_stats = {row["player_name"]: row for row in build_combined_player_stats(fixtures, archives, members)}
    overall_rows: list[dict[str, Any]] = []
    for member in members:
        name = str(member.get("name") or "").strip()
        aliases = _member_stat_hints(member)
        appearances = [
            fixture
            for fixture in fixtures
            if any(str(performance.get("player_name") or "").strip().lower() in aliases for performance in fixture.get("performances", []))
        ]
        appearances.sort(key=lambda item: str(item.get("date") or ""), reverse=True)
        last_game = appearances[0] if appearances else None
        upcoming_games = [
            fixture
            for fixture in fixtures
            if str(fixture.get("status") or "").strip().lower() == "scheduled"
            and any(str(performance.get("player_name") or "").strip().lower() in aliases for performance in fixture.get("performances", []))
        ]
        upcoming_games.sort(key=lambda item: str(item.get("date") or ""))
        next_game = upcoming_games[0] if upcoming_games else None
        overall_rows.append(
            {
                **_player_stat_bucket(
                    overall_stats.get(name, {}),
                    member,
                    _highest_score_for_member(fixtures, archives, member),
                    milestones=_batting_milestones(fixtures, archives, member),
                ),
                "last_game_date": last_game.get("date", "") if last_game else "",
                "last_opponent": last_game.get("opponent", "") if last_game else "",
                "next_game_date": next_game.get("date", "") if next_game else "",
                "next_opponent": next_game.get("opponent", "") if next_game else "",
            }
        )

    year_rows: list[dict[str, Any]] = []
    for year in _season_years(store):
        ranking_bundle = build_rankings_for_year(store, year)
        row_by_name = {row["player_name"]: row for row in ranking_bundle.get("player_stats", []) or []}
        for member in members:
            name = str(member.get("name") or "").strip()
            year_row = row_by_name.get(name)
            if not year_row:
                continue
            year_rows.append(
                {
                    **_player_stat_bucket(
                        year_row,
                        member,
                        _highest_score_for_member(fixtures, archives, member, year=year),
                        milestones=_batting_milestones(fixtures, archives, member, year=year),
                    ),
                    "season_year": str(year),
                }
            )

    club_rows: list[dict[str, Any]] = []
    club_rankings = build_club_rankings(store)
    for member in members:
        name = str(member.get("name") or "").strip()
        for club_membership in member.get("club_memberships", []) or []:
            club_name = str(club_membership.get("club_name") or "").strip()
            club_id = str(club_membership.get("club_id") or "").strip()
            if not club_id or not club_name:
                continue
            club_bundle = club_rankings.get(club_name, {})
            row_by_name = {row["player_name"]: row for row in club_bundle.get("player_stats", []) or []}
            club_row = row_by_name.get(name)
            if not club_row:
                continue
            club_rows.append(
                {
                    **_player_stat_bucket(
                        club_row,
                        member,
                        _highest_score_for_member(fixtures, archives, member, club_id=club_id),
                        milestones=_batting_milestones(fixtures, archives, member, club_id=club_id),
                    ),
                    "club_id": club_id,
                    "club_name": club_name,
                }
            )
    return overall_rows, year_rows, club_rows


def build_club_rankings(store: dict[str, Any]) -> dict[str, dict[str, list[dict[str, Any]]]]:
    rankings: dict[str, dict[str, list[dict[str, Any]]]] = {}
    for club in store.get("clubs", []) or ([store["club"]] if store.get("club") else []):
        club_store = scoped_store_for_club(store, club)
        club_members = club_store.get("members", [])
        club_id = str(club.get("id") or "").strip()
        club_fixtures = [fixture for fixture in club_store.get("fixtures", []) if str(fixture.get("club_id") or "").strip() == club_id]
        club_archives = canonical_archive_uploads(club_store.get("archive_uploads", []))
        club_stats = build_combined_player_stats(club_fixtures, club_archives, club_members)
        club_name = str(club.get("name") or "").strip()
        if not club_name:
            continue
        rankings[club_name] = {
            "player_stats": club_stats,
            "batting_rankings": build_batting_rankings(club_stats),
            "bowling_rankings": build_bowling_rankings(club_stats),
            "fielding_rankings": build_fielding_rankings(club_stats),
        }
    return rankings


def _club_match_counts(
    fixtures: list[dict[str, Any]],
    archives: list[dict[str, Any]],
    club_name: str,
    club_short_name: str,
) -> dict[str, int]:
    matches_played = 0
    matches_won = 0
    matches_lost = 0
    matches_nr = 0
    club_name = str(club_name or "").strip().lower()
    club_short_name = str(club_short_name or "").strip().lower()
    for match in fixtures:
        result_text = " ".join(
            str(part or "")
            for part in (
                match.get("result", ""),
                (match.get("scorecard") or {}).get("result", ""),
                (match.get("summary") or {}).get("result_text", ""),
            )
        ).strip().lower()
        opponent = str(match.get("opponent") or "").strip().lower()
        played, won, lost, nr = _count_match_result(result_text, club_name, club_short_name, opponent)
        if not played:
            continue
        matches_played += played
        matches_won += won
        matches_lost += lost
        matches_nr += nr
    for archive in canonical_archive_uploads(archives):
        result_text = _result_text_for_archive(archive)
        opponent = _archive_opponent_name(archive)
        played, won, lost, nr = _count_match_result(result_text, club_name, club_short_name, opponent.lower())
        if not played:
            continue
        matches_played += played
        matches_won += won
        matches_lost += lost
        matches_nr += nr
    return {
        "matches_played": matches_played,
        "matches_won": matches_won,
        "matches_lost": matches_lost,
        "matches_nr": matches_nr,
    }


def _build_materialized_club_stats(store: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    clubs = list(store.get("clubs", []) or ([store.get("club", {})] if store.get("club") else []))
    global_archives = canonical_archive_uploads(store.get("archive_uploads", []))
    overall_rows: list[dict[str, Any]] = []
    year_rows: list[dict[str, Any]] = []
    season_years = _dashboard_season_years(store)
    for club in clubs:
        club_id = str(club.get("id") or "").strip()
        club_name = str(club.get("name") or "").strip()
        if not club_id or not club_name:
            continue
        club_store = scoped_store_for_club(store, club)
        club_members = club_store.get("members", [])
        club_fixtures = _club_owned_fixtures(store, club)
        club_archives = _club_owned_archives(global_archives, club)
        club_stats = build_combined_player_stats(club_fixtures, club_archives, club_members)
        batting_rankings = build_batting_rankings(club_stats)
        highest_score = max((int(row.get("runs", 0) or 0) for row in club_stats), default=0)
        total_runs = sum(int(row.get("runs", 0) or 0) for row in club_stats)
        total_wickets = sum(int(row.get("wickets", 0) or 0) for row in club_stats)
        total_catches = sum(int(row.get("catches", 0) or 0) for row in club_stats)
        milestones = {"scores_25_plus": 0, "scores_50_plus": 0, "scores_100_plus": 0}
        for member in club_members:
            member_milestones = _batting_milestones(club_fixtures, club_archives, member, club_id=club_id)
            for key in milestones:
                milestones[key] += int(member_milestones.get(key, 0) or 0)
        overall_match_counts = _club_match_counts(club_fixtures, club_archives, club_name, str(club.get("short_name") or ""))
        overall_rows.append(
            {
                "club_id": club_id,
                "club_name": club_name,
                "season_year": _display_club_season(store, club)[:4],
                "member_count": len(_club_member_names(store, club)),
                "team_count": _club_team_count(store, club, _club_member_names(store, club)),
                "fixture_count": len(club_fixtures),
                "archive_count": _club_archive_count(club_archives, _club_member_names(store, club)),
                "total_runs": total_runs,
                "total_wickets": total_wickets,
                "total_catches": total_catches,
                "highest_score": highest_score or None,
                "top_batter": batting_rankings[0]["player_name"] if batting_rankings else "",
                "top_batter_runs": batting_rankings[0]["runs"] if batting_rankings else 0,
                "scores_25_plus": milestones["scores_25_plus"],
                "scores_50_plus": milestones["scores_50_plus"],
                "scores_100_plus": milestones["scores_100_plus"],
                **overall_match_counts,
                "updated_at": now_iso(),
            }
        )
        for year in season_years:
            year_fixtures = _filter_fixtures_by_year(club_fixtures, year)
            year_archives = _filter_archives_by_year(club_archives, year)
            year_stats = build_combined_player_stats(year_fixtures, year_archives, club_members)
            year_batting_rankings = build_batting_rankings(year_stats)
            year_highest = max((int(row.get("runs", 0) or 0) for row in year_stats), default=0)
            year_match_counts = _club_match_counts(year_fixtures, year_archives, club_name, str(club.get("short_name") or ""))
            year_rows.append(
                {
                    "club_id": club_id,
                    "season_year": str(year),
                    "club_name": club_name,
                    "member_count": len(_club_member_names(store, club)),
                    "fixture_count": len(year_fixtures),
                    "archive_count": _club_archive_count(year_archives, _club_member_names(store, club)),
                    "total_runs": sum(int(row.get("runs", 0) or 0) for row in year_stats),
                    "total_wickets": sum(int(row.get("wickets", 0) or 0) for row in year_stats),
                    "total_catches": sum(int(row.get("catches", 0) or 0) for row in year_stats),
                    "highest_score": year_highest or None,
                    "top_batter": year_batting_rankings[0]["player_name"] if year_batting_rankings else "",
                    "top_batter_runs": year_batting_rankings[0]["runs"] if year_batting_rankings else 0,
                    "scores_25_plus": sum(_batting_milestones(year_fixtures, year_archives, member, year=year)["scores_25_plus"] for member in club_members),
                    "scores_50_plus": sum(_batting_milestones(year_fixtures, year_archives, member, year=year)["scores_50_plus"] for member in club_members),
                    "scores_100_plus": sum(_batting_milestones(year_fixtures, year_archives, member, year=year)["scores_100_plus"] for member in club_members),
                    **year_match_counts,
                    "updated_at": now_iso(),
                }
            )
    return overall_rows, year_rows


def _season_years(store: dict[str, Any]) -> list[str]:
    years: set[str] = set()
    for fixture in store.get("fixtures", []):
        season_year = fixture_season_year(fixture)
        if season_year:
            years.add(season_year)
    for archive in store.get("archive_uploads", []):
        archive_year = str(archive.get("archive_year", "") or "").strip()
        archive_date = str(archive.get("archive_date", "") or "").strip()
        if re.match(r"20\d{2}", archive_year):
            years.add(archive_year[:4])
        elif re.match(r"20\d{2}", archive_date):
            years.add(archive_date[:4])
    return sorted(years)


def _filter_fixtures_by_year(fixtures: list[dict[str, Any]], year: str) -> list[dict[str, Any]]:
    target = str(year or "").strip()
    if not target:
        return list(fixtures)
    return [fixture for fixture in fixtures if fixture_season_year(fixture) == target]


def _filter_archives_by_year(archive_uploads: list[dict[str, Any]], year: str) -> list[dict[str, Any]]:
    canonical_uploads = canonical_archive_uploads(archive_uploads)
    target = str(year or "").strip()
    if not target:
        return canonical_uploads
    filtered = []
    for archive in canonical_uploads:
        archive_year = str(archive.get("archive_year", "") or "").strip()
        archive_date = str(archive.get("archive_date", "") or "").strip()
        if archive_year == target or archive_date.startswith(target):
            filtered.append(archive)
    return filtered


def _result_text_for_archive(archive: dict[str, Any]) -> str:
    draft = archive.get("draft_scorecard", {}) or {}
    return " ".join(
        str(part or "")
        for part in (
            draft.get("result", ""),
            draft.get("live_summary", ""),
            archive.get("extracted_summary", ""),
            draft.get("batting_team", ""),
            draft.get("home_team", ""),
            draft.get("visitor_team", ""),
        )
    ).strip().lower()


def _archive_opponent_name(archive: dict[str, Any]) -> str:
    draft = archive.get("draft_scorecard", {}) or {}
    return str(draft.get("opponent") or archive.get("opponent") or "").strip()


def _count_match_result(
    result_text: str,
    club_name: str,
    club_short_name: str,
    opponent_name: str = "",
) -> tuple[int, int, int, int]:
    if not result_text:
        return 0, 0, 0, 0
    if any(keyword in result_text for keyword in ("tbd", "pending", "scheduled", "awaiting", "not started", "recovered from", "imported from")):
        return 0, 0, 0, 0
    played_matches = 1
    if any(keyword in result_text for keyword in ("no result", "nr", "abandoned", "washout")):
        return played_matches, 0, 0, 1
    if any(keyword in result_text for keyword in ("tied", "tie", "draw")):
        return played_matches, 0, 0, 1
    if any(keyword in result_text for keyword in ("won", "beat", "defeated")):
        if club_name and club_name in result_text:
            return played_matches, 1, 0, 0
        if club_short_name and club_short_name in result_text:
            return played_matches, 1, 0, 0
        if opponent_name and opponent_name.lower() in result_text:
            return played_matches, 0, 1, 0
        return played_matches, 1, 0, 0
    if "lost" in result_text:
        if club_name and club_name in result_text:
            return played_matches, 0, 1, 0
        if club_short_name and club_short_name in result_text:
            return played_matches, 0, 1, 0
        return played_matches, 0, 1, 0
    return played_matches, 0, 0, 1


def build_rankings_for_year(
    store: dict[str, Any],
    year: str,
) -> dict[str, list[dict[str, Any]]]:
    fixtures = _filter_fixtures_by_year(store.get("fixtures", []), year)
    archives = _filter_archives_by_year(store.get("archive_uploads", []), year)
    combined = build_combined_player_stats(fixtures, archives, store.get("members", []))
    return {
        "player_stats": combined,
        "batting_rankings": build_batting_rankings(combined),
        "bowling_rankings": build_bowling_rankings(combined),
        "fielding_rankings": build_fielding_rankings(combined),
    }


def _default_ranking_year(store: dict[str, Any], ranking_years: list[str]) -> str:
    if not ranking_years:
        return ""
    best_year = ranking_years[-1]
    best_score = -1
    for year in ranking_years:
        ranking_bundle = build_rankings_for_year(store, year)
        score = (
            len(ranking_bundle["batting_rankings"]) * 100
            + len(ranking_bundle["bowling_rankings"]) * 10
            + len(ranking_bundle["fielding_rankings"])
        )
        if score >= best_score:
            best_score = score
            best_year = year
    return best_year


def build_summary(store: dict[str, Any]) -> dict[str, Any]:
    fixtures = store["fixtures"]
    members = store["members"]
    canonical_archives = canonical_archive_uploads(store.get("archive_uploads", []))
    opponents = Counter(match["opponent"] for match in fixtures)
    availability_board = build_availability_board(members, fixtures)
    combined_player_stats = build_combined_player_stats(fixtures, canonical_archives, members)
    batting_rankings = build_batting_rankings(combined_player_stats)
    bowling_rankings = build_bowling_rankings(combined_player_stats)
    fielding_rankings = build_fielding_rankings(combined_player_stats)
    commentary_count = sum(len(match.get("commentary", [])) for match in fixtures)
    pending_player_stats = build_player_pending_stats(canonical_archives, members)
    completed_matches = sum(1 for match in fixtures if match.get("status") == "Completed")
    live_matches = sum(1 for match in fixtures if match.get("status") == "Live")
    no_captain = sum(1 for match in fixtures if not match.get("heartlake_captain"))
    played_matches = 0
    matches_won = 0
    matches_lost = 0
    matches_nr = 0
    club_name = str(store.get("club", {}).get("name") or "").strip().lower()
    club_short_name = str(store.get("club", {}).get("short_name") or "").strip().lower()
    for match in fixtures:
        result_text = " ".join(
            str(part or "")
            for part in (
                match.get("result", ""),
                (match.get("scorecard") or {}).get("result", ""),
                (match.get("summary") or {}).get("result_text", ""),
            )
        ).strip().lower()
        opponent = str(match.get("opponent") or "").strip().lower()
        played, won, lost, nr = _count_match_result(result_text, club_name, club_short_name, opponent)
        if not played:
            continue
        played_matches += played
        matches_won += won
        matches_lost += lost
        matches_nr += nr
    for archive in canonical_archives:
        result_text = _result_text_for_archive(archive)
        opponent = _archive_opponent_name(archive)
        if opponent:
            opponents[opponent] += 1
        played, won, lost, nr = _count_match_result(result_text, club_name, club_short_name, opponent.lower())
        if not played:
            continue
        played_matches += played
        completed_matches += played
        matches_won += won
        matches_lost += lost
        matches_nr += nr
    if opponents:
        most_common_opponent, most_common_opponent_count = opponents.most_common(1)[0]
    else:
        most_common_opponent, most_common_opponent_count = "", 0
    availability_leader = availability_board[0]["player_name"] if availability_board else ""
    batting_leader = batting_rankings[0]["player_name"] if batting_rankings else ""
    batting_leader_runs = batting_rankings[0]["runs"] if batting_rankings else 0
    wicket_leader = bowling_rankings[0] if bowling_rankings else {"player_name": "", "wickets": 0}
    fielding_leader = fielding_rankings[0] if fielding_rankings else {"player_name": "", "catches": 0}
    return {
        "fixture_count": len(fixtures),
        "member_count": len(members),
        "visiting_team_count": len(opponents),
        "most_common_opponent": most_common_opponent,
        "most_common_opponent_count": most_common_opponent_count,
        "matches_without_captain": no_captain,
        "completed_matches": completed_matches,
        "live_matches": live_matches,
        "commentary_count": commentary_count,
        "archive_count": len(canonical_archives),
        "archive_file_count": len(store.get("archive_uploads", [])),
        "duplicate_count": len(store.get("duplicate_uploads", [])),
        "matches_played": played_matches,
        "matches_won": matches_won,
        "matches_lost": matches_lost,
        "matches_nr": matches_nr,
        "availability_leader": availability_leader,
        "batting_leader": batting_leader,
        "batting_leader_runs": batting_leader_runs,
        "wicket_leader": wicket_leader["player_name"],
        "wicket_leader_count": wicket_leader["wickets"],
        "fielding_leader": fielding_leader["player_name"],
        "fielding_leader_count": fielding_leader["catches"],
        "pending_player_entries": sum(item["matches"] for item in pending_player_stats if item["matches"]),
    }


def resolve_focus_club(store: dict[str, Any], focus_club_id: str = "") -> dict[str, Any]:
    clubs = store.get("clubs", []) or ([store.get("club", {})] if store.get("club") else [])
    requested = str(focus_club_id or store.get("viewer_profile", {}).get("primary_club_id") or "").strip().lower()
    if requested:
        for club in clubs:
            identifiers = {
                str(club.get("id") or "").strip().lower(),
                str(club.get("name") or "").strip().lower(),
                str(club.get("short_name") or "").strip().lower(),
            }
            if requested in identifiers:
                return club
    return store.get("club", {}) or (clubs[0] if clubs else {})


def _club_member_names(store: dict[str, Any], club: dict[str, Any]) -> set[str]:
    club_id = str(club.get("id") or "").strip()
    club_name = str(club.get("name") or "").strip()
    names = {
        member.get("name", "")
        for member in store.get("members", [])
        if member_in_club(member, club_id, club_name)
    }
    if names:
        return names
    short_name = str(club.get("short_name") or "").strip().lower()
    if short_name:
        return {
            member.get("name", "")
            for member in store.get("members", [])
            if str(member.get("team_name") or "").strip().lower() == short_name
        }
    return names


def _club_team_count(store: dict[str, Any], club: dict[str, Any], member_names: set[str]) -> int:
    club_id = str(club.get("id") or "").strip()
    club_name = str(club.get("name") or "").strip().lower()
    count = 0
    seen: set[str] = set()
    for team in store.get("teams", []):
        team_id = str(team.get("id") or "").strip()
        if team_id in seen:
            continue
        if club_id and str(team.get("club_id") or "").strip() == club_id:
            seen.add(team_id)
            count += 1
            continue
        if club_name and str(team.get("club_name") or "").strip().lower() == club_name:
            seen.add(team_id)
            count += 1
    if count:
        return count
    return len(
        {
            str(member.get("team_name") or "").strip()
            for member in store.get("members", [])
            if member.get("name") in member_names
        }
    )


def _club_archive_count(archives: list[dict[str, Any]], member_names: set[str]) -> int:
    total = 0
    for archive in archives:
        performance_names = {
            str(item.get("player_name") or "").strip()
            for item in archive.get("suggested_performances", [])
            if str(item.get("player_name") or "").strip()
        }
        if performance_names.intersection(member_names):
            total += 1
    return total


def _club_owned_fixtures(store: dict[str, Any], club: dict[str, Any]) -> list[dict[str, Any]]:
    club_id = str(club.get("id") or "").strip().lower()
    club_name = str(club.get("name") or "").strip().lower()
    club_short_name = str(club.get("short_name") or "").strip().lower()
    owned: list[dict[str, Any]] = []
    for fixture in store.get("fixtures", []):
        fixture_club_id = str(fixture.get("club_id") or "").strip().lower()
        fixture_club_name = str(fixture.get("club_name") or fixture.get("details", {}).get("club_name") or "").strip().lower()
        if club_id and fixture_club_id == club_id:
            owned.append(fixture)
            continue
        if fixture_club_name and fixture_club_name in {club_name, club_short_name}:
            owned.append(fixture)
    return owned


def _club_owned_archives(archives: list[dict[str, Any]], club: dict[str, Any]) -> list[dict[str, Any]]:
    club_id = str(club.get("id") or "").strip().lower()
    club_name = str(club.get("name") or "").strip().lower()
    club_short_name = str(club.get("short_name") or "").strip().lower()
    owned: list[dict[str, Any]] = []
    for archive in archives:
        archive_club_ids = {str(item or "").strip().lower() for item in _coerce_archive_string_list(archive.get("club_ids"))}
        archive_club_names = {str(item or "").strip().lower() for item in _coerce_archive_string_list(archive.get("club_names"))}
        archive_club_id = str(archive.get("club_id") or "").strip().lower()
        archive_club_name = str(archive.get("club_name") or "").strip().lower()
        if club_id and club_id in archive_club_ids:
            owned.append(archive)
            continue
        if club_name and club_name in archive_club_names:
            owned.append(archive)
            continue
        if club_short_name and club_short_name in archive_club_names:
            owned.append(archive)
            continue
        if club_id and archive_club_id == club_id:
            owned.append(archive)
            continue
        if archive_club_name and archive_club_name in {club_name, club_short_name}:
            owned.append(archive)
    return owned


def _duplicate_belongs_to_club(duplicate: dict[str, Any], club: dict[str, Any], archives: list[dict[str, Any]]) -> bool:
    if not club:
        return False
    club_archives = _club_owned_archives(archives, club)
    if not club_archives:
        return False
    original_name = str(duplicate.get("original_file_name") or "").strip().lower()
    original_hash = str(duplicate.get("file_hash") or "").strip().lower()
    for archive in club_archives:
        archive_name = str(archive.get("file_name") or "").strip().lower()
        archive_hash = str(archive.get("file_hash") or "").strip().lower()
        if original_name and original_name == archive_name:
            return True
        if original_hash and original_hash == archive_hash:
            return True
    return False


def _resolve_archive_club(archive: dict[str, Any], clubs: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not clubs:
        return None
    logger.debug(
        "Resolve archive club requested → archive_id=%s club_id=%s club_name=%s",
        str(archive.get("id") or ""),
        str(archive.get("club_id") or ""),
        str(archive.get("club_name") or ""),
    )
    current_ids = [str(item or "").strip().lower() for item in _coerce_archive_string_list(archive.get("club_ids"))]
    current_names = [str(item or "").strip().lower() for item in _coerce_archive_string_list(archive.get("club_names"))]
    current_id = str(archive.get("club_id") or "").strip().lower()
    current_name = str(archive.get("club_name") or "").strip().lower()
    batting_team = archive_batting_team_name(archive).lower()
    summary_text = " ".join(
        str(part or "").strip()
        for part in [
            current_name,
            archive.get("season", ""),
            archive.get("extracted_summary", ""),
            archive.get("raw_extracted_text", ""),
            archive.get("draft_scorecard", {}).get("live_summary", ""),
        ]
    ).lower()

    def club_matches(club: dict[str, Any]) -> bool:
        club_id = str(club.get("id") or "").strip().lower()
        club_name = str(club.get("name") or "").strip().lower()
        club_short_name = str(club.get("short_name") or "").strip().lower()
        if club_id and club_id in current_ids:
            return True
        if club_name and club_name in current_names:
            return True
        if club_short_name and club_short_name in current_names:
            return True
        if batting_team and batting_team in {club_name, club_short_name}:
            return True
        if current_id and current_id == club_id and not batting_team:
            return True
        if current_name and current_name in {club_name, club_short_name} and not batting_team:
            return True
        identifiers = {club_name, club_short_name}
        return any(identifier and identifier in summary_text for identifier in identifiers)

    matched = [club for club in clubs if club_matches(club)]
    if len(matched) == 1:
        logger.debug("Resolve archive club matched uniquely → archive_id=%s club_id=%s", str(archive.get("id") or ""), str(matched[0].get("id") or ""))
        return matched[0]
    if current_ids:
        for club_id in current_ids:
            current = next((club for club in clubs if str(club.get("id") or "").strip().lower() == club_id), None)
            if current:
                return current
    if batting_team:
        batting_matches = [
            club
            for club in clubs
            if batting_team
            in {
                str(club.get("name") or "").strip().lower(),
                str(club.get("short_name") or "").strip().lower(),
            }
        ]
        if len(batting_matches) == 1:
            return batting_matches[0]
    if current_id:
        current = next((club for club in clubs if str(club.get("id") or "").strip().lower() == current_id), None)
        if current:
            return current
    return matched[0] if matched else None


def _find_club_year_stats(store: dict[str, Any], club_id: str, season_year: str) -> dict[str, Any] | None:
    if not club_id or not season_year:
        return None
    club_id = str(club_id).strip().lower()
    season_year = str(season_year).strip()
    return next(
        (
            row
            for row in store.get("club_year_stats", [])
            if str(row.get("club_id") or "").strip().lower() == club_id
            and str(row.get("season_year") or "").strip() == season_year
        ),
        None,
    )


def _club_dashboard_card(
    store: dict[str, Any],
    club: dict[str, Any],
    combined_stats: list[dict[str, Any]],
    archives: list[dict[str, Any]],
    season_year: str = "",
) -> dict[str, Any]:
    member_names = _club_member_names(store, club)
    club_stats = list(combined_stats)
    batting_rankings = build_batting_rankings(club_stats)
    club_fixtures = _club_owned_fixtures(store, club)
    season_stats = _find_club_year_stats(store, str(club.get("id") or ""), season_year)
    return {
        "id": str(club.get("id") or "").strip(),
        "name": str(club.get("name") or "").strip(),
        "short_name": str(club.get("short_name") or "").strip(),
        "season": _display_club_season(store, club),
        "member_count": len(member_names),
        "team_count": _club_team_count(store, club, member_names),
        "fixture_count": season_stats["fixture_count"] if season_stats and season_stats.get("fixture_count") is not None else len(club_fixtures),
        "archive_count": season_stats["archive_count"] if season_stats and season_stats.get("archive_count") is not None else _club_archive_count(archives, member_names),
        "top_batter": season_stats["top_batter"] if season_stats and season_stats.get("top_batter") else (batting_rankings[0]["player_name"] if batting_rankings else ""),
        "top_batter_runs": season_stats["top_batter_runs"] if season_stats and season_stats.get("top_batter_runs") is not None else (batting_rankings[0]["runs"] if batting_rankings else 0),
    }


def _filter_archives_for_club(archives: list[dict[str, Any]], club: dict[str, Any], member_names: set[str]) -> list[dict[str, Any]]:
    filtered = []
    for archive in archives:
        if archive_belongs_to_club(archive, club):
            filtered.append(archive)
    return filtered


def scoped_store_for_club(store: dict[str, Any], club: dict[str, Any]) -> dict[str, Any]:
    focused = dict(store)
    member_names = _club_member_names(store, club)
    focused_members = [member for member in store.get("members", []) if member.get("name") in member_names]
    club_id = str(club.get("id") or "").strip()
    club_name = str(club.get("name") or "").strip().lower()
    club_short_name = str(club.get("short_name") or "").strip().lower()

    focused_teams = []
    for team in store.get("teams", []):
        team_club_id = str(team.get("club_id") or "").strip()
        team_club_name = str(team.get("club_name") or "").strip().lower()
        team_name = str(team.get("name") or "").strip().lower()
        if club_id and team_club_id == club_id:
            focused_teams.append(team)
        elif club_name and team_club_name == club_name:
            focused_teams.append(team)
        elif club_short_name and team_name == club_short_name:
            focused_teams.append(team)
        elif any(member.get("team_name") == team.get("name") for member in focused_members):
            focused_teams.append(team)

    focused_fixtures = _club_owned_fixtures(store, club)
    focused_archives = _club_owned_archives(store.get("archive_uploads", []), club)

    focused["club"] = club
    focused["members"] = focused_members
    focused["teams"] = focused_teams
    focused["fixtures"] = focused_fixtures
    focused["archive_uploads"] = focused_archives
    return focused


def build_dashboard(
    store: dict[str, Any],
    llm_status: dict[str, Any],
    focus_club_id: str = "",
    requested_season_year: str = "",
) -> dict[str, Any]:
    store_signature = _store_cache_signature(store)
    dashboard_cache_key = (
        store_signature,
        str(focus_club_id or "").strip(),
        str(requested_season_year or "").strip(),
        json.dumps(llm_status or {}, sort_keys=True, default=str),
    )
    cached_dashboard = _DASHBOARD_CACHE.get(dashboard_cache_key)
    if cached_dashboard is not None:
        logger.debug(
            "Build dashboard served from memory cache → club=%s year=%s signature=%s",
            focus_club_id or "",
            requested_season_year or "",
            store_signature,
        )
        return deepcopy(cached_dashboard)
    focus_club = resolve_focus_club(store, focus_club_id)
    focused_store = scoped_store_for_club(store, focus_club)
    global_members = list(store.get("members", []))
    global_fixtures = list(store.get("fixtures", []))
    global_archives = canonical_archive_uploads(store.get("archive_uploads", []))
    club_duplicate_uploads = [
        duplicate
        for duplicate in list(reversed(store.get("duplicate_uploads", [])))
        if _duplicate_belongs_to_club(duplicate, focus_club, focused_store.get("archive_uploads", []))
    ]
    selected_year = _resolve_dashboard_season_year(store, requested_season_year)
    season_label = _season_label_for_year(selected_year)
    season_years = _dashboard_season_years(store)
    season_fixtures = _filter_fixtures_by_year(_club_owned_fixtures(store, focus_club), selected_year)
    season_archives = _filter_archives_by_year(_club_owned_archives(global_archives, focus_club), selected_year)
    season_store = dict(focused_store)
    season_store["fixtures"] = season_fixtures
    season_store["archive_uploads"] = season_archives
    season_store["duplicate_uploads"] = club_duplicate_uploads
    ordered_clubs = sorted(
        store.get("clubs", []) or ([store["club"]] if store.get("club") else []),
        key=lambda club: (
            0 if str(club.get("id") or "").strip() == str(focus_club.get("id") or "").strip() else 1,
            str(club.get("name") or ""),
        ),
    )
    ordered_teams = sorted(
        focused_store.get("teams", []),
        key=lambda team: (
            0 if str(team.get("club_id") or "").strip() == str(focus_club.get("id") or "").strip() else 1,
            str(team.get("display_name") or team.get("name") or ""),
        ),
    )
    summary = build_summary(season_store)
    season_club_year_stats = _find_club_year_stats(store, str(focus_club.get("id") or ""), selected_year)
    if season_club_year_stats:
        summary = {
            **summary,
            "member_count": season_club_year_stats.get("member_count", summary.get("member_count")),
            "fixture_count": season_club_year_stats.get("fixture_count", summary.get("fixture_count")),
            "archive_count": season_club_year_stats.get("archive_count", summary.get("archive_count")),
            "top_batter": season_club_year_stats.get("top_batter") or summary.get("top_batter"),
            "top_batter_runs": season_club_year_stats.get("top_batter_runs") if season_club_year_stats.get("top_batter_runs") is not None else summary.get("top_batter_runs"),
            "highest_score": season_club_year_stats.get("highest_score", summary.get("highest_score")),
            "total_runs": season_club_year_stats.get("total_runs", summary.get("total_runs")),
            "total_wickets": season_club_year_stats.get("total_wickets", summary.get("total_wickets")),
            "total_catches": season_club_year_stats.get("total_catches", summary.get("total_catches")),
            "matches_played": season_club_year_stats.get("matches_played", summary.get("matches_played")),
            "matches_won": season_club_year_stats.get("matches_won", summary.get("matches_won")),
            "matches_lost": season_club_year_stats.get("matches_lost", summary.get("matches_lost")),
            "matches_nr": season_club_year_stats.get("matches_nr", summary.get("matches_nr")),
            "scores_25_plus": season_club_year_stats.get("scores_25_plus", summary.get("scores_25_plus")),
            "scores_50_plus": season_club_year_stats.get("scores_50_plus", summary.get("scores_50_plus")),
            "scores_100_plus": season_club_year_stats.get("scores_100_plus", summary.get("scores_100_plus")),
        }
    fixtures = sorted(season_fixtures, key=lambda item: item["date"])
    upcoming = next((match for match in fixtures if match["status"] != "Completed"), fixtures[0] if fixtures else {})
    global_pending_player_stats = build_player_pending_stats(global_archives, global_members)
    global_player_stats = build_player_stats(global_fixtures, global_members)
    global_combined_player_stats = build_combined_player_stats(global_fixtures, global_archives, global_members)
    pending_player_stats = build_player_pending_stats(season_archives, focused_store["members"])
    player_stats = build_player_stats(season_fixtures, focused_store["members"])
    combined_player_stats = build_combined_player_stats(season_fixtures, season_archives, focused_store["members"])
    focus_fixtures = fixtures
    focus_stats = list(combined_player_stats)
    focus_batting_rankings = build_batting_rankings(focus_stats)
    club_directory = []
    season_club_rankings: dict[str, dict[str, list[dict[str, Any]]]] = {}
    for club in store.get("clubs", []) or []:
        club_store = scoped_store_for_club(store, club)
        club_archives = _filter_archives_by_year(_club_owned_archives(global_archives, club), selected_year)
        club_fixtures = _filter_fixtures_by_year(_club_owned_fixtures(store, club), selected_year)
        club_stats = build_combined_player_stats(club_fixtures, club_archives, club_store.get("members", []))
        club_name = str(club.get("name") or "").strip()
        if club_name:
            season_club_rankings[club_name] = {
                "player_stats": club_stats,
                "batting_rankings": build_batting_rankings(club_stats),
                "bowling_rankings": build_bowling_rankings(club_stats),
                "fielding_rankings": build_fielding_rankings(club_stats),
            }
        club_directory.append(_club_dashboard_card(store, club, club_stats, club_archives, selected_year))
    club_directory.sort(
        key=lambda club: (
            0 if str(club.get("id") or "").strip() == str(focus_club.get("id") or "").strip() else 1,
            str(club.get("name") or ""),
        )
    )
    followed_players = [
        {
            "player_name": member.get("name", ""),
            "full_name": member.get("full_name", ""),
            "team_name": member.get("team_name", ""),
            "runs": next((item.get("runs", 0) for item in combined_player_stats if item.get("player_name") == member.get("name")), 0),
            "matches": next((item.get("matches", 0) for item in combined_player_stats if item.get("player_name") == member.get("name")), 0),
            "wickets": next((item.get("wickets", 0) for item in combined_player_stats if item.get("player_name") == member.get("name")), 0),
            "catches": next((item.get("catches", 0) for item in combined_player_stats if item.get("player_name") == member.get("name")), 0),
        }
        for member in store.get("members", [])
        if member.get("name") in store.get("viewer_profile", {}).get("followed_player_names", [])
    ]
    dashboard = {
        "club": focus_club or focused_store["club"],
        "clubs": ordered_clubs,
        "visible_clubs": [dict(focus_club or store["club"])],
        "focus_club": focus_club or store["club"],
        "teams": ordered_teams,
        "members": focused_store["members"],
        "all_members": global_members,
        "fixtures": fixtures,
        "summary": summary,
        "upcoming_match": upcoming,
        "visiting_teams": build_visiting_teams(fixtures),
        "availability_board": build_availability_board(focused_store["members"], fixtures),
        "player_stats": player_stats,
        "combined_player_stats": combined_player_stats,
        "all_player_stats": global_player_stats,
        "all_combined_player_stats": global_combined_player_stats,
        "all_player_pending_stats": global_pending_player_stats,
        "member_summary_stats": list(store.get("member_summary_stats", [])),
        "member_year_stats": list(store.get("member_year_stats", [])),
        "member_club_stats": list(store.get("member_club_stats", [])),
        "club_summary_stats": list(store.get("club_summary_stats", [])),
        "club_year_stats": list(store.get("club_year_stats", [])),
        "all_fixtures": global_fixtures,
        "all_archive_uploads": global_archives,
        "batting_rankings": build_batting_rankings(focus_stats),
        "bowling_rankings": build_bowling_rankings(focus_stats),
        "fielding_rankings": build_fielding_rankings(focus_stats),
        "club_rankings": season_club_rankings,
        "season_years": season_years,
        "default_season_year": selected_year,
        "selected_season_year": selected_year,
        "ranking_years": season_years,
        "default_ranking_year": selected_year,
        "player_pending_stats": pending_player_stats,
        "archive_uploads": list(reversed(season_archives)),
        "archive_file_uploads": list(reversed(focused_store["archive_uploads"])),
        "duplicate_uploads": club_duplicate_uploads,
        "llm": llm_status,
        "insights": focused_store["insights"],
        "viewer_profile": store.get("viewer_profile", dict(DEFAULT_VIEWER_PROFILE)),
        "landing_upcoming_matches": focus_fixtures[:10],
        "landing_club_stats": {
            "member_count": len(_club_member_names(store, focus_club)),
            "team_count": _club_team_count(store, focus_club, _club_member_names(store, focus_club)),
            "fixture_count": season_club_year_stats.get("fixture_count") if season_club_year_stats and season_club_year_stats.get("fixture_count") is not None else len(focus_fixtures),
            "archive_count": season_club_year_stats.get("archive_count") if season_club_year_stats and season_club_year_stats.get("archive_count") is not None else _club_archive_count(season_archives, _club_member_names(store, focus_club)),
            "top_batter": season_club_year_stats.get("top_batter") if season_club_year_stats and season_club_year_stats.get("top_batter") else (focus_batting_rankings[0]["player_name"] if focus_batting_rankings else ""),
            "top_batter_runs": season_club_year_stats.get("top_batter_runs") if season_club_year_stats and season_club_year_stats.get("top_batter_runs") is not None else (focus_batting_rankings[0]["runs"] if focus_batting_rankings else 0),
        },
        "club_directory": club_directory,
        "followed_players": followed_players,
    }
    if dashboard.get("club"):
        dashboard["club"] = dict(dashboard["club"])
        dashboard["club"]["season"] = season_label
    if dashboard.get("focus_club"):
        dashboard["focus_club"] = dict(dashboard["focus_club"])
        dashboard["focus_club"]["season"] = season_label
    dashboard["clubs"] = [
        {**club, "season": season_label}
        for club in ordered_clubs
    ]
    dashboard["visible_clubs"] = [
        {**club, "season": season_label}
        for club in dashboard["visible_clubs"]
    ]
    dashboard["club_directory"] = [
        {**club, "season": season_label}
        for club in club_directory
    ]
    _write_text_atomic(DASHBOARD_CACHE_FILE, json.dumps(dashboard, indent=2))
    _DASHBOARD_CACHE[dashboard_cache_key] = deepcopy(dashboard)
    return dashboard
