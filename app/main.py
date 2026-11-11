import hashlib
import hmac
import json
import html
import os
import re
import secrets
import sqlite3
import shutil
import threading
import time as time_module
import httpx
from collections import Counter, defaultdict
from difflib import SequenceMatcher
from copy import deepcopy
from urllib import request
from urllib.parse import urlencode
import uuid
from datetime import datetime, date, timedelta, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

# The clubs play in Ontario, but Azure's servers run on GMT/UTC: a match started at 12:08 AM showed "4:08 AM"
# and "today" could be tomorrow's date in the evening. Run the whole app on the clubs' time zone
# (APP_TIMEZONE, default America/Toronto) so datetime.now() / date.today() are local everywhere.
# Stored timestamps from now_iso() stay UTC (with "Z"). README "Local time (Oct 29 2026)".
APP_TIMEZONE = os.getenv("APP_TIMEZONE", "America/Toronto")
if hasattr(__import__("time"), "tzset"):  # Linux / Mac (Azure); Windows already uses the PC's own time zone
    os.environ["TZ"] = APP_TIMEZONE
    __import__("time").tzset()


from fastapi import FastAPI, File, Form, Header, HTTPException, Request, Response, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.background import BackgroundTask
from pydantic import BaseModel, Field

import sqlite3
import logging

logger = logging.getLogger("CricketClubApp")


def _current_local_date() -> date:
    try:
        return datetime.now(ZoneInfo("America/Toronto")).date()
    except Exception:
        return datetime.now().date()


def _scorebook_is_open(match: dict[str, Any]) -> bool:
    status = str(match.get("status") or "").strip().lower()
    raw_date = str(match.get("date") or "").strip()
    if not raw_date:
        return False
    try:
        match_day = datetime.fromisoformat(raw_date[:10]).date()
    except Exception:
        return False
    today = _current_local_date()
    if match_day < today:
        return False
    if status == "completed":
        return False
    return match_day == today or status in {"live", "in progress"}


def _fixture_is_past(match: dict[str, Any]) -> bool:
    """True when the fixture's date is before today (Toronto time). Live match actions are locked."""
    raw_date = str((match or {}).get("date") or "").strip()[:10]
    if not raw_date:
        return False
    try:
        return datetime.fromisoformat(raw_date).date() < _current_local_date()
    except Exception:
        return False


def _fixture_is_completed(match: dict[str, Any]) -> bool:
    status = str((match or {}).get("status") or "").strip().lower()
    if status in {"complete", "completed", "finished", "final"}:
        return True
    results = (
        (match or {}).get("result"),
        ((match or {}).get("scorecard") or {}).get("result"),
    )
    incomplete_results = {"", "tbd", "to be determined", "pending", "not recorded", "in progress", "ongoing"}
    if any(str(result or "").strip().lower() not in incomplete_results for result in results):
        return True
    innings = ((match or {}).get("scorebook") or {}).get("innings") or []
    completed_innings = [
        str(innings_row.get("status") or "").strip().lower()
        for innings_row in innings
    ]
    return len(completed_innings) >= 2 and all(
        innings_status in {"complete", "completed", "finished"}
        for innings_status in completed_innings
    )


def _require_not_past(match: dict[str, Any], what: str = "scores and availability") -> None:
    """Scores, availability and the playing XI of past matches can't be changed (README: "Past matches are locked")."""
    if _fixture_is_past(match):
        label = str(match.get("date_label") or match.get("date") or "an earlier date")
        raise HTTPException(
            status_code=403,
            detail=f"This match was on {label}. Past matches are locked, so {what} can't be changed."
            + (" To add an old score, upload the scorecard photo in Archives." if what == "scores" else ""),
        )

_AUTH_SCHEMA_BOOTSTRAP_LOCK = threading.Lock()
_AUTH_SCHEMA_BOOTSTRAP_DONE = False

if not logger.handlers:
    app_env = str(
        os.getenv("APP_ENV")
        or os.getenv("ENVIRONMENT")
        or os.getenv("AZURE_ENVIRONMENT")
        or os.getenv("WEBSITE_INSTANCE_ID")
        or "local"
    ).strip().lower()
    log_level = logging.DEBUG if app_env in {"local", "dev", "development", "debug", ""} else logging.ERROR
    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)
    if not root_logger.handlers:
        stream_handler = logging.StreamHandler()
        stream_handler.setLevel(log_level)
        stream_handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] [%(name)s] %(message)s"))
        root_logger.addHandler(stream_handler)
    else:
        for handler in root_logger.handlers:
            handler.setLevel(log_level)
            if handler.formatter is None:
                handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] [%(name)s] %(message)s"))
    logger.setLevel(log_level)
    logger.propagate = True

try:
    import scorecard_pdf
    from cricket_brain import answer_question, get_llm_status
    import cricket_insights as cricket_insights
    import muse as muse
    import muse_agent as muse_agent
    import subscriptions as subscriptions
    import ai_scorer as ai_scorer
    import scorecard_checks as scorecard_checks
    import ai_vision as ai_vision
    import ai_chat as ai_chat
    from llm_service import clear_query_cache, infer as llm_infer, list_llm_documents, list_prompt_manifest, reindex_llm_corpus
    from player_merge import MergeError, choose_survivor, merge_members_in_store
    from ai_duplicate_engine import AIDuplicateEngine, identity_names
    from cricket_store import (
        card_sides_are_swapped,
        inferred_innings_teams_for_archive,
        side_anchors,
        ocr_rows_look_real,
        normalize_name,
        BASE_DIR,
        CACHE_FILE,
        DATABASE_FILE,
        DASHBOARD_CACHE_FILE,
        DUPLICATE_DIR,
        UPLOAD_DIR,
        archive_record_from_file,
        build_dashboard,
        build_summary,
        build_batting_rankings,
        build_bowling_rankings,
        build_combined_player_stats,
        _build_materialized_member_stats,
        canonical_phone,
        canonical_archive_uploads,
        create_duplicate_record_from_bytes,
        default_scorecard,
        default_match_scorebook,
        auto_register_players_from_archive,
        club_season_year,
        archive_belongs_to_club,
        archive_club_context,
        archive_has_persisted_json,
        _coerce_archive_string_list,
        extract_archive_by_id,
        fixture_season_year,
        get_archive_or_404,
        get_match_or_404,
        load_store,
        member_initials,
        member_in_club,
        now_iso,
        normalize_scorebook_ball,
        _resolve_archive_club,
        reset_score_data,
        resolve_member_name,
        review_scorecard_template_with_llm,
        scorecard_template_from_archive,
        save_store,
        scoped_store_for_club,
        _club_stat_fixtures,
        _club_dashboard_fixture_view,
        _scorebook_is_club_side,
        summarize_innings_scorebook,
        scorebook_match_finished,
        scorebook_wickets_for_all_out,
        scorebook_result_text,
        sync_fixture_scorecard_from_scorebook,
    )
except ModuleNotFoundError:
    from app import scorecard_pdf
    from app.cricket_brain import answer_question, get_llm_status
    from app import cricket_insights
    from app import muse
    from app import muse_agent
    from app import subscriptions
    from app import ai_scorer
    from app import scorecard_checks
    from app import ai_vision
    from app import ai_chat
    from app.llm_service import clear_query_cache, infer as llm_infer, list_llm_documents, list_prompt_manifest, reindex_llm_corpus
    from app.player_merge import MergeError, choose_survivor, merge_members_in_store
    from app.ai_duplicate_engine import AIDuplicateEngine, identity_names
    from app.cricket_store import (
        card_sides_are_swapped,
        inferred_innings_teams_for_archive,
        side_anchors,
        ocr_rows_look_real,
        normalize_name,
        BASE_DIR,
        CACHE_FILE,
        DATABASE_FILE,
        DASHBOARD_CACHE_FILE,
        DUPLICATE_DIR,
        UPLOAD_DIR,
        archive_record_from_file,
        build_dashboard,
        build_summary,
        build_batting_rankings,
        build_bowling_rankings,
        build_combined_player_stats,
        _build_materialized_member_stats,
        canonical_phone,
        canonical_archive_uploads,
        create_duplicate_record_from_bytes,
        default_scorecard,
        default_match_scorebook,
        auto_register_players_from_archive,
        club_season_year,
        archive_belongs_to_club,
        archive_club_context,
        archive_has_persisted_json,
        _coerce_archive_string_list,
        extract_archive_by_id,
        fixture_season_year,
        get_archive_or_404,
        get_match_or_404,
        load_store,
        member_initials,
        member_in_club,
        now_iso,
        normalize_scorebook_ball,
        _resolve_archive_club,
        reset_score_data,
        resolve_member_name,
        review_scorecard_template_with_llm,
        scorecard_template_from_archive,
        save_store,
        scoped_store_for_club,
        _club_stat_fixtures,
        _club_dashboard_fixture_view,
        _scorebook_is_club_side,
        summarize_innings_scorebook,
        scorebook_match_finished,
        scorebook_wickets_for_all_out,
        scorebook_result_text,
        sync_fixture_scorecard_from_scorebook,
    )


STATIC_DIR = BASE_DIR / "static"


app = FastAPI(
    title="CricketClubApp",
    version="0.2.0",
    description="Local website for club operations, scoring, availability, archive recovery, and AI-assisted queries.",
)

MIN_SEASON_SETUP_YEAR = 2026
SESSION_TIMEOUT_MINUTES = 30

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)
# Squeeze JSON and pages (about 8x smaller), so the live scorecard and the Score page stay quick on
# phone data at the ground (README "Live page like a cricket score app (Oct 30 2026)").
app.add_middleware(GZipMiddleware, minimum_size=1024)


def _canonical_dashboard_widget_path(path: str) -> str:
    clean_path = str(path or "").rstrip("/")
    if not clean_path.startswith("/dashboard/widgets/"):
        return clean_path or path
    widget_name = clean_path[len("/dashboard/widgets/") :].strip().lower()
    widget_aliases = {
        "club-performance": "performance",
        "performances": "performance",
        "fixtures": "schedule",
        "upcoming-fixtures": "schedule",
        "availability": "availability",
        "playing-xi": "match-center",
        "rankings": "performance",
        "players": "player-profile",
        "profile": "player-profile",
        "player-profile": "player-profile",
        "assistant": "assistant",
        "scorecards": "archive",
        "scoring": "scoring",
        "commentary": "commentary",
        "squad": "squad",
        "archive": "archive",
        "match-center": "match-center",
        "teams": "teams",
        "schedule": "schedule",
        "more": "more",
    }
    canonical = widget_aliases.get(widget_name, widget_name)
    return f"/dashboard/widgets/{canonical}" if canonical else clean_path


@app.middleware("http")
async def _log_http_requests(request: Request, call_next):
    canonical_path = _canonical_dashboard_widget_path(request.scope.get("path", ""))
    if canonical_path != request.scope.get("path", ""):
        request.scope["path"] = canonical_path
    start = datetime.utcnow()
    path = request.url.path
    query = request.url.query
    visitor_cookie = str(request.cookies.get("ccVisitorId") or "").strip().lower()
    issue_visitor_cookie = not re.fullmatch(r"[a-f0-9]{32}", visitor_cookie)
    visitor_id = uuid.uuid4().hex if issue_visitor_cookie else visitor_cookie
    request.state.cc_visitor_id = visitor_id
    audience_poll = request.method == "GET" and path.startswith("/api/public/match/") and not path.endswith(".pdf")
    if logger.isEnabledFor(logging.DEBUG):
        logger.debug(
            "HTTP request started. method=%s path=%s query=%s auth_cookie=%s",
            request.method,
            path,
            query or "",
            bool(request.cookies.get("cricketClubAppAuthToken")),
        )
    try:
        response = await call_next(request)
    except Exception as exc:
        if exc.__class__.__name__ == "EndOfStream":
            logger.debug(
                "HTTP request disconnected. method=%s path=%s",
                request.method,
                path,
            )
            return Response(status_code=499)
        logger.exception("HTTP request error. method=%s path=%s", request.method, path)
        raise
    duration_ms = int((datetime.utcnow() - start).total_seconds() * 1000)
    if logger.isEnabledFor(logging.DEBUG):
        logger.debug(
            "HTTP request complete. method=%s path=%s status=%s duration_ms=%s",
            request.method,
            path,
            getattr(response, "status_code", 0),
            duration_ms,
        )
    elif getattr(response, "status_code", 200) >= 400:
        logger.error(
            "HTTP request failed. method=%s path=%s status=%s duration_ms=%s",
            request.method,
            path,
            getattr(response, "status_code", 0),
            duration_ms,
        )
    if path.startswith("/assets/"):
        response.headers["Cache-Control"] = "no-cache"
    is_html_page = (
        request.method == "GET"
        and getattr(response, "status_code", 500) < 400
        and response.headers.get("content-type", "").lower().startswith("text/html")
    )
    if is_html_page:
        try:
            _record_site_visit(request, visitor_id, path)
        except Exception:
            logger.exception("Could not record site visit.")
    if issue_visitor_cookie and (is_html_page or audience_poll):
        response.set_cookie(
            "ccVisitorId",
            visitor_id,
            max_age=60 * 60 * 24 * 365,
            httponly=True,
            secure=request.url.scheme == "https",
            samesite="lax",
            path="/",
        )
    return response

app.mount("/assets", StaticFiles(directory=STATIC_DIR), name="assets")
app.mount("/uploads", StaticFiles(directory=UPLOAD_DIR), name="uploads")
app.mount("/duplicates", StaticFiles(directory=DUPLICATE_DIR), name="duplicates")


def _page_response(filename: str) -> FileResponse:
    return FileResponse(
        STATIC_DIR / filename,
        headers={
            "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
            "Pragma": "no-cache",
        },
    )


def _identity_badge_html(display_name: str, role: str) -> str:
    safe_name = html.escape(str(display_name or "Signed in").strip() or "Signed in")
    safe_role = html.escape(str(role or "Player").strip() or "Player")
    initials = "".join(
        part[:1].upper()
        for part in str(display_name or "").strip().split()
        if part
    )[:2] or "CC"
    safe_initials = html.escape(initials)
    return f"""
      <div id="userIdentityBadge" class="user-chip" aria-live="polite">
        <span class="user-chip-mark" aria-hidden="true">{safe_initials}</span>
        <span class="user-chip-copy">
          <strong>{safe_name}</strong>
          <span>{safe_role}</span>
        </span>
      </div>
    """


def _club_badge_html(club_name: str) -> str:
    safe_name = html.escape(str(club_name or "No club selected").strip() or "No club selected")
    initials = "".join(part[:1].upper() for part in safe_name.split() if part)[:2] or "CL"
    return f"""
      <div id="currentClubBadge" class="club-chip" aria-live="polite">
        <span class="club-chip-mark" aria-hidden="true">{html.escape(initials)}</span>
        <span class="club-chip-copy">
          <small>Club</small>
          <strong>{safe_name}</strong>
        </span>
      </div>
    """


def _season_setup_page_html(request: Request) -> HTMLResponse | RedirectResponse:
    session = _require_page_session(request)
    if isinstance(session, RedirectResponse):
        return session
    token = _auth_token_from_request(request)
    store = load_store()
    user_row, current_club_id = _auth_user_from_token(token) if token else (None, "")
    club = _selected_club(store, current_club_id)
    scoped = scoped_store_for_club(store, club)
    fixtures = sorted(
        scoped.get("fixtures", []),
        key=lambda fixture: (str(fixture.get("date") or ""), str(fixture.get("opponent") or "")),
    )
    current_year = str(datetime.utcnow().year)
    season_years = {
        fixture_season_year(fixture)
        for fixture in fixtures
        if fixture_season_year(fixture)
    }
    season_years.add(current_year)
    viewer_selected_year = str(store.get("viewer_profile", {}).get("selected_season_year") or "").strip()
    if re.match(r"20\d{2}$", viewer_selected_year):
        season_years.add(viewer_selected_year)
    selected_year = current_year
    if not re.match(r"20\d{2}$", selected_year):
        selected_year = str(MIN_SEASON_SETUP_YEAR)
    season_years = sorted(
        {str(year).strip() for year in season_years if str(year).strip()},
        reverse=True,
    )
    if selected_year not in season_years:
        season_years = sorted({*season_years, selected_year}, reverse=True)

    badge_html = ""
    if user_row is not None:
        user_payload = _auth_user_payload(user_row, current_club_id)
        badge_html = _identity_badge_html(
            str(user_payload.get("display_name") or user_payload.get("email") or user_payload.get("mobile") or "Signed in"),
            str(user_payload.get("effective_role") or user_payload.get("role") or "Player"),
        )
    options_html = "".join(
        f'<option value="{html.escape(year)}"{(" selected" if year == selected_year else "")}>{html.escape(year)} Season</option>'
        for year in season_years
    )
    filtered_fixtures = [
        fixture
        for fixture in fixtures
        if str(fixture_season_year(fixture) or "") == selected_year
    ]
    fixture_cards = "".join(
        f"""
        <article class="detail-card">
          <strong>{html.escape(str(fixture.get("date_label") or fixture.get("date") or "Fixture"))} vs {html.escape(str(fixture.get("opponent") or "Opponent"))}</strong>
          <p>{html.escape(str(fixture.get("venue") or "Venue TBD"))} · {html.escape(str(fixture.get("scheduled_time") or "Time TBD"))}</p>
          <small>{html.escape(str(fixture.get("season") or f"{fixture_season_year(fixture) or selected_year} Season"))} · {html.escape(str(fixture.get("status") or "Scheduled"))}</small>
        </article>
        """
        for fixture in filtered_fixtures
    ) or '<p class="empty-state">No fixtures created yet for this club.</p>'
    body = (STATIC_DIR / "season_setup.html").read_text(encoding="utf-8")
    body = body.replace(
        '<select id="seasonFilter"></select>',
        f'<select id="seasonFilter">{options_html}</select>',
    )
    body = body.replace(
        '<div id="seasonFixtures" class="detail-stack"></div>',
        f'<div id="seasonFixtures" class="detail-stack">{fixture_cards}</div>',
    )
    body = body.replace(
        '<div class="topbar-actions">\n          <a class="secondary-button" href="/signout">Sign out</a>\n        </div>',
        f'<div class="topbar-actions">\n          {_club_badge_html(str(club.get("name") or "Selected club"))}\n          {badge_html}\n          <a class="secondary-button" href="/signout">Sign out</a>\n        </div>',
    )
    return HTMLResponse(
        body,
        headers={
            "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
            "Pragma": "no-cache",
        },
    )


def _redirect_to_signin() -> RedirectResponse:
    response = RedirectResponse(url="/signin", status_code=303)
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    response.headers["Pragma"] = "no-cache"
    return response


def _redirect_to_admin_center(club_id: str = "", notice: str = "", tone: str = "success") -> RedirectResponse:
    params: list[tuple[str, str]] = []
    if club_id:
        params.append(("club_id", str(club_id)))
    if notice:
        params.append(("notice", str(notice)))
    if tone:
        params.append(("tone", str(tone)))
    query = f"?{urlencode(params)}" if params else ""
    response = RedirectResponse(url=f"/admin-center{query}", status_code=303)
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    response.headers["Pragma"] = "no-cache"
    return response


def _require_page_session(request: Request) -> tuple[sqlite3.Row, str] | RedirectResponse:
    token = _auth_token_from_request(request)
    if not token:
        return _redirect_to_signin()
    try:
        return _auth_user_from_token(token)
    except HTTPException:
        return _redirect_to_signin()


def _site_visitor_key(request: Request, visitor_id: str | None = None) -> str:
    ensure_auth_schema()
    token = _auth_token_from_request(request)
    if token:
        with _auth_connection() as connection:
            row = connection.execute(
                "SELECT user_id FROM app_auth_sessions WHERE token = ? AND ended_at IS NULL",
                (token,),
            ).fetchone()
        if row:
            return f"user:{int(row['user_id'])}"
    clean_id = str(visitor_id or getattr(request.state, "cc_visitor_id", "") or "").strip()
    return "visitor:" + hashlib.sha256(clean_id.encode("utf-8")).hexdigest()


def _record_site_visit(request: Request, visitor_id: str, page_path: str) -> None:
    ensure_auth_schema()
    now = datetime.now(timezone.utc).replace(microsecond=0)
    timestamp = now.isoformat().replace("+00:00", "Z")
    bucket = now.replace(minute=0, second=0).isoformat().replace("+00:00", "Z")
    visitor_key = _site_visitor_key(request, visitor_id)
    with _auth_connection() as connection:
        connection.execute(
            """
            INSERT INTO app_analytics_visits(visitor_key, bucket_hour, visited_at, page_path)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(visitor_key, bucket_hour) DO UPDATE SET
              visited_at = excluded.visited_at,
              page_path = excluded.page_path
            """,
            (visitor_key, bucket, timestamp, page_path[:300]),
        )


def _touch_live_match_viewer(match_id: str, request: Request) -> int:
    ensure_auth_schema()
    now = datetime.now(timezone.utc).replace(microsecond=0)
    timestamp = now.isoformat().replace("+00:00", "Z")
    active_since = (now - timedelta(seconds=45)).isoformat().replace("+00:00", "Z")
    visitor_key = _site_visitor_key(request)
    with _auth_connection() as connection:
        connection.execute(
            """
            INSERT INTO app_live_match_viewers(match_id, visitor_key, last_seen_at)
            VALUES (?, ?, ?)
            ON CONFLICT(match_id, visitor_key) DO UPDATE SET last_seen_at = excluded.last_seen_at
            """,
            (str(match_id), visitor_key, timestamp),
        )
        connection.execute(
            "DELETE FROM app_live_match_viewers WHERE last_seen_at < ?",
            ((now - timedelta(days=1)).isoformat().replace("+00:00", "Z"),),
        )
        row = connection.execute(
            "SELECT COUNT(*) FROM app_live_match_viewers WHERE match_id = ? AND last_seen_at >= ?",
            (str(match_id), active_since),
        ).fetchone()
    return int(row[0] or 0)

def _auth_identifier_candidates(identifier: str) -> list[str]:
    clean = str(identifier or "").strip()
    if not clean:
        return []
    candidates = []
    for candidate in (
        clean,
        canonical_phone(clean),
        re.sub(r"\D", "", clean),
    ):
        candidate = str(candidate or "").strip()
        if candidate and candidate not in candidates:
            candidates.append(candidate)
    return candidates

def _set_auth_cookies(response: Response, token: str, club_id: str = "") -> None:
    response.set_cookie("cricketClubAppAuthToken", token, httponly=False, samesite="lax", path="/")


def _clear_auth_cookies(response: Response) -> None:
    response.delete_cookie("cricketClubAppAuthToken", path="/")


def _auth_token_from_request(request: Request, x_auth_token: str | None = None) -> str:
    token = str(x_auth_token or "").strip()
    if token:
        return token
    return str(request.cookies.get("cricketClubAppAuthToken") or "").strip()


def _sqlite_copy(source_file: Path, target_file: Path) -> None:
    """Copy a SQLite database with SQLite's own backup API (README "Database export and import").

    The database runs in WAL mode: recent saves sit in the "-wal" file until a checkpoint, so copying the
    .db file alone can miss them or give an inconsistent file. The backup API copies the full, current data.
    """
    source = sqlite3.connect(str(source_file), timeout=60)
    try:
        target = sqlite3.connect(str(target_file), timeout=60)
        try:
            source.backup(target)
        finally:
            target.close()
    finally:
        source.close()


def _validated_database_backup_path() -> Path:
    timestamp = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    return DATABASE_FILE.with_name(f"{DATABASE_FILE.stem}.backup-{timestamp}{DATABASE_FILE.suffix}")


def _clubs_page_html(request: Request, search: str = "", focus_club_id: str = "") -> HTMLResponse:
    store = load_store()
    token = _auth_token_from_request(request)
    current_club_id = focus_club_id or str(store.get("viewer_profile", {}).get("primary_club_id") or "")
    dashboard = current_dashboard(store, current_club_id)
    member_club_ids: list[str] = []
    is_superadmin = False
    viewer_display_name = "Signed in"
    snapshot_title = "No player selected"
    snapshot_details = "Sign in with your player profile to see your totals here."
    year_rows_html = '<tr><td colspan="16">Loading year wise breakdown...</td></tr>'
    club_rows_html = '<tr><td colspan="16">Loading club wise breakdown...</td></tr>'

    def _format_stat(value: Any, decimals: int = 0) -> str:
        if value in ("", None):
            return "—"
        try:
            number = float(value)
        except (TypeError, ValueError):
            return html.escape(str(value))
        if decimals:
            text = f"{number:.{decimals}f}".rstrip("0").rstrip(".")
            return text or "0"
        return str(int(round(number)))

    def _player_row_from_rankings(payload: dict[str, Any], player_name: str) -> dict[str, Any] | None:
        for key in ("player_stats", "batting_rankings", "combined_player_stats"):
            rows = payload.get(key, []) or []
            row = next((item for item in rows if str(item.get("player_name") or "").strip() == player_name), None)
            if row:
                return row
        return None

    def _player_row_from_dashboard(payload: dict[str, Any], player_name: str) -> dict[str, Any]:
        row = _player_row_from_rankings(payload, player_name)
        return row or {
            "player_name": player_name,
            "matches": 0,
            "batting_innings": 0,
            "outs": 0,
            "runs": 0,
            "balls": 0,
            "batting_average": 0.0,
            "strike_rate": 0.0,
            "fours": 0,
            "sixes": 0,
            "wickets": 0,
            "catches": 0,
        }

    if token:
        try:
            user_row, current_club_id = _auth_user_from_token(token)
            is_superadmin = _effective_role_name(user_row, current_club_id) == "superadmin"
            dashboard = current_dashboard(store, current_club_id)
            viewer_display_name = str(user_row["display_name"] or user_row["email"] or user_row["mobile"] or "Signed in")
            member_id = str(user_row["member_id"] or "")
            members = dashboard.get("all_members") or dashboard.get("members") or []
            viewer_hints = {
                hint
                for hint in (
                    str(user_row["display_name"] or "").strip().lower(),
                    str(user_row["email"] or "").strip().lower(),
                    str(user_row["mobile"] or "").strip().lower(),
                )
                if hint
            }
            member = next(
                (
                    item
                    for item in members
                    if item.get("id") == member_id
                    or str(item.get("name") or "").strip().lower() in viewer_hints
                    or str(item.get("full_name") or "").strip().lower() in viewer_hints
                    or str(item.get("phone") or "").strip().lower() in viewer_hints
                    or str(item.get("email") or "").strip().lower() in viewer_hints
                    or any(str(alias or "").strip().lower() in viewer_hints for alias in item.get("aliases", []))
                ),
                None,
            )
            if member:
                member_name = str(member.get("name") or "")
                viewer_display_name = str(member.get("full_name") or member.get("name") or viewer_display_name)
                member_club_ids = [
                    str(club.get("club_id") or "").strip()
                    for club in member.get("club_memberships", [])
                    if str(club.get("club_id") or "").strip()
                ]
                member_aliases = {
                    hint
                    for hint in (
                        str(member.get("name") or "").strip().lower(),
                        str(member.get("full_name") or "").strip().lower(),
                        str(user_row["display_name"] or "").strip().lower(),
                        str(user_row["email"] or "").strip().lower(),
                        str(user_row["mobile"] or "").strip().lower(),
                        *(str(alias or "").strip().lower() for alias in member.get("aliases", [])),
                    )
                    if hint
                }
                def _performance_matches_member(performance_name: str) -> bool:
                    return str(performance_name or "").strip().lower() in member_aliases

                def _row_matches_member(row: dict[str, Any]) -> bool:
                    return (
                        str(row.get("player_name") or "").strip().lower() in member_aliases
                        or str(row.get("full_name") or "").strip().lower() in member_aliases
                    )

                def _highest_score_for(year: str | None = None, club_id: str | None = None) -> int | None:
                    highest: int | None = None
                    for fixture in store.get("fixtures", []):
                        if year and str(fixture.get("season_year") or "").strip() != str(year).strip():
                            continue
                        if club_id and str(fixture.get("club_id") or "").strip() != str(club_id).strip():
                            continue
                        for performance in fixture.get("performances", []) or []:
                            if not _performance_matches_member(performance.get("player_name") or ""):
                                continue
                            runs = int(performance.get("runs") or 0)
                            highest = runs if highest is None else max(highest, runs)
                    for archive in canonical_archive_uploads(store.get("archive_uploads", [])):
                        if year and str(archive.get("archive_year") or "").strip() != str(year).strip():
                            continue
                        if club_id and str(archive.get("club_id") or "").strip() != str(club_id).strip():
                            continue
                        performances = [item for item in archive.get("suggested_performances", []) or [] if isinstance(item, dict)]
                        if not performances:
                            try:
                                template = json.loads(str(archive.get("review_template_json") or "{}"))
                            except Exception:
                                template = {}
                            for inning in template.get("innings", []) or []:
                                for batting in inning.get("batting", []) or []:
                                    performances.append(
                                        {
                                            "player_name": (batting.get("player") or {}).get("name") or batting.get("player_name") or "",
                                            "runs": batting.get("runs") or 0,
                                        }
                                    )
                        for performance in performances:
                            if not _performance_matches_member(performance.get("player_name") or ""):
                                continue
                            runs = int(performance.get("runs") or 0)
                            highest = runs if highest is None else max(highest, runs)
                    return highest

                snapshot_stats = next(
                    (item for item in dashboard.get("member_summary_stats", []) if _row_matches_member(item)),
                    None,
                ) or next(
                    (item for item in dashboard.get("all_combined_player_stats", []) if _row_matches_member(item)),
                    {"runs": 0, "wickets": 0, "catches": 0},
                )
                all_fixtures = dashboard.get("all_fixtures", []) or []
                appearances = [
                    fixture
                    for fixture in all_fixtures
                    if any(_performance_matches_member(performance.get("player_name") or "") for performance in fixture.get("performances", []))
                ]
                appearances.sort(key=lambda item: str(item.get("date") or ""), reverse=True)
                last_game = appearances[0] if appearances else None
                upcoming_games = [
                    fixture
                    for fixture in all_fixtures
                    if str(fixture.get("status") or "").lower() == "scheduled"
                    and any(_performance_matches_member(performance.get("player_name") or "") for performance in fixture.get("performances", []))
                ]
                upcoming_games.sort(key=lambda item: str(item.get("date") or ""))
                next_game = upcoming_games[0] if upcoming_games else None
                snapshot_title = str(member.get("full_name") or member_name or "Player")
                games_played = max(int(snapshot_stats.get("matches") or 0), len(appearances))
                snapshot_bits = [
                    f'{int(snapshot_stats.get("runs") or 0)} runs',
                    f'HS: {int(snapshot_stats.get("highest_score") or 0) if snapshot_stats.get("highest_score") is not None else "—"}',
                    f'Avg: {_format_stat(snapshot_stats.get("batting_average"), 2)}',
                    f'SR: {_format_stat(snapshot_stats.get("strike_rate"), 2)}',
                    f'25s: {int(snapshot_stats.get("scores_25_plus") or 0)}',
                    f'50s: {int(snapshot_stats.get("scores_50_plus") or 0)}',
                    f'100s: {int(snapshot_stats.get("scores_100_plus") or 0)}',
                    f'{int(snapshot_stats.get("wickets") or 0)} wickets',
                    f'{int(snapshot_stats.get("catches") or 0)} catches',
                    f"{games_played} games",
                ]
                if last_game:
                    snapshot_bits.append(f'Last: {last_game.get("date_label") or "Game"} vs {last_game.get("opponent") or "TBD"}')
                if next_game:
                    snapshot_bits.append(f'Next: {next_game.get("date_label") or "Game"} vs {next_game.get("opponent") or "TBD"}')
                snapshot_details = " · ".join(snapshot_bits)

                year_rows: list[str] = []
                year_summary_rows = dashboard.get("member_year_stats", []) or []
                for year in dashboard.get("ranking_years", []) or []:
                    year_row = next(
                        (
                            item
                            for item in year_summary_rows
                            if str(item.get("season_year") or "").strip() == str(year)
                            and _row_matches_member(item)
                        ),
                        {},
                    )
                    year_no = max(0, int(year_row.get("batting_innings", 0) or 0) - int(year_row.get("outs", 0) or 0))
                    year_hs = _highest_score_for(str(year))
                    year_rows.append(
                        "<tr>"
                        f"<td>{html.escape(str(year))}</td>"
                        f"<td>{_format_stat(year_row.get('matches'))}</td>"
                        f"<td>{_format_stat(year_row.get('batting_innings'))}</td>"
                        f"<td>{_format_stat(year_no)}</td>"
                        f"<td>{_format_stat(year_row.get('runs'))}</td>"
                        f"<td>{html.escape(str(year_hs) if year_hs is not None else '—')}</td>"
                        f"<td>{_format_stat(year_row.get('batting_average'), 2)}</td>"
                        f"<td>{_format_stat(year_row.get('balls'))}</td>"
                        f"<td>{_format_stat(year_row.get('strike_rate'), 2)}</td>"
                        f"<td>{_format_stat(year_row.get('scores_25_plus'))}</td>"
                        f"<td>{_format_stat(year_row.get('scores_50_plus') or year_row.get('fifties') or year_row.get('fiftys'))}</td>"
                        f"<td>{_format_stat(year_row.get('scores_100_plus') or year_row.get('centuries') or year_row.get('hundreds'))}</td>"
                        f"<td>{_format_stat(year_row.get('fours'))}</td>"
                        f"<td>{_format_stat(year_row.get('sixes'))}</td>"
                        f"<td>{_format_stat(year_row.get('catches'))}</td>"
                        f"<td>{_format_stat(year_row.get('stumpings'))}</td>"
                        "</tr>"
                    )
                if year_rows:
                    year_rows_html = "".join(year_rows)

                club_rows: list[str] = []
                club_summary_rows = dashboard.get("member_club_stats", []) or []
                for club in member.get("club_memberships", []):
                    club_id = str(club.get("club_id") or "").strip()
                    club_name = str(club.get("club_name") or club_id or "").strip()
                    if not club_id:
                        continue
                    club_row = next(
                        (
                            item
                            for item in club_summary_rows
                            if str(item.get("club_id") or "").strip() == club_id
                            and (
                                str(item.get("player_name") or "").strip() == member_name
                                or str(item.get("player_name") or "").strip().lower() == member_name.lower()
                            )
                        ),
                        {},
                    )
                    club_rows.append(
                        "<tr>"
                        f"<td>{html.escape(club_name)}</td>"
                        f"<td>{_format_stat(club_row.get('matches'))}</td>"
                        f"<td>{_format_stat(club_row.get('batting_innings'))}</td>"
                        f"<td>{_format_stat(max(0, int(club_row.get('batting_innings', 0) or 0) - int(club_row.get('outs', 0) or 0)))}</td>"
                        f"<td>{_format_stat(club_row.get('runs'))}</td>"
                        f"<td>{html.escape(str(club_row.get('highest_score')) if club_row.get('highest_score') is not None else '—')}</td>"
                        f"<td>{_format_stat(club_row.get('batting_average'), 2)}</td>"
                        f"<td>{_format_stat(club_row.get('balls'))}</td>"
                        f"<td>{_format_stat(club_row.get('strike_rate'), 2)}</td>"
                        f"<td>{_format_stat(club_row.get('scores_25_plus'))}</td>"
                        f"<td>{_format_stat(club_row.get('scores_50_plus'))}</td>"
                        f"<td>{_format_stat(club_row.get('scores_100_plus'))}</td>"
                        f"<td>{_format_stat(club_row.get('fours'))}</td>"
                        f"<td>{_format_stat(club_row.get('sixes'))}</td>"
                        f"<td>{_format_stat(club_row.get('catches'))}</td>"
                        f"<td>—</td>"
                        "</tr>"
                    )
                if club_rows:
                    club_rows_html = "".join(club_rows)
        except HTTPException:
            member_club_ids = []
    clubs = _sorted_club_choices(store, current_club_id)
    # Nov 4 2026 (Amit): everyone (the superadmin too) sees all the clubs they belong to / played for; a search
    # looks through every club (it used to show the superadmin only the current club, and search found nothing).
    query = search.strip().lower()
    linked_only = [club for club in clubs if str(club.get("id") or "").strip() in set(member_club_ids)]
    if not linked_only:
        linked_only = [club for club in clubs if str(club.get("id") or "").strip() == str(current_club_id or "").strip()]
    if not linked_only:
        linked_only = clubs[:1]
    current_club = next((club for club in clubs if str(club.get("id") or "").strip() == str(current_club_id or "").strip()), None)
    default_clubs = []
    if current_club:
        default_clubs.append(current_club)
    default_clubs.extend(
        club
        for club in linked_only
        if str(club.get("id") or "").strip() != str(current_club_id or "").strip()
    )
    if not default_clubs:
        default_clubs = clubs[:1]
    source_clubs = clubs if query else default_clubs
    filtered = [
        club
        for club in source_clubs
        if not query
        or query in str(club.get("name", "")).lower()
        or query in str(club.get("short_name", "")).lower()
        or query in str(club.get("city", "")).lower()
        or query in str(club.get("country", "")).lower()
        or query in str(club.get("season", "")).lower()
    ]
    summary = (
        f"{len(filtered)} club{'s' if len(filtered) != 1 else ''} match your search."
        if query
        else f"{len(filtered)} linked club{'s' if len(filtered) != 1 else ''} available."
    )
    cards = "".join(
        f"""
        <article class="detail-card {'active-card' if club.get('id') == focus_club_id else ''}">
          <strong>{html.escape(str(club.get('name', '') or ''))}</strong>
          <p>{html.escape(str(club.get('season', '') or 'Season TBD'))}</p>
          <small>{html.escape(" · ".join(part for part in [str(club.get('short_name', '') or ''), str(club.get('city', '') or ''), str(club.get('country', '') or '')] if part))}</small>
          <div class="inline-actions">
            <form method="post" action="/clubs/select">
              <input type="hidden" name="club_id" value="{html.escape(str(club.get('id', '') or ''))}" />
              <input type="hidden" name="search" value="{html.escape(search or '')}" />
              <button class="secondary-button" type="submit">Select club</button>
            </form>
          </div>
        </article>
        """
        for club in filtered
    ) or '<p class="empty-state">No clubs match that search.</p>'
    search_value = html.escape(search or "")
    badge_html = ""
    club_badge_html = ""
    if token:
        try:
            user_row, _ = _auth_user_from_token(token)
            user_payload = _auth_user_payload(user_row, current_club_id)
            club_badge_html = _club_badge_html(
                str(user_payload.get("current_club_name") or user_payload.get("primary_club_name") or "Selected club")
            )
            badge_html = _identity_badge_html(
                str(user_payload.get("display_name") or user_payload.get("email") or user_payload.get("mobile") or "Signed in"),
                str(user_payload.get("effective_role") or user_payload.get("role") or "Player"),
            )
        except Exception:
            badge_html = ""
    topbar = '<header class="page-topbar"></header>'
    body = f"""
    <!DOCTYPE html>
    <html lang="en">
      <head>
        <meta charset="UTF-8" />
        <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, viewport-fit=cover" />
        <script src="/assets/zoom_lock.js?v=20261014a"></script>
        <title>Select Club · CricketClubApp</title>
        <link rel="stylesheet" href="/assets/styles.css?v=20261016g" />
        <link rel="stylesheet" href="/assets/app_polish.css?v=20261006a" />
        <link rel="stylesheet" href="/assets/sports-system.css?v=20260926a" />
      </head>
      <body>
        <div class="page-shell">
          {topbar}
          <section class="panel onboarding-panel">
            <div class="stack-card">
              <p class="section-kicker">Club Selection</p>
              <h1 id="clubsGreeting">Welcome, {html.escape(viewer_display_name)}</h1>
              <p id="selectedClubSummary" class="lede">{"Your current club is shown here. Use Admin Center to manage other clubs." if is_superadmin else "Choose your current club. Your primary club is the default."}</p>
              <div id="clubsStatus" class="status-banner" hidden></div>
              <form class="toolbar-actions" method="get" action="/clubs">
                <input id="clubSearchInput" name="search" type="search" value="{search_value}" placeholder="Search clubs by name, short name, or season" />
                <button id="clubSearchButton" class="primary-button" type="submit">Search clubs</button>
                <div id="clubsSearchSummary" class="archive-search-summary">{html.escape(summary)}</div>
              </form>
              <h2 class="section-heading">Available clubs</h2>
              <div id="clubsList" class="detail-stack" data-server-rendered="true">{cards}</div>
              <div class="mini-stat">
                <span>Player Snapshot</span>
                <strong id="clubsPlayerSnapshotTitle">{html.escape(snapshot_title)}</strong>
                <small id="clubsPlayerSnapshotDetails">{html.escape(snapshot_details)}</small>
              </div>
              <div class="detail-card snapshot-breakdown">
                <strong class="snapshot-breakdown-title">Year wise</strong>
                <div class="review-table-wrap">
                  <table class="review-table snapshot-table">
                    <thead>
                      <tr>
                        <th>Year</th>
                        <th>Mat</th>
                        <th>Inns</th>
                        <th>NO</th>
                        <th>Runs</th>
                        <th>HS</th>
                        <th>Ave</th>
                        <th>BF</th>
                        <th>SR</th>
                        <th>25+</th>
                        <th>50+</th>
                        <th>100+</th>
                        <th>4s</th>
                        <th>6s</th>
                        <th>Ct</th>
                        <th>St</th>
                      </tr>
                    </thead>
                    <tbody id="clubsPlayerYearRows">{year_rows_html}</tbody>
                  </table>
                </div>
                <strong class="snapshot-breakdown-title">Club wise</strong>
                <div class="review-table-wrap">
                  <table class="review-table snapshot-table">
                    <thead>
                      <tr>
                        <th>Club</th>
                        <th>Mat</th>
                        <th>Inns</th>
                        <th>NO</th>
                        <th>Runs</th>
                        <th>HS</th>
                        <th>Ave</th>
                        <th>BF</th>
                        <th>SR</th>
                        <th>25+</th>
                        <th>50+</th>
                        <th>100+</th>
                        <th>4s</th>
                        <th>6s</th>
                        <th>Ct</th>
                        <th>St</th>
                      </tr>
                    </thead>
                    <tbody id="clubsPlayerClubRows">{club_rows_html}</tbody>
                  </table>
                </div>
              </div>
              <div class="inline-actions">
                <a id="seasonSetupLink" class="primary-link" href="/season-setup">Season Fixtures</a>
                <a id="playerAvailabilityLink" class="primary-link" href="/player-availability">Player availability</a>
                <a id="playerProfileLink" class="primary-link" href="/profile">Player profile</a>
              </div>
            </div>
          </section>
        </div>
        <script src="/assets/multipage.js?v=20261025a"></script>
        <script src="/assets/clubs.js?v=20261104c"></script>
      </body>
    </html>
    """
    return HTMLResponse(
        body,
        headers={
            "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
            "Pragma": "no-cache",
        },
    )


class MemberCreateRequest(BaseModel):
    name: str
    full_name: str = ""
    gender: str = ""
    team_name: str = "Club"
    club_id: str = ""
    team_memberships: list[str] | str = []
    aliases: list[str] | str = []
    age: int
    role: str
    batting_style: str = ""
    bowling_style: str = ""
    notes: str = ""
    picture_url: str = ""
    phone: str = ""
    email: str = ""
    jersey_number: str = ""


class MemberUpdateRequest(BaseModel):
    name: str | None = None
    full_name: str | None = None
    gender: str | None = None
    team_name: str | None = None
    team_memberships: list[str] | str | None = None
    aliases: list[str] | str | None = None
    age: int | None = None
    role: str | None = None
    batting_style: str | None = None
    bowling_style: str | None = None
    notes: str | None = None
    picture_url: str | None = None
    phone: str | None = None
    email: str | None = None
    jersey_number: str | None = None


class MatchDetailsRequest(BaseModel):
    heartlake_captain: str | None = None
    venue: str | None = None
    match_type: str | None = None
    scheduled_time: str | None = None
    overs: str | None = None
    toss_winner: str | None = None
    toss_decision: str | None = None
    weather: str | None = None
    umpires: str | None = None
    scorer: str | None = None
    whatsapp_thread: str | None = None
    notes: str | None = None
    status: str | None = None


class AvailabilityUpdateRequest(BaseModel):
    player_name: str
    status: str
    note: str = ""
    club_id: str = ""


class PlayingXiUpdateRequest(BaseModel):
    player_names: list[str] = []
    club_id: str = ""


class ScorecardUpdateRequest(BaseModel):
    heartlake_runs: str | None = None
    heartlake_wickets: str | None = None
    heartlake_overs: str | None = None
    opponent_runs: str | None = None
    opponent_wickets: str | None = None
    opponent_overs: str | None = None
    result: str | None = None
    live_summary: str | None = None
    status: str | None = None


class PerformanceCreateRequest(BaseModel):
    player_name: str
    runs: int = 0
    balls: int = 0
    wickets: int = 0
    catches: int = 0
    fours: int = 0
    sixes: int = 0
    notes: str = ""
    source: str = "manual"


class CommentaryRequest(BaseModel):
    mode: str
    text: str


class ScorebookSetupRequest(BaseModel):
    innings_number: int
    batting_team: str = ""
    bowling_team: str = ""
    overs_limit: int = 20
    target_runs: int | None = None
    status: str = "Not started"
    batters: list[str] = []
    bowlers: list[str] = []


class ScorebookBallRequest(BaseModel):
    innings_number: int
    over_number: int
    ball_number: int
    striker: str
    non_striker: str = ""
    bowler: str
    runs_bat: int = 0
    extras_type: str = "none"
    extras_runs: int = 0
    wicket: bool = False
    wicket_type: str = ""
    wicket_player: str = ""
    fielder: str = ""
    commentary: str = ""
    # Set when fixing a ball already scored (tap the ball on /score): that ball is replaced in place.
    id: str = ""
    # The Score page's own id for a new ball: a retry after a lost connection never saves it twice.
    client_id: str = ""
    # On a wicket: the batter coming in (so a new name typed on the day joins the line-up before "all out" is decided).
    new_batter: str = ""


def _grow_lineups_with_new_players(match_id: str, match: dict[str, Any], innings: dict[str, Any], ball: dict[str, Any], lineups: dict[str, Any], new_batter: str = "") -> dict[str, Any]:
    """A batter or bowler typed in on the day ("Someone else?") joins their team's line-up (up to 11), so the next
    pick lists show them and "all out" counts them (Afghan Eagles match, Oct 31 2026: "Ab" batted but wasn't in the
    line-up, and the innings could end at 7 wickets with batters still to come)."""
    if not lineups or not (lineups.get("club") or lineups.get("opponent")):
        return lineups
    club = str(match.get("club_name") or "").strip().lower()
    bat_side = "club" if str(innings.get("batting_team") or "").strip().lower() == club else "opponent"
    bowl_side = "opponent" if bat_side == "club" else "club"
    changed = False
    for side, names in ((bat_side, [ball.get("striker"), ball.get("non_striker"), new_batter]), (bowl_side, [ball.get("bowler")])):
        current = list(lineups.get(side) or [])
        known = {str(n).strip().lower() for n in current}
        for name in names:
            name = " ".join(str(name or "").split())
            if name and name.lower() not in known and len(current) < LINEUP_MAX:
                current.append(name)
                known.add(name.lower())
                changed = True
        lineups[side] = current
    if changed:
        try:
            load_store()
            with _auth_connection() as connection:
                _ensure_extra_match_tables(connection)
                connection.execute(
                    "UPDATE app_match_lineups SET lineups_json = ?, updated_at = ? WHERE match_id = ?",
                    (json.dumps({"club": lineups.get("club") or [], "opponent": lineups.get("opponent") or [], "roles": lineups.get("roles") or {}}), now_iso(), match_id),
                )
        except Exception:
            logger.exception("Couldn't add new players to the line-ups of %s", match_id)
    return lineups


def _settle_scorebook_result(match: dict[str, Any], lineups: dict[str, list[str]]) -> None:
    """After a ball / fix / undo (club and guest matches): end the chase once the target is passed and write the
    result with the real team size ("Afghans won by 3 wickets"), or clear it if the match isn't over (README
    "How a scored match ends")."""
    ordered = sorted(_match_scorebook(match).get("innings", []), key=lambda row: int(row.get("inning_number") or 1))
    if len(ordered) < 2:
        return
    first, second = ordered[0], ordered[1]
    first_summary, second_summary = summarize_innings_scorebook(first), summarize_innings_scorebook(second)
    if (second.get("balls") or []) and int(second_summary["runs"]) > int(first_summary["runs"]):
        second["status"] = "Completed"
    scorecard = match.setdefault("scorecard", {})
    if scorebook_match_finished(ordered):
        text = scorebook_result_text(first, second, first_summary, second_summary, _all_out_at(match, second, lineups))
    else:
        text = "TBD"
    scorecard["result"] = text
    match["result"] = text


def _innings_is_over(match: dict[str, Any], innings: dict[str, Any], lineups: dict[str, list[str]]) -> bool:
    """No new balls once an innings is finished: all out, overs used up, or (2nd innings) target passed.
    Oct 29 2026: fast taps after the last wicket were saved, giving "28/11" (README "Full test and fixes")."""
    summary = summarize_innings_scorebook(innings)
    if scorebook_wickets_for_all_out(innings) >= _all_out_at(match, innings, lineups):
        return True
    if summary["legal_balls"] >= int(innings.get("overs_limit", 20) or 20) * 6:
        return True
    if int(innings.get("inning_number") or 1) == 2:
        first = next((row for row in _match_scorebook(match).get("innings", []) if int(row.get("inning_number") or 1) == 1), None)
        if first and (first.get("balls") or []) and summary["runs"] > summarize_innings_scorebook(first)["runs"]:
            return True
    return False


def _client_ball_seen(innings: dict[str, Any], ball: dict[str, Any], request: "ScorebookBallRequest") -> bool:
    """New balls from the Score page carry a client_id (README "Balls are never lost"). It becomes the ball's id;
    if a ball with that id is already saved, this is a retry of a ball that did save, so nothing is added."""
    client_id = re.sub(r"[^A-Za-z0-9_-]", "", str(request.client_id or ""))[:40]
    if not client_id or str(request.id or "").strip():
        return False
    if any(str(item.get("id") or "") == client_id for item in innings.get("balls", []) or []):
        return True
    ball["id"] = client_id
    return False


# ---------------------------------------------------------------------------
# One scoring change at a time (README "Scoring changes one at a time", Oct 31 2026). Every scoring write loads the
# whole match, changes it and saves it. Two at once (Undo still saving while the next ball arrives, or two phones
# scoring) each saved their own copy and one change was lost: an undone 6 came back. This lock makes them wait for
# each other - across threads with a threading lock and across worker processes (Azure) with an SQLite write lock
# on a small side file (released by itself if a worker stops).
# ---------------------------------------------------------------------------
import functools as _functools

_SCORING_THREAD_LOCK = threading.RLock()
_SCORING_DEPTH = threading.local()  # a locked endpoint calling another one (setup -> lineups) doesn't lock twice


def _scoring_locked(func):
    @_functools.wraps(func)
    def wrapper(*args, **kwargs):
        with _SCORING_THREAD_LOCK:
            depth = getattr(_SCORING_DEPTH, "value", 0)
            connection = None
            if depth == 0:
                lock_file = DATABASE_FILE.with_name(f"{DATABASE_FILE.name}.scorelock")
                try:
                    lock_file.parent.mkdir(parents=True, exist_ok=True)
                    connection = sqlite3.connect(lock_file, timeout=30, isolation_level=None)
                    connection.execute("BEGIN IMMEDIATE")
                except sqlite3.Error:
                    logger.warning("Scoring lock not available; saving without it.", exc_info=True)
                    if connection is not None:
                        connection.close()
                        connection = None
            _SCORING_DEPTH.value = depth + 1
            try:
                return func(*args, **kwargs)
            finally:
                _SCORING_DEPTH.value = depth
                if connection is not None:
                    try:
                        connection.execute("COMMIT")
                    except sqlite3.Error:
                        pass
                    connection.close()

    return wrapper


def _apply_ball_edit(innings: dict[str, Any], ball: dict[str, Any], ball_id: str) -> bool:
    """Fixing a scored ball (README "Easier live scoring"): keep its id, place and time. Returns True when editing."""
    ball_id = str(ball_id or "").strip()
    if not ball_id:
        return False
    existing = next((item for item in innings.get("balls", []) or [] if str(item.get("id") or "") == ball_id), None)
    if existing is None:
        raise HTTPException(status_code=404, detail="That ball isn't in this innings any more. Refresh the page.")
    ball["id"] = ball_id
    ball["over_number"] = int(existing.get("over_number") or ball.get("over_number") or 1)
    ball["ball_number"] = int(existing.get("ball_number") or ball.get("ball_number") or 1)
    ball["created_at"] = str(existing.get("created_at") or ball.get("created_at") or "")
    return True


def _validate_retired_out_ball(ball: dict[str, Any]) -> None:
    wicket_type = str(ball.get("wicket_type") or "").strip().lower()
    extras_type = str(ball.get("extras_type") or "none").strip().lower()
    new_batter = str(ball.get("new_batter") or "").strip()
    wicket_player = str(ball.get("wicket_player") or "").strip()
    if new_batter and not ball.get("wicket") and wicket_type != "retired_out":
        raise HTTPException(status_code=400, detail="A replacement batter can only be selected for a wicket or retired-out event.")
    if new_batter and new_batter.casefold() == wicket_player.casefold():
        raise HTTPException(status_code=400, detail="The retired batter cannot be selected as their own replacement.")
    if wicket_type == "retired_out":
        if (
            not ball.get("wicket_player")
            or int(ball.get("runs_bat") or 0)
            or int(ball.get("extras_runs") or 0)
        ):
            raise HTTPException(status_code=400, detail="Retired out must identify a temporarily retired batter, with no runs or ball faced.")
        ball["wicket"] = False
        ball["extras_type"] = "retired_out"
        ball["bowler"] = ""
    elif extras_type == "retired_out":
        raise HTTPException(status_code=400, detail="Retired out must be recorded as a temporary batter retirement.")


def _reindex_scorebook_innings(innings: dict[str, Any]) -> None:
    balls = sorted(
        innings.get("balls", []) or [],
        key=lambda ball: (
            int(ball.get("over_number") or 1),
            int(ball.get("ball_number") or 1),
            str(ball.get("created_at") or ""),
        ),
    )
    legal_count = 0
    for ball in balls:
        ball["over_number"] = legal_count // 6 + 1
        ball["ball_number"] = legal_count % 6 + 1
        if str(ball.get("extras_type") or "none") not in {"wide", "no_ball", "retired_out"}:
            legal_count += 1
    innings["balls"] = balls


class ChatRequest(BaseModel):
    question: str
    session_id: str | None = None
    history: list[dict[str, Any]] = Field(default_factory=list)
    focus_club_id: str | None = None


class LLMInferRequest(BaseModel):
    question: str
    session_id: str | None = None
    history: list[dict[str, Any]] = Field(default_factory=list)
    focus_club_id: str | None = None
    mode: str = "auto"
    prompt_name: str = ""
    template_args: dict[str, Any] = Field(default_factory=dict)
    limit: int = 8


class ArchiveApplyRequest(BaseModel):
    match_id: str
    heartlake_runs: str = ""
    heartlake_wickets: str = ""
    heartlake_overs: str = ""
    opponent_runs: str = ""
    opponent_wickets: str = ""
    opponent_overs: str = ""
    result: str = ""
    source_note: str = ""


class ArchiveImportRequest(BaseModel):
    text: str


class ArchiveReviewRequest(BaseModel):
    text: str


def _apply_archive_review_text(
    store: dict[str, Any],
    upload: dict[str, Any],
    raw_text: str,
    *,
    user_row: dict[str, Any] | None = None,
) -> None:
    review_text = str(raw_text or "").strip()
    if not review_text:
        raise HTTPException(status_code=400, detail="Paste the reviewed scorecard JSON first.")

    try:
        payload = json.loads(review_text)
    except json.JSONDecodeError:
        payload = None

    if isinstance(payload, dict):
        template_payload = _canonical_scorecard_template_payload(payload)
        if template_payload is not None:
            logger.debug(
                "Archive review enrichment started. file_name=%s club_id=%s",
                upload.get("file_name") or "",
                upload.get("club_id") or "",
            )
            draft, suggested, extracted_summary = _scorecard_template_review_data(store, template_payload)
            template_payload = _enrich_scorecard_template_payload(template_payload, draft=draft, archive=upload)
            upload["extraction_template"] = template_payload
            upload["review_source_json"] = review_text[:12000]
            upload["draft_scorecard"] = draft
            upload["suggested_performances"] = suggested
            upload["raw_extracted_text"] = review_text[:12000]
            meta = template_payload.get("meta") if isinstance(template_payload.get("meta"), dict) else {}
            upload["ocr_engine"] = str(meta.get("source") or upload.get("ocr_engine") or "manual-review")
            upload["ocr_pipeline"] = str(meta.get("processed_by") or upload.get("ocr_pipeline") or "Admin reviewed extraction")
            upload["confidence"] = str(meta.get("confidence") or upload.get("confidence") or "review")
            upload["extracted_summary"] = str(
                _extract_field(template_payload, "extracted_summary")
                or extracted_summary
                or upload.get("extracted_summary")
                or "Reviewed archive scorecard."
            )
            reviewed_template, llm_notes, llm_model, llm_assessment = review_scorecard_template_with_llm(
                template_payload,
                review_text,
                archive=upload,
                store=store,
            )
            logger.debug(
                "Archive review enrichment finished. file_name=%s model=%s used_llm=%s",
                upload.get("file_name") or "",
                llm_model or "",
                bool(llm_notes or llm_model),
            )
            if isinstance(reviewed_template, dict):
                upload["extraction_template"] = reviewed_template
                upload["review_template_json"] = json.dumps(reviewed_template, indent=2)
            else:
                upload["review_template_json"] = json.dumps(template_payload, indent=2)
            upload["review_llm_model"] = llm_model or upload.get("review_llm_model") or ""
            upload["review_llm_notes"] = llm_notes[:12000] if llm_notes else upload.get("review_llm_notes") or "LLM review completed."
            upload["review_llm_assessment"] = llm_assessment or upload.get("review_llm_assessment") or {}
            return
        if "draft_scorecard" in payload:
            draft = payload.get("draft_scorecard")
            if isinstance(draft, dict):
                upload["draft_scorecard"] = draft
            if isinstance(payload.get("suggested_performances"), list):
                upload["suggested_performances"] = [
                    item for item in payload.get("suggested_performances", []) if isinstance(item, dict)
                ]
            template = payload.get("extraction_template")
            if isinstance(template, dict) and _is_scorecard_template_payload(template):
                upload["extraction_template"] = deepcopy(template)
                upload["review_source_json"] = review_text[:12000]
        elif "match" in payload or "innings" in payload:
            parsed = parse_imported_extraction(store, review_text)
            upload.update(parsed)
            upload["review_source_json"] = review_text[:12000]
        else:
            draft = default_scorecard(_extract_field(payload, "result") or upload.get("extracted_summary") or "Reviewed archive")
            draft.update(
                {
                    "heartlake_runs": _extract_field(payload, "heartlake_runs", "summary"),
                    "heartlake_wickets": _extract_field(payload, "heartlake_wickets", "summary"),
                    "heartlake_overs": _extract_field(payload, "heartlake_overs", "summary"),
                    "opponent_runs": _extract_field(payload, "opponent_runs", "summary"),
                    "opponent_wickets": _extract_field(payload, "opponent_wickets", "summary"),
                    "opponent_overs": _extract_field(payload, "opponent_overs", "summary"),
                    "result": _extract_field(payload, "result") or "Reviewed archive",
                    "live_summary": _extract_field(payload, "live_summary", "summary"),
                }
            )
            upload["draft_scorecard"] = draft
            upload["suggested_performances"] = _parse_imported_player_scores(store, payload)
            upload["extraction_template"] = _scorecard_template_from_review_payload(
                store,
                payload,
                draft,
                upload["suggested_performances"],
                review_text,
                ocr_engine=str(_extract_field(payload, "ocr_engine") or upload.get("ocr_engine") or "manual-review"),
                ocr_pipeline=str(_extract_field(payload, "ocr_pipeline") or upload.get("ocr_pipeline") or "Admin reviewed extraction"),
                confidence=str(_extract_field(payload, "confidence") or upload.get("confidence") or "review"),
                extracted_summary=str(_extract_field(payload, "extracted_summary") or upload.get("extracted_summary") or "Reviewed archive scorecard."),
            )
            upload["review_source_json"] = review_text[:12000]

        upload["raw_extracted_text"] = str(_extract_field(payload, "raw_extracted_text") or review_text)[:12000]
        meta = payload.get("meta") if isinstance(payload.get("meta"), dict) else {}
        upload["ocr_engine"] = str(
            _extract_field(payload, "ocr_engine")
            or meta.get("source")
            or upload.get("ocr_engine")
            or "manual-review"
        )
        upload["ocr_pipeline"] = str(_extract_field(payload, "ocr_pipeline") or upload.get("ocr_pipeline") or "Admin reviewed extraction")
        upload["confidence"] = str(_extract_field(payload, "confidence") or meta.get("confidence") or upload.get("confidence") or "review")
        summary = _extract_field(payload, "extracted_summary") or upload.get("extracted_summary") or "Reviewed archive scorecard."
        upload["extracted_summary"] = str(summary)
        if "extraction_template" not in upload:
            upload["extraction_template"] = _scorecard_template_from_review_payload(
                store,
                payload,
                upload.get("draft_scorecard") or default_scorecard("Reviewed archive"),
                upload.get("suggested_performances") or [],
                review_text,
                ocr_engine=upload["ocr_engine"],
                ocr_pipeline=upload["ocr_pipeline"],
                confidence=upload["confidence"],
                extracted_summary=upload["extracted_summary"],
            )
        reviewed_template, llm_notes, llm_model, llm_assessment = review_scorecard_template_with_llm(
            upload.get("extraction_template") or {},
            review_text,
            archive=upload,
            store=store,
        )
        logger.debug(
            "Archive review enrichment finished. file_name=%s model=%s used_llm=%s",
            upload.get("file_name") or "",
            llm_model or "",
            bool(llm_notes or llm_model),
        )
        if isinstance(reviewed_template, dict):
            upload["extraction_template"] = reviewed_template
            upload["review_template_json"] = json.dumps(reviewed_template, indent=2)
        else:
            upload["review_template_json"] = json.dumps(upload.get("extraction_template") or {}, indent=2)
        upload["review_llm_model"] = llm_model or upload.get("review_llm_model") or ""
        upload["review_llm_notes"] = llm_notes[:12000] if llm_notes else upload.get("review_llm_notes") or "LLM review completed."
        upload["review_llm_assessment"] = llm_assessment or upload.get("review_llm_assessment") or {}
    else:
        upload["raw_extracted_text"] = review_text[:12000]
        upload["review_source_json"] = review_text[:12000]
        upload["ocr_engine"] = upload.get("ocr_engine") or "manual-review"
        upload["ocr_pipeline"] = upload.get("ocr_pipeline") or "Admin reviewed extraction"
        upload["confidence"] = upload.get("confidence") or "review"
        upload["extraction_template"] = _scorecard_template_from_review_payload(
            store,
            {},
            upload.get("draft_scorecard") or default_scorecard("Reviewed archive"),
            upload.get("suggested_performances") or [],
            review_text,
            ocr_engine=upload["ocr_engine"],
            ocr_pipeline=upload["ocr_pipeline"],
            confidence=upload["confidence"],
            extracted_summary=upload.get("extracted_summary") or "Reviewed archive scorecard.",
        )
        reviewed_template, llm_notes, llm_model, llm_assessment = review_scorecard_template_with_llm(
            upload.get("extraction_template") or {},
            review_text,
            archive=upload,
            store=store,
        )
        logger.debug(
            "Archive review enrichment finished. file_name=%s model=%s used_llm=%s",
            upload.get("file_name") or "",
            llm_model or "",
            bool(llm_notes or llm_model),
        )
        if isinstance(reviewed_template, dict):
            upload["extraction_template"] = reviewed_template
            upload["review_template_json"] = json.dumps(reviewed_template, indent=2)
        else:
            upload["review_template_json"] = json.dumps(upload.get("extraction_template") or {}, indent=2)
        upload["review_llm_model"] = llm_model or upload.get("review_llm_model") or ""
        upload["review_llm_notes"] = llm_notes[:12000] if llm_notes else upload.get("review_llm_notes") or "LLM review completed."
        upload["review_llm_assessment"] = llm_assessment or upload.get("review_llm_assessment") or {}


def _archive_scorecard_update_from_review(upload: dict[str, Any], request: ArchiveReviewRequest | None = None) -> dict[str, str]:
    draft = upload.get("draft_scorecard") if isinstance(upload.get("draft_scorecard"), dict) else {}

    def pick(*values: Any) -> str:
        for value in values:
            text = str(value or "").strip()
            if text:
                return text
        return ""

    return {
        "heartlake_runs": pick(getattr(request, "heartlake_runs", None), draft.get("heartlake_runs"), draft.get("total_runs")),
        "heartlake_wickets": pick(getattr(request, "heartlake_wickets", None), draft.get("heartlake_wickets"), draft.get("wickets")),
        "heartlake_overs": pick(getattr(request, "heartlake_overs", None), draft.get("heartlake_overs"), draft.get("overs")),
        "opponent_runs": pick(getattr(request, "opponent_runs", None), draft.get("opponent_runs")),
        "opponent_wickets": pick(getattr(request, "opponent_wickets", None), draft.get("opponent_wickets")),
        "opponent_overs": pick(getattr(request, "opponent_overs", None), draft.get("opponent_overs")),
        "result": pick(getattr(request, "result", None), draft.get("result"), upload.get("result"), upload.get("extracted_summary"), "Reviewed archive"),
        "live_summary": pick(getattr(request, "live_summary", None), draft.get("live_summary"), upload.get("live_summary"), upload.get("extracted_summary")),
    }

    inferred_club = _resolve_archive_club(upload, store.get("clubs", []))
    if inferred_club:
        upload["club_id"] = inferred_club.get("id", upload.get("club_id", ""))
        upload["club_name"] = inferred_club.get("name", upload.get("club_name", ""))
    upload["status"] = "Pending review"
    if user_row:
        upload["reviewed_by"] = user_row["display_name"] or user_row["mobile"] or "admin"
    upload["reviewed_at"] = now_iso()


class ViewerProfileRequest(BaseModel):
    display_name: str = ""
    mobile: str = ""
    email: str = ""
    primary_club_id: str = ""
    selected_season_year: str = ""


class FollowPlayerRequest(BaseModel):
    player_name: str
    following: bool = True


class RegisterRequest(BaseModel):
    display_name: str
    mobile: str = ""
    email: str = ""
    password: str
    role: str = "player"
    roles: list[str] | str | None = None
    primary_club_id: str = ""
    member_name: str = ""
    member_id: str = ""
    player_id: str = ""
    aliases: list[str] | str = []
    date_of_birth: str = ""
    club_name: str = ""
    club_city: str = ""
    club_country: str = ""


class SignInRequest(BaseModel):
    identifier: str
    password: str = ""
    player_name: str = ""


class SelectClubRequest(BaseModel):
    club_id: str


class SeasonFixtureRequest(BaseModel):
    club_id: str = ""
    season_year: int
    date: str
    date_label: str
    opponent: str
    venue: str = ""
    match_type: str = "Friendly"
    scheduled_time: str = ""
    overs: str = "20"
    # Ask the club's players "Are you available?" when the match is added (off for "Start a new match" today).
    notify: bool = True


class PlayerAvailabilitySelfRequest(BaseModel):
    fixture_id: str
    status: str
    note: str = ""
    club_id: str = ""


class PlayerSeasonAvailabilityRequest(BaseModel):
    status: str
    note: str = ""
    club_id: str = ""


class PlayerSelfProfileRequest(BaseModel):
    full_name: str = ""
    gender: str = ""
    age: int = 0
    date_of_birth: str = ""
    role: str = ""
    batting_style: str = ""
    bowling_style: str = ""
    phone: str = ""
    email: str = ""
    notes: str = ""
    aliases: list[str] | str = []
    team_memberships: list[str] | str = []
    primary_club_id: str = ""


def current_dashboard(
    store: dict[str, Any],
    focus_club_id: str | None = None,
    requested_season_year: str | None = None,
) -> dict[str, Any]:
    return build_dashboard(store, get_llm_status(), focus_club_id or "", requested_season_year or "")


def _club_is_disabled(club: dict[str, Any] | None) -> bool:
    if not club:
        return False
    return str(club.get("is_disabled") or "").strip().lower() in {"1", "true", "yes", "disabled"}


def _selected_club(store: dict[str, Any], focus_club_id: str | None = None) -> dict[str, Any]:
    requested = str(
        focus_club_id
        or store.get("viewer_profile", {}).get("primary_club_id")
        or ""
    ).strip()

    logger.debug("Selecting club. requested=%s", requested)

    club = next(
        (
            club
            for club in store.get("clubs", [])
            if str(club.get("id") or "").strip() == requested
        ),
        None,
    )

    if not club:
        logger.warning("Club not found. Fallback club used.")

    return club or store.get("club", {})


def _club_by_identifier(clubs: list[dict[str, Any]], identifier: str) -> dict[str, Any] | None:
    clean = str(identifier or "").strip().lower()
    if not clean:
        return None
    for club in clubs:
        identifiers = {
            str(club.get("id") or "").strip().lower(),
            str(club.get("name") or "").strip().lower(),
            str(club.get("short_name") or "").strip().lower(),
            *(str(alias or "").strip().lower() for alias in club.get("aliases", []) or []),
        }
        if clean in {item for item in identifiers if item}:
            return club
    return None


def _lower_key(value: Any) -> str:
    return str(value or "").strip().lower()


def _club_context_names(store: dict[str, Any], club: dict[str, Any]) -> set[str]:
    club_id = _lower_key(club.get("id"))
    names = {
        club_id,
        _lower_key(club.get("name")),
        _lower_key(club.get("short_name")),
    }
    for team in store.get("teams", []):
        if _lower_key(team.get("club_id")) != club_id:
            continue
        names.add(_lower_key(team.get("name")))
        names.add(_lower_key(team.get("display_name")))
    return {name for name in names if name}


def _member_team_names(member: dict[str, Any]) -> list[str]:
    names: list[str] = []
    seen: set[str] = set()

    def add(value: Any) -> None:
        clean = str(value or "").strip()
        key = clean.lower()
        if not clean or key in seen:
            return
        seen.add(key)
        names.append(clean)

    add(member.get("team_name"))
    for raw in member.get("team_memberships", []) or member.get("memberships", []) or []:
        if isinstance(raw, str):
            add(raw)
            continue
        if isinstance(raw, dict):
            add(raw.get("team_name") or raw.get("name") or raw.get("display_name"))
    return names


def _archive_match_club_ids(store: dict[str, Any], club_id: str, match_id: str = "") -> list[str]:
    selected = _club_by_identifier(store.get("clubs", []), club_id)
    if not selected:
        return []
    related_ids = [str(selected.get("id") or "").strip()]
    if not match_id:
        return [item for item in dict.fromkeys(item for item in related_ids if item)]
    match = next((item for item in store.get("fixtures", []) if str(item.get("id") or "").strip() == str(match_id).strip()), None)
    if match:
        related_ids.append(str(match.get("club_id") or "").strip())
        opponent = _club_by_identifier(store.get("clubs", []), str(match.get("opponent") or match.get("visiting_team") or ""))
        if opponent:
            related_ids.append(str(opponent.get("id") or "").strip())
    return [item for item in dict.fromkeys(item for item in related_ids if item)]


def _auth_connection() -> sqlite3.Connection:
    logger.debug("🗄️ Opening DB connection: %s", DATABASE_FILE)
    DATABASE_FILE.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(DATABASE_FILE, timeout=60)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    # WAL is unsafe on Azure Files (SMB) and corrupted the production DB on 2026-11-04.
    connection.execute("PRAGMA journal_mode = %s" % ("DELETE" if os.environ.get("WEBSITE_SITE_NAME") else "WAL"))
    connection.execute("PRAGMA synchronous = NORMAL")
    connection.execute("PRAGMA busy_timeout = 60000")
    return connection


ROLE_IDS: dict[str, int] = {"superadmin": 1, "club_admin": 2, "captain": 3, "player": 4}

DEFAULT_ROLE_PERMISSIONS: dict[str, dict[str, str]] = {
    "player": {},
    "captain": {
        "score_matches": "Score matches and upload scorecards",
        "manage_fixtures": "Create and edit fixtures",
        "manage_players": "Invite and update club players",
    },
    "club_admin": {
        "score_matches": "Score matches and upload scorecards",
        "manage_club": "Update club-level details",
        "manage_fixtures": "Create and edit fixtures",
        "manage_players": "Invite and update club players",
    },
    "superadmin": {
        "view_admin": "View admin center and club controls",
        "manage_club": "Update club-level details",
        "manage_fixtures": "Create and edit fixtures",
        "manage_scorecards": "Review and approve scorecards",
        "score_matches": "Score matches and upload scorecards",
        "manage_players": "Update player records",
        "manage_roles": "Assign club roles",
    },
}


def _seed_role_catalog(connection: sqlite3.Connection) -> None:
    existing = connection.execute("SELECT COUNT(*) FROM app_roles").fetchone()[0]
    if existing:
        return
    now = now_iso()
    for role_name, permissions in DEFAULT_ROLE_PERMISSIONS.items():
        display_name = {
            "player": "Player",
            "captain": "Captain",
            "club_admin": "Club admin",
            "superadmin": "Superadmin",
        }.get(role_name, role_name.replace("_", " ").title())
        connection.execute(
            """
            INSERT INTO app_roles (role_name, display_name, description, created_at)
            VALUES (?, ?, ?, ?)
            """,
            (role_name, display_name, f"Default {display_name.lower()} role", now),
        )
        for permission, description in permissions.items():
            connection.execute(
                """
                INSERT INTO app_role_permissions (role_name, permission, description, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (role_name, permission, description, now),
            )


def _sync_role_permissions(connection: sqlite3.Connection) -> None:
    for role_name, permissions in DEFAULT_ROLE_PERMISSIONS.items():
        connection.execute("DELETE FROM app_role_permissions WHERE role_name = ?", (role_name,))
        now = now_iso()
        for permission, description in permissions.items():
            connection.execute(
                """
                INSERT INTO app_role_permissions (role_name, permission, description, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (role_name, permission, description, now),
            )


def ensure_auth_schema() -> None:
    global _AUTH_SCHEMA_BOOTSTRAP_DONE
    if _AUTH_SCHEMA_BOOTSTRAP_DONE:
        return
    with _AUTH_SCHEMA_BOOTSTRAP_LOCK:
        if _AUTH_SCHEMA_BOOTSTRAP_DONE:
            return
        try:
            load_store()
            with _auth_connection() as connection:
                connection.executescript(
                    """
                    CREATE TABLE IF NOT EXISTS app_users (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              display_name TEXT NOT NULL,
              mobile TEXT UNIQUE,
              email TEXT UNIQUE,
              password_hash TEXT NOT NULL,
              role TEXT NOT NULL,
              member_id TEXT,
              player_id TEXT,
              primary_club_id TEXT,
              created_at TEXT NOT NULL,
              FOREIGN KEY (member_id) REFERENCES members(id) ON DELETE SET NULL,
              FOREIGN KEY (primary_club_id) REFERENCES clubs(id) ON DELETE SET NULL
            );

                    CREATE TABLE IF NOT EXISTS app_auth_sessions (
              token TEXT PRIMARY KEY,
              user_id INTEGER NOT NULL,
              current_club_id TEXT,
              created_at TEXT NOT NULL,
              last_seen_at TEXT,
              ended_at TEXT,
              activity_count INTEGER NOT NULL DEFAULT 0,
              FOREIGN KEY (user_id) REFERENCES app_users(id) ON DELETE CASCADE,
              FOREIGN KEY (current_club_id) REFERENCES clubs(id) ON DELETE SET NULL
            );

                    CREATE TABLE IF NOT EXISTS app_roles (
              role_name TEXT PRIMARY KEY,
              display_name TEXT NOT NULL,
              description TEXT,
              created_at TEXT NOT NULL
            );

                    CREATE TABLE IF NOT EXISTS app_role_permissions (
              role_name TEXT NOT NULL,
              permission TEXT NOT NULL,
              description TEXT,
              created_at TEXT NOT NULL,
              PRIMARY KEY (role_name, permission),
              FOREIGN KEY (role_name) REFERENCES app_roles(role_name) ON DELETE CASCADE
            );

                    CREATE TABLE IF NOT EXISTS app_user_club_roles (
              user_id INTEGER NOT NULL,
              club_id TEXT NOT NULL,
              role_name TEXT NOT NULL,
              created_at TEXT NOT NULL,
              PRIMARY KEY (user_id, club_id, role_name),
              FOREIGN KEY (user_id) REFERENCES app_users(id) ON DELETE CASCADE,
              FOREIGN KEY (club_id) REFERENCES clubs(id) ON DELETE CASCADE,
              FOREIGN KEY (role_name) REFERENCES app_roles(role_name) ON DELETE RESTRICT
            );

                    CREATE TABLE IF NOT EXISTS app_player_season_availability (
              user_id INTEGER NOT NULL,
              club_id TEXT NOT NULL,
              status TEXT,
              note TEXT,
              updated_at TEXT NOT NULL,
              PRIMARY KEY (user_id, club_id),
              FOREIGN KEY (user_id) REFERENCES app_users(id) ON DELETE CASCADE,
              FOREIGN KEY (club_id) REFERENCES clubs(id) ON DELETE CASCADE
            );

                    CREATE TABLE IF NOT EXISTS app_audit_log (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              created_at TEXT NOT NULL,
              actor_user_id INTEGER,
              actor_display_name TEXT,
              club_id TEXT,
              club_name TEXT,
              action TEXT NOT NULL,
              entity_type TEXT NOT NULL,
              entity_id TEXT,
              details_json TEXT,
              source TEXT,
              FOREIGN KEY (actor_user_id) REFERENCES app_users(id) ON DELETE SET NULL
            );

                    CREATE TABLE IF NOT EXISTS app_analytics_visits (
              visitor_key TEXT NOT NULL,
              bucket_hour TEXT NOT NULL,
              visited_at TEXT NOT NULL,
              page_path TEXT NOT NULL,
              PRIMARY KEY (visitor_key, bucket_hour)
            );

                    CREATE TABLE IF NOT EXISTS app_live_match_viewers (
              match_id TEXT NOT NULL,
              visitor_key TEXT NOT NULL,
              last_seen_at TEXT NOT NULL,
              PRIMARY KEY (match_id, visitor_key)
            );

                    CREATE TABLE IF NOT EXISTS app_name_claims (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              user_id INTEGER NOT NULL,
              member_id TEXT NOT NULL,
              claimed_name TEXT NOT NULL,
              claimed_name_norm TEXT NOT NULL,
              status TEXT NOT NULL DEFAULT 'pending',
              created_at TEXT NOT NULL,
              decided_at TEXT,
              decided_by_user_id INTEGER,
              decision_note TEXT,
              FOREIGN KEY (user_id) REFERENCES app_users(id) ON DELETE CASCADE,
              FOREIGN KEY (decided_by_user_id) REFERENCES app_users(id) ON DELETE SET NULL
            );

                    CREATE UNIQUE INDEX IF NOT EXISTS idx_name_claims_pending ON app_name_claims(user_id, member_id, claimed_name_norm) WHERE status = 'pending';
                    CREATE INDEX IF NOT EXISTS idx_name_claims_status ON app_name_claims(status, created_at);
                    CREATE TABLE IF NOT EXISTS app_merge_requests (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              requester_user_id INTEGER NOT NULL,
              requester_member_id TEXT NOT NULL,
              target_member_id TEXT NOT NULL,
              status TEXT NOT NULL DEFAULT 'pending',
              created_at TEXT NOT NULL,
              decided_at TEXT,
              decided_by_user_id INTEGER,
              decision_note TEXT,
              merge_id INTEGER,
              keep_member_id TEXT,
              FOREIGN KEY (requester_user_id) REFERENCES app_users(id) ON DELETE CASCADE
            );
                    CREATE INDEX IF NOT EXISTS idx_merge_requests_status ON app_merge_requests(status, created_at);
                    CREATE TABLE IF NOT EXISTS app_merge_suggestion_dismissals (
              user_id INTEGER NOT NULL,
              target_member_id TEXT NOT NULL,
              created_at TEXT NOT NULL,
              PRIMARY KEY (user_id, target_member_id),
              FOREIGN KEY (user_id) REFERENCES app_users(id) ON DELETE CASCADE
            );
                    CREATE TABLE IF NOT EXISTS app_name_match_rejections (
              member_low_id TEXT NOT NULL,
              member_high_id TEXT NOT NULL,
              rejected_by_user_id INTEGER,
              created_at TEXT NOT NULL,
              PRIMARY KEY (member_low_id, member_high_id)
            );
                    CREATE TABLE IF NOT EXISTS app_member_merges (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              kept_member_id TEXT NOT NULL,
              removed_member_id TEXT NOT NULL,
              removed_name TEXT NOT NULL DEFAULT '',
              merged_by_user_id INTEGER,
              created_at TEXT NOT NULL,
              store_version_after INTEGER NOT NULL,
              store_snapshot TEXT NOT NULL,
              auth_snapshot TEXT NOT NULL,
              undone_at TEXT,
              undone_by_user_id INTEGER
            );
                    CREATE INDEX IF NOT EXISTS idx_analytics_visits_time ON app_analytics_visits(visited_at);
                    CREATE INDEX IF NOT EXISTS idx_live_match_viewers_time ON app_live_match_viewers(match_id, last_seen_at);
                    """
                )
                user_columns = {str(row[1]) for row in connection.execute("PRAGMA table_info(app_users)").fetchall()}
                if "player_id" not in user_columns:
                    connection.execute("ALTER TABLE app_users ADD COLUMN player_id TEXT")
                merge_request_columns = {str(row[1]) for row in connection.execute("PRAGMA table_info(app_merge_requests)").fetchall()}
                if "keep_member_id" not in merge_request_columns:
                    connection.execute("ALTER TABLE app_merge_requests ADD COLUMN keep_member_id TEXT")

                connection.execute("CREATE INDEX IF NOT EXISTS idx_app_users_player_id ON app_users(player_id)")
                _seed_role_catalog(connection)
                # Nov 4 2026 (Amit): fixed role IDs - 1 superadmin, 2 club admin, 3 captain, 4 player
                role_columns = {str(row[1]) for row in connection.execute("PRAGMA table_info(app_roles)").fetchall()}
                if "role_id" not in role_columns:
                    connection.execute("ALTER TABLE app_roles ADD COLUMN role_id INTEGER")
                for role_name, role_id in ROLE_IDS.items():
                    connection.execute("UPDATE app_roles SET role_id = ? WHERE role_name = ?", (role_id, role_name))
                _sync_role_permissions(connection)
                _migrate_multi_role_assignments(connection)
                _migrate_auth_sessions(connection)
                subscriptions.ensure_schema(connection)
            load_store()
        except sqlite3.OperationalError as exc:
            if "locked" not in str(exc).lower():
                raise
            logger.warning("Auth schema bootstrap skipped because the database is busy. Login will retry on the next request.")
            return
        except sqlite3.DatabaseError as exc:
            logger.warning("Auth schema bootstrap skipped because the auth database is unhealthy: %s", exc)
            return
        _AUTH_SCHEMA_BOOTSTRAP_DONE = True


def _audit_event(
    action: str,
    entity_type: str,
    entity_id: str = "",
    *,
    actor: sqlite3.Row | None = None,
    club_id: str = "",
    club_name: str = "",
    details: dict[str, Any] | None = None,
    source: str = "",
) -> None:
    ensure_auth_schema()
    actor_id = int(actor["id"]) if actor is not None and actor["id"] is not None else None
    actor_name = str(actor["display_name"] or actor["mobile"] or "system") if actor is not None else "system"
    payload = json.dumps(details or {}, ensure_ascii=False, separators=(",", ":"))
    with _auth_connection() as connection:
        connection.execute(
            """
            INSERT INTO app_audit_log (
              created_at, actor_user_id, actor_display_name, club_id, club_name,
              action, entity_type, entity_id, details_json, source
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                now_iso(),
                actor_id,
                actor_name,
                str(club_id or "").strip() or None,
                str(club_name or "").strip() or None,
                str(action or "").strip(),
                str(entity_type or "").strip(),
                str(entity_id or "").strip() or None,
                payload,
                str(source or "").strip() or None,
            ),
        )


def _parse_utc_timestamp(value: str | None) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc).replace(tzinfo=None)
    except ValueError:
        return None


def _session_timeout_seconds() -> int:
    return int(SESSION_TIMEOUT_MINUTES * 60)


def _session_snapshot(connection: sqlite3.Connection, token: str) -> dict[str, Any] | None:
    row = connection.execute(
        """
        SELECT token, user_id, current_club_id, created_at, last_seen_at, ended_at, activity_count
        FROM app_auth_sessions
        WHERE token = ?
        """,
        (token,),
    ).fetchone()
    if not row:
        return None
    created_at = _parse_utc_timestamp(row["created_at"])
    last_seen_at = _parse_utc_timestamp(row["last_seen_at"] or row["created_at"])
    ended_at = _parse_utc_timestamp(row["ended_at"])
    now = datetime.utcnow()
    session_start = created_at or last_seen_at or now
    active_last_seen = last_seen_at or session_start
    elapsed_seconds = max(0, int((now - session_start).total_seconds()))
    idle_seconds = max(0, int((now - active_last_seen).total_seconds()))
    return {
        "token": row["token"],
        "user_id": int(row["user_id"]),
        "current_club_id": row["current_club_id"] or "",
        "created_at": row["created_at"] or "",
        "last_seen_at": row["last_seen_at"] or row["created_at"] or "",
        "ended_at": row["ended_at"] or "",
        "activity_count": int(row["activity_count"] or 0),
        "timeout_minutes": SESSION_TIMEOUT_MINUTES,
        "elapsed_seconds": elapsed_seconds,
        "idle_seconds": idle_seconds,
        "active": not bool(ended_at),
    }


def _touch_auth_session(
    connection: sqlite3.Connection,
    token: str,
    *,
    force: bool = False,
    activity_delta: int = 1,
) -> None:
    row = connection.execute(
        """
        SELECT created_at, last_seen_at, ended_at, activity_count
        FROM app_auth_sessions
        WHERE token = ?
        """,
        (token,),
    ).fetchone()
    if not row or row["ended_at"]:
        return
    now = now_iso()
    last_seen = _parse_utc_timestamp(row["last_seen_at"] or row["created_at"])
    elapsed = (datetime.utcnow() - last_seen).total_seconds() if last_seen else _session_timeout_seconds() + 1
    should_touch = force or last_seen is None or elapsed >= 30
    if should_touch:
        connection.execute(
            """
            UPDATE app_auth_sessions
            SET last_seen_at = ?, activity_count = COALESCE(activity_count, 0) + ?
            WHERE token = ?
            """,
            (now, max(1, int(activity_delta or 1)), token),
        )


def _end_auth_session(connection: sqlite3.Connection, token: str) -> None:
    connection.execute(
        """
        UPDATE app_auth_sessions
        SET ended_at = COALESCE(ended_at, ?)
        WHERE token = ?
        """,
        (now_iso(), token),
    )


def _migrate_multi_role_assignments(connection: sqlite3.Connection) -> None:
    table_info = connection.execute("PRAGMA table_info(app_user_club_roles)").fetchall()
    pk_columns = [str(row["name"]) for row in table_info if int(row["pk"] or 0)]
    if pk_columns == ["user_id", "club_id", "role_name"]:
        return
    existing_rows = connection.execute(
        "SELECT user_id, club_id, role_name, created_at FROM app_user_club_roles"
    ).fetchall()
    connection.execute("ALTER TABLE app_user_club_roles RENAME TO app_user_club_roles_legacy")
    connection.execute(
        """
        CREATE TABLE app_user_club_roles (
          user_id INTEGER NOT NULL,
          club_id TEXT NOT NULL,
          role_name TEXT NOT NULL,
          created_at TEXT NOT NULL,
          PRIMARY KEY (user_id, club_id, role_name),
          FOREIGN KEY (user_id) REFERENCES app_users(id) ON DELETE CASCADE,
          FOREIGN KEY (club_id) REFERENCES clubs(id) ON DELETE CASCADE,
          FOREIGN KEY (role_name) REFERENCES app_roles(role_name) ON DELETE RESTRICT
        )
        """
    )
    for row in existing_rows:
        role_name = str(row["role_name"] or "").strip()
        if not role_name:
            continue
        connection.execute(
            """
            INSERT OR IGNORE INTO app_user_club_roles (user_id, club_id, role_name, created_at)
            VALUES (?, ?, ?, ?)
            """,
            (int(row["user_id"]), str(row["club_id"] or ""), role_name, str(row["created_at"] or now_iso())),
        )
    connection.execute("DROP TABLE app_user_club_roles_legacy")


def _migrate_auth_sessions(connection: sqlite3.Connection) -> None:
    table_info = connection.execute("PRAGMA table_info(app_auth_sessions)").fetchall()
    existing_columns = {str(row["name"]) for row in table_info}
    migrations = [
        ("last_seen_at", "ALTER TABLE app_auth_sessions ADD COLUMN last_seen_at TEXT"),
        ("ended_at", "ALTER TABLE app_auth_sessions ADD COLUMN ended_at TEXT"),
        ("activity_count", "ALTER TABLE app_auth_sessions ADD COLUMN activity_count INTEGER NOT NULL DEFAULT 0"),
    ]
    for column_name, statement in migrations:
        if column_name not in existing_columns:
            connection.execute(statement)
    connection.execute(
        """
        UPDATE app_auth_sessions
        SET last_seen_at = COALESCE(last_seen_at, created_at),
            activity_count = COALESCE(activity_count, 0)
        """
    )


def _password_hash(password: str) -> str:
    return hashlib.sha256(password.encode("utf-8")).hexdigest()


def _role_permissions(connection: sqlite3.Connection, role_name: str) -> set[str]:
    rows = connection.execute(
        "SELECT permission FROM app_role_permissions WHERE role_name = ?",
        (role_name,),
    ).fetchall()
    return {str(row["permission"] or "").strip() for row in rows if str(row["permission"] or "").strip()}


def _role_rank(role_name: str) -> int:
    return {
        "player": 1,
        "captain": 2,
        "club_admin": 3,
        "superadmin": 4,
    }.get(str(role_name or "").strip(), 0)


def _normalize_role_name(role_name: str) -> str:
    clean = str(role_name or "").strip().lower()
    if clean == "admin":
        return "club_admin"
    return clean


def _user_role_names(user_row: sqlite3.Row, current_club_id: str = "") -> list[str]:
    base_role = str(user_row["role"] or "player").strip() or "player"
    roles = [base_role]
    club_id = str(current_club_id or "").strip()
    if club_id:
        with _auth_connection() as connection:
            rows = connection.execute(
                """
                SELECT role_name
                FROM app_user_club_roles
                WHERE user_id = ? AND club_id = ?
                ORDER BY role_name
                """,
                (int(user_row["id"]), club_id),
            ).fetchall()
        roles.extend(str(row["role_name"] or "").strip() for row in rows if str(row["role_name"] or "").strip())
    unique_roles = []
    for role_name in roles:
        if role_name and role_name not in unique_roles:
            unique_roles.append(role_name)
    return unique_roles


def _effective_role_name(user_row: sqlite3.Row, current_club_id: str = "") -> str:
    roles = _user_role_names(user_row, current_club_id)
    if not roles:
        return "player"
    return max(roles, key=_role_rank)


def _user_permissions(user_row: sqlite3.Row, current_club_id: str = "") -> set[str]:
    role_names = _user_role_names(user_row, current_club_id)
    with _auth_connection() as connection:
        permissions: set[str] = set()
        for role_name in role_names:
            permissions |= _role_permissions(connection, role_name)
        if "superadmin" in role_names:
            permissions |= {
                "view_admin",
                "manage_club",
                "manage_fixtures",
                "manage_scorecards",
                "score_matches",
                "manage_players",
                "manage_roles",
            }
        return permissions


def _role_catalog(connection: sqlite3.Connection) -> list[dict[str, Any]]:
    rows = connection.execute(
        """
        SELECT role_name, display_name, description, created_at
        FROM app_roles
        ORDER BY CASE role_name
          WHEN 'player' THEN 1
          WHEN 'captain' THEN 2
          WHEN 'club_admin' THEN 3
          WHEN 'superadmin' THEN 4
          ELSE 99
        END, display_name
        """
    ).fetchall()
    permissions_by_role = {
        row["role_name"]: sorted(
            permission_row["permission"]
            for permission_row in connection.execute(
                "SELECT permission FROM app_role_permissions WHERE role_name = ? ORDER BY permission",
                (row["role_name"],),
            ).fetchall()
        )
        for row in rows
    }
    return [
        {
            "role_name": row["role_name"],
            "display_name": row["display_name"],
            "description": row["description"] or "",
            "permissions": permissions_by_role.get(row["role_name"], []),
        }
        for row in rows
    ]


def _auth_user_payload(user_row: sqlite3.Row, current_club_id: str = "") -> dict[str, Any]:
    effective_role = _effective_role_name(user_row, current_club_id)
    role_names = _user_role_names(user_row, current_club_id)
    permissions = sorted(_user_permissions(user_row, current_club_id))
    member_name = ""
    member_full_name = ""
    current_club_name = ""
    store = _safe_load_store_for_auth("auth.user_payload")
    member = _member_for_user(store, user_row)
    if member:
        member_name = str(member.get("name") or "").strip()
        member_full_name = str(member.get("full_name") or "").strip()
    try:
        club_lookup_id = str(current_club_id or user_row["primary_club_id"] or "").strip()
        club = next(
            (club for club in store.get("clubs", []) if str(club.get("id") or "").strip() == club_lookup_id),
            store.get("club", {}) if club_lookup_id else {},
        )
        current_club_name = str(club.get("name") or "").strip()
    except Exception:
        current_club_name = ""
    return {
        "id": int(user_row["id"]),
        "display_name": user_row["display_name"] or "",
        "mobile": user_row["mobile"] or "",
        "email": user_row["email"] or "",
        "role": user_row["role"] or "player",
        "roles": role_names,
        "effective_role": effective_role,
        "role_id": ROLE_IDS.get(str(effective_role or ""), 4),
        "permissions": permissions,
        "member_id": user_row["member_id"] or "",
        "player_id": str(user_row["player_id"] or (member.get("player_id") if member else "") or ("1000" if str(user_row["role"] or "").lower() == "superadmin" else "")),
        "viewer_member_name": member_name,
        "viewer_member_full_name": member_full_name,
        "primary_club_id": user_row["primary_club_id"] or "",
        "current_club_id": current_club_id or user_row["primary_club_id"] or "",
        "current_club_name": current_club_name,
        **_plan_payload_fields(user_row, current_club_id),
    }


def _plan_payload_fields(user_row: sqlite3.Row, current_club_id: str = "") -> dict[str, Any]:
    plan = _plan_for(user_row, current_club_id)
    club_id = str(current_club_id or user_row["primary_club_id"] or "")
    return {
        "plan": plan.get("plan", "free"),
        "plan_name": plan.get("plan_name", "Free"),
        "plan_features": plan.get("features", []),
        # Players of a club whose captain/admin pays can still mark availability (README: "Plan-based menu").
        "club_paid": _club_is_paid(club_id) if plan.get("plan", "free") == "free" else True,
        # Free users: their one free AI match is still open (README: "One free AI match").
        "ai_trial_open": _ai_trial_open(plan.get("ai_trial")),
        "ai_trial": plan.get("ai_trial"),
    }


def _ai_trial_open(trial: Any) -> bool:
    if not isinstance(trial, dict):
        return False
    if not trial.get("used"):
        return True
    try:
        return not _fixture_is_past(get_match_or_404(load_store(), str(trial.get("match_id") or "")))
    except Exception:
        return False


# Pages that are part of Pro. Free users are sent to /pricing (README: "Plan-based menu").
_PAID_PAGES = {
    "schedule": "match_roster",
    "match-center": "match_roster",
    "squad": "match_roster",
    "teams": "match_roster",
    "availability": "availability",
    "assistant": "ai_assistant",
}


def _paid_page_redirect(request: Request, page: str) -> Response | None:
    feature = _PAID_PAGES.get(page)
    if not feature:
        return None
    token = _auth_token_from_request(request)
    if not token:
        return None
    try:
        user_row, current_club_id = _auth_user_from_token(token, touch=False)
    except HTTPException:
        return None
    if _has_feature(user_row, current_club_id, feature):
        return None
    if feature == "availability" and _club_is_paid(str(current_club_id or user_row["primary_club_id"] or "")):
        return None
    if feature in subscriptions.AI_TRIAL_FEATURES and _ai_trial_open(_plan_for(user_row, current_club_id).get("ai_trial")):
        return None
    return RedirectResponse(f"/pricing?feature={feature}", status_code=303)

def _visible_club_choices_for_user(
    store: dict[str, Any],
    user_row: sqlite3.Row,
    current_club_id: str = "",
    all_for_superadmin: bool = True,
) -> list[dict[str, str]]:
    linked_ids: list[str] = []

    def add(value: Any) -> None:
        clean = str(value or "").strip()
        if clean and clean not in linked_ids:
            linked_ids.append(clean)

    add(current_club_id)
    add(user_row["primary_club_id"])

    member = _member_for_user(store, user_row)
    if member:
        add(member.get("primary_club_id"))
        for club_membership in member.get("club_memberships", []) or []:
            add(club_membership.get("club_id"))
        for team_membership in member.get("team_memberships", []) or []:
            # Team memberships can be plain team names (saved from the profile page) - skip those.
            if isinstance(team_membership, dict):
                add(team_membership.get("club_id"))

    try:
        with _auth_connection() as connection:
            for row in connection.execute(
                "SELECT club_id FROM app_user_club_roles WHERE user_id = ?",
                (int(user_row["id"]),),
            ).fetchall():
                add(row["club_id"])
    except Exception:
        logger.debug("Could not load club-role links for user_id=%s", user_row["id"])

    if all_for_superadmin and "superadmin" in _user_role_names(user_row, current_club_id):
        return _sorted_club_choices(store, current_club_id, include_disabled=True)

    clubs = [
        club
        for club in store.get("clubs", [])
        if str(club.get("id") or "").strip() in set(linked_ids)
        and not _club_is_disabled(club)
    ]
    if not clubs:
        fallback_club_id = str(current_club_id or user_row["primary_club_id"] or "").strip()
        club = next(
            (item for item in store.get("clubs", []) if str(item.get("id") or "").strip() == fallback_club_id),
            None,
        )
        clubs = [club] if club and not _club_is_disabled(club) else []
    return _sorted_club_choices({"clubs": clubs}, str(current_club_id or user_row["primary_club_id"] or ""))

def _member_for_user(store: dict[str, Any], user_row: sqlite3.Row) -> dict[str, Any] | None:
    member_id = str(user_row["member_id"] or "").strip()
    members = store.get("members", [])
    if member_id:
        by_id = next((item for item in members if str(item.get("id") or "").strip() == member_id), None)
        if by_id:
            return by_id
    hint = str(user_row["display_name"] or "").strip()
    if not hint:
        return None
    resolved_name = resolve_member_name(store, hint)
    normalized = normalize_name(resolved_name)
    return next(
        (
            item for item in members
            if normalize_name(str(item.get("name") or "")) == normalized
            or normalize_name(str(item.get("full_name") or "")) == normalized
            or any(normalize_name(str(alias or "")) == normalized for alias in (item.get("aliases", []) or []))
        ),
        None,
    )


def _member_identity_keys(member: dict[str, Any]) -> set[str]:
    keys: set[str] = set()
    for value in [
        member.get("player_id"),
        member.get("normalized_name"),
        member.get("name"),
        member.get("full_name"),
        *(member.get("aliases", []) or []),
    ]:
        normalized = normalize_name(str(value or ""))
        if normalized:
            keys.add(normalized)
    return keys


def _member_matches_name(member: dict[str, Any], candidate: str) -> bool:
    normalized_candidate = normalize_name(candidate)
    if not normalized_candidate:
        return False
    return normalized_candidate in _member_identity_keys(member)


def _validated_date_of_birth(value: str | None) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    try:
        parsed = date.fromisoformat(text)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Enter a valid date of birth.") from exc
    if parsed > _current_local_date():
        raise HTTPException(status_code=400, detail="Date of birth cannot be in the future.")
    return parsed.isoformat()





def _existing_user_for_member(connection: sqlite3.Connection, member_id: str) -> sqlite3.Row | None:
    clean_member_id = str(member_id or "").strip()
    if not clean_member_id:
        return None
    return connection.execute(
        """
        SELECT *
        FROM app_users
        WHERE member_id = ?
        ORDER BY id
        LIMIT 1
        """,
        (clean_member_id,),
    ).fetchone()


def _require_permission(token: str | None, permission: str) -> tuple[sqlite3.Row, str]:
    user_row, current_club_id = _auth_user_from_token(token)
    if permission not in _user_permissions(user_row, current_club_id):
        raise HTTPException(status_code=403, detail="You do not have permission to perform this action.")
    return user_row, current_club_id


def _match_scorer_is_authorized(
    store: dict[str, Any],
    user_row: sqlite3.Row,
    current_club_id: str,
    match: dict[str, Any],
) -> bool:
    """Allow a signed-in player from either playing club to enter live scores."""
    participant_clubs = _match_participating_club_ids(store, match)
    if "superadmin" in _user_role_names(user_row, current_club_id):
        return True
    user_club_ids = set(_user_club_ids(store, user_row, current_club_id)) | {
        str(user_row["primary_club_id"] or ""), str(current_club_id or "")
    }
    if participant_clubs.intersection(user_club_ids):
        return True
    member = _member_for_user(store, user_row)
    captain_name = normalize_name(str(match.get("heartlake_captain") or ""))
    member_names = {
        normalize_name(str(value or ""))
        for value in [
            user_row["display_name"],
            (member or {}).get("name"),
            (member or {}).get("full_name"),
            *((member or {}).get("aliases", []) or []),
        ]
        if str(value or "").strip()
    }
    captain_member_id = str(match.get("heartlake_captain_member_id") or "").strip()
    is_assigned_captain = bool(
        (captain_name and captain_name in member_names)
        or (captain_member_id and captain_member_id == str(user_row["member_id"] or "").strip())
    )
    return is_assigned_captain


def _match_participating_club_ids(store: dict[str, Any], match: dict[str, Any]) -> set[str]:
    """Resolve the owner and recognized opponent clubs for this fixture."""
    ids = {str(match.get("club_id") or "").strip()} - {""}
    labels = {str(match.get("opponent") or "").strip(), str(match.get("visiting_team") or "").strip()}
    for innings in (match.get("scorebook") or {}).get("innings", []) or []:
        labels.update((str(innings.get("batting_team") or "").strip(), str(innings.get("bowling_team") or "").strip()))
    for label in labels - {""}:
        opponent = _find_club_by_name(store, label)
        if opponent and opponent.get("id"):
            ids.add(str(opponent["id"]))
    return ids


def _match_score_editor_is_authorized(store: dict[str, Any], user_row: sqlite3.Row, current_club_id: str, match: dict[str, Any]) -> bool:
    """Only a playing-club captain/admin or a superadmin may alter saved scoring."""
    if "superadmin" in _user_role_names(user_row, current_club_id):
        return True
    participant_clubs = _match_participating_club_ids(store, match)
    linked_clubs = set(_user_club_ids(store, user_row, current_club_id)) | {
        str(user_row["primary_club_id"] or ""), str(current_club_id or "")
    }
    member = _member_for_user(store, user_row)
    member_names = {normalize_name(str(value or "")) for value in [
        user_row["display_name"], (member or {}).get("name"), (member or {}).get("full_name"),
        *((member or {}).get("aliases", []) or []),
    ] if str(value or "").strip()}
    assigned = normalize_name(str(match.get("heartlake_captain") or "")) in member_names or (
        str(match.get("heartlake_captain_member_id") or "").strip() == str(user_row["member_id"] or "").strip()
    )
    for club_id in participant_clubs.intersection(linked_clubs):
        if set(_user_role_names(user_row, club_id)).intersection({"captain", "club_admin"}):
            return True
    return bool(assigned and participant_clubs.intersection(linked_clubs))


def _require_match_score_editor(token: str | None, match_id: str) -> tuple[sqlite3.Row, str]:
    user_row, current_club_id = _auth_user_from_token(token)
    store = load_store()
    try:
        match = get_match_or_404(store, match_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    if not _match_score_editor_is_authorized(store, user_row, current_club_id, match):
        raise HTTPException(status_code=403, detail="Only a playing club captain, club admin, or superadmin can edit saved scores.")
    return user_row, current_club_id


def _match_delete_is_authorized(
    store: dict[str, Any],
    user_row: sqlite3.Row,
    current_club_id: str,
    match: dict[str, Any],
) -> bool:
    club_id = str(match.get("club_id") or "").strip()
    if "superadmin" in _user_role_names(user_row, current_club_id):
        return True
    member = _member_for_user(store, user_row)
    if club_id:
        roles = set(_user_role_names(user_row, club_id))
        allowed_clubs = set(_user_club_ids(store, user_row, current_club_id)) | {
            str(user_row["primary_club_id"] or ""),
            str(current_club_id or ""),
        }
        # Nov 4 2026 (Amit's role rules): deleting a match / scorecard is for club admins and the superadmin only
        # (captains manage and edit their games but don't delete them).
        if club_id in allowed_clubs and roles.intersection({"club_admin"}):
            return True
    return False


def _require_match_scorer(token: str | None, match_id: str, expected_club_id: str = "") -> tuple[sqlite3.Row, str]:
    """Authorize club scorers, superadmins, and the captain assigned to this match."""
    user_row, current_club_id = _auth_user_from_token(token)
    store = load_store()
    try:
        match = get_match_or_404(store, match_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    if expected_club_id and str(match.get("club_id") or "") != str(expected_club_id).strip():
        raise HTTPException(status_code=404, detail="Fixture not found.")
    if not _match_scorer_is_authorized(store, user_row, current_club_id, match):
        raise HTTPException(status_code=403, detail="You can only score your own club's matches.")
    return user_row, current_club_id


def _auth_user_from_token(token: str | None, touch: bool = True) -> tuple[sqlite3.Row, str]:
    ensure_auth_schema()
    if not token:
        raise HTTPException(status_code=401, detail="Sign in first.")
    with _auth_connection() as connection:
        row = connection.execute(
            """
            SELECT u.*, s.current_club_id, s.created_at AS session_created_at, s.last_seen_at AS session_last_seen_at, s.ended_at AS session_ended_at, s.activity_count AS session_activity_count
            FROM app_auth_sessions s
            JOIN app_users u ON u.id = s.user_id
            WHERE s.token = ?
            """,
            (token,),
        ).fetchone()
        if not row:
            raise HTTPException(status_code=401, detail="Session expired. Sign in again.")
        if row["session_ended_at"]:
            raise HTTPException(status_code=401, detail="Session expired. Sign in again.")
        last_seen = _parse_utc_timestamp(row["session_last_seen_at"] or row["session_created_at"])
        if last_seen is not None:
            idle_seconds = int((datetime.utcnow() - last_seen).total_seconds())
            if idle_seconds >= _session_timeout_seconds():
                _end_auth_session(connection, token)
                raise HTTPException(status_code=401, detail="Session expired after 30 minutes of inactivity. Sign in again.")
        if touch:
            _touch_auth_session(connection, token)
    current_club_id = str(row["current_club_id"] or row["primary_club_id"] or "").strip()
    if current_club_id:
        store = load_store()
        current_club = next(
            (item for item in store.get("clubs", []) if str(item.get("id") or "").strip() == current_club_id),
            None,
        )
        if _club_is_disabled(current_club) and "superadmin" not in _user_role_names(row, current_club_id):
            active_clubs = _visible_club_choices_for_user(store, row, current_club_id)
            if not active_clubs:
                raise HTTPException(status_code=403, detail="Your club is disabled. Contact a superadmin to restore access.")
            primary_id = str(row["primary_club_id"] or "").strip()
            current_club_id = next(
                (str(item.get("id") or "") for item in active_clubs if str(item.get("id") or "") == primary_id),
                str(active_clubs[0].get("id") or ""),
            )
            with _auth_connection() as connection:
                connection.execute(
                    "UPDATE app_auth_sessions SET current_club_id = ? WHERE token = ?",
                    (current_club_id or None, token),
                )
    return row, current_club_id


def _safe_load_store_for_auth(context: str) -> dict[str, Any]:
    try:
        return load_store()
    except Exception as exc:
        logger.warning("%s: store unavailable, returning minimal auth payload: %s", context, exc)
        return {
            "clubs": [],
            "members": [],
            "fixtures": [],
            "archive_uploads": [],
            "duplicate_uploads": [],
            "teams": [],
            "insights": {},
            "member_summary_stats": [],
            "member_year_stats": [],
            "member_club_stats": [],
            "club_summary_stats": [],
            "club_year_stats": [],
            "viewer_profile": {},
        }


def _require_admin(token: str | None) -> tuple[sqlite3.Row, str]:
    return _require_permission(token, "view_admin")


def _require_superadmin(token: str | None) -> tuple[sqlite3.Row, str]:
    user_row, current_club_id = _require_admin(token)
    if _effective_role_name(user_row, current_club_id) != "superadmin":
        raise HTTPException(status_code=403, detail="Only superadmin can perform this action.")
    return user_row, current_club_id


@app.get("/api/admin/traffic")
def admin_traffic(x_auth_token: str | None = Header(default=None)) -> dict[str, Any]:
    _require_superadmin(x_auth_token)
    zone = ZoneInfo(APP_TIMEZONE)
    now_utc = datetime.now(timezone.utc)
    now_local = now_utc.astimezone(zone)
    cutoff = (now_utc - timedelta(days=366 * 5 + 5)).isoformat(timespec="seconds").replace("+00:00", "Z")
    ensure_auth_schema()
    with _auth_connection() as connection:
        rows = connection.execute(
            "SELECT visitor_key, visited_at FROM app_analytics_visits WHERE visited_at >= ?",
            (cutoff,),
        ).fetchall()

    hourly_visitors: dict[str, set[str]] = defaultdict(set)
    daily_visitors: dict[str, set[str]] = defaultdict(set)
    monthly_visitors: dict[str, set[str]] = defaultdict(set)
    annual_visitors: dict[str, set[str]] = defaultdict(set)
    peak_counts: Counter[int] = Counter()
    parsed_rows: list[tuple[str, datetime]] = []
    for row in rows:
        try:
            visited = datetime.fromisoformat(str(row["visited_at"]).replace("Z", "+00:00")).astimezone(zone)
        except (TypeError, ValueError):
            continue
        visitor_key = str(row["visitor_key"] or "")
        parsed_rows.append((visitor_key, visited))
        hour_key = visited.strftime("%Y-%m-%dT%H:00")
        day_key = visited.date().isoformat()
        month_key = visited.strftime("%Y-%m")
        year_key = visited.strftime("%Y")
        hourly_visitors[hour_key].add(visitor_key)
        daily_visitors[day_key].add(visitor_key)
        monthly_visitors[month_key].add(visitor_key)
        annual_visitors[year_key].add(visitor_key)
        if visited >= now_local - timedelta(days=30):
            peak_counts[visited.hour] += 1

    hour_start = now_local.replace(minute=0, second=0, microsecond=0) - timedelta(hours=23)
    hourly_buckets = [hour_start + timedelta(hours=index) for index in range(24)]
    day_start = now_local.date() - timedelta(days=29)
    daily_buckets = [day_start + timedelta(days=index) for index in range(30)]
    month_total = now_local.year * 12 + now_local.month - 1
    monthly_buckets = [
        (month_total - offset) for offset in range(11, -1, -1)
    ]
    annual_buckets = list(range(now_local.year - 4, now_local.year + 1))

    def month_label(value: int) -> str:
        year, month_index = divmod(value, 12)
        return f"{year:04d}-{month_index + 1:02d}"

    def series(buckets: list[Any], source: dict[str, set[str]], key_fn: Any, label_fn: Any) -> list[dict[str, Any]]:
        output = []
        for bucket_value in buckets:
            key = key_fn(bucket_value)
            output.append({"bucket": key, "label": label_fn(bucket_value), "visitors": len(source.get(key, set()))})
        return output

    totals = {
        "hourly": len({visitor for visitor, visited in parsed_rows if visited >= now_local - timedelta(hours=24)}),
        "daily": len({visitor for visitor, visited in parsed_rows if visited >= now_local - timedelta(days=30)}),
        "monthly": len({visitor for visitor, visited in parsed_rows if visited >= now_local - timedelta(days=366)}),
        "annually": len({visitor for visitor, visited in parsed_rows if visited >= now_local - timedelta(days=366 * 5)}),
    }
    peak_hour = max(range(24), key=lambda hour: (peak_counts[hour], -hour))
    return {
        "timezone": APP_TIMEZONE,
        "generated_at": now_iso(),
        "totals": totals,
        "peak_time": {"hour": peak_hour, "label": f"{peak_hour:02d}:00–{(peak_hour + 1) % 24:02d}:00", "visitors": peak_counts[peak_hour], "window_days": 30},
        "hourly": series(hourly_buckets, hourly_visitors, lambda value: value.strftime("%Y-%m-%dT%H:00"), lambda value: value.strftime("%b %d, %I %p").replace(" 0", " ")),
        "daily": series(daily_buckets, daily_visitors, lambda value: value.isoformat(), lambda value: value.strftime("%b %d").replace(" 0", " ")),
        "monthly": series(monthly_buckets, monthly_visitors, lambda value: month_label(value), lambda value: month_label(value)),
        "annually": series(annual_buckets, annual_visitors, lambda value: str(value), lambda value: str(value)),
    }


def _club_matches_removed_club(club_id: str, club_name: str, removed_club: dict[str, Any]) -> bool:
    removed_names = {
        str(value or "").strip().lower()
        for value in [removed_club.get("id"), removed_club.get("name"), removed_club.get("short_name"), *(removed_club.get("aliases") or [])]
        if str(value or "").strip()
    }
    candidate_id = str(club_id or "").strip().lower()
    candidate_name = str(club_name or "").strip().lower()
    return any(candidate and candidate in removed_names for candidate in [candidate_id, candidate_name])


def _prune_member_references(
    store: dict[str, Any],
    member_id: str,
    member_name: str,
    club: dict[str, Any] | None = None,
) -> None:
    removed_member_id = str(member_id or "").strip()
    removed_member_name = str(member_name or "").strip()
    if not removed_member_id and not removed_member_name:
        return
    viewer_profile = dict(store.get("viewer_profile", {}))
    followed = [
        name
        for name in viewer_profile.get("followed_player_names", []) or []
        if str(name or "").strip() != removed_member_name
    ]
    viewer_profile["followed_player_names"] = followed
    store["viewer_profile"] = viewer_profile

    for fixture in store.get("fixtures", []):
        if club and str(fixture.get("club_id") or "").strip() != str(club.get("id") or "").strip():
            continue
        statuses = fixture.get("availability_statuses", {})
        notes = fixture.get("availability_notes", {})
        if removed_member_name in statuses:
            statuses.pop(removed_member_name, None)
        if removed_member_name in notes:
            notes.pop(removed_member_name, None)
        selected_xi = [
            name
            for name in fixture.get("selected_playing_xi", []) or []
            if str(name or "").strip() != removed_member_name
        ]
        fixture["selected_playing_xi"] = selected_xi
        selected_ids = [
            player_id
            for player_id in fixture.get("selected_playing_xi_member_ids", []) or []
            if str(player_id or "").strip() != removed_member_id
        ]
        fixture["selected_playing_xi_member_ids"] = selected_ids
        fixture["performances"] = [
            performance
            for performance in fixture.get("performances", [])
            if str(performance.get("player_name") or "").strip() != removed_member_name
        ]
        if str(fixture.get("heartlake_captain") or "").strip() == removed_member_name:
            fixture["heartlake_captain"] = ""

    for archive in store.get("archive_uploads", []):
        if club and not archive_belongs_to_club(archive, club, store.get("clubs", []), store.get("members", []), store.get("fixtures", [])):
            continue
        archive["suggested_performances"] = [
            performance
            for performance in archive.get("suggested_performances", [])
            if str(performance.get("player_name") or "").strip() != removed_member_name
        ]


def _unlink_member_from_auth(member_id: str) -> None:
    clean_member_id = str(member_id or "").strip()
    if not clean_member_id:
        return
    with _auth_connection() as connection:
        user_ids = [
            int(row["id"])
            for row in connection.execute(
                "SELECT id FROM app_users WHERE member_id = ?",
                (clean_member_id,),
            ).fetchall()
        ]
        connection.execute(
            "UPDATE app_users SET member_id = NULL WHERE member_id = ?",
            (clean_member_id,),
        )
        if user_ids:
            connection.executemany(
                "DELETE FROM app_player_season_availability WHERE user_id = ?",
                [(user_id,) for user_id in user_ids],
            )


def _unlink_member_from_club_auth(member_id: str, club_id: str, fallback_primary_club_id: str = "") -> None:
    clean_member_id = str(member_id or "").strip()
    clean_club_id = str(club_id or "").strip()
    if not clean_member_id or not clean_club_id:
        return
    with _auth_connection() as connection:
        user_rows = connection.execute(
            "SELECT id, primary_club_id FROM app_users WHERE member_id = ?",
            (clean_member_id,),
        ).fetchall()
        user_ids = [int(row["id"]) for row in user_rows]
        connection.execute(
            "DELETE FROM app_user_club_roles WHERE club_id = ? AND user_id IN ({})".format(",".join("?" for _ in user_ids)) if user_ids else "DELETE FROM app_user_club_roles WHERE club_id = ?",
            (clean_club_id, *user_ids) if user_ids else (clean_club_id,),
        )
        connection.execute(
            "DELETE FROM app_player_season_availability WHERE club_id = ? AND user_id IN ({})".format(",".join("?" for _ in user_ids)) if user_ids else "DELETE FROM app_player_season_availability WHERE club_id = ?",
            (clean_club_id, *user_ids) if user_ids else (clean_club_id,),
        )
        for row in user_rows:
            current_primary = str(row["primary_club_id"] or "").strip()
            if current_primary.lower() != clean_club_id.lower():
                continue
            replacement = str(fallback_primary_club_id or "").strip() or None
            connection.execute(
                "UPDATE app_users SET primary_club_id = ? WHERE id = ?",
                (replacement, int(row["id"])),
            )
        if user_ids and fallback_primary_club_id:
            connection.execute(
                "UPDATE app_auth_sessions SET current_club_id = ? WHERE user_id IN ({}) AND current_club_id = ?".format(",".join("?" for _ in user_ids)),
                (fallback_primary_club_id, *user_ids, clean_club_id),
            )


def _retarget_club_links_after_deletion(removed_club_id: str, replacement_club_id: str = "") -> None:
    removed = str(removed_club_id or "").strip()
    if not removed:
        return
    replacement = str(replacement_club_id or "").strip() or None
    with _auth_connection() as connection:
        connection.execute(
            "DELETE FROM app_user_club_roles WHERE club_id = ?",
            (removed,),
        )
        connection.execute(
            "DELETE FROM app_player_season_availability WHERE club_id = ?",
            (removed,),
        )
        connection.execute(
            """
            UPDATE app_users
            SET primary_club_id = CASE WHEN primary_club_id = ? THEN ? ELSE primary_club_id END
            WHERE primary_club_id = ?
            """,
            (removed, replacement, removed),
        )
        connection.execute(
            """
            UPDATE app_auth_sessions
            SET current_club_id = CASE WHEN current_club_id = ? THEN ? ELSE current_club_id END
            WHERE current_club_id = ?
            """,
            (removed, replacement, removed),
        )
        connection.execute(
            "UPDATE app_user_profile SET primary_club_id = ? WHERE id = 1",
            (replacement,),
        )


def _retarget_member_team_memberships(member: dict[str, Any], removed_club: dict[str, Any]) -> tuple[bool, str]:
    removed_team_names = {
        str(removed_club.get("id") or "").strip().lower(),
        str(removed_club.get("name") or "").strip().lower(),
        str(removed_club.get("short_name") or "").strip().lower(),
        *(str(alias or "").strip().lower() for alias in removed_club.get("aliases", []) or []),
    }
    updated_memberships: list[dict[str, Any]] = []
    for raw_membership in list(member.get("team_memberships", []) or []):
        if not isinstance(raw_membership, dict):
            continue
        club_id = str(raw_membership.get("club_id") or "").strip().lower()
        club_name = str(raw_membership.get("club_name") or "").strip().lower()
        team_name = str(raw_membership.get("team_name") or raw_membership.get("display_name") or "").strip().lower()
        if club_id in removed_team_names or club_name in removed_team_names or team_name in removed_team_names:
            continue
        updated_memberships.append(dict(raw_membership))
    member["team_memberships"] = updated_memberships
    if updated_memberships:
        primary = next((item for item in updated_memberships if item.get("is_primary")), updated_memberships[0])
        member["team_name"] = str(primary.get("team_name") or primary.get("display_name") or member.get("team_name") or "").strip()
        if "club_memberships" in member:
            member["club_memberships"] = [
                dict(club_membership)
                for club_membership in member.get("club_memberships", []) or []
                if not _club_matches_removed_club(
                    str(club_membership.get("club_id") or ""),
                    str(club_membership.get("club_name") or ""),
                    removed_club,
                )
            ]
            if not member["club_memberships"]:
                member.pop("club_memberships", None)
        return True, ""
    member["team_name"] = ""
    if "club_memberships" in member:
        member.pop("club_memberships", None)
    return False, str(member.get("name") or "").strip()


def _touch_fixture_audit(match: dict[str, Any], user_row: sqlite3.Row, created: bool = False) -> None:
    timestamp = now_iso()
    user_id = int(user_row["id"])
    if created and not match.get("created_by_user_id"):
        match["created_by_user_id"] = user_id
    if created and not match.get("created_at"):
        match["created_at"] = timestamp
    match["updated_by_user_id"] = user_id
    match["updated_at"] = timestamp


def _normalize_gender(value: str) -> str:
    gender = str(value or "").strip().lower()
    if gender in {"m", "male"}:
        return "Male"
    if gender in {"f", "female"}:
        return "Female"
    return ""


def _club_choices(store: dict[str, Any], include_disabled: bool = False) -> list[dict[str, Any]]:
    return [
        {
            "id": str(club.get("id") or ""),
            "name": str(club.get("name") or ""),
            "short_name": str(club.get("short_name") or ""),
            "city": str(club.get("city") or ""),
            "country": str(club.get("country") or ""),
            "season": str(club.get("season") or ""),
            "is_disabled": _club_is_disabled(club),
        }
        for club in store.get("clubs", [])
        if include_disabled or not _club_is_disabled(club)
    ]


def _sorted_club_choices(
    store: dict[str, Any], preferred_club_id: str = "", include_disabled: bool = False
) -> list[dict[str, Any]]:
    return sorted(
        _club_choices(store, include_disabled),
        key=lambda club: (
            0 if str(club.get("id") or "").strip() == str(preferred_club_id or "").strip() else 1,
            str(club.get("name") or ""),
        ),
    )


def _club_match_key(value: str) -> str:
    return normalize_name(value)


def _club_identity_keys(club: dict[str, Any]) -> set[str]:
    keys = {
        _club_match_key(club.get("id") or ""),
        _club_match_key(club.get("name") or ""),
        _club_match_key(club.get("short_name") or ""),
        *(_club_match_key(alias) for alias in club.get("aliases", []) or []),
    }
    return {key for key in keys if key}


def _find_club_by_name(store: dict[str, Any], club_name: str) -> dict[str, Any] | None:
    target = _club_match_key(club_name)
    if not target:
        return None
    return next((club for club in store.get("clubs", []) if target in _club_identity_keys(club)), None)


def _club_slug(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", normalize_name(name))
    slug = re.sub(r"-+", "-", slug).strip("-")
    return slug or "club"


def _create_club_record(
    store: dict[str, Any],
    name: str,
    city: str,
    country: str,
    *,
    about: str = "Created during registration",
) -> tuple[dict[str, Any], bool]:
    existing = _find_club_by_name(store, name)
    if existing:
        return existing, False
    base_slug = _club_slug(name)
    existing_ids = {str(club.get("id") or "").strip().lower() for club in store.get("clubs", [])}
    candidate = f"club-{base_slug}"
    suffix = 2
    while candidate.lower() in existing_ids:
        candidate = f"club-{base_slug}-{suffix}"
        suffix += 1
    club = {
        "id": candidate,
        "name": name.strip(),
        "short_name": name.strip(),
        "city": city.strip(),
        "country": country.strip(),
        "season": f"{datetime.utcnow().year} Season",
        "home_ground": "",
        "whatsapp_number": "",
        "about": about,
    }
    store.setdefault("clubs", []).append(club)
    save_store(store)
    return club, True


def _attach_creator_to_club(store: dict[str, Any], club: dict[str, Any], member: dict[str, Any]) -> None:
    club_id = str(club.get("id") or "").strip()
    club_name = str(club.get("name") or "").strip()
    club_short_name = str(club.get("short_name") or "").strip()
    team_name = club_short_name or club_name or club_id or "Club"
    if not club_id and not club_name:
        return

    teams = store.setdefault("teams", [])
    if not any(
        str(team.get("name") or "").strip().lower() == team_name.lower()
        or (club_id and str(team.get("club_id") or "").strip().lower() == club_id.lower())
        for team in teams
    ):
        teams.append(
            {
                "name": team_name,
                "type": "club",
                "display_name": club_name or team_name,
                "club_id": club_id,
                "club_name": club_name,
            }
        )

    memberships = list(member.get("team_memberships") or [])
    memberships = [
        raw
        for raw in memberships
        if not (
            isinstance(raw, dict)
            and (
                str(raw.get("club_id") or "").strip().lower() == club_id.lower()
                or str(raw.get("club_name") or "").strip().lower() == club_name.lower()
                or str(raw.get("team_name") or "").strip().lower() == team_name.lower()
            )
        )
    ]
    memberships.insert(
        0,
        {
            "team_name": team_name,
            "display_name": club_name or team_name,
            "club_id": club_id,
            "club_name": club_name,
            "team_type": "club",
            "is_primary": True,
        },
    )
    member["team_memberships"] = memberships
    member["team_name"] = team_name
    member["primary_club_id"] = club_id
    member["primary_club_name"] = club_name or team_name
    member["club_memberships"] = [
        {
            "club_id": club_id,
            "club_name": club_name,
            "teams": [team_name],
        }
    ]


def _primary_club_for_member(store: dict[str, Any], member: dict[str, Any]) -> dict[str, Any]:
    for membership in member.get("team_memberships", []) or []:
        if not isinstance(membership, dict):
            continue
        if membership.get("is_primary") and membership.get("club_id"):
            return _selected_club(store, str(membership.get("club_id") or ""))
    for membership in member.get("club_memberships", []):
        if membership.get("club_id"):
            return _selected_club(store, str(membership.get("club_id") or ""))
    return _selected_club(store, "")


def _match_scorebook(match: dict[str, Any]) -> dict[str, Any]:
    scorebook = match.get("scorebook")
    if not isinstance(scorebook, dict):
        scorebook = default_match_scorebook(match)
        match["scorebook"] = scorebook
    innings = scorebook.get("innings")
    if not isinstance(innings, list) or len(innings) < 2:
        scorebook = default_match_scorebook(match)
        match["scorebook"] = scorebook
    return match["scorebook"]


def _fixture_year(match: dict[str, Any]) -> str:
    return fixture_season_year(match)


def _archive_year(upload: dict[str, Any]) -> str:
    archive_year = str(upload.get("archive_year", "")).strip()
    if archive_year:
        return archive_year
    season = str(upload.get("season", "")).strip()
    match = re.search(r"(20\d{2})", season)
    return match.group(1) if match else ""


def _archive_matches_fixture_season(upload: dict[str, Any], match: dict[str, Any]) -> bool:
    archive_year = _archive_year(upload)
    fixture_year = _fixture_year(match)
    if archive_year and fixture_year and archive_year != fixture_year:
        return False
    return True


def file_sha256_from_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _string_value(value: Any) -> str:
    return str(value or "").strip()

def _extract_field(payload: dict[str, Any], *keys: str) -> str:
    containers = [payload]
    nested = payload.get("scorecard")
    if isinstance(nested, dict):
        containers.append(nested)
    for container in containers:
        for key in keys:
            value = container.get(key)
            if value not in (None, ""):
                return _string_value(value)
    return ""


def _parse_imported_player_scores(store: dict[str, Any], payload: dict[str, Any]) -> list[dict[str, Any]]:
    rows = payload.get("player_scores") or payload.get("performances") or []
    parsed: list[dict[str, Any]] = []
    if not isinstance(rows, list):
        return parsed
    for row in rows:
        if not isinstance(row, dict):
            continue
        raw_name = _string_value(row.get("name") or row.get("player_name"))
        if not raw_name:
            continue
        parsed.append(
            {
                "player_name": resolve_member_name(store, raw_name),
                "runs": int(row.get("runs", 0) or 0),
                "balls": int(row.get("balls", 0) or 0),
                "wickets": int(row.get("wickets", 0) or 0),
                "catches": int(row.get("catches", 0) or 0),
                "fours": int(row.get("fours", 0) or 0),
                "sixes": int(row.get("sixes", 0) or 0),
                "notes": _string_value(row.get("evidence") or row.get("notes") or "Imported from ChatGPT/manual extraction"),
                "source": "imported-review",
                "confidence": _string_value(row.get("confidence") or "imported"),
            }
        )
    return parsed


def _is_scorecard_template_payload(payload: Any) -> bool:
    return (
        isinstance(payload, dict)
        and isinstance(payload.get("meta"), dict)
        and isinstance(payload.get("match"), dict)
        and isinstance(payload.get("innings"), list)
        and isinstance(payload.get("validation"), dict)
    )


def _canonical_scorecard_template_payload(payload: dict[str, Any]) -> dict[str, Any] | None:
    template = payload if _is_scorecard_template_payload(payload) else payload.get("extraction_template")
    if not _is_scorecard_template_payload(template):
        return None
    return deepcopy(template)


def _scorecard_template_review_data(store: dict[str, Any], template: dict[str, Any]) -> tuple[dict[str, Any], list[dict[str, Any]], str]:
    meta = template.get("meta") if isinstance(template.get("meta"), dict) else {}
    match = template.get("match") if isinstance(template.get("match"), dict) else {}
    innings = template.get("innings") if isinstance(template.get("innings"), list) else []
    first_innings = innings[0] if len(innings) > 0 and isinstance(innings[0], dict) else {}
    second_innings = innings[1] if len(innings) > 1 and isinstance(innings[1], dict) else {}
    first_summary = first_innings.get("summary") if isinstance(first_innings.get("summary"), dict) else {}
    second_summary = second_innings.get("summary") if isinstance(second_innings.get("summary"), dict) else {}
    first_extras = first_innings.get("extras") if isinstance(first_innings.get("extras"), dict) else {}
    match_teams = match.get("teams") if isinstance(match.get("teams"), dict) else {}
    first_batting_team = _string_value(first_innings.get("batting_team") or match_teams.get("team_1"))
    first_bowling_team = _string_value(first_innings.get("bowling_team") or match_teams.get("team_2"))

    draft = default_scorecard("Imported from pasted extraction")
    draft["heartlake_runs"] = _string_value(first_summary.get("runs"))
    draft["heartlake_wickets"] = _string_value(first_summary.get("wickets"))
    draft["heartlake_overs"] = _string_value(first_summary.get("overs"))
    draft["opponent_runs"] = _string_value(second_summary.get("runs"))
    draft["opponent_wickets"] = _string_value(second_summary.get("wickets"))
    draft["opponent_overs"] = _string_value(second_summary.get("overs"))
    expected_result = _string_value((template.get("validation") or {}).get("expected_result"))
    if expected_result:
        draft["result"] = expected_result

    summary_bits = []
    if first_batting_team:
        summary_bits.append(f"Batting team: {first_batting_team}")
    if first_bowling_team:
        summary_bits.append(f"Bowling team: {first_bowling_team}")
    extras_total = _string_value(first_extras.get("total"))
    if extras_total:
        summary_bits.append(f"Extras: {extras_total}")
    if isinstance(first_innings.get("did_not_bat"), list) and first_innings.get("did_not_bat"):
        summary_bits.append(
            "Did not bat: "
            + ", ".join(_string_value(name) for name in first_innings.get("did_not_bat", []) if _string_value(name))
        )
    if expected_result:
        summary_bits.append(f"Expected result: {expected_result}")
    draft["live_summary"] = " | ".join(summary_bits)

    suggested: list[dict[str, Any]] = []
    for inning_index, inning in enumerate(innings[:2], start=1):
        if not isinstance(inning, dict):
            continue
        batting_rows = inning.get("batting") or []
        if not isinstance(batting_rows, list):
            continue
        for row in batting_rows:
            if not isinstance(row, dict):
                continue
            player = row.get("player") if isinstance(row.get("player"), dict) else {}
            raw_name = _string_value(
                player.get("name")
                or player.get("normalized_name")
                or row.get("name")
                or row.get("player_name")
            )
            if not raw_name:
                continue
            dismissal = row.get("dismissal") if isinstance(row.get("dismissal"), dict) else {}
            dismissal_bits = []
            if dismissal.get("type"):
                dismissal_bits.append(_string_value(dismissal.get("type")))
            if dismissal.get("fielder"):
                dismissal_bits.append(f"fielder: {_string_value(dismissal.get('fielder'))}")
            if dismissal.get("bowler"):
                dismissal_bits.append(f"bowler: {_string_value(dismissal.get('bowler'))}")
            suggested.append(
                {
                    "player_name": resolve_member_name(store, raw_name),
                    "runs": int(row.get("runs", 0) or 0),
                    "balls": int(row.get("balls", 0) or 0),
                    "wickets": int(row.get("wickets", 0) or 0),
                    "catches": int(row.get("catches", 0) or 0),
                    "fours": int(row.get("fours", 0) or 0),
                    "sixes": int(row.get("sixes", 0) or 0),
                    "notes": " | ".join(dismissal_bits) or "Imported from ChatGPT/manual extraction",
                    "source": "imported-review",
                    "confidence": "imported",
                    "inning_number": inning_index,
                }
            )

    extracted_summary = "Imported scorecard template"
    if first_batting_team or first_bowling_team:
        extracted_summary += f" for {first_batting_team or 'batting team'} vs {first_bowling_team or 'opponent'}"
    extracted_summary += f" with {len(suggested)} batting entries for review."
    return draft, suggested, extracted_summary


def _parse_team_names_from_summary(summary: str) -> tuple[str, str]:
    batting = ""
    bowling = ""
    text = str(summary or "")
    batting_match = re.search(r"Batting team:\s*([^|]+)", text, flags=re.IGNORECASE)
    bowling_match = re.search(r"Bowling team:\s*([^|]+)", text, flags=re.IGNORECASE)
    if batting_match:
        batting = batting_match.group(1).strip()
    if bowling_match:
        bowling = bowling_match.group(1).strip()
    return batting, bowling


def _enrich_scorecard_template_payload(
    template: dict[str, Any],
    *,
    draft: dict[str, Any] | None = None,
    archive: dict[str, Any] | None = None,
) -> dict[str, Any]:
    enriched = deepcopy(template)
    match = enriched.get("match") if isinstance(enriched.get("match"), dict) else {}
    teams = match.get("teams") if isinstance(match.get("teams"), dict) else {}
    innings = enriched.get("innings") if isinstance(enriched.get("innings"), list) else []
    first_innings = innings[0] if len(innings) > 0 and isinstance(innings[0], dict) else {}
    second_innings = innings[1] if len(innings) > 1 and isinstance(innings[1], dict) else {}
    summary_source = ""
    if isinstance(draft, dict):
        summary_source = str(draft.get("live_summary") or "")
    if not summary_source and isinstance(archive, dict):
        summary_source = str(archive.get("live_summary") or archive.get("extracted_summary") or "")
    parsed_batting_team, parsed_bowling_team = _parse_team_names_from_summary(summary_source)
    batting_team = _string_value(first_innings.get("batting_team") or teams.get("team_1") or parsed_batting_team)
    bowling_team = _string_value(first_innings.get("bowling_team") or teams.get("team_2") or parsed_bowling_team)
    if batting_team or bowling_team:
        teams["team_1"] = batting_team or teams.get("team_1") or None
        teams["team_2"] = bowling_team or teams.get("team_2") or None
        match["teams"] = teams
        first_innings["batting_team"] = batting_team or first_innings.get("batting_team") or None
        first_innings["bowling_team"] = bowling_team or first_innings.get("bowling_team") or None
        if second_innings:
            second_innings["batting_team"] = second_innings.get("batting_team") or bowling_team or None
            second_innings["bowling_team"] = second_innings.get("bowling_team") or batting_team or None
    if isinstance(archive, dict):
        match.setdefault("date", archive.get("archive_date") or archive.get("scorecard_date") or archive.get("photo_taken_at") or None)
        match.setdefault("match_id", archive.get("match_id") or None)
        match.setdefault("format", archive.get("match_format") or None)
        match.setdefault("venue", archive.get("venue") or None)
        match.setdefault("overs_limit", archive.get("overs_limit") or None)
    validation = enriched.get("validation") if isinstance(enriched.get("validation"), dict) else {}
    if draft:
        draft_result = _string_value(draft.get("result"))
        if draft_result and draft_result not in {
            "Imported from pasted extraction",
            "Imported from pasted extraction?",
            "Reviewed archive",
            "Imported from ChatGPT/manual extraction",
        }:
            validation.setdefault("expected_result", draft_result)
        validation.setdefault("inning_1_total", draft.get("heartlake_runs") or None)
        validation.setdefault("inning_2_total", draft.get("opponent_runs") or None)
    validation.setdefault("notes", "Template preserved for admin review.")
    enriched["match"] = match
    if innings:
        if len(innings) > 0:
            innings[0] = first_innings
        if len(innings) > 1:
            innings[1] = second_innings
        enriched["innings"] = innings
    enriched["validation"] = validation
    return enriched


def _scorecard_template_from_review_payload(
    store: dict[str, Any],
    payload: dict[str, Any],
    draft: dict[str, Any],
    suggested: list[dict[str, Any]],
    raw_text: str,
    *,
    ocr_engine: str,
    ocr_pipeline: str,
    confidence: str,
    extracted_summary: str,
) -> dict[str, Any]:
    template = _canonical_scorecard_template_payload(payload)
    if template is None:
        template = scorecard_template_from_archive(
            {
                "draft_scorecard": draft,
                "suggested_performances": suggested,
                "ocr_engine": ocr_engine,
                "ocr_pipeline": ocr_pipeline,
                "confidence": confidence,
                "created_at": now_iso(),
                "ocr_processed_at": now_iso(),
            }
        )
    else:
        template = deepcopy(template)
    template = _enrich_scorecard_template_payload(template, draft=draft)
    if isinstance(template.get("meta"), dict):
        template["meta"].setdefault("source", ocr_engine or None)
        template["meta"].setdefault("processed_by", ocr_pipeline or None)
        template["meta"].setdefault("confidence", confidence or None)
        template["meta"].setdefault("status", "template")
        template["meta"].setdefault("created_at", None)
        template["meta"].setdefault("updated_at", None)
    return template


def _parse_match_json_payload(store: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any] | None:
    match_block = payload.get("match")
    if not isinstance(match_block, dict):
        return None
    innings = match_block.get("innings") or []
    if not isinstance(innings, list) or not innings:
        return None

    first_innings = innings[0] if isinstance(innings[0], dict) else {}
    draft = default_scorecard("Imported from pasted extraction")
    draft["heartlake_runs"] = _string_value(first_innings.get("total_runs"))
    draft["heartlake_wickets"] = _string_value(first_innings.get("wickets"))
    draft["heartlake_overs"] = _string_value(first_innings.get("overs"))

    match_teams = match_block.get("teams") if isinstance(match_block.get("teams"), dict) else {}
    batting_team = _string_value(first_innings.get("batting_team") or match_teams.get("batting"))
    bowling_team = _string_value(match_teams.get("bowling"))
    extras = first_innings.get("extras") if isinstance(first_innings.get("extras"), dict) else {}
    extras_total = _string_value(extras.get("total"))
    did_not_bat = first_innings.get("did_not_bat") if isinstance(first_innings.get("did_not_bat"), list) else []
    summary_bits = []
    if batting_team:
        summary_bits.append(f"Batting team: {batting_team}")
    if bowling_team:
        summary_bits.append(f"Bowling team: {bowling_team}")
    if extras_total:
        summary_bits.append(f"Extras: {extras_total}")
    if did_not_bat:
        summary_bits.append("Did not bat: " + ", ".join(_string_value(name) for name in did_not_bat if _string_value(name)))
    draft["live_summary"] = " | ".join(summary_bits)

    player_scores: list[dict[str, Any]] = []
    batting_rows = first_innings.get("batting") or []
    if isinstance(batting_rows, list):
        for row in batting_rows:
            if not isinstance(row, dict):
                continue
            raw_name = _string_value(row.get("name"))
            if not raw_name:
                continue
            dismissal = row.get("dismissal") if isinstance(row.get("dismissal"), dict) else {}
            dismissal_bits = []
            if dismissal.get("type"):
                dismissal_bits.append(_string_value(dismissal.get("type")))
            if dismissal.get("bowler"):
                dismissal_bits.append(f"bowler: {_string_value(dismissal.get('bowler'))}")
            player_scores.append(
                {
                    "player_name": resolve_member_name(store, raw_name),
                    "runs": int(row.get("runs", 0) or 0),
                    "balls": int(row.get("balls", 0) or 0),
                    "wickets": 0,
                    "catches": 0,
                    "fours": int(row.get("fours", 0) or 0),
                    "sixes": int(row.get("sixes", 0) or 0),
                    "notes": " | ".join(dismissal_bits) or "Imported from ChatGPT/manual extraction",
                    "source": "imported-review",
                    "confidence": "imported",
                }
            )

    extracted_summary = "Imported nested match JSON"
    if batting_team or bowling_team:
        extracted_summary += f" for {batting_team or 'batting team'} vs {bowling_team or 'opponent'}"
    extracted_summary += f" with {len(player_scores)} batting entries for review."

    return {
        "draft_scorecard": draft,
        "suggested_performances": player_scores,
        "extraction_template": _scorecard_template_from_review_payload(
            store,
            payload,
            draft,
            player_scores,
            json.dumps(payload, indent=2)[:12000],
            ocr_engine="manual-import",
            ocr_pipeline="Imported from ChatGPT/manual extraction",
            confidence="Imported review",
            extracted_summary=extracted_summary,
        ),
        "raw_extracted_text": json.dumps(payload, indent=2)[:12000],
        "ocr_engine": "manual-import",
        "ocr_pipeline": "Imported from ChatGPT/manual extraction",
        "confidence": "Imported review",
        "extracted_summary": extracted_summary,
    }


def _parse_innings_root_json_payload(store: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any] | None:
    innings = payload.get("innings")
    if not isinstance(innings, list) or not innings:
        return None

    first_innings = innings[0] if isinstance(innings[0], dict) else {}
    if not first_innings:
        return None

    second_innings = innings[1] if len(innings) > 1 and isinstance(innings[1], dict) else {}
    info = payload.get("info") if isinstance(payload.get("info"), dict) else {}
    summary = first_innings.get("summary") if isinstance(first_innings.get("summary"), dict) else {}
    second_summary = second_innings.get("summary") if isinstance(second_innings.get("summary"), dict) else {}
    extras = first_innings.get("extras") if isinstance(first_innings.get("extras"), dict) else {}

    draft = default_scorecard("Imported from pasted extraction")
    draft["heartlake_runs"] = _string_value(summary.get("runs"))
    draft["heartlake_wickets"] = _string_value(summary.get("wickets"))
    draft["heartlake_overs"] = _string_value(summary.get("overs"))
    draft["opponent_runs"] = _string_value(second_summary.get("runs"))
    draft["opponent_wickets"] = _string_value(second_summary.get("wickets"))
    draft["opponent_overs"] = _string_value(second_summary.get("overs"))

    batting_team = _string_value(first_innings.get("batting_team"))
    bowling_team = _string_value(first_innings.get("bowling_team"))
    extras_total = _string_value(extras.get("total"))
    outcome = info.get("outcome") if isinstance(info.get("outcome"), dict) else {}
    result = _string_value(outcome.get("result"))
    if result and result.lower() != "unknown":
        draft["result"] = result
    did_not_bat = first_innings.get("did_not_bat") if isinstance(first_innings.get("did_not_bat"), list) else []
    summary_bits = []
    if batting_team:
        summary_bits.append(f"Batting team: {batting_team}")
    if bowling_team:
        summary_bits.append(f"Bowling team: {bowling_team}")
    if extras_total:
        summary_bits.append(f"Extras: {extras_total}")
    if did_not_bat:
        summary_bits.append("Did not bat: " + ", ".join(_string_value(name) for name in did_not_bat if _string_value(name)))
    draft["live_summary"] = " | ".join(summary_bits)

    player_scores: list[dict[str, Any]] = []
    batting_rows = first_innings.get("batting") or []
    if isinstance(batting_rows, list):
        for row in batting_rows:
            if not isinstance(row, dict):
                continue
            raw_name = _string_value(row.get("name"))
            if not raw_name:
                continue
            dismissal = row.get("dismissal") if isinstance(row.get("dismissal"), dict) else {}
            dismissal_bits = []
            if dismissal.get("type"):
                dismissal_bits.append(_string_value(dismissal.get("type")))
            if dismissal.get("fielder"):
                dismissal_bits.append(f"fielder: {_string_value(dismissal.get('fielder'))}")
            if dismissal.get("bowler"):
                dismissal_bits.append(f"bowler: {_string_value(dismissal.get('bowler'))}")
            player_scores.append(
                {
                    "player_name": resolve_member_name(store, raw_name),
                    "runs": int(row.get("runs", 0) or 0),
                    "balls": int(row.get("balls", 0) or 0),
                    "wickets": 0,
                    "catches": 0,
                    "fours": int(row.get("fours", 0) or 0),
                    "sixes": int(row.get("sixes", 0) or 0),
                    "notes": " | ".join(dismissal_bits) or "Imported from ChatGPT/manual extraction",
                    "source": "imported-review",
                    "confidence": "imported",
                }
            )

    extracted_summary = "Imported innings JSON"
    if batting_team or bowling_team:
        extracted_summary += f" for {batting_team or 'batting team'} vs {bowling_team or 'opponent'}"
    extracted_summary += f" with {len(player_scores)} batting entries for review."

    return {
        "draft_scorecard": draft,
        "suggested_performances": player_scores,
        "extraction_template": _scorecard_template_from_review_payload(
            store,
            payload,
            draft,
            player_scores,
            json.dumps(payload, indent=2)[:12000],
            ocr_engine="manual-import",
            ocr_pipeline="Imported from ChatGPT/manual extraction",
            confidence="Imported review",
            extracted_summary=extracted_summary,
        ),
        "raw_extracted_text": json.dumps(payload, indent=2)[:12000],
        "ocr_engine": "manual-import",
        "ocr_pipeline": "Imported from ChatGPT/manual extraction",
        "confidence": "Imported review",
        "extracted_summary": extracted_summary,
    }


def _parse_imported_text_fallback(store: dict[str, Any], text: str) -> dict[str, Any]:
    draft = default_scorecard("Imported from pasted extraction")
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    for line in lines:
        lowered = line.lower()
        score_match = re.search(r"(\d{1,3})\s*[/ -]\s*(\d{1,2})", line)
        if "heartlake" in lowered and score_match:
            draft["heartlake_runs"], draft["heartlake_wickets"] = score_match.groups()
        elif ("opponent" in lowered or "other team" in lowered or "away" in lowered) and score_match:
            draft["opponent_runs"], draft["opponent_wickets"] = score_match.groups()
        elif any(word in lowered for word in ["won", "lost", "tie", "draw"]):
            draft["result"] = line[:180]

    suggested: list[dict[str, Any]] = []
    for line in lines:
        match = re.search(r"([A-Za-z][A-Za-z .']{1,40})\s*[-:|]\s*(\d{1,3})(?:\s*(?:off|\()?\s*(\d{1,3}))?", line)
        if not match:
            continue
        raw_name = match.group(1).strip()
        if raw_name.lower() in {"heartlake", "opponent", "extras", "total"}:
            continue
        suggested.append(
            {
                "player_name": resolve_member_name(store, raw_name),
                "runs": int(match.group(2) or 0),
                "balls": int(match.group(3) or 0),
                "wickets": 0,
                "catches": 0,
                "fours": 0,
                "sixes": 0,
                "notes": f"Imported from pasted extraction line: {line[:140]}",
                "source": "imported-review",
                "confidence": "imported",
            }
        )
    return {"draft_scorecard": draft, "suggested_performances": suggested}


def parse_imported_extraction(store: dict[str, Any], text: str) -> dict[str, Any]:
    raw_text = text.strip()
    if not raw_text:
        raise HTTPException(status_code=400, detail="Paste the extracted scorecard text or JSON first.")

    try:
        payload = json.loads(raw_text)
    except json.JSONDecodeError:
        payload = None

    if isinstance(payload, dict):
        template_payload = _canonical_scorecard_template_payload(payload)
        if template_payload is not None:
            draft, suggested, extracted_summary = _scorecard_template_review_data(store, template_payload)
            return {
                "draft_scorecard": draft,
                "suggested_performances": suggested,
                "extraction_template": template_payload,
                "raw_extracted_text": raw_text[:12000],
                "ocr_engine": _string_value((template_payload.get("meta") or {}).get("source")) or "manual-import",
                "ocr_pipeline": _string_value((template_payload.get("meta") or {}).get("processed_by"))
                or "Imported from ChatGPT/manual extraction",
                "confidence": _string_value((template_payload.get("meta") or {}).get("confidence")) or "Imported review",
                "extracted_summary": extracted_summary,
            }
        nested_match_payload = _parse_match_json_payload(store, payload)
        if nested_match_payload is not None:
            return nested_match_payload
        innings_root_payload = _parse_innings_root_json_payload(store, payload)
        if innings_root_payload is not None:
            return innings_root_payload
        draft = default_scorecard(_extract_field(payload, "result") or "Imported from pasted extraction")
        draft.update(
            {
                "heartlake_runs": _extract_field(payload, "heartlake_runs"),
                "heartlake_wickets": _extract_field(payload, "heartlake_wickets"),
                "heartlake_overs": _extract_field(payload, "heartlake_overs"),
                "opponent_runs": _extract_field(payload, "opponent_runs"),
                "opponent_wickets": _extract_field(payload, "opponent_wickets"),
                "opponent_overs": _extract_field(payload, "opponent_overs"),
                "result": _extract_field(payload, "result") or "Imported from pasted extraction",
                "live_summary": _extract_field(payload, "live_summary", "summary"),
            }
        )
        suggested = _parse_imported_player_scores(store, payload)
        template = _scorecard_template_from_review_payload(
            store,
            payload,
            draft,
            suggested,
            raw_text,
            ocr_engine="manual-import",
            ocr_pipeline="Imported from ChatGPT/manual extraction",
            confidence="Imported review",
            extracted_summary=f"Imported pasted extraction with {len(suggested)} player score entries for review.",
        )
    else:
        fallback = _parse_imported_text_fallback(store, raw_text)
        draft = fallback["draft_scorecard"]
        suggested = fallback["suggested_performances"]
        template = _scorecard_template_from_review_payload(
            store,
            {},
            draft,
            suggested,
            raw_text,
            ocr_engine="manual-import",
            ocr_pipeline="Imported from ChatGPT/manual extraction",
            confidence="Imported review",
            extracted_summary=f"Imported pasted extraction with {len(suggested)} player score entries for review.",
        )

    return {
        "draft_scorecard": draft,
        "suggested_performances": suggested,
        "extraction_template": template,
        "raw_extracted_text": raw_text[:12000],
        "ocr_engine": "manual-import",
        "ocr_pipeline": "Imported from ChatGPT/manual extraction",
        "confidence": "Imported review",
        "extracted_summary": f"Imported pasted extraction with {len(suggested)} player score entries for review.",
    }


@app.get("/")
def root(request: Request) -> RedirectResponse:
    """Opening the app: signed in -> Home, signed out -> Live scores (with Sign in). README "First page"."""
    token = _auth_token_from_request(request)
    if token:
        try:
            _auth_user_from_token(token, touch=False)
            return RedirectResponse(url="/dashboard", status_code=303)
        except HTTPException:
            pass
    return RedirectResponse(url="/live", status_code=303)


@app.on_event("startup")
def startup_tasks() -> None:
    ensure_auth_schema()
    _refresh_player_stats_once()
    # Nov 5 2026: clubs from played games are registered BEFORE the first request. Doing it in a background thread
    # could save an older copy of the data over a change a request had just saved.
    try:
        _register_played_fixture_teams(load_store())  # saves by itself when it adds anything
    except Exception:
        logger.exception("Registering clubs from played games failed")
    # Fixtures take the result of their published scorecard (backfill for scorecards approved before this).
    try:
        startup_store = load_store()
        if _sync_fixture_results_from_scorecards(startup_store):
            save_store(startup_store)
    except Exception:
        logger.exception("Syncing fixture results from scorecards failed")
    threading.Thread(target=_backup_loop, name="database-backups", daemon=True).start()
    threading.Thread(target=_reminder_loop, name="match-reminders", daemon=True).start()


_REGISTER_LOCK = threading.Lock()


def _register_played_teams_in_background() -> None:
    """Nov 3 2026 (Amit: "I see only my primary club, not Coca Cola or Amit CC where I have played"): make sure
    every club and player from played games (scored fixtures and published scorecards) is registered, and each
    player is a member of the clubs they played for, so those clubs show on the Clubs / switch club page."""

    if not _REGISTER_LOCK.acquire(blocking=False):
        return  # one run at a time

    def _work() -> None:
        try:
            store = load_store()
            if _register_played_fixture_teams(store):
                save_store(store)
                logger.info("Registered clubs and players from played games.")
        except Exception:
            logger.exception("Registering clubs from played games failed")
        finally:
            _REGISTER_LOCK.release()

    threading.Thread(target=_work, name="register-played-teams", daemon=True).start()


STATS_REFRESH_VERSION = "one-club-per-match-3"  # Nov 7 2026: club-wise stats = one club per match


def _refresh_player_stats_once() -> None:
    """Rebuild the saved player stats once after a stats formula change (runs in the background)."""
    marker = Path(__file__).resolve().parent / "data" / ".stats_version"
    try:
        if marker.exists() and marker.read_text(encoding="utf-8").strip() == STATS_REFRESH_VERSION:
            return
    except OSError:
        return

    def _work() -> None:
        try:
            logger.info("Refreshing saved player stats (%s)...", STATS_REFRESH_VERSION)
            save_store(load_store())
            marker.parent.mkdir(parents=True, exist_ok=True)
            marker.write_text(STATS_REFRESH_VERSION, encoding="utf-8")
            logger.info("Player stats refreshed.")
        except Exception:
            logger.exception("Player stats refresh failed; it will be retried on next start.")

    threading.Thread(target=_work, name="stats-refresh", daemon=True).start()


@app.get("/signin")
def signin_page() -> HTMLResponse:
    logger.debug("Signin page requested.")
    html_text = (STATIC_DIR / "signin.html").read_text(encoding="utf-8")
    try:
        stats = public_signin_stats()
    except Exception:
        logger.exception("Signin stats preload failed.")
        stats = {"batting_leaders": [], "bowling_leaders": [], "club_leaders": []}

    def _render_batting_rows(rows: list[dict[str, Any]]) -> str:
        if not rows:
            return '<div class="signin-empty">No batting leaders yet.</div>'
        return "".join(
            f"""
            <div class="signin-leader-row">
              <span class="signin-rank">{index}</span>
              <div class="signin-leader-copy">
                <strong>{html.escape(str(row.get('player_name') or 'Player'))}</strong>
                <small>{int(row.get('runs') or 0)} runs · {float(row.get('batting_average') or 0.0):.1f} avg · {int(row.get('matches') or 0)} matches</small>
              </div>
            </div>
            """
            for index, row in enumerate(rows, start=1)
        )

    def _render_bowling_rows(rows: list[dict[str, Any]]) -> str:
        if not rows:
            return '<div class="signin-empty">No bowling leaders yet.</div>'
        return "".join(
            f"""
            <div class="signin-leader-row">
              <span class="signin-rank">{index}</span>
              <div class="signin-leader-copy">
                <strong>{html.escape(str(row.get('player_name') or 'Player'))}</strong>
                <small>{int(row.get('wickets') or 0)} wickets · {float(row.get('wickets_per_match') or 0.0):.1f} wickets/match · {int(row.get('matches') or 0)} matches</small>
              </div>
            </div>
            """
            for index, row in enumerate(rows, start=1)
        )

    def _render_club_rows(rows: list[dict[str, Any]]) -> str:
        if not rows:
            return '<div class="signin-empty">No club results yet.</div>'
        return "".join(
            f"""
            <div class="signin-club-row">
              <div class="signin-club-head">
                <span class="signin-rank">{index}</span>
                <div class="signin-leader-copy">
                  <strong>{html.escape(str(row.get('club_name') or 'Club'))}</strong>
                  <small>{int(row.get('matches_won') or 0)} won · {int(row.get('matches_played') or 0)} played</small>
                </div>
              </div>
              <span class="signin-widget-pill">{int(round(float(row.get('win_rate') or 0) * 100))}%</span>
            </div>
            """
            for index, row in enumerate(rows, start=1)
        )

    batting_rows = list(stats.get("batting_leaders", []))
    bowling_rows = list(stats.get("bowling_leaders", []))
    club_rows = list(stats.get("club_leaders", []))

    replacements = {
        '<span id="signinBatsmenCount" class="signin-widget-pill">Loading</span>': f'<span id="signinBatsmenCount" class="signin-widget-pill">{len(batting_rows)} shown</span>',
        '<span id="signinBowlersCount" class="signin-widget-pill">Loading</span>': f'<span id="signinBowlersCount" class="signin-widget-pill">{len(bowling_rows)} shown</span>',
        '<span id="signinClubsCount" class="signin-widget-pill">Loading</span>': f'<span id="signinClubsCount" class="signin-widget-pill">{len(club_rows)} shown</span>',
        '<div id="signinTopBatsmen" class="signin-leader-list" aria-live="polite"></div>': f'<div id="signinTopBatsmen" class="signin-leader-list" aria-live="polite">{_render_batting_rows(batting_rows)}</div>',
        '<div id="signinTopBowlers" class="signin-leader-list" aria-live="polite"></div>': f'<div id="signinTopBowlers" class="signin-leader-list" aria-live="polite">{_render_bowling_rows(bowling_rows)}</div>',
        '<div id="signinTopClubs" class="signin-club-list" aria-live="polite"></div>': f'<div id="signinTopClubs" class="signin-club-list" aria-live="polite">{_render_club_rows(club_rows)}</div>',
    }
    for needle, replacement in replacements.items():
        html_text = html_text.replace(needle, replacement)

    return HTMLResponse(
        content=html_text,
        headers={
            "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
            "Pragma": "no-cache",
        },
    )


def _parse_public_fixture_date(value: Any) -> date | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return date.fromisoformat(text[:10])
    except Exception:
        return None


def _public_fixture_group_label(fixture: dict[str, Any]) -> str:
    details = fixture.get("details") or {}
    candidates = [
        fixture.get("group"),
        fixture.get("league"),
        fixture.get("division"),
        details.get("group"),
        details.get("league"),
        details.get("division"),
        details.get("match_type"),
        fixture.get("season"),
    ]
    for candidate in candidates:
        text = str(candidate or "").strip()
        if text:
            return text
    return "Upcoming"


def _public_fixture_recent_balls(fixture: dict[str, Any], limit: int = 6) -> list[str]:
    balls: list[str] = []
    innings_list = (fixture.get("scorebook", {}) or {}).get("innings", []) or []
    for innings in innings_list:
        for ball in innings.get("balls", []) or []:
            runs = str(ball.get("runs_bat") or 0)
            extras_type = str(ball.get("extras_type") or "none")
            wicket = bool(ball.get("wicket"))
            token = runs
            if wicket:
                token = "W"
            elif extras_type and extras_type != "none":
                token = "WD" if extras_type == "wide" else "NB" if extras_type == "no_ball" else extras_type[:2].upper()
            balls.append(token)
    return balls[-limit:]


def _fixture_has_recorded_score_data(fixture: dict[str, Any]) -> bool:
    scorecard = fixture.get("scorecard") or {}
    score_values = (
        scorecard.get("heartlake_runs"),
        scorecard.get("heartlake_wickets"),
        scorecard.get("opponent_runs"),
        scorecard.get("opponent_wickets"),
        fixture.get("heartlake_score"),
        fixture.get("opponent_score"),
    )
    if any(
        value is not None and str(value).strip().lower() not in {"", "-", "tbd"}
        for value in score_values
    ):
        return True
    result = str(scorecard.get("result") or fixture.get("result") or "").strip().lower()
    if result and result not in {"tbd", "to be determined", "pending", "not recorded"}:
        return True
    return _fixture_has_balls(fixture)


def _public_fixture_card(fixture: dict[str, Any]) -> dict[str, Any]:
    scorecard = dict(fixture.get("scorecard") or {})
    status = str(fixture.get("status") or "Scheduled").strip() or "Scheduled"
    date_text = str(fixture.get("date") or "").strip()
    parsed_date = _parse_public_fixture_date(date_text)
    today = date.today()
    day_diff = (parsed_date - today).days if parsed_date else None
    if day_diff == 0:
        day_label = "Today"
    elif day_diff == 1:
        day_label = "Tomorrow"
    elif day_diff is not None and 2 <= day_diff <= 6 and parsed_date and parsed_date.weekday() >= 5:
        day_label = "Weekend"
    else:
        day_label = "Upcoming"
    return {
        "id": str(fixture.get("id") or ""),
        "club_id": str(fixture.get("club_id") or ""),
        "club_name": str(fixture.get("club_name") or ""),
        "date": date_text,
        "date_label": str(fixture.get("date_label") or date_text or "Date TBD"),
        "day_label": day_label,
        "opponent": str(fixture.get("opponent") or "Opponent"),
        "venue": str((fixture.get("details") or {}).get("venue") or "Venue TBD"),
        "match_type": str((fixture.get("details") or {}).get("match_type") or "Friendly"),
        "scheduled_time": str((fixture.get("details") or {}).get("scheduled_time") or "Time TBD"),
        "overs": str((fixture.get("details") or {}).get("overs") or ""),
        "group_label": _public_fixture_group_label(fixture),
        "status": status,
        "status_key": status.lower(),
        "result": str(scorecard.get("result") or fixture.get("result") or "TBD"),
        "heartlake_score": _side_score_text(scorecard, "heartlake", fixture.get("heartlake_score")),
        "opponent_score": _side_score_text(scorecard, "opponent", fixture.get("opponent_score")),
        "live_summary": str(scorecard.get("live_summary") or ""),
        "commentary_count": len(fixture.get("commentary", []) or []),
        "performances_count": len(fixture.get("performances", []) or []),
        "availability_count": len(fixture.get("availability", []) or []),
        "selected_playing_xi": list(fixture.get("selected_playing_xi", []) or []),
        "recent_balls": _public_fixture_recent_balls(fixture),
    }


def _fill_results_from_uploaded_scorecards(store: dict[str, Any], cards: list[dict[str, Any]]) -> None:
    """Nov 5 2026 (home "Recent results": Heartlake vs Imran XI, 6 Sep, "Result not recorded" while the uploaded
    scorecard has Imran XI 219/8, Heartlake 125): a fixture with no result takes it from the published scorecard
    of the same game (same date, same two teams)."""
    pending = [
        card for card in cards
        if str(card.get("result") or "").strip().lower() in {"", "tbd", "club won", "to be determined", "not recorded"}
    ]
    if not pending:
        return
    uploads = []
    for archive in store.get("archive_uploads", []) or []:
        if not isinstance(archive, dict) or not _archive_scorecard_is_published(archive):
            continue
        try:
            uploads.append(_scorecard_from_archive(archive))
        except Exception:
            continue
    for card in pending:
        names = [card.get("club_name"), card.get("opponent")]
        match = next(
            (
                item for item in uploads
                if str(item.get("date") or "") == str(card.get("date") or "")
                and all(any(_same_team_name(name, team) for team in item.get("teams") or []) for name in names if name)
            ),
            None,
        )
        if not match:
            continue
        card["result"] = str(match.get("result") or card.get("result") or "")
        scores = {}
        for innings in match.get("innings") or []:
            score = str(innings.get("score") or "")
            if score.endswith("/10"):
                score = score[:-3]
            scores[str(innings.get("team") or "")] = score
        for key, name in (("heartlake_score", card.get("club_name")), ("opponent_score", card.get("opponent"))):
            if str(card.get(key) or "").strip() in {"", "0", "0/0"}:
                value = next((score for team, score in scores.items() if _same_team_name(name, team)), "")
                if value:
                    card[key] = value
        card["scorecard_url"] = f"/scorecards/{match.get('id')}"


def _split_innings_score(text: str) -> tuple[str, str]:
    match = re.match(r"\s*(\d+)\s*(?:/\s*(\d+))?", str(text or ""))
    return (match.group(1), match.group(2) or "") if match else ("", "")


def _side_score_text(scorecard: dict[str, Any], side: str, fallback: Any) -> str:
    """Nov 9 2026: every score is "runs/wickets" (all out is "154/10"), the same text on Home, fixtures, live and scorecards."""
    runs = str(scorecard.get(f"{side}_runs") or "").strip()
    if not runs:
        return str(fallback or "")
    wickets = str(scorecard.get(f"{side}_wickets") or "").strip()
    return f"{runs}/{wickets}" if wickets.isdigit() else runs


def _sync_fixture_results_from_scorecards(store: dict[str, Any]) -> bool:
    """Nov 9 2026 (/live/2026-08-23-carl was empty while /scorecards/a-fa879005 had the full scorecard): a past
    fixture linked to one published scorecard takes that game's result and innings scores, so the live page,
    Recent results and fixtures show the same thing. Fixtures that already have scores (scored in the app) are kept."""
    fixtures = [fixture for fixture in store.get("fixtures", []) or [] if isinstance(fixture, dict)]
    if not fixtures:
        return False
    links = _past_fixture_scorecard_urls(store, [_public_fixture_card_payload(fixture) for fixture in fixtures])
    if not links:
        return False
    archives = {str(item.get("id") or ""): item for item in store.get("archive_uploads", []) or [] if isinstance(item, dict)}
    changed = False
    for fixture in fixtures:
        url = links.get(str(fixture.get("id") or ""), "")
        archive = archives.get(url.rsplit("/a-", 1)[-1]) if url else None
        if not archive or not _archive_scorecard_is_published(archive):
            continue
        view = _public_fixture_card_payload(fixture)
        if _fixture_has_recorded_score_data(view):
            continue
        card = _scorecard_from_archive(archive)
        innings = [item for item in card.get("innings") or [] if isinstance(item, dict)]
        ours = next((item for item in innings if _same_team_name(view["club_name"], item.get("team"))), None)
        theirs = next((item for item in innings if _same_team_name(view["opponent"], item.get("team"))), None)
        if not ours or not theirs:
            continue
        ours_runs, ours_wickets = _split_innings_score(ours.get("score"))
        theirs_runs, theirs_wickets = _split_innings_score(theirs.get("score"))
        result = str(card.get("result") or "").strip()
        if not ours_runs or not theirs_runs or not result or result.upper() == "TBD":
            continue
        scorecard = dict(fixture.get("scorecard") or {})
        scorecard.update(
            {
                "heartlake_runs": ours_runs,
                "heartlake_wickets": ours_wickets,
                "opponent_runs": theirs_runs,
                "opponent_wickets": theirs_wickets,
                "result": result,
            }
        )
        fixture["scorecard"] = scorecard
        fixture["heartlake_score"] = f"{ours_runs}/{ours_wickets}" if ours_wickets else ours_runs
        fixture["opponent_score"] = f"{theirs_runs}/{theirs_wickets}" if theirs_wickets else theirs_runs
        fixture["status"] = "Completed"
        changed = True
    return changed


def _public_live_page_payload(store: dict[str, Any]) -> dict[str, Any]:
    live_matches = [_public_fixture_card(match) for match in _public_live_matches(store)]
    live_match_ids = {item["id"] for item in live_matches}
    today = date.today()
    upcoming_candidates: list[dict[str, Any]] = []
    recent_results: list[dict[str, Any]] = []
    for fixture in list(store.get("fixtures", []) or []):
        card = _public_fixture_card(fixture)
        if card["id"] in live_match_ids:
            continue
        parsed_date = _parse_public_fixture_date(card.get("date"))
        status_key = card.get("status_key") or ""
        if status_key == "completed" or (
            parsed_date and parsed_date < today and _fixture_has_recorded_score_data(fixture)
        ):
            recent_results.append(card)
            continue
        if parsed_date and parsed_date < today:
            continue
        upcoming_candidates.append(card)
    upcoming_candidates.sort(
        key=lambda item: (
            str(item.get("date") or ""),
            str(item.get("scheduled_time") or ""),
            str(item.get("club_name") or ""),
        )
    )
    recent_results.sort(key=lambda item: str(item.get("date") or ""), reverse=True)
    _fill_results_from_uploaded_scorecards(store, recent_results)
    grouped_upcoming: list[dict[str, Any]] = []
    group_map: dict[str, list[dict[str, Any]]] = {}
    for item in upcoming_candidates:
        bucket = str(item.get("day_label") or "Upcoming")
        group = str(item.get("group_label") or "Upcoming")
        key = f"{bucket}::{group}"
        group_map.setdefault(key, []).append(item)
    for key in sorted(group_map.keys(), key=lambda value: value.split("::", 1)):
        bucket, group = key.split("::", 1)
        grouped_upcoming.append({"bucket": bucket, "group": group, "matches": group_map[key]})
    return {
        "hero": live_matches[0] if live_matches else (upcoming_candidates[0] if upcoming_candidates else {}),
        "live_matches": live_matches,
        "upcoming_groups": grouped_upcoming[:8],
        "recent_results": recent_results[:8],
        "generated_at": now_iso(),
    }


_SIGNIN_STATS_CACHE: tuple[str, dict[str, Any]] | None = None


@app.get("/api/public/signin-stats")
def public_signin_stats() -> dict[str, Any]:
    # Leaders only change when the store changes, so they are cached against the store's signature.
    global _SIGNIN_STATS_CACHE
    store = load_store()
    signature = str(store.get("_cache_signature") or "")
    cached = _SIGNIN_STATS_CACHE
    if signature and cached is not None and cached[0] == signature:
        return deepcopy(cached[1])
    stats = _build_public_signin_stats(store)
    if signature:
        _SIGNIN_STATS_CACHE = (signature, deepcopy(stats))
    return stats


def _build_public_signin_stats(store: dict[str, Any]) -> dict[str, Any]:
    logger.debug("Public signin stats requested.")
    members = list(store.get("members", []))
    fixtures = list(store.get("fixtures", []))
    archives = canonical_archive_uploads(store.get("archive_uploads", []))
    combined_player_stats = build_combined_player_stats(fixtures, archives, members)

    batting_leaders = [
        {
            "player_name": row.get("player_name", ""),
            "runs": int(row.get("runs") or 0),
            "batting_average": float(row.get("batting_average") or 0.0),
            "matches": int(row.get("matches") or 0),
        }
        for row in build_batting_rankings(combined_player_stats)[:5]
    ]
    bowling_leaders = [
        {
            "player_name": row.get("player_name", ""),
            "wickets": int(row.get("wickets") or 0),
            "wickets_per_match": float(row.get("wickets_per_match") or 0.0),
            "matches": int(row.get("matches") or 0),
        }
        for row in build_bowling_rankings(combined_player_stats)[:5]
    ]

    club_leaders = []
    for club in store.get("clubs", []) or []:
        club_store = scoped_store_for_club(store, club)
        summary = build_summary(club_store)
        matches_played = int(summary.get("matches_played") or 0)
        matches_won = int(summary.get("matches_won") or 0)
        matches_decided = int(summary.get("matches_decided") or 0)
        if matches_played <= 0 and matches_won <= 0:
            continue
        club_leaders.append(
            {
                "club_id": club.get("id", ""),
                "club_name": club.get("name", ""),
                "matches_played": matches_played,
                "matches_won": matches_won,
                "matches_lost": int(summary.get("matches_lost") or 0),
                "matches_decided": matches_decided,
                # Nov 7 2026: wins out of the matches whose result is known (one-innings cards have none)
                "win_rate": (matches_won / matches_decided) if matches_decided else 0.0,
            }
        )
    club_leaders.sort(
        key=lambda item: (
            -float(item.get("win_rate", 0) or 0),
            -int(item.get("matches_won", 0) or 0),
            -int(item.get("matches_played", 0) or 0),
            str(item.get("club_name") or ""),
        )
    )

    logger.info(
        "Public signin stats loaded. batting=%s bowling=%s clubs=%s",
        len(batting_leaders),
        len(bowling_leaders),
        len(club_leaders[:10]),
    )

    return {
        "batting_leaders": batting_leaders,
        "bowling_leaders": bowling_leaders,
        "club_leaders": club_leaders[:10],
        "generated_at": now_iso(),
    }


def _build_public_batting_chart_figure(player_labels: list[str], total_runs: list[int]):
    """Build the public batting-leaders chart with Plotly Graph Objects."""
    import plotly.graph_objects as go

    safe_labels = [str(label or "Player") for label in player_labels]
    safe_runs = [max(0, int(runs or 0)) for runs in total_runs]
    if len(safe_labels) != len(safe_runs):
        raise ValueError("Player labels and run totals must have matching lengths.")

    return go.Figure(
        data=[
            go.Bar(
                x=safe_labels,
                y=safe_runs,
                name="Runs",
                marker={"color": "#D32F2F", "line": {"color": "#9A1B1B", "width": 1}},
                hovertemplate="%{x}<br>%{y} runs<extra></extra>",
            )
        ],
        layout=go.Layout(
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            font={"family": "Roboto, Arial, sans-serif", "color": "#1A1A1A"},
            margin={"t": 12, "r": 12, "b": 72, "l": 48},
            xaxis={"tickangle": -25, "automargin": True, "showgrid": False, "zeroline": False},
            yaxis={
                "title": "Runs",
                "gridcolor": "#EAEAEA",
                "zeroline": False,
                "rangemode": "tozero",
            },
            showlegend=False,
        ),
    )


@app.get("/api/public/rankings-chart")
def public_rankings_chart() -> JSONResponse:
    stats = public_signin_stats()
    batting = stats.get("batting_leaders", [])
    figure = _build_public_batting_chart_figure(
        [str(row.get("player_name") or "Player") for row in batting],
        [int(row.get("runs") or 0) for row in batting],
    )
    return JSONResponse(content=json.loads(figure.to_json()))


def _public_live_matches(store: dict[str, Any]) -> list[dict[str, Any]]:
    today = _current_local_date().isoformat()
    live_statuses = {"live", "in progress", "ongoing"}
    matches: list[dict[str, Any]] = []
    for fixture in list(store.get("fixtures", []) or []) + _guest_fixtures(only_today=True):
        status = str(fixture.get("status") or "").strip()
        status_key = status.lower()
        fixture_date = str(fixture.get("date") or "").strip()
        if fixture_date != today and status_key not in live_statuses:
            continue
        if fixture_date[:10] < today:
            continue  # a game from an earlier day is not live any more
        if status_key == "completed":
            continue
        scorecard = dict(fixture.get("scorecard") or {})
        scorebook_innings = []
        for innings in (fixture.get("scorebook", {}) or {}).get("innings", []) or []:
            summary = summarize_innings_scorebook(innings)
            scorebook_innings.append(
                {
                    "inning_number": int(innings.get("inning_number") or 1),
                    "batting_team": str(innings.get("batting_team") or ""),
                    "bowling_team": str(innings.get("bowling_team") or ""),
                    "overs_limit": int(innings.get("overs_limit") or 20),
                    "status": str(innings.get("status") or "Not started"),
                    "target_runs": int(innings["target_runs"]) if innings.get("target_runs") is not None else None,
                    "summary": summary,
                    "batters": [
                        {
                            "player_name": str(item.get("player_name") or ""),
                            "runs": int(item.get("runs") or 0),
                            "balls": int(item.get("balls") or 0),
                            "fours": int(item.get("fours") or 0),
                            "sixes": int(item.get("sixes") or 0),
                            "status": str(item.get("status") or ""),
                            "strike_rate": float(item.get("strike_rate") or ((int(item.get("runs") or 0) / int(item.get("balls") or 0)) * 100 if int(item.get("balls") or 0) else 0.0)),
                        }
                        for item in summary.get("batting", [])
                    ],
                    "bowlers": [
                        {
                            "player_name": str(item.get("player_name") or ""),
                            "overs": str(item.get("overs") or "0.0"),
                            "runs_conceded": int(item.get("runs_conceded") or 0),
                            "wickets": int(item.get("wickets") or 0),
                            "economy": float(item.get("economy") or 0.0),
                        }
                        for item in summary.get("bowling", [])
                    ],
                    "balls": [
                        {
                            "id": str(ball.get("id") or ""),
                            "over_number": int(ball.get("over_number") or 1),
                            "ball_number": int(ball.get("ball_number") or 1),
                            "striker": str(ball.get("striker") or ""),
                            "non_striker": str(ball.get("non_striker") or ""),
                            "bowler": str(ball.get("bowler") or ""),
                            "runs_bat": int(ball.get("runs_bat") or 0),
                            "extras_type": str(ball.get("extras_type") or "none"),
                            "extras_runs": int(ball.get("extras_runs") or 0),
                            "wicket": bool(ball.get("wicket")),
                            "wicket_type": str(ball.get("wicket_type") or ""),
                            "wicket_player": str(ball.get("wicket_player") or ""),
                            "fielder": str(ball.get("fielder") or ""),
                            "commentary": str(ball.get("commentary") or ""),
                            "created_at": str(ball.get("created_at") or ""),
                        }
                        for ball in innings.get("balls", []) or []
                    ],
                }
            )
        matches.append(
            {
                "id": str(fixture.get("id") or ""),
                "club_id": str(fixture.get("club_id") or ""),
                "club_name": str(fixture.get("club_name") or ""),
                "date": fixture_date,
                "date_label": str(fixture.get("date_label") or fixture_date),
                "opponent": str(fixture.get("opponent") or "Opponent"),
                "venue": str((fixture.get("details") or {}).get("venue") or "Venue TBD"),
                "match_type": str((fixture.get("details") or {}).get("match_type") or "Friendly"),
                "scheduled_time": str((fixture.get("details") or {}).get("scheduled_time") or "Time TBD"),
                "overs": str((fixture.get("details") or {}).get("overs") or ""),
                "status": status or "Scheduled",
                "status_key": status_key or "scheduled",
                "result": str(scorecard.get("result") or fixture.get("result") or "TBD"),
                "heartlake_score": _side_score_text(scorecard, "heartlake", fixture.get("heartlake_score")),
                "opponent_score": _side_score_text(scorecard, "opponent", fixture.get("opponent_score")),
                "live_summary": str(scorecard.get("live_summary") or ""),
                "commentary_count": len(fixture.get("commentary", []) or []),
                "performances_count": len(fixture.get("performances", []) or []),
                "availability_count": len(fixture.get("availability", []) or []),
                "selected_playing_xi": list(fixture.get("selected_playing_xi", []) or []),
                "scorebook": {"innings": scorebook_innings},
            }
        )
    matches.sort(
        key=lambda item: (
            0 if str(item.get("status_key") or "") in live_statuses else 1,
            str(item.get("date") or ""),
            str(item.get("scheduled_time") or ""),
            str(item.get("opponent") or ""),
        )
    )
    return matches


def _published_scorecard_for_fixture(store: dict[str, Any], fixture: dict[str, Any]) -> dict[str, Any] | None:
    """A past fixture linked to a published scorecard shows that scorecard on its live page when it has no
    ball-by-ball scorebook, so the live page and /scorecards/a-... show the same numbers."""
    url = _past_fixture_scorecard_urls(store, [fixture]).get(str(fixture.get("id") or ""), "")
    card_id = url.rsplit("/", 1)[-1]
    if not card_id:
        return None
    return next((card for card in _public_scorecards(store) if card["id"] == card_id), None)


def _public_match_payload(store: dict[str, Any], match_id: str) -> dict[str, Any]:
    match = get_match_or_404(store, match_id)
    scorecard = dict(match.get("scorecard") or {})
    innings_payload = []
    for innings in (match.get("scorebook", {}) or {}).get("innings", []) or []:
        summary = summarize_innings_scorebook(innings)
        innings_payload.append(
            {
                "inning_number": int(innings.get("inning_number") or 1),
                "batting_team": str(innings.get("batting_team") or ""),
                "bowling_team": str(innings.get("bowling_team") or ""),
                "overs_limit": int(innings.get("overs_limit") or 20),
                "status": str(innings.get("status") or "Not started"),
                "target_runs": int(innings["target_runs"]) if innings.get("target_runs") is not None else None,
                "summary": summary,
                "batters": [
                    {
                        "player_name": str(item.get("player_name") or ""),
                        "runs": int(item.get("runs") or 0),
                        "balls": int(item.get("balls") or 0),
                        "fours": int(item.get("fours") or 0),
                        "sixes": int(item.get("sixes") or 0),
                        "status": str(item.get("status") or ""),
                        "strike_rate": float(item.get("strike_rate") or ((int(item.get("runs") or 0) / int(item.get("balls") or 0)) * 100 if int(item.get("balls") or 0) else 0.0)),
                    }
                    for item in summary.get("batting", [])
                ],
                "bowlers": [
                    {
                        "player_name": str(item.get("player_name") or ""),
                        "overs": str(item.get("overs") or "0.0"),
                        "runs_conceded": int(item.get("runs_conceded") or 0),
                        "wickets": int(item.get("wickets") or 0),
                        "economy": float(item.get("economy") or 0.0),
                    }
                    for item in summary.get("bowling", [])
                ],
                "balls": [
                    {
                        "id": str(ball.get("id") or ""),
                        "over_number": int(ball.get("over_number") or 1),
                        "ball_number": int(ball.get("ball_number") or 1),
                        "striker": str(ball.get("striker") or ""),
                        "non_striker": str(ball.get("non_striker") or ""),
                        "bowler": str(ball.get("bowler") or ""),
                        "runs_bat": int(ball.get("runs_bat") or 0),
                        "extras_type": str(ball.get("extras_type") or "none"),
                        "extras_runs": int(ball.get("extras_runs") or 0),
                        "wicket": bool(ball.get("wicket")),
                        "wicket_type": str(ball.get("wicket_type") or ""),
                        "wicket_player": str(ball.get("wicket_player") or ""),
                        "fielder": str(ball.get("fielder") or ""),
                        "commentary": str(ball.get("commentary") or ""),
                        "created_at": str(ball.get("created_at") or ""),
                    }
                    for ball in innings.get("balls", []) or []
                ],
            }
        )
    published = None
    if not any(item["balls"] for item in innings_payload):
        published = _published_scorecard_for_fixture(store, match)
    status_text = str(match.get("status") or "Scheduled")
    result_text = str(scorecard.get("result") or match.get("result") or "TBD")
    if published:
        status_text = "Completed"
        if result_text in ("", "TBD"):
            result_text = str(published.get("result") or "") or "Scorecard published"
    return {
        "id": str(match.get("id") or ""),
        "published_scorecard": published,
        # same Match ID as the /scorecards page for the linked card (e.g. M-FA879005)
        "published_match_code": _match_code(published.get("id")) if published else "",
        "club_id": str(match.get("club_id") or ""),
        "club_name": str(match.get("club_name") or ""),
        "date": str(match.get("date") or ""),
        "date_label": str(match.get("date_label") or match.get("date") or ""),
        "opponent": str(match.get("opponent") or "Opponent"),
        "venue": str((match.get("details") or {}).get("venue") or "Venue TBD"),
        "match_type": str((match.get("details") or {}).get("match_type") or "Friendly"),
        "scheduled_time": str((match.get("details") or {}).get("scheduled_time") or "Time TBD"),
        "overs": str((match.get("details") or {}).get("overs") or ""),
        "status": status_text,
        "result": result_text,
        "heartlake_score": _side_score_text(scorecard, "heartlake", match.get("heartlake_score")),
        "opponent_score": _side_score_text(scorecard, "opponent", match.get("opponent_score")),
        "live_summary": str(scorecard.get("live_summary") or ""),
        "selected_playing_xi": list(match.get("selected_playing_xi", []) or []),
        "availability": list(match.get("availability", []) or []),
        "commentary": list(match.get("commentary", []) or []),
        "performances": list(match.get("performances", []) or []),
        "scorecard": {
            "heartlake_runs": scorecard.get("heartlake_runs", "") or "",
            "heartlake_wickets": scorecard.get("heartlake_wickets", "") or "",
            "heartlake_overs": scorecard.get("heartlake_overs", "") or "",
            "opponent_runs": scorecard.get("opponent_runs", "") or "",
            "opponent_wickets": scorecard.get("opponent_wickets", "") or "",
            "opponent_overs": scorecard.get("opponent_overs", "") or "",
            "result": scorecard.get("result", match.get("result") or "TBD") or "TBD",
            "live_summary": scorecard.get("live_summary", "") or "",
        },
        "scorebook": {"innings": innings_payload},
    }


@app.get("/api/public/live-matches")
def public_live_matches() -> dict[str, Any]:
    logger.debug("Public live matches requested.")
    store = load_store()
    matches = _public_live_matches(store)
    return {
        "matches": matches,
        "generated_at": now_iso(),
    }


@app.get("/api/public/live-page")
def public_live_page() -> dict[str, Any]:
    logger.debug("Public live landing page requested.")
    store = load_store()
    return _public_live_page_payload(store)


@app.get("/api/public/fixtures-page")
def public_fixtures_page() -> dict[str, Any]:
    logger.debug("Public fixtures landing page requested.")
    store = load_store()
    return _public_fixtures_page_payload(store)


def _public_fixture_card_payload(fixture: dict[str, Any]) -> dict[str, Any]:
    details = dict(fixture.get("details") or {})
    scorecard = dict(fixture.get("scorecard") or {})
    date_value = str(fixture.get("date") or "")
    club_name = str(fixture.get("club_name") or "").strip() or "Club"
    return {
        "id": str(fixture.get("id") or ""),
        "club_id": str(fixture.get("club_id") or ""),
        "club_name": club_name,
        "club_short_name": str(fixture.get("club_short_name") or "").strip(),
        "date": date_value,
        "date_label": str(fixture.get("date_label") or date_value or "Date TBD"),
        "day_label": str(fixture.get("day_label") or ""),
        "opponent": str(fixture.get("opponent") or "Opponent"),
        "venue": str(details.get("venue") or "Venue TBD"),
        "match_type": str(details.get("match_type") or "Friendly"),
        "scheduled_time": str(details.get("scheduled_time") or "Time TBD"),
        "overs": str(details.get("overs") or ""),
        "status": str(fixture.get("status") or "Scheduled"),
        "status_key": str(fixture.get("status_key") or str(fixture.get("status") or "").lower().replace(" ", "-")),
        "result": str(scorecard.get("result") or fixture.get("result") or "TBD"),
        "heartlake_score": _side_score_text(scorecard, "heartlake", fixture.get("heartlake_score")),
        "opponent_score": _side_score_text(scorecard, "opponent", fixture.get("opponent_score")),
        "live_summary": str(scorecard.get("live_summary") or ""),
    }


def _past_fixture_scorecard_urls(store: dict[str, Any], fixtures: list[dict[str, Any]]) -> dict[str, str]:
    """Return only unambiguous links from past fixtures to approved archive scorecards."""
    today = datetime.utcnow().date().isoformat()
    approved_archives = [
        archive
        for archive in (store.get("archive_uploads", []) or [])
        if isinstance(archive, dict) and _scorecard_text(archive.get("status")).lower() == "approved"
    ]
    links: dict[str, str] = {}

    for fixture in fixtures:
        fixture_id = str(fixture.get("id") or "").strip()
        fixture_date = str(fixture.get("date") or "")[:10]
        club_id = str(fixture.get("club_id") or "").strip()
        if not fixture_id or not club_id or not re.fullmatch(r"20\d{2}-\d{2}-\d{2}", fixture_date) or fixture_date >= today:
            continue

        scoped_archives = []
        for archive in approved_archives:
            archive_club_ids = set(_coerce_archive_string_list(archive.get("club_ids")))
            archive_club_id = str(archive.get("club_id") or "").strip()
            if archive_club_id:
                archive_club_ids.add(archive_club_id)
            if club_id in archive_club_ids:
                scoped_archives.append(archive)

        # An explicit applied/upload match reference is authoritative, but remains club-scoped.
        direct = [
            archive
            for archive in scoped_archives
            if fixture_id
            in {
                str(archive.get("applied_to_match_id") or "").strip(),
                str(archive.get("match_id") or "").strip(),
            }
        ]
        if len(direct) == 1:
            links[fixture_id] = f"/scorecards/a-{_scorecard_text(direct[0].get('id'))}"
            continue
        if direct:
            continue

        fixture_opponent = normalize_name(str(fixture.get("opponent") or ""))
        fixture_club_name = normalize_name(str(fixture.get("club_name") or ""))
        matched = []
        for archive in scoped_archives:
            # Photo metadata may be the upload date, not the game date. Only use
            # scorecard-extracted or explicitly assigned archive dates for inference.
            date_source = str(archive.get("archive_date_source") or "").strip().lower()
            if date_source not in {"scorecard", "manual-season"}:
                continue
            card = _scorecard_from_archive(archive)
            if str(card.get("date") or "")[:10] != fixture_date:
                continue
            card_teams = [
                str(team.get("team") or "")
                for team in (card.get("innings") or [])
                if isinstance(team, dict) and team.get("team")
            ]
            # The scorecard must identify both sides (same team rule as the sync: "Coca Cola" = "Coca Cola XI"); never match on date/club alone.
            if (
                fixture_opponent
                and fixture_club_name
                and any(_same_team_name(fixture.get("club_name"), team) for team in card_teams)
                and any(_same_team_name(fixture.get("opponent"), team) for team in card_teams)
            ):
                matched.append(archive)

        # Ambiguous same-day fixtures deliberately remain unlinked.
        if len(matched) == 1:
            links[fixture_id] = f"/scorecards/a-{_scorecard_text(matched[0].get('id'))}"

    return links


def _public_fixtures_page_payload(store: dict[str, Any]) -> dict[str, Any]:
    fixtures = [_public_fixture_card_payload(fixture) for fixture in list(store.get("fixtures", []) or [])]
    scorecard_urls = _past_fixture_scorecard_urls(store, fixtures)
    for fixture in fixtures:
        fixture["scorecard_url"] = scorecard_urls.get(str(fixture.get("id") or ""), "")
        fixture["is_past"] = _fixture_is_past(fixture)
    _fill_results_from_uploaded_scorecards(store, fixtures)
    # Past games that were never played or scored are not "upcoming": hide them. Played games stay as results.
    fixtures = [
        fixture
        for fixture in fixtures
        if not fixture["is_past"]
        or str(fixture.get("status_key") or "") == "completed"
        or fixture.get("scorecard_url")
        or str(fixture.get("result") or "TBD").strip().upper() not in {"", "TBD"}
        or _fixture_has_recorded_score_data(fixture)
    ]
    fixtures.sort(
        key=lambda item: (
            str(item.get("date") or ""),
            str(item.get("club_name") or ""),
            str(item.get("scheduled_time") or ""),
            str(item.get("opponent") or ""),
        )
    )
    grouped: dict[str, list[dict[str, Any]]] = {}
    for fixture in fixtures:
        grouped.setdefault(str(fixture.get("club_name") or "Club"), []).append(fixture)
    club_groups = [
        {"club_name": club_name, "count": len(items), "fixtures": items}
        for club_name, items in grouped.items()
    ]
    club_groups.sort(key=lambda item: str(item.get("club_name") or ""))
    return {
        "hero": {
            "headline": "Fixtures across clubs",
            "summary": "Browse fixtures by club. Signed-in users see their own club fixtures.",
            "total_fixtures": len(fixtures),
            "club_count": len(club_groups),
            "upcoming_count": sum(1 for fixture in fixtures if str(fixture.get("status") or "").lower() != "completed" and not fixture.get("is_past")),
        },
        "fixtures": fixtures,
        "club_groups": club_groups,
        "generated_at": now_iso(),
    }


@app.get("/api/public/clubs")
def public_clubs() -> dict[str, Any]:
    """Read-only club directory for the public Clubs page (no player contact details)."""
    store = load_store()
    fixtures = list(store.get("fixtures", []) or [])
    today = datetime.utcnow().date().isoformat()
    clubs: list[dict[str, Any]] = []
    for club in _sorted_club_choices(store):
        club_id = str(club.get("id") or "")
        club_fixtures = [fixture for fixture in fixtures if str(fixture.get("club_id") or "") == club_id]
        upcoming = [
            fixture
            for fixture in club_fixtures
            if str(fixture.get("date") or "") >= today and str(fixture.get("status") or "").lower() != "completed"
        ]
        clubs.append({**club, "fixture_count": len(club_fixtures), "upcoming_count": len(upcoming)})
    return {"clubs": clubs, "generated_at": now_iso()}


@app.get("/api/public/search")
def public_search(q: str = "") -> dict[str, Any]:
    """Navbar search: players, clubs and matches. Public data only (no phone, email or age)."""
    query = normalize_name(q)
    empty = {"query": q, "players": [], "clubs": [], "matches": []}
    if len(query) < 2:
        return empty
    store = load_store()
    limit = 6

    def hit(*values: Any) -> bool:
        return any(query in normalize_name(str(value or "")) for value in values)

    stats_by_member = {
        str(row.get("member_id") or ""): row
        for row in store.get("member_summary_stats", []) or []
        if isinstance(row, dict)
    }
    players: list[dict[str, Any]] = []
    for member in store.get("members", []) or []:
        aliases = [alias for alias in (member.get("aliases") or []) if isinstance(alias, str)]
        if not hit(member.get("name"), member.get("full_name"), *aliases):
            continue
        stats = stats_by_member.get(str(member.get("id") or ""), {})
        club_names = [
            str(club.get("club_name") or "").strip()
            for club in (member.get("club_memberships") or [])
            if isinstance(club, dict) and str(club.get("club_name") or "").strip()
        ] or [str(member.get("primary_club_name") or "").strip()]
        players.append(
            {
                "id": str(member.get("id") or ""),
                "name": str(member.get("full_name") or member.get("name") or "Player"),
                "short_name": str(member.get("name") or ""),
                "clubs": [name for name in club_names if name],
                "matches": int(stats.get("matches") or 0),
                "runs": int(stats.get("runs") or 0),
                "wickets": int(stats.get("wickets") or 0),
            }
        )
        if len(players) >= limit:
            break

    clubs = [
        club
        for club in _sorted_club_choices(store)
        if hit(club.get("name"), club.get("short_name"), club.get("city"))
    ][:limit]

    matches: list[dict[str, Any]] = []
    fixtures = sorted(
        [fixture for fixture in store.get("fixtures", []) or [] if isinstance(fixture, dict)],
        key=lambda fixture: str(fixture.get("date") or ""),
        reverse=True,
    )
    for fixture in fixtures:
        details = fixture.get("details") if isinstance(fixture.get("details"), dict) else {}
        if not hit(fixture.get("club_name"), fixture.get("opponent"), details.get("venue"), fixture.get("date"), fixture.get("date_label")):
            continue
        matches.append(
            {
                "id": str(fixture.get("id") or ""),
                "title": f"{fixture.get('club_name') or 'Club'} vs {fixture.get('opponent') or 'Opponent'}",
                "date_label": str(fixture.get("date_label") or fixture.get("date") or ""),
                "status": str(fixture.get("status") or "Scheduled"),
                "score": " · ".join(
                    part for part in [str(fixture.get("heartlake_score") or ""), str(fixture.get("opponent_score") or "")] if part
                ),
            }
        )
        if len(matches) >= limit:
            break

    return {"query": q, "players": players, "clubs": clubs, "matches": matches}


# ---------------------------------------------------------------------------
# Public digital scorecards (Cricinfo-style), built from APPROVED archive uploads.
# Browsable by game date. Public data only: names and cricket figures.
# ---------------------------------------------------------------------------

_SCORECARD_JUNK_NAME = re.compile(r"scorecard|\bruns\b.*\bballs\b|^batter\b|^bowler\b|^total\b|^extras\b", re.IGNORECASE)
_SCORECARD_TEAM_NOTE = re.compile(r"team:\s*([^|]+)", re.IGNORECASE)
_SCORECARD_DISMISSAL_NOTE = re.compile(r"batting dismissal:\s*([a-z_ ]+)", re.IGNORECASE)
_SCORECARD_WICKETS_NOTE = re.compile(r"bowling wickets:\s*(\d+)", re.IGNORECASE)
_SCORECARD_FIELDER_NOTE = re.compile(r"fielder:\s*([^|]+)", re.IGNORECASE)
_SCORECARD_OCR_BOWLING = re.compile(r"archive line:.*?\s(\d{1,2}\.\d)\s+(\d{1,3})\s+(\d{1,2})\s*$", re.IGNORECASE)
_SCORECARD_OCR_BATTING = re.compile(r"archive line:.*?\s(\d{1,3})\s+(\d{1,3})\s+(\d{1,2})\s+(\d{1,2})\s*$", re.IGNORECASE)
_SCORECARD_WON_BY = re.compile(r"^(.+?)\s+won by\b", re.IGNORECASE)


def _scorecard_json(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str) and value.strip():
        try:
            parsed = json.loads(value)
        except (TypeError, ValueError):
            return {}
        return parsed if isinstance(parsed, dict) else {}
    return {}


def _scorecard_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(float(str(value).strip()))
    except (TypeError, ValueError):
        return None


def _scorecard_text(value: Any) -> str:
    return str(value or "").strip()


def _scorecard_summary_parts(live_summary: str) -> dict[str, str]:
    """Parse 'Batting team: X | Bowling team: Y | Venue: Z | ...' into a dict."""
    parts: dict[str, str] = {}
    for chunk in str(live_summary or "").split("|"):
        if ":" not in chunk:
            continue
        key, _, value = chunk.partition(":")
        key = key.strip().lower()
        if key and value.strip():
            parts[key] = value.strip()
    return parts


def _scorecard_clean_result(value: Any) -> str:
    text = _scorecard_text(value)
    text = re.sub(r"^result:\s*", "", text, flags=re.IGNORECASE)
    lowered = text.lower()
    if not text or lowered in {"tbd", "pending review"} or lowered.startswith("imported from") or "awaiting" in lowered:
        return ""
    return text


def _scorecard_dismissal(raw: Any, fielder: Any = "", bowler: Any = "") -> tuple[str, bool, bool]:
    """Return (dismissal text, is_not_out, did_not_bat)."""
    text = _scorecard_text(raw).lower().replace("_", " ")
    fielder = _scorecard_text(fielder)
    bowler = _scorecard_text(bowler)
    if not text:
        return ("", False, False)
    if "did not bat" in text or text == "dnb":
        return ("", False, True)
    if text.strip() in {"ro", "r.o", "r.o.", "r/o", "r o"}:
        # Short form "RO": the club rule decides (default retired out). README "Retired out (RO)".
        text = ai_vision.ro_meaning()
    if "not out" in text:
        return ("not out", True, False)
    if "retired" in text:
        # "Retired out" is a dismissal (Laws of Cricket 25.4.3); plain "retired" / "retired hurt" is not out.
        if re.search(r"retired\s*(out|oot)", text):
            return ("retired out", False, False)
        return ("retired", True, False)
    caught_and_bowled = bool(re.match(r"^(c|ct|caught)\s*(&|and|\+)\s*(b|bowled)\b", text)) or (
        (text.startswith("caught") or text == "c") and fielder and bowler and fielder.lower() == bowler.lower()
    )
    if caught_and_bowled:  # "c Singh b Singh" is written "c & b Singh" (Dhruvika, Oct 30)
        return (f"c & b {bowler or fielder}".strip(), False, False)
    if text.startswith("caught") or text == "c":
        return (" ".join(part for part in ["c " + fielder if fielder else "caught", "b " + bowler if bowler else ""] if part), False, False)
    if text.startswith("bowled") or text == "b":
        return (f"b {bowler}" if bowler else "bowled", False, False)
    if text.startswith("lbw"):
        return (f"lbw b {bowler}" if bowler else "lbw", False, False)
    if text.startswith("stumped") or text == "st":
        return (" ".join(part for part in ["st " + fielder if fielder else "stumped", "b " + bowler if bowler else ""] if part), False, False)
    if text.startswith("run out"):
        return (f"run out ({fielder})" if fielder else "run out", False, False)
    if "hit wicket" in text:
        return (f"hit wicket b {bowler}" if bowler else "hit wicket", False, False)
    return (text, False, False)


def _scorecard_strike_rate(runs: int | None, balls: int | None) -> str:
    if runs is None or not balls:
        return ""
    return f"{(runs / balls) * 100:.2f}"


def _scorecard_overs_to_balls(overs: Any) -> int | None:
    text = _scorecard_text(overs)
    if not text:
        return None
    try:
        whole, _, part = text.partition(".")
        return int(whole or 0) * 6 + int(part or 0)
    except ValueError:
        return None


def _scorecard_pick_template(archive: dict[str, Any]) -> dict[str, Any]:
    """Pick the template with the most filled-in figures (reviewed copies win ties). A card a person typed in or
    fixed with Edit always wins over the AI's reading, even when the AI listed more rows (Oct 27: fixes made with
    Edit didn't show because the AI copy had more names - README "Worked examples")."""
    for key in ("review_template_json", "extraction_template"):
        template = _scorecard_json(archive.get(key))
        source = str(((template.get("meta") or {}) if isinstance(template.get("meta"), dict) else {}).get("source") or "")
        if source in {"manual-entry", "manual-import", "checked-example"} and template.get("innings"):
            return template
    best: dict[str, Any] = {}
    best_score = -1
    for key in ("review_source_json", "review_template_json", "extraction_template"):
        template = _scorecard_json(archive.get(key))
        score = 0
        for innings in template.get("innings", []) or []:
            if not isinstance(innings, dict):
                continue
            summary = innings.get("summary") if isinstance(innings.get("summary"), dict) else {}
            score += 3 if summary.get("runs") is not None else 0
            score += sum(
                1
                for row in innings.get("batting", []) or []
                if isinstance(row, dict) and _scorecard_text((row.get("player") or {}).get("name"))
            )
            score += sum(
                1
                for row in innings.get("bowling", []) or []
                if isinstance(row, dict) and _scorecard_text((row.get("player") or {}).get("name"))
            )
        if score > best_score:
            best, best_score = template, score
    return best


def _scorecard_archive_date(archive: dict[str, Any]) -> str:
    for key in ("archive_date", "scorecard_date"):
        value = _scorecard_text(archive.get(key))
        if re.match(r"^\d{4}-\d{2}-\d{2}$", value):
            return value
    return ""


def _scorecard_date_label(value: str) -> str:
    try:
        return datetime.strptime(value, "%Y-%m-%d").strftime("%a %d %b %Y")
    except ValueError:
        return value or "Date unknown"


def _archive_scorecard_is_published(archive: dict[str, Any]) -> bool:
    return _scorecard_text(archive.get("status")).lower() in {"approved", "applied to match", "completed", "published"}


def _scorecard_photo_url(archive: dict[str, Any]) -> str:
    preview = _scorecard_text(archive.get("preview_url"))
    if not preview.startswith("/uploads/"):
        return ""
    name = preview[len("/uploads/"):]
    if "/" in name or "\\" in name or ".." in name:
        return ""
    image_path = UPLOAD_DIR / name
    if not image_path.is_file():
        return ""
    if image_path.suffix.lower() not in {".heic", ".heif"}:
        return preview

    browser_preview_dir = UPLOAD_DIR / ".previews"
    preview_name = f"{hashlib.sha256(name.encode('utf-8')).hexdigest()[:24]}.jpg"
    browser_preview_path = browser_preview_dir / preview_name
    try:
        if not browser_preview_path.is_file() or browser_preview_path.stat().st_mtime_ns < image_path.stat().st_mtime_ns:
            from PIL import Image, ImageOps

            browser_preview_dir.mkdir(parents=True, exist_ok=True)
            temporary_path = browser_preview_dir / f"{name}.{uuid.uuid4().hex}.tmp.jpg"
            try:
                with Image.open(image_path) as source:
                    ImageOps.exif_transpose(source).convert("RGB").save(temporary_path, format="JPEG", quality=92)
                temporary_path.replace(browser_preview_path)
            finally:
                temporary_path.unlink(missing_ok=True)
        return f"/uploads/.previews/{preview_name}"
    except (OSError, ValueError):
        logger.exception("Unable to create browser-compatible scorecard image preview. file=%s", name)
        return ""


def _scorecard_from_archive_base(archive: dict[str, Any]) -> dict[str, Any]:
    template = _scorecard_pick_template(archive)
    template_match = template.get("match") if isinstance(template.get("match"), dict) else {}
    template_teams = template_match.get("teams") if isinstance(template_match.get("teams"), dict) else {}
    validation = template.get("validation") if isinstance(template.get("validation"), dict) else {}
    draft = archive.get("draft_scorecard") if isinstance(archive.get("draft_scorecard"), dict) else {}
    parts = _scorecard_summary_parts(draft.get("live_summary"))
    club_name = _scorecard_text(archive.get("club_name")) or "Club"

    raw_innings = [item for item in (template.get("innings") or []) if isinstance(item, dict)]
    while len(raw_innings) < 2:
        raw_innings.append({"inning_number": len(raw_innings) + 1})

    first_team = (
        parts.get("batting team")
        or _scorecard_text(raw_innings[0].get("batting_team"))
        or _scorecard_text(template_teams.get("team_1"))
        or club_name
    )
    second_team = (
        parts.get("bowling team")
        or _scorecard_text(raw_innings[1].get("batting_team"))
        or _scorecard_text(raw_innings[0].get("bowling_team"))
        or _scorecard_text(template_teams.get("team_2"))
        or ("Opponent" if normalize_name(first_team) == normalize_name(club_name) else club_name)
    )
    if second_team == "Opponent":
        # "X won by ..." where X is not the first team names the other side.
        for candidate in (draft.get("result"), validation.get("expected_result")):
            won = _SCORECARD_WON_BY.match(_scorecard_clean_result(candidate))
            if won and normalize_name(won.group(1)) != normalize_name(first_team):
                second_team = won.group(1).strip()
                break
    teams = [first_team, second_team]

    # Player rows that came from the reviewed import (names, balls, dismissals, team tags).
    performances = [
        row
        for row in archive.get("suggested_performances", []) or []
        if isinstance(row, dict)
        and _scorecard_text(row.get("player_name"))
        and not _SCORECARD_JUNK_NAME.search(_scorecard_text(row.get("player_name")))
    ]
    tagged = any(_SCORECARD_TEAM_NOTE.search(_scorecard_text(row.get("notes"))) for row in performances)
    # When the template already lists batters for every innings (AI read, typed in, reviewed JSON), it is
    # the source of truth: untagged imported rows would otherwise all land in the 1st innings.
    filled_innings = sum(
        1
        for inn in raw_innings[:2]
        if isinstance(inn, dict)
        and any(isinstance(item, dict) and _scorecard_text((item.get("player") or {}).get("name")) for item in inn.get("batting", []) or [])
    )
    if not tagged and len(raw_innings) >= 2 and filled_innings >= 2:
        performances = []

    def perf_team(row: dict[str, Any]) -> str:
        found = _SCORECARD_TEAM_NOTE.search(_scorecard_text(row.get("notes")))
        return found.group(1).strip() if found else ""

    ocr_bowlers: dict[str, int] = {}
    batting_perf: list[list[dict[str, Any]]] = [[], []]
    bowling_perf: list[list[dict[str, Any]]] = [[], []]
    for index, row in enumerate(performances):
        notes = _scorecard_text(row.get("notes"))
        ocr_bowling = _SCORECARD_OCR_BOWLING.search(notes)
        if ocr_bowling:
            # e.g. "Amit S 4.0 15 1" is a bowling line: overs, runs, wickets.
            ocr_bowlers[normalize_name(_scorecard_text(row.get("player_name")))] = int(float(ocr_bowling.group(1)))
            bowling_perf[0].append(
                {
                    "name": _scorecard_text(row.get("player_name")),
                    "overs": ocr_bowling.group(1),
                    "runs": int(ocr_bowling.group(2)),
                    "wickets": int(ocr_bowling.group(3)),
                }
            )
            continue
        if tagged:
            team = perf_team(row)
            side = 1 if team and normalize_name(team) == normalize_name(second_team) else 0
        else:
            side = 0 if (len(performances) <= 11 or index < 11) else 1
        dismissal_match = _SCORECARD_DISMISSAL_NOTE.search(notes)
        wickets = _scorecard_int(row.get("wickets")) or 0
        wickets_match = _SCORECARD_WICKETS_NOTE.search(notes)
        bats = bool(dismissal_match) or not tagged
        if tagged and not dismissal_match and not wickets_match:
            bats = True
        if bats:
            batting_perf[side].append(row)
        if wickets_match or (tagged and wickets):
            # A bowler from this side bowled in the OTHER side's innings.
            bowling_perf[1 - side].append(
                {
                    "name": _scorecard_text(row.get("player_name")),
                    "overs": "",
                    "runs": None,
                    "wickets": int(wickets_match.group(1)) if wickets_match else wickets,
                }
            )

    innings_out: list[dict[str, Any]] = []
    for position, innings in enumerate(raw_innings[:2]):
        summary = innings.get("summary") if isinstance(innings.get("summary"), dict) else {}
        team = teams[position]
        opponent = teams[1 - position]

        # Batting: template rows first, then fill gaps / add rows from the imported performances.
        rows: list[dict[str, Any]] = []
        by_name: dict[str, dict[str, Any]] = {}
        # When the reviewed import tags each player with a team, it is the reliable source.
        template_batting = [] if tagged else (innings.get("batting", []) or [])
        for item in template_batting:
            if not isinstance(item, dict):
                continue
            name = _scorecard_text((item.get("player") or {}).get("name"))
            if not name or _SCORECARD_JUNK_NAME.search(name):
                continue
            if normalize_name(name) in ocr_bowlers and _scorecard_int(item.get("runs")) == ocr_bowlers[normalize_name(name)]:
                continue  # the OCR read a bowling line (overs) as a batting score
            dismissal = item.get("dismissal") if isinstance(item.get("dismissal"), dict) else {}
            row = {
                "name": name,
                "runs": _scorecard_int(item.get("runs")),
                "balls": _scorecard_int(item.get("balls")),
                "fours": _scorecard_int(item.get("fours")),
                "sixes": _scorecard_int(item.get("sixes")),
                # Nov 5 2026: counted from the batter's ball-by-ball marks (ai_vision.count_batter_marks)
                "dots": _scorecard_int(item.get("dots")),
                "ones": _scorecard_int(item.get("ones")),
                "twos": _scorecard_int(item.get("twos")),
                "threes": _scorecard_int(item.get("threes")),
                "how": _scorecard_text(dismissal.get("type")),
                "fielder": _scorecard_text(dismissal.get("fielder")),
                "bowler": _scorecard_text(dismissal.get("bowler")),
            }
            rows.append(row)
            by_name.setdefault(normalize_name(name), row)
        for perf in batting_perf[position]:
            name = _scorecard_text(perf.get("player_name"))
            notes = _scorecard_text(perf.get("notes"))
            dismissal_match = _SCORECARD_DISMISSAL_NOTE.search(notes)
            fielder_match = _SCORECARD_FIELDER_NOTE.search(notes)
            how = dismissal_match.group(1) if dismissal_match else notes.split("|")[0]
            if any(word in how.lower() for word in ("ocr suggested", "imported", "extraction", "typed in", "read by ai")):
                how = ""  # a note about where the row came from, not how the batter got out
            balls = _scorecard_int(perf.get("balls"))
            row = by_name.get(normalize_name(name))
            if row is None:
                # The same batter under a roster spelling ("Vinay" on the card, "Vinny" in the club):
                # same runs and same first letters -> same row, so they aren't counted twice.
                perf_runs = _scorecard_int(perf.get("runs"))
                row = next(
                    (
                        candidate for candidate in rows
                        if perf_runs is not None and candidate["runs"] == perf_runs
                        and normalize_name(candidate["name"])[:3] == normalize_name(name)[:3]
                        and normalize_name(candidate["name"]) not in {normalize_name(_scorecard_text(p.get("player_name"))) for p in batting_perf[position]}
                    ),
                    None,
                )
            if row is None:
                row = {"name": name, "runs": None, "balls": None, "fours": None, "sixes": None, "how": "", "fielder": "", "bowler": ""}
                rows.append(row)
                by_name[normalize_name(name)] = row
            if row["runs"] is None:
                row["runs"] = _scorecard_int(perf.get("runs"))
            if row["balls"] is None and balls:
                row["balls"] = balls
            if row["fours"] is None and _scorecard_int(perf.get("fours")):
                row["fours"] = _scorecard_int(perf.get("fours"))
            if row["sixes"] is None and _scorecard_int(perf.get("sixes")):
                row["sixes"] = _scorecard_int(perf.get("sixes"))
            ocr_batting = _SCORECARD_OCR_BATTING.search(notes)
            if ocr_batting and row["runs"] == int(ocr_batting.group(1)):
                row["fours"] = row["fours"] if row["fours"] is not None else int(ocr_batting.group(3))
                row["sixes"] = row["sixes"] if row["sixes"] is not None else int(ocr_batting.group(4))
            if not row["how"]:
                row["how"] = how.strip()
            if not row["fielder"] and fielder_match:
                row["fielder"] = fielder_match.group(1).strip()

        batting: list[dict[str, Any]] = []
        did_not_bat: list[str] = []
        for row in rows:
            text, not_out, dnb = _scorecard_dismissal(row["how"], row["fielder"], row["bowler"])
            if dnb or (row["how"] == "" and row["runs"] is None and row["balls"] is None):
                did_not_bat.append(row["name"])
                continue
            batting.append(
                {
                    "name": row["name"],
                    "dismissal": text,
                    "not_out": not_out,
                    "runs": row["runs"],
                    "balls": row["balls"],
                    "fours": row["fours"],
                    "sixes": row["sixes"],
                    "strike_rate": _scorecard_strike_rate(row["runs"], row["balls"]),
                    **{key: row.get(key) for key in ("dots", "ones", "twos", "threes") if row.get(key) is not None},
                }
            )
        if position == 0 and parts.get("did not bat"):
            for name in parts["did not bat"].split(","):
                name = name.strip()
                if name and normalize_name(name) not in {normalize_name(item) for item in did_not_bat}:
                    did_not_bat.append(name)

        # Bowling.
        bowling: list[dict[str, Any]] = []
        for item in innings.get("bowling", []) or []:
            if not isinstance(item, dict):
                continue
            name = _scorecard_text((item.get("player") or {}).get("name"))
            if not name:
                continue
            overs = _scorecard_text(item.get("overs"))
            runs = _scorecard_int(item.get("runs_conceded"))
            balls = _scorecard_overs_to_balls(overs)
            economy = item.get("economy")
            if economy in (None, "") and runs is not None and balls:
                economy = runs / (balls / 6)
            bowling.append(
                {
                    "name": name,
                    "overs": overs,
                    "maidens": _scorecard_int(item.get("maidens")),
                    "runs": runs,
                    "wickets": _scorecard_int(item.get("wickets")),
                    "economy": f"{float(economy):.2f}" if economy not in (None, "") else "",
                    # Nov 5 2026: counted from the bowler's analysis boxes (ai_vision.count_bowler_marks)
                    **{key: _scorecard_int(item.get(key)) for key in ("dots", "wides", "no_balls", "fours", "sixes") if item.get(key) not in (None, "")},
                    # Nov 7 2026: runs in each of his overs (written under the boxes, or counted from them)
                    **({"over_runs": [int(value) for value in item.get("over_runs") if str(value).strip().lstrip("-").isdigit()]} if isinstance(item.get("over_runs"), list) and item.get("over_runs") else {}),
                }
            )
        known_bowlers = {normalize_name(item["name"]) for item in bowling}
        for item in bowling_perf[position]:
            if normalize_name(item["name"]) in known_bowlers:
                continue
            balls = _scorecard_overs_to_balls(item["overs"])
            bowling.append(
                {
                    "name": item["name"],
                    "overs": item["overs"],
                    "maidens": None,
                    "runs": item["runs"],
                    "wickets": item["wickets"],
                    "economy": f"{item['runs'] / (balls / 6):.2f}" if item["runs"] is not None and balls else "",
                }
            )

        # Totals: template first, then the reviewed draft figures.
        draft_prefix = "heartlake" if position == 0 else "opponent"
        runs = _scorecard_int(summary.get("runs"))
        if runs is None:
            runs = _scorecard_int(draft.get(f"{draft_prefix}_runs"))
        if runs is None:
            runs = _scorecard_int(validation.get(f"inning_{position + 1}_total"))
        wickets = _scorecard_int(summary.get("wickets"))
        if wickets is None:
            wickets = _scorecard_int(draft.get(f"{draft_prefix}_wickets"))
        overs = _scorecard_text(summary.get("overs")) or _scorecard_text(draft.get(f"{draft_prefix}_overs"))
        if position == 1 and runs is None and parts.get("second innings"):
            second = re.search(r"(\d+)\s*/\s*(\d+)\s*(?:\(([\d.]+)\))?", parts["second innings"])
            if second:
                runs, wickets, overs = int(second.group(1)), int(second.group(2)), second.group(3) or overs

        extras = innings.get("extras") if isinstance(innings.get("extras"), dict) else {}
        extras_total = _scorecard_int(extras.get("total"))
        if extras_total is None and position == 0:
            extras_total = _scorecard_int(parts.get("extras"))
        extras_detail = ", ".join(
            f"{label} {_scorecard_int(extras.get(key))}"
            for key, label in (("byes", "b"), ("leg_byes", "lb"), ("wides", "w"), ("no_balls", "nb"), ("penalties", "pen"))
            if _scorecard_int(extras.get(key))
        )

        has_data = bool(batting or bowling or runs is not None)
        innings_out.append(
            {
                "number": position + 1,
                "written_inning_number": _scorecard_int(innings.get("inning_number")),
                "team": team,
                "bowling_team": opponent,
                "runs": runs,
                "wickets": wickets,
                "overs": overs,
                "score": (f"{runs}" + (f"/{wickets}" if wickets is not None else "")) if runs is not None else "",
                "extras": extras_total,
                "extras_detail": extras_detail,
                "batting": batting,
                "did_not_bat": did_not_bat,
                "bowling": bowling,
                "has_data": has_data,
            }
        )

    result = (
        _scorecard_clean_result(draft.get("result"))
        or _scorecard_clean_result(parts.get("result"))
        or _scorecard_clean_result(parts.get("expected result"))
        or _scorecard_clean_result(validation.get("expected_result"))
    )
    overs_limit = _scorecard_int(template_match.get("overs_limit"))
    if overs_limit is None:
        overs_values = [_scorecard_int(item["overs"]) for item in innings_out if item["overs"]]
        overs_limit = max([value for value in overs_values if value], default=None)
    game_date = _scorecard_archive_date(archive)
    venue = parts.get("venue") or _scorecard_text(template_match.get("venue"))
    has_details = any(item["batting"] or item["bowling"] for item in innings_out)
    return {
        "id": f"a-{_scorecard_text(archive.get('id'))}",
        "source": "archive",
        "date": game_date,
        "date_label": _scorecard_date_label(game_date),
        "year": game_date[:4],
        "season": _scorecard_text(archive.get("season")),
        "club_id": _scorecard_text(archive.get("club_id")),
        "club_ids": [
            str(value).strip()
            for value in (archive.get("club_ids") if isinstance(archive.get("club_ids"), list) else [])
            if str(value or "").strip()
        ],
        "club_name": club_name,
        "title": f"{teams[0]} vs {teams[1]}",
        "teams": teams,
        "venue": venue,
        "toss": parts.get("toss", ""),
        "match_type": (_scorecard_text(template_match.get("match_type")) or "club").title() + " match",
        "overs_limit": overs_limit,
        "result": result,
        "innings": innings_out,
        "has_details": has_details,
        "match_code": _match_code(archive.get("id")),
        "photo_url": _scorecard_photo_url(archive),
        # Nov 2 2026: a card photographed on two pages (1st innings / 2nd innings)
        "photo_urls": [url for url in (_scorecard_photo_url(archive), _scorecard_photo_url({"preview_url": archive.get("second_preview_url")})) if url],
    }


def _scorecard_from_fixture_base(fixture: dict[str, Any]) -> dict[str, Any]:
    match = _public_match_payload({"fixtures": [fixture]}, str(fixture.get("id") or ""))
    raw_innings = sorted(
        (match.get("scorebook") or {}).get("innings") or [],
        key=lambda item: int(item.get("inning_number") or 1),
    )
    fallback_teams = [
        _scorecard_text(fixture.get("club_name")) or "Club",
        _scorecard_text(fixture.get("opponent") or fixture.get("visiting_team")) or "Opponent",
    ]
    teams = [
        _scorecard_text(innings.get("batting_team")) or fallback_teams[index]
        for index, innings in enumerate(raw_innings[:2])
    ]
    while len(teams) < 2:
        used = {normalize_name(team) for team in teams}
        teams.append(next((team for team in fallback_teams if normalize_name(team) not in used), fallback_teams[len(teams)]))

    innings_out: list[dict[str, Any]] = []
    max_overs = 0
    for index in range(2):
        source = raw_innings[index] if index < len(raw_innings) else {}
        summary = source.get("summary") or {}
        team = teams[index]
        opponent = teams[1 - index]
        runs = _scorecard_int(summary.get("runs"))
        wickets = _scorecard_int(summary.get("wickets"))
        overs = _scorecard_text(summary.get("overs"))
        max_overs = max(max_overs, int(source.get("overs_limit") or 0))
        dismissals: dict[str, str] = {}
        retired: set[str] = set()
        for ball in source.get("balls", []) or []:
            for name in (ball.get("striker"), ball.get("non_striker"), ball.get("new_batter")):
                key = normalize_name(name)
                if key in retired:
                    dismissals.pop(key, None)
                    retired.discard(key)
            player = _scorecard_text(ball.get("wicket_player"))
            kind = _scorecard_text(ball.get("wicket_type")).lower()
            if not player or not (ball.get("wicket") or kind == "retired_out"):
                continue
            dismissal, _, _ = _scorecard_dismissal(kind, ball.get("fielder"), ball.get("bowler"))
            dismissals[normalize_name(player)] = dismissal
            if kind == "retired_out":
                retired.add(normalize_name(player))

        batting: list[dict[str, Any]] = []
        did_not_bat: list[str] = []
        for batter in summary.get("batting") or []:
            name = _scorecard_text(batter.get("player_name"))
            if not name:
                continue
            status = _scorecard_text(batter.get("status")).lower()
            if status == "not_batted":
                did_not_bat.append(name)
                continue
            dismissal = dismissals.get(normalize_name(name), "")
            if not dismissal:
                dismissal = "retired" if status == "retired" else "not out" if status in {"batting", "not_out"} else "out" if status == "out" else ""
            _, not_out, _ = _scorecard_dismissal(dismissal)
            batter_runs = _scorecard_int(batter.get("runs"))
            batter_balls = _scorecard_int(batter.get("balls"))
            batting.append(
                {
                    "name": name,
                    "dismissal": dismissal,
                    "not_out": not_out,
                    "runs": batter_runs,
                    "balls": batter_balls,
                    "fours": _scorecard_int(batter.get("fours")),
                    "sixes": _scorecard_int(batter.get("sixes")),
                    "strike_rate": _scorecard_strike_rate(batter_runs, batter_balls),
                }
            )

        bowling = [
            {
                "name": _scorecard_text(bowler.get("player_name")),
                "overs": _scorecard_text(bowler.get("overs")),
                "maidens": _scorecard_int(bowler.get("maidens")),
                "runs": _scorecard_int(bowler.get("runs_conceded")),
                "wickets": _scorecard_int(bowler.get("wickets")),
                "economy": f"{float(bowler.get('economy') or 0):.2f}",
            }
            for bowler in summary.get("bowling") or []
            if _scorecard_text(bowler.get("player_name"))
            and (int(bowler.get("legal_balls") or 0) > 0 or int(bowler.get("runs_conceded") or 0) > 0)
        ]
        extras_detail = ", ".join(
            f"{label} {int(summary.get(key) or 0)}"
            for key, label in (("byes", "b"), ("legByes", "lb"), ("wides", "w"), ("noBalls", "nb"))
            if int(summary.get(key) or 0)
        )
        score = f"{runs}" if runs is not None else ""
        if runs is not None and wickets is not None:
            score += f"/{wickets}"
        innings_out.append(
            {
                "number": index + 1,
                "team": team,
                "bowling_team": opponent,
                "runs": runs,
                "wickets": wickets,
                "overs": overs,
                "score": score,
                "extras": _scorecard_int(summary.get("extras")),
                "extras_detail": extras_detail,
                "batting": batting,
                "did_not_bat": did_not_bat,
                "bowling": bowling,
                "has_data": bool(batting or bowling or runs is not None),
            }
        )

    date_text = str(fixture.get("date") or "").strip()[:10]
    scorecard = fixture.get("scorecard") or {}
    result = _scorecard_clean_result(scorecard.get("result") or fixture.get("result"))
    return {
        "id": f"f-{_scorecard_text(fixture.get('id'))}",
        "source": "fixture",
        "fixture_id": _scorecard_text(fixture.get("id")),
        "is_incomplete": not _fixture_is_completed(fixture),
        "date": date_text,
        "date_label": _scorecard_text(fixture.get("date_label")) or _scorecard_date_label(date_text),
        "year": date_text[:4],
        "season": _scorecard_text(fixture.get("season") or fixture.get("season_year") or date_text[:4]),
        "club_id": _scorecard_text(fixture.get("club_id")),
        "club_name": _scorecard_text(fixture.get("club_name")) or "Club",
        "title": f"{teams[0]} vs {teams[1]}",
        "teams": teams,
        "venue": _scorecard_text((fixture.get("details") or {}).get("venue")),
        "toss": "",
        "match_type": _scorecard_text((fixture.get("details") or {}).get("match_type")) or "Club match",
        "overs_limit": max_overs or _scorecard_int((fixture.get("details") or {}).get("overs")),
        "result": result,
        "innings": innings_out,
        "has_details": any(item["batting"] or item["bowling"] for item in innings_out),
        "photo_url": "",
    }


def _is_test_match(card: dict[str, Any]) -> bool:
    kind = str(card.get("match_type") or "").lower()
    return "test" in kind.split() or "multi-day" in kind or "two-day" in kind or "2-day" in kind


def _innings_ids(card: dict[str, Any]) -> list[dict[str, Any]]:
    """Nov 3 2026 (Amit): a match (Match ID = parent) has one innings ID per innings as its children:
    M-XXXXXXXX-I1, M-XXXXXXXX-I2 (a Test match: I1 to I4). An innings with nothing recorded is "missing",
    so a match with a missing innings scorecard is easy to see and to link."""
    code = _match_code(card.get("id"))
    if not code:
        return []
    innings = [item for item in card.get("innings") or [] if isinstance(item, dict)]
    detailed = [item for item in innings if item.get("batting")]
    recorded = detailed if detailed else [item for item in innings if item.get("has_data")]
    slots = 4 if _is_test_match(card) else 2
    slots = max(slots, len(recorded))
    teams = [str(team or "") for team in card.get("teams") or []]
    # the innings number written on the card ("Innings of Amit CC (2nd)") puts it in its own slot,
    # so a page holding only the 2nd innings shows I1 as the missing one
    written = [item.get("written_inning_number") for item in recorded]
    if all(isinstance(n, int) and 1 <= n <= slots for n in written) and len(set(written)) == len(written):
        by_slot = {int(n): item for n, item in zip(written, recorded)}
    else:
        by_slot = {index + 1: item for index, item in enumerate(recorded)}
    out = []
    for number in range(1, slots + 1):
        if number in by_slot:
            item = by_slot[number]
            out.append({
                "id": f"{code}-I{number}",
                "number": number,
                "team": str(item.get("team") or ""),
                "score": str(item.get("score") or ""),
                "overs": item.get("overs"),
                "status": "recorded",
            })
        else:
            # who should bat: teams take turns (a Test with a follow-on can differ; fixed when it is linked)
            near = by_slot.get(number - 1) or by_slot.get(number + 1) or {}
            previous = str(near.get("team") or (out[-1]["team"] if out else ""))
            other = next((team for team in teams if team and team != previous), "")
            out.append({"id": f"{code}-I{number}", "number": number, "team": other, "score": "", "overs": None, "status": "missing"})
    return out


_RESULT_WORDS = re.compile(r"\b(won|win|wins|beat|beats|tie|tied|draw|drawn|abandon|abandoned|no result|forfeit|conceded)\b", re.I)


def _result_from_innings(card: dict[str, Any]) -> str:
    """Nov 5 2026 ("Imran XI 219/8" shown as the result): a 2-innings card with no result written gets it from
    the two totals - "Imran XI won by 94 runs" / "X won by 4 wickets" / "Match tied"."""
    innings = [item for item in card.get("innings") or [] if isinstance(item, dict) and item.get("runs") not in (None, "")]
    if len(innings) != 2:
        return ""
    first, second = sorted(innings, key=lambda item: int(item.get("number") or 0))
    try:
        first_runs, second_runs = int(first.get("runs")), int(second.get("runs"))
    except (TypeError, ValueError):
        return ""
    if not first.get("team") or not second.get("team"):
        return ""
    if second_runs > first_runs:
        try:
            left = 10 - int(second.get("wickets"))
        except (TypeError, ValueError):
            return f"{second['team']} won"
        return f"{second['team']} won by {left} wicket{'s' if left != 1 else ''}" if left > 0 else f"{second['team']} won"
    if second_runs < first_runs:
        diff = first_runs - second_runs
        return f"{first['team']} won by {diff} run{'s' if diff != 1 else ''}"
    return "Match tied"


def _card_people(archive: dict[str, Any], card: dict[str, Any]) -> None:
    """Nov 7 2026 (Amit): captains and the man of the match read from the card (CAPTS. HOME / VISIT, MAN OF MATCH)."""
    template = _scorecard_pick_template(archive) or {}
    match = template.get("match") if isinstance(template.get("match"), dict) else {}
    teams_info = match.get("teams") if isinstance(match.get("teams"), dict) else {}
    captains = match.get("captains") if isinstance(match.get("captains"), dict) else {}
    pairs = []
    for key in ("team_1", "team_2"):
        name = " ".join(str(captains.get(key) or "").split())
        if name and name.lower() not in {"null", "none", "-"}:
            team = str(teams_info.get(key) or "")
            shown = next((item for item in card.get("teams") or [] if team and _same_team_name(team, item)), team)
            pairs.append({"team": shown, "name": name})
    card["captains"] = pairs
    mom = " ".join(str(match.get("man_of_match") or "").split())
    card["man_of_match"] = "" if mom.lower() in {"", "null", "none", "-"} else mom


def _scorecard_from_archive(archive: dict[str, Any]) -> dict[str, Any]:
    card = _scorecard_from_archive_base(archive)
    card["innings_ids"] = _innings_ids(card)
    _card_people(archive, card)
    if not _RESULT_WORDS.search(str(card.get("result") or "")):
        derived = _result_from_innings(card)
        if derived:
            card["result"] = derived
    return card


def _scorecard_from_fixture(fixture: dict[str, Any]) -> dict[str, Any]:
    card = _scorecard_from_fixture_base(fixture)
    card["innings_ids"] = _innings_ids(card)
    return card


def _public_scorecards(store: dict[str, Any]) -> list[dict[str, Any]]:
    cards = [
        _scorecard_from_archive(archive)
        for archive in store.get("archive_uploads", []) or []
        if isinstance(archive, dict) and _scorecard_text(archive.get("status")).lower() == "approved"
    ]
    for fixture in store.get("fixtures", []) or []:
        if not isinstance(fixture, dict) or not _fixture_is_past(fixture) or not _fixture_has_recorded_score_data(fixture):
            continue
        card = _scorecard_from_fixture(fixture)
        card_teams = {normalize_name(team) for team in card["teams"]}
        already_archived = any(
            existing["date"] == card["date"]
            and existing["club_id"] == card["club_id"]
            and len(card_teams & {normalize_name(team) for team in existing["teams"]}) >= 2
            for existing in cards
        )
        if not already_archived:
            cards.append(card)
    cards = [card for card in cards if card["date"]]
    cards.sort(key=lambda card: (card["date"], card["id"]), reverse=True)
    return cards


def _match_code(raw_id: Any) -> str:
    """Nov 2 2026 (Amit): every match has a Match ID that both teams can quote, e.g. "M-8A311D9B"
    (from the scorecard / match id, so it never changes; the two innings of a match share it once linked)."""
    text = str(raw_id or "")
    if text[:2] in {"a-", "f-"}:
        text = text[2:]
    clean = re.sub(r"[^0-9a-zA-Z]", "", text)[:8].upper()
    return f"M-{clean}" if clean else ""


def _upload_by_match_code(store: dict[str, Any], code: str) -> dict[str, Any] | None:
    wanted = re.sub(r"-I\d+$", "", str(code or "").strip().upper())  # an innings ID links to its match
    wanted = re.sub(r"[^0-9A-Z]", "", wanted)
    if wanted.startswith("M") and len(wanted) > 8:
        wanted = wanted[1:]
    if not wanted:
        return None
    for upload in store.get("archive_uploads", []) or []:
        for known_id in [upload.get("id"), *(upload.get("joined_upload_ids") or [])]:
            if re.sub(r"[^0-9A-Z]", "", _match_code(known_id).upper())[1:] == wanted:
                return upload
    return None


def _json_with_match_ids(text: str, upload: dict[str, Any]) -> str:
    """Admin Center review JSON (Amit, Nov 3 2026): add match.match_code "M-XXXXXXXX" and each innings'
    innings_id "M-XXXXXXXX-I1" ... so the reviewed JSON carries the same IDs as Scorecards."""
    code = _match_code(upload.get("id"))
    try:
        template = json.loads(text)
    except Exception:
        return text
    if not code or not isinstance(template, dict):
        return text
    match = template.get("match") if isinstance(template.get("match"), dict) else {}
    template["match"] = {"match_code": code, **{k: v for k, v in match.items() if k != "match_code"}}
    innings = [item for item in template.get("innings") or [] if isinstance(item, dict)]
    numbers = [_scorecard_int(item.get("inning_number")) for item in innings]
    use_written = all(isinstance(n, int) and n >= 1 for n in numbers) and len(set(numbers)) == len(numbers)
    template["innings"] = [
        {"innings_id": f"{code}-I{numbers[i] if use_written else i + 1}", **{k: v for k, v in item.items() if k != "innings_id"}}
        for i, item in enumerate(innings)
    ]
    return json.dumps(template, indent=2)


def _scorecard_list_item(card: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": card["id"],
        "match_code": _match_code(card["id"]),
        "innings_ids": card.get("innings_ids") or [],
        "source": card.get("source") or "archive",
        "fixture_id": card.get("fixture_id") or "",
        "is_incomplete": bool(card.get("is_incomplete")),
        "date": card["date"],
        "date_label": card["date_label"],
        "year": card["year"],
        "club_id": card["club_id"],
        "club_name": card["club_name"],
        "title": card["title"],
        "teams": [
            {"name": item["team"], "score": item["score"], "overs": item["overs"]} for item in card["innings"]
        ],
        "result": card["result"],
        "venue": card["venue"],
        "has_details": card["has_details"],
        "has_photo": bool(card["photo_url"]),
    }


def _scorecard_involved_club_ids(store: dict[str, Any], card: dict[str, Any]) -> set[str]:
    ids = {str(card.get("club_id") or "").strip()} - {""}
    ids.update(str(value).strip() for value in (card.get("club_ids") or []) if str(value or "").strip())
    if card.get("source") == "fixture":
        fixture_id = str(card.get("fixture_id") or "")
        fixture = next((item for item in store.get("fixtures", []) or [] if str(item.get("id") or "") == fixture_id), None)
        if fixture:
            ids.update(_match_participating_club_ids(store, fixture))
    for team in card.get("teams", []) or []:
        club = _find_club_by_name(store, str(team or ""))
        if club and club.get("id"):
            ids.add(str(club["id"]))
    return ids


@app.get("/api/public/scorecards")
def public_scorecards(
    date: str = "",
    club_id: str = "",
    year: str = "",
    x_auth_token: str | None = Header(default=None),
) -> dict[str, Any]:
    """Approved scorecards; signed-in users are scoped to their club except superadmins."""
    store = load_store()
    cards = _public_scorecards(store)
    signed_in = bool(x_auth_token)
    can_select_club = False
    selected_club_id = ""
    clubs: list[dict[str, str]] = []
    if signed_in:
        user_row, current_club_id = _auth_user_from_token(x_auth_token)
        selected_club_id = str(current_club_id or user_row["primary_club_id"] or "").strip()
        can_select_club = "superadmin" in _user_role_names(user_row, selected_club_id)
        if can_select_club:
            clubs = sorted(
                [
                    {"id": str(club.get("id") or ""), "name": str(club.get("name") or "")}
                    for club in store.get("clubs", []) or []
                    if club.get("id") and club.get("name")
                ],
                key=lambda item: item["name"].lower(),
            )
            if club_id:
                cards = [card for card in cards if club_id in _scorecard_involved_club_ids(store, card)]
        elif selected_club_id:
            cards = [card for card in cards if selected_club_id in _scorecard_involved_club_ids(store, card)]
            selected = next(
                (club for club in store.get("clubs", []) or [] if str(club.get("id") or "") == selected_club_id),
                None,
            )
            if selected:
                clubs = [{"id": selected_club_id, "name": str(selected.get("name") or "My club")}]
        else:
            cards = []
    pending_ids: set[str] = set()
    if signed_in:
        # Nov 3 2026: captains, club admins and superadmins also see their matches still waiting for review
        # (marked "Waiting for review", opening the check page), so a just-linked match can always be found.
        try:
            if "score_matches" in _user_permissions(user_row, selected_club_id):
                for upload in store.get("archive_uploads", []) or []:
                    status = str(upload.get("status") or "").lower()
                    if _archive_scorecard_is_published(upload) or status in {"rejected", "duplicate"}:
                        continue
                    try:
                        card = _scorecard_from_archive(upload)
                    except Exception:
                        continue
                    involved = _scorecard_involved_club_ids(store, card) | {str(c) for c in upload.get("club_ids") or [upload.get("club_id")] if c}
                    if can_select_club:
                        if club_id and club_id not in involved:
                            continue
                    elif not selected_club_id or selected_club_id not in involved:
                        continue
                    cards.append(card)
                    pending_ids.add(card["id"])
        except Exception:
            logger.exception("Could not list scorecards waiting for review")
    cards.sort(key=lambda card: (str(card.get("date") or ""), str(card.get("id") or "")), reverse=True)
    dates = sorted({card["date"] for card in cards}, reverse=True)
    if year:
        cards = [card for card in cards if card["year"] == year]
    if date:
        cards = [card for card in cards if card["date"] == date]
    scorecards = []
    for card in cards:
        item = _scorecard_list_item(card)
        item["club_ids"] = sorted(_scorecard_involved_club_ids(store, card))
        if card["id"] in pending_ids:
            item["pending"] = True
            item["url"] = f"/scorecards/{card['id'][2:]}?preview=1"
        scorecards.append(item)
    return {
        "scorecards": scorecards,
        "dates": dates,
        "clubs": clubs,
        "can_select_club": can_select_club,
        "selected_club_id": selected_club_id,
        "generated_at": now_iso(),
    }


# ---------------------------------------------------------------------------
# Nov 7 2026 (Amit: "When we click on players name it should show players profile and his stats in a read only
# mode"): scorecard names link to /players/<player id>, a public read-only profile (no phone, email or age).
# ---------------------------------------------------------------------------
def _club_roster(store: dict[str, Any], club_id: str) -> list[dict[str, Any]]:
    return [
        member for member in store.get("members", []) or []
        if any(str(link.get("club_id") or "") == club_id for link in member.get("club_memberships", []) or [] if isinstance(link, dict))
    ]


def _member_for_card_name(store: dict[str, Any], name: Any, team: Any) -> dict[str, Any] | None:
    """The registered player behind a name on a card: first among the players of the club that team is, then anyone
    with exactly that name or alias. None when it isn't clear (two players fit)."""
    clean = " ".join(str(name or "").split())
    if not clean:
        return None
    club = _find_club_by_name(store, str(team or "")) if team else None
    pools = []
    if club:
        pools.append(_club_roster(store, str(club.get("id") or "")))
    pools.append(list(store.get("members", []) or []))
    for pool in pools:
        found = [member for member in pool if _member_matches_name(member, clean)]
        if len(found) == 1:
            return found[0]
        if len(found) > 1:
            return None
    return None


def _member_public_key(member: dict[str, Any]) -> str:
    return str(member.get("player_id") or member.get("id") or "").strip()


def _link_card_players(store: dict[str, Any], card: dict[str, Any]) -> dict[str, Any]:
    for innings in card.get("innings") or []:
        if not isinstance(innings, dict):
            continue
        for key, team in (("batting", innings.get("team")), ("bowling", innings.get("bowling_team"))):
            for row in innings.get(key) or []:
                if not isinstance(row, dict) or row.get("player_key"):
                    continue
                member = _member_for_card_name(store, row.get("name"), team)
                if member and _member_public_key(member):
                    row["player_key"] = _member_public_key(member)
    return card


def _lineup_player_keys(store: dict[str, Any], match: dict[str, Any], lineups: dict[str, Any]) -> dict[str, str]:
    """Name -> player id for the live scorecard, so its names link to /players/<id> like an uploaded card (Nov 9 2026)."""
    keys: dict[str, str] = {}
    for side, team in (("club", match.get("club_name")), ("opponent", match.get("opponent"))):
        for name in lineups.get(side) or []:
            if not isinstance(name, str) or not name.strip():
                continue
            member = _member_for_card_name(store, name, team)
            if member and _member_public_key(member):
                keys[name] = _member_public_key(member)
    return keys


def _find_member_by_key(store: dict[str, Any], key: str) -> dict[str, Any] | None:
    key = str(key or "").strip()
    return next(
        (member for member in store.get("members", []) or [] if key and key in {str(member.get("player_id") or ""), str(member.get("id") or "")}),
        None,
    )


@app.get("/players/{player_key}")
def public_player_page(player_key: str) -> FileResponse:
    return _page_response("player_public.html")


@app.get("/api/public/players/{player_key}")
def public_player_profile(player_key: str) -> dict[str, Any]:
    store = load_store()
    member = _find_member_by_key(store, player_key)
    if not member:
        raise HTTPException(status_code=404, detail="Player not found.")
    member_id = str(member.get("id") or "")

    def rows(name: str) -> list[dict[str, Any]]:
        return [dict(row) for row in store.get(name, []) or [] if str(row.get("member_id") or "") == member_id]

    keep = ("matches", "batting_innings", "outs", "runs", "balls", "batting_average", "strike_rate", "wickets", "catches", "fours", "sixes", "highest_score", "scores_50_plus", "scores_100_plus")
    summary = next(iter(rows("member_summary_stats")), {})
    years = sorted(rows("member_year_stats"), key=lambda row: str(row.get("season_year") or ""), reverse=True)
    clubs = sorted(rows("member_club_stats"), key=lambda row: -int(row.get("matches") or 0))
    recent = []
    for card in _public_scorecards(store):
        _link_card_players(store, card)
        batting = bowling = None
        for innings in card.get("innings") or []:
            for row in innings.get("batting") or []:
                if row.get("player_key") == _member_public_key(member):
                    batting = {"runs": row.get("runs"), "balls": row.get("balls"), "not_out": row.get("not_out"), "team": innings.get("team")}
            for row in innings.get("bowling") or []:
                if row.get("player_key") == _member_public_key(member):
                    bowling = {"overs": row.get("overs"), "runs": row.get("runs"), "wickets": row.get("wickets")}
        if batting or bowling:
            recent.append({"id": card.get("id"), "date": card.get("date"), "date_label": card.get("date_label"), "title": card.get("title"), "result": card.get("result"), "batting": batting, "bowling": bowling})
    recent.sort(key=lambda item: str(item.get("date") or ""), reverse=True)
    return {
        "player": {
            "name": member.get("name") or "",
            "full_name": member.get("full_name") or "",
            "player_id": member.get("player_id") or "",
            "role": member.get("role") or "",
            "batting_style": member.get("batting_style") or "",
            "bowling_style": member.get("bowling_style") or "",
            "aliases": [alias for alias in member.get("aliases") or [] if alias],
            "clubs": [str(link.get("club_name") or "") for link in member.get("club_memberships", []) or [] if isinstance(link, dict) and link.get("club_name")],
            "picture_url": member.get("picture_url") or "",
        },
        "summary": {key: summary.get(key) for key in keep},
        "years": [{"season_year": row.get("season_year"), **{key: row.get(key) for key in keep}} for row in years if row.get("matches")],
        "clubs": [{"club_name": row.get("club_name"), **{key: row.get(key) for key in keep}} for row in clubs if row.get("matches")],
        "recent": recent[:20],
        "read_only": True,
    }


@app.get("/api/public/scorecards/{scorecard_id}")
def public_scorecard_detail(
    scorecard_id: str,
    x_auth_token: str | None = Header(default=None),
) -> dict[str, Any]:
    store = load_store()
    for card in _public_scorecards(store):
        if card["id"] == scorecard_id:
            if x_auth_token:
                user_row, current_club_id = _auth_user_from_token(x_auth_token)
                if "superadmin" not in _user_role_names(user_row, current_club_id):
                    allowed_club_id = str(current_club_id or user_row["primary_club_id"] or "").strip()
                    if not allowed_club_id or allowed_club_id not in _scorecard_involved_club_ids(store, card):
                        raise HTTPException(status_code=404, detail="Scorecard not found.")
            return {"scorecard": _link_card_players(store, card), "generated_at": now_iso()}
    raise HTTPException(status_code=404, detail="Scorecard not found.")


@app.get("/scorecards")
def scorecards_page() -> FileResponse:
    return _page_response("scorecards.html")


@app.get("/scorecards/upload")
def scorecard_upload_page(request: Request) -> Response:
    """Captains and club admins upload a scorecard photo (README: "Scorecard uploads: checks, review and duplicates")."""
    session = _require_page_session(request)
    if isinstance(session, RedirectResponse):
        return session
    return _page_response("scorecard_upload.html")


@app.get("/scorecards/{scorecard_id}")
def scorecard_page(scorecard_id: str) -> FileResponse:
    return _page_response("scorecard.html")


@app.get("/api/public/match/{match_id}")
def public_match(
    match_id: str,
    request: Request,
    x_auth_token: str | None = Header(default=None),
) -> dict[str, Any]:
    logger.debug("Public scorecard requested. match_id=%s", match_id)
    store = load_store()
    fixture: dict[str, Any] | None = None
    try:
        if str(match_id).startswith("guest-"):
            guest = _guest_load(match_id)
            if not guest:
                raise ValueError("Match not found.")
            guest.pop("_code", None)
            match = _public_match_payload({"fixtures": [guest]}, match_id)
            lineups = guest.get("lineups") or {}
        else:
            fixture = get_match_or_404(store, match_id)
            match = _public_match_payload(store, match_id)
            lineups = _match_lineups(match_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    scorebook = match.get("scorebook") if isinstance(match.get("scorebook"), dict) else {}
    innings = scorebook.get("innings") if isinstance(scorebook.get("innings"), list) else []
    has_started = str(match.get("status") or "").strip().lower() == "live" or any(
        isinstance(inning, dict) and bool(inning.get("balls")) for inning in innings
    )
    is_completed = _fixture_is_completed(fixture) if fixture else (
        str(match.get("status") or "").strip().lower() == "completed"
        or str(match.get("result") or "").strip().lower() not in {"", "tbd"}
    )
    match["live_viewers"] = _touch_live_match_viewer(match_id, request) if has_started and not is_completed else 0
    can_delete_incomplete = False
    can_delete_completed = False
    token = _auth_token_from_request(request, x_auth_token)
    if token and fixture:
        try:
            user_row, current_club_id = _auth_user_from_token(token, touch=False)
        except HTTPException:
            pass
        else:
            allowed = _match_delete_is_authorized(
                store,
                user_row,
                current_club_id,
                fixture,
            )
            # Nov 2 2026 (Amit): a finished but wrong scorecard can be deleted too, by the same people.
            can_delete_incomplete = allowed and not _fixture_is_completed(fixture)
            can_delete_completed = allowed and _fixture_is_completed(fixture)
    match["can_delete_incomplete"] = can_delete_incomplete
    match["can_delete_completed"] = can_delete_completed
    # Player names only, for "Yet to bat" on the public scorecard (README "Public scorecard (Oct 29 2026)").
    match["lineups"] = {
        "club": list(lineups.get("club") or []),
        "opponent": list(lineups.get("opponent") or []),
        "roles": _clean_lineup_roles(lineups.get("roles"), list(lineups.get("club") or []), list(lineups.get("opponent") or [])),
    }
    match["player_keys"] = _lineup_player_keys(store, match, match["lineups"])
    # Names on the linked published card keep their player links even when the match has no lineup.
    for innings in (match.get("published_scorecard") or {}).get("innings") or []:
        if not isinstance(innings, dict):
            continue
        for key, team in (("batting", innings.get("team")), ("bowling", innings.get("bowling_team"))):
            for row in innings.get(key) or []:
                if not isinstance(row, dict) or not row.get("name"):
                    continue
                member = _member_for_card_name(store, row.get("name"), team)
                if member and _member_public_key(member):
                    match["player_keys"].setdefault(str(row["name"]), _member_public_key(member))
    return {
        "match": match,
        "generated_at": now_iso(),
    }


@app.get("/api/public/match/{match_id}/scorecard.pdf")
def public_match_scorecard_pdf(match_id: str) -> Response:
    store = load_store()
    try:
        if str(match_id).startswith("guest-"):
            guest = _guest_load(match_id)
            if not guest:
                raise ValueError("Match not found.")
            guest.pop("_code", None)
            match = _public_match_payload({"fixtures": [guest]}, match_id)
        else:
            match = _public_match_payload(store, match_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    pdf = scorecard_pdf.build_scorecard_pdf(match)
    filename = scorecard_pdf.scorecard_pdf_filename(match)
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.get("/public/match/{match_id}")
def public_match_page(match_id: str) -> FileResponse:
    return _page_response("public_match.html")


@app.get("/live")
def live_page() -> FileResponse:
    return _page_response("live.html")


@app.get("/fixtures")
def fixtures_page() -> FileResponse:
    return _page_response("fixtures.html")


@app.get("/rankings")
def rankings_page() -> FileResponse:
    return _page_response("rankings.html")


@app.get("/live/{match_id}")
def live_match_page(match_id: str) -> FileResponse:
    return _page_response("public_match.html")


@app.get("/live/{match_id}/commentary")
def live_match_commentary_page(match_id: str) -> RedirectResponse:
    return RedirectResponse(url=f"/live/{match_id}", status_code=303)


@app.get("/live/{match_id}/stats")
def live_match_stats_page(match_id: str) -> RedirectResponse:
    return RedirectResponse(url=f"/live/{match_id}", status_code=303)


def _admin_center_html(request: Request) -> HTMLResponse:
    user_row, current_club_id = _auth_user_from_token(_auth_token_from_request(request))
    if _effective_role_name(user_row, current_club_id) != "superadmin":
        raise HTTPException(status_code=403, detail="Only superadmin can open the admin center.")
    store = load_store()
    selected_club_id = str(request.query_params.get("club_id") or current_club_id or "").strip()
    club = _selected_club(store, selected_club_id)
    role = _effective_role_name(user_row, current_club_id)
    logger.debug(
        "Admin Center opened by %s for club %s.",
        user_row["display_name"] or user_row["mobile"] or "admin",
        club.get("name") or club.get("short_name") or selected_club_id or "",
    )
    notice = html.escape(str(request.query_params.get("notice") or "").strip())
    notice_tone = html.escape(str(request.query_params.get("tone") or "info").strip() or "info")

    def _review_assessment_bits(upload: dict[str, Any]) -> tuple[list[str], str]:
        assessment = upload.get("review_llm_assessment")
        if not isinstance(assessment, dict):
            return [], ""
        chips: list[str] = []
        if assessment.get("has_both_innings") is True:
            chips.append("Both innings found")
        if assessment.get("has_both_innings") is False:
            chips.append("Single innings only")
        duplicate_ids = [
            str(item).strip()
            for item in assessment.get("possible_duplicate_archive_ids", [])
            if str(item).strip()
        ]
        companion_ids = [
            str(item).strip()
            for item in assessment.get("possible_companion_archive_ids", [])
            if str(item).strip()
        ]
        if duplicate_ids:
            chips.append(f"Possible duplicates: {', '.join(duplicate_ids)}")
        if companion_ids:
            chips.append(f"Possible companion archives: {', '.join(companion_ids)}")
        review_notes = str(assessment.get("review_notes") or "").strip()
        if review_notes:
            chips.append(review_notes)
        details = " · ".join(chips)
        return chips, details

    def _review_summary_text(upload: dict[str, Any]) -> str:
        assessment = upload.get("review_llm_assessment")
        chips: list[str] = []
        if isinstance(assessment, dict):
            if assessment.get("has_both_innings") is True:
                chips.append("Both innings detected")
            if assessment.get("has_both_innings") is False:
                chips.append("Single innings only")
            duplicate_count = len(
                [
                    str(item).strip()
                    for item in assessment.get("possible_duplicate_archive_ids", [])
                    if str(item).strip()
                ]
            )
            companion_count = len(
                [
                    str(item).strip()
                    for item in assessment.get("possible_companion_archive_ids", [])
                    if str(item).strip()
                ]
            )
            if duplicate_count:
                chips.append(f"{duplicate_count} possible duplicate{'s' if duplicate_count != 1 else ''}")
            if companion_count:
                chips.append(f"{companion_count} possible companion archive{'s' if companion_count != 1 else ''}")
        if not chips and str(upload.get("review_llm_model") or "").strip():
            chips.append("LLM reviewed and enriched the template")
        return " · ".join(chips) or "Review the extracted JSON before approving."

    review_uploads: list[dict[str, Any]] = []
    for upload in canonical_archive_uploads(store.get("archive_uploads", [])):
        status = str(upload.get("status") or "").strip().lower()
        if status in {"approved", "applied to match", "deleted"}:
            continue
        club_ids, club_names = archive_club_context(upload, store.get("clubs", []), store.get("members", []), store.get("fixtures", []))
        inferred_club = _resolve_archive_club(upload, store.get("clubs", []))
        resolved_club_id = str((club_ids[0] if club_ids else upload.get("club_id")) or (inferred_club.get("id") if inferred_club else "") or "").strip()
        resolved_club_name = " / ".join(club_names) if club_names else str(upload.get("club_name") or (inferred_club.get("name") if inferred_club else "") or "Unassigned").strip() or "Unassigned"
        # superadmin sees every club's scorecards (grouped by club below), not just the selected club's
        review_uploads.append(
            {
                **upload,
                "resolved_club_id": resolved_club_id,
                "resolved_club_name": resolved_club_name,
                "resolved_club_ids": club_ids,
                "resolved_club_names": club_names,
            }
        )
    club_options = "\n".join(
        f'<option value="{html.escape(item["id"])}"{" selected" if item["id"] == selected_club_id else ""}>{html.escape(item["name"])} · {html.escape(item["season"] or "Season TBD")}</option>'
        for item in _sorted_club_choices(store, selected_club_id, include_disabled=True)
    )
    review_groups: dict[str, list[dict[str, Any]]] = {}
    for upload in review_uploads:
        key = f'{upload.get("resolved_club_id") or ""}::{upload.get("resolved_club_name") or "Unassigned"}'
        review_groups.setdefault(key, []).append(upload)
    club_id_value = str(club.get("id") or "").strip().lower()
    club_name_value = str(club.get("name") or "").strip().lower()
    club_short_name_value = str(club.get("short_name") or "").strip().lower()
    club_members = [
        member
        for member in store.get("members", [])
        if member_in_club(member, str(club.get("id") or ""), str(club.get("name") or ""))
    ]
    club_teams = [
        team
        for team in store.get("teams", []) or []
        if (
            club_id_value
            and str(team.get("club_id") or "").strip().lower() == club_id_value
        )
        or (
            club_name_value
            and str(team.get("club_name") or "").strip().lower() in {club_name_value, club_short_name_value}
        )
    ]
    club_status_html = (
        '<p class="status-banner error">Disabled · members cannot access this club.</p>'
        if _club_is_disabled(club)
        else '<p class="status-banner success">Active</p>'
    )
    club_toggle_html = (
        f'<form method="post" action="/api/admin/clubs/{html.escape(str(club.get("id") or ""))}/enable"><button class="secondary-button" type="submit">Re-enable club</button></form>'
        if _club_is_disabled(club)
        else f'''<form method="post" action="/api/admin/clubs/{html.escape(str(club.get("id") or ""))}/disable">
            <label class="stack-label">Type the exact club name to confirm disabling
              <input name="confirmation" type="text" placeholder="{html.escape(club.get('name') or '')}" autocomplete="off" required />
            </label>
            <button class="secondary-button" type="submit">Disable club</button>
          </form>'''
    )
    delete_blockers = _club_blocking_deletion(store, club)
    if any(delete_blockers.values()):
        delete_form_html = (
            '<p class="empty-state">This club cannot be deleted: it still has '
            + html.escape(_describe_deletion_blockers(delete_blockers))
            + ". A club can only be deleted when it has no matches and no players. Use Disable club to keep its history.</p>"
        )
    else:
        delete_form_html = f'''<form class="admin-delete-form" method="post" action="/api/admin/clubs/{html.escape(str(club.get('id') or ''))}/delete">
            <label class="stack-label">
              Type the exact club name to confirm deletion
              <input name="confirmation" type="text" placeholder="{html.escape(club.get('name') or '')}" autocomplete="off" required />
            </label>
            <button class="danger-button" type="submit">Delete club</button>
          </form>'''
    club_detail_html = (
        f"""
        <article class="detail-card admin-club-card" data-admin-club="{html.escape(str(club.get('id') or ''))}">
          <strong>{html.escape(club.get('name') or 'Selected club')}</strong>
          <p>{html.escape(club.get('short_name') or '')} · {html.escape(club.get('season') or 'Season TBD')}</p>
          {club_status_html}
          <small>{len(club_members)} players · {len(club_teams)} teams · {html.escape(club.get('city') or 'City TBD')} · {html.escape(club.get('country') or 'Country TBD')}</small>
          {club_toggle_html}
          {delete_form_html}
        </article>
        <article class="stack-card admin-roster-panel">
          <div class="panel-head compact-head">
            <div>
              <p class="section-kicker">Players</p>
              <h3>Club roster</h3>
            </div>
          </div>
          <div class="archive-list">
            {''.join(
                f'''
                  <article class="detail-card admin-member-card" data-admin-member="{html.escape(str(member.get("id") or ""))}">
                  <strong>{html.escape(member.get("name") or "Player")}</strong>
                  <p>{html.escape(member.get("full_name") or "")}</p>
                  <small>{html.escape(member.get("role") or "player")} · {html.escape(member.get("phone") or "No mobile")}</small>
                  <small>{html.escape(member.get("team_name") or "")}</small>
                  <form class="admin-delete-form" method="post" action="/api/admin/clubs/{html.escape(str(club.get('id') or ''))}/members/{html.escape(str(member.get('id') or ''))}/delete">
                    <label class="stack-label">
                      Type the exact player name to confirm unlinking from this club
                      <input name="confirmation" type="text" placeholder="{html.escape(member.get('name') or '')}" autocomplete="off" required />
                    </label>
                    <button class="danger-button" type="submit">Remove from club</button>
                  </form>
                </article>
                '''
                for member in club_members
            ) or '<p class="empty-state">No club members are linked to this club yet.</p>'}
          </div>
        </article>
        """
        if club else '<p class="empty-state">Select a club to manage its roster.</p>'
    )
    if review_uploads:
        rendered_groups: list[str] = []
        for group in review_groups.values():
            rendered_cards: list[str] = []
            for upload in group:
                template_value = upload.get("extraction_template") if isinstance(upload.get("extraction_template"), dict) else scorecard_template_from_archive(upload)
                template_text = str(upload.get("review_template_json") or "").strip() or json.dumps(template_value, indent=2)
                template_text = _json_with_match_ids(template_text, upload)
                llm_chips, llm_details = _review_assessment_bits(upload)
                review_llm_model = str(upload.get("review_llm_model") or "").strip()
                review_llm_notes = str(upload.get("review_llm_notes") or "").strip()
                review_summary = _review_summary_text(upload)
                llm_chip_html = "".join(
                    f'<span class="audit-chip">{html.escape(chip)}</span>'
                    for chip in llm_chips
                )
                raw_output_html = ""
                if review_llm_notes:
                    raw_output_html = (
                        "<details class=\"audit-raw-panel\">"
                        "<summary>View raw LLM output</summary>"
                        f"<pre class=\"audit-details\">{html.escape(review_llm_notes[:12000])}</pre>"
                        "</details>"
                    )
                rendered_cards.append(
                    f"""
                      <article class="detail-card" data-admin-upload="{html.escape(str(upload.get('id') or ''))}">
                        <strong>{html.escape(upload.get('file_name') or '')}</strong>
                        <p>Match ID <b>{html.escape(_match_code(upload.get('id')))}</b></p>
                        <p>{html.escape(upload.get('club_name') or upload.get('resolved_club_name') or 'Club TBD')} · {html.escape(upload.get('season') or 'Season TBD')}</p>
                        <small>{html.escape(upload.get('archive_date') or 'Date TBD')} · {html.escape(upload.get('status') or 'Pending review')}</small>
                        <p>{html.escape(upload.get('extracted_summary') or 'Review the extracted draft before approving.')}</p>
                        <small>{html.escape(f'LLM review: {review_llm_model}' if review_llm_model else 'LLM review pending')}</small>
                        <p class="audit-details">{html.escape(review_summary)}</p>
                        {f'<div class="audit-chip-row">{llm_chip_html}</div>' if llm_chip_html else ''}
                        {f'<p class="audit-details">{html.escape(llm_details)}</p>' if llm_details else ''}
                        {raw_output_html}
                        <div class="admin-review-workspace">
                          <section class="admin-scorecard-snapshot-panel">
                            <h4>Scorecard snapshot · Scorecards view</h4>
                            <div class="admin-scorecard-preview" data-scorecard-preview="{html.escape(str(upload.get('id') or ''))}">
                              <p class="empty-state">Loading scorecard snapshot…</p>
                            </div>
                          </section>
                          <form class="admin-review-form" method="post" action="/api/admin/archive/{html.escape(str(upload.get('id') or ''))}/review-form">
                            <label class="stack-label">
                              Reviewed extraction JSON
                              <textarea class="admin-review-text" name="text" rows="10" spellcheck="false">{html.escape(template_text)}</textarea>
                            </label>
                            <div class="inline-actions">
                              <button class="secondary-button" type="submit" data-action="save">Save review</button>
                              <button class="primary-button" type="submit" data-action="approve" formaction="/api/admin/archive/{html.escape(str(upload.get('id') or ''))}/approve-form">Approve</button>
                            </div>
                          </form>
                          <section class="admin-original-scorecard-image" data-scorecard-original="{html.escape(str(upload.get('id') or ''))}">
                            <p class="empty-state">Loading original image…</p>
                          </section>
                        </div>
                        <div class="inline-actions">
                          <button class="secondary-button" type="button" data-action="extract">Re-extract</button>
                          <button class="secondary-button" type="button" data-action="delete">Delete</button>
                        </div>
                      </article>
                    """
                )
            rendered_groups.append(
                f"""
                <section class="admin-review-group">
                  <div class="panel-head compact-head">
                    <div>
                      <p class="section-kicker">Club review queue</p>
                      <h3>{html.escape(group[0].get('resolved_club_name') or 'Unassigned')} · {len(group)}</h3>
                    </div>
                  </div>
                  <div class="archive-list">
                    {''.join(rendered_cards)}
                  </div>
                </section>
                """
            )
        review_queue_html = "".join(rendered_groups)
    else:
        review_queue_html = '<p class="empty-state">No archives match this club or search.</p>'
    body = f"""
    <!DOCTYPE html>
    <html lang="en">
      <head>
        <meta charset="UTF-8" />
        <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, viewport-fit=cover" />
        <script src="/assets/zoom_lock.js?v=20261014a"></script>
        <title>Admin center · CricketClubApp</title>
        <link rel="stylesheet" href="/assets/styles.css?v=20261102a" />
        <link rel="stylesheet" href="/assets/app_polish.css?v=20261006a" />
        <link rel="stylesheet" href="/assets/sports-system.css?v=20260926a" />
        <link rel="stylesheet" href="/assets/scorecards.css?v=20261111a" />
      </head>
      <body>
        <div class="page-shell">
          <header class="page-topbar"></header>
          <section class="panel onboarding-panel">
            <div class="stack-card">
              <p class="section-kicker">Admin center</p>
              <h1>{html.escape(club.get('name', 'Selected club'))} control room</h1>
              <div id="adminRoleBadge" class="hero-badge admin-role-badge">Loading role...</div>
              <p class="lede">Manage a club, then use the section menu to open visitor analytics, scorecards, archives, audit history, or fixtures.</p>
              <div id="adminCenterStatus" class="status-banner {notice_tone}"{" hidden" if not notice else ""}>{notice}</div>
            </div>

            <div class="detail-stack">
              <nav class="admin-section-nav" aria-label="Admin Center sections" role="tablist">
                <button class="secondary-button is-active" type="button" role="tab" aria-selected="true" aria-controls="adminSectionClubMaintenance" data-admin-section="club-maintenance">Club Maintenance</button>
                <button class="secondary-button" type="button" role="tab" aria-selected="false" aria-controls="adminSectionOverview" data-admin-section="overview">Overview</button>
                <button class="secondary-button" type="button" role="tab" aria-selected="false" aria-controls="adminSectionVisitors" data-admin-section="visitors">Unique Visitors</button>
                <button class="secondary-button" type="button" role="tab" aria-selected="false" aria-controls="adminSectionScorecards" data-admin-section="scorecards">Scorecard Tools</button>
                <button class="secondary-button" type="button" role="tab" aria-selected="false" aria-controls="adminSectionArchives" data-admin-section="archives">Archives</button>
                <button class="secondary-button" type="button" role="tab" aria-selected="false" aria-controls="adminSectionNameMatches" data-admin-section="name-matches">Name Matches</button>
                <button class="secondary-button" type="button" role="tab" aria-selected="false" aria-controls="adminSectionAudit" data-admin-section="audit">Audit Log</button>
                <button class="secondary-button" type="button" role="tab" aria-selected="false" aria-controls="adminSectionFixtures" data-admin-section="fixtures">Fixtures</button>
              </nav>
              <section class="admin-section" id="adminSectionClubMaintenance" data-admin-section-panel="club-maintenance" role="tabpanel">
                <div class="stack-card admin-controls-panel">
                  <div class="panel-head compact-head"><div><p class="section-kicker">Club Maintenance</p><h2>Manage clubs and rosters</h2></div></div>
                  <p class="lede">Superadmin only. Disable a club to preserve its history while blocking member access, re-enable it later, or permanently delete it.</p>
                  <form id="adminClubForm" class="toolbar-actions" method="get" action="/admin-center">
                    <select id="adminClubSelect" name="club_id">{club_options}</select>
                    <button id="adminLoadClubButton" class="secondary-button" type="submit">Load club</button>
                  </form>
                  <div id="adminClubDetail" class="detail-stack">{club_detail_html}</div>
                </div>
              </section>
              <section class="admin-section" id="adminSectionOverview" data-admin-section-panel="overview" role="tabpanel" hidden>
                <div class="stack-card"><div class="panel-head compact-head"><div><p class="section-kicker">Overview</p><h2>Club snapshot</h2></div></div><div class="summary-grid compact-summary-grid" id="adminClubStats"></div></div>
              </section>
              <section class="admin-section" id="adminSectionVisitors" data-admin-section-panel="visitors" role="tabpanel" hidden>
              <div class="stack-card" id="adminTrafficCard">
                <div class="panel-head compact-head">
                  <div>
                    <p class="section-kicker">Site audience</p>
                    <h2>Unique visitors</h2>
                  </div>
                  <button id="adminTrafficRefreshButton" class="secondary-button" type="button">Refresh</button>
                </div>
                <p class="lede">Distinct signed-in accounts or anonymous browsers, grouped in the {html.escape(APP_TIMEZONE)} time zone.</p>
                <div id="adminTrafficSummary" class="summary-grid compact-summary-grid"><p class="empty-state">Loading traffic...</p></div>
                <p id="adminTrafficPeak" class="lede"></p>
                <div class="toolbar-actions" role="group" aria-label="Visitor reporting period">
                  <button class="secondary-button" type="button" data-traffic-period="hourly">Hourly</button>
                  <button class="secondary-button" type="button" data-traffic-period="daily">Daily</button>
                  <button class="secondary-button" type="button" data-traffic-period="monthly">Monthly</button>
                  <button class="secondary-button" type="button" data-traffic-period="annually">Yearly</button>
                </div>
                <div id="adminTrafficSeries" class="archive-list"><p class="empty-state">Traffic will load after the page finishes loading.</p></div>
              </div>
              </section>
              <section class="admin-section" id="adminSectionScorecards" data-admin-section-panel="scorecards" role="tabpanel" hidden>
              <div class="stack-card" id="adminRereadCard" hidden>
                <div class="panel-head compact-head">
                  <div>
                    <p class="section-kicker">Scorecard photos</p>
                    <h2>Clean up and re-read all with AI</h2>
                  </div>
                </div>
                <p class="lede">Reads every scorecard photo again with the AI reader and runs the checks. About half a minute per photo; you can keep using the app.</p>
                <label style="display:flex;gap:10px;align-items:flex-start;margin:6px 0"><input type="checkbox" id="adminRereadCleanup" checked style="width:auto;margin-top:4px" /> Clean up first: delete uploads whose photo isn't on this computer and extra copies of the same photo, and add new photos from the img folder</label>
                <label style="display:flex;gap:10px;align-items:flex-start;margin:6px 0"><input type="checkbox" id="adminRereadSkip" style="width:auto;margin-top:4px" /> Skip cards already read by the newest AI reader (to continue after the daily free limit)</label>
                <label style="display:flex;gap:10px;align-items:flex-start;margin:6px 0"><input type="checkbox" id="adminRereadProblems" style="width:auto;margin-top:4px" /> Only cards with problems (runs or wickets don't add up, other team missing) - saves the free daily limit</label>
                <div class="toolbar-actions"><button id="adminRereadButton" class="primary-button" type="button">🤖 Re-read all scorecards</button> <a class="secondary-button" href="/admin/backups">🗄️ Database backups</a></div>
                <div id="adminRereadStatus" class="status-banner info" hidden></div>
              </div>
              </section>
              <section class="admin-section" id="adminSectionArchives" data-admin-section-panel="archives" role="tabpanel" hidden>
              <div class="stack-card">
                <div class="panel-head compact-head">
                  <div>
                    <p class="section-kicker">Archives</p>
                    <h2>Review queue</h2>
                  </div>
                </div>
                <div class="toolbar-actions">
                  <input id="adminArchiveSearch" type="search" placeholder="Search archived scorecards" />
                  <button id="adminRefreshButton" class="secondary-button" type="button">Refresh queue</button>
                </div>
                <div id="adminReviewQueue" class="detail-stack">{review_queue_html}</div>
              </div>
              <div class="stack-card">
                <div class="panel-head compact-head">
                  <div>
                    <p class="section-kicker">Players</p>
                    <h2>Name claims</h2>
                  </div>
                </div>
                <p>A player asked to add a name from a scorecard to their profile. Approving only adds it as an alias. No player records are merged or deleted.</p>
                <div id="adminNameClaims" class="detail-stack"><p class="empty-state">Loading name claims...</p></div>
              </div>
              </section>
              <section class="admin-section" id="adminSectionNameMatches" data-admin-section-panel="name-matches" role="tabpanel" hidden>
              <div class="stack-card">
                <div class="panel-head compact-head">
                  <div>
                    <p class="section-kicker">Players</p>
                    <h2>Name matches</h2>
                  </div>
                </div>
                <p>Read-only list of member records with the same or similar names, with their clubs. Nothing is merged, deleted or changed here except by the Merge buttons. Club admins see groups where all players belong to their clubs; superadmins see all groups.</p>
                <div id="adminNameMatches" class="detail-stack"><p class="empty-state">Loading name matches...</p></div>
              </div>
              <div class="stack-card">
                <div class="panel-head compact-head">
                  <div>
                    <p class="section-kicker">Players</p>
                    <h2>Merge requests</h2>
                  </div>
                </div>
                <p>Players who asked for two of their records to be merged. Approve merges the older record into the other one (undoable by a superadmin). Reject records the decision only.</p>
                <div id="adminMergeRequests" class="detail-stack"><p class="empty-state">Loading merge requests...</p></div>
              </div>
              </section>
              <section class="admin-section" id="adminSectionAudit" data-admin-section-panel="audit" role="tabpanel" hidden>
              <div class="stack-card">
                <div class="panel-head compact-head">
                  <div>
                    <p class="section-kicker">Audit</p>
                    <h2>Change history</h2>
                  </div>
                </div>
                <p class="lede">Track who added, reviewed, changed, or removed club data. This stays club-scoped so the history matches the club you selected.</p>
                <div class="toolbar-actions">
                  <button id="adminAuditRefreshButton" class="secondary-button" type="button">Refresh audit log</button>
                </div>
                <div id="adminAuditLog" class="detail-stack">
                  <p class="empty-state">Audit log will load after the page finishes loading.</p>
                </div>
              </div>
              </section>
              <section class="admin-section" id="adminSectionFixtures" data-admin-section-panel="fixtures" role="tabpanel" hidden>
              <div class="stack-card">
                <div class="panel-head compact-head">
                  <div>
                    <p class="section-kicker">Fixtures</p>
                    <h2>Fixture editor</h2>
                  </div>
                </div>
                <form id="adminFixtureForm" class="form-grid">
                  <input type="hidden" id="adminFixtureId" />
                  <input id="adminFixtureDateLabel" type="text" placeholder="Date label" />
                  <input id="adminFixtureDate" type="date" />
                  <input id="adminFixtureOpponent" type="text" placeholder="Opponent" />
                  <input id="adminFixtureVenue" type="text" placeholder="Venue" />
                  <input id="adminFixtureType" type="text" placeholder="Match type" />
                  <input id="adminFixtureTime" type="text" placeholder="Start time" />
                  <input id="adminFixtureOvers" type="text" placeholder="Overs" />
                  <input id="adminSeasonYear" type="number" placeholder="Season year" />
                  <button class="primary-button wide" type="submit">Save fixture</button>
                </form>
                <div id="adminFixtureList" class="detail-stack"></div>
              </div>
              </section>
            </div>
          </section>
        </div>
        <script src="/assets/multipage.js?v=20261025a"></script>
        <script src="/assets/scorecard_view.js?v=20261109a"></script>
        <script src="/assets/scorecard.js?v=20261111a"></script>
        <script src="/assets/admin_center.js?v=20261111d"></script>
        <script src="/assets/admin_reread.js?v=20261024a"></script>
      </body>
    </html>
    """
    return HTMLResponse(
        body,
        headers={
            "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
            "Pragma": "no-cache",
        },
    )


@app.get("/admin-center")
def admin_center_page(request: Request) -> Response:
    session = _require_page_session(request)
    if isinstance(session, RedirectResponse):
        return session
    try:
        token = _auth_token_from_request(request)
        user_row, current_club_id = _auth_user_from_token(token)
        store = load_store()
        club = _selected_club(store, str(request.query_params.get("club_id") or current_club_id or "").strip())
        logger.debug(
            "Admin Center page requested by %s for club %s.",
            user_row["display_name"] or user_row["mobile"] or "admin",
            club.get("name") or club.get("short_name") or current_club_id or "",
        )
    except Exception:
        logger.debug("Admin Center page requested.")
    return _admin_center_html(request)


@app.get("/admin")
def admin_page_alias(request: Request) -> Response:
    session = _require_page_session(request)
    if isinstance(session, RedirectResponse):
        return session
    return _admin_center_html(request)


@app.get("/signin/quick")
def signin_quick_page() -> HTMLResponse:
    return HTMLResponse(
        """
        <!DOCTYPE html>
        <html lang="en">
          <head>
            <meta charset="UTF-8" />
            <meta http-equiv="refresh" content="0; url=/signin" />
            <title>Sign In</title>
          </head>
          <body>
            <script>window.location.href = "/signin";</script>
            <p>Redirecting to sign in...</p>
          </body>
        </html>
        """,
        headers={
            "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
            "Pragma": "no-cache",
        },
    )


def _signin_redirect_page(token: str, club_id: str) -> HTMLResponse:
    safe_token = json.dumps(token)
    safe_club_id = json.dumps(club_id or "")
    return HTMLResponse(
        f"""
        <!DOCTYPE html>
        <html lang="en">
          <head>
            <meta charset="UTF-8" />
            <meta http-equiv="refresh" content="0; url=/clubs" />
            <title>Signing In</title>
          </head>
          <body>
            <script>
              window.localStorage.setItem("cricketClubAppAuthToken", {safe_token});
              window.sessionStorage.setItem("cricketClubAppPrimaryClubId", {safe_club_id});
              document.cookie = "cricketClubAppAuthToken=" + encodeURIComponent({safe_token}) + "; path=/; samesite=lax";
              window.location.href = "/clubs";
            </script>
            <p>Signing you in...</p>
          </body>
        </html>
        """
    )


def _signin_error_page(message: str) -> HTMLResponse:
    safe_message = json.dumps(message)
    return HTMLResponse(
        f"""
        <!DOCTYPE html>
        <html lang="en">
          <head>
            <meta charset="UTF-8" />
            <title>Sign In Failed</title>
          </head>
          <body>
            <script>
              const message = {safe_message};
              alert(message);
              window.location.href = "/signin";
            </script>
            <p>{message}</p>
            <p><a href="/signin">Back to sign in</a></p>
          </body>
        </html>
        """,
        status_code=401,
    )


def _player_season_availability(user_id: int, club_id: str) -> dict[str, str]:
    ensure_auth_schema()
    with _auth_connection() as connection:
        row = connection.execute(
            """
            SELECT status, note, updated_at
            FROM app_player_season_availability
            WHERE user_id = ? AND club_id = ?
            """,
            (user_id, club_id),
        ).fetchone()
    if not row:
        return {"status": "", "note": "", "updated_at": ""}
    return {
        "status": row["status"] or "",
        "note": row["note"] or "",
        "updated_at": row["updated_at"] or "",
    }


@app.get("/register")
def register_page() -> FileResponse:
    return _page_response("register.html")


@app.get("/clubs")
def clubs_page(request: Request, search: str = "", focus_club_id: str = "") -> Response:
    logger.debug("Clubs page opened. search=%s focus_club_id=%s", search or "", focus_club_id or "")
    session = _require_page_session(request)
    if isinstance(session, RedirectResponse):
        # Signed-out visitors get the public, read-only club list instead of the sign-in page.
        return _page_response("public_clubs.html")
    return _clubs_page_html(request, search, focus_club_id)


@app.post("/clubs/select")
def clubs_select(request: Request, club_id: str = Form(...), search: str = Form(default="")) -> Response:
    token = _auth_token_from_request(request)
    logger.debug("Club selected. club_id=%s search=%s token_present=%s", club_id or "", search or "", bool(token))
    if not token:
        return HTMLResponse(
            """
            <!DOCTYPE html>
            <html lang="en">
              <head>
                <meta charset="UTF-8" />
                <meta http-equiv="refresh" content="0; url=/signin" />
                <title>Sign In Required</title>
              </head>
              <body><p>Sign in first.</p></body>
            </html>
            """,
            status_code=401,
        )
    clubs_user_row, _ = _auth_user_from_token(token)
    store = load_store()
    selected_club = _selected_club(store, club_id)
    if _club_is_disabled(selected_club) and "superadmin" not in _user_role_names(clubs_user_row, str(selected_club.get("id") or "")):
        return HTMLResponse("This club is disabled. Contact a superadmin to restore access.", status_code=403)
    try:
        _require_multi_club(clubs_user_row, str(selected_club.get("id") or ""))
    except HTTPException:
        return RedirectResponse("/pricing?feature=multi_club", status_code=303)
    with _auth_connection() as connection:
        connection.execute(
            "UPDATE app_auth_sessions SET current_club_id = ? WHERE token = ?",
            (selected_club.get("id", "") or None, token),
        )
    response = RedirectResponse(url=f"/dashboard?focus_club_id={html.escape(selected_club.get('id', ''))}", status_code=303)
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    response.headers["Pragma"] = "no-cache"
    _set_auth_cookies(response, token, selected_club.get("id", "") or "")
    return response


@app.get("/signout")
def signout_page(request: Request) -> HTMLResponse:
    token = _auth_token_from_request(request)
    if token:
        try:
            load_store()
            with _auth_connection() as connection:
                _end_auth_session(connection, token)
        except Exception:
            logger.exception("Failed to close auth session during sign out.")
    response = HTMLResponse(
        """
        <!DOCTYPE html>
        <html lang="en">
          <head>
            <meta charset="UTF-8" />
            <meta http-equiv="refresh" content="0; url=/signin" />
            <title>Signing Out</title>
          </head>
          <body>
            <script>
              window.localStorage.removeItem("cricketClubAppAuthToken");
              window.sessionStorage.removeItem("cricketClubAppPrimaryClubId");
              window.sessionStorage.removeItem("cricketClubAppSessionState");
              window.location.href = "/signin";
            </script>
            <p>Signing you out...</p>
          </body>
        </html>
        """,
    )
    _clear_auth_cookies(response)
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    response.headers["Pragma"] = "no-cache"
    return response


@app.get("/season-setup")
def season_setup_page(request: Request) -> Response:
    locked = _paid_page_redirect(request, "schedule")
    if locked is not None:
        return locked
    return _season_setup_page_html(request)


@app.get("/player-availability")
def player_availability_page(request: Request) -> Response:
    session = _require_page_session(request)
    if isinstance(session, RedirectResponse):
        return session
    locked = _paid_page_redirect(request, "availability")
    if locked is not None:
        return locked
    return _page_response("player_availability.html")


@app.get("/matches")
def matches_page(request: Request) -> Response:
    """Menu item "Matches" (README: "Simple menu and app tour"): upcoming games plus availability.
    Pro (or a player whose captain is on Pro) -> /player-availability; everyone else -> /fixtures."""
    token = _auth_token_from_request(request)
    if token:
        try:
            user_row, current_club_id = _auth_user_from_token(token, touch=False)
        except HTTPException:
            user_row = None
        if user_row is not None and (
            _has_feature(user_row, current_club_id, "availability")
            or _club_is_paid(str(current_club_id or user_row["primary_club_id"] or ""))
        ):
            return RedirectResponse("/player-availability", status_code=303)
    return RedirectResponse("/fixtures", status_code=303)


@app.get("/profile")
@app.get("/player-profile")
def player_profile_page(request: Request) -> Response:
    session = _require_page_session(request)
    if isinstance(session, RedirectResponse):
        return session
    return _page_response("player_profile.html")


def _dashboard_page_html(request: Request, widget_name: str | None = None) -> HTMLResponse:
    logger.debug("Dashboard page opened. widget=%s", widget_name or "")
    session = _require_page_session(request)
    if isinstance(session, RedirectResponse):
        return session
    token = _auth_token_from_request(request)
    badge_html = ""
    body_attrs = ' data-can-manage="0" data-paid="0"'
    if token:
        try:
            user_row, current_club_id = _auth_user_from_token(token)
            user_payload = _auth_user_payload(
                user_row,
                current_club_id
                or str(request.query_params.get("focus_club_id") or "").strip(),
            )
            # Stats page (README "Stats: basic for everyone, more for Pro"): invite / add-performance forms only for
            # people who can manage players; season-by-season trends only for Pro (and site admins).
            permissions = set(user_payload.get("permissions") or [])
            role = str(user_payload.get("effective_role") or user_payload.get("role") or "")
            can_manage = role == "superadmin" or bool(permissions & {"manage_players", "manage_club"})
            paid = role == "superadmin" or str(user_payload.get("plan") or "free") != "free"
            body_attrs = f' data-can-manage="{1 if can_manage else 0}" data-paid="{1 if paid else 0}"'
            badge_html = _identity_badge_html(
                str(user_payload.get("display_name") or user_payload.get("email") or user_payload.get("mobile") or "Signed in"),
                str(user_payload.get("effective_role") or user_payload.get("role") or "Player"),
            )
        except Exception:
            badge_html = ""
    body = (STATIC_DIR / "index.html").read_text(encoding="utf-8")
    if widget_name:
        body = body.replace("<body>", f'<body data-dashboard-widget="{html.escape(widget_name)}"{body_attrs}>', 1)
    else:
        body = body.replace("<body>", f"<body{body_attrs}>", 1)
    if widget_name != "overview":
        body = re.sub(
            r"\s*<section class=\"panel template-shell glass dashboard-hero-panel\">.*?</section>\s*",
            "\n",
            body,
            count=1,
            flags=re.S,
        )
    if badge_html:
        body = body.replace(
            '<div id="userIdentityBadge" class="user-chip" aria-live="polite" hidden></div>',
            badge_html,
        )
    return HTMLResponse(
        body,
        headers={
            "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
            "Pragma": "no-cache",
        },
    )


@app.get("/dashboard")
def dashboard_page(request: Request) -> Response:
    return _dashboard_page_html(request, "overview")


@app.get("/dashboard/widgets/performance")
def dashboard_performance_page(request: Request) -> Response:
    return _dashboard_page_html(request, "performance")


@app.get("/dashboard/widgets/performances")
def dashboard_performances_page(request: Request) -> Response:
    return _dashboard_page_html(request, "performance")


@app.get("/dashboard/widgets/{widget_name}")
def dashboard_widget_page(request: Request, widget_name: str) -> Response:
    widget_aliases = {
        "club-performance": "performance",
        "performances": "performance",
        "fixtures": "schedule",
        "upcoming-fixtures": "schedule",
        "availability": "availability",
        "playing-xi": "match-center",
        "rankings": "performance",
        "players": "player-profile",
        "profile": "player-profile",
        "player-profile": "player-profile",
        "assistant": "assistant",
        "scorecards": "archive",
        "scoring": "scoring",
        "commentary": "commentary",
        "squad": "squad",
        "archive": "archive",
        "match-center": "match-center",
        "teams": "teams",
        "schedule": "schedule",
        "more": "more",
    }
    normalized = str(widget_name or "").strip().lower()
    target_widget = widget_aliases.get(normalized)
    if not target_widget:
        raise HTTPException(status_code=404, detail="Unknown dashboard widget.")
    locked = _paid_page_redirect(request, target_widget)
    if locked is not None:
        return locked
    if target_widget == "player-profile":
        return _page_response("player_profile.html")
    return _dashboard_page_html(request, target_widget)


@app.get("/api/health")
def health() -> dict[str, Any]:
    return {"status": "ok", "llm": get_llm_status()}


@app.get("/api/dashboard")
def dashboard(
    request: Request,
    focus_club_id: str | None = None,
    selected_season_year: str | None = None,
) -> dict[str, Any]:
    token = _auth_token_from_request(request)
    store = load_store()
    resolved_focus_club_id = (
        focus_club_id
        or None
    )
    requested_season_year = (
        str(selected_season_year or request.query_params.get("selected_season_year") or "").strip()
        or str(request.cookies.get("cricketClubAppSelectedSeasonYear") or "").strip()
        or str(datetime.utcnow().year)
    )
    logger.debug(
        "Dashboard loaded. focus_club_id=%s resolved_focus_club_id=%s selected_season_year=%s",
        focus_club_id or "",
        resolved_focus_club_id or "",
        requested_season_year,
    )
    user_row = None
    current_club_id = ""
    if token:
        try:
            user_row, current_club_id = _auth_user_from_token(token)
        except Exception:
            user_row = None
            current_club_id = ""
    resolved_focus_club_id = current_club_id or resolved_focus_club_id
    dashboard_data = current_dashboard(store, resolved_focus_club_id, requested_season_year)
    for member_list_key in ("members", "all_members"):
        if isinstance(dashboard_data.get(member_list_key), list):
            dashboard_data[member_list_key] = [
                {key: value for key, value in member.items() if key != "date_of_birth"}
                for member in dashboard_data[member_list_key]
                if isinstance(member, dict)
            ]
    if user_row:
        dashboard_data["user"] = _auth_user_payload(user_row, current_club_id or resolved_focus_club_id or "")
    return dashboard_data


@app.get("/api/auth/options")
def auth_options() -> dict[str, Any]:
    store = load_store()
    if _register_played_fixture_teams(store):
        try:
            save_store(store)
        except Exception:
            logger.exception("Saving registered clubs and players failed")
    linked_member_ids: set[str] = set()
    linked_member_name_keys: set[str] = set()
    with _auth_connection() as connection:
        roles = _role_catalog(connection)
        # Do not expose internal/sensitive roles in the public options
        roles = [r for r in roles if str(r.get("role_name") or "") != "superadmin"]
        linked_member_ids = {
            str(row["member_id"]).strip()
            for row in connection.execute(
                "SELECT member_id FROM app_users WHERE member_id IS NOT NULL AND TRIM(member_id) != ''"
            ).fetchall()
            if str(row["member_id"] or "").strip()
        }
    for member in store.get("members", []):
        if str(member.get("id") or "").strip() not in linked_member_ids:
            continue
        for value in [member.get("name"), member.get("full_name"), *(member.get("aliases", []) or [])]:
            normalized = normalize_name(str(value or ""))
            if normalized:
                linked_member_name_keys.add(normalized)

    def member_club_names(member: dict[str, Any]) -> list[str]:
        names = {
            str(item.get("club_name") or "").strip()
            for item in member.get("club_memberships", []) or []
            if isinstance(item, dict) and str(item.get("club_name") or "").strip()
        }
        names.update(
            str(item.get("club_name") or item.get("display_name") or "").strip()
            for item in member.get("team_memberships", []) or []
            if isinstance(item, dict)
            and str(item.get("club_name") or item.get("display_name") or "").strip()
        )
        return sorted(names, key=str.casefold)

    return {
        "clubs": _sorted_club_choices(store, str(store.get("viewer_profile", {}).get("primary_club_id") or "")),
        "members": [
            {
                "id": member.get("id", ""),
                "player_id": member.get("player_id", ""),
                "name": member.get("name", ""),
                "full_name": member.get("full_name", ""),
                "team_name": member.get("team_name", ""),
                "club_names": member_club_names(member),
            }
            for member in store.get("members", [])
            if str(member.get("id") or "").strip() not in linked_member_ids
            and normalize_name(str(member.get("name") or "")) not in linked_member_name_keys
            and normalize_name(str(member.get("full_name") or "")) not in linked_member_name_keys
        ],
        "roles": roles,
    }


_GENERIC_TEAM_NAMES = {"", "club", "opponent", "opposition", "team", "team 1", "team 2", "home", "away", "visitors", "tbd", "unknown"}


def _published_scorecard_matches(store: dict[str, Any]) -> list[dict[str, Any]]:
    """Nov 3 2026 (Amit): published scorecard uploads register their clubs and players too (e.g. "Amit CC" from
    a photo), the same way scored fixtures do. Each one becomes a fixture-like row for _register_played_fixture_teams."""
    rows: list[dict[str, Any]] = []
    anchors = side_anchors(store.get("archive_uploads"))
    for upload in store.get("archive_uploads", []) or []:
        if not isinstance(upload, dict):
            continue
        published = _archive_scorecard_is_published(upload)
        if not published and _scorecard_text(upload.get("status")).lower() in {"rejected", "duplicate", "deleted"}:
            continue
        try:
            card = _scorecard_from_archive(upload)
        except Exception:
            continue
        if not published and not card.get("innings"):
            continue  # an unread photo has no team names to register
        teams = [re.sub(r"\s+", " ", str(team or "").strip()) for team in card.get("teams") or []]
        teams = [team for team in teams if normalize_name(team) not in _GENERIC_TEAM_NAMES]
        # imported cards can omit team names: take them from the card's two clubs and its "won by" result
        inferred = inferred_innings_teams_for_archive(upload) if len(teams) < 2 else {}
        if inferred:
            teams = [inferred[0][0], inferred[0][1]]
        # "Coca Cola" on a card is the existing "Coca Cola XI" club, not a new one
        existing = [club for club in store.get("clubs", []) or [] if isinstance(club, dict)]

        def registered_name(team: Any) -> str:
            team = re.sub(r"\s+", " ", str(team or "").strip())
            if not team:
                return team
            return next(
                (str(club.get("name")) for club in existing if club.get("name") and (_same_team_name(team, club.get("name")) or _same_team_name(team, club.get("short_name")))),
                team,
            )

        raw_teams = list(teams)
        teams = [registered_name(team) for team in teams]
        # Nov 5 2026 (Amit 11 = Amit CC): the innings labels must use the same registered club names as the card's
        # teams, otherwise "Amit 11" batters fall back to the uploader's club (Heartlake) when the card is approved.
        same_side = {normalize_name(raw): name for raw, name in zip(raw_teams, teams)}

        def side_name(team: Any) -> str:
            key = normalize_name(str(team or ""))
            return same_side.get(key) or registered_name(team) if key else ""
        if len(teams) < 2 or normalize_name(teams[0]) == normalize_name(teams[1]):
            continue
        uploader_club = _club_by_identifier(store.get("clubs", []), str(upload.get("club_id") or "")) or {}
        home, opponent = teams[0], teams[1]
        if uploader_club and _club_match_key(teams[1]) in _club_identity_keys(uploader_club):
            home, opponent = teams[1], teams[0]
        home_is_uploader = bool(uploader_club) and _club_match_key(home) in _club_identity_keys(uploader_club)
        innings = []
        specs = []
        for index, item in enumerate(card.get("innings") or []):
            fallback_bat, fallback_bowl = inferred.get(index, ("", ""))
            specs.append((
                str(item.get("team") or fallback_bat),
                str(item.get("bowling_team") or fallback_bowl),
                [row.get("name") for row in item.get("batting") or [] if row.get("name")],
                [row.get("name") for row in item.get("bowling") or [] if row.get("name")],
            ))
        # a card whose team labels contradict the players' known teams is read with the sides swapped
        swapped = card_sides_are_swapped(specs, anchors)
        for item, (bat_team, bowl_team, _batters, _bowlers) in zip(card.get("innings") or [], specs):
            if swapped:
                bat_team, bowl_team = bowl_team, bat_team
            bat_team, bowl_team = side_name(bat_team), side_name(bowl_team)
            innings.append({
                "batting_team": bat_team,
                "bowling_team": bowl_team,
                "_players": {
                    "batting": [{"player_name": row.get("name")} for row in item.get("batting") or [] if row.get("name")],
                    "bowling": [{"player_name": row.get("name")} for row in item.get("bowling") or [] if row.get("name")],
                },
            })
        rows.append({
            "id": f"scorecard-{upload.get('id')}",
            "club_id": str(uploader_club.get("id") or "") if home_is_uploader else "",
            "club_name": home,
            "opponent": opponent,
            "scorebook": {"innings": innings},
            "_from_scorecard": True,
            "_clubs_only": not published,
        })
    return rows


def _repair_typed_club_links(store: dict[str, Any]) -> bool:
    """Link players to registered clubs they only have as typed text (e.g. "Amit CC" typed on the profile, which
    reloads as a team with no club). Returns True when a link was added."""
    changed = False
    for member in store.get("members", []) or []:
        typed = [
            item
            for item in member.get("team_memberships") or []
            if not isinstance(item, dict)
            or (not str(item.get("club_id") or "").strip() and str(item.get("team_type") or "") != "club")
        ]
        if typed and _add_member_clubs_by_name(store, member, typed):
            changed = True
    return changed


def _register_played_fixture_teams(store: dict[str, Any]) -> bool:
    """Make clubs and players from scored fixtures available in registration."""
    # repair profiles saved before Nov 4 2026, whose club links were replaced by typed names ("Amit CC")
    changed = _repair_typed_club_links(store)
    played_for: dict[str, set[str]] = {}
    played_against: dict[str, set[str]] = {}

    def club_for_team(team_name: str, fallback: dict[str, Any]) -> dict[str, Any]:
        clean_name = re.sub(r"\s+", " ", str(team_name or "").strip())
        key = normalize_name(clean_name)
        if key in home_team_keys:
            return home_club
        if key in opponent_team_keys:
            return opponent_club
        return _find_club_by_name(store, clean_name) or fallback

    for fixture in [*(store.get("fixtures", []) or []), *_published_scorecard_matches(store)]:
        if not isinstance(fixture, dict) or not (fixture.get("_from_scorecard") or _fixture_has_recorded_score_data(fixture)):
            continue

        home_name = str(fixture.get("club_name") or fixture.get("team_name") or "").strip()
        opponent_name = str(fixture.get("visiting_team") or fixture.get("opponent") or "").strip()
        if not home_name or not opponent_name or normalize_name(home_name) == normalize_name(opponent_name):
            continue

        home_club = _find_club_by_name(store, str(fixture.get("club_id") or "")) or _find_club_by_name(store, home_name)
        if not home_club:
            home_club, created = _create_club_record(
                store,
                home_name,
                "",
                "",
                about="Automatically registered from a played fixture.",
            )
            changed = changed or created

        opponent_club = _find_club_by_name(store, opponent_name)
        if not opponent_club:
            opponent_club, created = _create_club_record(
                store,
                opponent_name,
                "",
                "",
                about="Automatically registered from a played fixture.",
            )
            changed = changed or created

        home_club_name = str(home_club.get("name") or home_name).strip()
        opponent_club_name = str(opponent_club.get("name") or opponent_name).strip()
        home_team_keys = {
            normalize_name(value)
            for value in (
                home_name,
                home_club_name,
                home_club.get("short_name"),
                home_club.get("id"),
                "club",
                "heartlake",
            )
            if normalize_name(str(value or ""))
        }
        opponent_team_keys = {
            normalize_name(value)
            for value in (
                opponent_name,
                opponent_club_name,
                opponent_club.get("short_name"),
                opponent_club.get("id"),
                "opponent",
                "visiting team",
            )
            if normalize_name(str(value or ""))
        }

        team_rows = store.setdefault("teams", [])
        for club in (home_club, opponent_club):
            club_id = str(club.get("id") or "").strip()
            team_name = str(club.get("short_name") or club.get("name") or "").strip()
            if not any(
                str(team.get("club_id") or "").strip() == club_id
                or (
                    not team.get("club_id")
                    and normalize_name(str(team.get("name") or "")) == normalize_name(team_name)
                )
                for team in team_rows
                if isinstance(team, dict)
            ):
                team_rows.append(
                    {
                        "name": team_name,
                        "type": "club",
                        "display_name": str(club.get("name") or team_name),
                        "club_id": club_id,
                        "club_name": str(club.get("name") or team_name),
                    }
                )
                changed = True

        # Nov 4 2026 (Amit CC vs Heartlake, 2024): a scorecard still waiting for approval registers its clubs, but
        # players and memberships only come from approved cards (a misread name must not create a player).
        if fixture.get("_clubs_only"):
            continue

        players_by_club: dict[str, set[str]] = {
            str(home_club.get("id") or ""): set(),
            str(opponent_club.get("id") or ""): set(),
        }
        scorebook = fixture.get("scorebook") or {}
        innings_list = scorebook.get("innings", []) if isinstance(scorebook, dict) else []
        for index, innings in enumerate(innings_list):
            if not isinstance(innings, dict):
                continue
            default_batting_club = home_club if index % 2 == 0 else opponent_club
            default_bowling_club = opponent_club if default_batting_club is home_club else home_club
            batting_club = club_for_team(
                str(innings.get("batting_team") or ""),
                default_batting_club,
            )
            bowling_club = club_for_team(
                str(innings.get("bowling_team") or ""),
                default_bowling_club,
            )
            summary = innings.get("_players") or summarize_innings_scorebook(innings)
            for row in summary.get("batting", []):
                name = re.sub(r"\s+", " ", str(row.get("player_name") or "").strip())
                if name:
                    players_by_club.setdefault(str(batting_club.get("id") or ""), set()).add(name)
            for row in summary.get("bowling", []):
                name = re.sub(r"\s+", " ", str(row.get("player_name") or "").strip())
                if name:
                    players_by_club.setdefault(str(bowling_club.get("id") or ""), set()).add(name)
            for ball in innings.get("balls", []) or []:
                if not isinstance(ball, dict):
                    continue
                fielder = re.sub(r"\s+", " ", str(ball.get("fielder") or "").strip())
                if fielder:
                    players_by_club.setdefault(str(bowling_club.get("id") or ""), set()).add(fielder)

        lineups = {} if fixture.get("_from_scorecard") else _match_lineups(str(fixture.get("id") or ""))
        for name in lineups.get("club", []):
            clean_name = re.sub(r"\s+", " ", str(name or "").strip())
            if clean_name:
                players_by_club.setdefault(str(home_club.get("id") or ""), set()).add(clean_name)
        for name in lineups.get("opponent", []):
            clean_name = re.sub(r"\s+", " ", str(name or "").strip())
            if clean_name:
                players_by_club.setdefault(str(opponent_club.get("id") or ""), set()).add(clean_name)

        home_id, opponent_id = str(home_club.get("id") or ""), str(opponent_club.get("id") or "")
        for side_id, side_names in players_by_club.items():
            for side_name in side_names:
                played_for.setdefault(normalize_name(side_name), set()).add(side_id)
                played_against.setdefault(normalize_name(side_name), set()).add(opponent_id if side_id == home_id else home_id)

        for club in (home_club, opponent_club):
            club_id = str(club.get("id") or "").strip()
            club_name = str(club.get("name") or "").strip()
            team_name = str(club.get("short_name") or club_name).strip()
            for player_name in sorted(players_by_club.get(club_id, set()), key=str.casefold):
                member = next(
                    (item for item in store.get("members", []) if _member_matches_name(item, player_name)),
                    None,
                )
                if member is None:
                    member = {
                        "id": str(uuid.uuid4()),
                        "name": player_name,
                        "full_name": player_name,
                        "team_name": team_name,
                        "aliases": [],
                        "age": 0,
                        "role": "Player",
                        "batting_style": "",
                        "bowling_style": "",
                        "notes": "Auto-added from a played scorebook.",
                        "picture": member_initials(player_name),
                        "picture_url": "",
                        "phone": "",
                        "email": "",
                        "jersey_number": "",
                        "primary_club_id": club_id,
                        "primary_club_name": club_name,
                        "team_memberships": [],
                        "club_memberships": [],
                    }
                    store.setdefault("members", []).append(member)
                    changed = True

                current_player_id = str(member.get("player_id") or "").strip()
                if len(current_player_id) != 4 or not current_player_id.isdigit():
                    member["player_id"] = ""
                    changed = True
                memberships = member.get("team_memberships", [])
                if isinstance(memberships, str):
                    memberships = [item.strip() for item in memberships.split(",") if item.strip()]
                elif not isinstance(memberships, list):
                    memberships = []
                member["team_memberships"] = memberships
                matching_membership = next(
                    (
                        item
                        for item in memberships
                        if isinstance(item, dict)
                        and (
                            str(item.get("club_id") or "").strip() == club_id
                            or (
                                not str(item.get("club_id") or "").strip()
                                and normalize_name(
                                    str(item.get("club_name") or item.get("team_name") or item.get("display_name") or "")
                                )
                                == normalize_name(club_name)
                            )
                        )
                    ),
                    None,
                )
                if matching_membership is None:
                    existing_team_name = normalize_name(str(member.get("team_name") or ""))
                    has_primary_club = (
                        bool(str(member.get("primary_club_id") or "").strip())
                        or any(
                            isinstance(item, dict) and item.get("is_primary") and item.get("club_id")
                            for item in memberships
                        )
                        or existing_team_name not in {"", "club"}
                    )
                    memberships.append(
                        {
                            "team_name": team_name,
                            "display_name": club_name or team_name,
                            "club_id": club_id,
                            "club_name": club_name,
                            "team_type": "club",
                            "is_primary": not has_primary_club,
                        }
                    )
                    if not has_primary_club:
                        member["team_name"] = team_name
                        member["primary_club_id"] = club_id
                        member["primary_club_name"] = club_name
                    changed = True
                else:
                    for field, value in (
                        ("team_name", team_name),
                        ("display_name", club_name or team_name),
                        ("club_id", club_id),
                        ("club_name", club_name),
                        ("team_type", "club"),
                    ):
                        if str(matching_membership.get(field) or "").strip() != value:
                            matching_membership[field] = value
                            changed = True

                club_memberships = member.setdefault("club_memberships", [])
                if not isinstance(club_memberships, list):
                    club_memberships = []
                    member["club_memberships"] = club_memberships
                if not any(
                    isinstance(item, dict)
                    and (
                        str(item.get("club_id") or "").strip() == club_id
                        or normalize_name(str(item.get("club_name") or "")) == normalize_name(club_name)
                    )
                    for item in club_memberships
                ):
                    club_memberships.append(
                        {"club_id": club_id, "club_name": club_name, "teams": [team_name]}
                    )
                    changed = True

    # A club a player only played AGAINST is not theirs (e.g. Amit S played for Coca Cola XI vs TP Community):
    # drop that link unless it is their primary club or a club they typed on their profile.
    for member in store.get("members", []) or []:
        member_keys = {normalize_name(str(value)) for value in (member.get("name"), member.get("full_name"), *(member.get("aliases") or [])) if value}
        for_ids = set().union(*(played_for.get(key, set()) for key in member_keys)) if member_keys else set()
        against_ids = set().union(*(played_against.get(key, set()) for key in member_keys)) if member_keys else set()
        wrong_ids = {
            club_id
            for club_id in against_ids - for_ids
            if club_id and club_id != str(member.get("primary_club_id") or "").strip()
        }
        if not wrong_ids:
            continue
        typed_keys = {
            normalize_name(str(item if not isinstance(item, dict) else item.get("team_name") or item.get("display_name") or ""))
            for item in member.get("team_memberships") or []
            if not isinstance(item, dict) or (not str(item.get("club_id") or "").strip() and str(item.get("team_type") or "") != "club")
        }
        for club_id in wrong_ids:
            wrong_club = _club_by_identifier(store.get("clubs", []), club_id) or {}
            if typed_keys & {normalize_name(str(wrong_club.get(key) or "")) for key in ("name", "short_name")} - {""}:
                continue
            for field in ("club_memberships", "team_memberships"):
                kept = [item for item in member.get(field) or [] if not (isinstance(item, dict) and str(item.get("club_id") or "").strip() == club_id and not item.get("is_primary"))]
                if len(kept) != len(member.get(field) or []):
                    member[field] = kept
                    changed = True

    # a club typed on a profile ("Amit CC") may only have been registered just now from a scorecard
    changed = _repair_typed_club_links(store) or changed
    # Nov 4 2026: a scorecard belongs to the clubs of both teams (e.g. Heartlake AND Amit CC), so it
    # shows under both clubs and counts in both clubs' stats (each player only for the side they played for).
    # One still waiting for approval is linked too, so the other club's admin sees it in the review queue.
    for upload in store.get("archive_uploads", []) or []:
        if not isinstance(upload, dict) or _scorecard_text(upload.get("status")).lower() in {"rejected", "duplicate", "deleted"}:
            continue
        try:
            card = _scorecard_from_archive(upload)
        except Exception:
            continue
        ids = [str(item) for item in upload.get("club_ids") or [] if item]
        for team in card.get("teams") or []:
            if normalize_name(str(team or "")) in _GENERIC_TEAM_NAMES:
                continue
            club = _find_club_by_name(store, str(team)) or next(
                (item for item in store.get("clubs", []) or [] if _same_team_name(team, item.get("name")) or _same_team_name(team, item.get("short_name"))),
                None,
            )
            if club and str(club.get("id")) not in ids:
                ids.append(str(club["id"]))
        if ids != [str(item) for item in upload.get("club_ids") or [] if item]:
            upload["club_ids"] = ids
            changed = True

    if changed:
        save_store(store)
        saved_ids = {str(item.get("id") or ""): str(item.get("player_id") or "") for item in load_store().get("members", [])}
        for item in store.get("members", []):
            if str(item.get("id") or "") in saved_ids:
                item["player_id"] = saved_ids[str(item.get("id") or "")]
    return changed


@app.get("/api/auth/roles")
def auth_roles() -> dict[str, Any]:
    ensure_auth_schema()
    with _auth_connection() as connection:
        return {"roles": _role_catalog(connection)}

@app.post("/api/auth/register")
def register(request: RegisterRequest, response: Response) -> dict[str, Any]:
    ensure_auth_schema()

    logger.debug("Registration started.")

    try:
        # -----------------------------
        # ✅ VALIDATION
        # -----------------------------
        if not request.mobile.strip() and not request.email.strip():
            raise HTTPException(status_code=400, detail="Register with mobile or email.")

        if len(request.password.strip()) < 4:
            raise HTTPException(status_code=400, detail="Password must be at least 4 characters.")

        # -----------------------------
        # ✅ LOAD STORE
        # -----------------------------
        store = load_store()

        # -----------------------------
        # ✅ ROLE
        # -----------------------------
        raw_roles = request.roles if request.roles is not None else request.role
        if isinstance(raw_roles, str):
            requested_roles = [item.strip() for item in re.split(r"[,\n;|]", raw_roles) if item.strip()]
        elif isinstance(raw_roles, list):
            requested_roles = [str(item or "").strip() for item in raw_roles if str(item or "").strip()]
        else:
            requested_roles = []
        if not requested_roles:
            requested_roles = [request.role or "player"]
        requested_roles = [_normalize_role_name(role) for role in requested_roles if _normalize_role_name(role)]
        if not requested_roles:
            requested_roles = ["player"]
        role = requested_roles[0]
        if role == "superadmin":
            raise HTTPException(status_code=403, detail="Superadmin registration is reserved for Amit S / Amit Sethi.")

        # -----------------------------
        # ✅ NAME NORMALIZATION
        # -----------------------------
        raw_name = request.member_name or request.display_name or ""
        input_name = raw_name.strip()
        normalized_input = normalize_name(input_name)

        logger.debug("Registration input received. input=%s normalized=%s", input_name or "", normalized_input or "")

        requested_club_id = str(request.primary_club_id or "").strip()
        requested_club_name = str(request.club_name or "").strip()
        requested_club_city = str(request.club_city or "").strip()
        requested_club_country = str(request.club_country or "").strip()
        selected_club = None
        created_club = False

        if requested_club_id:
            selected_club = next(
                (
                    club
                    for club in store.get("clubs", [])
                    if str(club.get("id") or "").strip().lower() == requested_club_id.lower()
                ),
                None,
            )
        if not selected_club and requested_club_name:
            selected_club = _find_club_by_name(store, requested_club_name)
        if not selected_club and requested_club_name:
            if not requested_club_city or not requested_club_country:
                raise HTTPException(status_code=400, detail="Add club name, city, and country to create a new club.")
            selected_club, created_club = _create_club_record(store, requested_club_name, requested_club_city, requested_club_country)
            requested_club_id = str(selected_club.get("id") or "").strip()
        if not selected_club:
            raise HTTPException(status_code=400, detail="Select an existing club or add a new club.")
        if not requested_club_id:
            requested_club_id = str(selected_club.get("id") or "").strip()

        effective_role = max(requested_roles, key=_role_rank)
        if created_club and role in {"player", "captain", "club_admin", "admin"}:
            effective_role = "club_admin"

        member = None
        member_id = None
        member_to_create = None  # 🔥 IMPORTANT

        requested_member_key = str(request.member_id or request.player_id or "").strip().lower()
        if requested_member_key:
            member = next(
                (
                    item for item in store.get("members", [])
                    if requested_member_key in {
                        str(item.get("id") or "").strip().lower(),
                        str(item.get("player_id") or "").strip().lower(),
                    }
                ),
                None,
            )
            if not member:
                raise HTTPException(status_code=404, detail="Player ID not found. Check the ID or create a new player profile.")

        if input_name and not member:
            resolved_name = resolve_member_name(store, input_name)
            member = next(
                (
                    m
                    for m in store.get("members", [])
                    if _member_matches_name(m, resolved_name)
                    or _member_matches_name(m, input_name)
                ),
                None,
            )

        if member:
            aliases = [str(alias or "").strip() for alias in (member.get("aliases") or []) if str(alias or "").strip()]
            requested_aliases = request.aliases.split(",") if isinstance(request.aliases, str) else request.aliases
            known_aliases = {normalize_name(str(member.get("name") or "")), *(normalize_name(alias) for alias in aliases)}
            for alias in [input_name, *(str(item or "").strip() for item in requested_aliases or [])]:
                if alias and normalize_name(alias) not in known_aliases:
                    aliases.append(alias)
                    known_aliases.add(normalize_name(alias))
            if aliases != member.get("aliases", []):
                member["aliases"] = aliases
                save_store(store)

        # -----------------------------
        # ✅ PREPARE MEMBER (DO NOT SAVE YET)
        # -----------------------------
        if not member:
            display_name = request.display_name.strip() or input_name or "Player"
            normalized_display = normalize_name(display_name)
            requested_aliases = request.aliases.split(",") if isinstance(request.aliases, str) else request.aliases
            aliases = [str(item or "").strip() for item in requested_aliases or [] if str(item or "").strip()]
            if input_name and normalize_name(input_name) != normalized_display:
                aliases.append(input_name)

            new_member_id = str(uuid.uuid4())
            member_to_create = {
                "id": new_member_id,
                "player_id": "",
                "name": display_name,
                "normalized_name": normalized_display,
                "full_name": display_name,
                "aliases": aliases,
                "role": role,
                "date_of_birth": _validated_date_of_birth(request.date_of_birth),
                "created_at": now_iso(),
            }

            logger.debug("Registration member prepared. member=%s", display_name or "")

        # -----------------------------
        # ✅ MOBILE / EMAIL
        # -----------------------------
        mobile = "".join(filter(str.isdigit, request.mobile.strip() if request.mobile else ""))
        email = request.email.strip().lower()

        if mobile and len(mobile) < 10:
            raise HTTPException(status_code=400, detail="Invalid mobile number")

        token = secrets.token_urlsafe(24)

        # -----------------------------
        # ✅ DB TRANSACTION
        # -----------------------------
        with _auth_connection() as connection:

            # check existing user
            existing = connection.execute(
                "SELECT * FROM app_users WHERE mobile = ? OR email = ?",
                (mobile or None, email or None),
            ).fetchone()

            existing_user_for_member = None
            reusable_existing_user = existing if existing and not existing["member_id"] else None
            if existing and existing["member_id"]:
                raise HTTPException(status_code=409, detail="User already exists.")

            # -----------------------------
            # ✅ CREATE MEMBER NOW (SAFE POINT)
            # -----------------------------
            if member_to_create:
                store.setdefault("members", []).append(member_to_create)
                save_store(store)
                saved_member = next((item for item in load_store().get("members", []) if str(item.get("id") or "") == str(member_to_create.get("id") or "")), None)
                if saved_member:
                    member_to_create.update(saved_member)
                member = member_to_create
                logger.info("Member created during registration. member=%s", member["name"])

            if member:
                member_id = member.get("id")
                if request.date_of_birth.strip():
                    member["date_of_birth"] = _validated_date_of_birth(request.date_of_birth)
                    save_store(store)

            if created_club and member:
                _attach_creator_to_club(store, selected_club, member)
                save_store(store)

            existing_user_for_member = reusable_existing_user or _existing_user_for_member(connection, member_id or "")
            if existing_user_for_member and not reusable_existing_user:
                raise HTTPException(status_code=409, detail="This Player ID is already linked to an account. Sign in to use that profile.")

            # -----------------------------
            # ✅ CREATE OR REUSE USER
            # -----------------------------
            if existing_user_for_member:
                user_id = int(existing_user_for_member["id"])
                connection.execute(
                    """
                    UPDATE app_users
                    SET display_name = ?, mobile = ?, email = ?, role = ?, member_id = ?, player_id = ?, primary_club_id = ?
                    WHERE id = ?
                    """,
                    (
                        request.display_name.strip() or input_name or existing_user_for_member["display_name"],
                        mobile or None,
                        email or None,
                        effective_role,
                        member_id,
                        str(member.get("player_id") or ""),
                        requested_club_id or None,
                        user_id,
                    ),
                )
            else:
                cursor = connection.execute(
                    """
                    INSERT INTO app_users (
                      display_name, mobile, email, password_hash, role, member_id, player_id, primary_club_id, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        request.display_name.strip() or input_name or "User",
                        mobile or None,
                        email or None,
                        _password_hash(request.password.strip()),
                        effective_role,
                        member_id,
                        str(member.get("player_id") or ""),
                        requested_club_id or None,
                        now_iso(),
                    ),
                )

                user_id = int(cursor.lastrowid)

            club_role_names = [role_name for role_name in requested_roles if role_name in {"captain", "club_admin"}]
            if created_club and "club_admin" not in club_role_names:
                club_role_names.append("club_admin")
            for club_role_name in club_role_names:
                connection.execute(
                    """
                    INSERT INTO app_user_club_roles (user_id, club_id, role_name, created_at)
                    VALUES (?, ?, ?, ?)
                    ON CONFLICT(user_id, club_id, role_name) DO UPDATE SET
                      created_at = excluded.created_at
                    """,
                    (
                        user_id,
                        requested_club_id,
                        club_role_name,
                        now_iso(),
                    ),
                )

            connection.execute(
                """
                INSERT INTO app_auth_sessions (token, user_id, current_club_id, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (token, user_id, requested_club_id or None, now_iso()),
            )

            user_row = connection.execute(
                "SELECT * FROM app_users WHERE id = ?", (user_id,)
            ).fetchone()

        # -----------------------------
        # ✅ RESPONSE
        # -----------------------------
        _set_auth_cookies(response, token, requested_club_id)

        logger.info("Registration done by %s. user_id=%s club_id=%s", user_row["display_name"] or user_row["mobile"] or "user", user_id, requested_club_id or "")
        _audit_event(
            "auth.register",
            "user",
            str(user_id),
            actor=user_row,
            club_id=requested_club_id or "",
            club_name=str(selected_club.get("name") or ""),
            details={
                "display_name": request.display_name.strip() or input_name or "",
                "role": effective_role,
                "mobile": mobile,
                "email": email,
            },
            source="api",
        )

        return {
            "token": token,
            "user": _auth_user_payload(user_row, requested_club_id),
            "member": member,
            "clubs": _sorted_club_choices(load_store(), requested_club_id),
        }

    # -----------------------------
    # ❌ ERROR HANDLING (FIXED)
    # -----------------------------
    except sqlite3.IntegrityError as e:
        logger.warning("Registration integrity error. %s", str(e))

        raise HTTPException(
            status_code=409,
            detail="Duplicate member or user."
        )

    except Exception:
        logger.exception("Registration failed.")

        raise HTTPException(
            status_code=500,
            detail="Registration failed due to server error."
        )

@app.post("/api/auth/signin")
def signin(request: SignInRequest, response: Response) -> dict[str, Any]:
    ensure_auth_schema()

    identifier = (request.identifier or "").strip()
    password = (request.password or "").strip()
    player_name = (request.player_name or "").strip()

    logger.debug("Sign in attempt. identifier=%s player=%s", identifier or "", player_name or "")

    identifier_phone_candidates = _auth_identifier_candidates(identifier) if identifier and "@" not in identifier else []
    identifier_email = identifier.lower() if "@" in identifier else ""

    with _auth_connection() as connection:
        user_row = None

        if password:
            logger.debug("Trying password login.")

            if identifier_phone_candidates:
                mobile_clause = ", ".join("?" for _ in identifier_phone_candidates)
                user_row = connection.execute(
                    f"""
                    SELECT * FROM app_users
                    WHERE (mobile IN ({mobile_clause}) OR lower(email) = lower(?))
                      AND password_hash = ?
                    """,
                    (*identifier_phone_candidates, identifier_email or None, _password_hash(password)),
                ).fetchone()
            else:
                user_row = connection.execute(
                    """
                    SELECT * FROM app_users
                    WHERE lower(email) = lower(?)
                      AND password_hash = ?
                    """,
                    (identifier_email or None, _password_hash(password)),
                ).fetchone()

            if user_row:
                logger.debug("Login done by %s. method=password user_id=%s", user_row["display_name"] or user_row["mobile"] or "user", user_row["id"])

        if not user_row:
            logger.debug("Trying direct user lookup.")

            if identifier_phone_candidates:
                mobile_clause = ", ".join("?" for _ in identifier_phone_candidates)
                user_row = connection.execute(
                    f"""
                    SELECT * FROM app_users
                    WHERE mobile IN ({mobile_clause}) OR lower(email) = lower(?)
                    ORDER BY id
                    LIMIT 1
                    """,
                    (*identifier_phone_candidates, identifier_email or None),
                ).fetchone()
            else:
                user_row = connection.execute(
                    """
                    SELECT * FROM app_users
                    WHERE lower(email) = lower(?)
                    ORDER BY id
                    LIMIT 1
                    """,
                    (identifier_email or None,),
                ).fetchone()

            if user_row:
                logger.debug("Login done by %s. method=direct user_id=%s", user_row["display_name"] or user_row["mobile"] or "user", user_row["id"])

        if not user_row and player_name:
            logger.debug("Falling back to player name lookup.")

            store = _safe_load_store_for_auth("signin.member_lookup")
            resolved_name = resolve_member_name(store, player_name)
            normalized_input = normalize_name(resolved_name)

            member = next(
                (
                    m for m in store.get("members", [])
                    if normalize_name(m.get("name")) == normalized_input
                ),
                None,
            )

            if member:
                logger.debug("Member matched for sign in. member=%s", member.get("name") or "")

                primary_club = _primary_club_for_member(store, member)

                existing_user = connection.execute(
                    """
                    SELECT * FROM app_users
                    WHERE member_id = ?
                    ORDER BY id
                    LIMIT 1
                    """,
                    (member.get("id", ""),),
                ).fetchone()

                if existing_user:
                    logger.debug("Existing user reused for sign in. user_id=%s", existing_user["id"])
                    user_row = existing_user

                else:
                    logger.debug("Creating user from matched member.")

                    cursor = connection.execute(
                        """
                    INSERT INTO app_users (
                          display_name, mobile, email, password_hash, role, member_id, player_id, primary_club_id, created_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            member.get("full_name") or member.get("name"),
                            identifier_phone_candidates[0] if identifier_phone_candidates else None,
                            identifier_email or None,
                            _password_hash(secrets.token_urlsafe(24)),
                            "player",
                            member.get("id"),
                            str(member.get("player_id") or ""),
                            primary_club.get("id") if primary_club else None,
                            now_iso(),
                        ),
                    )

                    user_row = connection.execute(
                        "SELECT * FROM app_users WHERE id = ?",
                        (int(cursor.lastrowid),),
                    ).fetchone()

        if not user_row:
            logger.warning("Login failed.")
            raise HTTPException(
                status_code=401,
                detail="Invalid sign-in. Use mobile/email or player name."
            )

        token = secrets.token_urlsafe(24)
        current_club_id = user_row["primary_club_id"] or ""

        connection.execute(
            """
            INSERT INTO app_auth_sessions (token, user_id, current_club_id, created_at)
            VALUES (?, ?, ?, ?)
            """,
            (token, int(user_row["id"]), current_club_id or None, now_iso()),
        )
        _touch_auth_session(connection, token, force=True)
        session_state = _session_snapshot(connection, token) or {
            "created_at": now_iso(),
            "last_seen_at": now_iso(),
            "ended_at": "",
            "activity_count": 0,
            "timeout_minutes": SESSION_TIMEOUT_MINUTES,
            "elapsed_seconds": 0,
            "idle_seconds": 0,
            "active": True,
        }

    logger.info("Login done by %s. user_id=%s club_id=%s", user_row["display_name"] or user_row["mobile"] or "user", user_row["id"], current_club_id or "")
    _audit_event(
        "auth.signin",
        "user",
        str(user_row["id"]),
        actor=user_row,
        club_id=current_club_id or "",
        club_name="",
        details={
            "method": "password" if password else ("direct" if identifier_phone_candidates or identifier_email else "member"),
            "identifier": identifier,
            "player_name": player_name,
        },
        source="api",
    )

    _set_auth_cookies(response, token, current_club_id)

    store = _safe_load_store_for_auth("signin.post_auth")

    return {
        "token": token,
        "user": _auth_user_payload(user_row, current_club_id),
        "clubs": _visible_club_choices_for_user(store, user_row, current_club_id),
        "visible_clubs": _visible_club_choices_for_user(store, user_row, current_club_id),
        # Nov 4 2026 (Amit): the clubs this person belongs to / played for (primary first) - for a superadmin too,
        # whose "clubs" list is every club
        "my_clubs": _visible_club_choices_for_user(store, user_row, current_club_id, all_for_superadmin=False),
        "session": session_state,
    }

@app.post("/signin/quick")
def signin_quick_form(
    identifier: str = Form(...),
    password: str = Form(default=""),
    player_name: str = Form(default=""),
) -> HTMLResponse:
    logger.debug(
        "Quick sign in started. identifier=%s player=%s",
        identifier,
        player_name
    )

    try:
        # ✅ Call signin logic
        result = signin(
            SignInRequest(
                identifier=identifier,
                password=password,
                player_name=player_name,
            ),
            Response(),  # internal response (not used for cookies)
        )

        token = str(result.get("token") or "")
        user = result.get("user", {})

        club_id = str(
            user.get("current_club_id")
            or user.get("primary_club_id")
            or ""
        )

        logger.debug(
            "Quick sign in completed. user_id=%s club=%s",
            user.get("id"),
            club_id
        )

        # ✅ Create redirect response
        redirect = _signin_redirect_page(token, club_id)

        # ✅ Set cookies ONLY here (correct place)
        _set_auth_cookies(redirect, token, club_id)

        return redirect

    except HTTPException as exc:
        logger.warning("Quick sign in failed. %s", exc.detail)
        return _signin_error_page(str(exc.detail))

    except Exception:
        logger.exception("Quick sign in unexpected error.")
        return _signin_error_page("Unexpected error during sign-in")

@app.get("/api/auth/me")
def auth_me(x_auth_token: str | None = Header(default=None)) -> dict[str, Any]:
    user_row, current_club_id = _auth_user_from_token(x_auth_token)
    logger.debug("Auth profile requested. user_id=%s current_club_id=%s", user_row["id"], current_club_id or "")
    store = _safe_load_store_for_auth("auth.me")
    session_state = None
    if x_auth_token:
        with _auth_connection() as connection:
            session_state = _session_snapshot(connection, x_auth_token)
    return {
        "user": _auth_user_payload(user_row, current_club_id),
        "clubs": _visible_club_choices_for_user(store, user_row, current_club_id),
        "visible_clubs": _visible_club_choices_for_user(store, user_row, current_club_id),
        # Nov 4 2026 (Amit): the clubs this person belongs to / played for (primary first) - for a superadmin too,
        # whose "clubs" list is every club
        "my_clubs": _visible_club_choices_for_user(store, user_row, current_club_id, all_for_superadmin=False),
        "session": session_state,
    }


# App tour after the first sign-in (README "Simple menu and app tour"): remembered per account, so it shows
# once per person, not once per browser. `can_score` picks the steps (captains / club admins / site admins).
def _tour_table(connection: sqlite3.Connection) -> None:
    connection.execute(
        "CREATE TABLE IF NOT EXISTS app_tour_seen (user_id INTEGER PRIMARY KEY, seen_at TEXT NOT NULL)"
    )


@app.get("/api/tour")
def tour_status(x_auth_token: str | None = Header(default=None)) -> dict[str, Any]:
    user_row, current_club_id = _auth_user_from_token(x_auth_token, touch=False)
    with _auth_connection() as connection:
        _tour_table(connection)
        row = connection.execute("SELECT seen_at FROM app_tour_seen WHERE user_id = ?", (int(user_row["id"]),)).fetchone()
    permissions = _user_permissions(user_row, current_club_id)
    return {
        "seen": bool(row),
        "can_score": "score_matches" in permissions,
        "has_club": bool(current_club_id or user_row["primary_club_id"]),
        "name": (user_row["display_name"] or "").split(" ")[0],
    }


@app.post("/api/tour/seen")
def tour_seen(x_auth_token: str | None = Header(default=None)) -> dict[str, Any]:
    user_row, _ = _auth_user_from_token(x_auth_token, touch=False)
    with _auth_connection() as connection:
        _tour_table(connection)
        connection.execute(
            "INSERT OR IGNORE INTO app_tour_seen (user_id, seen_at) VALUES (?, ?)", (int(user_row["id"]), now_iso())
        )
        connection.commit()
    return {"ok": True}


@app.post("/api/auth/signout")
def auth_signout(request: Request, x_auth_token: str | None = Header(default=None)) -> dict[str, Any]:
    token = _auth_token_from_request(request, x_auth_token)
    if token:
        try:
            load_store()
            with _auth_connection() as connection:
                _end_auth_session(connection, token)
        except Exception:
            logger.exception("Failed to close auth session via api sign out.")
    response = JSONResponse({"ok": True})
    _clear_auth_cookies(response)
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    response.headers["Pragma"] = "no-cache"
    return response


@app.post("/api/auth/select-club")
def select_club(request: SelectClubRequest, x_auth_token: str | None = Header(default=None)) -> dict[str, Any]:
    user_row, _ = _auth_user_from_token(x_auth_token)
    store = load_store()
    selected_club = _selected_club(store, request.club_id)
    if _club_is_disabled(selected_club) and "superadmin" not in _user_role_names(user_row, str(selected_club.get("id") or "")):
        raise HTTPException(status_code=403, detail="This club is disabled. Contact a superadmin to restore access.")
    _require_multi_club(user_row, str(selected_club.get("id") or ""))
    logger.debug(
        "Selected club saved. user_id=%s club_id=%s club_name=%s",
        user_row["id"],
        selected_club.get("id", ""),
        selected_club.get("name", ""),
    )
    with _auth_connection() as connection:
        connection.execute(
            "UPDATE app_auth_sessions SET current_club_id = ? WHERE token = ?",
            (selected_club.get("id", "") or None, x_auth_token),
        )
    _audit_event(
        "club.select",
        "club",
        str(selected_club.get("id") or ""),
        actor=user_row,
        club_id=str(selected_club.get("id") or ""),
        club_name=str(selected_club.get("name") or ""),
        details={"source": "api", "selected_by": user_row["display_name"] or user_row["mobile"] or "user"},
        source="api",
    )
    return {
        "user": _auth_user_payload(user_row, selected_club.get("id", "")),
        "club": selected_club,
        "clubs": _visible_club_choices_for_user(store, user_row, selected_club.get("id", "")),
        "dashboard": current_dashboard(store, selected_club.get("id", "")),
    }


@app.post("/api/viewer-profile")
def update_viewer_profile(request: ViewerProfileRequest) -> dict[str, Any]:
    store = load_store()
    viewer_profile = dict(store.get("viewer_profile", {}))
    selected_season_year = str(request.selected_season_year or viewer_profile.get("selected_season_year") or "").strip()
    if not re.match(r"20\d{2}$", selected_season_year):
        selected_season_year = str(datetime.utcnow().year)
    viewer_profile.update(
        {
            "display_name": request.display_name.strip(),
            "mobile": canonical_phone(request.mobile),
            "email": request.email.strip(),
            "primary_club_id": request.primary_club_id.strip() or viewer_profile.get("primary_club_id", ""),
            "selected_season_year": selected_season_year,
        }
    )
    selected_club = next(
        (club for club in store.get("clubs", []) if club.get("id") == viewer_profile.get("primary_club_id")),
        store.get("club", {}),
    )
    viewer_profile["primary_club_name"] = selected_club.get("name", viewer_profile.get("primary_club_name", ""))
    store["viewer_profile"] = viewer_profile
    save_store(store)
    return current_dashboard(store, viewer_profile.get("primary_club_id"), selected_season_year)


@app.post("/api/viewer-profile/follow-player")
def follow_player(request: FollowPlayerRequest) -> dict[str, Any]:
    store = load_store()
    player_name = resolve_member_name(store, request.player_name)
    if not any(member.get("name") == player_name for member in store.get("members", [])):
        raise HTTPException(status_code=404, detail="Player not found.")
    viewer_profile = dict(store.get("viewer_profile", {}))
    followed = list(viewer_profile.get("followed_player_names", []) or [])
    if request.following:
        if player_name not in followed:
            followed.append(player_name)
    else:
        followed = [name for name in followed if name != player_name]
    viewer_profile["followed_player_names"] = followed
    store["viewer_profile"] = viewer_profile
    save_store(store)
    return current_dashboard(store, viewer_profile.get("primary_club_id"))


@app.get("/api/season-setup/data")
def season_setup_data(
    x_auth_token: str | None = Header(default=None),
    club_id: str | None = None,
) -> dict[str, Any]:
    user_row, current_club_id = _auth_user_from_token(x_auth_token)
    store = load_store()
    club = _selected_club(store, str(club_id or "").strip() or current_club_id)
    scoped = scoped_store_for_club(store, club)
    fixtures = sorted(scoped.get("fixtures", []), key=lambda fixture: (str(fixture.get("date") or ""), str(fixture.get("opponent") or "")))
    current_year = str(datetime.utcnow().year)
    season_years = {
        fixture_season_year(fixture)
        for fixture in fixtures
        if fixture_season_year(fixture)
    }
    season_years.add(current_year)
    viewer_selected_year = str(store.get("viewer_profile", {}).get("selected_season_year") or "").strip()
    if re.match(r"20\d{2}$", viewer_selected_year):
        season_years.add(viewer_selected_year)
    selected_year = current_year
    if not re.match(r"20\d{2}$", selected_year):
        selected_year = str(MIN_SEASON_SETUP_YEAR)
    season_years = sorted(
        {str(year).strip() for year in season_years if str(year).strip()},
        reverse=True,
    )
    if selected_year not in season_years:
        season_years = sorted({*season_years, selected_year}, reverse=True)
    fixtures = [
        {
            **fixture,
            "can_delete_incomplete": bool(
                not _fixture_is_completed(fixture)
                and _match_delete_is_authorized(store, user_row, current_club_id, fixture)
            ),
        }
        for fixture in fixtures
    ]
    return {
        "user": _auth_user_payload(user_row, current_club_id),
        "club": club,
        "fixtures": fixtures,
        "season_years": season_years,
        "selected_year": selected_year,
        "clubs": _sorted_club_choices(store, club.get("id", "")),
    }


def _fixture_identity_value(value: Any) -> str:
    return " ".join(str(value or "").strip().lower().split())


def _fixture_matches_identity(existing: dict[str, Any], club_id: str, request: SeasonFixtureRequest) -> bool:
    return (
        _fixture_identity_value(existing.get("club_id") or "") == _fixture_identity_value(club_id)
        and _fixture_identity_value(existing.get("date") or "") == _fixture_identity_value(request.date)
        and _fixture_identity_value(existing.get("opponent") or "") == _fixture_identity_value(request.opponent)
        and _fixture_identity_value(existing.get("details", {}).get("scheduled_time") or "")
        == _fixture_identity_value(request.scheduled_time)
    )


@app.post("/api/season-setup/fixtures")
def create_season_fixture(request: SeasonFixtureRequest, x_auth_token: str | None = Header(default=None)) -> dict[str, Any]:
    user_row, current_club_id = _require_permission(x_auth_token, "manage_fixtures")
    store = load_store()
    club = _selected_club(store, request.club_id or current_club_id)
    club_name = str(club.get("name") or club.get("short_name") or "Club").strip() or "Club"
    club_short_name = str(club.get("short_name") or club_name).strip() or club_name
    logger.debug(
        "Season fixture create requested. club_id=%s club_name=%s season_year=%s date=%s opponent=%s actor=%s",
        club.get("id", ""),
        club.get("name", ""),
        request.season_year,
        request.date,
        request.opponent,
        user_row["display_name"] or user_row["mobile"] or "user",
    )
    season_year = int(request.season_year)
    if season_year < MIN_SEASON_SETUP_YEAR:
        raise HTTPException(
            status_code=400,
            detail=f"Season setup is only available for {MIN_SEASON_SETUP_YEAR} and later.",
        )
    duplicate_fixture = next(
        (
            fixture
            for fixture in store.get("fixtures", [])
            if _fixture_matches_identity(fixture, str(club.get("id") or ""), request)
        ),
        None,
    )
    if duplicate_fixture:
        raise HTTPException(
            status_code=409,
            detail=(
                f"Fixture already exists for {club.get('name', 'selected club')} "
                f"on {request.date_label or request.date} vs {request.opponent} "
                f"at {request.scheduled_time or 'the selected time'}."
            ),
        )
    season_label = f"{season_year} Season"
    created_at = now_iso()

    new_fixture = {
        "id": str(uuid.uuid4())[:8],
        "club_id": club.get("id", ""),
        "club_name": club_name,
        "club_short_name": club_short_name,
        "season_year": str(season_year),
        "season": season_label,
        "date": request.date,
        "date_label": request.date_label,
        "opponent": request.opponent.strip(),
        "visiting_team": request.opponent.strip(),
        "heartlake_captain": "",
        "availability_seed": [],
        "availability_statuses": {},
        "availability_notes": {},
        "heartlake_score": "",
        "opponent_score": "",
        "result": "TBD",
        "status": "Scheduled",
        "commentary": [],
        "created_at": created_at,
        "updated_at": created_at,
        "details": {
            "venue": request.venue.strip(),
            "match_type": request.match_type.strip() or "Friendly",
            "scheduled_time": request.scheduled_time.strip(),
            "overs": request.overs.strip() or "20",
            "toss_winner": "",
            "toss_decision": "",
            "weather": "",
            "umpires": "",
            "scorer": "",
            "whatsapp_thread": "",
            "notes": "",
        },
        "scorecard": default_scorecard("TBD"),
        "performances": [],
        "scorebook": default_match_scorebook(
            {
                "club_name": club_name,
                "club_short_name": club_short_name,
                "opponent": request.opponent.strip(),
                "details": {"overs": request.overs.strip() or "20"},
            }
        ),
    }
    _touch_fixture_audit(new_fixture, user_row, created=True)
    store.setdefault("fixtures", []).append(new_fixture)
    save_store(store)
    logger.info(
        "Season fixture saved. club=%s season_year=%s date=%s opponent=%s fixture_id=%s",
        club.get("name", ""),
        season_year,
        request.date,
        request.opponent,
        new_fixture["id"],
    )
    _audit_event(
        "fixture.create",
        "fixture",
        new_fixture["id"],
        actor=user_row,
        club_id=club.get("id", ""),
        club_name=club.get("name", ""),
        details={
            "date_label": request.date_label,
            "date": request.date,
            "opponent": request.opponent,
            "season_year": season_year,
            "match_type": request.match_type,
        },
        source="api",
    )
    if request.notify:
        _announce_new_fixture(new_fixture)
    return season_setup_data(x_auth_token, str(club.get("id") or ""))


@app.put("/api/admin/clubs/{club_id}/fixtures/{fixture_id}")
def update_season_fixture(
    club_id: str,
    fixture_id: str,
    request: SeasonFixtureRequest,
    x_auth_token: str | None = Header(default=None),
) -> dict[str, Any]:
    user_row, _ = _require_permission(x_auth_token, "manage_fixtures")
    store = load_store()
    club = _selected_club(store, club_id)
    club_name = str(club.get("name") or club.get("short_name") or "Club").strip() or "Club"
    club_short_name = str(club.get("short_name") or club_name).strip() or club_name
    season_year = int(request.season_year)
    if season_year < MIN_SEASON_SETUP_YEAR:
        raise HTTPException(
            status_code=400,
            detail=f"Season setup is only available for {MIN_SEASON_SETUP_YEAR} and later.",
        )
    fixture = next(
        (
            item
            for item in store.get("fixtures", [])
            if str(item.get("id") or "").strip() == fixture_id
            and str(item.get("club_id") or "").strip() == str(club.get("id") or "").strip()
        ),
        None,
    )
    if fixture is None:
        raise HTTPException(status_code=404, detail="Fixture not found.")
    fixture_date = str(fixture.get("date") or "").strip()
    if fixture_date:
        try:
            fixture_day = date.fromisoformat(fixture_date)
        except ValueError:
            fixture_day = None
        if fixture_day and fixture_day < _current_local_date():
            raise HTTPException(
                status_code=400,
                detail="Past fixtures cannot be edited.",
            )
    duplicate_fixture = next(
        (
            item
            for item in store.get("fixtures", [])
            if str(item.get("id") or "").strip() != fixture_id
            and _fixture_matches_identity(item, str(club.get("id") or ""), request)
        ),
        None,
    )
    if duplicate_fixture:
        raise HTTPException(
            status_code=409,
            detail=(
                f"Fixture already exists for {club.get('name', 'selected club')} "
                f"on {request.date_label or request.date} vs {request.opponent} "
                f"at {request.scheduled_time or 'the selected time'}."
            ),
        )
    before = (
        str(fixture.get("date") or ""),
        str((fixture.get("details") or {}).get("scheduled_time") or "").strip(),
        str((fixture.get("details") or {}).get("venue") or "").strip(),
    )
    fixture.update(
        {
            "club_id": club.get("id", ""),
            "club_name": club_name,
            "club_short_name": club_short_name,
            "season_year": str(season_year),
            "season": f"{season_year} Season",
            "date": request.date,
            "date_label": request.date_label,
            "opponent": request.opponent.strip(),
            "visiting_team": request.opponent.strip(),
            "details": {
                **(fixture.get("details") or {}),
                "venue": request.venue.strip(),
                "match_type": request.match_type.strip() or "Friendly",
                "scheduled_time": request.scheduled_time.strip(),
                "overs": request.overs.strip() or "20",
            },
        }
    )
    _touch_fixture_audit(fixture, user_row)
    save_store(store)
    _audit_event(
        "fixture.update",
        "fixture",
        fixture_id,
        actor=user_row,
        club_id=club.get("id", ""),
        club_name=club.get("name", ""),
        details={
            "date_label": request.date_label,
            "date": request.date,
            "opponent": request.opponent,
            "season_year": season_year,
            "match_type": request.match_type,
        },
        source="api",
    )
    after = (str(request.date or ""), request.scheduled_time.strip(), request.venue.strip())
    changes = [label for label, old, new in zip(("date", "time", "ground"), before, after) if old != new]
    if changes:
        _announce_fixture_change(fixture, " and ".join(changes))
    return season_setup_data(x_auth_token, club_id)


@app.delete("/api/admin/clubs/{club_id}/fixtures/{fixture_id}")
def delete_season_fixture(
    club_id: str,
    fixture_id: str,
    finished: bool = False,
    x_auth_token: str | None = Header(default=None),
) -> dict[str, Any]:
    user_row, current_club_id = _auth_user_from_token(x_auth_token)
    store = load_store()
    try:
        match = get_match_or_404(store, fixture_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    if str(match.get("club_id") or "").strip() != str(club_id).strip():
        raise HTTPException(status_code=404, detail="Fixture not found.")
    if not _match_delete_is_authorized(store, user_row, current_club_id, match):
        raise HTTPException(status_code=403, detail="Only the club captain, club admin, or superadmin can delete this fixture.")
    club = _selected_club(store, club_id)
    fixture = next(
        (
            item
            for item in store.get("fixtures", [])
            if str(item.get("id") or "").strip() == fixture_id
            and str(item.get("club_id") or "").strip() == str(club.get("id") or "").strip()
        ),
        None,
    )
    if fixture is None:
        raise HTTPException(status_code=404, detail="Fixture not found.")
    if _fixture_is_completed(fixture) and not finished:
        # Nov 2 2026 (Amit): wrong finished scorecards can be removed too, but only when asked for on purpose.
        raise HTTPException(status_code=409, detail="This match is finished. Confirm that you want to delete a finished match.")
    before = len(store.get("fixtures", []))
    store["fixtures"] = [
        item
        for item in store.get("fixtures", [])
        if not (
            str(item.get("id") or "").strip() == fixture_id
            and str(item.get("club_id") or "").strip() == str(club.get("id") or "").strip()
        )
    ]
    if len(store.get("fixtures", [])) == before:
        raise HTTPException(status_code=404, detail="Fixture not found.")
    save_store(store)
    _audit_event(
        "fixture.delete",
        "fixture",
        fixture_id,
        actor=user_row,
        club_id=club.get("id", ""),
        club_name=club.get("name", ""),
        details={
            "date_label": (fixture or {}).get("date_label") or (fixture or {}).get("date") or "",
            "opponent": (fixture or {}).get("opponent") or "",
        },
        source="api",
    )
    return season_setup_data(x_auth_token, club_id)


def _member_appeared_in_fixture(
    member: dict[str, Any] | None,
    fixture: dict[str, Any],
    club: dict[str, Any] | None = None,
) -> bool:
    if not member or not _fixture_has_recorded_score_data(fixture):
        return False
    aliases = member.get("aliases") or []
    if not isinstance(aliases, list):
        aliases = [aliases]
    member_names = {
        normalize_name(value)
        for value in [member.get("name"), member.get("full_name"), *aliases]
        if str(value or "").strip()
    }
    if not member_names:
        return False
    innings_rows = (fixture.get("scorebook") or {}).get("innings") or []
    if innings_rows:
        for innings in innings_rows:
            batting_side = not club or _scorebook_is_club_side(fixture, innings.get("batting_team", ""), club)
            bowling_side = not club or _scorebook_is_club_side(fixture, innings.get("bowling_team", ""), club)
            for ball in innings.get("balls") or []:
                participants = []
                if batting_side:
                    participants.extend((ball.get("striker"), ball.get("non_striker"), ball.get("wicket_player"), ball.get("new_batter")))
                if bowling_side:
                    participants.extend((ball.get("bowler"), ball.get("fielder")))
                if any(normalize_name(name) in member_names for name in participants if str(name or "").strip()):
                    return True
            summary = summarize_innings_scorebook(innings)
            if batting_side and any(
                normalize_name(row.get("player_name")) in member_names
                for row in summary.get("batting") or []
                if str(row.get("status") or "").lower() != "not_batted"
            ):
                return True
            if bowling_side and any(
                normalize_name(row.get("player_name")) in member_names
                for row in summary.get("bowling") or []
                if int(row.get("legal_balls") or 0) > 0 or int(row.get("runs_conceded") or 0) > 0
            ):
                return True
        return False
    return any(
        normalize_name(row.get("player_name")) in member_names
        for row in fixture.get("performances") or []
        if isinstance(row, dict) and str(row.get("player_name") or "").strip()
    )


@app.get("/api/player/availability-data")
def player_availability_data(x_auth_token: str | None = Header(default=None)) -> dict[str, Any]:
    user_row, current_club_id = _auth_user_from_token(x_auth_token)
    store = load_store()
    club = _selected_club(store, current_club_id)
    active_year = club_season_year(club)
    member = _member_for_user(store, user_row)
    changed = False
    fixtures = []
    for fixture in _club_stat_fixtures(store, club):
        played = _member_appeared_in_fixture(member, fixture, club) if member else False
        is_past = _fixture_is_past(fixture)
        fixture_view = _club_dashboard_fixture_view(fixture, club)
        if played:
            statuses = fixture.get("availability_statuses")
            if not isinstance(statuses, dict):
                statuses = {}
                fixture["availability_statuses"] = statuses
            if statuses.get(member["name"]) != "Available":
                statuses[member["name"]] = "Available"
                changed = True
            fixtures.append({**fixture_view, "availability_read_only": True})
            continue
        if (
            (not active_year or fixture_season_year(fixture) == active_year)
            and str(fixture.get("status") or "").lower() != "completed"
            and not is_past
        ):
            fixtures.append({**fixture_view, "availability_read_only": False})
    if changed:
        save_store(store)
    fixtures.sort(key=lambda fixture: (str(fixture.get("date") or ""), str(fixture.get("opponent") or "")))
    return {
        "user": _auth_user_payload(user_row, current_club_id),
        "club": club,
        "clubs": _sorted_club_choices(store, club.get("id", "")),
        "member": member,
        "fixtures": fixtures,
        "selected_year": active_year,
        "season_outlook": _player_season_availability(int(user_row["id"]), club.get("id", "")),
    }


@app.post("/api/player/availability")
def save_player_availability(request: PlayerAvailabilitySelfRequest, x_auth_token: str | None = Header(default=None)) -> dict[str, Any]:
    user_row, current_club_id = _auth_user_from_token(x_auth_token)
    store = load_store()
    member = _member_for_user(store, user_row)
    if not member:
        raise HTTPException(status_code=400, detail="This signed-in account is not linked to a player profile.")
    try:
        match = get_match_or_404(store, request.fixture_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    _require_not_past(match, "availability")
    club = _selected_club(store, request.club_id or current_club_id)
    if str(match.get("club_id") or "").strip() and str(match.get("club_id") or "").strip() != str(club.get("id") or "").strip():
        raise HTTPException(status_code=403, detail="This match is not in your selected club.")
    _require_feature(user_row, current_club_id, "availability", club_id=str(club.get("id") or ""))
    match["availability_statuses"][member["name"]] = request.status
    if request.note.strip():
        match["availability_notes"][member["name"]] = request.note.strip()
    else:
        match["availability_notes"].pop(member["name"], None)
    save_store(store)
    _audit_event(
        "availability.update",
        "fixture",
        request.fixture_id,
        actor=user_row,
        club_id=str(club.get("id") or ""),
        club_name=str(club.get("name") or ""),
        details={
            "player_name": member.get("name") or "",
            "status": request.status,
            "note": request.note,
        },
        source="api",
    )
    return player_availability_data(x_auth_token)


@app.post("/api/player/season-availability")
def save_player_season_availability(
    request: PlayerSeasonAvailabilityRequest,
    x_auth_token: str | None = Header(default=None),
) -> dict[str, Any]:
    user_row, current_club_id = _auth_user_from_token(x_auth_token)
    store = load_store()
    club = _selected_club(store, request.club_id or current_club_id)
    _require_feature(user_row, current_club_id, "availability", club_id=str(club.get("id") or ""))
    with _auth_connection() as connection:
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
                int(user_row["id"]),
                club.get("id", ""),
                request.status.strip(),
                request.note.strip(),
                now_iso(),
            ),
        )
    _audit_event(
        "availability.season.update",
        "club",
        str(club.get("id") or ""),
        actor=user_row,
        club_id=str(club.get("id") or ""),
        club_name=str(club.get("name") or ""),
        details={
            "status": request.status,
            "note": request.note,
        },
        source="api",
    )
    return player_availability_data(x_auth_token)


@app.get("/api/player/profile-data")
def player_profile_data(x_auth_token: str | None = Header(default=None)) -> dict[str, Any]:
    user_row, current_club_id = _auth_user_from_token(x_auth_token)
    store = load_store()
    club = _selected_club(store, current_club_id)
    member = _member_for_user(store, user_row)
    member_aliases = {
        hint
        for hint in (
            str(member.get("name") or "").strip().lower() if member else "",
            str(member.get("full_name") or "").strip().lower() if member else "",
            str(user_row["display_name"] or "").strip().lower(),
            str(user_row["email"] or "").strip().lower(),
            str(user_row["mobile"] or "").strip().lower(),
            *(str(alias or "").strip().lower() for alias in (member or {}).get("aliases", [])),
        )
        if hint
    }

    def _matches_member(row: dict[str, Any]) -> bool:
        return (
            str(row.get("player_name") or "").strip().lower() in member_aliases
            or str(row.get("full_name") or "").strip().lower() in member_aliases
        )

    member_club_ids = {
        str(item.get("club_id") or "").strip().lower()
        for item in (member or {}).get("club_memberships", []) or []
        if str(item.get("club_id") or "").strip()
    }
    member_club_names = {
        str(item.get("club_name") or "").strip().lower()
        for item in (member or {}).get("club_memberships", []) or []
        if str(item.get("club_name") or "").strip()
    }

    overall_rows = list(store.get("member_summary_stats", []))
    year_rows_all = list(store.get("member_year_stats", []))
    club_rows_all = list(store.get("member_club_stats", []))

    def _archive_matches_member_clubs(archive: dict[str, Any]) -> bool:
        archive_ids = {
            str(value or "").strip().lower()
            for value in [archive.get("club_id"), *((archive.get("club_ids") or []) if isinstance(archive.get("club_ids"), list) else [])]
            if str(value or "").strip()
        }
        archive_names = {
            str(value or "").strip().lower()
            for value in [archive.get("club_name"), *((archive.get("club_names") or []) if isinstance(archive.get("club_names"), list) else [])]
            if str(value or "").strip()
        }
        return bool(archive_ids.intersection(member_club_ids) or archive_names.intersection(member_club_names))

    summary_stats = next((item for item in overall_rows if _matches_member(item)), {}) or {}
    year_stats = [row for row in year_rows_all if _matches_member(row)]
    year_stats.sort(key=lambda row: (str(row.get("season_year") or ""), str(row.get("player_name") or "")), reverse=True)
    club_stats = [row for row in club_rows_all if _matches_member(row)]
    club_stats.sort(key=lambda row: (str(row.get("club_name") or ""), str(row.get("player_name") or "")))

    recent_history_by_key: dict[str, dict[str, Any]] = {}
    seen_archive_keys: set[str] = set()
    for archive in sorted(canonical_archive_uploads(store.get("archive_uploads", []) or []), key=lambda item: str(item.get("archive_date") or item.get("date") or ""), reverse=True):
        archive_key = "|".join(
            str(value or "").strip().lower()
            for value in (
                archive.get("family_key"),
                archive.get("id"),
                archive.get("archive_id"),
                archive.get("file_hash"),
                archive.get("archive_date") or archive.get("date"),
                archive.get("club_id"),
                archive.get("club_name"),
            )
            if str(value or "").strip()
        )
        if archive_key and archive_key in seen_archive_keys:
            continue
        if archive_key:
            seen_archive_keys.add(archive_key)
        archive_status = str(archive.get("status") or "").strip().lower()
        if archive_status.startswith("pending"):
            continue
        archive_rows_by_key: dict[str, dict[str, Any]] = {}
        def _add_archive_row(performance: dict[str, Any], fallback_note: str = "") -> None:
            player_key = str(performance.get("player_name") or "").strip().lower()
            if player_key not in member_aliases:
                return
            row = {
                "source": "archive",
                "date": str(archive.get("archive_date") or archive.get("date") or ""),
                "season_year": str(archive.get("archive_year") or archive.get("season_year") or ""),
                "club_name": str(archive.get("club_name") or club.get("name") or ""),
                "opponent": str(
                    archive.get("match", {}).get("teams", {}).get("team_2")
                    or archive.get("opponent")
                    or "TBD"
                ),
                "status": str(archive.get("status") or ""),
                "result": str(archive.get("validation", {}).get("expected_result") or archive.get("result") or ""),
                "runs": int(performance.get("runs") or 0),
                "balls": int(performance.get("balls") or 0),
                "wickets": int(performance.get("wickets") or 0),
                "catches": int(performance.get("catches") or 0),
                "player_name": str(performance.get("player_name") or "").strip().lower(),
                "notes": str(performance.get("notes") or fallback_note or ""),
            }
            row_key = "|".join(
                [
                    row["date"],
                    row["club_name"],
                    row["opponent"],
                    row["player_name"],
                    str(row["runs"]),
                    str(row["balls"]),
                    str(row["wickets"]),
                    str(row["catches"]),
                ]
            )
            if row_key not in archive_rows_by_key:
                archive_rows_by_key[row_key] = row
        performances = [
            performance
            for performance in archive.get("suggested_performances", []) or []
            if str(performance.get("player_name") or "").strip().lower() in member_aliases
        ]
        if performances:
            source_rows = performances
        else:
            try:
                review_template = json.loads(str(archive.get("review_template_json") or "{}"))
            except Exception:
                review_template = {}
            batting_rows: list[dict[str, Any]] = []
            for inning in review_template.get("innings", []) or []:
                for batting in inning.get("batting", []) or []:
                    candidate_name = str((batting.get("player") or {}).get("name") or batting.get("player_name") or "").strip().lower()
                    if candidate_name and candidate_name in member_aliases:
                        batting_rows.append(
                            {
                                "player_name": candidate_name,
                                "runs": int(batting.get("runs") or 0),
                                "balls": int(batting.get("balls") or 0),
                                "wickets": int(batting.get("wickets") or 0),
                                "catches": int(batting.get("catches") or 0),
                                "notes": "Verified archive scorecard",
                            }
                    )
            source_rows = batting_rows
        if not source_rows:
            continue
        for performance in source_rows:
            _add_archive_row(performance, archive.get("status") or "Reviewed archive scorecard")
        for row in archive_rows_by_key.values():
            key = "|".join(
                str(value or "").strip().lower()
                for value in (
                    row.get("date"),
                    row.get("club_name"),
                    row.get("opponent"),
                    row.get("player_name"),
                )
                if str(value or "").strip()
            )
            if key and key not in recent_history_by_key:
                recent_history_by_key[key] = row

    recent_history = sorted(
        recent_history_by_key.values(),
        key=lambda item: str(item.get("date") or ""),
        reverse=True,
    )
    return {
        "user": _auth_user_payload(user_row, current_club_id),
        "club": club,
        "member": member,
        "clubs": _sorted_club_choices(store, club.get("id", "")),
        "summary_stats": summary_stats,
        "year_stats": year_stats,
        "club_stats": club_stats,
        "recent_history": recent_history[:20],
    }


@app.get("/api/player/summary")
def player_summary_data(x_auth_token: str | None = Header(default=None)) -> dict[str, Any]:
    return player_profile_data(x_auth_token)


def _add_member_clubs_by_name(store: dict[str, Any], member: dict[str, Any], names: list[Any]) -> list[str]:
    """Link a player to the registered clubs named in `names` (exact or close spelling); keeps every existing link."""
    added: list[str] = []
    memberships = [item for item in member.get("team_memberships") or [] if isinstance(item, dict)]
    club_links = [item for item in member.get("club_memberships") or [] if isinstance(item, dict)]
    have = {str(item.get("club_id") or "") for item in memberships + club_links if item.get("club_id")}
    clubs = [club for club in store.get("clubs", []) or [] if isinstance(club, dict) and club.get("id")]
    for raw in names:
        name = str(raw.get("club_name") or raw.get("team_name") or "") if isinstance(raw, dict) else str(raw or "")
        name = name.strip()
        if not name:
            continue
        club = _find_club_by_name(store, name) or next(
            (item for item in clubs if _same_team_name(name, item.get("name")) or _same_team_name(name, item.get("short_name"))),
            None,
        )
        if not club or str(club["id"]) in have:
            continue
        club_id, club_name = str(club["id"]), str(club.get("name") or name)
        team_name = str(club.get("short_name") or club_name)
        memberships.append({"team_name": team_name, "display_name": club_name, "club_id": club_id, "club_name": club_name, "team_type": "club", "is_primary": False})
        club_links.append({"club_id": club_id, "club_name": club_name, "is_primary": False})
        have.add(club_id)
        added.append(club_name)
    member["team_memberships"] = memberships
    member["club_memberships"] = club_links
    if not str(member.get("primary_club_id") or "").strip() and memberships:
        member["primary_club_id"] = str(memberships[0].get("club_id") or "")
        member["primary_club_name"] = str(memberships[0].get("club_name") or "")
    return added


# ---------------------------------------------------------------------------
# Nov 7 2026 (Amit: "the player who registers as CHECKLEY should see all his scorecards with his match names like
# chuck, checkly, chukli, CJ ... AI should suggest the matches and ask the player to identify and merge"):
# names written on scorecards that look like the signed-in player are suggested on his profile; "This is me"
# adds the name to his aliases (and merges an unclaimed duplicate player record of that name into his), so those
# scorecards count in his stats.
# ---------------------------------------------------------------------------
class NameClaimRequest(BaseModel):
    name: str


class NameClaimDecisionRequest(BaseModel):
    decision: str
    note: str = ""


def _claimed_member_ids() -> set[str]:
    try:
        with _auth_connection() as connection:
            return {str(row[0]) for row in connection.execute("SELECT member_id FROM app_users WHERE member_id IS NOT NULL AND member_id != ''")}
    except Exception:
        return set()


def _consonant_skeleton(text: str) -> str:
    """'checkley' -> 'chkl', 'chukli' -> 'chkl': consonants in order, doubles and a trailing y dropped."""
    letters = re.sub(r"[^a-z]", "", text.lower()).replace("ck", "k").replace("ph", "f")
    out = ""
    for ch in letters[:1] + re.sub(r"[aeiouy]", "", letters[1:]):
        if not out or out[-1] != ch:
            out += ch
    return out


def _looks_like_member(name: str, member: dict[str, Any]) -> float:
    """0..1: how much a written name looks like this player. Nov 9 2026: tightened after testing on live data
    ("Harry" for Barry, "Amit G" for Amir were suggested): the first letter must match, and a near spelling
    ("Checkly"), the same sounds ("Chukli" for Checkley) or the player's initials ("CJ") are needed."""
    import difflib

    low = normalize_name(name)
    if not low:
        return 0.0
    keys = [key for key in _member_identity_keys(member) if key and not key.isdigit()]
    compact = low.replace(" ", "")
    best = 0.0
    for key in keys:
        words = key.split()
        if len(compact) in (2, 3) and " " not in low and compact == "".join(word[0] for word in words if word) and len(words) > 1:
            best = max(best, 0.86)  # "CJ" for "Chris James"
        if key[:1] != low[:1]:
            continue
        low_words = low.split()
        if len(low_words) > 1 and len(words) > 1 and low_words[0] == words[0] and low_words[1][:1] != words[1][:1]:
            return 0.0  # same first name, different surname initial ("Amit G" is not "Amit S")
        best = max(best, difflib.SequenceMatcher(None, low, key).ratio())
        if len(low_words[0]) >= 4 and _consonant_skeleton(low_words[0]) == _consonant_skeleton(words[0]) and len(_consonant_skeleton(words[0])) >= 3:
            best = max(best, 0.86)  # "Chukli" / "Checkly" for "Checkley"
        if len(words) > 1 and low == words[0]:
            best = max(best, 0.86)  # "Amit" for "Amit S" (skipped later when another player is also "Amit")
    return best


def _name_fits_other_players(store: dict[str, Any], member: dict[str, Any], name: str) -> bool:
    """True when the name is (or could be) somebody else: another player's name or alias, or a bare first name
    ("Amit") that another player also has."""
    low = normalize_name(name)
    for other in store.get("members", []) or []:
        if other is member or str(other.get("id") or "") == str(member.get("id") or ""):
            continue
        if _member_matches_name(other, name):
            return True
        if " " not in low and normalize_name(str(other.get("name") or "")).split(" ")[0] == low:
            return True
    return False


def _name_suggestions_for(store: dict[str, Any], member: dict[str, Any]) -> list[dict[str, Any]]:
    claimed = _claimed_member_ids() - {str(member.get("id") or "")}
    own_clubs = {str(link.get("club_name") or "") for link in member.get("club_memberships", []) or [] if isinstance(link, dict)}
    found: dict[str, dict[str, Any]] = {}
    for card in _public_scorecards(store):
        for innings in card.get("innings") or []:
            for key, team in (("batting", innings.get("team")), ("bowling", innings.get("bowling_team"))):
                if own_clubs and team and not any(_same_team_name(team, club) for club in own_clubs):
                    continue  # he didn't play for that side
                for row in innings.get(key) or []:
                    name = " ".join(str(row.get("name") or "").split())
                    if not name or _member_matches_name(member, name):
                        continue
                    other = _member_for_card_name(store, name, team)
                    if other and str(other.get("id") or "") in claimed:
                        continue  # that name is another registered player
                    if _name_fits_other_players(store, member, name) and not (other and str(other.get("id") or "") not in claimed and normalize_name(str(other.get("name") or "")) == normalize_name(name)):
                        continue  # "Amit" could be Amit G as well - not suggested
                    score = _looks_like_member(name, member)
                    if score < 0.85:
                        continue
                    item = found.setdefault(normalize_name(name), {"name": name, "score": round(score, 2), "cards": []})
                    if not any(entry["id"] == card.get("id") for entry in item["cards"]):
                        detail = f"{row.get('runs')} runs" if key == "batting" and row.get("runs") is not None else (f"{row.get('wickets')} wkts" if row.get("wickets") is not None else "")
                        item["cards"].append({"id": card.get("id"), "date": card.get("date"), "title": card.get("title"), "detail": detail})
    return sorted(found.values(), key=lambda item: (-item["score"], -len(item["cards"])))[:12]


@app.get("/api/player/name-suggestions")
def player_name_suggestions(x_auth_token: str | None = Header(default=None)) -> dict[str, Any]:
    user_row, _ = _auth_user_from_token(x_auth_token)
    store = load_store()
    member = _member_for_user(store, user_row)
    if not member:
        return {"suggestions": []}
    return {"player": member.get("name") or "", "suggestions": _name_suggestions_for(store, member)}


@app.post("/api/player/name-suggestions/claim")
def player_claim_name(request: NameClaimRequest, x_auth_token: str | None = Header(default=None)) -> dict[str, Any]:
    user_row, _ = _auth_user_from_token(x_auth_token)
    store = load_store()
    member = _member_for_user(store, user_row)
    name = " ".join(str(request.name or "").split())
    if not member or not name:
        raise HTTPException(status_code=400, detail="Choose a name first.")
    claimed = _claimed_member_ids() - {str(member.get("id") or "")}
    duplicates = [
        item for item in store.get("members", []) or []
        if item is not member and normalize_name(str(item.get("name") or "")) == normalize_name(name)
    ]
    if any(str(item.get("id") or "") in claimed for item in duplicates):
        raise HTTPException(status_code=409, detail=f"'{name}' is another registered player. Ask a club admin if it is really you.")
    others = [item for item in store.get("members", []) or [] if item is not member and not any(item is dup for dup in duplicates)]
    if _name_fits_other_players({"members": others}, member, name):
        raise HTTPException(status_code=409, detail=f"'{name}' could also be another player. Ask a club admin to link it to the right player.")
    # Phase 0: no member merge or alias write here. A club admin decides via /api/admin/name-claims.
    existing = _pending_name_claim(int(user_row["id"]), str(member.get("id") or ""), name)
    if existing:
        return {"message": f"Request for '{name}' is already waiting for a club admin to confirm.", "claim_id": existing, "status": "pending"}
    with _auth_connection() as connection:
        cursor = connection.execute(
            """
            INSERT INTO app_name_claims (user_id, member_id, claimed_name, claimed_name_norm, status, created_at)
            VALUES (?, ?, ?, ?, 'pending', ?)
            """,
            (int(user_row["id"]), str(member.get("id") or ""), name, normalize_name(name), now_iso()),
        )
        claim_id = int(cursor.lastrowid)
    _audit_event("player.claim_requested", "member", str(member.get("id") or ""), actor=user_row, club_id="", club_name="", details={"name": name, "claim_id": claim_id}, source="api")
    return {"message": f"Request sent. A club admin will confirm that '{name}' is you.", "claim_id": claim_id, "status": "pending"}



def _pending_name_claim(user_id: int, member_id: str, name: str) -> int | None:
    with _auth_connection() as connection:
        row = connection.execute(
            "SELECT id FROM app_name_claims WHERE user_id = ? AND member_id = ? AND claimed_name_norm = ? AND status = 'pending'",
            (user_id, member_id, normalize_name(name)),
        ).fetchone()
    return int(row["id"]) if row else None


def _reviewer_can_decide(store: dict[str, Any], user_row: sqlite3.Row, current_club_id: str, member: dict[str, Any]) -> bool:
    """Superadmin decides any claim; other reviewers only for players who belong to one of their clubs."""
    if "superadmin" in _user_role_names(user_row, current_club_id):
        return True
    reviewer_ids = set(_user_club_ids(store, user_row, current_club_id))
    reviewer_names = [str(club.get("name") or "") for club in store.get("clubs", []) or [] if str(club.get("id") or "") in reviewer_ids]
    return any(
        _same_team_name(str(link.get("club_name") or ""), club_name)
        for link in member.get("club_memberships", []) or [] if isinstance(link, dict)
        for club_name in reviewer_names
    )


def _member_by_id(store: dict[str, Any], member_id: str) -> dict[str, Any] | None:
    return next((item for item in store.get("members", []) or [] if str(item.get("id") or "") == member_id), None)


@app.get("/api/admin/name-claims")
def admin_name_claims(x_auth_token: str | None = Header(default=None)) -> dict[str, Any]:
    user_row, current_club_id = _require_permission(x_auth_token, "manage_players")
    store = load_store()
    with _auth_connection() as connection:
        rows = connection.execute(
            """
            SELECT c.id, c.member_id, c.claimed_name, c.created_at, u.display_name AS requester
            FROM app_name_claims c LEFT JOIN app_users u ON u.id = c.user_id
            WHERE c.status = 'pending' ORDER BY c.created_at
            """
        ).fetchall()
    claims: list[dict[str, Any]] = []
    for row in rows:
        member = _member_by_id(store, str(row["member_id"]))
        if not member or not _reviewer_can_decide(store, user_row, current_club_id, member):
            continue
        claims.append({
            "id": int(row["id"]),
            "member_id": str(row["member_id"]),
            "member_name": str(member.get("name") or ""),
            "claimed_name": str(row["claimed_name"] or ""),
            "requested_by": str(row["requester"] or ""),
            "created_at": str(row["created_at"] or ""),
        })
    return {"claims": claims}


class MemberMergeRequest(BaseModel):
    first_member_id: str
    second_member_id: str
    keep_member_id: str = ""


def _store_version_now() -> int:
    with _auth_connection() as connection:
        try:
            row = connection.execute("SELECT version FROM app_store_version WHERE id = 1").fetchone()
        except sqlite3.OperationalError:
            return 0
    return int(row["version"]) if row else 0


def _relink_member_auth(kept_id: str, removed_id: str) -> str:
    """Move login and follow links from the removed member to the kept one. Returns what undo needs to reverse it."""
    with _auth_connection() as connection:
        user_ids = [int(row["id"]) for row in connection.execute("SELECT id FROM app_users WHERE member_id = ?", (removed_id,)).fetchall()]
        removed_followers = [int(row["user_id"]) for row in connection.execute("SELECT user_id FROM app_followed_players WHERE member_id = ?", (removed_id,)).fetchall()]
        kept_followers = [int(row["user_id"]) for row in connection.execute("SELECT user_id FROM app_followed_players WHERE member_id = ?", (kept_id,)).fetchall()]
        connection.execute("UPDATE app_users SET member_id = ? WHERE member_id = ?", (kept_id, removed_id))
        connection.execute("UPDATE OR IGNORE app_followed_players SET member_id = ? WHERE member_id = ?", (kept_id, removed_id))
        connection.execute("DELETE FROM app_followed_players WHERE member_id = ?", (removed_id,))
    return json.dumps({"user_ids": user_ids, "removed_followers": removed_followers, "kept_followers": kept_followers})


def _restore_member_auth(kept_id: str, removed_id: str, snapshot: dict[str, Any]) -> None:
    with _auth_connection() as connection:
        for user_id in snapshot.get("user_ids", []):
            connection.execute("UPDATE app_users SET member_id = ? WHERE id = ? AND member_id = ?", (removed_id, user_id, kept_id))
        for user_id in snapshot.get("removed_followers", []):
            connection.execute("INSERT OR IGNORE INTO app_followed_players (user_id, member_id) VALUES (?, ?)", (user_id, removed_id))
        added_to_kept = set(snapshot.get("removed_followers", [])) - set(snapshot.get("kept_followers", []))
        for user_id in added_to_kept:
            connection.execute("DELETE FROM app_followed_players WHERE user_id = ? AND member_id = ?", (user_id, kept_id))


@app.post("/api/admin/name-matches/merge")
def admin_merge_members(request: MemberMergeRequest, x_auth_token: str | None = Header(default=None)) -> dict[str, Any]:
    # Superadmin merges any two players; a club admin only players from their own clubs. The older record survives unless keep_member_id names the newer one.
    user_row, current_club_id = _require_permission(x_auth_token, "manage_players")
    store = load_store()
    first_id, second_id = str(request.first_member_id or "").strip(), str(request.second_member_id or "").strip()
    keep_id = str(request.keep_member_id or "").strip() or None
    if keep_id and keep_id not in (first_id, second_id):
        raise HTTPException(status_code=400, detail="Choose one of the two players to keep.")
    for member_id in (first_id, second_id):
        member = _member_by_id(store, member_id)
        if not member:
            raise HTTPException(status_code=404, detail="Player not found.")
        if not _reviewer_can_decide(store, user_row, current_club_id, member):
            raise HTTPException(status_code=403, detail="You can only merge players from your own clubs.")
    result = _perform_member_merge(store, first_id, second_id, user_row, keep_id)
    return {"message": f"'{result['removed_name']}' is merged into '{result['kept_name']}'. A superadmin can undo this.", **result}


@app.post("/api/admin/name-matches/reject")
def admin_reject_name_match(request: MemberMergeRequest, x_auth_token: str | None = Header(default=None)) -> dict[str, Any]:
    # Saves "not the same player" for this pair so it stops showing in Name matches.
    user_row, current_club_id = _require_permission(x_auth_token, "manage_players")
    store = load_store()
    first_id, second_id = str(request.first_member_id or "").strip(), str(request.second_member_id or "").strip()
    if not first_id or not second_id or first_id == second_id:
        raise HTTPException(status_code=400, detail="Choose two different players.")
    for member_id in (first_id, second_id):
        member = _member_by_id(store, member_id)
        if not member:
            raise HTTPException(status_code=404, detail="Player not found.")
        if not _reviewer_can_decide(store, user_row, current_club_id, member):
            raise HTTPException(status_code=403, detail="You can only review players from your own clubs.")
    low, high = sorted((first_id, second_id))
    with _auth_connection() as connection:
        connection.execute(
            "INSERT OR IGNORE INTO app_name_match_rejections (member_low_id, member_high_id, rejected_by_user_id, created_at) VALUES (?, ?, ?, ?)",
            (low, high, int(user_row["id"]), now_iso()),
        )
    _audit_event("member.name_match_rejected", "member", first_id, actor=user_row, club_id="", club_name="", details={"first_member_id": first_id, "second_member_id": second_id}, source="api")
    return {"message": "Marked as not the same player. It will not show again.", "first_member_id": first_id, "second_member_id": second_id}


def _perform_member_merge(store: dict[str, Any], first_id: str, second_id: str, user_row: sqlite3.Row, keep_id: str | None = None) -> dict[str, Any]:
    """Merge two members, relink their logins, save the store and record the merge so a superadmin can undo it."""
    store_before = json.dumps(store, default=str)
    try:
        summary = merge_members_in_store(store, first_id, second_id, keep_id)
    except MergeError as error:
        raise HTTPException(status_code=400, detail=str(error))
    auth_snapshot = _relink_member_auth(summary["kept_member_id"], summary["removed_member_id"])
    save_store(store)
    version_after = _store_version_now()
    with _auth_connection() as connection:
        cursor = connection.execute(
            """
            INSERT INTO app_member_merges (kept_member_id, removed_member_id, removed_name, merged_by_user_id, created_at,
                                           store_version_after, store_snapshot, auth_snapshot)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (summary["kept_member_id"], summary["removed_member_id"], summary["removed_name"], int(user_row["id"]), now_iso(), version_after, store_before, auth_snapshot),
        )
        merge_id = int(cursor.lastrowid)
    _audit_event("member.merge", "member", summary["kept_member_id"], actor=user_row, club_id="", club_name="", details={**summary, "merge_id": merge_id}, source="api")
    return {"merge_id": merge_id, **summary}


@app.post("/api/admin/member-merges/{merge_id}/undo")
def admin_undo_member_merge(merge_id: int, x_auth_token: str | None = Header(default=None)) -> dict[str, Any]:
    user_row, _ = _require_superadmin(x_auth_token)
    with _auth_connection() as connection:
        row = connection.execute("SELECT * FROM app_member_merges WHERE id = ?", (merge_id,)).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Merge not found.")
    if row["undone_at"]:
        raise HTTPException(status_code=409, detail="This merge was already undone.")
    if _store_version_now() != int(row["store_version_after"]):
        raise HTTPException(status_code=409, detail="Player data changed after this merge, so it cannot be undone automatically.")
    save_store(json.loads(row["store_snapshot"]))
    _restore_member_auth(str(row["kept_member_id"]), str(row["removed_member_id"]), json.loads(row["auth_snapshot"]))
    with _auth_connection() as connection:
        connection.execute(
            "UPDATE app_member_merges SET undone_at = ?, undone_by_user_id = ? WHERE id = ?",
            (now_iso(), int(user_row["id"]), merge_id),
        )
    _audit_event("member.merge_undo", "member", str(row["removed_member_id"]), actor=user_row, club_id="", club_name="", details={"merge_id": merge_id, "kept_member_id": str(row["kept_member_id"])}, source="api")
    return {"message": f"Merge undone. '{row['removed_name']}' is restored as a separate player.", "merge_id": merge_id}


NAME_MATCH_SIMILARITY = 0.85
NAME_MATCH_MAX_GROUPS = 200


@app.get("/api/admin/name-matches")
def admin_name_matches(x_auth_token: str | None = Header(default=None)) -> dict[str, Any]:
    # Read-only: lists member records with the same or similar names. Nothing is merged or written.
    user_row, current_club_id = _require_permission(x_auth_token, "manage_players")
    store = load_store()
    club_names = {str(club.get("id") or ""): str(club.get("name") or "") for club in store.get("clubs", []) or [] if isinstance(club, dict)}
    by_name: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for member in store.get("members", []) or []:
        if not isinstance(member, dict) or not str(member.get("name") or "").strip():
            continue
        by_name[normalize_name(member.get("name"))].append(member)

    candidates: list[tuple[str, float, list[dict[str, Any]]]] = []
    for norm, items in by_name.items():
        if len(items) > 1:
            candidates.append(("exact", 1.0, items))
    # Compare every name a player is known by (name, full name, aliases), so "Bim B" finds "Bim" once it is an alias.
    members_with_names = [item for item in store.get("members", []) or [] if isinstance(item, dict) and str(item.get("name") or "").strip()]
    prefixes: dict[str, list[tuple[str, int]]] = defaultdict(list)
    for index, item in enumerate(members_with_names):
        for norm in _identity_names(item):
            prefixes[norm[:2]].append((norm, index))
    paired: set[tuple[int, int]] = set()
    for entries in prefixes.values():
        for position, (first, i) in enumerate(entries):
            for second, j in entries[position + 1:]:
                pair = (min(i, j), max(i, j))
                if i == j or pair in paired:
                    continue
                if normalize_name(members_with_names[i].get("name")) == normalize_name(members_with_names[j].get("name")):
                    continue  # already listed as an exact match
                if _names_look_same(first, second):
                    paired.add(pair)
                    score = SequenceMatcher(None, first, second).ratio()
                    candidates.append(("similar", round(score, 2), [members_with_names[i], members_with_names[j]]))

    groups: list[dict[str, Any]] = []
    with _auth_connection() as connection:
        rejected_pairs = {(str(row["member_low_id"]), str(row["member_high_id"])) for row in connection.execute("SELECT member_low_id, member_high_id FROM app_name_match_rejections").fetchall()}
    engine = _match_engine(store)
    for match_type, score, items in sorted(candidates, key=lambda entry: (-entry[1], entry[0])):
        # Drop pairs a reviewer already rejected as "not the same player".
        first_member = items[0]
        items = [first_member] + [member for member in items[1:] if tuple(sorted((str(first_member.get("id")), str(member.get("id"))))) not in rejected_pairs]
        if len(items) < 2:
            continue
        # Show a group only when the reviewer may see every record in it, so no hidden player name leaks.
        if not all(_reviewer_can_decide(store, user_row, current_club_id, member) for member in items):
            continue
        pair = engine.score(items[0], items[1])
        groups.append({
            "match_type": match_type,
            "score": score,
            "ai_match_percent": round(pair.score * 100),
            "ai_reasons": pair.reasons,
            "members": [
                {
                    "id": str(member.get("id") or ""),
                    "player_id": str(member.get("player_id") or ""),
                    "name": str(member.get("name") or ""),
                    "clubs": [
                        club_names.get(str(link.get("club_id") or ""), str(link.get("club_id") or ""))
                        for link in member.get("club_memberships") or []
                        if isinstance(link, dict)
                    ],
                }
                for member in items
            ],
        })
        if len(groups) >= NAME_MATCH_MAX_GROUPS:
            break
    return {"groups": groups, "similarity_threshold": NAME_MATCH_SIMILARITY}


@app.post("/api/admin/name-claims/{claim_id}/decision")
def admin_decide_name_claim(claim_id: int, request: NameClaimDecisionRequest, x_auth_token: str | None = Header(default=None)) -> dict[str, Any]:
    user_row, current_club_id = _require_permission(x_auth_token, "manage_players")
    decision = str(request.decision or "").strip().lower()
    if decision not in {"approve", "reject"}:
        raise HTTPException(status_code=400, detail="Decision must be approve or reject.")
    with _auth_connection() as connection:
        row = connection.execute("SELECT * FROM app_name_claims WHERE id = ?", (claim_id,)).fetchone()
    if not row or row["status"] != "pending":
        raise HTTPException(status_code=404, detail="This request was not found or was already decided.")
    store = load_store()
    member_id = str(row["member_id"])
    member = _member_by_id(store, member_id)
    if not member or not _reviewer_can_decide(store, user_row, current_club_id, member):
        raise HTTPException(status_code=403, detail="You can only decide requests for players in your clubs.")
    claimed_name = str(row["claimed_name"])
    status = "rejected"
    if decision == "approve":
        claimed_norm = normalize_name(claimed_name)
        claimed_elsewhere = _claimed_member_ids() - {member_id}
        if any(
            str(item.get("id") or "") in claimed_elsewhere and normalize_name(str(item.get("name") or "")) == claimed_norm
            for item in store.get("members", []) or []
        ):
            raise HTTPException(status_code=409, detail=f"'{claimed_name}' now belongs to another registered player. Reject this request.")
        aliases = [alias for alias in member.get("aliases") or [] if alias]
        if claimed_norm not in {normalize_name(alias) for alias in aliases}:
            aliases.append(claimed_name)
            member["aliases"] = aliases
            save_store(store)
        status = "approved"
    with _auth_connection() as connection:
        connection.execute(
            "UPDATE app_name_claims SET status = ?, decided_at = ?, decided_by_user_id = ?, decision_note = ? WHERE id = ?",
            (status, now_iso(), int(user_row["id"]), str(request.note or "").strip()[:500], claim_id),
        )
    _audit_event("player.claim_" + status, "member", member_id, actor=user_row, club_id="", club_name="", details={"name": claimed_name, "claim_id": claim_id}, source="api")
    return {"status": status, "claim_id": claim_id}


class MergeRequestCreate(BaseModel):
    target_member_id: str
    keep: str = "older"


class MergeRequestDecision(BaseModel):
    decision: str
    note: str = ""


def _names_look_same(first: str, second: str) -> bool:
    first_norm, second_norm = normalize_name(first), normalize_name(second)
    if not first_norm or not second_norm:
        return False
    if first_norm == second_norm or SequenceMatcher(None, first_norm, second_norm).ratio() >= NAME_MATCH_SIMILARITY:
        return True
    # "Bim" vs "Bim B" and "Amit" vs "Amit S": a name plus a one- or two-letter initial. Short names score too low for the ratio.
    short, long_ = sorted((first_norm, second_norm), key=len)
    extra = long_[len(short):]
    return long_.startswith(short) and extra.startswith(" ") and len(extra.strip()) <= 2


def _identity_names(member: dict[str, Any]) -> list[str]:
    """Every name a player is known by: main name, full name and aliases, normalized and without duplicates."""
    return identity_names(member)


def _members_look_same(first: dict[str, Any], second: dict[str, Any]) -> bool:
    return any(_names_look_same(a, b) for a in _identity_names(first) for b in _identity_names(second))


PLAYER_MERGE_SUGGEST_MIN_SCORE = 0.75  # overall match confidence (names, clubs, match history) that a record is suggested


def _archive_performance_rows(archive: dict[str, Any]) -> list[dict[str, Any]]:
    """Batting rows of one archived match: the saved performances, or the review template when none are saved."""
    performances = [item for item in archive.get("suggested_performances", []) or [] if isinstance(item, dict)]
    if performances:
        return performances
    try:
        template = json.loads(str(archive.get("review_template_json") or "{}"))
    except Exception:
        template = {}
    for inning in template.get("innings", []) or []:
        for batting in inning.get("batting", []) or []:
            performances.append({
                "player_name": (batting.get("player") or {}).get("name") or batting.get("player_name") or "",
                "runs": batting.get("runs") or 0,
                "balls": batting.get("balls") or 0,
            })
    return performances


def _match_engine(store: dict[str, Any]) -> AIDuplicateEngine:
    """AIDuplicateEngine that knows which names batted together in each past match (used to veto two-person pairs)."""
    played: list[set[str]] = []
    for archive in canonical_archive_uploads(store.get("archive_uploads", [])):
        if str(archive.get("status") or "").lower().startswith("pending"):
            continue
        names = {normalize_name(str(row.get("player_name") or "")) for row in _archive_performance_rows(archive)} - {""}
        if names:
            played.append(names)
    return AIDuplicateEngine(played)
def _pending_merge_request(member_a: str, member_b: str) -> int | None:
    with _auth_connection() as connection:
        row = connection.execute(
            """
            SELECT id FROM app_merge_requests WHERE status = 'pending' AND (
              (requester_member_id = ? AND target_member_id = ?) OR (requester_member_id = ? AND target_member_id = ?))
            """,
            (member_a, member_b, member_b, member_a),
        ).fetchone()
    return int(row["id"]) if row else None


def _dismissed_suggestion_ids(user_id: int) -> set[str]:
    with _auth_connection() as connection:
        rows = connection.execute(
            "SELECT target_member_id FROM app_merge_suggestion_dismissals WHERE user_id = ?",
            (user_id,),
        ).fetchall()
    return {str(row["target_member_id"]) for row in rows}


def _member_club_names(store: dict[str, Any], member: dict[str, Any]) -> list[str]:
    club_names = {str(club.get("id") or ""): str(club.get("name") or "") for club in store.get("clubs", []) or [] if isinstance(club, dict)}
    names: list[str] = []
    for link in member.get("club_memberships") or []:
        if not isinstance(link, dict):
            continue
        name = str(link.get("club_name") or club_names.get(str(link.get("club_id") or ""), "")).strip()
        if name and name not in names:
            names.append(name)
    return names


def _member_career_summary(store: dict[str, Any], member_id: str) -> dict[str, Any]:
    row = next((item for item in store.get("member_summary_stats", []) or [] if str(item.get("member_id") or "") == member_id), {})
    return {
        "matches": int(row.get("matches") or 0),
        "runs": int(row.get("runs") or 0),
        "wickets": int(row.get("wickets") or 0),
        "highest_score": row.get("highest_score") or 0,
        "batting_average": row.get("batting_average") or 0,
    }


def _member_recent_matches(store: dict[str, Any], member: dict[str, Any], limit: int = 10) -> list[dict[str, Any]]:
    """Recent batting rows for a player across club archives, matched by any of their known names."""
    names = set(_identity_names(member))
    club_names = {str(club.get("id") or ""): str(club.get("name") or "") for club in store.get("clubs", []) or [] if isinstance(club, dict)}
    rows: list[dict[str, Any]] = []
    for archive in canonical_archive_uploads(store.get("archive_uploads", [])):
        if str(archive.get("status") or "").lower().startswith("pending"):
            continue
        performances = _archive_performance_rows(archive)
        match = archive.get("match") if isinstance(archive.get("match"), dict) else {}
        teams = match.get("teams") if isinstance(match.get("teams"), dict) else {}
        for performance in performances:
            if normalize_name(str(performance.get("player_name") or "")) not in names:
                continue
            rows.append({
                "date": str(match.get("date") or archive.get("archive_year") or ""),
                "club": club_names.get(str(archive.get("club_id") or ""), ""),
                "opponent": str(teams.get("team_2") or ""),
                "runs": int(performance.get("runs") or 0),
                "balls": int(performance.get("balls") or 0),
                "wickets": int(performance.get("wickets") or 0),
                "catches": int(performance.get("catches") or 0),
            })
    rows.sort(key=lambda row: row["date"], reverse=True)
    return rows[:limit]


@app.get("/api/player/merge-candidates/{target_member_id}/details")
def player_merge_candidate_details(target_member_id: str, x_auth_token: str | None = Header(default=None)) -> dict[str, Any]:
    """Full profile of one suggested player, limited to records that are valid suggestions for the caller."""
    user_row, _ = _auth_user_from_token(x_auth_token)
    store = load_store()
    member = _member_for_user(store, user_row)
    if not member:
        raise HTTPException(status_code=400, detail="Your login is not linked to a player record yet.")
    target = _member_by_id(store, target_member_id)
    engine = _match_engine(store)
    pair = engine.score(member, target) if target else None
    if not target or str(target.get("id")) == str(member.get("id")) or pair.score < PLAYER_MERGE_SUGGEST_MIN_SCORE:
        raise HTTPException(status_code=404, detail="Player not found.")
    return {
        "id": str(target.get("id") or ""),
        "player_id": str(target.get("player_id") or ""),
        "name": str(target.get("name") or ""),
        "full_name": str(target.get("full_name") or target.get("name") or ""),
        "aliases": [str(alias) for alias in target.get("aliases") or [] if str(alias or "").strip()],
        "clubs": _member_club_names(store, target),
        "career": _member_career_summary(store, str(target.get("id") or "")),
        "matches": _member_recent_matches(store, target),
        "match_percent": round(pair.score * 100),
        "reasons": pair.reasons,
    }


@app.post("/api/player/merge-suggestions/{target_member_id}/dismiss")
def dismiss_player_merge_suggestion(target_member_id: str, x_auth_token: str | None = Header(default=None)) -> dict[str, Any]:
    """Remember that this player rejected a similar-name suggestion so it stops showing."""
    user_row, _ = _auth_user_from_token(x_auth_token)
    store = load_store()
    member = _member_for_user(store, user_row)
    if not member:
        raise HTTPException(status_code=400, detail="Your login is not linked to a player record yet.")
    target = _member_by_id(store, target_member_id)
    if not target or str(target.get("id")) == str(member.get("id")):
        raise HTTPException(status_code=404, detail="Player not found.")
    with _auth_connection() as connection:
        connection.execute(
            "INSERT OR IGNORE INTO app_merge_suggestion_dismissals (user_id, target_member_id, created_at) VALUES (?, ?, ?)",
            (int(user_row["id"]), target_member_id, now_iso()),
        )
    return {"message": "Suggestion dismissed. It will not show again.", "target_member_id": target_member_id}


@app.get("/api/player/merge-candidates")
def player_merge_candidates(x_auth_token: str | None = Header(default=None)) -> dict[str, Any]:
    """Other player records whose name is 75% or more similar, plus this player's own merge requests."""
    user_row, _ = _auth_user_from_token(x_auth_token)
    store = load_store()
    member = _member_for_user(store, user_row)
    if not member:
        return {"candidates": [], "requests": []}
    own_id = str(member.get("id") or "")
    dismissed = _dismissed_suggestion_ids(int(user_row["id"]))
    engine = _match_engine(store)
    scored: list[tuple[float, dict[str, Any], list[str]]] = []
    for item in store.get("members", []) or []:
        item_id = str(item.get("id") or "")
        if item_id == own_id or item_id in dismissed:
            continue
        pair = engine.score(member, item)
        if pair.score < PLAYER_MERGE_SUGGEST_MIN_SCORE:
            continue
        scored.append((pair.score, item, pair.reasons))
    scored.sort(key=lambda entry: entry[0], reverse=True)
    candidates: list[dict[str, Any]] = []
    for position, (score, item, reasons) in enumerate(scored[:20]):
        item_id = str(item.get("id") or "")
        candidates.append({
            "id": item_id,
            "player_id": str(item.get("player_id") or ""),
            "name": str(item.get("name") or ""),
            "full_name": str(item.get("full_name") or item.get("name") or ""),
            "clubs": _member_club_names(store, item),
            "career": _member_career_summary(store, item_id),
            "match_percent": round(score * 100),
            "reasons": reasons,
            "recommended": position == 0,
            "older_name": str(member.get("name") or "") if choose_survivor(store, own_id, item_id)[0] == own_id else str(item.get("name") or ""),
            "newer_name": str(item.get("name") or "") if choose_survivor(store, own_id, item_id)[0] == own_id else str(member.get("name") or ""),
            "pending_request_id": _pending_merge_request(own_id, item_id),
        })
    with _auth_connection() as connection:
        rows = connection.execute(
            "SELECT id, target_member_id, status, created_at, decision_note FROM app_merge_requests WHERE requester_member_id = ? ORDER BY id DESC LIMIT 10",
            (own_id,),
        ).fetchall()
    requests = []
    for row in rows:
        target = _member_by_id(store, str(row["target_member_id"]))
        requests.append({
            "id": int(row["id"]),
            "target_name": str(target.get("name") or "") if target else "Removed player",
            "status": str(row["status"]),
            "created_at": str(row["created_at"] or ""),
            "decision_note": str(row["decision_note"] or ""),
        })
    return {"candidates": candidates, "requests": requests}


@app.post("/api/player/merge-requests")
def player_request_merge(request: MergeRequestCreate, x_auth_token: str | None = Header(default=None)) -> dict[str, Any]:
    """A player asks for two records of the same person to be merged. Only a club admin or superadmin decides."""
    user_row, _ = _auth_user_from_token(x_auth_token)
    store = load_store()
    member = _member_for_user(store, user_row)
    if not member:
        raise HTTPException(status_code=400, detail="This signed-in account is not linked to a player profile.")
    own_id = str(member.get("id") or "")
    target_id = str(request.target_member_id or "").strip()
    target = _member_by_id(store, target_id)
    if not target or target_id == own_id:
        raise HTTPException(status_code=400, detail="Choose another player to merge with.")
    if _match_engine(store).score(member, target).score < PLAYER_MERGE_SUGGEST_MIN_SCORE:
        raise HTTPException(status_code=400, detail="Only players that the engine finds to be the same person can be merged.")
    keep = str(request.keep or "older").strip().lower()
    if keep not in {"older", "newer"}:
        raise HTTPException(status_code=400, detail="Choose whether to keep the older or the newer record.")
    older_id, _ = choose_survivor(store, own_id, target_id)
    keep_member_id = (older_id if keep == "older" else (target_id if older_id == own_id else own_id))
    existing = _pending_merge_request(own_id, target_id)
    if existing:
        return {"message": "A merge request for this player is already waiting for a club admin.", "request_id": existing, "status": "pending"}
    with _auth_connection() as connection:
        cursor = connection.execute(
            """
            INSERT INTO app_merge_requests (requester_user_id, requester_member_id, target_member_id, status, created_at, keep_member_id)
            VALUES (?, ?, ?, 'pending', ?, ?)
            """,
            (int(user_row["id"]), own_id, target_id, now_iso(), keep_member_id),
        )
        request_id = int(cursor.lastrowid)
    _audit_event("player.merge_requested", "member", own_id, actor=user_row, club_id="", club_name="", details={"target_member_id": target_id, "request_id": request_id, "keep_member_id": keep_member_id}, source="api")
    kept_name = str((_member_by_id(store, keep_member_id) or {}).get("name") or "that record")
    return {"message": f"Request sent. A club admin will review the merge and keep '{kept_name}'.", "request_id": request_id, "status": "pending"}


@app.get("/api/admin/merge-requests")
def admin_merge_requests(x_auth_token: str | None = Header(default=None)) -> dict[str, Any]:
    user_row, current_club_id = _require_permission(x_auth_token, "manage_players")
    store = load_store()
    with _auth_connection() as connection:
        rows = connection.execute(
            """
            SELECT r.id, r.requester_member_id, r.target_member_id, r.created_at, u.display_name AS requester
            FROM app_merge_requests r LEFT JOIN app_users u ON u.id = r.requester_user_id
            WHERE r.status = 'pending' ORDER BY r.created_at
            """
        ).fetchall()
    requests: list[dict[str, Any]] = []
    for row in rows:
        first = _member_by_id(store, str(row["requester_member_id"]))
        second = _member_by_id(store, str(row["target_member_id"]))
        if not first or not second:
            continue
        if not (_reviewer_can_decide(store, user_row, current_club_id, first) and _reviewer_can_decide(store, user_row, current_club_id, second)):
            continue
        requests.append({
            "id": int(row["id"]),
            "requester_name": str(first.get("name") or ""),
            "requester_player_id": str(first.get("player_id") or ""),
            "target_member_id": str(second.get("id") or ""),
            "target_name": str(second.get("name") or ""),
            "target_player_id": str(second.get("player_id") or ""),
            "requested_by": str(row["requester"] or ""),
            "created_at": str(row["created_at"] or ""),
        })
    return {"requests": requests}


@app.post("/api/admin/merge-requests/{request_id}/decision")
def admin_decide_merge_request(request_id: int, request: MergeRequestDecision, x_auth_token: str | None = Header(default=None)) -> dict[str, Any]:
    user_row, current_club_id = _require_permission(x_auth_token, "manage_players")
    decision = str(request.decision or "").strip().lower()
    if decision not in {"approve", "reject"}:
        raise HTTPException(status_code=400, detail="Decision must be approve or reject.")
    with _auth_connection() as connection:
        row = connection.execute("SELECT * FROM app_merge_requests WHERE id = ?", (request_id,)).fetchone()
    if not row or row["status"] != "pending":
        raise HTTPException(status_code=404, detail="This request was not found or was already decided.")
    store = load_store()
    requester_id, target_id = str(row["requester_member_id"]), str(row["target_member_id"])
    members = [_member_by_id(store, requester_id), _member_by_id(store, target_id)]
    if not all(members):
        raise HTTPException(status_code=409, detail="One of these players no longer exists. Reject this request.")
    if not all(_reviewer_can_decide(store, user_row, current_club_id, member) for member in members):
        raise HTTPException(status_code=403, detail="You can only decide requests for players in your clubs.")
    merge_id: int | None = None
    status = "rejected"
    if decision == "approve":
        result = _perform_member_merge(store, requester_id, target_id, user_row, row["keep_member_id"])
        merge_id = int(result["merge_id"])
        status = "approved"
    with _auth_connection() as connection:
        connection.execute(
            "UPDATE app_merge_requests SET status = ?, decided_at = ?, decided_by_user_id = ?, decision_note = ?, merge_id = ? WHERE id = ?",
            (status, now_iso(), int(user_row["id"]), str(request.note or "").strip()[:500], merge_id, request_id),
        )
    _audit_event("player.merge_request_" + status, "member", requester_id, actor=user_row, club_id="", club_name="", details={"target_member_id": target_id, "request_id": request_id, "merge_id": merge_id}, source="api")
    return {"status": status, "request_id": request_id, "merge_id": merge_id}


@app.post("/api/player/profile")
def save_player_profile(request: PlayerSelfProfileRequest, x_auth_token: str | None = Header(default=None)) -> dict[str, Any]:
    user_row, current_club_id = _auth_user_from_token(x_auth_token)
    store = load_store()
    member = _member_for_user(store, user_row)
    if not member:
        raise HTTPException(status_code=400, detail="This signed-in account is not linked to a player profile.")

    updates = request.model_dump()
    updates["phone"] = canonical_phone(updates.get("phone", ""))
    if updates["phone"] and any(
        canonical_phone(other.get("phone", "")) == updates["phone"] and other.get("id") != member.get("id")
        for other in store.get("members", [])
    ):
        raise HTTPException(status_code=409, detail="A player with this mobile number already exists.")
    if isinstance(updates.get("aliases"), str):
        updates["aliases"] = [alias.strip() for alias in updates["aliases"].split(",") if alias.strip()]
    if isinstance(updates.get("team_memberships"), str):
        updates["team_memberships"] = [team.strip() for team in updates["team_memberships"].split(",") if team.strip()]
    updates["email"] = str(updates.get("email", "") or "").strip()
    updates["full_name"] = str(updates.get("full_name", "") or "").strip()
    updates["gender"] = _normalize_gender(updates.get("gender", ""))
    updates["date_of_birth"] = _validated_date_of_birth(updates.get("date_of_birth", ""))
    updates["role"] = str(updates.get("role", "") or "").strip()
    updates["batting_style"] = str(updates.get("batting_style", "") or "").strip()
    updates["bowling_style"] = str(updates.get("bowling_style", "") or "").strip()
    updates["notes"] = str(updates.get("notes", "") or "").strip()
    updates["age"] = int(updates.get("age", 0) or 0)
    typed_teams = list(updates.pop("team_memberships", None) or [])
    updates["aliases"] = list(updates.get("aliases") or [])
    selected_primary_club_id = str(updates.pop("primary_club_id", "") or "").strip()

    for key, value in updates.items():
        member[key] = value
    # Nov 4 2026 (Amit: "team memberships show only Amit CC after saving"): saving the profile used to REPLACE the
    # player's club links with the typed text, so Heartlake / Coca Cola disappeared everywhere. Club memberships
    # now come from the games played (and club admins); a typed club name that matches a registered club is
    # ADDED, nothing is ever removed here.
    _add_member_clubs_by_name(store, member, typed_teams)

    save_store(store)

    if selected_primary_club_id:
        with _auth_connection() as connection:
            connection.execute(
                "UPDATE app_users SET primary_club_id = ? WHERE id = ?",
                (selected_primary_club_id, int(user_row["id"])),
            )
            connection.execute(
                "UPDATE app_auth_sessions SET current_club_id = ? WHERE token = ?",
                (selected_primary_club_id, x_auth_token),
            )
        current_club_id = selected_primary_club_id
        selected_club = _selected_club(store, selected_primary_club_id)
        _audit_event(
            "club.select",
            "club",
            selected_primary_club_id,
            actor=user_row,
            club_id=selected_primary_club_id,
            club_name=str(selected_club.get("name") or selected_club.get("short_name") or ""),
            details={"source": "viewer.profile", "selected_by": user_row["display_name"] or user_row["mobile"] or "user"},
            source="api",
        )
    _audit_event(
        "player.profile.update",
        "member",
        str(member.get("id") or ""),
        actor=user_row,
        club_id=str(current_club_id or ""),
        club_name=str(_selected_club(store, current_club_id).get("name") or ""),
        details={
            "fields": sorted(list(updates.keys()) + (["primary_club_id"] if selected_primary_club_id else [])),
        },
        source="api",
    )

    return player_profile_data(x_auth_token)


@app.get("/api/cache-status")
def cache_status() -> dict[str, Any]:
    return {
        "store_cache": str(CACHE_FILE),
        "dashboard_cache": str(DASHBOARD_CACHE_FILE),
        "store_cache_exists": CACHE_FILE.exists(),
        "dashboard_cache_exists": DASHBOARD_CACHE_FILE.exists(),
    }


@app.get("/api/admin/db/export")
def export_database(x_auth_token: str | None = Header(default=None)) -> FileResponse:
    _require_superadmin(x_auth_token)
    if not DATABASE_FILE.exists():
        raise HTTPException(status_code=404, detail="Database file not found.")
    # A complete snapshot (including changes still in the -wal file), deleted after it is sent.
    snapshot = DATABASE_FILE.with_name(f"{DATABASE_FILE.stem}.export-{uuid.uuid4().hex[:8]}{DATABASE_FILE.suffix}")
    _sqlite_copy(DATABASE_FILE, snapshot)
    return FileResponse(
        path=snapshot,
        filename=DATABASE_FILE.name,
        media_type="application/x-sqlite3",
        background=BackgroundTask(lambda: snapshot.unlink(missing_ok=True)),
    )


@app.post("/api/admin/db/import")
async def import_database(
    database: UploadFile = File(...),
    x_auth_token: str | None = Header(default=None),
) -> dict[str, Any]:
    _require_superadmin(x_auth_token)
    filename = str(database.filename or "").strip().lower()
    if not filename.endswith((".db", ".sqlite", ".sqlite3")):
        raise HTTPException(status_code=400, detail="Upload a SQLite database file.")

    payload = await database.read()
    if not payload:
        raise HTTPException(status_code=400, detail="Uploaded database file is empty.")

    incoming_path = DATABASE_FILE.with_suffix(f"{DATABASE_FILE.suffix}.incoming")
    backup_path = _validated_database_backup_path()
    incoming_path.write_bytes(payload)

    try:
        with sqlite3.connect(str(incoming_path)) as connection:
            connection.row_factory = sqlite3.Row
            integrity_row = connection.execute("PRAGMA integrity_check").fetchone()
            if not integrity_row or str(integrity_row[0] or "").strip().lower() != "ok":
                raise HTTPException(status_code=400, detail="Uploaded database failed integrity check.")
            required_tables = {"clubs", "members", "fixtures", "archives", "app_user_profile"}
            existing_tables = {
                str(row[0]).strip()
                for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()
            }
            if not required_tables.issubset(existing_tables):
                missing = ", ".join(sorted(required_tables - existing_tables))
                raise HTTPException(status_code=400, detail=f"Uploaded database is missing required tables: {missing}")
    except HTTPException:
        incoming_path.unlink(missing_ok=True)
        raise
    except Exception as exc:
        incoming_path.unlink(missing_ok=True)
        raise HTTPException(status_code=400, detail=f"Unable to validate uploaded database: {exc}") from exc

    # Keep a complete copy of the current data, then load the uploaded data into the live database through
    # SQLite (swapping the file under a WAL database could apply an old -wal file to the new data).
    try:
        old_version = 0
        if DATABASE_FILE.exists():
            _sqlite_copy(DATABASE_FILE, backup_path)
            with sqlite3.connect(str(DATABASE_FILE), timeout=60) as live:
                try:
                    row = live.execute("SELECT version FROM app_store_version WHERE id = 1").fetchone()
                    old_version = int(row[0]) if row else 0
                except sqlite3.OperationalError:
                    old_version = 0
        _sqlite_copy(incoming_path, DATABASE_FILE)
        # New data: every worker must drop its in-memory copy (README "Fresh data on every request").
        live = sqlite3.connect(str(DATABASE_FILE), timeout=60)
        try:
            live.execute("CREATE TABLE IF NOT EXISTS app_store_version (id INTEGER PRIMARY KEY CHECK (id = 1), version INTEGER NOT NULL)")
            row = live.execute("SELECT version FROM app_store_version WHERE id = 1").fetchone()
            new_version = max(old_version, int(row[0]) if row else 0) + 1
            live.execute(
                "INSERT INTO app_store_version (id, version) VALUES (1, ?) ON CONFLICT(id) DO UPDATE SET version = excluded.version",
                (new_version,),
            )
            live.commit()
        finally:
            live.close()
    finally:
        incoming_path.unlink(missing_ok=True)

    refreshed_store = load_store()
    return {
        "ok": True,
        "database_file": str(DATABASE_FILE),
        "backup_file": str(backup_path) if backup_path.exists() else "",
        "members": len(refreshed_store.get("members", []) or []),
        "fixtures": len(refreshed_store.get("fixtures", []) or []),
        "archives": len(refreshed_store.get("archive_uploads", []) or []),
    }


@app.post("/api/members")
def create_member(request: MemberCreateRequest, x_auth_token: str | None = Header(default=None)) -> dict[str, Any]:
    user_row, current_club_id = _require_permission(x_auth_token, "manage_players")
    store = load_store()
    selected_club = _selected_club(store, request.club_id or current_club_id)
    if str(selected_club.get("id") or "").strip() != str(current_club_id or "").strip():
        raise HTTPException(status_code=403, detail="You can only invite players into your selected club.")
    phone = canonical_phone(request.phone)
    existing_member = next(
        (
            member
            for member in store["members"]
            if (
                phone
                and canonical_phone(member.get("phone", "")) == phone
            )
            or (
                str(member.get("name") or "").strip().lower() == str(request.name or "").strip().lower()
            )
            or (
                str(member.get("full_name") or "").strip().lower() == str(request.full_name or "").strip().lower()
                and str(request.full_name or "").strip()
            )
        ),
        None,
    )
    aliases = request.aliases
    if isinstance(aliases, str):
        aliases = [alias.strip() for alias in aliases.split(",") if alias.strip()]
    team_memberships = request.team_memberships
    if isinstance(team_memberships, str):
        team_memberships = [team.strip() for team in team_memberships.split(",") if team.strip()]
    club_team_name = str(selected_club.get("short_name") or selected_club.get("name") or request.team_name or "Club").strip()
    if not team_memberships:
        team_memberships = [club_team_name]
    elif club_team_name and club_team_name not in team_memberships:
        team_memberships.insert(0, club_team_name)
    if existing_member:
        member = existing_member
        member["name"] = request.name or member.get("name") or ""
        member["full_name"] = request.full_name or member.get("full_name") or request.name or ""
        member["gender"] = _normalize_gender(request.gender) or member.get("gender", "")
        member["team_name"] = club_team_name
        existing_memberships = list(member.get("team_memberships") or [])
        merged_memberships = []
        seen_memberships: set[str] = set()
        for value in list(team_memberships) + existing_memberships:
            clean = str(value or "").strip()
            key = clean.lower()
            if not clean or key in seen_memberships:
                continue
            seen_memberships.add(key)
            merged_memberships.append(clean)
        member["team_memberships"] = merged_memberships
        member["aliases"] = list(dict.fromkeys([*(member.get("aliases") or []), *aliases]))
        member["age"] = request.age or member.get("age", 0)
        member["role"] = request.role or member.get("role", "")
        member["batting_style"] = request.batting_style or member.get("batting_style", "")
        member["bowling_style"] = request.bowling_style or member.get("bowling_style", "")
        member["notes"] = request.notes or member.get("notes", "")
        member["picture"] = member.get("picture") or member_initials(member["name"] or request.name)
        member["picture_url"] = request.picture_url or member.get("picture_url", "")
        member["phone"] = phone or member.get("phone", "")
        member["email"] = request.email or member.get("email", "")
        member["jersey_number"] = request.jersey_number or member.get("jersey_number", "")
    else:
        member = {
            "id": str(uuid.uuid4())[:8],
            "name": request.name,
            "full_name": request.full_name,
            "gender": _normalize_gender(request.gender),
            "team_name": club_team_name,
            "team_memberships": team_memberships,
            "aliases": aliases,
            "age": request.age,
            "role": request.role,
            "batting_style": request.batting_style,
            "bowling_style": request.bowling_style,
            "notes": request.notes,
            "picture": member_initials(request.name),
            "picture_url": request.picture_url,
            "phone": phone,
            "email": request.email,
            "jersey_number": request.jersey_number,
        }
        store["members"].append(member)
    _attach_creator_to_club(store, selected_club, member)
    with _auth_connection() as connection:
        existing_user = connection.execute(
            "SELECT * FROM app_users WHERE mobile = ? OR email = ?",
            (phone or None, str(request.email or "").strip().lower() or None),
        ).fetchone()
        if existing_user and not existing_user["member_id"]:
            connection.execute(
                "UPDATE app_users SET member_id = ?, primary_club_id = ? WHERE id = ?",
                (member["id"], selected_club.get("id", ""), int(existing_user["id"])),
            )
    save_store(store)
    _audit_event(
        "player.create",
        "member",
        str(member.get("id") or ""),
        actor=user_row,
        club_id=str(selected_club.get("id") or ""),
        club_name=str(selected_club.get("name") or ""),
        details={
            "name": member.get("name") or "",
            "full_name": member.get("full_name") or "",
            "phone": phone or "",
            "role": request.role or "",
            "team_name": club_team_name,
        },
        source="api",
    )
    return current_dashboard(load_store(), current_club_id)


@app.post("/api/members/{member_id}")
def update_member(member_id: str, request: MemberUpdateRequest, x_auth_token: str | None = Header(default=None)) -> dict[str, Any]:
    user_row, current_club_id = _require_permission(x_auth_token, "manage_players")
    store = load_store()
    member = next((item for item in store["members"] if item.get("id") == member_id), None)
    if not member:
        raise HTTPException(status_code=404, detail="Player not found.")

    before = dict(member)
    updates = request.model_dump(exclude_none=True)
    if "phone" in updates:
        updates["phone"] = canonical_phone(updates["phone"])
        if updates["phone"] and any(
            canonical_phone(other.get("phone", "")) == updates["phone"] and other.get("id") != member_id
            for other in store["members"]
        ):
            raise HTTPException(status_code=409, detail="A player with this mobile number already exists.")
    if "aliases" in updates and isinstance(updates["aliases"], str):
        updates["aliases"] = [alias.strip() for alias in updates["aliases"].split(",") if alias.strip()]
    if "team_memberships" in updates and isinstance(updates["team_memberships"], str):
        updates["team_memberships"] = [team.strip() for team in updates["team_memberships"].split(",") if team.strip()]
    if "gender" in updates:
        updates["gender"] = _normalize_gender(updates["gender"])

    previous_name = member.get("name", "")
    for key, value in updates.items():
        member[key] = value
    if member.get("name") != previous_name:
        for fixture in store.get("fixtures", []):
            statuses = fixture.get("availability_statuses", {})
            notes = fixture.get("availability_notes", {})
            if previous_name in statuses:
                statuses[member["name"]] = statuses.pop(previous_name)
            if previous_name in notes:
                notes[member["name"]] = notes.pop(previous_name)
            for performance in fixture.get("performances", []):
                if performance.get("player_name") == previous_name:
                    performance["player_name"] = member["name"]
        for upload in store.get("archive_uploads", []):
            for performance in upload.get("suggested_performances", []):
                if performance.get("player_name") == previous_name:
                    performance["player_name"] = member["name"]

    save_store(store)
    club = _selected_club(store, current_club_id)
    _audit_event(
        "player.update",
        "member",
        member_id,
        actor=user_row,
        club_id=club.get("id", ""),
        club_name=club.get("name", ""),
        details={
            "before_name": before.get("name", ""),
            "after_name": member.get("name", ""),
            "fields": sorted(updates.keys()),
        },
        source="api",
    )
    return current_dashboard(load_store())


def _delete_club_member_core(club_id: str, member_id: str, token: str | None, confirmation: str = "") -> dict[str, Any]:
    user_row, _ = _auth_user_from_token(token)
    _require_superadmin(token)
    store = load_store()
    club = next((item for item in store.get("clubs", []) if str(item.get("id") or "").strip() == str(club_id or "").strip()), None)
    if not club:
        raise HTTPException(status_code=404, detail="Club not found.")
    member = next((item for item in store.get("members", []) if str(item.get("id") or "").strip() == str(member_id or "").strip()), None)
    if not member:
        raise HTTPException(status_code=404, detail="Player not found.")
    if not member_in_club(member, str(club.get("id") or ""), str(club.get("name") or "")):
        raise HTTPException(status_code=403, detail="This player is not part of the selected club.")

    expected = str(member.get("name") or "").strip()
    if str(confirmation or "").strip() != expected:
        raise HTTPException(status_code=400, detail=f'Type "{expected}" exactly to confirm removal from the club.')

    keep_member, removed_name = _retarget_member_team_memberships(member, club)
    remaining_memberships = list(member.get("club_memberships", []) or [])
    fallback_primary_club_id = ""
    if remaining_memberships:
        fallback_primary_club_id = str(remaining_memberships[0].get("club_id") or "").strip()
    elif keep_member:
        first_membership = (member.get("team_memberships") or [{}])[0]
        fallback_primary_club_id = str(first_membership.get("club_id") or "").strip() if isinstance(first_membership, dict) else ""
    _unlink_member_from_club_auth(member_id, str(club.get("id") or ""), fallback_primary_club_id)
    save_store(store)
    refreshed = load_store()
    _audit_event(
        "player.unlink",
        "member",
        member_id,
        actor=user_row,
        club_id=str(club.get("id") or ""),
        club_name=str(club.get("name") or ""),
        details={
            "member_name": member.get("name") or "",
            "fallback_primary_club_id": fallback_primary_club_id,
        },
        source="api",
    )
    return {
        "message": f"{member.get('name') or 'Player'} removed from {club.get('name') or 'the club'} roster.",
        "dashboard": current_dashboard(refreshed, club.get("id", "")),
        "club_id": str(club.get("id") or "").strip(),
        "club_name": str(club.get("name") or "").strip(),
        "member_name": str(member.get("name") or "").strip(),
    }


def _club_blocking_deletion(store: dict[str, Any], club: dict[str, Any]) -> dict[str, int]:
    """What stops a club being deleted: players linked to it, and matches (fixtures or scorecards) it is part of."""
    club_id = str(club.get("id") or "").strip()
    club_name = str(club.get("name") or "").strip()
    players = sum(1 for member in store.get("members", []) or [] if member_in_club(member, club_id, club_name))
    fixtures = sum(
        1
        for fixture in store.get("fixtures", []) or []
        if str(fixture.get("club_id") or "").strip() == club_id
        or _club_matches_removed_club("", str(fixture.get("opponent") or ""), club)
    )
    scorecards = sum(
        1
        for archive in store.get("archive_uploads", []) or []
        if archive_belongs_to_club(archive, club, store.get("clubs", []), store.get("members", []), store.get("fixtures", []))
    )
    return {"players": players, "matches": fixtures, "scorecards": scorecards}


def _describe_deletion_blockers(blockers: dict[str, int]) -> str:
    return ", ".join(
        f"{count} {label}"
        for label, count in (("player(s)", blockers.get("players", 0)), ("match(es)", blockers.get("matches", 0)), ("scorecard(s)", blockers.get("scorecards", 0)))
        if count
    )


def _delete_club_core(club_id: str, token: str | None, confirmation: str = "") -> dict[str, Any]:
    user_row, _ = _auth_user_from_token(token)
    _require_superadmin(token)
    store = load_store()
    club = next((item for item in store.get("clubs", []) if str(item.get("id") or "").strip() == str(club_id or "").strip()), None)
    if not club:
        raise HTTPException(status_code=404, detail="Club not found.")

    removed_club_id = str(club.get("id") or "").strip()
    removed_club_name = str(club.get("name") or "").strip()
    removed_short_name = str(club.get("short_name") or "").strip()

    blockers = _club_blocking_deletion(store, club)
    if any(blockers.values()):
        raise HTTPException(
            status_code=409,
            detail=f"{removed_club_name} cannot be deleted: it still has {_describe_deletion_blockers(blockers)}. A club can only be deleted when it has no matches and no players. Disable it instead to keep its history.",
        )

    expected = str(club.get("name") or "").strip()
    if str(confirmation or "").strip() != expected:
        raise HTTPException(status_code=400, detail=f'Type "{expected}" exactly to confirm club deletion.')

    replacement_club = next(
        (
            item
            for item in store.get("clubs", [])
            if str(item.get("id") or "").strip() != removed_club_id
        ),
        {},
    )
    replacement_club_id = str(replacement_club.get("id") or "").strip()

    retained_members: list[dict[str, Any]] = []
    removed_member_names: list[str] = []
    for member in list(store.get("members", [])):
        if not member_in_club(member, removed_club_id, removed_club_name):
            retained_members.append(member)
            continue
        keep_member, removed_name = _retarget_member_team_memberships(member, club)
        if keep_member:
            retained_members.append(member)
        else:
            member_name = removed_name or str(member.get("name") or "").strip()
            removed_member_names.append(member_name)
            _prune_member_references(store, str(member.get("id") or ""), member_name, club)
            _unlink_member_from_auth(str(member.get("id") or ""))

    store["members"] = retained_members
    store["teams"] = [
        team
        for team in store.get("teams", [])
        if not _club_matches_removed_club(team.get("club_id", ""), team.get("club_name", ""), club)
        and not _club_matches_removed_club(team.get("id", ""), team.get("name", ""), club)
    ]
    store["fixtures"] = [
        fixture
        for fixture in store.get("fixtures", [])
        if str(fixture.get("club_id") or "").strip() != removed_club_id
    ]

    cleaned_archives: list[dict[str, Any]] = []
    for archive in store.get("archive_uploads", []):
        club_ids = [
            item
            for item in _coerce_archive_string_list(archive.get("club_ids"))
            if str(item or "").strip().lower() != removed_club_id.lower()
        ]
        club_names = [
            item
            for item in _coerce_archive_string_list(archive.get("club_names"))
            if str(item or "").strip().lower() not in {removed_club_id.lower(), removed_club_name.lower(), removed_short_name.lower()}
        ]
        primary_club_id = str(archive.get("club_id") or "").strip()
        primary_club_name = str(archive.get("club_name") or "").strip()
        if primary_club_id.lower() == removed_club_id.lower() or primary_club_name.lower() in {
            removed_club_id.lower(),
            removed_club_name.lower(),
            removed_short_name.lower(),
        }:
            primary_club_id = club_ids[0] if club_ids else replacement_club_id
            primary_club_name = ""
        if not club_ids and not primary_club_id:
            continue
        archive["club_ids"] = list(dict.fromkeys([item for item in club_ids if str(item or "").strip()]))
        if primary_club_id:
            archive["club_id"] = primary_club_id
        if primary_club_name:
            archive["club_name"] = primary_club_name
        elif primary_club_id:
            resolved = _club_by_identifier(store.get("clubs", []), primary_club_id)
            if resolved:
                archive["club_name"] = str(resolved.get("name") or resolved.get("short_name") or "").strip()
        archive["club_names"] = list(dict.fromkeys([item for item in club_names if str(item or "").strip()]))
        cleaned_archives.append(archive)
    store["archive_uploads"] = cleaned_archives

    viewer_profile = dict(store.get("viewer_profile", {}))
    current_primary = str(viewer_profile.get("primary_club_id") or "").strip()
    if current_primary.lower() == removed_club_id.lower():
        viewer_profile["primary_club_id"] = replacement_club_id
        replacement = _club_by_identifier(store.get("clubs", []), replacement_club_id) if replacement_club_id else None
        viewer_profile["primary_club_name"] = str((replacement or {}).get("name") or replacement_club_id or "").strip()
    viewer_profile["followed_player_names"] = [
        name
        for name in viewer_profile.get("followed_player_names", []) or []
        if str(name or "").strip() not in set(removed_member_names)
    ]
    store["viewer_profile"] = viewer_profile

    store["clubs"] = [
        item
        for item in store.get("clubs", [])
        if str(item.get("id") or "").strip() != removed_club_id
    ]
    store["club"] = _selected_club(store, replacement_club_id) if replacement_club_id else {}

    _retarget_club_links_after_deletion(removed_club_id, replacement_club_id)
    save_store(store)
    refreshed = load_store()
    _audit_event(
        "club.delete",
        "club",
        removed_club_id,
        actor=user_row,
        club_id=removed_club_id,
        club_name=removed_club_name,
        details={
            "replacement_club_id": replacement_club_id,
            "removed_members": removed_member_names,
            "retained_archive_count": len(cleaned_archives),
        },
        source="api",
    )
    return {
        "message": f"{club.get('name') or 'Club'} removed from the database.",
        "dashboard": current_dashboard(refreshed, replacement_club_id),
        "club_id": replacement_club_id,
        "club_name": removed_club_name,
    }


def _set_club_disabled_core(club_id: str, token: str | None, disabled: bool, confirmation: str = "") -> dict[str, Any]:
    user_row, _ = _auth_user_from_token(token)
    _require_superadmin(token)
    store = load_store()
    club = next((item for item in store.get("clubs", []) if str(item.get("id") or "").strip() == str(club_id or "").strip()), None)
    if not club:
        raise HTTPException(status_code=404, detail="Club not found.")
    club_name = str(club.get("name") or "Club").strip()
    if disabled and str(confirmation or "").strip() != club_name:
        raise HTTPException(status_code=400, detail=f'Type "{club_name}" exactly to confirm disabling this club.')
    club["is_disabled"] = bool(disabled)
    primary = store.get("club")
    if isinstance(primary, dict) and str(primary.get("id") or "").strip() == str(club.get("id") or "").strip():
        primary["is_disabled"] = bool(disabled)
    save_store(store)
    _audit_event(
        "club.disable" if disabled else "club.enable",
        "club",
        str(club.get("id") or ""),
        actor=user_row,
        club_id=str(club.get("id") or ""),
        club_name=club_name,
        details={"is_disabled": bool(disabled)},
        source="api",
    )
    return {"message": f"{club_name} {'disabled' if disabled else 're-enabled'}.", "club_id": str(club.get("id") or ""), "club_name": club_name}


@app.post("/api/admin/clubs/{club_id}/disable")
def disable_club_form(request: Request, club_id: str, confirmation: str = Form(default="")) -> Response:
    try:
        result = _set_club_disabled_core(club_id, _auth_token_from_request(request), True, confirmation)
        return _redirect_to_admin_center(club_id, result["message"], "success")
    except HTTPException as exc:
        return _redirect_to_admin_center(club_id, str(exc.detail), "error")


@app.post("/api/admin/clubs/{club_id}/enable")
def enable_club_form(request: Request, club_id: str) -> Response:
    try:
        result = _set_club_disabled_core(club_id, _auth_token_from_request(request), False)
        return _redirect_to_admin_center(club_id, result["message"], "success")
    except HTTPException as exc:
        return _redirect_to_admin_center(club_id, str(exc.detail), "error")


@app.delete("/api/admin/clubs/{club_id}/members/{member_id}")
def delete_club_member(
    club_id: str,
    member_id: str,
    x_auth_token: str | None = Header(default=None),
) -> dict[str, Any]:
    return _delete_club_member_core(club_id, member_id, x_auth_token)


@app.post("/api/admin/clubs/{club_id}/members/{member_id}/delete")
def delete_club_member_form(
    request: Request,
    club_id: str,
    member_id: str,
    confirmation: str = Form(default=""),
) -> Response:
    try:
        result = _delete_club_member_core(club_id, member_id, _auth_token_from_request(request), confirmation)
        return _redirect_to_admin_center(result.get("club_id", club_id), result.get("message", "Player removed."), "success")
    except HTTPException as exc:
        return _redirect_to_admin_center(club_id, str(exc.detail), "error")


@app.get("/api/admin/clubs/{club_id}/delete-check")
def delete_club_check(club_id: str, x_auth_token: str | None = Header(default=None)) -> dict[str, Any]:
    _require_superadmin(x_auth_token)
    store = load_store()
    club = next((item for item in store.get("clubs", []) if str(item.get("id") or "").strip() == str(club_id or "").strip()), None)
    if not club:
        raise HTTPException(status_code=404, detail="Club not found.")
    blockers = _club_blocking_deletion(store, club)
    return {"can_delete": not any(blockers.values()), "blockers": blockers, "reason": _describe_deletion_blockers(blockers)}


@app.delete("/api/admin/clubs/{club_id}")
def delete_club(
    club_id: str,
    x_auth_token: str | None = Header(default=None),
) -> dict[str, Any]:
    return _delete_club_core(club_id, x_auth_token)


@app.post("/api/admin/clubs/{club_id}/delete")
def delete_club_form(
    request: Request,
    club_id: str,
    confirmation: str = Form(default=""),
) -> Response:
    try:
        result = _delete_club_core(club_id, _auth_token_from_request(request), confirmation)
        return _redirect_to_admin_center(result.get("club_id", ""), result.get("message", "Club removed."), "success")
    except HTTPException as exc:
        return _redirect_to_admin_center(club_id, str(exc.detail), "error")


@app.post("/api/matches/{match_id}/details")
def update_match_details(match_id: str, request: MatchDetailsRequest, x_auth_token: str | None = Header(default=None)) -> dict[str, Any]:
    user_row, _ = _require_permission(x_auth_token, "manage_fixtures")
    store = load_store()
    try:
        match = get_match_or_404(store, match_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))

    updates = request.model_dump(exclude_none=True)
    for key, value in updates.items():
        if key == "heartlake_captain":
            match["heartlake_captain"] = value
        elif key == "status":
            match["status"] = value
        else:
            match["details"][key] = value
    _touch_fixture_audit(match, user_row)
    save_store(store)
    _audit_event(
        "fixture.update",
        "fixture",
        match_id,
        actor=user_row,
        club_id=str(match.get("club_id") or ""),
        club_name=str(match.get("club_name") or ""),
        details={"fields": sorted(updates.keys())},
        source="api",
    )
    return current_dashboard(load_store())


@app.post("/api/matches/{match_id}/availability")
def update_availability(match_id: str, request: AvailabilityUpdateRequest, x_auth_token: str | None = Header(default=None)) -> dict[str, Any]:
    user_row, current_club_id = _auth_user_from_token(x_auth_token)
    store = load_store()
    try:
        match = get_match_or_404(store, match_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    _require_not_past(match, "availability")

    member = _member_for_user(store, user_row)
    if not member:
        raise HTTPException(status_code=400, detail="This signed-in account is not linked to a player profile.")
    effective_role = _effective_role_name(user_row, current_club_id)
    can_edit_other_availability = effective_role in {"captain", "club_admin", "superadmin"}
    requested_player_name = resolve_member_name(store, request.player_name) if request.player_name else ""
    player_name = member.get("name", "")
    if can_edit_other_availability and requested_player_name:
        player_name = requested_player_name
    elif requested_player_name and requested_player_name != player_name:
        raise HTTPException(status_code=403, detail="Only captains, club admins, or superadmins can update another player's availability.")
    if player_name != member.get("name", ""):
        _require_feature(user_row, current_club_id, "match_roster")
    else:
        _require_feature(user_row, current_club_id, "availability", club_id=str(match.get("club_id") or current_club_id))
    match["availability_statuses"][player_name] = request.status
    if request.note.strip():
        match["availability_notes"][player_name] = request.note.strip()
    else:
        match["availability_notes"].pop(player_name, None)
    _touch_fixture_audit(match, user_row)
    save_store(store)
    return current_dashboard(load_store(), request.club_id or match.get("club_id") or "")


@app.post("/api/matches/{match_id}/lineup")
def update_playing_xi(match_id: str, request: PlayingXiUpdateRequest, x_auth_token: str | None = Header(default=None)) -> dict[str, Any]:
    user_row, current_club_id = _require_permission(x_auth_token, "manage_fixtures")
    _require_feature(user_row, current_club_id, "playing_xi")
    store = load_store()
    try:
        match = get_match_or_404(store, match_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    _require_not_past(match, "the playing XI")

    effective_role = _effective_role_name(user_row, current_club_id)
    selected_club = _selected_club(store, request.club_id or match.get("club_id") or current_club_id)
    selected_club_id = str(selected_club.get("id") or "").strip()
    match_club_id = str(match.get("club_id") or "").strip()
    if selected_club_id and match_club_id and selected_club_id != match_club_id:
        raise HTTPException(status_code=400, detail="The selected club does not match this fixture.")
    if effective_role != "superadmin" and selected_club_id and selected_club_id != current_club_id:
        raise HTTPException(status_code=403, detail="You can only manage the playing XI for your selected club.")

    dashboard = current_dashboard(store, selected_club_id or match_club_id or current_club_id)
    club_members = {str(member.get("name") or "").strip(): member for member in dashboard.get("members", [])}
    selected_names: list[str] = []
    selected_member_ids: list[str] = []
    for raw_name in request.player_names or []:
        resolved_name = resolve_member_name(store, raw_name)
        if not resolved_name:
            continue
        member = club_members.get(resolved_name)
        if not member:
            raise HTTPException(status_code=400, detail=f"{resolved_name} is not associated with this club.")
        status = str(match.get("availability_statuses", {}).get(resolved_name, "")).strip().lower()
        if status not in {"available", "maybe"}:
            raise HTTPException(status_code=400, detail=f"{resolved_name} must be marked available or maybe before selection.")
        member_id = str(member.get("id") or "").strip()
        if member_id in selected_member_ids:
            continue
        selected_names.append(resolved_name)
        selected_member_ids.append(member_id)
    if len(selected_names) > 11:
        raise HTTPException(status_code=400, detail="Playing XI can include at most 11 players.")

    match["selected_playing_xi"] = selected_names
    match["selected_playing_xi_member_ids"] = selected_member_ids
    _touch_fixture_audit(match, user_row)
    save_store(store)
    return current_dashboard(load_store(), request.club_id or match.get("club_id") or current_club_id)


@app.post("/api/matches/{match_id}/scorecard")
def update_scorecard(match_id: str, request: ScorecardUpdateRequest, x_auth_token: str | None = Header(default=None)) -> dict[str, Any]:
    user_row, current_club_id = _require_match_score_editor(x_auth_token, match_id)
    store = load_store()
    try:
        match = get_match_or_404(store, match_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))

    updates = request.model_dump(exclude_none=True)
    if _fixture_is_past(match) and "status" in updates:
        current_status = str(match.get("status") or "").strip().lower()
        requested_status = str(updates["status"] or "").strip().lower()
        if requested_status != current_status:
            raise HTTPException(status_code=400, detail="A past match's status cannot be changed while editing its scorecard.")
    for key, value in updates.items():
        if key == "status":
            match["status"] = value
        else:
            match["scorecard"][key] = value
    _touch_fixture_audit(match, user_row)
    save_store(store)
    return current_dashboard(load_store(), str(match.get("club_id") or current_club_id or ""))


@app.post("/api/matches/{match_id}/performances")
def add_performance(match_id: str, request: PerformanceCreateRequest, x_auth_token: str | None = Header(default=None)) -> dict[str, Any]:
    user_row, _ = _require_match_scorer(x_auth_token, match_id)
    store = load_store()
    try:
        match = get_match_or_404(store, match_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    _require_not_past(match, "scores")

    player_name = resolve_member_name(store, request.player_name)
    match["performances"].append(
        {
            "id": str(uuid.uuid4())[:8],
            "player_name": player_name,
            "runs": request.runs,
            "balls": request.balls,
            "wickets": request.wickets,
            "catches": request.catches,
            "fours": request.fours,
            "sixes": request.sixes,
            "notes": request.notes,
            "source": request.source,
            "archive_upload_id": "",
        }
    )
    _touch_fixture_audit(match, user_row)
    save_store(store)
    return current_dashboard(load_store())


@app.post("/api/matches/{match_id}/commentary")
def add_commentary(match_id: str, request: CommentaryRequest, x_auth_token: str | None = Header(default=None)) -> dict[str, Any]:
    user_row, _ = _require_match_scorer(x_auth_token, match_id)
    store = load_store()
    try:
        match = get_match_or_404(store, match_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    _require_not_past(match, "commentary")

    match["commentary"].append(
        {
            "id": str(uuid.uuid4())[:8],
            "mode": request.mode,
            "text": request.text,
            "created_at": now_iso(),
        }
    )
    _touch_fixture_audit(match, user_row)
    save_store(store)
    return current_dashboard(load_store())


@app.post("/api/matches/{match_id}/scorebook/setup")
@_scoring_locked
def update_scorebook_setup(
    match_id: str,
    request: ScorebookSetupRequest,
    edit_mode: bool = False,
    x_auth_token: str | None = Header(default=None),
    x_lite_response: str | None = Header(default=None),
) -> dict[str, Any]:
    user_row, _ = _require_match_scorer(x_auth_token, match_id)
    store = load_store()
    try:
        match = get_match_or_404(store, match_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    if not _scorebook_is_open(match) and not (edit_mode and (_fixture_is_past(match) or _fixture_is_completed(match))):
        raise HTTPException(status_code=400, detail="Live scoring is locked for this fixture. Use authorized edit mode to correct a past scorebook.")

    scorebook = _match_scorebook(match)
    innings_index = max(1, min(2, int(request.innings_number or 1))) - 1
    innings = scorebook["innings"][innings_index]
    if innings.get("balls") or edit_mode:
        user_row, _ = _require_match_score_editor(x_auth_token, match_id)
    # Both line-ups (2-11 players each) must be set before scoring starts (README: "Line-ups and guest matches").
    already_started = any((item.get("balls") or []) for item in scorebook.get("innings", []))
    if not already_started and not _lineups_ready(_match_lineups(match_id)):
        batters = _clean_lineup(request.batters)
        bowlers = _clean_lineup(request.bowlers)
        if len(batters) >= LINEUP_MIN and len(bowlers) >= LINEUP_MIN:
            club_is_batting = request.batting_team.strip().lower() == str(match.get("club_name") or "").strip().lower()
            save_match_lineups(match_id, LineupsRequest(club=batters if club_is_batting else bowlers, opponent=bowlers if club_is_batting else batters), x_auth_token)
        else:
            raise HTTPException(status_code=400, detail=f"Set both teams' line-ups first ({LINEUP_MIN}-{LINEUP_MAX} players each), then start scoring.")
    innings["inning_number"] = innings_index + 1
    innings["batting_team"] = request.batting_team.strip()
    innings["bowling_team"] = request.bowling_team.strip()
    innings["overs_limit"] = max(1, int(request.overs_limit or 20))
    _same_overs_both_innings(match, scorebook, innings)
    innings["target_runs"] = int(request.target_runs) if request.target_runs else None
    innings["status"] = request.status.strip() or "Not started"
    innings["batters"] = [
        {"slot_number": slot, "player_name": str(request.batters[slot - 1] if slot - 1 < len(request.batters) else "").strip()}
        for slot in range(1, 12)
    ]
    innings["bowlers"] = [
        {"slot_number": slot, "player_name": str(request.bowlers[slot - 1] if slot - 1 < len(request.bowlers) else "").strip()}
        for slot in range(1, 12)
    ]
    sync_fixture_scorecard_from_scorebook(match)
    _touch_fixture_audit(match, user_row)
    save_store(store)
    if x_lite_response:
        return {"ok": True}  # the Score page reloads the match itself (README "Faster saving")
    return current_dashboard(load_store())


@app.post("/api/matches/{match_id}/scorebook/ball")
@_scoring_locked
def add_scorebook_ball(
    match_id: str,
    request: ScorebookBallRequest,
    edit_mode: bool = False,
    x_auth_token: str | None = Header(default=None),
    x_lite_response: str | None = Header(default=None),
) -> dict[str, Any]:
    user_row, _ = _require_match_scorer(x_auth_token, match_id)
    store = load_store()
    try:
        match = get_match_or_404(store, match_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    if not _scorebook_is_open(match) and not (edit_mode and (_fixture_is_past(match) or _fixture_is_completed(match))):
        raise HTTPException(status_code=400, detail="Live scoring is locked for this fixture. Use authorized edit mode to correct a past scorebook.")

    scorebook = _match_scorebook(match)
    innings_index = max(1, min(2, int(request.innings_number or 1))) - 1
    innings = scorebook["innings"][innings_index]
    saved_ids = {str(item.get("id") or "") for item in innings.get("balls", [])}
    if edit_mode or (request.id and str(request.id) in saved_ids):
        user_row, _ = _require_match_score_editor(x_auth_token, match_id)
    ball = normalize_scorebook_ball(
        {
            "over_number": request.over_number,
            "ball_number": request.ball_number,
            "striker": resolve_member_name(store, request.striker) if request.striker.strip() else "",
            "non_striker": resolve_member_name(store, request.non_striker) if request.non_striker.strip() else "",
            "bowler": resolve_member_name(store, request.bowler) if request.bowler.strip() else "",
            "runs_bat": request.runs_bat,
            "extras_type": request.extras_type,
            "extras_runs": request.extras_runs,
            "wicket": request.wicket,
            "wicket_type": request.wicket_type,
            "wicket_player": resolve_member_name(store, request.wicket_player) if request.wicket_player.strip() else "",
            "fielder": resolve_member_name(store, request.fielder) if request.fielder.strip() else "",
            "commentary": request.commentary,
            "new_batter": resolve_member_name(store, request.new_batter) if request.new_batter.strip() else "",
        }
    )
    _validate_retired_out_ball(ball)
    if _client_ball_seen(innings, ball, request):
        return {"ok": True, "status": innings.get("status"), "already_saved": True} if x_lite_response else current_dashboard(load_store())
    editing = _apply_ball_edit(innings, ball, request.id)
    if not editing and _innings_is_over(match, innings, _match_lineups(match_id)):
        raise HTTPException(status_code=400, detail="This innings is over. To change the last ball, tap Undo.")
    previous_status = str(innings.get("status") or "")
    before_summary = summarize_innings_scorebook(innings)
    before_summary["status"] = str(innings.get("status") or "")
    innings["balls"] = [item for item in innings.get("balls", []) if item.get("id") != ball["id"]]
    innings["balls"].append(ball)
    innings["balls"].sort(key=lambda item: (int(item.get("over_number", 1) or 1), int(item.get("ball_number", 1) or 1), str(item.get("created_at", ""))))
    if edit_mode:
        _reindex_scorebook_innings(innings)

    for collection_name, player_name in [
        ("batters", ball.get("striker", "")),
        ("batters", ball.get("non_striker", "")),
        ("bowlers", ball.get("bowler", "")),
    ]:
        if not player_name:
            continue
        existing = {str(item.get("player_name", "") or "").strip() for item in innings.get(collection_name, [])}
        if player_name in existing:
            continue
        for slot in innings.get(collection_name, []):
            if not str(slot.get("player_name", "") or "").strip():
                slot["player_name"] = player_name
                break

    summary = summarize_innings_scorebook(innings)
    lineups = _grow_lineups_with_new_players(match_id, match, innings, ball, _match_lineups(match_id), request.new_batter)
    if not (edit_mode and editing):
        if summary["runs"] or summary["wickets"] or summary["legal_balls"]:
            innings["status"] = "Live"
        if scorebook_wickets_for_all_out(innings) >= _all_out_at(match, innings, lineups) or summary["legal_balls"] >= int(innings.get("overs_limit", 20) or 20) * 6:
            innings["status"] = "Completed"
    else:
        innings["status"] = previous_status or "Completed"
    sync_fixture_scorecard_from_scorebook(match)
    _settle_scorebook_result(match, lineups)
    _touch_fixture_audit(match, user_row)
    save_store(store)
    if editing or edit_mode:
        # Historical corrections and appended balls must not send live alerts.
        return {"ok": True, "status": innings.get("status")} if x_lite_response else current_dashboard(load_store())
    # Live score alerts (bell icon): match start, wickets, 50s/100s, end of innings
    try:
        alert_events = muse.live_score_events(match, innings, before_summary, summary, ball)
        if alert_events and not (_has_feature(user_row, "", "score_updates") or _club_is_paid(str(match.get("club_id") or ""))):
            alert_events = []  # Live score alerts are a Pro feature
        for kind, title, body in alert_events:
            _notify(str(match.get("club_id") or ""), kind, title, body, f"/live/{match.get('id')}", str(match.get("id") or ""), "Live scoring")
    except Exception:
        logger.exception("Live score alert failed for match %s", match_id)
    if x_lite_response:
        # The Score page only needs "saved"; the full dashboard is ~1.6 MB per ball on mobile data (README "Faster saving").
        return {"ok": True, "status": innings.get("status")}
    return current_dashboard(load_store())


class ScorebookEditRequest(BaseModel):
    action: str  # "teams" | "rename" | "over_bowler"
    innings_number: int = 1
    batting: str = ""  # teams: "club" or "opponent" bats in innings_number (the other innings is the other team)
    from_name: str = ""  # rename: every place this name is used in the match ...
    to_name: str = ""  # ... becomes this name (pick an existing name to merge two spellings)
    over_number: int = 0  # over_bowler: this over of innings_number ...
    bowler: str = ""  # ... was bowled by this bowler


@app.post("/api/matches/{match_id}/scorebook/edit")
@_scoring_locked
def edit_scorebook(match_id: str, request: ScorebookEditRequest, x_auth_token: str | None = Header(default=None)) -> dict[str, Any]:
    """Fix a scored match (README "Edit a scored match", Nov 1 2026): which team batted in each innings, a player's
    name everywhere in the match (or two spellings of one player merged), the bowler of an over. Captains, club
    admins and site admins only (the same people who score), today's match or one already scored before."""
    user_row, _ = _require_match_score_editor(x_auth_token, match_id)
    store = load_store()
    try:
        match = get_match_or_404(store, match_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    if not any((row.get("balls") or []) for row in (_match_scorebook(match).get("innings") or [])):
        raise HTTPException(status_code=400, detail="This match has no balls scored yet.")
    scorebook = _match_scorebook(match)
    innings_list = sorted(scorebook.get("innings", []), key=lambda row: int(row.get("inning_number") or 1))
    club_name = str(match.get("club_name") or "").strip()
    opponent = str(match.get("opponent") or "").strip()
    action = str(request.action or "").strip().lower()
    lineups = _match_lineups(match_id)
    message = ""
    if action == "teams":
        if request.batting not in {"club", "opponent"} or request.innings_number not in {1, 2}:
            raise HTTPException(status_code=400, detail="Pick which team batted.")
        first_bats = (club_name if request.batting == "club" else opponent) if request.innings_number == 1 else (opponent if request.batting == "club" else club_name)
        second_bats = opponent if first_bats == club_name else club_name
        for row, bats in zip(innings_list, (first_bats, second_bats)):
            row["batting_team"] = bats
            row["bowling_team"] = opponent if bats == club_name else club_name
        message = f"1st innings: {first_bats} batting. 2nd innings: {second_bats} batting."
    elif action == "rename":
        old = " ".join(str(request.from_name or "").split())
        new = " ".join(str(request.to_name or "").split())
        if not old or not new or old == new:
            raise HTTPException(status_code=400, detail="Pick the name to change and type the right name.")
        count = 0
        for row in innings_list:
            for ball in row.get("balls") or []:
                for key in ("striker", "non_striker", "bowler", "fielder", "wicket_player"):
                    if str(ball.get(key) or "").strip().lower() == old.lower():
                        ball[key] = new
                        count += 1
            for key in ("batters", "bowlers"):
                names = [str(slot.get("player_name") or "").strip() for slot in row.get(key) or []]
                if new.lower() in {n.lower() for n in names}:
                    for slot in row.get(key) or []:
                        if str(slot.get("player_name") or "").strip().lower() == old.lower():
                            slot["player_name"] = ""  # merged into the existing name
                else:
                    for slot in row.get(key) or []:
                        if str(slot.get("player_name") or "").strip().lower() == old.lower():
                            slot["player_name"] = new
        if lineups:
            for side in ("club", "opponent"):
                names, seen = [], set()
                for name in lineups.get(side) or []:
                    name = new if name.strip().lower() == old.lower() else name
                    if name.lower() not in seen:
                        seen.add(name.lower())
                        names.append(name)
                lineups[side] = names
                roles = (lineups.get("roles") or {}).get(side) or {}
                for role, name in list(roles.items()):
                    if str(name or "").strip().lower() == old.lower():
                        roles[role] = new
        message = f"{old} is now {new} everywhere in this match ({count} place{'s' if count != 1 else ''})."
    elif action == "over_bowler":
        bowler = " ".join(str(request.bowler or "").split())
        row = next((r for r in innings_list if int(r.get("inning_number") or 1) == int(request.innings_number or 1)), None)
        if row is None or not bowler or int(request.over_number or 0) < 1:
            raise HTTPException(status_code=400, detail="Pick the over and the bowler.")
        changed = [ball for ball in row.get("balls") or [] if int(ball.get("over_number") or 0) == int(request.over_number)]
        if not changed:
            raise HTTPException(status_code=400, detail=f"Over {request.over_number} has no balls yet.")
        for ball in changed:
            ball["bowler"] = bowler
        message = f"Over {request.over_number} is now bowled by {bowler}."
    else:
        raise HTTPException(status_code=400, detail="Unknown change.")
    if lineups and action == "rename":
        with _auth_connection() as connection:
            _ensure_extra_match_tables(connection)
            connection.execute(
                "UPDATE app_match_lineups SET lineups_json = ?, updated_at = ? WHERE match_id = ?",
                (json.dumps({"club": lineups.get("club") or [], "opponent": lineups.get("opponent") or [], "roles": lineups.get("roles") or {}}), now_iso(), match_id),
            )
    # the result is worked out again (team names may have changed)
    scorecard = dict(match.get("scorecard") or {})
    scorecard["result"] = "TBD"
    match["scorecard"] = scorecard
    match["result"] = "TBD"
    sync_fixture_scorecard_from_scorebook(match)
    _settle_scorebook_result(match, lineups)
    _touch_fixture_audit(match, user_row)
    save_store(store)
    _audit_event("scorebook.edit", "fixture", match_id, actor=user_row, club_id=str(match.get("club_id") or ""), club_name=club_name, details={"action": action, "message": message}, source="api")
    return {"ok": True, "message": message}


@app.delete("/api/matches/{match_id}/scorebook/ball")
@_scoring_locked
def delete_scorebook_ball(
    match_id: str,
    edit_mode: bool = False,
    innings_number: int | None = None,
    ball_id: str = "",
    x_auth_token: str | None = Header(default=None),
    x_lite_response: str | None = Header(default=None),
) -> dict[str, Any]:
    user_row, _ = _require_match_score_editor(x_auth_token, match_id)
    store = load_store()
    try:
        match = get_match_or_404(store, match_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    if not _scorebook_is_open(match) and not (edit_mode and (_fixture_is_past(match) or _fixture_is_completed(match))):
        raise HTTPException(status_code=400, detail="Live scoring is locked for this fixture. Use authorized edit mode to correct a past scorebook.")

    scorebook = _match_scorebook(match)
    balls_by_innings: list[tuple[dict[str, Any], dict[str, Any]]] = []
    for innings in scorebook.get("innings", []):
        for ball in innings.get("balls", []):
            balls_by_innings.append((innings, ball))
    if not balls_by_innings:
        raise HTTPException(status_code=400, detail="No scorebook delivery to undo.")

    def _ball_sort_key(item: tuple[dict[str, Any], dict[str, Any]]) -> tuple[int, int, str, str]:
        innings, ball = item
        return (
            int(innings.get("inning_number", 1) or 1),
            int(ball.get("over_number", 1) or 1) * 10 + int(ball.get("ball_number", 1) or 1),
            str(ball.get("created_at") or ""),
            str(ball.get("id") or ""),
        )

    target_innings = None
    target_ball = None
    if edit_mode and ball_id:
        target_innings = next(
            (
                innings
                for innings, ball in balls_by_innings
                if str(ball.get("id") or "") == ball_id
                and (innings_number is None or int(innings.get("inning_number") or 1) == innings_number)
            ),
            None,
        )
        if target_innings:
            target_ball = next(
                ball
                for innings, ball in balls_by_innings
                if innings is target_innings and str(ball.get("id") or "") == ball_id
            )
        else:
            raise HTTPException(status_code=404, detail="That ball isn't in this innings any more. Refresh the page.")
    elif edit_mode and innings_number is not None:
        selected = next(
            (innings for innings in scorebook.get("innings", []) if int(innings.get("inning_number") or 1) == innings_number),
            None,
        )
        if selected and selected.get("balls"):
            target_innings = selected
            target_ball = max(
                selected["balls"],
                key=lambda ball: (
                    int(ball.get("over_number") or 1) * 10 + int(ball.get("ball_number") or 1),
                    str(ball.get("created_at") or ""),
                    str(ball.get("id") or ""),
                ),
            )
        else:
            raise HTTPException(status_code=400, detail="No scorebook delivery to undo in this innings.")
    else:
        target_innings, target_ball = sorted(balls_by_innings, key=_ball_sort_key)[-1]
    previous_status = str(target_innings.get("status") or "")
    target_innings["balls"] = [ball for ball in target_innings.get("balls", []) if ball.get("id") != target_ball.get("id")]
    summary = summarize_innings_scorebook(target_innings)
    if not target_innings["balls"]:
        target_innings["status"] = "Not started"
    elif edit_mode and previous_status.lower() in {"complete", "completed", "finished"}:
        target_innings["status"] = previous_status
    else:
        target_innings["status"] = "Live"
    if edit_mode:
        _reindex_scorebook_innings(target_innings)
    if scorebook_wickets_for_all_out(target_innings) >= _all_out_at(match, target_innings, _match_lineups(match_id)) or summary["legal_balls"] >= int(target_innings.get("overs_limit", 20) or 20) * 6:
        target_innings["status"] = "Completed"
    sync_fixture_scorecard_from_scorebook(match)
    _settle_scorebook_result(match, _match_lineups(match_id))
    _touch_fixture_audit(match, user_row)
    save_store(store)
    return {"ok": True} if x_lite_response else current_dashboard(load_store())


# ---------------------------------------------------------------------------
# AI Assistant, notifications and quick scoring (see README.md -> "AI Assistant and notifications")
# ---------------------------------------------------------------------------
class MuseRequest(BaseModel):
    message: str
    focus_club_id: str | None = None
    history: list[dict[str, Any]] = Field(default_factory=list)
    session_id: str | None = None


class MuseConfirmScoreRequest(BaseModel):
    match_id: str
    draft: dict[str, Any]


class NotificationReadRequest(BaseModel):
    ids: list[str] = Field(default_factory=list)
    all: bool = False


class QuickStartRequest(BaseModel):
    opponent: str
    overs: str = "20"
    venue: str = ""
    match_type: str = "Friendly"


def _user_club_ids(store: dict[str, Any], user_row: sqlite3.Row, current_club_id: str) -> list[str]:
    return [str(club.get("id") or "") for club in _visible_club_choices_for_user(store, user_row, current_club_id) if club.get("id")]


def _club_fixtures(store: dict[str, Any], club_id: str) -> list[dict[str, Any]]:
    return [fixture for fixture in store.get("fixtures", []) or [] if str(fixture.get("club_id") or "") == club_id]


def _club_member_names(store: dict[str, Any], club: dict[str, Any]) -> list[str]:
    club_id = str(club.get("id") or "")
    names = []
    for member in store.get("members", []) or []:
        ids = {str(item.get("club_id") or "") for item in member.get("club_memberships") or [] if isinstance(item, dict)}
        ids.add(str(member.get("primary_club_id") or ""))
        if club_id in ids and member.get("name"):
            names.append(str(member["name"]))
    return sorted(set(names), key=str.lower)


def _notify(club_id: str, kind: str, title: str, body: str = "", link: str = "", match_id: str = "", created_by: str = "") -> None:
    try:
        with _auth_connection() as connection:
            muse.create_notification(connection, club_id=club_id, kind=kind, title=title, body=body, link=link, match_id=match_id, created_by=created_by)
    except Exception:
        logger.exception("Could not save notification kind=%s club=%s", kind, club_id)


# ---------------------------------------------------------------------------
# Availability requests and match reminders (README "Availability requests and match reminders", Oct 29 2026).
# Bell notifications, each sent once per match (table app_fixture_reminders, safe with several workers):
#   ask   - when the match is added (or, for older matches, once it is 7 days away): "Are you available?"
#   nudge - 2 days before: only to players who haven't replied (one notification each)
#   eve   - the day before, from 6 PM: "Tomorrow: vs GT at 10:00 AM" with how many are available
#   day   - match day, from 7 AM: "Match today: vs GT at 10:00 AM"
# A change of date / time / ground tells everyone and asks again. Matches added on the day itself
# ("Start a new match") send none of these.
# ---------------------------------------------------------------------------
_REMINDER_LOCK = threading.Lock()
_REMINDER_LAST_RUN = 0.0
_REMINDER_TABLE = "CREATE TABLE IF NOT EXISTS app_fixture_reminders (fixture_id TEXT NOT NULL, kind TEXT NOT NULL, sent_at TEXT NOT NULL, PRIMARY KEY (fixture_id, kind))"


def _reminder_claim(fixture_id: str, kind: str) -> bool:
    """True the first time (fixture, kind) is claimed, in any worker; False afterwards."""
    try:
        with _auth_connection() as connection:
            connection.execute(_REMINDER_TABLE)
            cursor = connection.execute(
                "INSERT OR IGNORE INTO app_fixture_reminders (fixture_id, kind, sent_at) VALUES (?, ?, ?)", (fixture_id, kind, now_iso())
            )
            return cursor.rowcount == 1
    except Exception:
        logger.exception("Reminder bookkeeping failed for %s/%s", fixture_id, kind)
        return False


def _reminder_unclaim(fixture_id: str, kinds: tuple[str, ...]) -> None:
    try:
        with _auth_connection() as connection:
            connection.execute(_REMINDER_TABLE)
            connection.executemany("DELETE FROM app_fixture_reminders WHERE fixture_id = ? AND kind = ?", [(fixture_id, kind) for kind in kinds])
    except Exception:
        logger.exception("Reminder reset failed for %s", fixture_id)


def _club_gets_availability(club_id: str) -> bool:
    """Availability is a Pro feature; during the launch everyone has Pro."""
    return (not subscriptions.subscriptions_on()) or _club_is_paid(club_id)


def _fixture_day(fixture: dict[str, Any]) -> date | None:
    try:
        return date.fromisoformat(str(fixture.get("date") or "")[:10])
    except ValueError:
        return None


def _fixture_when(fixture: dict[str, Any]) -> str:
    """'vs GT · Sat Nov 7 · 10:00 AM'"""
    day = _fixture_day(fixture)
    details = fixture.get("details") or {}
    parts = [f"vs {fixture.get('opponent') or 'Opponent'}"]
    if day:
        parts.append(f"{day.strftime('%a %b')} {day.day}")
    if str(details.get("scheduled_time") or "").strip():
        parts.append(str(details.get("scheduled_time")).strip())
    return " · ".join(parts)


def _fixture_venue(fixture: dict[str, Any]) -> str:
    venue = str((fixture.get("details") or {}).get("venue") or "").strip()
    return "" if venue.lower() in {"", "venue tbd", "tbd"} else venue


def _fixture_reminders_apply(fixture: dict[str, Any], today: date) -> bool:
    day = _fixture_day(fixture)
    status = str(fixture.get("status") or "").strip().lower()
    if not day or day < today or status in {"completed", "cancelled", "canceled", "abandoned"}:
        return False
    created = str(fixture.get("created_at") or "")[:10]
    if created and day == today and created >= (today - timedelta(days=1)).isoformat():
        return False  # added on (or the day before) the match day, e.g. "Start a new match"
    return True


def _ask_availability(fixture: dict[str, Any], title_prefix: str = "Are you available?", body: str = "") -> None:
    club_id = str(fixture.get("club_id") or "")
    venue = _fixture_venue(fixture)
    _notify(
        club_id,
        "availability",
        f"{title_prefix} {_fixture_when(fixture)}",
        body or f"{'At ' + venue + '. ' if venue else ''}Tap to say Available, Maybe or Not available.",
        f"/player-availability?fixture_id={fixture.get('id')}",
        str(fixture.get("id") or ""),
        "Match reminders",
    )


def _announce_new_fixture(fixture: dict[str, Any]) -> None:
    """A match was added: ask the club's players if they're available (once)."""
    club_id = str(fixture.get("club_id") or "")
    day = _fixture_day(fixture)
    if not club_id or not day or day <= _current_local_date() or not _club_gets_availability(club_id):
        return
    if _reminder_claim(str(fixture.get("id")), "ask"):
        _ask_availability(fixture, "New match · are you available?")


def _announce_fixture_change(fixture: dict[str, Any], what: str) -> None:
    club_id = str(fixture.get("club_id") or "")
    day = _fixture_day(fixture)
    if not club_id or not day or day < _current_local_date() or not _club_gets_availability(club_id):
        return
    _reminder_unclaim(str(fixture.get("id")), ("nudge", "eve", "day"))  # sent again for the new date / time
    _reminder_claim(str(fixture.get("id")), "ask")
    _ask_availability(fixture, "Match changed ·", f"New {what}. Please check you can still make it: tap to update your availability.")


def _player_users_for_club(store: dict[str, Any], club: dict[str, Any]) -> list[tuple[int, str]]:
    """(user id, player name) of signed-up players in this club."""
    roster = set(_club_member_names(store, club))
    found: list[tuple[int, str]] = []
    try:
        with _auth_connection() as connection:
            rows = connection.execute("SELECT * FROM app_users").fetchall()
    except Exception:
        return found
    for row in rows:
        member = _member_for_user(store, row)
        name = str((member or {}).get("name") or "")
        if name and name in roster:
            found.append((int(row["id"]), name))
    return found


def _run_match_reminders(force: bool = False) -> int:
    """Send the reminders that are due. Cheap; runs every few minutes and when people open the bell."""
    global _REMINDER_LAST_RUN
    if not _REMINDER_LOCK.acquire(blocking=False):
        return 0
    try:
        now = time_module.time()
        if not force and now - _REMINDER_LAST_RUN < 240:
            return 0
        _REMINDER_LAST_RUN = now
        store = load_store()
        today = _current_local_date()
        hour = datetime.now().hour
        sent = 0
        for fixture in store.get("fixtures", []) or []:
            if not _fixture_reminders_apply(fixture, today):
                continue
            fixture_id = str(fixture.get("id") or "")
            club_id = str(fixture.get("club_id") or "")
            if not fixture_id or not club_id or not _club_gets_availability(club_id):
                continue
            days = (_fixture_day(fixture) - today).days
            statuses = fixture.get("availability_statuses") or {}
            venue = _fixture_venue(fixture)
            if 1 <= days <= 7 and _reminder_claim(fixture_id, "ask"):
                _ask_availability(fixture)
                sent += 1
            if 1 <= days <= 2 and _reminder_claim(fixture_id, "nudge"):
                club = _selected_club(store, club_id)
                for user_id, name in _player_users_for_club(store, club):
                    if statuses.get(name):
                        continue
                    try:
                        with _auth_connection() as connection:
                            muse.create_notification(
                                connection,
                                club_id=club_id,
                                kind="availability",
                                title=f"Reminder: are you available? {_fixture_when(fixture)}",
                                body="You haven't replied yet. Tap to answer, it only takes a second.",
                                link=f"/player-availability?fixture_id={fixture_id}",
                                match_id=fixture_id,
                                target_user_id=user_id,
                                created_by="Match reminders",
                            )
                        sent += 1
                    except Exception:
                        logger.exception("Availability nudge failed for user %s", user_id)
            if days == 1 and hour >= 18 and _reminder_claim(fixture_id, "eve"):
                yes = sum(1 for value in statuses.values() if str(value).lower() == "available")
                _notify(
                    club_id,
                    "match_reminder",
                    f"Tomorrow: {_fixture_when(fixture)}",
                    f"{'At ' + venue + '. ' if venue else ''}{yes} player{'s' if yes != 1 else ''} available so far. Not replied yet? Tap to answer.",
                    f"/player-availability?fixture_id={fixture_id}",
                    fixture_id,
                    "Match reminders",
                )
                sent += 1
            if days == 0 and hour >= 7 and _reminder_claim(fixture_id, "day"):
                _notify(
                    club_id,
                    "match_reminder",
                    f"Match today: {_fixture_when(fixture)}",
                    f"{'At ' + venue + '. ' if venue else ''}Good luck! 🏏 Follow it live once scoring starts.",
                    f"/live/{fixture_id}",
                    fixture_id,
                    "Match reminders",
                )
                sent += 1
        if sent:
            logger.info("Match reminders sent: %s", sent)
        return sent
    except Exception:
        logger.exception("Match reminders failed")
        return 0
    finally:
        _REMINDER_LOCK.release()


def _reminder_loop() -> None:
    time_module.sleep(20)
    while True:
        _run_match_reminders(force=True)
        time_module.sleep(300)


@app.get("/api/notifications")
def notifications_list(x_auth_token: str | None = Header(default=None)) -> dict[str, Any]:
    user_row, current_club_id = _auth_user_from_token(x_auth_token, touch=False)
    _run_match_reminders()  # also when the bell is opened (the app may have been asleep on Azure)
    store = load_store()
    club_ids = _user_club_ids(store, user_row, current_club_id)
    with _auth_connection() as connection:
        items = muse.list_notifications(connection, int(user_row["id"]), club_ids)
    return {"notifications": items, "unread": sum(1 for item in items if not item["read"]), "generated_at": now_iso()}


@app.post("/api/notifications/read")
def notifications_read(request: NotificationReadRequest, x_auth_token: str | None = Header(default=None)) -> dict[str, Any]:
    user_row, current_club_id = _auth_user_from_token(x_auth_token, touch=False)
    ids = list(request.ids or [])
    if request.all:
        store = load_store()
        with _auth_connection() as connection:
            ids = [item["id"] for item in muse.list_notifications(connection, int(user_row["id"]), _user_club_ids(store, user_row, current_club_id), limit=200)]
    with _auth_connection() as connection:
        marked = muse.mark_notifications_read(connection, int(user_row["id"]), ids)
    return {"marked": marked}


@app.post("/api/muse")
def muse_chat(request: MuseRequest, x_auth_token: str | None = Header(default=None)) -> dict[str, Any]:
    """AI Assistant: carries out commands (with a Confirm step) and answers everything else with the LLM assistant.

    README: MD/README.md -> "AI Assistant and notifications" -> "AI Assistant as an agent".
    """
    user_row, current_club_id = _auth_user_from_token(x_auth_token)
    store = load_store()
    club = _selected_club(store, request.focus_club_id or current_club_id)
    message = " ".join(str(request.message or "").split())[:800]
    ctx = _muse_context(user_row, current_club_id, store, club, x_auth_token)
    if not message:
        return _muse_reply("Tell me what you'd like to do, or ask me anything about your club.")
    # Greetings / thanks / "what can you do" get an instant built-in answer (README "AI Assistant answers (Gemini)").
    basic = ai_chat.basic_reply(message)
    if basic and basic[0] == "chat":
        first = str(user_row["display_name"] or "").split(" ")[0]
        text = basic[1].replace("Hi! 👋", f"Hi {first}! 👋", 1) if first else basic[1]
        return {"reply": text, "intent": "chat", "source_label": "AI Assistant"}

    plan = muse_agent.parse_command(message, _current_local_date(), muse.looks_like_score_message)
    if not plan and muse_agent.looks_like_command(message):
        plan = muse_agent.llm_plan(message, _muse_llm_context(ctx), _muse_llm_call)
    if plan:
        return _muse_prepare(plan, ctx, message)

    intent = muse.detect_intent(message)
    if intent == "upload_help":
        return _muse_reply("Tap the 📎 button below and choose the scorecard photo. I'll upload it to Archives, where it's read and then approved by an admin.", action_hint="open_upload")
    if intent == "scoring_help":
        return _muse_reply(
            "For ball-by-ball scoring open Quick Score: big buttons, voice and automatic strike rotation. You can also tell me the score as it goes, e.g. \"We are 85/3 after 12 overs\".",
            links=[{"label": "Open Quick Score", "href": "/score"}],
        )

    # Everything else: the built-in data assistant looks up the club's data, then (README "AI Assistant
    # answers (Gemini)") the free Gemini model turns it into a proper answer - and also handles greetings,
    # cricket questions and "how do I..." about the app. Ollama answers stay as they are.
    chat_store = _chat_store_for(store, str(club.get("id") or ""))
    answer = answer_question(message, chat_store, history=request.history, session_id=request.session_id)
    data_answer = str(answer.get("answer") or "")
    if str(answer.get("source_provider") or "") != "ollama" and ai_chat.enabled():
        snapshot = _assistant_club_snapshot(store, club, user_row)
        smart = ai_chat.answer(message, data_notes=data_answer, context=_muse_llm_context(ctx) + ("\n" + snapshot if snapshot else ""), history=request.history)
        if smart:
            return {"reply": smart, "intent": "chat", "source_label": "AI Assistant", "llm": ai_chat.provider()}
    # No AI answer (busy / not set up): app how-tos and cricket terms still get a proper built-in answer.
    if basic:
        return {"reply": basic[1], "intent": "chat", "source_label": "AI Assistant"}
    return {
        "reply": data_answer or "I couldn't find an answer to that.",
        "intent": "chat",
        "source_label": "AI Assistant",
        "llm": (answer.get("llm") or {}).get("model") or "",
    }


class MuseExecuteRequest(BaseModel):
    tool: str
    args: dict[str, Any] = Field(default_factory=dict)
    focus_club_id: str | None = None


@app.post("/api/muse/execute")
def muse_execute(request: MuseExecuteRequest, x_auth_token: str | None = Header(default=None)) -> dict[str, Any]:
    """Carry out a task the AI Assistant planned, after the person tapped Confirm. Everything is checked again here."""
    user_row, current_club_id = _auth_user_from_token(x_auth_token)
    store = load_store()
    club = _selected_club(store, request.focus_club_id or current_club_id)
    ctx = _muse_context(user_row, current_club_id, store, club, x_auth_token)
    tool = str(request.tool or "")
    if tool not in muse_agent.TOOLS or tool in {"chat", "availability_summary"}:
        raise HTTPException(status_code=400, detail="Unknown task.")
    _muse_require_plan(ctx, tool, str((request.args or {}).get("match_id") or ""), claim=True)
    result = _muse_run(tool, dict(request.args or {}), ctx)
    _audit_event("muse.execute", "muse", tool, actor=user_row, club_id=str(club.get("id") or ""), club_name=str(club.get("name") or ""), details={"tool": tool}, source="api")
    return result


# ---------------------------------------------------------------------------
# AI Assistant agent helpers
# ---------------------------------------------------------------------------
def _muse_reply(text: str, **extra: Any) -> dict[str, Any]:
    return {"reply": text, "intent": extra.pop("intent", "agent"), "source_label": extra.pop("source_label", "AI Assistant"), **extra}


def _muse_context(user_row: sqlite3.Row, current_club_id: str, store: dict[str, Any], club: dict[str, Any], token: str | None) -> dict[str, Any]:
    club_id = str(club.get("id") or "")
    return {
        "user": user_row,
        "current_club_id": current_club_id,
        "permissions": _user_permissions(user_row, current_club_id),
        "role": _effective_role_name(user_row, current_club_id),
        "store": store,
        "club": club,
        "club_id": club_id,
        "club_name": str(club.get("name") or "your club"),
        "fixtures": _club_fixtures(store, club_id),
        "token": token,
        "actor": str(user_row["display_name"] or user_row["mobile"] or "AI Assistant"),
    }


def _muse_llm_context(ctx: dict[str, Any]) -> str:
    upcoming = [f for f in ctx["fixtures"] if not _fixture_is_past(f) and str(f.get("status") or "").lower() != "completed"]
    upcoming.sort(key=lambda f: str(f.get("date") or ""))
    nxt = ", ".join(muse.fixture_label(f) for f in upcoming[:3]) or "none"
    return f"Today is {_current_local_date().isoformat()}. Club: {ctx['club_name']}. Speaker: {ctx['actor']} ({ctx['role']}). Next fixtures: {nxt}."


def _assistant_club_snapshot(store: dict[str, Any], club: dict[str, Any], user_row: Any) -> str:
    """Short summary of the club's real data for the AI Assistant (README "AI Assistant knows your club").
    Names and cricket numbers only - never phone numbers, emails or ages."""
    club_id = str((club or {}).get("id") or "")
    if not club_id:
        return ""
    lines: list[str] = []
    try:
        today = _current_local_date().isoformat()
        speaker = str(user_row["display_name"] or "") if user_row else ""
        member_ids: set[str] = set()
        roster: list[str] = []
        my_member_id = str(user_row["member_id"] or "") if user_row else ""
        for member in store.get("members", []) or []:
            ids = {str(item.get("club_id") or "") for item in member.get("club_memberships") or [] if isinstance(item, dict)}
            ids.add(str(member.get("primary_club_id") or ""))
            if club_id in ids:
                member_ids.add(str(member.get("id") or ""))
                if member.get("name"):
                    roster.append(str(member["name"]))
        lines.append(f"Club: {club.get('name')}. Season: {club.get('season') or ''}. Today: {today}.")
        if speaker:
            lines.append(f"The person asking is {speaker} (\"me\", \"my\", \"I\" mean this person).")
        if roster:
            lines.append(f"Players ({len(roster)}): " + ", ".join(sorted(roster, key=str.lower)[:70]))
        fixtures = [f for f in store.get("fixtures", []) or [] if str(f.get("club_id") or "") == club_id]
        upcoming = sorted((f for f in fixtures if str(f.get("date") or "") >= today and str(f.get("status") or "").lower() != "completed"), key=lambda f: str(f.get("date") or ""))
        if upcoming:
            lines.append("Upcoming matches: " + "; ".join(f"{f.get('date')} vs {f.get('opponent') or f.get('visiting_team')}" for f in upcoming[:5]))
        else:
            lines.append("Upcoming matches: none scheduled.")
        played = sorted((f for f in fixtures if str(f.get("status") or "").lower() == "completed" or str(f.get("result") or "").upper() not in {"", "TBD"}), key=lambda f: str(f.get("date") or ""), reverse=True)
        if played:
            lines.append("Recent results: " + "; ".join(
                f"{f.get('date')} vs {f.get('opponent')}: {f.get('heartlake_score') or '?'} v {f.get('opponent_score') or '?'}, {f.get('result') or ''}" for f in played[:5]))
        cards = [card for card in _public_scorecards(store) if str(card.get("club_id") or "") == club_id]
        cards.sort(key=lambda card: str(card.get("date") or ""), reverse=True)
        if cards:
            lines.append(f"Published scorecards: {len(cards)}. Latest:")
            for card in cards[:6]:
                innings = card.get("innings") or []
                scores = ", ".join(f"{item.get('team')} {item.get('score')}" for item in innings)
                bats = [row for item in innings for row in item.get("batting") or [] if isinstance(row.get("runs"), int)]
                bowls = [row for item in innings for row in item.get("bowling") or [] if isinstance(row.get("wickets"), int)]
                top_bat = max(bats, key=lambda row: row["runs"], default=None)
                top_bowl = max(bowls, key=lambda row: row["wickets"], default=None)
                extra = []
                if top_bat:
                    extra.append(f"top score {top_bat['name']} {top_bat['runs']}")
                if top_bowl and top_bowl["wickets"]:
                    extra.append(f"best bowling {top_bowl['name']} {top_bowl['wickets']} wkts")
                lines.append(f"- {card.get('date')} {card.get('title')}: {scores}. {card.get('result') or ''} {('(' + '; '.join(extra) + ')') if extra else ''}".strip())
        else:
            lines.append("Published scorecards: none yet.")
        # Season numbers per player (member_year_stats), latest seasons with data first.
        by_year: dict[str, list[dict[str, Any]]] = {}
        for stat in store.get("member_year_stats", []) or []:
            if str(stat.get("member_id") or "") in member_ids and (stat.get("runs") or stat.get("wickets")):
                by_year.setdefault(str(stat.get("season_year") or ""), []).append(stat)
        for year in sorted(by_year, reverse=True)[:2]:
            rows = by_year[year]
            top_runs = sorted(rows, key=lambda r: int(r.get("runs") or 0), reverse=True)[:5]
            top_wkts = sorted(rows, key=lambda r: int(r.get("wickets") or 0), reverse=True)[:5]
            lines.append(f"{year} most runs: " + ", ".join(f"{r.get('player_name')} {int(r.get('runs') or 0)}" + (f" ({int(r.get('matches') or 0)} matches, HS {int(r.get('highest_score') or 0)})" if r.get("matches") else "") for r in top_runs))
            lines.append(f"{year} most wickets: " + ", ".join(f"{r.get('player_name')} {int(r.get('wickets') or 0)}" for r in top_wkts if int(r.get("wickets") or 0)))
            mine = next((r for r in rows if str(r.get("member_id") or "") == my_member_id), None)
            if mine:
                lines.append(f"{year} the asker's own stats: {int(mine.get('runs') or 0)} runs in {int(mine.get('matches') or 0)} matches, "
                             f"HS {int(mine.get('highest_score') or 0)}, average {mine.get('batting_average') or 0}, {int(mine.get('wickets') or 0)} wickets, {int(mine.get('catches') or 0)} catches.")
        if not by_year:
            lines.append("Season stats: no runs or wickets recorded yet (they appear once scorecards are published or matches are scored).")
    except Exception:
        logger.exception("Assistant snapshot failed")
    return "\n".join(lines)[:6000]


def _muse_llm_call(system_prompt: str, user_prompt: str) -> str:
    """Ask the local Ollama model for a JSON tool choice; without Ollama, the free Gemini model (ai_chat).
    Raises if neither is available."""
    status = get_llm_status()
    if status.get("provider") != "ollama" or not status.get("model"):
        if ai_chat.enabled():
            return ai_chat.complete(system_prompt, user_prompt, json_mode=True, timeout=20.0)
        raise RuntimeError("LLM offline")
    response = httpx.post(
        f"{str(status.get('base_url') or '').rstrip('/')}/api/chat",
        json={
            "model": status["model"],
            "stream": False,
            "format": "json",
            "options": {"temperature": 0, "num_predict": 200},
            "messages": [{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}],
        },
        timeout=45.0,
    )
    response.raise_for_status()
    return str(response.json().get("message", {}).get("content", "") or "")


_MUSE_TOOL_LABELS = {
    "mark_availability": "Updating availability",
    "request_availability": "Sending availability requests",
    "remind_pending": "Sending availability reminders",
    "pick_xi": "Picking the playing XI",
    "create_fixture": "Adding fixtures",
    "live_update": "Updating the live score",
    "record_result": "Saving match scores",
}


def _muse_require_plan(ctx: dict[str, Any], tool: str, match_id: str = "", *, claim: bool = False) -> None:
    """AI Assistant tasks are part of Pro. Free users get one free AI match. Reading availability stays free."""
    if tool == "availability_summary":
        return
    if not match_id and not claim and not _has_feature(ctx["user"], ctx["current_club_id"], "ai_assistant"):
        # Planning a task before the match is known: allow it while the free AI match is still to come.
        try:
            load_store()
            with _auth_connection() as connection:
                trial_match = subscriptions.ai_trial_match(connection, int(ctx["user"]["id"]))
        except Exception:
            trial_match = ""
        if trial_match:
            try:
                if not _fixture_is_past(get_match_or_404(ctx["store"], trial_match)):
                    match_id = trial_match
            except ValueError:
                pass
    if not _ai_allowed(ctx["user"], ctx["current_club_id"], "ai_assistant", match_id, claim=claim):
        raise HTTPException(
            status_code=402,
            detail=f"{_MUSE_TOOL_LABELS.get(tool, 'This task')} through the AI Assistant is part of Pro ($9 a month or $90 a year). Your one free AI match has been used. See /pricing to upgrade.",
        )


def _muse_find_fixture(ctx: dict[str, Any], when_text: str, *, today_only: bool = False) -> dict[str, Any] | None:
    """The fixture a command is about: a date ('Saturday', 'Oct 12'), an opponent, else the next upcoming one."""
    today = _current_local_date()
    fixtures = [f for f in ctx["fixtures"] if not _fixture_is_past(f) and str(f.get("status") or "").lower() != "completed"]
    if today_only:
        fixtures = [f for f in ctx["fixtures"] if str(f.get("date") or "")[:10] == today.isoformat()]
    fixtures.sort(key=lambda f: (str(f.get("date") or ""), str((f.get("details") or {}).get("scheduled_time") or "")))
    when = muse_agent.parse_when(when_text, today)
    if when:
        on_day = [f for f in fixtures if str(f.get("date") or "")[:10] == when.isoformat()]
        return on_day[0] if on_day else None
    lowered = str(when_text or "").lower()
    by_opponent = [
        f for f in fixtures
        if str(f.get("opponent") or "").strip() and len(str(f.get("opponent")).split()[0]) >= 3 and str(f.get("opponent")).lower().split()[0] in lowered
    ]
    pool = by_opponent or fixtures
    return pool[0] if pool else None


def _muse_no_fixture(ctx: dict[str, Any], when_text: str) -> dict[str, Any]:
    when = muse_agent.parse_when(when_text, _current_local_date())
    day = f" on {when.strftime('%a %d %b')}" if when else ""
    return _muse_reply(
        f"I can't find an upcoming fixture for {ctx['club_name']}{day}. Past matches are locked, so I can only work with today's or future games. You can ask me to add one, e.g. \"Add a match vs Imran XI on Saturday at 10am\".",
        links=[{"label": "Fixtures", "href": "/dashboard/widgets/schedule"}],
    )


def _muse_can_manage(ctx: dict[str, Any]) -> bool:
    return ctx["role"] in {"captain", "club_admin", "superadmin"} or bool({"manage_fixtures", "manage_players"} & ctx["permissions"])


def _muse_action(text: str, tool: str, args: dict[str, Any], confirm_label: str, **extra: Any) -> dict[str, Any]:
    return _muse_reply(text, action={"tool": tool, "args": args, "confirm_label": confirm_label}, **extra)


def _muse_resolve_players(ctx: dict[str, Any], names: list[str]) -> tuple[list[str], list[str]]:
    club_names = {normalize_name(n): n for n in _club_member_names(ctx["store"], ctx["club"])}
    found: list[str] = []
    missing: list[str] = []
    for raw in names:
        member = cricket_insights.find_member(ctx["store"], raw)
        name = str(member.get("name")) if member else resolve_member_name(ctx["store"], raw)
        if name and normalize_name(name) in club_names:
            if club_names[normalize_name(name)] not in found:
                found.append(club_names[normalize_name(name)])
        else:
            missing.append(raw)
    return found, missing


_STATUS_LABEL = {"available": "Available", "maybe": "Maybe", "unavailable": "Not available"}


def _muse_prepare(plan: dict[str, Any], ctx: dict[str, Any], message: str) -> dict[str, Any]:
    tool = plan["tool"]
    args = dict(plan.get("args") or {})
    try:
        _muse_require_plan(ctx, tool)
    except HTTPException as exc:
        return _muse_reply(str(exc.detail).replace(" See /pricing to upgrade.", ""), links=[{"label": "See plans", "href": "/pricing"}], upgrade=True)

    if tool == "availability_summary":
        fixture = _muse_find_fixture(ctx, args.get("when", ""))
        if not fixture:
            return _muse_no_fixture(ctx, args.get("when", ""))
        groups = muse.availability_summary(fixture, _club_member_names(ctx["store"], ctx["club"]))
        lines = [f"Availability for {muse.fixture_label(fixture)}:"]
        for key, label in (("available", "Available"), ("maybe", "Maybe"), ("unavailable", "Not available"), ("no response", "No reply yet")):
            names = groups[key]
            lines.append(f"• {label} ({len(names)}): {', '.join(names[:14]) + (' …' if len(names) > 14 else '') if names else '–'}")
        if groups["no response"] and _muse_can_manage(ctx):
            lines.append("Say \"remind the players who haven't replied\" and I'll nudge them.")
        return _muse_reply("\n".join(lines))

    if tool == "mark_availability":
        fixture = _muse_find_fixture(ctx, args.get("when", ""))
        if not fixture:
            return _muse_no_fixture(ctx, args.get("when", ""))
        status = str(args.get("status") or "")
        if status not in _STATUS_LABEL:
            return _muse_reply("Should I mark Available, Maybe or Not available?")
        players = [str(p) for p in args.get("players") or ["me"]]
        if players == ["me"]:
            member = _member_for_user(ctx["store"], ctx["user"])
            if not member:
                return _muse_reply("Your account isn't linked to a player profile yet, so I can't mark your availability. Ask your club admin to link it.")
            return _muse_action(
                f"Mark you ({member.get('name')}) as {_STATUS_LABEL[status]} for {muse.fixture_label(fixture)}?",
                tool,
                {"players": ["me"], "status": status, "match_id": fixture.get("id")},
                f"Yes, mark {_STATUS_LABEL[status]}",
            )
        if not _muse_can_manage(ctx):
            return _muse_reply("Only captains and club admins can change other players' availability. You can say \"mark me available\" for yourself.")
        found, missing = _muse_resolve_players(ctx, players)
        if not found:
            return _muse_reply(f"I couldn't find {', '.join(missing)} in {ctx['club_name']}. Check the spelling or use the name on their profile.")
        note = f"\n(I couldn't find: {', '.join(missing)}.)" if missing else ""
        return _muse_action(
            f"Mark {', '.join(found)} as {_STATUS_LABEL[status]} for {muse.fixture_label(fixture)}?{note}",
            tool,
            {"players": found, "status": status, "match_id": fixture.get("id")},
            f"Yes, update {len(found)} player{'s' if len(found) != 1 else ''}",
        )

    if tool in {"request_availability", "remind_pending"}:
        if not _muse_can_manage(ctx):
            return _muse_reply("Only captains and club admins can send availability requests. You can update your own: say \"mark me available for the next match\".")
        fixture = _muse_find_fixture(ctx, args.get("when", ""))
        if not fixture:
            return _muse_no_fixture(ctx, args.get("when", ""))
        groups = muse.availability_summary(fixture, _club_member_names(ctx["store"], ctx["club"]))
        if tool == "remind_pending":
            pending = groups["no response"]
            if not pending:
                return _muse_reply(f"Everyone has replied for {muse.fixture_label(fixture)} ✓")
            return _muse_action(
                f"Send a reminder for {muse.fixture_label(fixture)}? {len(pending)} player{'s have' if len(pending) != 1 else ' has'} not replied: {', '.join(pending[:10])}{' …' if len(pending) > 10 else ''}.",
                tool,
                {"match_id": fixture.get("id")},
                "Send reminder",
            )
        count = len(_club_member_names(ctx["store"], ctx["club"]))
        return _muse_action(
            f"Send an availability request for {muse.fixture_label(fixture)} to all {count} players of {ctx['club_name']}?",
            tool,
            {"match_id": fixture.get("id")},
            "Send request",
        )

    if tool == "pick_xi":
        if not ({"manage_fixtures"} & ctx["permissions"]) or not _has_feature(ctx["user"], ctx["current_club_id"], "playing_xi"):
            return _muse_reply("Only captains and club admins on a paid plan can pick the playing XI.")
        fixture = _muse_find_fixture(ctx, args.get("when", ""))
        if not fixture:
            return _muse_no_fixture(ctx, args.get("when", ""))
        best = cricket_insights.best_xi(ctx["store"], ctx["club"])
        statuses = {normalize_name(k): str(v or "").lower() for k, v in (fixture.get("availability_statuses") or {}).items()}
        xi = [str(p.get("name") or "") for p in best.get("xi") or [] if p.get("name")]
        eligible = [name for name in xi if statuses.get(normalize_name(name), "") in {"available", "maybe"}]
        lines = [f"Suggested XI for {muse.fixture_label(fixture)}:"]
        for index, player in enumerate(best.get("xi") or [], start=1):
            mark = "" if normalize_name(str(player.get("name") or "")) in {normalize_name(n) for n in eligible} else " (hasn't said available)"
            lines.append(f"{index}. {player.get('name')} – {player.get('reason') or ''}{mark}")
        if not eligible:
            lines.append("Nobody in this XI has said they're available yet, so I can't save it. Ask everyone for availability first.")
            return _muse_reply("\n".join(lines))
        if len(eligible) < len(xi):
            lines.append(f"I'll save the {len(eligible)} player{'s' if len(eligible) != 1 else ''} who said Available or Maybe; the others can be added once they reply.")
        return _muse_action("\n".join(lines), tool, {"match_id": fixture.get("id"), "players": eligible}, f"Save this XI ({len(eligible)})")

    if tool == "create_fixture":
        if "manage_fixtures" not in ctx["permissions"]:
            return _muse_reply("Only captains and club admins can add fixtures.")
        opponent = str(args.get("opponent") or "").strip()
        when_raw = str(args.get("date") or "")
        when = muse_agent.parse_when(when_raw, _current_local_date()) if when_raw else None
        if not opponent or not when:
            return _muse_reply("Tell me the opponent and the date, e.g. \"Add a match vs Imran XI on Saturday at 10am, 20 overs\".")
        if when < _current_local_date():
            return _muse_reply("That date has already passed. Past matches are locked, so I can only add today's or future fixtures.")
        time_text = str(args.get("time") or "")
        overs = str(args.get("overs") or "20")
        venue = str(args.get("venue") or "")
        return _muse_action(
            f"Add {ctx['club_name']} vs {opponent} on {when.strftime('%a %d %b %Y')}{' at ' + time_text if time_text else ''} ({overs} overs{', ' + venue if venue else ''})?",
            tool,
            {"opponent": opponent, "date": when.isoformat(), "time": time_text, "overs": overs, "venue": venue},
            "Add fixture",
        )

    if tool == "live_update":
        if "score_matches" not in ctx["permissions"]:
            return _muse_reply("Only scorers and club admins can update the live score.")
        fixture = _muse_find_fixture(ctx, "", today_only=True)
        if not fixture:
            return _muse_reply("There's no match for your club today. Start one in Quick Score, then tell me the score as it goes.", links=[{"label": "Quick Score", "href": "/score"}])
        team = ctx["club_name"] if args.get("team") != "them" else str(fixture.get("opponent") or "Opponent")
        overs = str(args.get("overs") or "")
        return _muse_action(
            f"Update the live score for {muse.fixture_label(fixture)}: {team} {args.get('runs')}/{args.get('wickets')}{f' after {overs} overs' if overs else ''}? Followers get a live alert.",
            tool,
            {"match_id": fixture.get("id"), "runs": str(args.get("runs") or ""), "wickets": str(args.get("wickets") or ""), "overs": overs, "team": "them" if args.get("team") == "them" else "us"},
            "Update live score",
        )

    if tool == "record_result":
        if "score_matches" not in ctx["permissions"]:
            return _muse_reply("Only scorers and club admins can save scores. Send the score to your captain, or upload a photo of the scorecard for review.")
        store, club = ctx["store"], ctx["club"]

        def resolve_player(name: str) -> str | None:
            found = cricket_insights.find_member(store, name)
            return str(found.get("name")) if found else None

        parsed = muse.parse_score_message(args.get("text") or message, [ctx["club_name"], str(club.get("short_name") or "")], resolve_player)
        if not parsed["club_side"]:
            return _muse_reply("I couldn't find a team score in that. Try: \"Heartlake 145/6 in 20 overs, Imran XI 120/9. Heartlake won by 25 runs. Amit S 45 off 30, Nick 3 wickets\".")
        opponent_name = (parsed["opponent_side"] or {}).get("name", "")
        fixture = muse.pick_fixture(ctx["fixtures"], f"{message} {opponent_name}", prefer="past")
        if fixture and _fixture_is_past(fixture):
            return _muse_reply(
                f"That looks like {muse.fixture_label(fixture)}, which has already passed. Past matches are locked, so I can't change its score. To add an old score, upload the scorecard photo (📎) for admin review.",
                action_hint="open_upload",
            )
        if not fixture or str(fixture.get("date") or "")[:10] != _current_local_date().isoformat():
            return _muse_reply(f"I can only save the final score for today's match. I couldn't find a {ctx['club_name']} match today; start one in Quick Score first.", links=[{"label": "Quick Score", "href": "/score"}])
        ours, theirs = parsed["club_side"], parsed["opponent_side"] or {}
        draft = {
            "scorecard": {
                "heartlake_runs": ours.get("runs", ""),
                "heartlake_wickets": ours.get("wickets", ""),
                "heartlake_overs": ours.get("overs", ""),
                "opponent_runs": theirs.get("runs", ""),
                "opponent_wickets": theirs.get("wickets", ""),
                "opponent_overs": theirs.get("overs", ""),
                "result": parsed["result"] or "TBD",
            },
            "performances": parsed["performances"],
        }
        lines = [
            f"Here's what I understood for {muse.fixture_label(fixture)}:",
            f"• {ctx['club_name']}: {ours.get('runs')}/{ours.get('wickets')}" + (f" ({ours.get('overs')} ov)" if ours.get("overs") else ""),
            f"• {fixture.get('opponent') or opponent_name or 'Opponent'}: " + (f"{theirs.get('runs')}/{theirs.get('wickets')}" + (f" ({theirs.get('overs')} ov)" if theirs.get("overs") else "") if theirs else "not given"),
            f"• Result: {parsed['result'] or 'not given'}",
        ]
        if parsed["performances"]:
            lines.append("• Players: " + ", ".join(
                f"{p['player_name']} " + " ".join(part for part in [
                    f"{p['runs']}{'*' if p.get('not_out') else ''}" + (f" ({p['balls']})" if p.get("balls") else "") if p.get("runs") else "",
                    f"{p['wickets']} wkts" if p.get("wickets") else "",
                    f"{p['catches']} ct" if p.get("catches") else "",
                ] if part)
                for p in parsed["performances"]
            ))
        return _muse_action("\n".join(lines), tool, {"match_id": fixture.get("id"), "draft": draft}, "Save score")

    return _muse_reply("I'm not sure how to do that yet. Try \"mark me available for Saturday\", \"who is available?\", \"pick the best XI\" or ask me a question.")


def _muse_run(tool: str, args: dict[str, Any], ctx: dict[str, Any]) -> dict[str, Any]:
    store = ctx["store"]
    token = ctx["token"]
    match: dict[str, Any] | None = None
    if args.get("match_id"):
        try:
            match = get_match_or_404(store, str(args["match_id"]))
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc))
        if str(match.get("club_id") or "") and str(match.get("club_id")) != ctx["club_id"]:
            raise HTTPException(status_code=403, detail="That match belongs to another club.")
        _require_not_past(match, "it")

    if tool == "mark_availability":
        status = str(args.get("status") or "")
        if status not in _STATUS_LABEL or match is None:
            raise HTTPException(status_code=400, detail="Missing availability details.")
        players = [str(p) for p in args.get("players") or []]
        if players == ["me"]:
            member = _member_for_user(store, ctx["user"])
            if not member:
                raise HTTPException(status_code=400, detail="Your account isn't linked to a player profile.")
            names = [str(member.get("name") or "")]
        else:
            if not _muse_can_manage(ctx):
                raise HTTPException(status_code=403, detail="Only captains and club admins can change other players' availability.")
            names, _ = _muse_resolve_players(ctx, players)
        for name in names:
            match.setdefault("availability_statuses", {})[name] = status
        _touch_fixture_audit(match, ctx["user"])
        save_store(store)
        return _muse_reply(
            f"Done ✓ {', '.join(names)} {'is' if len(names) == 1 else 'are'} marked {_STATUS_LABEL[status]} for {muse.fixture_label(match)}.",
            links=[{"label": "Open availability", "href": f"/player-availability?fixture_id={match.get('id')}"}],
        )

    if tool in {"request_availability", "remind_pending"}:
        if not _muse_can_manage(ctx) or match is None:
            raise HTTPException(status_code=403, detail="Only captains and club admins can send availability requests.")
        label = muse.fixture_label(match)
        if tool == "remind_pending":
            pending = muse.availability_summary(match, _club_member_names(store, ctx["club"]))["no response"]
            _notify(ctx["club_id"], "availability", f"Reminder: are you available? {label}", f"{len(pending)} players haven't replied yet. Tap to mark Available, Maybe or Not available.", f"/player-availability?fixture_id={match.get('id')}", str(match.get("id") or ""), ctx["actor"])
            return _muse_reply(f"Done ✓ Reminder sent for {label}. {len(pending)} player{'s' if len(pending) != 1 else ''} still need{'' if len(pending) != 1 else 's'} to reply; they'll see it under the 🔔 bell.")
        _notify(ctx["club_id"], "availability", f"Are you available? {label}", f"{ctx['actor']} is picking the team for {label}. Tap to mark Available, Maybe or Not available.", f"/player-availability?fixture_id={match.get('id')}", str(match.get("id") or ""), ctx["actor"])
        return _muse_reply(f"Done ✓ Availability request sent for {label}. Ask me \"who is available?\" later to see the replies.")

    if tool == "pick_xi":
        if match is None:
            raise HTTPException(status_code=400, detail="Missing fixture.")
        update_playing_xi(str(match.get("id")), PlayingXiUpdateRequest(player_names=[str(p) for p in args.get("players") or []], club_id=ctx["club_id"]), token)
        return _muse_reply(
            f"Done ✓ Playing XI saved for {muse.fixture_label(match)} ({len(args.get('players') or [])} player{'s' if len(args.get('players') or []) != 1 else ''}).",
            links=[{"label": "Open fixture", "href": f"/dashboard/widgets/schedule?match_id={match.get('id')}#selectedPlayingXiTitle"}],
        )

    if tool == "create_fixture":
        when = muse_agent.parse_when(str(args.get("date") or ""), _current_local_date())
        opponent = str(args.get("opponent") or "").strip()
        if not when or not opponent:
            raise HTTPException(status_code=400, detail="Missing opponent or date.")
        if when < _current_local_date():
            raise HTTPException(status_code=400, detail="That date has already passed.")
        create_season_fixture(
            SeasonFixtureRequest(
                club_id=ctx["club_id"],
                season_year=when.year,
                date=when.isoformat(),
                date_label=f"{when.strftime('%B')} {when.day}",
                opponent=opponent,
                venue=str(args.get("venue") or ""),
                match_type="Friendly",
                scheduled_time=str(args.get("time") or ""),
                overs=str(args.get("overs") or "20"),
            ),
            token,
        )
        return _muse_reply(
            f"Done ✓ {ctx['club_name']} vs {opponent} is added for {when.strftime('%a %d %b %Y')}. Want me to ask everyone for availability?",
            links=[{"label": "Fixtures", "href": "/dashboard/widgets/schedule"}],
        )

    if tool == "live_update":
        if match is None or str(match.get("date") or "")[:10] != _current_local_date().isoformat():
            raise HTTPException(status_code=400, detail="Live updates are only for today's match.")
        runs, wickets, overs = str(args.get("runs") or ""), str(args.get("wickets") or ""), str(args.get("overs") or "")
        ours = args.get("team") != "them"
        team = ctx["club_name"] if ours else str(match.get("opponent") or "Opponent")
        summary = f"{team} {runs}/{wickets}" + (f" after {overs} overs" if overs else "")
        update = ScorecardUpdateRequest(
            **({"heartlake_runs": runs, "heartlake_wickets": wickets, "heartlake_overs": overs or None} if ours else {"opponent_runs": runs, "opponent_wickets": wickets, "opponent_overs": overs or None}),
            live_summary=summary,
            status="Live" if str(match.get("status") or "").lower() != "completed" else None,
        )
        update_scorecard(str(match.get("id")), update, token)
        _notify(ctx["club_id"], "live_score", f"Live: {summary}", f"{ctx['club_name']} vs {match.get('opponent') or 'Opponent'}", f"/live/{match.get('id')}", str(match.get("id") or ""), ctx["actor"])
        return _muse_reply(f"Done ✓ Live score updated: {summary}. Followers got a live alert.", links=[{"label": "Open live scorecard", "href": f"/live/{match.get('id')}"}])

    if tool == "record_result":
        if match is None:
            raise HTTPException(status_code=400, detail="Missing match.")
        result = muse_confirm_score(MuseConfirmScoreRequest(match_id=str(match.get("id")), draft=dict(args.get("draft") or {})), token)
        return _muse_reply("Done ✓ " + str(result.get("reply") or "Saved."), links=[{"label": "Open scorecard", "href": f"/live/{match.get('id')}"}])

    raise HTTPException(status_code=400, detail="Unknown task.")


@app.post("/api/muse/confirm-score")
def muse_confirm_score(request: MuseConfirmScoreRequest, x_auth_token: str | None = Header(default=None)) -> dict[str, Any]:
    muse_user_row, muse_club_id = _auth_user_from_token(x_auth_token, touch=False)
    if not _ai_allowed(muse_user_row, muse_club_id, "ai_assistant", request.match_id):
        raise _upgrade_error("ai_assistant")
    user_row, _ = _require_match_scorer(x_auth_token, request.match_id)
    store = load_store()
    try:
        match = get_match_or_404(store, request.match_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    _require_not_past(match, "scores")
    card = dict(request.draft.get("scorecard") or {})
    for key in ("heartlake_runs", "heartlake_wickets", "heartlake_overs", "opponent_runs", "opponent_wickets", "opponent_overs", "result"):
        if key in card and str(card[key] or "").strip():
            match.setdefault("scorecard", {})[key] = str(card[key]).strip()
    match["heartlake_score"] = str(card.get("heartlake_runs") or match.get("heartlake_score") or "")
    match["opponent_score"] = str(card.get("opponent_runs") or match.get("opponent_score") or "")
    if str(card.get("result") or "").strip() and str(card.get("result")).strip().upper() != "TBD":
        match["result"] = str(card["result"]).strip()
        match["status"] = "Completed"
    added = 0
    for perf in request.draft.get("performances") or []:
        name = resolve_member_name(store, str(perf.get("player_name") or ""))
        if not name:
            continue
        match.setdefault("performances", []).append(
            {
                "id": str(uuid.uuid4())[:8],
                "player_name": name,
                "runs": int(perf.get("runs") or 0),
                "balls": int(perf.get("balls") or 0),
                "wickets": int(perf.get("wickets") or 0),
                "catches": int(perf.get("catches") or 0),
                "fours": 0,
                "sixes": 0,
                "notes": "not out" if perf.get("not_out") else "",
                "source": "ai-muse",
                "archive_upload_id": "",
            }
        )
        added += 1
    _touch_fixture_audit(match, user_row)
    save_store(store)
    result_text = str(match.get("result") or card.get("result") or "").strip()
    _notify(
        str(match.get("club_id") or ""),
        "result",
        f"Result: {match.get('club_name') or 'Club'} vs {match.get('opponent') or 'Opponent'}",
        result_text if result_text and result_text.upper() != "TBD" else "Score updated.",
        f"/live/{match.get('id')}",
        str(match.get("id") or ""),
        str(user_row["display_name"] or ""),
    )
    return {"reply": f"Saved. The score for {match.get('date_label') or match.get('date')} vs {match.get('opponent')} is updated" + (f" with {added} player performances." if added else ".") + " Everyone in the club got a result alert.", "match_id": match.get("id")}


def _chat_store_for(store: dict[str, Any], focus_club_id: str) -> dict[str, Any]:
    focus_club = next((club for club in store.get("clubs", []) if club.get("id") == focus_club_id), store.get("club", {}))
    chat_store = dict(scoped_store_for_club(store, focus_club) if focus_club_id else dict(store))
    chat_store["focus_club_id"] = str(focus_club_id or "").strip()
    chat_store["focus_club"] = dict(focus_club or {})
    for key, source in (
        ("all_clubs", "clubs"), ("all_members", "members"), ("all_fixtures", "fixtures"), ("all_archive_uploads", "archive_uploads"),
        ("all_teams", "teams"), ("all_member_summary_stats", "member_summary_stats"), ("all_member_year_stats", "member_year_stats"),
        ("all_member_club_stats", "member_club_stats"), ("all_club_summary_stats", "club_summary_stats"), ("all_club_year_stats", "club_year_stats"),
    ):
        chat_store[key] = list(store.get(source, []) or [])
    return chat_store


@app.get("/api/quick-score/fixtures")
def quick_score_fixtures(x_auth_token: str | None = Header(default=None)) -> dict[str, Any]:
    user_row, current_club_id = _auth_user_from_token(x_auth_token)
    permissions = _user_permissions(user_row, current_club_id)
    store = load_store()
    club = _selected_club(store, current_club_id)
    today = _current_local_date().isoformat()
    items = []
    club_fixture_ids = {str(fixture.get("id") or "") for fixture in _club_stat_fixtures(store, club)}
    club_id = str(club.get("id") or "")
    club_fixture_ids.update(
        str(fixture.get("id") or "")
        for fixture in store.get("fixtures", []) or []
        if club_id in _match_participating_club_ids(store, fixture)
    )
    for source_fixture in store.get("fixtures", []) or []:
        if str(source_fixture.get("id") or "") not in club_fixture_ids:
            continue
        fixture = _club_dashboard_fixture_view(source_fixture, club)
        if not _match_scorer_is_authorized(store, user_row, current_club_id, source_fixture):
            continue
        open_now = _scorebook_is_open(fixture)
        can_edit = _match_score_editor_is_authorized(store, user_row, current_club_id, source_fixture)
        edit_existing = can_edit and _fixture_has_balls(fixture) and (_fixture_is_past(fixture) or _fixture_is_completed(fixture))
        if not open_now and str(fixture.get("date") or "") < today and not edit_existing:
            continue
        items.append(
            {
                "id": fixture.get("id"),
                "date": fixture.get("date"),
                "date_label": fixture.get("date_label") or fixture.get("date"),
                "opponent": fixture.get("opponent"),
                "status": fixture.get("status"),
                "overs": (fixture.get("details") or {}).get("overs") or "20",
                "open": open_now,
                "can_edit_scorebook": edit_existing,
                # Oct 29 2026: two matches vs the same team on one day need telling apart
                "time": str((fixture.get("details") or {}).get("scheduled_time") or ""),
                "started": _fixture_has_balls(fixture),
                "result": str((fixture.get("scorecard") or {}).get("result") or fixture.get("result") or "TBD"),
            }
        )
    # open matches first; on the same day the newest start time first (so a match just started is on top)
    items.sort(key=lambda item: (not item["open"], str(item["date"] or ""), -_time_sort_key(item["time"])))
    return {
        "club": {"id": club.get("id"), "name": club.get("name")},
        "fixtures": items[:12],
        "can_score": bool(items),
        "can_create": "manage_fixtures" in permissions,
        "today": today,
    }


def _fixture_has_balls(fixture: dict[str, Any]) -> bool:
    return any((innings.get("balls") or []) for innings in ((fixture.get("scorebook") or {}).get("innings") or []))


def _time_sort_key(text: str) -> int:
    """'9:05 AM' -> minutes after midnight, for ordering matches on the same day (unknown times last)."""
    match = re.match(r"\s*(\d{1,2}):(\d{2})\s*([AaPp][Mm])?", str(text or ""))
    if not match:
        return 24 * 60
    hour, minute = int(match.group(1)) % 12, int(match.group(2))
    if (match.group(3) or "").lower() == "pm":
        hour += 12
    return hour * 60 + minute


@app.post("/api/quick-score/start")
@_scoring_locked
def quick_score_start(request: QuickStartRequest, x_auth_token: str | None = Header(default=None)) -> dict[str, Any]:
    """Create a fixture for today so scoring can start straight away."""
    user_row, current_club_id = _require_permission(x_auth_token, "manage_fixtures")
    today = _current_local_date()
    opponent = request.opponent.strip()
    if not opponent:
        raise HTTPException(status_code=400, detail="Enter the opponent's name.")
    store = load_store()
    club = _selected_club(store, current_club_id)

    def todays_matches(current_store: dict[str, Any]) -> list[dict[str, Any]]:
        return [
            f
            for f in _club_fixtures(current_store, str(club.get("id") or ""))
            if str(f.get("date") or "") == today.isoformat() and str(f.get("opponent") or "").strip().lower() == opponent.lower()
        ]

    # Reuse today's match vs this team only if no ball has been bowled in it yet; once a match has started
    # (or finished), "Start" makes a new match (Dhruvika, Oct 29: it reopened the earlier GT / RCB scorecard).
    earlier = todays_matches(store)
    existing = next((f for f in earlier if not _fixture_has_balls(f)), None)
    if not existing:
        try:
            create_season_fixture(
                SeasonFixtureRequest(
                    club_id=str(club.get("id") or ""),
                    season_year=today.year,
                    date=today.isoformat(),
                    date_label=today.strftime("%B %-d") if os.name != "nt" else today.strftime("%B %#d"),
                    opponent=opponent,
                    venue=request.venue,
                    match_type=request.match_type or "Friendly",
                    scheduled_time=datetime.now().strftime("%I:%M %p").lstrip("0"),
                    overs=request.overs or "20",
                    notify=False,
                ),
                x_auth_token,
            )
        except HTTPException as exc:
            if exc.status_code == 409:  # same team, same minute
                raise HTTPException(status_code=409, detail=f"A match against {opponent} was started a moment ago. Open it from the list above.")
            raise
        store = load_store()
        known = {str(f.get("id")) for f in earlier}
        existing = next((f for f in todays_matches(store) if str(f.get("id")) not in known), None)
    if not existing:
        raise HTTPException(status_code=500, detail="Could not create today's match.")
    return {"match_id": existing.get("id")}


@app.get("/api/quick-score/{match_id}")
def quick_score_state(match_id: str, x_auth_token: str | None = Header(default=None)) -> dict[str, Any]:
    user_row, current_club_id = _auth_user_from_token(x_auth_token)
    store = load_store()
    try:
        fixture = get_match_or_404(store, match_id)
        payload = _public_match_payload(store, match_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    club = _selected_club(store, str(fixture.get("club_id") or current_club_id))
    lineups = _match_lineups(match_id)
    started = any((innings.get("balls") or []) for innings in (fixture.get("scorebook") or {}).get("innings", []) or [])
    can_score = _match_scorer_is_authorized(store, user_row, current_club_id, fixture)
    can_edit_scorebook = _match_score_editor_is_authorized(store, user_row, current_club_id, fixture)
    can_delete_incomplete = (
        not _fixture_is_completed(fixture)
        and _match_delete_is_authorized(store, user_row, current_club_id, fixture)
    )
    can_delete_completed = bool(
        _fixture_is_completed(fixture)
        and _match_delete_is_authorized(store, user_row, current_club_id, fixture)
    )
    return {
        "can_delete_completed": can_delete_completed,
        "match": payload,
        "open": _scorebook_is_open(fixture),
        "can_score": can_score,
        "can_edit_scorebook": can_edit_scorebook,
        "can_delete_incomplete": can_delete_incomplete,
        "roster": _club_member_names(store, club),
        # Nov 4 2026 (Amit): Player IDs shown while picking the team
        "roster_player_ids": {
            str(member.get("name")): str(member.get("player_id") or "")
            for member in store.get("members", []) or []
            if member.get("name") and member.get("player_id") and str(member.get("name")) in set(_club_member_names(store, club))
        },
        "lineups": lineups,
        # Matches already being scored before line-ups were required carry on without them.
        "lineups_ready": _lineups_ready(lineups) or started,
        "lineup_limits": {"min": LINEUP_MIN, "max": LINEUP_MAX},
        "club": {"id": club.get("id"), "name": club.get("name")},
    }


@app.get("/score")
def quick_score_page(request: Request) -> Response:
    session = _require_page_session(request)
    if isinstance(session, RedirectResponse):
        # Not signed in: score a guest match (README: "Line-ups and guest matches").
        return _page_response("quick_score_guest.html")
    return _page_response("quick_score.html")


# ---------------------------------------------------------------------------
# Public (signed-out) AI Assistant: read-only answers from public data only.
# Actions (saving scores, uploads, availability, alerts, team selection) ask the visitor to sign in.
# See README.md -> "AI Assistant and notifications" -> "Public AI Assistant".
# ---------------------------------------------------------------------------
class PublicMuseRequest(BaseModel):
    message: str


_PUBLIC_SIGNIN_LINKS = [{"label": "Sign in", "href": "/signin"}, {"label": "Register", "href": "/register"}]
_MONTHS = {m: i for i, m in enumerate(["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], start=1)}


def _public_date_from_text(text: str) -> str:
    lowered = text.lower()
    iso = re.search(r"\b(20\d{2})-(\d{1,2})-(\d{1,2})\b", lowered)
    if iso:
        return f"{iso.group(1)}-{int(iso.group(2)):02d}-{int(iso.group(3)):02d}"
    day_month = re.search(r"\b(\d{1,2})(?:st|nd|rd|th)?\s+([a-z]{3})[a-z]*\.?,?\s+(20\d{2})\b", lowered)
    month_day = re.search(r"\b([a-z]{3})[a-z]*\.?\s+(\d{1,2})(?:st|nd|rd|th)?,?\s+(20\d{2})\b", lowered)
    if day_month and day_month.group(2) in _MONTHS:
        return f"{day_month.group(3)}-{_MONTHS[day_month.group(2)]:02d}-{int(day_month.group(1)):02d}"
    if month_day and month_day.group(1) in _MONTHS:
        return f"{month_day.group(3)}-{_MONTHS[month_day.group(1)]:02d}-{int(month_day.group(2)):02d}"
    return ""


def _public_card_line(card: dict[str, Any]) -> str:
    card = _scorecard_list_item(card) if card.get("innings") is not None else card
    teams = " vs ".join(
        f"{team['name']} {team['score']}" + (f" ({team['overs']} ov)" if team.get("overs") else "") if team.get("score") else team["name"]
        for team in card.get("teams", [])
    )
    return f"{card['date_label']}: {teams}" + (f". {card['result']}" if card.get("result") else "")


@app.post("/api/public/muse")
def public_muse(request: PublicMuseRequest, x_auth_token: str | None = Header(default=None)) -> dict[str, Any]:
    message = " ".join(str(request.message or "").split())[:500]
    lowered = f" {message.lower()} "
    store = load_store()

    def reply(text: str, links: list[dict[str, str]] | None = None, intent: str = "public") -> dict[str, Any]:
        return {"reply": text, "links": links or [], "intent": intent, "source_label": "AI Assistant"}

    # Plans (README "Plans: what each group can use"): the AI Assistant is for signed-in members only.
    signed_in = False
    if x_auth_token:
        try:
            _auth_user_from_token(x_auth_token, touch=False)
            signed_in = True
        except HTTPException:
            signed_in = False
    if not signed_in:
        return reply(
            "The AI Assistant is for members. Sign in (or register for free) to use it. You can still see live scores, fixtures, scorecards and rankings without signing in.",
            _PUBLIC_SIGNIN_LINKS,
            "signin",
        )
    if not message:
        return reply("Ask me about live scores, results, scorecards, players or clubs.")

    # 2. How to join
    if re.search(r"\b(register|sign ?up|join|create (an )?account|add (my|our) club|new club|how do i start|log ?in|sign ?in)\b", lowered):
        return reply(
            "To join Cricket Canada Clubs:\n• Tap Register, enter your name and mobile or email, and pick your club.\n• If your club isn't listed, add it on the same form.\n• Club admins can then add fixtures, score matches and invite players.",
            _PUBLIC_SIGNIN_LINKS,
            "join",
        )

    # 3. Live scores
    if re.search(r"\b(live|right now|current score|score now|what'?s the score|who is playing|playing now)\b", lowered) and not re.search(r"\b(scoring|score (a|the|this|our) match|start)\b", lowered):
        payload = _public_live_page_payload(store)
        live = payload.get("live_matches") or []
        if not live:
            recent = (payload.get("recent_results") or [])[:3]
            text = "No matches are live right now."
            if recent:
                text += "\nLatest results:\n" + "\n".join(
                    f"• {item.get('club_name')} vs {item.get('opponent')}: {item.get('heartlake_score') or '–'} / {item.get('opponent_score') or '–'}. {str(item.get('result') or '').replace('Result: ', '')}"
                    for item in recent
                )
            return reply(text, [{"label": "Fixtures", "href": "/fixtures"}], "live")
        lines = ["Live now:"]
        links = []
        for item in live[:5]:
            lines.append(f"• {item.get('club_name')} {item.get('heartlake_score') or '0'} vs {item.get('opponent')} {item.get('opponent_score') or ''}".rstrip())
            links.append({"label": f"Follow {item.get('club_name')} vs {item.get('opponent')}", "href": f"/live/{item.get('id')}"})
        return reply("\n".join(lines), links[:3], "live")

    # 1. Things that need an account
    action = muse.detect_intent(message)
    if action in {"score_entry", "availability_request", "availability_summary", "upload_help", "alerts_help", "scoring_help"} or re.search(
        r"\b(playing xi|playing 11|best xi|best team|team selection|who should play|lineup|line up|my (stats|profile|availability|club))\b", lowered
    ):
        what = {
            "score_entry": "save a match score",
            "availability_request": "send availability requests",
            "availability_summary": "see who is available",
            "upload_help": "upload a scorecard photo",
            "alerts_help": "get match alerts",
            "scoring_help": "score a match live",
        }.get(action, "use team selection and personal stats")
        return reply(
            f"You need to sign in to {what}. Club members can do this with AI Assistant after signing in. It's free to register your club.",
            _PUBLIC_SIGNIN_LINKS,
            "signin_required",
        )

    cards = _public_scorecards(store)

    # 4. Scorecards by date
    wanted_date = _public_date_from_text(message)
    if wanted_date or re.search(r"\bscorecards?\b", lowered):
        if wanted_date:
            found = [card for card in cards if card["date"] == wanted_date]
            if found:
                return reply(
                    "\n".join("• " + _public_card_line(card) for card in found),
                    [{"label": f"Open scorecard ({card['title']})", "href": f"/scorecards/{card['id']}"} for card in found[:3]],
                    "scorecard",
                )
            return reply(f"There's no approved scorecard on {wanted_date}.", [{"label": "Browse scorecards by date", "href": f"/scorecards?date={wanted_date}"}], "scorecard")
        latest = cards[:4]
        return reply(
            "Latest scorecards:\n" + "\n".join("• " + _public_card_line(card) for card in latest) if latest else "No approved scorecards yet.",
            [{"label": "All scorecards", "href": "/scorecards"}],
            "scorecard",
        )

    # 5. Results ("who won", "result", "Coca Cola XI vs TP Community")
    clubs_named = cricket_insights._matched_clubs(message, store)
    if re.search(r"\b(who won|result|results|won|lost|beat|last match|latest match|recent)\b", lowered) and not re.search(r"\b(will|predict|chance)\b", lowered):
        pool = cards
        if clubs_named:
            names = {normalize_name(club.get("name") or "") for club in clubs_named}
            pool = [card for card in cards if any(normalize_name(team) in names for team in card.get("teams", []))]
        fixtures = _public_fixtures_page_payload(store).get("fixtures") or []
        completed = [f for f in fixtures if str(f.get("status_key") or "") == "completed"]
        if clubs_named:
            ids = {str(club.get("id") or "") for club in clubs_named}
            names = {normalize_name(club.get("name") or "") for club in clubs_named}
            completed = [f for f in completed if str(f.get("club_id") or "") in ids or normalize_name(f.get("opponent") or "") in names]
        completed.sort(key=lambda f: str(f.get("date") or ""), reverse=True)
        lines = [
            f"• {f.get('date')}: {f.get('club_name')} {f.get('heartlake_score') or '–'} vs {f.get('opponent')} {f.get('opponent_score') or '–'}. {str(f.get('result') or '').replace('Result: ', '')}"
            for f in completed[:3]
        ] + ["• " + _public_card_line(card) for card in pool[:3]]
        if not lines:
            return reply("I couldn't find any recorded results for that yet.", [{"label": "All scorecards", "href": "/scorecards"}], "results")
        return reply("Recent results:\n" + "\n".join(lines[:5]), [{"label": "All scorecards", "href": "/scorecards"}], "results")

    # 6. Clubs on the app
    if re.search(r"\b(which|what|list|all|how many)\b.*\bclubs?\b", lowered) or lowered.strip() in {"clubs", "teams"}:
        clubs = [str(club.get("name") or "") for club in store.get("clubs", []) or [] if club.get("name")]
        return reply(
            f"{len(clubs)} clubs are on Cricket Canada Clubs: " + ", ".join(sorted(clubs, key=str.lower)) + ".",
            [{"label": "Browse clubs", "href": "/clubs"}, {"label": "Register your club", "href": "/register"}],
            "clubs",
        )

    # 7. Stats, form, predictions, rankings (public numbers only; no contact details or availability)
    try:
        insight = cricket_insights.answer(message, store)
    except Exception:
        logger.exception("Public Muse insights failed")
        insight = None
    if insight and not str(insight.get("mode") or "").endswith("best-xi"):
        text = str(insight.get("answer") or "")
        # Club tips mention availability and pending reviews; keep those for members.
        text = "\n".join(
            line for line in text.splitlines() if "available" not in line.lower() and "pending" not in line.lower() and "waiting for review" not in line.lower()
        )
        return reply(text.strip(), [{"label": "Rankings", "href": "/rankings"}], "stats")

    # 8. Tasks (mark availability, add fixtures, update scores...) need an account.
    task = muse_agent.parse_command(message, _current_local_date(), muse.looks_like_score_message)
    if task and task.get("tool") not in {"availability_summary"}:
        return reply(
            "I can do that for you once you sign in: marking availability, updating scores, picking the XI and adding fixtures all happen in your club's account.",
            _PUBLIC_SIGNIN_LINKS,
            "signin",
        )

    # 9. Anything else: the LLM assistant, on public data only (no phone, email, age, notes or availability).
    try:
        named = cricket_insights._matched_clubs(re.sub(r"['’]s\b", "", message), store)
        answer = answer_question(message, _public_chat_store(store, str((named[0] if named else {}).get("id") or "")), history=[], session_id=None)
        text = _public_scrub(str(answer.get("answer") or ""))
        if text and not re.search(r"\b(i (don'?t|do not) (know|have)|couldn'?t find|no (data|information))\b", text.lower()):
            return {**reply(text, [{"label": "Sign in for more", "href": "/signin"}], "chat"), "source_label": answer.get("source_label") or "AI Assistant"}
    except Exception:
        logger.exception("Public Muse LLM answer failed")

    return reply(
        "I can help with live scores, results, scorecards by date, club rankings and player stats. Try:\n• What's the live score?\n• Who won the last Coca Cola XI match?\n• Scorecard for 19 Oct 2024\n• Top run scorers\n• How is Amit S doing?\nSign in for scoring, availability and alerts.",
        _PUBLIC_SIGNIN_LINKS,
        "help",
    )


_PUBLIC_MEMBER_FIELDS = {
    "id", "name", "full_name", "aliases", "role", "batting_style", "bowling_style", "jersey_number",
    "primary_club_id", "primary_club_name", "club_memberships", "team_memberships", "team_name",
}


def _public_chat_store(store: dict[str, Any], focus_club_id: str = "") -> dict[str, Any]:
    """A copy of the data that is safe to show signed-out visitors: no contact details, ages, notes,
    availability or scorecards still waiting for review."""
    safe = {key: value for key, value in store.items() if key not in {"llm_documents", "llm_query_cache", "viewer_profile", "duplicate_uploads"}}
    safe["members"] = [{k: v for k, v in member.items() if k in _PUBLIC_MEMBER_FIELDS} for member in store.get("members", []) or []]
    safe["fixtures"] = [
        {
            **{k: v for k, v in fixture.items() if k not in {"created_by_user_id", "updated_by_user_id"}},
            # keep the keys (the assistant expects them) but empty: availability is members-only
            "availability": [],
            "availability_seed": [],
            "availability_statuses": {},
            "availability_notes": {},
            "selected_playing_xi": [],
            "selected_playing_xi_member_ids": [],
        }
        for fixture in store.get("fixtures", []) or []
    ]
    safe["archive_uploads"] = [upload for upload in store.get("archive_uploads", []) or [] if str(upload.get("status") or "").lower() == "approved"]
    safe["viewer_profile"] = {}
    return _chat_store_for(safe, focus_club_id)


def _public_scrub(text: str) -> str:
    """Belt and braces: remove anything that looks like an email address or phone number."""
    text = re.sub(r"[\w.+-]+@[\w-]+\.[\w.-]+", "[hidden]", text)
    return re.sub(r"(?<!\d)(?:\+?1[\s.-]?)?\(?\d{3}\)?[\s.-]?\d{3}[\s.-]?\d{4}(?!\d)", "[hidden]", text)


# ---------------------------------------------------------------------------
# Subscriptions and plans (Free / Pro) - see app/subscriptions.py
# Documented in README.md -> "Subscriptions and plans".
# ---------------------------------------------------------------------------
class CheckoutRequest(BaseModel):
    plan: str = "pro"
    interval: str = "month"


class AdminSetPlanRequest(BaseModel):
    user: str
    plan: str
    days: int = 0
    note: str = ""


class AiScorerRequest(BaseModel):
    text: str
    innings_number: int = 1


def _plan_for(user_row: sqlite3.Row, current_club_id: str = "") -> dict[str, Any]:
    try:
        with _auth_connection() as connection:
            return subscriptions.effective_plan(connection, user_row, _user_role_names(user_row, current_club_id))
    except Exception:
        logger.exception("Plan lookup failed for user %s", user_row["id"])
        # Never lock people out because of a billing error.
        return {"plan": "pro", "plan_name": "Pro", "features": subscriptions.plan_features("pro"), "upload_limit": None, "uploads_used": 0, "uploads_left": None, "source": "fallback"}


def _has_feature(user_row: sqlite3.Row, current_club_id: str, feature: str) -> bool:
    return feature in _plan_for(user_row, current_club_id).get("features", [])


def _ai_allowed(user_row: sqlite3.Row, current_club_id: str, feature: str, match_id: str = "", *, claim: bool = True) -> bool:
    """Pro has AI everywhere. A Free user gets ONE free AI match: the first match they use the
    AI Assistant or AI Scorer on (README: "Subscriptions and plans" -> "One free AI match")."""
    if _has_feature(user_row, current_club_id, feature):
        return True
    if feature not in subscriptions.AI_TRIAL_FEATURES:
        return False
    try:
        with _auth_connection() as connection:
            return subscriptions.claim_ai_trial(connection, int(user_row["id"]), str(match_id or ""), claim=claim)
    except Exception:
        logger.exception("AI trial lookup failed for user %s", user_row["id"])
        return False


def _club_is_paid(club_id: str) -> bool:
    """A club is paid when one of its captains / club admins is on Pro."""
    if not club_id:
        return False
    try:
        with _auth_connection() as connection:
            return subscriptions.paid_manager_count(connection, club_id) > 0
    except Exception:
        logger.exception("Paid-club lookup failed for %s", club_id)
        return True


def _upgrade_error(feature: str) -> HTTPException:
    return HTTPException(status_code=402, detail=subscriptions.upgrade_message(feature))


def _require_feature(user_row: sqlite3.Row, current_club_id: str, feature: str, *, club_id: str = "") -> None:
    """Raise 402 unless the user (or, when club_id is given, their club) has the feature."""
    if _has_feature(user_row, current_club_id, feature):
        return
    if club_id and _club_is_paid(club_id):
        return
    raise _upgrade_error(feature)


def _require_multi_club(user_row: sqlite3.Row, target_club_id: str) -> None:
    """Free users stay on their home club; switching to another club needs Pro."""
    primary = str(user_row["primary_club_id"] or "").strip()
    if not primary or not target_club_id or target_club_id == primary:
        return
    if _has_feature(user_row, target_club_id, "multi_club"):
        return
    raise _upgrade_error("multi_club")


_MUSE_PAID_ACTIONS = {"score_entry", "availability_request", "availability_summary", "alerts_help"}


def _muse_free_reply(message: str, intent: str) -> dict[str, Any]:
    """Free plan: AI Muse answers stats questions (like the public Muse); actions need Pro."""
    plans_link = [{"label": "See plans", "href": "/pricing"}]
    if intent in _MUSE_PAID_ACTIONS:
        what = {
            "score_entry": "Saving scores from a message or voice note",
            "availability_request": "Sending availability requests",
            "availability_summary": "Availability summaries",
            "alerts_help": "Player alerts",
        }.get(intent, "This")
        return {
            "reply": f"{what} is part of the AI Assistant on Pro ($9 a month or $90 a year). On Free you can still score matches yourself with Quick Score and ask me about stats, results and scorecards.",
            "intent": intent,
            "source_label": "AI Assistant",
            "links": plans_link + ([{"label": "Quick Score", "href": "/score"}] if intent == "score_entry" else []),
            "upgrade": "pro",
        }
    if intent == "scoring_help":
        return {
            "reply": "Open Quick Score, pick today's match and tap the big buttons: 0–6, Wd, Nb, Bye, LB and W. Live scoring is free on every plan.",
            "intent": intent,
            "source_label": "AI Assistant",
            "links": [{"label": "Quick Score", "href": "/score"}],
        }
    if intent == "upload_help":
        return {
            "reply": "Tap 📎 to upload a scorecard photo. The Free plan includes 2 scorecard image uploads a month; Pro is unlimited.",
            "intent": intent,
            "source_label": "AI Assistant",
            "links": plans_link,
        }
    result = public_muse(PublicMuseRequest(message=message))
    links = [link for link in result.get("links") or [] if link.get("href") not in {"/signin", "/register"}]
    reply_text = str(result.get("reply") or "")
    if "sign in" in reply_text.lower():
        reply_text = "That's part of the AI Assistant on Pro. On Free I can answer questions about live scores, results, scorecards, players and clubs."
        links = plans_link
    return {**result, "reply": reply_text, "links": links, "plan_note": "Free plan: stats answers only"}


def _match_intelligence(store: dict[str, Any], club: dict[str, Any], club_info: dict[str, Any] | None) -> dict[str, Any] | None:
    """Pro: a pre-match briefing for the next fixture."""
    next_match = (club_info or {}).get("next_match")
    if not next_match:
        return None
    opponent = str(next_match.get("opponent") or "")
    club_name = str(club.get("name") or "")
    club_id = str(club.get("id") or "")
    head_to_head = {"played": 0, "won": 0, "lost": 0, "last": ""}
    for fixture in sorted(store.get("fixtures") or [], key=lambda item: str(item.get("date") or "")):
        if str(fixture.get("club_id") or "") != club_id or normalize_name(str(fixture.get("opponent") or "")) != normalize_name(opponent):
            continue
        result = str(fixture.get("result") or "").strip()
        if not result or not re.search(r"\b(won|win|beat|tied|tie|no result|abandoned)\b", result.lower()):
            continue
        head_to_head["played"] += 1
        lowered = result.lower()
        if normalize_name(club_name) and lowered.startswith(normalize_name(club_name)) and " won" in lowered:
            head_to_head["won"] += 1
        elif " won" in lowered:
            head_to_head["lost"] += 1
        head_to_head["last"] = f"{fixture.get('date')}: {result}"
    opponent_club = cricket_insights.find_club(store, opponent)
    danger: list[dict[str, Any]] = []
    if opponent_club:
        try:
            opponent_info = cricket_insights.club_insights(store, opponent_club)
            danger = [
                {"name": row["name"], "runs": row["runs"], "form": row.get("form", "")}
                for row in (opponent_info.get("batting") or {}).get("top_scorers", [])[:3]
            ] + [
                {"name": row["name"], "wickets": row["wickets"]}
                for row in (opponent_info.get("bowling") or {}).get("wicket_takers", [])[:2]
            ]
        except Exception:
            logger.exception("Opponent insights failed for %s", opponent)
    in_form = ((club_info or {}).get("form") or {}).get("in_form", [])[:4]
    keys: list[str] = []
    chance = int(next_match.get("win_chance") or 50)
    if chance >= 60:
        keys.append(f"You start as favourites ({chance}%). Bat first and set a target if the pitch is good.")
    elif chance <= 40:
        keys.append(f"{opponent} are favourites ({100 - chance}%). Keep wickets in hand early and target their weaker bowlers.")
    else:
        keys.append("This looks like a close game. Fielding and extras will likely decide it.")
    if int(next_match.get("available") or 0) < 11:
        keys.append(f"Only {next_match.get('available', 0)} players are available so far. Chase replies before match day.")
    if in_form:
        keys.append("In form: " + ", ".join(in_form) + ". Give them the key batting slots.")
    if danger:
        keys.append(f"Watch out for {danger[0]['name']} from {opponent}.")
    return {
        "date": next_match.get("date"),
        "opponent": opponent,
        "win_chance": chance,
        "confidence": next_match.get("confidence"),
        "available": next_match.get("available"),
        "head_to_head": head_to_head,
        "opponent_key_players": danger,
        "our_in_form": in_form,
        "keys": keys,
    }


def _cross_club_stats(store: dict[str, Any], member: dict[str, Any]) -> list[dict[str, Any]]:
    """Pro: the player's numbers for every club they have played for."""
    member_id = str(member.get("id") or "")
    rows = [row for row in store.get("member_club_stats") or [] if str(row.get("member_id") or "") == member_id]
    return [
        {
            "club": row.get("club_name") or row.get("club_id"),
            "matches": int(row.get("matches") or 0),
            "runs": int(row.get("runs") or 0),
            "average": round(float(row.get("batting_average") or 0), 1),
            "highest": int(row.get("highest_score") or 0),
            "wickets": int(row.get("wickets") or 0),
            "catches": int(row.get("catches") or 0),
        }
        for row in sorted(rows, key=lambda item: -int(item.get("runs") or 0))
    ]


# ---------------------------------------------------------------------------
# Line-ups and guest matches (Oct 2026). README: MD/README.md -> "Line-ups and guest matches".
#
# * Both teams need a line-up of 2-11 players before scoring can start.
# * Anyone (no sign-in) can start a guest match: team names, both line-ups, then Quick Score.
#   The creator gets a 6-character match code; the code is needed to score (send it as
#   X-Guest-Code) and lets a second phone continue scoring. Guest matches are stored on their
#   own (table app_guest_matches) so they never change club stats, and they show on the public
#   Live page while they are being played.
# ---------------------------------------------------------------------------
LINEUP_MIN = 2
LINEUP_MAX = 11
_GUEST_CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"


def _ensure_extra_match_tables(connection: sqlite3.Connection) -> None:
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS app_match_lineups (
          match_id TEXT PRIMARY KEY,
          lineups_json TEXT NOT NULL,
          updated_at TEXT NOT NULL,
          updated_by TEXT
        );
        CREATE TABLE IF NOT EXISTS app_guest_matches (
          id TEXT PRIMARY KEY,
          code TEXT NOT NULL UNIQUE,
          match_date TEXT NOT NULL,
          created_at TEXT NOT NULL,
          updated_at TEXT NOT NULL,
          data_json TEXT NOT NULL
        );
        """
    )


def _clean_lineup(names: Any) -> list[str]:
    if isinstance(names, str):
        names = re.split(r"[\n,;]+", names)
    cleaned: list[str] = []
    for raw in names or []:
        name = " ".join(str(raw or "").split())[:40]
        if name and name.lower() not in {n.lower() for n in cleaned}:
            cleaned.append(name)
    return cleaned


LINEUP_ROLES = ("captain", "vice_captain", "keeper")


def _clean_lineup_roles(roles: Any, club_side: list[str], opponent_side: list[str]) -> dict[str, dict[str, str]]:
    """Captain, vice-captain and wicket keeper of each team (README "Captain, vice-captain and keeper").
    Only names in that team's line-up are kept; the keeper may also be the captain or vice-captain."""
    roles = roles if isinstance(roles, dict) else {}
    cleaned: dict[str, dict[str, str]] = {}
    for side, names in (("club", club_side), ("opponent", opponent_side)):
        by_lower = {name.lower(): name for name in names}
        side_roles = roles.get(side) if isinstance(roles.get(side), dict) else {}
        picked = {}
        for role in LINEUP_ROLES:
            name = by_lower.get(" ".join(str(side_roles.get(role) or "").split()).lower())
            if name:
                picked[role] = name
        cleaned[side] = picked
    return cleaned


def _lineup_problem(club_side: list[str], opponent_side: list[str], club_label: str, opponent_label: str) -> str:
    for label, names in ((club_label, club_side), (opponent_label, opponent_side)):
        if len(names) < LINEUP_MIN:
            return f"{label} needs at least {LINEUP_MIN} players in the line-up."
        if len(names) > LINEUP_MAX:
            return f"{label} can have at most {LINEUP_MAX} players in the line-up."
    overlap = {n.lower() for n in club_side} & {n.lower() for n in opponent_side}
    if overlap:
        return f"A player can't be in both line-ups: {', '.join(sorted(overlap))}."
    return ""


def _match_lineups(match_id: str) -> dict[str, list[str]]:
    with _auth_connection() as connection:
        _ensure_extra_match_tables(connection)
        row = connection.execute("SELECT lineups_json FROM app_match_lineups WHERE match_id = ?", (match_id,)).fetchone()
    if not row:
        return {}
    try:
        data = json.loads(row["lineups_json"] or "{}")
    except ValueError:
        return {}
    club_side, opponent_side = _clean_lineup(data.get("club")), _clean_lineup(data.get("opponent"))
    return {"club": club_side, "opponent": opponent_side, "roles": _clean_lineup_roles(data.get("roles"), club_side, opponent_side)}


def _lineups_ready(lineups: dict[str, list[str]]) -> bool:
    return bool(lineups) and not _lineup_problem(lineups.get("club", []), lineups.get("opponent", []), "Your team", "The other team")


def _all_out_at(match: dict[str, Any], innings: dict[str, Any], lineups: dict[str, list[str]]) -> int:
    """Wickets that end an innings: one fewer than the batting side's line-up (10 for a full XI)."""
    if not lineups:
        return 10
    batting = str(innings.get("batting_team") or "").strip().lower()
    side = "club" if batting == str(match.get("club_name") or "").strip().lower() else "opponent"
    count = len(lineups.get(side) or [])
    return max(1, min(10, count - 1)) if count >= LINEUP_MIN else 10


class LineupsRequest(BaseModel):
    club: list[str] | str = Field(default_factory=list)
    opponent: list[str] | str = Field(default_factory=list)
    # {"club": {"captain": "Ravi", "vice_captain": "Sam", "keeper": "Dev"}, "opponent": {...}} - all optional
    roles: dict[str, dict[str, str]] = Field(default_factory=dict)


@app.post("/api/matches/{match_id}/lineups")
@_scoring_locked
def save_match_lineups(match_id: str, request: LineupsRequest, x_auth_token: str | None = Header(default=None)) -> dict[str, Any]:
    user_row, _ = _require_match_scorer(x_auth_token, match_id)
    store = load_store()
    try:
        match = get_match_or_404(store, match_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    _require_not_past(match, "the line-ups")
    if _lineups_ready(_match_lineups(match_id)) or _fixture_has_balls(match):
        user_row, _ = _require_match_score_editor(x_auth_token, match_id)
    club_side, opponent_side = _clean_lineup(request.club), _clean_lineup(request.opponent)
    problem = _lineup_problem(club_side, opponent_side, str(match.get("club_name") or "Your team"), str(match.get("opponent") or "The other team"))
    if problem:
        raise HTTPException(status_code=400, detail=problem)
    roles = _clean_lineup_roles(request.roles, club_side, opponent_side)
    for side, label in (("club", str(match.get("club_name") or "Your team")), ("opponent", str(match.get("opponent") or "The other team"))):
        if roles[side].get("captain") and roles[side].get("captain") == roles[side].get("vice_captain"):
            raise HTTPException(status_code=400, detail=f"{label}: the captain and vice-captain must be different players.")
    with _auth_connection() as connection:
        _ensure_extra_match_tables(connection)
        connection.execute(
            """INSERT INTO app_match_lineups (match_id, lineups_json, updated_at, updated_by) VALUES (?, ?, ?, ?)
               ON CONFLICT(match_id) DO UPDATE SET lineups_json = excluded.lineups_json, updated_at = excluded.updated_at, updated_by = excluded.updated_by""",
            (match_id, json.dumps({"club": club_side, "opponent": opponent_side, "roles": roles}), now_iso(), str(user_row["display_name"] or "")),
        )
    return {"lineups": {"club": club_side, "opponent": opponent_side, "roles": roles}, "ready": True}


# ---------- guest matches ----------
class GuestMatchRequest(BaseModel):
    team_a: str
    team_b: str
    overs: int = 20
    venue: str = ""
    lineup_a: list[str] | str = Field(default_factory=list)
    roles: dict[str, dict[str, str]] = Field(default_factory=dict)  # same shape as LineupsRequest.roles (club = team 1)
    lineup_b: list[str] | str = Field(default_factory=list)


def _guest_code() -> str:
    import secrets

    return "".join(secrets.choice(_GUEST_CODE_ALPHABET) for _ in range(6))


def _guest_load(match_id: str) -> dict[str, Any] | None:
    with _auth_connection() as connection:
        _ensure_extra_match_tables(connection)
        row = connection.execute("SELECT data_json, code FROM app_guest_matches WHERE id = ?", (match_id,)).fetchone()
    if not row:
        return None
    match = json.loads(row["data_json"])
    match["_code"] = row["code"]
    return match


def _guest_save(match: dict[str, Any]) -> None:
    data = {k: v for k, v in match.items() if k != "_code"}
    data["updated_at"] = now_iso()
    with _auth_connection() as connection:
        connection.execute("UPDATE app_guest_matches SET data_json = ?, updated_at = ? WHERE id = ?", (json.dumps(data), data["updated_at"], match["id"]))


def _guest_require(match_id: str, code: str | None) -> dict[str, Any]:
    match = _guest_load(match_id)
    if not match:
        raise HTTPException(status_code=404, detail="Guest match not found.")
    if not code or not hmac.compare_digest(str(code).strip().upper(), str(match.get("_code") or "")):
        raise HTTPException(status_code=403, detail="Enter this match's 6-character code to score it.")
    return match


def _guest_fixtures(only_today: bool = True) -> list[dict[str, Any]]:
    today = _current_local_date().isoformat()
    try:
        with _auth_connection() as connection:
            _ensure_extra_match_tables(connection)
            rows = connection.execute(
                "SELECT data_json FROM app_guest_matches WHERE match_date = ? ORDER BY created_at DESC LIMIT 50" if only_today else "SELECT data_json FROM app_guest_matches ORDER BY created_at DESC LIMIT 200",
                (today,) if only_today else (),
            ).fetchall()
    except sqlite3.DatabaseError:
        return []
    return [json.loads(row["data_json"]) for row in rows]


@app.post("/api/guest/matches")
def guest_match_create(request: GuestMatchRequest) -> dict[str, Any]:
    team_a = " ".join(request.team_a.split())[:40]
    team_b = " ".join(request.team_b.split())[:40]
    if not team_a or not team_b:
        raise HTTPException(status_code=400, detail="Enter both team names.")
    if team_a.lower() == team_b.lower():
        raise HTTPException(status_code=400, detail="The two teams need different names.")
    lineup_a, lineup_b = _clean_lineup(request.lineup_a), _clean_lineup(request.lineup_b)
    problem = _lineup_problem(lineup_a, lineup_b, team_a, team_b)
    if problem:
        raise HTTPException(status_code=400, detail=problem)
    overs = max(1, min(50, int(request.overs or 20)))
    today = _current_local_date()
    match_id = f"guest-{uuid.uuid4().hex[:8]}"
    now = now_iso()
    fixture = {
        "id": match_id,
        "guest": True,
        "club_id": "",
        "club_name": team_a,
        "club_short_name": team_a,
        "season_year": str(today.year),
        "season": f"{today.year} Season",
        "date": today.isoformat(),
        "date_label": f"{today.strftime('%B')} {today.day}",
        "opponent": team_b,
        "visiting_team": team_b,
        "heartlake_captain": "",
        "availability_seed": [],
        "availability_statuses": {},
        "availability_notes": {},
        "heartlake_score": "",
        "opponent_score": "",
        "result": "TBD",
        "status": "Scheduled",
        "commentary": [],
        "created_at": now,
        "updated_at": now,
        "details": {"venue": " ".join(request.venue.split())[:60], "match_type": "Guest match", "scheduled_time": datetime.now().strftime("%I:%M %p").lstrip("0"), "overs": str(overs)},
        "scorecard": default_scorecard("TBD"),
        "performances": [],
        "lineups": {"club": lineup_a, "opponent": lineup_b, "roles": _clean_lineup_roles(request.roles, lineup_a, lineup_b)},
    }
    fixture["scorebook"] = default_match_scorebook({"club_name": team_a, "club_short_name": team_a, "opponent": team_b, "details": {"overs": str(overs)}})
    code = _guest_code()
    with _auth_connection() as connection:
        _ensure_extra_match_tables(connection)
        for _ in range(5):
            try:
                connection.execute(
                    "INSERT INTO app_guest_matches (id, code, match_date, created_at, updated_at, data_json) VALUES (?, ?, ?, ?, ?, ?)",
                    (match_id, code, today.isoformat(), now, now, json.dumps(fixture)),
                )
                break
            except sqlite3.IntegrityError:
                code = _guest_code()
    return {"match_id": match_id, "code": code, "live_url": f"/live/{match_id}"}


@app.get("/api/guest/resume")
def guest_match_resume(code: str) -> dict[str, Any]:
    with _auth_connection() as connection:
        _ensure_extra_match_tables(connection)
        row = connection.execute("SELECT id FROM app_guest_matches WHERE code = ?", (str(code or "").strip().upper(),)).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="No match has that code. Check the 6 characters and try again.")
    return {"match_id": row["id"]}


@app.get("/api/guest/matches/{match_id}")
def guest_match_state(match_id: str, x_guest_code: str | None = Header(default=None)) -> dict[str, Any]:
    match = _guest_require(match_id, x_guest_code)
    payload = _public_match_payload({"fixtures": [match]}, match_id)
    lineups = match.get("lineups") or {}
    return {
        "match": payload,
        "open": str(match.get("date") or "") == _current_local_date().isoformat() and str(match.get("status") or "").lower() != "completed",
        "can_score": True,
        "guest": True,
        "roster": lineups.get("club", []),
        "lineups": lineups,
        "lineups_ready": _lineups_ready(lineups),
        "club": {"id": "", "name": match.get("club_name")},
    }


def _same_overs_both_innings(match: dict[str, Any], scorebook: dict[str, Any], innings: dict[str, Any]) -> None:
    """Both teams get the same overs (Dhruvika, Oct 30: a 1-over match gave the other team 2 overs).
    The overs chosen when an innings is set up are copied to the other innings if it hasn't started, and to the match."""
    overs = int(innings.get("overs_limit") or 20)
    for other in scorebook.get("innings", []):
        if other is not innings and not (other.get("balls") or []):
            other["overs_limit"] = overs
    details = match.get("details")
    if isinstance(details, dict):
        details["overs"] = str(overs)
    if "overs" in match:
        match["overs"] = str(overs)


@app.post("/api/guest/matches/{match_id}/setup")
@_scoring_locked
def guest_match_setup(match_id: str, request: ScorebookSetupRequest, x_guest_code: str | None = Header(default=None)) -> dict[str, Any]:
    match = _guest_require(match_id, x_guest_code)
    if str(match.get("date") or "") != _current_local_date().isoformat():
        raise HTTPException(status_code=400, detail="Guest matches can only be scored on the day they were created.")
    scorebook = _match_scorebook(match)
    innings = scorebook["innings"][max(1, min(2, int(request.innings_number or 1))) - 1]
    innings["inning_number"] = max(1, min(2, int(request.innings_number or 1)))
    innings["batting_team"] = request.batting_team.strip()
    innings["bowling_team"] = request.bowling_team.strip()
    innings["overs_limit"] = max(1, int(request.overs_limit or 20))
    _same_overs_both_innings(match, scorebook, innings)
    innings["target_runs"] = int(request.target_runs) if request.target_runs else None
    innings["status"] = request.status.strip() or "Not started"
    innings["batters"] = [{"slot_number": slot, "player_name": str(request.batters[slot - 1] if slot - 1 < len(request.batters) else "").strip()} for slot in range(1, 12)]
    innings["bowlers"] = [{"slot_number": slot, "player_name": str(request.bowlers[slot - 1] if slot - 1 < len(request.bowlers) else "").strip()} for slot in range(1, 12)]
    sync_fixture_scorecard_from_scorebook(match)
    _guest_save(match)
    return {"ok": True}


@app.post("/api/guest/matches/{match_id}/ball")
@_scoring_locked
def guest_match_ball(match_id: str, request: ScorebookBallRequest, x_guest_code: str | None = Header(default=None)) -> dict[str, Any]:
    match = _guest_require(match_id, x_guest_code)
    scorebook = _match_scorebook(match)
    innings = scorebook["innings"][max(1, min(2, int(request.innings_number or 1))) - 1]
    retry_id = re.sub(r"[^A-Za-z0-9_-]", "", str(request.client_id or ""))[:40]
    if retry_id and not str(request.id or "").strip() and any(str(item.get("id") or "") == retry_id for item in innings.get("balls", []) or []):
        # a retry of a ball that did save (e.g. the winning ball, after which the match closes)
        return {"ok": True, "status": match.get("status"), "result": match.get("result"), "already_saved": True}
    if str(match.get("date") or "") != _current_local_date().isoformat() or str(match.get("status") or "").lower() == "completed":
        raise HTTPException(status_code=400, detail="This guest match is closed for scoring.")
    ball = normalize_scorebook_ball(
        {
            "over_number": request.over_number,
            "ball_number": request.ball_number,
            "striker": request.striker.strip(),
            "non_striker": request.non_striker.strip(),
            "bowler": request.bowler.strip(),
            "runs_bat": request.runs_bat,
            "extras_type": request.extras_type,
            "extras_runs": request.extras_runs,
            "wicket": request.wicket,
            "wicket_type": request.wicket_type,
            "wicket_player": request.wicket_player.strip(),
            "fielder": request.fielder.strip(),
            "commentary": request.commentary,
            "new_batter": request.new_batter.strip(),
        }
    )
    _validate_retired_out_ball(ball)
    if _client_ball_seen(innings, ball, request):
        return {"ok": True, "status": match.get("status"), "result": match.get("result"), "already_saved": True}
    is_edit = bool(str(request.id or "").strip())
    if not is_edit and _innings_is_over(match, innings, match.get("lineups") or {}):
        raise HTTPException(status_code=400, detail="This innings is over. To change the last ball, tap Undo.")
    if _apply_ball_edit(innings, ball, request.id):
        # A fixed ball can undo a finished innings / match (e.g. a wicket that wasn't); worked out again below.
        innings["status"] = "Live"
        match["status"] = "Live"
    innings["balls"] = [item for item in innings.get("balls", []) if item.get("id") != ball["id"]]
    innings["balls"].append(ball)
    innings["balls"].sort(key=lambda item: (int(item.get("over_number", 1) or 1), int(item.get("ball_number", 1) or 1), str(item.get("created_at", ""))))
    lineups = match.get("lineups")
    if not isinstance(lineups, dict):
        lineups = {}
        match["lineups"] = lineups
    batting_side = "club" if str(innings.get("batting_team") or "").strip().lower() == str(match.get("club_name") or "").strip().lower() else "opponent"
    batting_lineup = list(lineups.get(batting_side) or [])
    known_batters = {str(name).strip().lower() for name in batting_lineup}
    for name in (ball.get("striker"), ball.get("non_striker"), request.new_batter):
        clean_name = " ".join(str(name or "").split())
        if clean_name and clean_name.lower() not in known_batters and len(batting_lineup) < LINEUP_MAX:
            batting_lineup.append(clean_name)
            known_batters.add(clean_name.lower())
    lineups[batting_side] = batting_lineup
    summary = summarize_innings_scorebook(innings)
    if summary["runs"] or summary["wickets"] or summary["legal_balls"]:
        innings["status"] = "Live"
        match["status"] = "Live"
    if scorebook_wickets_for_all_out(innings) >= _all_out_at(match, innings, match.get("lineups") or {}) or summary["legal_balls"] >= int(innings.get("overs_limit", 20) or 20) * 6:
        innings["status"] = "Completed"
    first, second = scorebook["innings"][0], scorebook["innings"][1]
    if innings is second and first.get("status") == "Completed":
        target = int(summarize_innings_scorebook(first)["runs"]) + 1
        if summary["runs"] >= target:
            innings["status"] = "Completed"
    if first.get("status") == "Completed" and second.get("status") == "Completed":
        match["status"] = "Completed"
        a, b = summarize_innings_scorebook(first), summarize_innings_scorebook(second)
        match["result"] = scorebook_result_text(first, second, a, b, _all_out_at(match, second, match.get("lineups") or {}))
        match.setdefault("scorecard", {})["result"] = match["result"]
    sync_fixture_scorecard_from_scorebook(match)
    if str(match.get("status") or "").lower() != "completed":
        match["result"] = "TBD"
        match.setdefault("scorecard", {})["result"] = "TBD"
    else:
        match.setdefault("scorecard", {})["result"] = match["result"]
    _guest_save(match)
    return {"ok": True, "status": match.get("status"), "result": match.get("result")}


@app.delete("/api/guest/matches/{match_id}/ball")
@_scoring_locked
def guest_match_undo(match_id: str, x_guest_code: str | None = Header(default=None)) -> dict[str, Any]:
    match = _guest_require(match_id, x_guest_code)
    scorebook = _match_scorebook(match)
    for innings in reversed(scorebook.get("innings", [])):
        balls = innings.get("balls") or []
        if balls:
            innings["balls"] = balls[:-1]
            if innings.get("status") == "Completed":
                innings["status"] = "Live"
            match["status"] = "Live" if innings["balls"] else match.get("status")
            match["result"] = "TBD"
            break
    else:
        raise HTTPException(status_code=400, detail="No ball to undo.")
    sync_fixture_scorecard_from_scorebook(match)
    match["result"] = "TBD"
    match.setdefault("scorecard", {})["result"] = "TBD"
    if str(match.get("status") or "").lower() == "completed":
        match["status"] = "Live"
    _guest_save(match)
    return {"ok": True}


@app.get("/api/public/guest-matches")
def public_guest_matches() -> dict[str, Any]:
    """Today's guest matches for the public Live page (no codes, no private data)."""
    items = []
    for match in _guest_fixtures(only_today=True):
        payload = _public_match_payload({"fixtures": [match]}, str(match.get("id")))
        items.append({k: payload.get(k) for k in ("id", "club_name", "opponent", "date", "date_label", "status", "venue", "overs", "result", "match_type")} | {"innings": [{"batting_team": i["batting_team"], "summary": {k: i["summary"].get(k) for k in ("runs", "wickets", "overs", "legal_balls")}} for i in (payload.get("scorebook") or {}).get("innings") or []]})
    return {"matches": items}


@app.get("/api/public/config")
def public_config() -> dict[str, Any]:
    """Small switches the pages need. subscriptions=False: launch mode, everyone on Pro, Plans hidden."""
    return {"subscriptions": subscriptions.subscriptions_on()}


@app.delete("/api/admin/users/{user_id}")
def admin_delete_user(user_id: int, x_auth_token: str | None = Header(default=None)) -> dict[str, Any]:
    """Site admin: delete a sign-in account (e.g. test accounts before launch). The player record (member)
    is not touched. You can't delete yourself or another site admin."""
    admin_row, _ = _require_superadmin(x_auth_token)
    if int(user_id) == int(admin_row["id"]):
        raise HTTPException(status_code=400, detail="You can't delete your own account.")
    row = _delete_app_user(int(user_id))
    _audit_event("user.delete", "app_user", str(user_id), actor=admin_row, details={"display_name": str(row["display_name"] or "")}, source="api")
    return {"message": f"Account {row['display_name']} deleted."}


def _delete_app_user(user_id: int) -> sqlite3.Row:
    """Delete a sign-in account and everything linked to it by user id (sessions, settings, tour...).
    The club's player record and published scorecards stay (club match history). Site admins are never deleted."""
    with _auth_connection() as connection:
        row = connection.execute("SELECT id, display_name, role FROM app_users WHERE id = ?", (int(user_id),)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Account not found.")
        if str(row["role"] or "") == "superadmin":
            raise HTTPException(status_code=400, detail="Site admin accounts can't be deleted here.")
        tables = [r[0] for r in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()]
        for table in tables:
            columns = {r[1] for r in connection.execute(f'PRAGMA table_info("{table}")').fetchall()}
            for column in ("user_id", "target_user_id"):
                if column in columns and table != "app_users":
                    connection.execute(f'DELETE FROM "{table}" WHERE "{column}" = ?', (int(user_id),))
        connection.execute("DELETE FROM app_users WHERE id = ?", (int(user_id),))
    return row


class AccountDeleteRequest(BaseModel):
    confirmation: str = ""


@app.post("/api/account/delete")
def delete_my_account(request: AccountDeleteRequest, x_auth_token: str | None = Header(default=None)) -> dict[str, Any]:
    """"Delete my account" on the Profile page (README "Privacy policy and Delete my account"; Apple requires it
    for apps where people can sign up). The member types DELETE to confirm. Signs them out everywhere."""
    user_row, current_club_id = _auth_user_from_token(x_auth_token, touch=False)
    if str(request.confirmation or "").strip().upper() != "DELETE":
        raise HTTPException(status_code=400, detail="Type DELETE to confirm.")
    if "superadmin" in _user_role_names(user_row, current_club_id) or str(user_row["role"] or "") == "superadmin":
        raise HTTPException(status_code=400, detail="Site admin accounts can't be deleted from the app. Ask another site admin.")
    row = _delete_app_user(int(user_row["id"]))
    _audit_event("user.self_delete", "app_user", str(user_row["id"]), actor=None, club_id=current_club_id, details={"display_name": str(row["display_name"] or "")}, source="api")
    return {"message": "Your account has been deleted. You are signed out."}


@app.get("/privacy")
def privacy_page() -> HTMLResponse:
    """Privacy policy (both app stores need a link to it). SUPPORT_EMAIL in .env / Azure settings is the contact."""
    email = subscriptions.setting("SUPPORT_EMAIL", "").strip()
    contact = (
        f'<a href="mailto:{html.escape(email)}">{html.escape(email)}</a>'
        if email
        else "your club admin, who passes it to the CricketCanClubs team"
    )
    text = (STATIC_DIR / "privacy.html").read_text(encoding="utf-8").replace("{{CONTACT}}", contact)
    return HTMLResponse(text, headers={"Cache-Control": "no-cache"})


@app.get("/pricing")
def pricing_page(request: Request) -> Response:
    # Launch mode: the page is shown with "free during the launch" (Dhruvika, Oct 29 2026); before it redirected Home.
    token = _auth_token_from_request(request)
    if token:
        try:
            _auth_user_from_token(token, touch=False)
            return _page_response("pricing.html")
        except HTTPException:
            pass
    return _page_response("pricing_public.html")


@app.get("/api/plans")
def plans_catalog() -> dict[str, Any]:
    return subscriptions.public_catalog()


@app.get("/api/subscription/me")
def subscription_me(x_auth_token: str | None = Header(default=None)) -> dict[str, Any]:
    user_row, current_club_id = _auth_user_from_token(x_auth_token, touch=False)
    plan = _plan_for(user_row, current_club_id)
    is_superadmin = "superadmin" in _user_role_names(user_row, current_club_id)
    return {
        "subscription": plan,
        "club_paid": _club_is_paid(current_club_id),
        "is_site_admin": is_superadmin,
        **subscriptions.public_catalog(),
    }


@app.post("/api/subscription/checkout")
def subscription_checkout(request: CheckoutRequest, http_request: Request, x_auth_token: str | None = Header(default=None)) -> dict[str, Any]:
    user_row, current_club_id = _auth_user_from_token(x_auth_token)
    plan = subscriptions.normalize_plan(request.plan)
    interval = subscriptions.normalize_interval(request.interval)
    if not subscriptions.subscriptions_on():
        raise HTTPException(status_code=400, detail="Pro is free for everyone during the launch, so there's nothing to pay.")
    if plan != "pro":
        raise HTTPException(status_code=400, detail="Choose Pro (monthly or yearly).")
    if not subscriptions.stripe_enabled():
        raise HTTPException(
            status_code=503,
            detail="Online payment isn't switched on yet. Ask your site admin to upgrade your plan, or try again later.",
        )
    customer_id = ""
    with _auth_connection() as connection:
        row = connection.execute("SELECT stripe_customer_id FROM app_subscriptions WHERE user_id = ?", (int(user_row["id"]),)).fetchone()
        customer_id = str(row["stripe_customer_id"] or "") if row else ""
    try:
        url = subscriptions.create_checkout_session(user_row, plan, str(http_request.base_url), customer_id, interval)
    except subscriptions.StripeError as exc:
        raise HTTPException(status_code=502, detail=str(exc))
    _audit_event("subscription.checkout", "subscription", str(user_row["id"]), actor=user_row, club_id=current_club_id, details={"plan": plan, "interval": interval}, source="api")
    return {"url": url}


@app.post("/api/subscription/portal")
def subscription_portal(http_request: Request, x_auth_token: str | None = Header(default=None)) -> dict[str, Any]:
    user_row, _ = _auth_user_from_token(x_auth_token)
    if not subscriptions.stripe_enabled():
        raise HTTPException(status_code=503, detail="Online payment isn't switched on yet.")
    with _auth_connection() as connection:
        row = connection.execute("SELECT stripe_customer_id FROM app_subscriptions WHERE user_id = ?", (int(user_row["id"]),)).fetchone()
    customer_id = str(row["stripe_customer_id"] or "") if row else ""
    if not customer_id:
        raise HTTPException(status_code=400, detail="There's no card on file yet. Choose a plan first.")
    try:
        return {"url": subscriptions.create_portal_session(customer_id, str(http_request.base_url))}
    except subscriptions.StripeError as exc:
        raise HTTPException(status_code=502, detail=str(exc))


@app.post("/api/stripe/webhook")
async def stripe_webhook(request: Request) -> dict[str, Any]:
    payload = await request.body()
    try:
        event = subscriptions.verify_webhook(payload, request.headers.get("stripe-signature", ""))
    except subscriptions.StripeError as exc:
        logger.warning("Stripe webhook rejected: %s", exc)
        raise HTTPException(status_code=400, detail=str(exc))
    with _auth_connection() as connection:
        result = subscriptions.handle_stripe_event(connection, event)
    logger.info("Stripe webhook %s -> %s", event.get("type"), result)
    return result


def _find_user_for_admin(connection: sqlite3.Connection, identifier: str) -> sqlite3.Row | None:
    clean = str(identifier or "").strip()
    if not clean:
        return None
    if clean.isdigit() and len(clean) < 7:
        row = connection.execute("SELECT * FROM app_users WHERE id = ?", (int(clean),)).fetchone()
        if row:
            return row
    for candidate in _auth_identifier_candidates(clean):
        row = connection.execute("SELECT * FROM app_users WHERE mobile = ? OR lower(email) = lower(?)", (candidate, candidate)).fetchone()
        if row:
            return row
    rows = connection.execute("SELECT * FROM app_users WHERE lower(display_name) = lower(?)", (clean,)).fetchall()
    return rows[0] if len(rows) == 1 else None


@app.get("/api/admin/subscriptions")
def admin_subscriptions(x_auth_token: str | None = Header(default=None)) -> dict[str, Any]:
    _require_superadmin(x_auth_token)
    with _auth_connection() as connection:
        users = connection.execute("SELECT * FROM app_users ORDER BY display_name COLLATE NOCASE").fetchall()
        rows = []
        counts = {"free": 0, "pro": 0}
        for user_row in users:
            plan = subscriptions.effective_plan(connection, user_row, [str(user_row["role"] or "")])
            counts[plan["plan"]] = counts.get(plan["plan"], 0) + 1
            rows.append(
                {
                    "id": int(user_row["id"]),
                    "name": user_row["display_name"] or "",
                    "role": user_row["role"] or "",
                    "plan": plan["plan_name"],
                    "source": plan["source"],
                    "period_end": plan["period_end"],
                    "uploads_used": plan["uploads_used"],
                }
            )
    return {"users": rows, "counts": counts, "stripe_enabled": subscriptions.stripe_enabled()}


@app.post("/api/admin/subscriptions/set")
def admin_set_subscription(request: AdminSetPlanRequest, x_auth_token: str | None = Header(default=None)) -> dict[str, Any]:
    admin_row, current_club_id = _require_superadmin(x_auth_token)
    plan = subscriptions.LEGACY_PLANS.get(str(request.plan or "").strip().lower(), str(request.plan or "").strip().lower())
    if plan not in subscriptions.PLANS:
        raise HTTPException(status_code=400, detail="Plan must be free or pro.")
    with _auth_connection() as connection:
        target = _find_user_for_admin(connection, request.user)
        if not target:
            raise HTTPException(status_code=404, detail="No single user matches that name, mobile, email or id.")
        period_end = datetime.now(timezone.utc) + timedelta(days=int(request.days)) if request.days and request.days > 0 else None
        subscriptions.set_plan(
            connection,
            target,
            plan,
            source="admin" if plan != "free" else "free",
            status="active",
            period_end=period_end,
            note=request.note.strip() or f"Set by {admin_row['display_name'] or 'site admin'}",
        )
        info = subscriptions.effective_plan(connection, target, [str(target["role"] or "")])
    _audit_event(
        "subscription.admin_set",
        "subscription",
        str(target["id"]),
        actor=admin_row,
        club_id=current_club_id,
        details={"plan": plan, "days": request.days, "user": target["display_name"] or ""},
        source="api",
    )
    until = f" until {info['period_end'][:10]}" if info.get("period_end") else ""
    return {"message": f"{target['display_name'] or 'User'} is now on {info['plan_name']}{until}.", "subscription": info}


@app.post("/api/matches/{match_id}/ai-scorer")
def ai_live_scorer(match_id: str, request: AiScorerRequest, x_auth_token: str | None = Header(default=None)) -> dict[str, Any]:
    """Pro AI Live Scorer (or a Free user's one free AI match): phrase -> validated ball events. The client posts each event to /scorebook/ball."""
    user_row, current_club_id = _require_match_scorer(x_auth_token, match_id)
    if not _ai_allowed(user_row, current_club_id, "ai_live_scorer", match_id):
        raise _upgrade_error("ai_live_scorer")
    store = load_store()
    try:
        match = get_match_or_404(store, match_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    if not _scorebook_is_open(match):
        raise HTTPException(status_code=400, detail="Live scoring is only open on match day.")
    scorebook = _match_scorebook(match)
    innings_index = max(1, min(2, int(request.innings_number or 1))) - 1
    innings = scorebook["innings"][innings_index]
    summary = summarize_innings_scorebook(innings)
    parsed = ai_scorer.interpret(request.text)
    events, problems = ai_scorer.validate(parsed["events"], summary, int(innings.get("overs_limit", 20) or 20), str(innings.get("status") or ""))
    for event in events:
        event["label"] = ai_scorer.describe(event)
    if parsed["unknown"]:
        problems.append("Didn't understand: " + ", ".join(f"“{item}”" for item in parsed["unknown"][:3]))
    before = f"{summary['runs']}/{summary['wickets']} ({summary['legal_balls'] // 6}.{summary['legal_balls'] % 6})"
    after = events[-1].get("projected", before) if events else before
    return {"heard": parsed["text"], "events": events, "problems": problems, "before": before, "after": after}


@app.get("/api/insights/me")
def insights_me(x_auth_token: str | None = Header(default=None)) -> dict[str, Any]:
    """Signed-in user's own form/prediction/tips plus their current club's outlook."""
    user_row, current_club_id = _auth_user_from_token(x_auth_token)
    store = load_store()
    member = _member_for_user(store, user_row)
    club = cricket_insights.find_club(store, current_club_id)
    if not club and member:
        club = cricket_insights.find_club(store, str(member.get("primary_club_id") or ""))
    features = set(_plan_for(user_row, current_club_id).get("features", []))
    player = cricket_insights.player_insights(store, member) if member else None
    club_info = cricket_insights.club_insights(store, club) if club else None
    locked: list[dict[str, str]] = []

    def lock(feature: str) -> None:
        if not any(item["feature"] == feature for item in locked):
            plan = subscriptions.PLANS[subscriptions.feature_min_plan(feature)]
            locked.append({"feature": feature, "label": subscriptions.FEATURES[feature]["label"], "plan": plan["id"], "plan_name": plan["name"]})

    if "analysis" not in features:
        lock("analysis")
        if player:
            player = {**player, "prediction": None, "recommendations": [], "timeline": []}
        if club_info:
            club_info = {**club_info, "recommendations": []}
    if "match_intelligence" not in features:
        lock("match_intelligence")
        if club_info and club_info.get("next_match"):
            next_match = dict(club_info["next_match"])
            for key in ("win_chance", "confidence", "opponent_known"):
                next_match.pop(key, None)
            club_info = {**club_info, "next_match": next_match}
    best = None
    if club and "playing_xi" in features:
        best = cricket_insights.best_xi(store, club)
    elif club:
        lock("playing_xi")
    outlook = cricket_insights.season_outlook(store, club) if club and "analysis" in features else None
    intelligence = _match_intelligence(store, club, club_info) if club and "match_intelligence" in features else None
    cross_club = _cross_club_stats(store, member) if member and "cross_club_stats" in features else None
    if "cross_club_stats" not in features:
        lock("cross_club_stats")
    return {
        "player": player,
        "club": club_info,
        "best_xi": best,
        "outlook": outlook,
        "match_intelligence": intelligence,
        "cross_club": cross_club,
        "locked": locked,
        "plan": _plan_for(user_row, current_club_id).get("plan", "free"),
        "generated_at": now_iso(),
    }


@app.get("/api/insights/player/{player_key}")
def insights_player(player_key: str, x_auth_token: str | None = Header(default=None)) -> dict[str, Any]:
    _auth_user_from_token(x_auth_token)
    store = load_store()
    member = cricket_insights.find_member(store, player_key)
    if not member:
        raise HTTPException(status_code=404, detail="Player not found.")
    return {"player": cricket_insights.player_insights(store, member), "generated_at": now_iso()}


@app.get("/api/insights/club/{club_key}")
def insights_club(club_key: str, x_auth_token: str | None = Header(default=None)) -> dict[str, Any]:
    _auth_user_from_token(x_auth_token)
    store = load_store()
    club = cricket_insights.find_club(store, club_key)
    if not club:
        raise HTTPException(status_code=404, detail="Club not found.")
    return {"club": cricket_insights.club_insights(store, club), "generated_at": now_iso()}


@app.post("/api/chat")
def chat(request: ChatRequest, x_auth_token: str | None = Header(default=None)) -> dict[str, Any]:
    # Plans: predictions, tips, best XI and season outlook are Pro analysis (README.md -> "Subscriptions and plans").
    if x_auth_token and re.search(
        r"\b(predict|prediction|forecast|projected|improve|improvement|tips?|advice|playing xi|best xi|playing 11|season outlook|outlook|win chance|chances? of)\b",
        str(request.question or "").lower(),
    ):
        try:
            chat_user, chat_club = _auth_user_from_token(x_auth_token, touch=False)
        except HTTPException:
            chat_user = None
        if chat_user is not None and not _has_feature(chat_user, chat_club, "analysis"):
            return {
                "answer": "Predictions, improvement tips, best XI and season outlook are part of Pro ($9 a month or $90 a year). On Free you can still ask about stats, results, rankings and scorecards. See Plans to upgrade.",
                "source": "plans",
                "links": [{"label": "See plans", "href": "/pricing?feature=analysis"}],
            }
    store = load_store()
    focus_club = next((club for club in store.get("clubs", []) if club.get("id") == request.focus_club_id), store.get("club", {}))
    focused_store = scoped_store_for_club(store, focus_club) if request.focus_club_id else dict(store)
    chat_store = dict(focused_store)
    chat_store["focus_club_id"] = str(request.focus_club_id or "").strip()
    chat_store["focus_club"] = dict(focus_club or {})
    chat_store["all_clubs"] = list(store.get("clubs", []) or [])
    chat_store["all_members"] = list(store.get("members", []) or [])
    chat_store["all_fixtures"] = list(store.get("fixtures", []) or [])
    chat_store["all_archive_uploads"] = list(store.get("archive_uploads", []) or [])
    chat_store["all_teams"] = list(store.get("teams", []) or [])
    chat_store["all_member_summary_stats"] = list(store.get("member_summary_stats", []) or [])
    chat_store["all_member_year_stats"] = list(store.get("member_year_stats", []) or [])
    chat_store["all_member_club_stats"] = list(store.get("member_club_stats", []) or [])
    chat_store["all_club_summary_stats"] = list(store.get("club_summary_stats", []) or [])
    chat_store["all_club_year_stats"] = list(store.get("club_year_stats", []) or [])
    return answer_question(request.question, chat_store, history=request.history, session_id=request.session_id)


@app.get("/api/llm/status")
def llm_status() -> dict[str, Any]:
    store = load_store()
    status = get_llm_status()
    status["chat_provider"] = ai_chat.provider()  # "gemini" / "claude" / "" (README "AI Assistant answers (Gemini)")
    status["prompt_count"] = len(list_prompt_manifest())
    status["document_count"] = len(list_llm_documents(store))
    return status


@app.get("/api/llm/prompts")
def llm_prompts() -> dict[str, Any]:
    return {"prompts": list_prompt_manifest()}


@app.get("/api/llm/documents")
def llm_documents(
    doc_type: str = "",
    club_id: str = "",
    query: str = "",
    limit: int = 100,
) -> dict[str, Any]:
    store = load_store()
    docs = list_llm_documents(store, doc_type=doc_type, club_id=club_id, query=query, limit=limit)
    return {
        "documents": docs,
        "count": len(docs),
    }


@app.post("/api/llm/reindex")
def llm_reindex(x_auth_token: str | None = Header(default=None)) -> dict[str, Any]:
    user_row, _ = _require_permission(x_auth_token, "manage_scorecards")
    store = load_store()
    documents = reindex_llm_corpus(store)
    return {
        "message": "LLM corpus rebuilt from READMELLM.md, clubs, members, fixtures, and archive scorecards.",
        "documents_indexed": len(documents),
        "prompt_count": len(list_prompt_manifest()),
        "updated_at": now_iso(),
        "requested_by": user_row.get("display_name") or user_row.get("mobile") or "",
    }


@app.post("/api/llm/cache/clear")
def llm_clear_cache(x_auth_token: str | None = Header(default=None)) -> dict[str, Any]:
    user_row, _ = _auth_user_from_token(x_auth_token)
    cleared = clear_query_cache()
    return {
        "message": "LLM chat history and cached answers were cleared.",
        "cleared_entries": cleared,
        "updated_at": now_iso(),
        "requested_by": user_row["display_name"] or user_row["mobile"] or "",
    }


@app.post("/api/llm/infer")
def llm_infer_endpoint(request: LLMInferRequest) -> dict[str, Any]:
    store = load_store()
    focus_club_id = str(request.focus_club_id or "").strip()
    result = llm_infer(
        request.question,
        store=store,
        focus_club_id=focus_club_id,
        mode=request.mode,
        prompt_name=request.prompt_name,
        template_args=request.template_args,
        history=request.history,
        limit=request.limit,
    )
    return {
        "question": request.question,
        "focus_club_id": focus_club_id,
        "result": result,
    }


@app.post("/api/archive/reset-scores")
def reset_scores(x_auth_token: str | None = Header(default=None)) -> dict[str, Any]:
    user_row, _ = _require_permission(x_auth_token, "manage_scorecards")
    store = load_store()
    reset_score_data(store)
    for match in store.get("fixtures", []):
        _touch_fixture_audit(match, user_row)
    save_store(store)
    return {
        "message": "Confirmed player scores and archive extraction drafts were reset. You can now process scorecards one at a time.",
        "dashboard": current_dashboard(load_store()),
    }


@app.post("/api/archive/{upload_id}/extract")
def extract_archive(upload_id: str, focus_club_id: str | None = None, x_auth_token: str | None = Header(default=None)) -> dict[str, Any]:
    user_row, current_club_id = _require_permission(x_auth_token, "manage_scorecards")
    logger.debug("Archive re-extract requested. upload_id=%s focus_club_id=%s", upload_id, focus_club_id or "")
    store = load_store()
    # Re-extract reads the photo with the AI vision model first (handwriting included; README "Re-extract
    # uses the AI reader"), then falls back to the basic Tesseract reader when AI is off or fails.
    reader_note = ""
    try:
        upload = get_archive_or_404(store, upload_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    photo = _upload_file_path(upload)
    ai_done = False
    if photo is None:
        reader_note = " The original photo isn't in app/uploads, so it couldn't be read again."
    elif ai_vision.enabled():
        club = _selected_club(store, str(upload.get("club_id") or focus_club_id or current_club_id or ""))
        reason = _scorecard_ai_read(store, upload, photo, club)
        if reason:
            reader_note = f" AI reading didn't work ({reason}); used the basic reader instead."
        else:
            ai_done = True
            upload["status"] = "Pending review"
            upload["review_flags"] = []
    else:
        reader_note = " AI reading is off, so the basic reader was used (it can't read handwriting). Add a free GEMINI_API_KEY to .env and restart."
    if not ai_done:
        try:
            extract_archive_by_id(store, upload_id)
        except ValueError as exc:
            logger.error("Archive re-extract failed. upload_id=%s error=%s", upload_id, exc)
            raise HTTPException(status_code=404, detail=str(exc))
    save_store(store)
    refreshed = load_store()
    extracted = get_archive_or_404(refreshed, upload_id)
    if ai_done:
        checks = _scorecard_upload_checks(refreshed, extracted)
        save_store(refreshed)
        refreshed = load_store()
        extracted = get_archive_or_404(refreshed, upload_id)
        reader_note = f" Read by AI ({ai_vision.provider()}). Check it against the photo, then Approve." + (
            f" {len(checks['flags'])} thing(s) to check." if checks.get("flags") else ""
        )
    _audit_event(
        "archive.extract",
        "archive_upload",
        upload_id,
        actor=user_row,
        club_id=str(extracted.get("club_id") or focus_club_id or current_club_id or ""),
        club_name=str(extracted.get("club_name") or ""),
        details={
            "file_name": extracted.get("file_name") or "",
            "status": extracted.get("status") or "",
        },
        source="api",
    )
    return {
        "message": f"Processed {extracted['file_name']}.{reader_note}",
        "archive": extracted,
        "dashboard": current_dashboard(refreshed, focus_club_id or extracted.get("club_id")),
    }


@app.post("/api/archive/{upload_id}/import-extraction")
def import_archive_extraction(upload_id: str, request: ArchiveImportRequest, focus_club_id: str | None = None, x_auth_token: str | None = Header(default=None)) -> dict[str, Any]:
    user_row, current_club_id = _require_permission(x_auth_token, "manage_scorecards")
    logger.debug("Archive import requested. upload_id=%s focus_club_id=%s text_len=%s", upload_id, focus_club_id or "", len(request.text or ""))
    store = load_store()
    selected_club = _selected_club(store, focus_club_id)
    try:
        upload = get_archive_or_404(store, upload_id)
    except ValueError as exc:
        logger.error("Archive import failed. upload_id=%s error=%s", upload_id, exc)
        raise HTTPException(status_code=404, detail=str(exc))

    upload["club_id"] = upload.get("club_id") or selected_club.get("id", "")
    upload["club_name"] = upload.get("club_name") or selected_club.get("name", "")
    imported = parse_imported_extraction(store, request.text)
    upload.update(imported)
    inferred_club = _resolve_archive_club(upload, store.get("clubs", []))
    if inferred_club:
        upload["club_id"] = inferred_club.get("id", upload.get("club_id", ""))
        upload["club_name"] = inferred_club.get("name", upload.get("club_name", ""))
    upload["ocr_processed_at"] = now_iso()
    upload["status"] = "Pending review"
    save_store(store)
    # Typed-in / pasted scorecards get the same checks as photo uploads (old OCR flags are replaced).
    # Run them on the saved copy, so the digital scorecard is built exactly as it will be shown.
    refreshed = load_store()
    _scorecard_upload_checks(refreshed, get_archive_or_404(refreshed, upload_id))
    save_store(refreshed)
    refreshed = load_store()
    updated = get_archive_or_404(refreshed, upload_id)
    _audit_event(
        "archive.import",
        "archive_upload",
        upload_id,
        actor=user_row,
        club_id=str(updated.get("club_id") or focus_club_id or current_club_id or ""),
        club_name=str(updated.get("club_name") or ""),
        details={
            "file_name": updated.get("file_name") or "",
            "text_length": len(request.text or ""),
        },
        source="api",
    )
    return {
        "message": f"Imported extracted scorecard into {updated['file_name']} for review.",
        "archive": updated,
        "dashboard": current_dashboard(refreshed, focus_club_id or updated.get("club_id")),
    }


@app.post("/api/admin/archive/{upload_id}/review")
def save_archive_review(upload_id: str, request: ArchiveReviewRequest, x_auth_token: str | None = Header(default=None)) -> dict[str, Any]:
    user_row, current_club_id = _require_permission(x_auth_token, "manage_scorecards")
    logger.debug("Archive review saved. upload_id=%s club_id=%s text_len=%s", upload_id, current_club_id or "", len(request.text or ""))
    store = load_store()
    try:
        upload = get_archive_or_404(store, upload_id)
    except ValueError as exc:
        logger.error("Archive review save failed. upload_id=%s error=%s", upload_id, exc)
        raise HTTPException(status_code=404, detail=str(exc))

    club = _selected_club(store, current_club_id)
    upload["club_id"] = upload.get("club_id") or club.get("id", "")
    upload["club_name"] = upload.get("club_name") or club.get("name", "")
    ai_read = _scorecard_json(upload.get("review_source_json")) if upload.get("review_source_json") else None
    _apply_archive_review_text(store, upload, request.text, user_row=user_row)
    try:
        _learn_ai_corrections(str(upload.get("club_id") or ""), ai_read, json.loads(request.text or "{}"))
    except (ValueError, TypeError):
        pass
    save_store(store)
    refreshed = load_store()
    updated = get_archive_or_404(refreshed, upload_id)
    _audit_event(
        "archive.review.save",
        "archive_upload",
        upload_id,
        actor=user_row,
        club_id=str(updated.get("club_id") or club.get("id") or ""),
        club_name=str(updated.get("club_name") or club.get("name") or ""),
        details={
            "file_name": updated.get("file_name") or "",
            "text_length": len(request.text or ""),
            "status": updated.get("status") or "",
        },
        source="api",
    )
    return {
        "message": f"Reviewed draft saved for {updated['file_name']}.",
        "archive": updated,
        "dashboard": current_dashboard(refreshed, club.get("id", "")),
    }


@app.post("/api/admin/archive/{upload_id}/review-form")
def save_archive_review_form(
    request: Request,
    upload_id: str,
    text: str = Form(default=""),
) -> Response:
    try:
        logger.debug("Archive review form submitted. upload_id=%s text_len=%s", upload_id, len(text or ""))
        result = save_archive_review(
            upload_id,
            ArchiveReviewRequest(text=text),
            x_auth_token=_auth_token_from_request(request),
        )
        archive = result.get("archive", {}) if isinstance(result, dict) else {}
        return _redirect_to_admin_center(
            str(archive.get("club_id") or result.get("dashboard", {}).get("club", {}).get("id") or ""),
            result.get("message", "Reviewed extraction saved."),
            "success",
        )
    except HTTPException as exc:
        return _redirect_to_admin_center("", str(exc.detail), "error")


def _mark_single_innings_number(record: dict[str, Any], number: int) -> None:
    """Set the innings number of a one-innings upload in every stored copy of its template."""
    for key in ("review_template_json", "review_source_json"):
        try:
            template = json.loads(str(record.get(key) or "")) if record.get(key) else None
        except Exception:
            template = None
        if isinstance(template, dict) and len(_usable_innings(template)) == 1:
            for item in template.get("innings") or []:
                if isinstance(item, dict) and item in _usable_innings(template):
                    item["inning_number"] = number
            record[key] = json.dumps(template, indent=2)
    template = record.get("extraction_template")
    if isinstance(template, dict) and len(_usable_innings(template)) == 1:
        for item in _usable_innings(template):
            item["inning_number"] = number


@app.post("/api/scorecards/upload")
async def upload_scorecard(
    request: Request,
    match_id: str | None = None,
    season: str | None = None,
    focus_club_id: str | None = None,
    link_match_code: str | None = None,
    innings_number: int | None = None,
    x_auth_token: str | None = Header(default=None),
    file: UploadFile = File(...),
) -> dict[str, Any]:
    token = _auth_token_from_request(request, x_auth_token)
    user_row, upload_club_id = _require_permission(token, "score_matches")
    plan_info = _plan_for(user_row, upload_club_id)
    upload_limit = plan_info.get("upload_limit")
    if upload_limit is not None and int(plan_info.get("uploads_used") or 0) >= int(upload_limit):
        raise HTTPException(
            status_code=402,
            detail=(
                f"You've used all {upload_limit} scorecard image uploads for this month on the {plan_info.get('plan_name', 'Free')} plan. "
                "Upgrade at /pricing for more uploads, or wait until next month."
            ),
        )
    logger.debug("Scorecard upload started. match_id=%s season=%s focus_club_id=%s filename=%s", match_id or "", season or "", focus_club_id or "", file.filename or "")
    store = load_store()
    selected_club = _selected_club(store, focus_club_id)
    related_club_ids = _archive_match_club_ids(store, selected_club.get("id", ""), match_id or "")
    related_clubs = [_club_by_identifier(store.get("clubs", []), club_id) for club_id in related_club_ids]
    related_clubs = [club for club in related_clubs if club]
    related_club_names = [str(club.get("name") or club.get("short_name") or "").strip() for club in related_clubs]
    suffix = Path(file.filename or "scorecard.jpg").suffix or ".jpg"
    content = await file.read()
    incoming_hash = file_sha256_from_bytes(content)
    for existing in store["archive_uploads"]:
        if existing.get("file_hash") == incoming_hash:
            logger.debug("Duplicate scorecard upload rejected. filename=%s hash=%s", file.filename or "", incoming_hash)
            raise HTTPException(
                status_code=409,
                detail=(
                    f"This scorecard image was already uploaded as '{existing.get('file_name', 'an existing file')}'. "
                    "Duplicate uploads are not allowed."
                ),
            )

    fingerprint = scorecard_checks.image_fingerprint(content)
    if fingerprint:
        for existing in store["archive_uploads"]:
            if str(existing.get("status") or "").lower() in {"rejected", "duplicate"}:
                continue
            if not scorecard_checks.is_current_fingerprint(existing.get("image_fingerprint")):
                # an upload from before Nov 7 2026: work out its new-style fingerprint from its photo once
                path = _upload_file_path(existing)
                existing["image_fingerprint"] = scorecard_checks.image_fingerprint(path.read_bytes()) if path is not None else ""
            if not existing.get("image_fingerprint"):
                continue
            if scorecard_checks.fingerprint_distance(fingerprint, str(existing["image_fingerprint"])) <= scorecard_checks.FINGERPRINT_SAME:
                raise HTTPException(
                    status_code=409,
                    detail=(
                        f"This looks like the same photo as '{existing.get('original_file_name') or existing.get('file_name') or 'an earlier upload'}' "
                        f"(uploaded {str(existing.get('created_at') or '')[:10]}). Duplicate uploads are not allowed."
                    ),
                )

    file_token = f"{uuid.uuid4().hex[:10]}{suffix}"
    destination = UPLOAD_DIR / file_token
    destination.write_bytes(content)
    record = archive_record_from_file(
        destination,
        season or selected_club.get("season") or store["club"]["season"],
        match_id=match_id or "",
        source="upload",
        club_id=selected_club.get("id", ""),
        club_name=selected_club.get("name", ""),
        club_ids=related_club_ids,
        club_names=related_club_names,
    )
    record["original_file_name"] = file.filename or file_token
    record["status"] = "Pending review"
    record["image_fingerprint"] = fingerprint
    record["uploaded_by_user_id"] = int(user_row["id"])
    record["uploaded_by"] = str(user_row["display_name"] or "")
    store["archive_uploads"].append(record)
    # Handwritten cards: read the photo with the AI vision model when it is switched on
    # (README: "Reading handwritten scorecards automatically"); otherwise the local reader.
    # Plans (README "Plans: what each group can use"): Pro gets AI reading on every upload; a Free user's
    # first AI reading uses their one free AI try. Otherwise the photo is saved and they type it in.
    ai_note = ""
    if ai_vision.enabled():
        if _ai_allowed(user_row, upload_club_id, "ai_extraction", f"scorecard:{record['id']}"):
            ai_note = _scorecard_ai_read(store, record, destination, selected_club)
        else:
            ai_note = "AI reading of photos is a Pro feature (your free AI try is used)."
            record["ai_flags"] = [ai_note + " Type in the scorecard with ✏️, or upgrade to Pro on /pricing."]
    if not record.get("ocr_processed_at"):
        # No AI: Amit's local reader (OCR + Ollama vision with focused crops, Oct 16).
        record = extract_archive_by_id(store, record["id"])
        if not _is_scorecard_template_payload(record.get("extraction_template")):
            record["extraction_template"] = scorecard_template_from_archive(record)
        record["review_template_json"] = json.dumps(record["extraction_template"], indent=2)
    # Nov 6 2026 (Amit: "should allow if I have only 2nd innings scorecard"): the photo was put in the
    # "2nd innings" box, so its one innings is innings 2 (the 1st innings shows as missing until it's added).
    if innings_number == 2:
        _mark_single_innings_number(record, 2)
    # The other innings of a match already uploaded (by this club or the other team): join them into one scorecard.
    other_half = None
    if link_match_code:
        # the other team gave us their Match ID: link to it when it holds the other innings
        linked = _upload_by_match_code(store, link_match_code)
        mine, theirs = _single_innings(record), (_single_innings(linked) if linked else None)
        if linked is not None and mine and theirs and not (
            mine.get("batting_team") and theirs.get("batting_team") and _same_team_name(mine.get("batting_team"), theirs.get("batting_team"))
        ):
            other_half = linked
    if other_half is None:
        other_half = _find_other_half(store, record)
    if other_half is not None:
        checks = _join_halves(store, other_half, record, user_row)
        save_store(store)
        title = (checks.get("scorecard") or {}).get("title") or "this match"
        return {
            "message": f"This is the other innings of {title} (same date and teams). Both innings are now one scorecard.",
            "dashboard": current_dashboard(load_store(), selected_club.get("id", "")),
            "upload": other_half,
            "joined": True,
            "checks": {key: value for key, value in checks.items() if key != "scorecard"},
            "digital": checks.get("scorecard"),
            "preview_url": f"/scorecards/{other_half.get('id')}?preview=1&joined=1",
        }
    checks = _scorecard_upload_checks(store, record)
    save_store(store)
    logger.debug("Scorecard upload saved. archive_id=%s club_id=%s file=%s", record.get("id", ""), record.get("club_id", ""), record.get("file_name", ""))
    _audit_event(
        "archive.upload",
        "archive_upload",
        str(record.get("id") or ""),
        actor=user_row,
        club_id=str(record.get("club_id") or ""),
        club_name=str(record.get("club_name") or ""),
        details={
            "file_name": record.get("file_name") or "",
            "season": record.get("season") or "",
            "status": record.get("status") or "",
        },
        source="api",
    )
    _scorecard_check_alerts(record, checks, user_row)
    name_matches = _card_name_matches(load_store(), checks.get("scorecard") or {}, user_row, str(selected_club.get("id") or ""))
    name_notice = _name_match_notice(name_matches)
    left = "" if upload_limit is None else f" {max(0, int(upload_limit) - int(plan_info.get('uploads_used') or 0) - 1)} of {upload_limit} uploads left this month."
    if checks["needs_review"]:
        message = f"Scorecard '{record.get('original_file_name') or file.filename or file_token}' uploaded. Some things need checking, so a site admin will review it." + name_notice + left
    else:
        message = f"Scorecard '{record.get('original_file_name') or file.filename or file_token}' uploaded. Check the digital scorecard and tap Publish." + name_notice + left
    return {
                "message": message,
                "dashboard": current_dashboard(load_store(), selected_club.get("id", "")),
                "upload": record,
                "checks": checks,
                "digital": checks.get("scorecard"),
                "name_matches": name_matches,
                "preview_url": f"/scorecards/{record.get('id')}?preview=1",
            }


# ---------------------------------------------------------------------------
# How the AI reader learns (README "How the AI reader learns", Oct 2026)
# When someone fixes a name the AI misread (Edit / "Type in the scorecard"), the wrong -> right pair is
# saved for that club in app_ai_corrections. The next photo read for the club gets those corrections,
# every known player name and the photo date, so the same mistake is fixed automatically.
# ---------------------------------------------------------------------------
def _ai_corrections_table(connection: sqlite3.Connection) -> None:
    connection.execute(
        """CREATE TABLE IF NOT EXISTS app_ai_corrections (
            club_id TEXT NOT NULL,
            kind TEXT NOT NULL DEFAULT 'name',
            wrong TEXT NOT NULL,
            right_value TEXT NOT NULL,
            times INTEGER NOT NULL DEFAULT 1,
            updated_at TEXT NOT NULL,
            PRIMARY KEY (club_id, kind, wrong)
        )"""
    )


# What the AI reader has learned is also kept in app/ai_learning.json, which is committed to git, so every copy of
# the app (Amit's Mac, Azure, a fresh database) reads with the same training (README "How the AI reader learns").
AI_LEARNING_FILE = Path(__file__).resolve().parent / "ai_learning.json"


def _ai_learning() -> dict[str, Any]:
    try:
        data = json.loads(AI_LEARNING_FILE.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _save_ai_learning(club_id: str, pairs: dict[str, str]) -> None:
    data = _ai_learning()
    data.setdefault("about", "Names the AI scorecard reader learned from people's fixes, per club (wrong -> right). Committed to git so every copy of the app uses them. README: How the AI reader learns.")
    club = data.setdefault("corrections", {}).setdefault(club_id, {})
    club.update(pairs)
    data["updated_at"] = now_iso()
    try:
        AI_LEARNING_FILE.write_text(json.dumps(data, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
    except OSError:
        logger.exception("Could not write %s", AI_LEARNING_FILE)


def _ai_corrections(club_id: str) -> dict[str, str]:
    learned = {str(k).lower(): str(v) for k, v in ((_ai_learning().get("corrections") or {}).get(str(club_id or "")) or {}).items()}
    try:
        with _auth_connection() as connection:
            _ai_corrections_table(connection)
            rows = connection.execute(
                "SELECT wrong, right_value FROM app_ai_corrections WHERE club_id = ? AND kind = 'name' ORDER BY times DESC",
                (str(club_id or ""),),
            ).fetchall()
        learned.update({str(row["wrong"]): str(row["right_value"]) for row in rows})
    except Exception:
        logger.exception("Could not read AI corrections")
    return learned


def _template_names(template: Any) -> list[list[tuple[str, int, str]]]:
    """Per innings: (section, row number, name) for every batting and bowling row."""
    out: list[list[tuple[str, int, str]]] = []
    if not isinstance(template, dict):
        return out
    for inn in template.get("innings") or []:
        rows: list[tuple[str, int, str]] = []
        if isinstance(inn, dict):
            for section in ("batting", "bowling"):
                for number, row in enumerate(inn.get(section) or []):
                    player = row.get("player") if isinstance(row, dict) else None
                    name = (player.get("name") if isinstance(player, dict) else None) or (row.get("name") if isinstance(row, dict) else None)
                    if name:
                        rows.append((section, number, " ".join(str(name).split())))
        out.append(rows)
    return out


def _learn_ai_corrections(club_id: str, old_template: Any, new_template: Any) -> list[tuple[str, str]]:
    """Compare what the AI read with what a person saved; remember names that were fixed (same innings,
    same row, similar spelling). Returns the (wrong, right) pairs saved."""
    if not club_id or not isinstance(old_template, dict) or not isinstance(new_template, dict):
        return []
    import difflib

    pairs: dict[str, str] = {}
    for old_rows, new_rows in zip(_template_names(old_template), _template_names(new_template)):
        new_by_slot = {(section, number): name for section, number, name in new_rows}
        for section, number, wrong in old_rows:
            right = new_by_slot.get((section, number))
            if not right or right.lower() == wrong.lower():
                continue
            if difflib.SequenceMatcher(None, wrong.lower(), right.lower()).ratio() >= 0.5:
                pairs[wrong.lower()] = right
    if not pairs:
        return []
    try:
        with _auth_connection() as connection:
            _ai_corrections_table(connection)
            for wrong, right in pairs.items():
                connection.execute(
                    """INSERT INTO app_ai_corrections (club_id, kind, wrong, right_value, times, updated_at)
                       VALUES (?, 'name', ?, ?, 1, ?)
                       ON CONFLICT(club_id, kind, wrong) DO UPDATE SET right_value = excluded.right_value,
                       times = app_ai_corrections.times + 1, updated_at = excluded.updated_at""",
                    (club_id, wrong, right, now_iso()),
                )
        logger.info("AI reader learned %s name fix(es) for club %s: %s", len(pairs), club_id, pairs)
        _save_ai_learning(club_id, pairs)
    except Exception:
        logger.exception("Could not save AI corrections")
        return []
    return list(pairs.items())


def _ai_known_names(store: dict[str, Any], club: dict[str, Any]) -> list[str]:
    """Roster names + their aliases + names on this club's published scorecards (players from other teams too)."""
    club_id = str((club or {}).get("id") or "")
    names: set[str] = set()
    for member in store.get("members", []) or []:
        ids = {str(item.get("club_id") or "") for item in member.get("club_memberships") or [] if isinstance(item, dict)}
        ids.add(str(member.get("primary_club_id") or ""))
        if club_id in ids:
            aliases = member.get("aliases") or []
            if isinstance(aliases, str):
                aliases = aliases.split(",")
            names.update(str(alias).strip() for alias in aliases if str(alias).strip())
    for upload in store.get("archive_uploads", []) or []:
        # Nov 7 2026: every published card this club played in (it can be the other team's upload)
        card_clubs = {str(upload.get("club_id") or "")} | {str(item) for item in upload.get("club_ids") or []}
        if club_id not in card_clubs or str(upload.get("status") or "").lower() not in {"approved", "published"}:
            continue
        template = upload.get("extraction_template")
        if not isinstance(template, dict):
            template = _scorecard_json(upload.get("review_template_json")) if upload.get("review_template_json") else None
        for rows in _template_names(template):
            names.update(name for _, _, name in rows)
    names.update(str(name) for name in ((_ai_learning().get("known_names") or {}).get(club_id) or []) if str(name).strip())
    return sorted(names, key=str.lower)[:400]


def _ai_aliases(store: dict[str, Any], club: dict[str, Any]) -> dict[str, list[str]]:
    """{registered name: [other spellings]} for this club's players (their aliases and full name)."""
    club_id = str((club or {}).get("id") or "")
    found: dict[str, list[str]] = {}
    roster = _club_roster(store, club_id) if club_id else []
    first_names: dict[str, int] = {}
    for member in roster:
        first = normalize_name(str(member.get("name") or "")).split(" ")[0]
        first_names[first] = first_names.get(first, 0) + 1
    for member in roster:
        name = str(member.get("name") or "").strip()
        raw = member.get("aliases") or []
        if isinstance(raw, str):
            raw = raw.split(",")
        # a bare first name two players share ("Amit": Amit S and Amit G) is never given as one player's spelling
        others = [
            str(item).strip() for item in [*raw, member.get("full_name")]
            if str(item or "").strip() and normalize_name(str(item)) != normalize_name(name)
            and not (" " not in normalize_name(str(item)) and first_names.get(normalize_name(str(item)), 0) > 1)
        ]
        if name and others:
            found[name] = list(dict.fromkeys(others))
    return found


def _ai_other_clubs(store: dict[str, Any], club: dict[str, Any]) -> dict[str, list[str]]:
    """{club name: player names} for the clubs this club has played (most games first), so the other team's
    batters and bowlers are read as their registered players too."""
    club_id = str((club or {}).get("id") or "")
    if not club_id:
        return {}
    counts: dict[str, int] = {}
    for upload in store.get("archive_uploads", []) or []:
        ids = {str(upload.get("club_id") or "")} | {str(item) for item in upload.get("club_ids") or []}
        if club_id in ids:
            for other in ids - {club_id, ""}:
                counts[other] = counts.get(other, 0) + 1
    for fixture in store.get("fixtures", []) or []:
        if str(fixture.get("club_id") or "") == club_id:
            other = _find_club_by_name(store, str(fixture.get("opponent") or ""))
            if other and str(other.get("id") or "") != club_id:
                counts[str(other["id"])] = counts.get(str(other["id"]), 0) + 1
    result: dict[str, list[str]] = {}
    clubs = {str(item.get("id") or ""): item for item in store.get("clubs", []) or [] if isinstance(item, dict)}
    for other_id, _count in sorted(counts.items(), key=lambda item: -item[1])[:6]:
        other = clubs.get(other_id)
        names = sorted({str(member.get("name") or "").strip() for member in _club_roster(store, other_id)} - {""}, key=str.lower)
        if other and names:
            result[str(other.get("name") or other_id)] = names
    return result


def _photo_date(record: dict[str, Any]) -> str:
    """When the photo was really taken, or "" if we don't know. Order: a date in the phone's file name
    ("WhatsApp Image 2026-10-18 at ...", "IMG_20261018_..."), the camera date, then the upload time for photos
    uploaded in the app. A file's "modified" time on a computer is not used (old photos copied later)."""
    name = str(record.get("original_file_name") or "")
    found = re.search(r"(20\d{2})[-_]?(\d{2})[-_]?(\d{2})", name)
    if found:
        try:
            return date.fromisoformat(f"{found.group(1)}-{found.group(2)}-{found.group(3)}").isoformat()
        except ValueError:
            pass
    taken = str(record.get("photo_taken_at") or "")[:10]
    if taken and str(record.get("photo_date_source") or "") != "filesystem-modified" and re.match(r"^\d{4}-\d{2}-\d{2}$", taken):
        return taken
    created = str(record.get("created_at") or "")[:10]
    imported = str(record.get("uploaded_by") or "").startswith("Re-read script")  # old photos added from img/
    if str(record.get("source") or "") == "upload" and not imported and re.match(r"^\d{4}-\d{2}-\d{2}$", created):
        return created
    return ""


def _scorecard_ai_read(store: dict[str, Any], record: dict[str, Any], path: Path, club: dict[str, Any]) -> str:
    """Fill `record` from the AI vision model. Returns "" on success, else the reason it didn't work."""
    roster = _club_member_names(store, club) if club else []
    result = ai_vision.read_scorecard(
        Path(path),
        roster=roster,
        club_name=str((club or {}).get("name") or ""),
        known_names=_ai_known_names(store, club) if club else [],
        corrections=_ai_corrections(str((club or {}).get("id") or record.get("club_id") or "")),
        photo_date=_photo_date(record),
        aliases=_ai_aliases(store, club) if club else {},
        other_clubs=_ai_other_clubs(store, club) if club else {},
    )
    template = result.get("template")
    if not template:
        logger.warning("AI scorecard read skipped for %s: %s", record.get("id"), result.get("error"))
        return str(result.get("error") or "AI reading failed.")
    # A card photographed on two pages (Amit, Nov 2): read the 2nd innings photo too and join them.
    second = _second_photo_path(record)
    if second is not None and _template_innings_count(template) < 2:
        second_result = _read_photo_with_ai(store, record, second, club)
        if second_result.get("template"):
            template = _join_innings_photos(template, second_result["template"])
    return _apply_ai_template(store, record, template, result)


def _read_photo_with_ai(store: dict[str, Any], record: dict[str, Any], path: Path, club: dict[str, Any]) -> dict[str, Any]:
    return ai_vision.read_scorecard(
        Path(path),
        roster=_club_member_names(store, club) if club else [],
        club_name=str((club or {}).get("name") or ""),
        known_names=_ai_known_names(store, club) if club else [],
        corrections=_ai_corrections(str((club or {}).get("id") or record.get("club_id") or "")),
        photo_date=_photo_date(record),
        aliases=_ai_aliases(store, club) if club else {},
        other_clubs=_ai_other_clubs(store, club) if club else {},
    )


def _innings_has_play(innings: dict[str, Any]) -> bool:
    summary = innings.get("summary") or {}
    return bool(innings.get("batting") or innings.get("bowling") or summary.get("runs") not in (None, "", 0))


def _innings_has_detail(innings: dict[str, Any]) -> bool:
    """An innings with its batting written out (not only a total copied from the other team's page)."""
    def name(row: Any) -> str:
        if not isinstance(row, dict):
            return ""
        player = row.get("player")
        return str((player.get("name") if isinstance(player, dict) else player) or row.get("name") or row.get("player_name") or row.get("batter") or "").strip()

    return any(name(row) for row in innings.get("batting") or [])


def _usable_innings(template: dict[str, Any] | None) -> list[dict[str, Any]]:
    """The innings that count. Nov 2 2026 (Dhruvika): each team's page often has its own innings written out and
    only the other team's TOTAL (e.g. "Amit CC 207/7" + "Heartlake 204"); then only the written-out innings count."""
    played = [item for item in (template or {}).get("innings") or [] if isinstance(item, dict) and _innings_has_play(item)]
    detailed = [item for item in played if _innings_has_detail(item)]
    return detailed if detailed else played


def _template_innings_count(template: dict[str, Any] | None) -> int:
    """How many innings a scorecard template really has (an empty 2nd innings block or a copied total doesn't count)."""
    return len(_usable_innings(template))


def _join_innings_photos(first: dict[str, Any], second: dict[str, Any]) -> dict[str, Any]:
    """Join a card read from two photos: the 1st photo's innings + the other team's innings from the 2nd photo."""
    joined = deepcopy(first)
    kept = [deepcopy(item) for item in _usable_innings(joined)]
    taken = {_team_key_text(item.get("batting_team")) for item in kept}
    extra = [deepcopy(item) for item in _usable_innings(second)]
    # the innings of the team that hasn't batted yet; if the reader didn't name the teams, the first one read
    pick = next((item for item in extra if not any(_same_team_name(item.get("batting_team"), team) for team in taken if team)), None)
    if pick is None and extra and not all(_team_key_text(item.get("batting_team")) for item in extra):
        pick = extra[0]
    if pick is None:
        return joined
    teams = (joined.get("match") or {}).get("teams") or {}
    names = [str(teams.get("team_1") or ""), str(teams.get("team_2") or "")]
    if kept:
        first_bat = str(kept[0].get("batting_team") or "")
        first_bowl = str(kept[0].get("bowling_team") or "")
        pick["batting_team"] = pick.get("batting_team") or first_bowl or next((n for n in names if n and n != first_bat), "")
        pick["bowling_team"] = pick.get("bowling_team") or first_bat
    # the page written as the 2nd innings ("HEARTLAKE (2nd)") stays 2nd: the other photo's innings goes first
    kept_no = int((kept[0].get("inning_number") if kept else 1) or 1)
    pick_no = int(pick.get("inning_number") or 0)
    if len(kept) == 1 and kept_no == 2 and pick_no != 2:
        pick["inning_number"] = 1
        joined["innings"] = [pick] + kept
    else:
        pick["inning_number"] = len(kept) + 1
        joined["innings"] = kept + [pick]
    # fill in match details the 1st photo didn't have (the 2nd page often has the result)
    match = joined.setdefault("match", {})
    for key, value in ((second.get("match") or {}).items()):
        if value not in (None, "", {}, []) and match.get(key) in (None, "", {}, []):
            match[key] = value
    # the result is usually written on only one of the two pages
    validation = joined.setdefault("validation", {}) if isinstance(joined.get("validation"), dict) or "validation" not in joined else {}
    for key, value in ((second.get("validation") or {}).items() if isinstance(second.get("validation"), dict) else []):
        if key == "expected_result" and value and not validation.get(key):
            validation[key] = value
    if isinstance(validation, dict) and validation:
        joined["validation"] = validation
        joined["validation"]["inning_2_total"] = (pick.get("summary") or {}).get("runs")
    joined.setdefault("meta", {})["second_photo"] = True
    return joined


def _canonical_team_names(store: dict[str, Any], template: dict[str, Any]) -> None:
    """Use the registered club's name for a team written a little differently ("Hearthlake" -> "Heartlake Cricket Club")."""
    clubs = [club for club in store.get("clubs", []) or [] if isinstance(club, dict) and club.get("name")]

    def fix(name: Any) -> Any:
        text = str(name or "").strip()
        if not text:
            return name
        club = next((club for club in clubs if _same_team_name(text, club.get("name")) or _same_team_name(text, club.get("short_name"))), None)
        return str(club["name"]) if club else name

    teams = (template.get("match") or {}).get("teams")
    if isinstance(teams, dict):
        for key in list(teams):
            teams[key] = fix(teams[key])
    for innings in template.get("innings") or []:
        if isinstance(innings, dict):
            innings["batting_team"] = fix(innings.get("batting_team"))
            innings["bowling_team"] = fix(innings.get("bowling_team"))


def _team_key_text(name: Any) -> str:
    return re.sub(r"[^a-z0-9]", "", str(name or "").lower())


_HALF_STOP_WORDS = {"cricket", "club", "cc", "xi", "the", "and", "of", "team", "community", "sports", "academy"}


def _name_words(name: Any) -> set[str]:
    return {word for word in re.findall(r"[a-z0-9]+", str(name or "").lower()) if word not in _HALF_STOP_WORDS and len(word) > 1}


def _same_team_name(a: Any, b: Any) -> bool:
    if _team_key_text(a) and _team_key_text(a) == _team_key_text(b):
        return True
    words_a, words_b = _name_words(a), _name_words(b)
    if words_a and words_b and (words_a <= words_b or words_b <= words_a):
        return True
    # handwriting misreads: "Hearthlake" / "Heartcake" = "Heartlake" (Nov 3 2026)
    if words_a and words_b:
        from difflib import SequenceMatcher

        joined_a, joined_b = " ".join(sorted(words_a)), " ".join(sorted(words_b))
        if min(len(joined_a), len(joined_b)) >= 5 and SequenceMatcher(None, joined_a, joined_b).ratio() >= 0.8:
            return True
    return False


def _single_innings(upload: dict[str, Any]) -> dict[str, Any] | None:
    """The one innings of an upload that has exactly one innings (else None)."""
    usable = _usable_innings(_scorecard_pick_template(upload) or {})
    return usable[0] if len(usable) == 1 else None


def _halves_match(record: dict[str, Any], other: dict[str, Any]) -> bool:
    """Two uploads that are the two innings of one match: same date, same two teams, the same venue when both
    name one, and a different batting team in each (the same batting team twice is a duplicate, not a half)."""
    mine, theirs = _single_innings(record), _single_innings(other)
    if not mine or not theirs:
        return False
    try:
        card_a, card_b = _scorecard_from_archive(record), _scorecard_from_archive(other)
    except Exception:
        return False
    if not card_a.get("date") or card_a.get("date") != card_b.get("date"):
        return False
    teams_a = [team for team in card_a.get("teams") or [] if str(team or "").strip()]
    teams_b = [team for team in card_b.get("teams") or [] if str(team or "").strip()]
    if len(teams_a) < 2 or len(teams_b) < 2:
        return False
    if not all(any(_same_team_name(a, b) for b in teams_b) for a in teams_a[:2]):
        return False
    # the venue is often written differently on the two pages ("Save Max" / "Dixie" for the same ground), so it
    # doesn't block a join; date + both teams + a different batting side decide (Nov 3 2026, Amit's two pages)
    bat_a, bat_b = mine.get("batting_team"), theirs.get("batting_team")
    if bat_a and bat_b and _same_team_name(bat_a, bat_b):
        return False
    return True


def _same_innings(record: dict[str, Any], other: dict[str, Any]) -> bool:
    """True when the two uploads hold the same innings (same batting side and the same total or mostly the same
    batters): a real duplicate to delete, as opposed to the other team's innings, which is joined instead."""
    def batters(innings: dict[str, Any]) -> set[str]:
        names = set()
        for row in innings.get("batting") or []:
            player = row.get("player") if isinstance(row, dict) else None
            name = (player.get("name") if isinstance(player, dict) else player) if isinstance(row, dict) else row
            key = normalize_name(str((name or (row.get("name") if isinstance(row, dict) else "")) or ""))
            if key:
                names.add(key)
        return names

    mine = _usable_innings(_scorecard_pick_template(record) or {})
    theirs = _usable_innings(_scorecard_pick_template(other) or {})
    for first in mine:
        for second in theirs:
            bat_a, bat_b = first.get("batting_team"), second.get("batting_team")
            if bat_a and bat_b and not _same_team_name(bat_a, bat_b):
                continue
            runs_a = (first.get("summary") or {}).get("runs")
            runs_b = (second.get("summary") or {}).get("runs")
            if runs_a not in (None, "") and runs_a == runs_b:
                return True
            names_a, names_b = batters(first), batters(second)
            if names_a and names_b and len(names_a & names_b) >= max(2, min(len(names_a), len(names_b)) // 2):
                return True
    return False


def _same_photo(record: dict[str, Any], other: dict[str, Any]) -> bool:
    """The same photo uploaded again (same file hash or fingerprint, or the same file name saved as .jpg/.png/.HEIC
    with no conflicting date)."""
    for key in ("file_hash", "image_fingerprint"):
        if record.get(key) and record.get(key) == other.get(key):
            return True

    def stem(upload: dict[str, Any]) -> str:
        return Path(str(upload.get("original_file_name") or upload.get("file_name") or "").replace("\\", "/")).stem.strip().lower()

    def card_date(upload: dict[str, Any]) -> str:
        return str(upload.get("scorecard_date") or upload.get("archive_date") or ((_scorecard_pick_template(upload) or {}).get("match") or {}).get("date") or "")[:10]

    if not stem(record) or stem(record) != stem(other):
        return False
    date_a, date_b = card_date(record), card_date(other)
    return not date_a or not date_b or date_a == date_b


def _is_duplicate_upload(record: dict[str, Any], other: dict[str, Any]) -> bool:
    return _same_photo(record, other) or _same_innings(record, other)


def _find_other_half(store: dict[str, Any], record: dict[str, Any]) -> dict[str, Any] | None:
    """Amit / Dhruvika, Nov 2 2026: each team may upload its own innings photo (or one team both). Find the
    upload that holds the other innings of this match, so the two are joined into one scorecard."""
    if record.get("second_photo_file") or not _single_innings(record):
        return None
    def quick_date(upload: dict[str, Any]) -> str:
        return str(upload.get("scorecard_date") or upload.get("archive_date") or ((_scorecard_pick_template(upload) or {}).get("match") or {}).get("date") or "")[:10]

    my_date = quick_date(record)
    # newest first: the other team's innings is usually the most recent upload of that match
    for other in reversed(store.get("archive_uploads", []) or []):
        if other is record or str(other.get("id")) == str(record.get("id")):
            continue
        if str(other.get("status") or "").lower() in {"rejected", "duplicate"} or other.get("second_photo_file"):
            continue
        # cheap checks first (the full card is only built for uploads from the same day with one innings)
        if my_date and quick_date(other) and quick_date(other) != my_date:
            continue
        if _halves_match(record, other):
            return other
    return None


def _chasing_side(first_template: dict[str, Any], second_template: dict[str, Any], first_inn: dict[str, Any], second_inn: dict[str, Any]) -> str:
    """Which page's innings was the chase ("first" / "second" / ""): "won by N wickets" = the winner chased,
    "won by N runs" = the winner batted first; with no margin, a winner who scored more in fewer overs chased."""
    result = " ".join(
        str(((template.get("validation") or {}) if isinstance(template.get("validation"), dict) else {}).get("expected_result") or (template.get("match") or {}).get("result") or "")
        for template in (first_template, second_template)
    ).lower()
    if "won" not in result:
        return ""
    team_a, team_b = str(first_inn.get("batting_team") or ""), str(second_inn.get("batting_team") or "")
    winner = ""
    for team, side in ((team_a, "first"), (team_b, "second")):
        words = _name_words(team)
        if words and any(word in result for word in words):
            winner = side if not winner else "both"
    if winner not in {"first", "second"}:
        return ""
    loser = "second" if winner == "first" else "first"
    if "wicket" in result:
        return winner
    if " run" in result:
        return loser
    runs = {side: _scorecard_int((inn.get("summary") or {}).get("runs")) for side, inn in (("first", first_inn), ("second", second_inn))}
    if runs[winner] is not None and runs[loser] is not None and runs[winner] > runs[loser]:
        return winner  # passed the target
    return ""


def _join_halves(store: dict[str, Any], keep: dict[str, Any], half: dict[str, Any], user_row: sqlite3.Row | None) -> dict[str, Any]:
    """Join upload `half` (one innings) into upload `keep` (the other innings): one scorecard with both innings
    and both photos; `half` is removed. Returns the checks of the joined card."""
    first_template = _scorecard_pick_template(keep) or {}
    second_template = _scorecard_pick_template(half) or {}
    # the innings written as innings 1 on its photo goes first
    first_inn, second_inn = _single_innings(keep) or {}, _single_innings(half) or {}
    first_no = int(first_inn.get("inning_number") or 1)
    second_no = int(second_inn.get("inning_number") or 1)
    if first_no == second_no:
        # both pages say "1st" (the reader often misses "(2nd)"): the result decides who batted second
        chaser = _chasing_side(first_template, second_template, first_inn, second_inn)
        if chaser == "first":
            first_no, second_no = 2, 1
        elif chaser == "second":
            first_no, second_no = 1, 2
    if second_no < first_no:
        joined = _join_innings_photos(second_template, first_template)
    else:
        joined = _join_innings_photos(first_template, second_template)
    _canonical_team_names(store, joined)
    was_published = _archive_scorecard_is_published(keep) or _archive_scorecard_is_published(half)
    old_status = keep.get("status") if _archive_scorecard_is_published(keep) else half.get("status")
    _apply_ai_template(
        store,
        keep,
        joined,
        {"model": keep.get("review_llm_model") or "joined", "notes": list(keep.get("ai_flags") or []) + list(half.get("ai_flags") or [])},
    )
    # notes like "Only one innings is on this photo" don't apply to the joined card
    keep["ai_flags"] = [note for note in keep.get("ai_flags") or [] if "one innings" not in str(note).lower()]
    keep["second_photo_file"] = Path(str(half.get("file_path") or half.get("file_name") or "").replace("\\", "/")).name
    keep["second_photo_hash"] = half.get("file_hash") or ""
    keep["second_photo_name"] = half.get("original_file_name") or half.get("file_name") or ""
    keep["second_preview_url"] = half.get("preview_url") or (f"/uploads/{keep['second_photo_file']}" if keep["second_photo_file"] else "")
    keep["second_uploaded_by"] = half.get("uploaded_by") or ""
    keep["joined_upload_id"] = str(half.get("id") or "")
    keep["joined_upload_ids"] = list(dict.fromkeys([*(keep.get("joined_upload_ids") or []), *(half.get("joined_upload_ids") or []), str(half.get("id") or "")]))
    for club_id in half.get("club_ids") or [half.get("club_id")]:
        if club_id and club_id not in (keep.get("club_ids") or []):
            keep["club_ids"] = list(keep.get("club_ids") or []) + [club_id]
    store["archive_uploads"] = [item for item in store.get("archive_uploads", []) or [] if str(item.get("id")) != str(half.get("id"))]
    checks = _scorecard_upload_checks(store, keep)
    if was_published:
        # Nov 3 2026 (Amit: "innings got linked but I can't find the match"): a published card stays published
        # when its other innings is joined; anything the checks found is kept in review_flags for the admins.
        keep["status"] = old_status
        try:
            _register_played_fixture_teams(store)
        except Exception:
            logger.exception("Club registration after joining %s failed", keep.get("id"))
    _audit_event(
        "archive.join_innings",
        "archive_upload",
        str(keep.get("id") or ""),
        actor=user_row,
        club_id=str(keep.get("club_id") or ""),
        details={"joined": str(half.get("id") or "")},
        source="api",
    )
    return checks


def _second_photo_path(record: dict[str, Any]) -> Path | None:
    name = Path(str(record.get("second_photo_file") or "").replace("\\", "/")).name
    if name and (UPLOAD_DIR / name).is_file():
        return UPLOAD_DIR / name
    return None


def _repeated_batting_side_note(template: dict[str, Any]) -> str:
    """Nov 5 2026 (Scarborough Pro vs Heartlake): the reader sometimes gives both innings the same batting team.
    Which page is whose can't be guessed safely (the "Innings of" line decides), so the checker is asked."""
    innings = [item for item in template.get("innings") or [] if isinstance(item, dict)]
    if len(innings) != 2:
        return ""
    first, second = innings
    if first.get("batting_team") and _same_team_name(first.get("batting_team"), second.get("batting_team")) and _same_team_name(first.get("bowling_team"), second.get("bowling_team")):
        return (
            f"Both innings were read as '{first.get('batting_team')}' batting. Check the 'Innings of' line on each photo "
            "and set the right batting team with ✏️ Edit scorecard."
        )
    return ""


def _map_card_names_to_rosters(store: dict[str, Any], template: dict[str, Any]) -> list[str]:
    """Nov 7 2026 (Amit: "AI should try to map it with the existing players of that club so that we have less
    mismatch"): each name read from a card is matched to the registered players of the club on THAT side
    (batters to the batting club, bowlers and fielders to the bowling club): an exact name or alias becomes the
    player's registered name ("Chuck" -> "Checkley"), and a clear one-off misspelling of exactly one player of
    that club is corrected with a note to check. Anything unclear stays as written."""
    import difflib

    notes: list[str] = []
    rosters: dict[str, list[dict[str, Any]]] = {}

    def roster_for(team: Any) -> list[dict[str, Any]]:
        club = _find_club_by_name(store, str(team or "")) if team else None
        if not club:
            return []
        club_id = str(club.get("id") or "")
        if club_id not in rosters:
            rosters[club_id] = _club_roster(store, club_id)
        return rosters[club_id]

    def mapped(name: Any, roster: list[dict[str, Any]]) -> str:
        text = " ".join(str(name or "").split())
        if not text or not roster:
            return text
        low_text = normalize_name(text)
        if " " not in low_text:
            # a bare first name shared by two players of the club ("Amit": Amit S and Amit G) stays as written,
            # even when one of them has it saved as an alias
            sharing = [member for member in roster if normalize_name(str(member.get("name") or "")).split(" ")[0] == low_text]
            if len(sharing) > 1:
                return text
        exact = [member for member in roster if _member_matches_name(member, text)]
        if len(exact) == 1:
            return str(exact[0].get("name") or text)
        if exact:
            return text  # two players of the club fit: leave it for the person checking
        low = normalize_name(text)
        scored = []
        for member in roster:
            best = max((difflib.SequenceMatcher(None, low, key).ratio() for key in _member_identity_keys(member) if key and key[:1] == low[:1] and abs(len(key) - len(low)) <= 2), default=0.0)
            scored.append((best, member))
        scored.sort(key=lambda item: -item[0])
        if scored and scored[0][0] >= 0.85 and (len(scored) == 1 or scored[0][0] - scored[1][0] >= 0.1):
            chosen = str(scored[0][1].get("name") or text)
            if normalize_name(chosen) != low:
                notes.append(f"'{text}' was matched to the club's player '{chosen}'. Check it against the photo.")
            return chosen
        return text

    for innings in template.get("innings") or []:
        if not isinstance(innings, dict):
            continue
        batting_roster, bowling_roster = roster_for(innings.get("batting_team")), roster_for(innings.get("bowling_team"))
        for row in innings.get("batting") or []:
            if not isinstance(row, dict):
                continue
            player = row.get("player") if isinstance(row.get("player"), dict) else None
            if player and player.get("name"):
                new = mapped(player["name"], batting_roster)
                if new and new != player["name"]:
                    player["name"], player["normalized_name"] = new, normalize_name(new)
            dismissal = row.get("dismissal") if isinstance(row.get("dismissal"), dict) else None
            if dismissal:
                for key in ("bowler", "fielder"):
                    if dismissal.get(key):
                        dismissal[key] = mapped(dismissal[key], bowling_roster) or dismissal[key]
        for row in innings.get("bowling") or []:
            player = row.get("player") if isinstance(row, dict) and isinstance(row.get("player"), dict) else None
            if player and player.get("name"):
                new = mapped(player["name"], bowling_roster)
                if new and new != player["name"]:
                    player["name"], player["normalized_name"] = new, normalize_name(new)
        # the same bowler written two ways on one card ("Nandeep" in How out, "Nandip" in the bowling list): How out
        # uses the bowling-list name, so his wickets are credited to him
        bowlers = [str((row.get("player") or {}).get("name") or "") for row in innings.get("bowling") or [] if isinstance(row, dict) and isinstance(row.get("player"), dict)]
        bowlers = [name for name in bowlers if name]
        for row in innings.get("batting") or []:
            dismissal = row.get("dismissal") if isinstance(row, dict) and isinstance(row.get("dismissal"), dict) else None
            written = " ".join(str((dismissal or {}).get("bowler") or "").split())
            if not written or not bowlers or normalize_name(written) in {normalize_name(name) for name in bowlers}:
                continue
            low = normalize_name(written)
            close = sorted(
                ((difflib.SequenceMatcher(None, low, normalize_name(name)).ratio(), name) for name in bowlers if normalize_name(name)[:1] == low[:1]),
                reverse=True,
            )
            if close and close[0][0] >= 0.75 and (len(close) == 1 or close[0][0] - close[1][0] >= 0.1):
                notes.append(f"How out bowler '{written}' is '{close[0][1]}' in the bowling list - used '{close[0][1]}'.")
                dismissal["bowler"] = close[0][1]
    return list(dict.fromkeys(notes))


def _apply_ai_template(store: dict[str, Any], record: dict[str, Any], template: dict[str, Any], result: dict[str, Any]) -> str:
    """Save an AI-read template onto the upload record (shared by the 1st photo and the 2nd innings photo)."""
    side_note = _repeated_batting_side_note(template) if isinstance(template, dict) else ""
    if side_note:
        result = {**result, "notes": [*(result.get("notes") or []), side_note]}
    roster_notes = _map_card_names_to_rosters(store, template) if isinstance(template, dict) else []
    if roster_notes:
        result = {**result, "notes": [*(result.get("notes") or []), *roster_notes]}
    imported = parse_imported_extraction(store, json.dumps(template))
    record.update(imported)
    # Keep the AI result as THE reviewed copy too, so the Admin Center JSON box, the snapshot and the
    # public card all use it instead of an older OCR / review template (README "Re-extract uses the AI reader").
    record["extraction_template"] = deepcopy(template)
    record["review_source_json"] = json.dumps(template)[:12000]
    record["review_template_json"] = json.dumps(template, indent=2)
    # The date the AI read (after the photo-date check) also sets the card's season.
    card_date = str((template.get("match") or {}).get("date") or "")[:10]
    if re.match(r"^20\d{2}-\d{2}-\d{2}$", card_date):
        record.update({"scorecard_date": card_date, "archive_date": card_date, "archive_date_source": "scorecard", "archive_year": card_date[:4], "season": f"{card_date[:4]} Season"})
    elif str(record.get("archive_date_source") or "") == "filesystem-modified":
        # No date on the card: don't keep a date taken from when the file was copied.
        record.update({"scorecard_date": "", "archive_date": ""})
    record["review_llm_model"] = str(result.get("model") or "")
    record["review_llm_notes"] = "Read by AI: " + ("; ".join(result.get("notes") or []) or "no problems found.")
    record["ocr_engine"] = f"ai:{result.get('model')}"
    if result.get("fallback") == "ollama":
        # Backup read: no reader stamp, so "Skip cards already read by the newest AI reader" reads it again with Gemini later.
        record["ocr_pipeline"] = "Photo read by the local Ollama AI (backup while Gemini's free limit was used up)"
    else:
        record["ocr_pipeline"] = f"Photo read by an AI vision model (handwriting included), reader {ai_vision.READER_VERSION}"
    record["confidence"] = f"AI read ({(template.get('meta') or {}).get('confidence') or 'unrated'})"
    record["ocr_processed_at"] = now_iso()
    record["ai_flags"] = list(result.get("notes") or [])
    usage = result.get("usage") or {}
    record["extracted_summary"] = (
        f"Read by AI ({result.get('model')}); {usage.get('input_tokens', '?')} in / {usage.get('output_tokens', '?')} out tokens. "
        + str((template.get("validation") or {}).get("notes") or "")
    )[:500]
    return ""


def _upload_file_path(upload: dict[str, Any]) -> Path | None:
    for raw in (upload.get("file_path"), upload.get("file_name")):
        name = Path(str(raw or "").replace("\\", "/")).name
        if name and (UPLOAD_DIR / name).is_file():
            return UPLOAD_DIR / name
    return None


# ---------------------------------------------------------------------------
# Scorecard uploads: checks, review and duplicates (soft launch, Oct 2026)
# README: "Scorecard uploads: checks, review and duplicates". Logic: app/scorecard_checks.py
# ---------------------------------------------------------------------------
NEEDS_REVIEW = "Needs admin review"


def _scorecard_upload_checks(store: dict[str, Any], record: dict[str, Any]) -> dict[str, Any]:
    """Run the smart checks on a fresh upload and set its status. Mutates `record` in the store."""
    try:
        card = _scorecard_from_archive(record)
    except Exception:
        logger.exception("Digital scorecard build failed for upload %s", record.get("id"))
        card = {}
    problems = scorecard_checks.quality_problems(card, record) if card else ["The digital scorecard couldn't be built."]
    if str(record.get("ocr_engine") or "").startswith(("ai:", "claude:")):
        problems += [note for note in record.get("ai_flags") or [] if note not in problems]
    duplicates = scorecard_checks.find_duplicates(store.get("archive_uploads", []) or [], record, _scorecard_from_archive)
    if not duplicates and card and ai_vision.enabled():
        # Smart duplicate check (sticky note "fix the duplicate SC, use smart detection through AI or Ollama"):
        # ask the AI (Gemini, else Claude, else Ollama) about uploads from the same day, or with a shared team
        # and a total within 10 runs. README: "AI duplicate check".
        mine = scorecard_checks.card_summary(card)
        for other in scorecard_checks.ai_candidates(record, store.get("archive_uploads", []) or [], _scorecard_from_archive):
            try:
                verdict = ai_vision.same_match(mine, scorecard_checks.card_summary(_scorecard_from_archive(other)))
            except Exception:
                logger.exception("AI duplicate check failed for %s vs %s", record.get("id"), other.get("id"))
                verdict = None
            if verdict and verdict["same"]:
                duplicates.append({
                    "id": other.get("id"),
                    "file_name": other.get("original_file_name") or other.get("file_name"),
                    "status": other.get("status"),
                    "reason": f"AI thinks it's the same match ({verdict['reason'] or verdict['model']})",
                })
    for item in duplicates:
        item["match_code"] = _match_code(item.get("id"))
    flags = list(problems) + [f"Possible duplicate of '{item['file_name']}' (Match ID {item['match_code']}): {item['reason']}." for item in duplicates]
    record["review_flags"] = flags
    record["review_problems"] = problems
    record["possible_duplicates"] = duplicates
    record["status"] = NEEDS_REVIEW if flags else "Pending review"
    return {"needs_review": bool(flags), "problems": problems, "duplicates": duplicates, "flags": flags, "scorecard": card}


def _scorecard_safe_date(archive: dict[str, Any]) -> str:
    try:
        return str(_scorecard_from_archive(archive).get("date") or "")
    except Exception:
        return ""


def _notify_site_admins(kind: str, title: str, body: str = "", link: str = "", created_by: str = "") -> None:
    try:
        with _auth_connection() as connection:
            admins = connection.execute("SELECT id FROM app_users WHERE role = 'superadmin'").fetchall()
            for admin in admins:
                muse.create_notification(connection, club_id="", kind=kind, title=title, body=body, link=link, target_user_id=int(admin["id"]), created_by=created_by)
    except Exception:
        logger.exception("Could not notify site admins kind=%s", kind)


def _scorecard_check_alerts(record: dict[str, Any], checks: dict[str, Any], user_row: sqlite3.Row) -> None:
    """Not proper -> site admins get a review alert. Errors in the scorecard -> the club's players are told."""
    if not checks.get("needs_review"):
        return
    card = checks.get("scorecard") or {}
    title = card.get("title") or record.get("original_file_name") or "a scorecard"
    who = str(user_row["display_name"] or "A scorer")
    _notify_site_admins(
        "scorecard_review",
        f"Scorecard needs review: {title}",
        f"Uploaded by {who}. " + " ".join(checks.get("flags") or [])[:400],
        "/admin/scorecards",
        who,
    )
    if checks.get("problems") and record.get("club_id"):
        _notify(
            str(record.get("club_id")),
            "scorecard_error",
            f"Scorecard being checked: {title}",
            "The uploaded scorecard has some errors. A site admin is checking it before it goes live.",
            "/scorecards",
            str(record.get("match_id") or ""),
            who,
        )


def _scorecard_upload_access(token: str | None, upload_id: str) -> tuple[sqlite3.Row, str, dict[str, Any], dict[str, Any], bool]:
    """(user, club, store, upload, is_site_admin) for someone allowed to see or publish this upload."""
    user_row, current_club_id = _require_permission(token, "score_matches")
    store = load_store()
    if upload_id.startswith("a-"):
        upload_id = upload_id[2:]  # public scorecard address (/scorecards/a-<id>) works too
    try:
        upload = get_archive_or_404(store, upload_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    is_admin = "superadmin" in _user_role_names(user_row, current_club_id)
    if not is_admin:
        mine = int(upload.get("uploaded_by_user_id") or 0) == int(user_row["id"])
        club_ids = set(_user_club_ids(store, user_row, current_club_id)) | {str(user_row["primary_club_id"] or ""), str(current_club_id or "")}
        if not mine and not (set(str(c) for c in upload.get("club_ids") or [upload.get("club_id")]) & club_ids):
            raise HTTPException(status_code=403, detail="This scorecard belongs to another club.")
    return user_row, current_club_id, store, upload, is_admin


def _mark_archive_approved(store: dict[str, Any], upload: dict[str, Any], user_row: sqlite3.Row, current_club_id: str) -> None:
    club = _selected_club(store, current_club_id)
    inferred_club = _resolve_archive_club(upload, store.get("clubs", [])) or club
    upload["club_id"] = upload.get("club_id") or inferred_club.get("id", "") or club.get("id", "")
    upload["club_name"] = upload.get("club_name") or inferred_club.get("name", "") or club.get("name", "")
    existing_club_ids, existing_club_names = archive_club_context(upload, store.get("clubs", []), store.get("members", []), store.get("fixtures", []))
    upload["club_ids"] = list(dict.fromkeys([*(existing_club_ids or []), str(upload.get("club_id") or "").strip()]))
    names = [name for name in existing_club_names if name]
    for club_id in upload["club_ids"]:
        club_item = _club_by_identifier(store.get("clubs", []), club_id)
        if club_item:
            names.append(str(club_item.get("name") or club_item.get("short_name") or "").strip())
    upload["club_names"] = list(dict.fromkeys(name for name in names if name))
    upload["status"] = "Approved"
    upload["reviewed_by"] = user_row["display_name"] or user_row["mobile"] or "admin"
    upload["reviewed_at"] = now_iso()
    auto_register_players_from_archive(store, upload, club_id=upload.get("club_id", ""))
    # the teams on a published scorecard become clubs (with their players) if they aren't yet, e.g. "Amit CC"
    try:
        _register_played_fixture_teams(store)
    except Exception:
        logger.exception("Club registration from scorecard %s failed", upload.get("id"))
    try:
        _sync_fixture_results_from_scorecards(store)
    except Exception:
        logger.exception("Fixture result sync from scorecard %s failed", upload.get("id"))


class ScorecardReportRequest(BaseModel):
    note: str = ""


class ScorecardManualRequest(BaseModel):
    template: dict[str, Any]


class ScorecardDuplicatesHideRequest(BaseModel):
    ids: list[str] = Field(default_factory=list)


class ScorecardDecisionRequest(BaseModel):
    decision: str  # approve | reject
    note: str = ""


class ScorecardNameMergeRequest(BaseModel):
    first_id: str
    second_id: str
    keep: str = "older"  # older | newer


def _card_player_names(card: dict[str, Any]) -> list[str]:
    """Distinct batting and bowling names on a scorecard, in the order they appear."""
    names: list[str] = []
    seen: set[str] = set()
    for innings in card.get("innings") or []:
        if not isinstance(innings, dict):
            continue
        for key in ("batting", "bowling"):
            for row in innings.get(key) or []:
                name = str(row.get("name") or "").strip() if isinstance(row, dict) else ""
                norm = normalize_name(name)
                if norm and norm not in seen:
                    seen.add(norm)
                    names.append(name)
    return names


SCORECARD_NAME_MATCH_MIN_SCORE = PLAYER_MERGE_SUGGEST_MIN_SCORE  # upload name check uses the same 75% rule


def _card_name_matches(store: dict[str, Any], card: dict[str, Any], user_row: sqlite3.Row | None = None, current_club_id: str = "") -> list[dict[str, Any]]:
    """Names on a new scorecard that match players already on file (engine score at or above SCORECARD_NAME_MATCH_MIN_SCORE).

    The card name is scored as a player in the uploader's club. "recognised": one player fits, under an alias or a shorter name.
    "duplicate": two players fit and the engine says they are likely the same person; the older record is listed first.
    Only the uploader's own clubs can merge them.
    """
    members = store.get("members", []) or []
    engine = _match_engine(store)
    matches: list[dict[str, Any]] = []
    for name in _card_player_names(card):
        norm = normalize_name(name)
        card_player = {
            "name": name,
            "aliases": [],
            "primary_club_id": current_club_id,
            "club_memberships": [{"club_id": current_club_id}] if current_club_id else [],
        }
        scored: list[tuple[float, int, dict[str, Any]]] = []
        for index, member in enumerate(members):
            pair = engine.score(card_player, member, check_matches=False)
            if pair.score >= SCORECARD_NAME_MATCH_MIN_SCORE:
                scored.append((pair.score, index, member))
        if not scored:
            continue
        scored.sort(key=lambda item: (-item[0], item[1]))
        duplicate = None
        if len(scored) >= 2:
            first_two = sorted(scored[:2], key=lambda item: item[1])  # older record first
            older, newer = first_two[0][2], first_two[1][2]
            pair = engine.score(older, newer)
            if pair.score >= SCORECARD_NAME_MATCH_MIN_SCORE and not pair.vetoed:
                duplicate = (older, newer, pair)
        if duplicate:
            older, newer, pair = duplicate
            can_merge = user_row is not None and all(_reviewer_can_decide(store, user_row, current_club_id, m) for m in (older, newer))
            matches.append({
                "kind": "duplicate",
                "card_name": name,
                "match_percent": round(pair.score * 100),
                "reasons": pair.reasons,
                "members": [
                    {"id": str(m.get("id") or ""), "name": str(m.get("name") or ""), "clubs": _member_club_names(store, m), "is_older": position == 0}
                    for position, m in enumerate((older, newer))
                ],
                "can_merge": can_merge,
            })
            continue
        top_score, _, top = scored[0]
        if normalize_name(str(top.get("name") or "")) == norm:
            continue
        matches.append({
            "kind": "recognised",
            "card_name": name,
            "match_percent": round(top_score * 100),
            "reasons": engine.score(card_player, top, check_matches=False).reasons,
            "members": [{"id": str(top.get("id") or ""), "name": str(top.get("name") or ""), "clubs": _member_club_names(store, top)}],
            "can_merge": False,
        })
    return matches


def _name_match_notice(matches: list[dict[str, Any]]) -> str:
    """One sentence for the upload message, so the uploader hears about matches straight away."""
    parts = []
    for match in matches:
        names = [m["name"] for m in match["members"]]
        if match["kind"] == "duplicate":
            parts.append(f"'{names[0]}' and '{names[1]}' look like the same player")
        else:
            parts.append(f"'{match['card_name']}' is recognised as {names[0]}")
    return f" Name check: {'; '.join(parts)}." if parts else ""


@app.post("/api/scorecards/{upload_id}/name-merge")
def scorecard_name_merge(upload_id: str, request: ScorecardNameMergeRequest, x_auth_token: str | None = Header(default=None)) -> dict[str, Any]:
    """Merge two players that this scorecard's names show are the same person. Keeps the older or newer record."""
    user_row, current_club_id, store, upload, _ = _scorecard_upload_access(x_auth_token, upload_id)
    if request.keep not in {"older", "newer"}:
        raise HTTPException(status_code=400, detail="Choose which record to keep: older or newer.")
    pair_ids = {str(request.first_id or "").strip(), str(request.second_id or "").strip()}
    group = next(
        (
            match for match in _card_name_matches(store, _scorecard_from_archive(upload))
            if match["kind"] == "duplicate" and {m["id"] for m in match["members"]} == pair_ids
        ),
        None,
    )
    if not group:
        raise HTTPException(status_code=404, detail="These players are not a match on this scorecard any more.")
    older_id, newer_id = group["members"][0]["id"], group["members"][1]["id"]
    for member_id in (older_id, newer_id):
        member = _member_by_id(store, member_id)
        if not member or not _reviewer_can_decide(store, user_row, current_club_id, member):
            raise HTTPException(status_code=403, detail="Ask a club admin to merge these players.")
    keep_id = older_id if request.keep == "older" else newer_id
    result = _perform_member_merge(store, older_id, newer_id, user_row, keep_id)
    return {"message": f"'{result['removed_name']}' is merged into '{result['kept_name']}'.", **result}


@app.get("/api/scorecards/{upload_id}/preview")
def scorecard_upload_preview(upload_id: str, x_auth_token: str | None = Header(default=None)) -> dict[str, Any]:
    """The full digital scorecard of an upload that isn't published yet (uploader, own club's scorers, site admins)."""
    user_row, preview_club_id, store, upload, is_admin = _scorecard_upload_access(x_auth_token, upload_id)
    status = str(upload.get("status") or "")
    flags = list(upload.get("review_flags") or [])
    upload_roles = set(_user_role_names(user_row, preview_club_id))
    duplicate_candidates: list[dict[str, Any]] = []
    for item in upload.get("possible_duplicates") or []:
        if not isinstance(item, dict) or not item.get("id"):
            continue
        try:
            other = get_archive_or_404(store, str(item["id"]))
        except ValueError:
            continue
        if str(other.get("status") or "").lower() in {"rejected", "duplicate"} or not _is_duplicate_upload(upload, other):
            continue
        duplicate_candidates.append(
            {
                "id": other.get("id"),
                "match_code": _match_code(other.get("id")),
                "file_name": other.get("original_file_name") or other.get("file_name") or "",
                "is_published": _archive_scorecard_is_published(other),
            }
        )
    same_innings_ids = {str(item["id"]) for item in duplicate_candidates}
    return {
        "scorecard": _link_card_players(store, _scorecard_from_archive(upload)),
        "status": status,
        "flags": flags,
        "duplicates": list(upload.get("possible_duplicates") or []),
        "can_publish": status.lower().startswith("pending") and (is_admin or not flags),
        "can_report": status.lower() not in {"rejected", "duplicate"},
        "can_edit": status.lower() not in {"rejected", "duplicate"},
        "can_delete": bool(upload_roles.intersection({"club_admin", "superadmin"})),
        "is_published": _archive_scorecard_is_published(upload),
        "unreadable": any(word in str(upload.get("ocr_engine") or "").lower() for word in ("unreadable", "fallback"))
        or (
            str(upload.get("ocr_engine") or "").lower() == "tesseract"
            and not ocr_rows_look_real(list(upload.get("suggested_performances") or []), store.get("members", []) or [])
        ),
        "typed_in": str(upload.get("ocr_engine") or "") in {"manual-entry", "manual-import"},
        "ai_read": str(upload.get("ocr_engine") or "").startswith(("ai:", "claude:")),
        "ai_available": ai_vision.enabled() and _ai_allowed(user_row, preview_club_id, "ai_extraction", f"scorecard:{upload.get('id')}", claim=False),
        "ai_locked": ai_vision.enabled() and not _ai_allowed(user_row, preview_club_id, "ai_extraction", f"scorecard:{upload.get('id')}", claim=False),
        "is_site_admin": is_admin,
        "uploaded_by": upload.get("uploaded_by") or "",
        "match_code": _match_code(upload.get("id")),
        # possible same matches that are missing this card's other innings: offered as "Link as the other innings"
        "link_candidates": [
            {"id": item.get("id"), "match_code": _match_code(item.get("id")), "file_name": item.get("file_name") or ""}
            for item in (upload.get("possible_duplicates") or [])
            if isinstance(item, dict) and item.get("id") and str(item["id"]) not in same_innings_ids
        ] if _template_innings_count(_scorecard_pick_template(upload) or {}) < 2 else [],
        # the same innings uploaded twice: offered as "Delete the duplicate"
        "duplicate_candidates": duplicate_candidates,
        # names on this card that match players on file: shown as "recognised" or "may be the same player"
        "name_matches": _card_name_matches(store, _scorecard_from_archive(upload), user_row, preview_club_id),
        # Nov 2 2026: the other innings of this match uploaded separately -> offer "Join the two innings"
        "other_half": (lambda half: {"id": half.get("id"), "file_name": half.get("original_file_name") or half.get("file_name") or "", "uploaded_by": half.get("uploaded_by") or ""} if half else None)(_find_other_half(store, upload)),
        # Nov 2 2026: only one innings on the photo -> offer "Add the 2nd innings photo"
        "innings_count": _template_innings_count(_scorecard_pick_template(upload) or {}),
        "can_add_second_photo": bool(
            status.lower() not in {"rejected", "duplicate"}
            and not upload.get("second_photo_file")
            and _template_innings_count(_scorecard_pick_template(upload) or {}) < 2
        ),
    }


@app.post("/api/scorecards/{upload_id}/publish")
def scorecard_upload_publish(upload_id: str, x_auth_token: str | None = Header(default=None)) -> dict[str, Any]:
    """The scorer checked the digital scorecard and it looks right: publish it (no admin needed when the checks passed)."""
    user_row, current_club_id, store, upload, is_admin = _scorecard_upload_access(x_auth_token, upload_id)
    status = str(upload.get("status") or "").lower()
    if status in {"approved", "applied to match"}:
        return {"message": "This scorecard is already published.", "status": upload.get("status")}
    if (upload.get("review_flags") or status == NEEDS_REVIEW.lower()) and not is_admin:
        raise HTTPException(status_code=409, detail="A site admin needs to check this scorecard first. You'll see it on Scorecards once it's approved.")
    _mark_archive_approved(store, upload, user_row, current_club_id)
    save_store(store)
    _audit_event("archive.publish", "archive_upload", upload_id, actor=user_row, club_id=str(upload.get("club_id") or ""), club_name=str(upload.get("club_name") or ""), details={"file_name": upload.get("file_name") or ""}, source="api")
    title = _scorecard_from_archive(upload).get("title") or "New scorecard"
    if upload.get("club_id"):
        _notify(str(upload["club_id"]), "scorecard_published", f"Scorecard published: {title}", "", f"/scorecards/a-{upload_id}", str(upload.get("match_id") or ""), str(user_row["display_name"] or ""))
    return {"message": "Published. Everyone can see it on Scorecards now.", "status": "Approved", "url": f"/scorecards/a-{upload_id}"}


@app.post("/api/scorecards/{upload_id}/report")
def scorecard_upload_report(upload_id: str, request: ScorecardReportRequest, x_auth_token: str | None = Header(default=None)) -> dict[str, Any]:
    """"Something's wrong": send the upload to the site admins with a note, and tell the club's players."""
    user_row, _, store, upload, _ = _scorecard_upload_access(x_auth_token, upload_id)
    note = str(request.note or "").strip()[:500] or "The scorer says something is wrong."
    upload["review_flags"] = list(upload.get("review_flags") or []) + [f"Scorer's note: {note}"]
    was_published = str(upload.get("status") or "").lower() in {"approved", "applied to match"}
    upload["status"] = NEEDS_REVIEW
    save_store(store)
    title = _scorecard_from_archive(upload).get("title") or upload.get("original_file_name") or "a scorecard"
    who = str(user_row["display_name"] or "A scorer")
    _notify_site_admins("scorecard_review", f"Scorecard reported: {title}", f"{who}: {note}", "/admin/scorecards", who)
    if upload.get("club_id"):
        _notify(str(upload["club_id"]), "scorecard_error", f"Scorecard being checked: {title}", "Someone spotted an error. A site admin is checking it" + (" and it's hidden until then." if was_published else "."), "/scorecards", str(upload.get("match_id") or ""), who)
    return {"message": "Thanks. A site admin will check it, and the players have been told.", "status": NEEDS_REVIEW}


@app.get("/api/scorecards/reader")
def scorecard_reader_info(x_auth_token: str | None = Header(default=None)) -> dict[str, Any]:
    """Which photo reader the upload page will use (shown on /scorecards/upload). Plan-aware:
    a Free user whose free AI try is used gets the basic reader + type-in (README "Plans: what each group can use")."""
    chosen = ai_vision.provider()
    if chosen and x_auth_token:
        try:
            user_row, current_club_id = _auth_user_from_token(x_auth_token, touch=False)
            if not _has_feature(user_row, current_club_id, "ai_extraction"):
                plan = _plan_for(user_row, current_club_id)
                if not _ai_trial_open(plan.get("ai_trial")):
                    return {"provider": "basic", "label": "Basic photo reader, then you type it in (AI reading is part of Pro)", "speed": "about a minute", "locked": True}
                return {"provider": chosen, "label": "AI (your 1 free AI try on the Free plan)", "speed": "usually well under a minute", "trial": True}
        except HTTPException:
            pass
    labels = {
        "gemini": ("scorecard reader", "usually well under a minute"),
        "claude": ("scorecard reader", "usually well under a minute"),
        "ollama": ("scorecard reader", "can take a few minutes"),
    }
    label, speed = labels.get(chosen, ("scorecard reader", "about a minute"))
    return {"provider": chosen or "basic", "label": label, "speed": speed}


@app.post("/api/scorecards/{upload_id}/ai-read")
def scorecard_upload_ai_read(upload_id: str, x_auth_token: str | None = Header(default=None)) -> dict[str, Any]:
    """"🤖 Read with AI": (re)read an existing upload's photo with the AI vision model."""
    if not ai_vision.enabled():
        raise HTTPException(status_code=503, detail="AI reading is switched off. Add a free GEMINI_API_KEY to the .env file and restart the app (see README).")
    user_row, current_club_id, store, upload, _ = _scorecard_upload_access(x_auth_token, upload_id)
    if not _ai_allowed(user_row, current_club_id, "ai_extraction", f"scorecard:{upload.get('id')}"):
        raise _upgrade_error("ai_extraction")
    path = _upload_file_path(upload)
    if path is None:
        raise HTTPException(status_code=404, detail="The original photo for this upload isn't on this computer.")
    club = _selected_club(store, str(upload.get("club_id") or current_club_id or ""))
    reason = _scorecard_ai_read(store, upload, path, club)
    if reason:
        raise HTTPException(status_code=502, detail=reason)
    # Nov 5 2026 (M-CA36A6F1 lost the Scarborough Pro innings): reading again must read the 2nd innings photo too,
    # otherwise the other team's innings from that photo is thrown away.
    second_path = _second_photo_path(upload)
    if second_path is not None:
        first_template = _scorecard_pick_template(upload) or {}
        second_result = _read_photo_with_ai(store, upload, second_path, club)
        if second_result.get("template"):
            joined = _join_innings_photos(first_template, second_result["template"])
            if _template_innings_count(joined) > _template_innings_count(first_template):
                _apply_ai_template(
                    store,
                    upload,
                    joined,
                    {**second_result, "notes": [*(upload.get("ai_flags") or []), *(second_result.get("notes") or [])]},
                )
    upload["status"] = "Pending review"
    upload["review_flags"] = []
    save_store(store)
    refreshed = load_store()
    archive_id = str(upload.get("id"))
    checks = _scorecard_upload_checks(refreshed, get_archive_or_404(refreshed, archive_id))
    save_store(refreshed)
    _audit_event("archive.ai_read", "archive_upload", archive_id, actor=user_row, club_id=str(upload.get("club_id") or ""), details={"flags": len(checks["flags"])}, source="api")
    if checks["needs_review"]:
        _scorecard_check_alerts(get_archive_or_404(refreshed, archive_id), checks, user_row)
    return {
        "message": "Read by AI. Check it against the photo." + (" A site admin will look at the points listed." if checks["needs_review"] else " Everything adds up: tap Publish if it matches."),
        "checks": {key: value for key, value in checks.items() if key != "scorecard"},
    }


def _is_unread_folder_copy(upload: dict[str, Any]) -> bool:
    """An upload the uploads-folder scan made from a loose photo and nobody has read or reviewed yet."""
    return (
        str(upload.get("source") or "") == "filesystem"
        and str(upload.get("confidence") or "") == "Draft only"
        and not str(upload.get("ocr_engine") or "").strip()
        and not _archive_scorecard_is_published(upload)
        and not str(upload.get("reviewed_by") or "").strip()
    )


@app.post("/api/scorecards/{upload_id}/second-photo")
async def scorecard_upload_second_photo(
    upload_id: str,
    request: Request,
    x_auth_token: str | None = Header(default=None),
    file: UploadFile = File(...),
) -> dict[str, Any]:
    """Amit, Nov 2 2026: a scorecard photographed on two pages. When the upload has only one innings, the uploader,
    their club's scorers or a site admin add the 2nd innings photo; it is read and joined to the same scorecard."""
    token = _auth_token_from_request(request, x_auth_token)
    user_row, current_club_id, store, upload, _ = _scorecard_upload_access(token, upload_id)
    status = str(upload.get("status") or "").lower()
    if status in {"rejected", "duplicate"}:
        raise HTTPException(status_code=409, detail="This scorecard was rejected. Upload it again instead.")
    if upload.get("second_photo_file"):
        raise HTTPException(status_code=409, detail="This scorecard already has a 2nd innings photo.")
    template = _scorecard_pick_template(upload) or {}
    if _template_innings_count(template) >= 2:
        raise HTTPException(status_code=409, detail="This scorecard already has both innings.")
    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Choose a photo first.")
    incoming_hash = file_sha256_from_bytes(content)
    if incoming_hash == upload.get("file_hash"):
        raise HTTPException(status_code=409, detail="That is the same photo as the 1st innings. Take a photo of the 2nd innings page.")
    stray_file = ""
    for existing in list(store.get("archive_uploads", []) or []):
        if existing.get("file_hash") == incoming_hash and _is_unread_folder_copy(existing):
            # Nov 5 2026: an older 2nd photo that the uploads-folder scan turned into its own unread "Ready for
            # review" card (the "two Match IDs" bug). Take it back as this scorecard's 2nd photo.
            stray_file = Path(str(existing.get("file_path") or existing.get("file_name") or "").replace("\\", "/")).name
            store["archive_uploads"] = [item for item in store.get("archive_uploads", []) or [] if item is not existing]
            continue
        if existing.get("file_hash") == incoming_hash or existing.get("second_photo_hash") == incoming_hash:
            raise HTTPException(status_code=409, detail=f"This photo was already uploaded as '{existing.get('original_file_name') or existing.get('file_name') or 'another scorecard'}'.")
    suffix = Path(file.filename or "scorecard.jpg").suffix or ".jpg"
    if stray_file and (UPLOAD_DIR / stray_file).is_file():
        file_token = stray_file
    else:
        file_token = f"{uuid.uuid4().hex[:10]}{suffix}"
        (UPLOAD_DIR / file_token).write_bytes(content)
    upload["second_photo_file"] = file_token
    upload["second_photo_hash"] = incoming_hash
    upload["second_photo_name"] = file.filename or file_token
    upload["second_preview_url"] = f"/uploads/{file_token}"
    message = "2nd innings photo added."
    read = False
    if ai_vision.enabled() and _ai_allowed(user_row, current_club_id, "ai_extraction", f"scorecard:{upload.get('id')}:2"):
        club = _selected_club(store, str(upload.get("club_id") or current_club_id or ""))
        result = _read_photo_with_ai(store, upload, UPLOAD_DIR / file_token, club)
        if result.get("template"):
            joined = _join_innings_photos(template, result["template"])
            if _template_innings_count(joined) > _template_innings_count(template):
                _apply_ai_template(store, upload, joined, result)
                read = True
                message = "2nd innings photo read and added to the scorecard. Check it against the photos."
            else:
                message = "2nd innings photo added, but no new innings was found on it. Check it's the other team's batting page, or type the 2nd innings in with ✏️."
        else:
            message = f"2nd innings photo added, but it couldn't be read ({result.get('error') or 'AI reading failed'}). Type the 2nd innings in with ✏️."
    else:
        message = "2nd innings photo added. Type the 2nd innings in with ✏️ (AI reading isn't available for this account)."
    upload["status"] = "Pending review"
    upload["review_flags"] = []
    save_store(store)
    refreshed = load_store()
    archive_id = str(upload.get("id"))
    checks = _scorecard_upload_checks(refreshed, get_archive_or_404(refreshed, archive_id))
    save_store(refreshed)
    _audit_event("archive.second_photo", "archive_upload", archive_id, actor=user_row, club_id=str(upload.get("club_id") or ""), details={"read": read, "file": file_token}, source="api")
    return {
        "message": message,
        "read": read,
        "preview_url": f"/scorecards/{archive_id}?preview=1",
        "checks": {key: value for key, value in checks.items() if key != "scorecard"},
    }


class ScorecardLinkRequest(BaseModel):
    match_code: str


@app.post("/api/scorecards/{upload_id}/link")
def scorecard_upload_link(upload_id: str, request: ScorecardLinkRequest, x_auth_token: str | None = Header(default=None)) -> dict[str, Any]:
    """Nov 2 2026 (Amit): link this upload to the other team's innings by its Match ID, so the match has both
    innings. Either team's captain / club admin (or a superadmin) can link; the two must be different innings."""
    user_row, current_club_id, store, upload, _ = _scorecard_upload_access(x_auth_token, upload_id)
    other = _upload_by_match_code(store, request.match_code)
    if other is None:
        raise HTTPException(status_code=404, detail=f"No scorecard has Match ID {request.match_code.strip() or '(empty)'}. Check the ID on the other team's scorecard.")
    if str(other.get("id")) == str(upload.get("id")):
        raise HTTPException(status_code=400, detail="That is this scorecard's own Match ID. Enter the other team's Match ID.")
    mine, theirs = _single_innings(upload), _single_innings(other)
    if not mine or not theirs:
        raise HTTPException(status_code=409, detail="Linking needs one innings on each scorecard. One of them already has both innings, or has none.")
    if mine.get("batting_team") and theirs.get("batting_team") and _same_team_name(mine.get("batting_team"), theirs.get("batting_team")):
        raise HTTPException(status_code=409, detail="Both scorecards have the same team batting, so they're the same innings (a duplicate), not the two innings of one match.")
    keep, half = (upload, other) if str(upload.get("created_at") or "") <= str(other.get("created_at") or "") else (other, upload)
    checks = _join_halves(store, keep, half, user_row)
    save_store(store)
    return {
        "message": f"Linked: both innings are now one match ({_match_code(keep.get('id'))}).",
        "match_code": _match_code(keep.get("id")),
        "preview_url": f"/scorecards/{keep.get('id')}?preview=1",
        "checks": {key: value for key, value in checks.items() if key != "scorecard"},
    }


@app.post("/api/scorecards/{upload_id}/join/{other_id}")
def scorecard_upload_join(upload_id: str, other_id: str, x_auth_token: str | None = Header(default=None)) -> dict[str, Any]:
    """"🔗 Join the two innings": two uploads that are the two innings of one match become one scorecard."""
    user_row, current_club_id, store, upload, _ = _scorecard_upload_access(x_auth_token, upload_id)
    other_id = other_id[2:] if other_id.startswith("a-") else other_id
    try:
        other = get_archive_or_404(store, other_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    if not _halves_match(upload, other):
        raise HTTPException(status_code=409, detail="These two uploads don't look like the two innings of one match (date, teams, venue and batting side must fit).")
    # the older upload keeps its address; the newer one is joined into it
    keep, half = (upload, other) if str(upload.get("created_at") or "") <= str(other.get("created_at") or "") else (other, upload)
    checks = _join_halves(store, keep, half, user_row)
    save_store(store)
    return {
        "message": "Joined: both innings are now one scorecard.",
        "preview_url": f"/scorecards/{keep.get('id')}?preview=1",
        "checks": {key: value for key, value in checks.items() if key != "scorecard"},
    }


class ScorecardRemoveDuplicateRequest(BaseModel):
    confirm_published: bool = False


@app.post("/api/scorecards/{upload_id}/remove-duplicate/{other_id}")
def scorecard_upload_remove_duplicate(upload_id: str, other_id: str, request: ScorecardRemoveDuplicateRequest, x_auth_token: str | None = Header(default=None)) -> dict[str, Any]:
    """"🗑 Delete the duplicate": the other upload holds the same innings as this one, so it is removed (with its
    photo) and this scorecard keeps going. Club admins and site admins only; a published duplicate needs a confirm."""
    user_row, current_club_id, store, upload, is_admin = _scorecard_upload_access(x_auth_token, upload_id)
    if not is_admin and not set(_user_role_names(user_row, current_club_id)).intersection({"club_admin", "superadmin"}):
        raise HTTPException(status_code=403, detail="Only club admins or the superadmin can delete a duplicate scorecard.")
    other_id = other_id[2:] if other_id.startswith("a-") else other_id
    try:
        other = get_archive_or_404(store, other_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    if str(other.get("id")) == str(upload.get("id")):
        raise HTTPException(status_code=400, detail="Choose the other upload, not this one.")
    if not _is_duplicate_upload(upload, other):
        raise HTTPException(status_code=409, detail="These two uploads aren't the same photo or the same innings. If they are the two innings of one match, join them instead.")
    if _archive_scorecard_is_published(other) and not request.confirm_published:
        raise HTTPException(status_code=409, detail="That scorecard is published. Confirm that you want to delete a published scorecard.")
    other_key = str(other.get("id"))
    other_code = _match_code(other_key)
    file_path = str(other.get("file_path") or "").strip()
    store["archive_uploads"] = [item for item in store.get("archive_uploads", []) or [] if str(item.get("id")) != other_key]
    store["duplicate_uploads"] = [
        item
        for item in store.get("duplicate_uploads", []) or []
        if str(item.get("original_upload_id") or "") != other_key and str(item.get("duplicate_upload_id") or "") != other_key
    ]
    still_used = any(str(item.get("file_path") or "").strip() == file_path for item in store["archive_uploads"]) if file_path else True
    if file_path and not still_used:
        try:
            resolved = Path(file_path).resolve()
            if resolved.exists() and UPLOAD_DIR.resolve() in resolved.parents:
                resolved.unlink()
        except Exception as exc:
            logger.warning("Could not delete duplicate upload file from disk: %s", exc)
    upload["possible_duplicates"] = [item for item in upload.get("possible_duplicates") or [] if str((item or {}).get("id")) != other_key]
    upload["review_flags"] = [flag for flag in upload.get("review_flags") or [] if f"(Match ID {other_code})" not in str(flag)]
    if str(upload.get("status") or "") == NEEDS_REVIEW and not upload["review_flags"]:
        upload["status"] = "Pending review"
    save_store(store)
    _audit_event("archive.duplicate.delete", "archive_upload", other_key, actor=user_row, club_id=str(other.get("club_id") or ""), details={"kept": str(upload.get("id") or ""), "file_name": other.get("file_name") or ""}, source="api")
    return {"message": f"Deleted the duplicate {other_code}. This scorecard is kept.", "status": upload.get("status")}


@app.post("/api/scorecards/{upload_id}/manual")
def scorecard_upload_manual(upload_id: str, request: ScorecardManualRequest, x_auth_token: str | None = Header(default=None)) -> dict[str, Any]:
    """"Type in the scorecard": the uploader, their club's scorers or a site admin enter the card by hand
    (the form on /scorecards/{id}?preview=1). Replaces whatever the photo reading found; checks run again."""
    user_row, _, store, upload, _ = _scorecard_upload_access(x_auth_token, upload_id)
    template = dict(request.template or {})
    template.setdefault("meta", {})
    template["meta"].update({"source": "manual-entry", "processed_by": f"Typed in by {user_row['display_name'] or 'a scorer'}", "confidence": "Typed in", "status": "template"})
    if not isinstance(template.get("innings"), list) or not template["innings"]:
        raise HTTPException(status_code=400, detail="Add at least one innings.")
    # Learn from the fix: names the AI misread and the person corrected (README "How the AI reader learns").
    learned = _learn_ai_corrections(str(upload.get("club_id") or ""), _scorecard_json(upload.get("review_source_json")) if upload.get("review_source_json") else None, template)
    imported = parse_imported_extraction(store, json.dumps(template))
    upload.update(imported)
    # The typed-in card is THE reviewed copy now (the AI's reading stays in review_source_json for learning).
    upload["extraction_template"] = deepcopy(template)
    upload["review_template_json"] = json.dumps(template, indent=2)
    upload["ocr_processed_at"] = now_iso()
    upload["status"] = "Pending review"
    upload["review_flags"] = []
    save_store(store)
    refreshed = load_store()
    checks = _scorecard_upload_checks(refreshed, get_archive_or_404(refreshed, str(upload.get("id"))))
    save_store(refreshed)
    _audit_event("archive.manual", "archive_upload", upload_id, actor=user_row, club_id=str(upload.get("club_id") or ""), club_name=str(upload.get("club_name") or ""), details={"flags": len(checks["flags"])}, source="api")
    if checks["needs_review"]:
        _scorecard_check_alerts(get_archive_or_404(refreshed, str(upload.get("id"))), checks, user_row)
    return {
        "message": ("Saved. A site admin will check the points listed." if checks["needs_review"] else "Saved. Everything checks out: tap Publish if it matches the photo.")
        + (f" The AI will remember: {', '.join(right for _, right in learned)}." if learned else ""),
        "checks": {key: value for key, value in checks.items() if key != "scorecard"},
        "learned": [{"wrong": wrong, "right": right} for wrong, right in learned],
    }


# ---------------------------------------------------------------------------
# Admin Center: clean up and re-read all scorecards with AI (README "Clean up and re-read all scorecards").
# Runs scripts/scorecards_reread_all.py in a background thread; the Admin Center polls the progress.
# ---------------------------------------------------------------------------
_REREAD_JOB: dict[str, Any] = {"running": False}
_REREAD_LOCK = threading.Lock()


class RereadAllRequest(BaseModel):
    cleanup: bool = True
    skip_done: bool = False
    only_problems: bool = False


def _reread_script():
    import importlib.util

    path = Path(__file__).resolve().parent.parent / "scripts" / "scorecards_reread_all.py"
    spec = importlib.util.spec_from_file_location("scorecards_reread_all", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@app.post("/api/admin/scorecards/reread-all")
def admin_reread_all(request: RereadAllRequest, x_auth_token: str | None = Header(default=None)) -> dict[str, Any]:
    """Site admin: start the clean-up + AI re-read of every scorecard photo (background)."""
    user_row, _ = _require_superadmin(x_auth_token)
    if not ai_vision.enabled():
        raise HTTPException(status_code=400, detail="No AI reader is set up. Put GEMINI_API_KEY=... in the .env file and restart the app.")
    with _REREAD_LOCK:
        if _REREAD_JOB.get("running"):
            return {"job": dict(_REREAD_JOB), "message": "Already running."}
        _REREAD_JOB.clear()
        _REREAD_JOB.update({"running": True, "started_at": now_iso(), "started_by": str(user_row["display_name"] or ""), "message": "Starting...", "number": 0, "total": 0, "done": []})
    import sys
    import types

    args = types.SimpleNamespace(dry_run=False, no_cleanup=not request.cleanup, skip_done=request.skip_done, only_problems=request.only_problems,
                                 since=datetime.utcnow().strftime("%Y-%m-%d"), pause=4.0)
    app_module = sys.modules[__name__]

    def progress(info: dict[str, Any]) -> None:
        with _REREAD_LOCK:
            if info.get("message"):
                _REREAD_JOB["message"] = info["message"]
            for key in ("stage", "number", "total", "file"):
                if key in info:
                    _REREAD_JOB[key] = info[key]
            if info.get("done"):
                _REREAD_JOB["done"] = (_REREAD_JOB.get("done") or [])[-40:] + [f"{info.get('file')}: {info['done']}"]

    def work() -> None:
        try:
            result = _reread_script().run(app_module, args, progress=progress)
            with _REREAD_LOCK:
                _REREAD_JOB.update({
                    "message": ("Stopped early: the AI wasn't answering (busy or today's free limit). Tomorrow, tap the button again with “Skip cards already read by the newest AI reader” ticked: it carries on where it stopped."
                                if result.get("stopped") else f"Done: {result.get('records', 0)} photos read."),
                    "report_path": result.get("report_path", ""),
                })
        except Exception as exc:
            logger.exception("Re-read all failed")
            with _REREAD_LOCK:
                _REREAD_JOB["message"] = f"Stopped with an error: {exc}"
        finally:
            with _REREAD_LOCK:
                _REREAD_JOB["running"] = False
                _REREAD_JOB["finished_at"] = now_iso()
        _audit_event("archive.reread_all", "archive_upload", "all", actor=user_row, details={"cleanup": request.cleanup}, source="api")

    threading.Thread(target=work, name="reread-all", daemon=True).start()
    return {"job": dict(_REREAD_JOB), "message": "Started."}


@app.get("/api/admin/scorecards/reread-all")
def admin_reread_all_status(x_auth_token: str | None = Header(default=None)) -> dict[str, Any]:
    _require_superadmin(x_auth_token)
    with _REREAD_LOCK:
        return {"job": dict(_REREAD_JOB)}


@app.get("/api/admin/scorecards/checks")
def admin_scorecard_checks(x_auth_token: str | None = Header(default=None)) -> dict[str, Any]:
    """Site admin: uploads waiting for review (with the reasons) and groups of duplicate uploads."""
    _require_superadmin(x_auth_token)
    store = load_store()
    archives = store.get("archive_uploads", []) or []
    # Older uploads have no photo fingerprint yet: work it out from the file in app/uploads once.
    filled = 0
    for upload in archives:
        if scorecard_checks.is_current_fingerprint(upload.get("image_fingerprint")):
            continue
        name = Path(str(upload.get("file_path") or "").replace("\\", "/")).name or str(upload.get("file_name") or "")
        path = UPLOAD_DIR / name if name else None
        if path and path.is_file():
            try:
                upload["image_fingerprint"] = scorecard_checks.image_fingerprint(path.read_bytes())
                filled += 1 if upload["image_fingerprint"] else 0
            except OSError:
                pass
    if filled:
        save_store(store)
    waiting = []
    for upload in archives:
        status = str(upload.get("status") or "")
        # "Ready for review" = Admin Center queue (e.g. Amit's re-processed 2024/2025 photos) - show those too.
        if not status.lower().startswith(("pending", "needs", "ready")):
            continue
        try:
            card = _scorecard_from_archive(upload)
        except Exception:
            card = {}
        waiting.append(
            {
                "id": upload.get("id"),
                "status": status,
                "file_name": upload.get("original_file_name") or upload.get("file_name"),
                "club_name": upload.get("club_name") or "",
                "uploaded_by": upload.get("uploaded_by") or "",
                "created_at": upload.get("created_at") or "",
                "title": card.get("title") or "",
                "date": card.get("date") or "",
                "flags": list(upload.get("review_flags") or []),
                "photo_url": upload.get("preview_url") or "",
            }
        )
    waiting.sort(key=lambda item: (0 if item["flags"] else 1, str(item["created_at"])), reverse=False)
    return {
        "waiting": waiting,
        "duplicate_groups": scorecard_checks.duplicate_groups(archives, _scorecard_from_archive),
        "llm": ai_vision.provider() or ((get_llm_status().get("model") or "") if get_llm_status().get("available") else ""),
        "generated_at": now_iso(),
    }


@app.post("/api/admin/scorecards/{upload_id}/decision")
def admin_scorecard_decision(upload_id: str, request: ScorecardDecisionRequest, x_auth_token: str | None = Header(default=None)) -> dict[str, Any]:
    admin_row, current_club_id = _require_superadmin(x_auth_token)
    store = load_store()
    try:
        upload = get_archive_or_404(store, upload_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    decision = str(request.decision or "").lower()
    title = _scorecard_from_archive(upload).get("title") or upload.get("original_file_name") or "Scorecard"
    if decision == "approve":
        _mark_archive_approved(store, upload, admin_row, current_club_id)
        upload["review_flags"] = []
        message = "Approved and published."
    elif decision == "reject":
        upload["status"] = "Rejected"
        upload["reviewed_by"] = admin_row["display_name"] or "admin"
        upload["reviewed_at"] = now_iso()
        upload["review_note"] = str(request.note or "")[:500]
        message = "Rejected. It stays out of Scorecards and stats."
    else:
        raise HTTPException(status_code=400, detail="Decision must be approve or reject.")
    save_store(store)
    _audit_event(f"archive.{decision}", "archive_upload", upload_id, actor=admin_row, club_id=str(upload.get("club_id") or ""), club_name=str(upload.get("club_name") or ""), details={"note": request.note or ""}, source="api")
    uploader = int(upload.get("uploaded_by_user_id") or 0)
    if uploader:
        try:
            load_store()
            with _auth_connection() as connection:
                muse.create_notification(connection, club_id="", kind="scorecard_decision", title=f"{title}: {'published' if decision == 'approve' else 'not published'}", body=str(request.note or ""), link=f"/scorecards/a-{upload_id}" if decision == "approve" else "/scorecards", target_user_id=uploader, created_by=str(admin_row["display_name"] or ""))
        except Exception:
            logger.exception("Could not notify uploader %s", uploader)
    return {"message": message, "status": upload.get("status")}


@app.post("/api/admin/scorecards/duplicates/ai-scan")
def admin_ai_scan_duplicates(x_auth_token: str | None = Header(default=None)) -> dict[str, Any]:
    """Ask the AI about likely pairs the simple checks didn't catch (same day, or a shared team with a total
    within 10 runs). Returns groups in the same shape as duplicate_groups. README: "AI duplicate check"."""
    _require_superadmin(x_auth_token)
    if not ai_vision.enabled():
        raise HTTPException(status_code=400, detail="No AI is set up. Add GEMINI_API_KEY to .env (free) and restart the app.")
    store = load_store()
    archives = [item for item in store.get("archive_uploads", []) or [] if isinstance(item, dict)]
    known = {
        str(member.get("id"))
        for group in scorecard_checks.duplicate_groups(archives, _scorecard_from_archive)
        for member in [group["keep"], *group["duplicates"]]
    }
    groups: list[dict[str, Any]] = []
    asked = 0
    seen_pairs: set[tuple[str, str]] = set()
    for record in archives:
        key = str(record.get("id"))
        if key in known or str(record.get("status") or "").lower() in {"rejected", "duplicate"}:
            continue
        for other in scorecard_checks.ai_candidates(record, archives, _scorecard_from_archive, limit=3):
            if key in known:
                break  # already matched to another upload in this scan
            pair = tuple(sorted((key, str(other.get("id")))))
            if pair in seen_pairs or str(other.get("id")) in known or asked >= 25:
                continue
            seen_pairs.add(pair)
            asked += 1
            verdict = ai_vision.same_match(
                scorecard_checks.card_summary(_scorecard_from_archive(record)),
                scorecard_checks.card_summary(_scorecard_from_archive(other)),
            )
            if not verdict or not verdict["same"]:
                continue
            first, second = sorted([record, other], key=lambda item: (0 if str(item.get("status") or "").lower() in {"approved", "applied to match"} else 1, str(item.get("created_at") or "")))
            groups.append({
                "keep": scorecard_checks._brief(first, _scorecard_from_archive(first)),
                "duplicates": [scorecard_checks._brief(second, _scorecard_from_archive(second))],
                "reasons": [f"AI: {verdict['reason'] or 'same match'}"],
            })
            known.update({key, str(other.get("id"))})
    return {"groups": groups, "asked": asked, "message": f"Asked the AI about {asked} pair{'s' if asked != 1 else ''}; found {len(groups)} more duplicate{'s' if len(groups) != 1 else ''}."}


@app.post("/api/admin/scorecards/duplicates/hide")
def admin_hide_duplicate_scorecards(request: ScorecardDuplicatesHideRequest, x_auth_token: str | None = Header(default=None)) -> dict[str, Any]:
    """Mark uploads as duplicates. Nothing is deleted: they just drop out of Scorecards, stats and the queue."""
    admin_row, _ = _require_superadmin(x_auth_token)
    ids = {str(item) for item in request.ids or [] if str(item).strip()}
    if not ids:
        raise HTTPException(status_code=400, detail="Choose the duplicates to hide.")
    store = load_store()
    hidden = 0
    for upload in store.get("archive_uploads", []) or []:
        if str(upload.get("id")) in ids and str(upload.get("status") or "").lower() != "duplicate":
            upload["status_before_duplicate"] = upload.get("status") or ""
            upload["status"] = "Duplicate"
            upload["reviewed_by"] = admin_row["display_name"] or "admin"
            upload["reviewed_at"] = now_iso()
            hidden += 1
    save_store(store)
    _audit_event("archive.duplicates.hide", "archive_upload", ",".join(sorted(ids))[:200], actor=admin_row, details={"count": hidden}, source="api")
    return {"message": f"Hid {hidden} duplicate upload{'s' if hidden != 1 else ''}.", "hidden": hidden}


@app.get("/admin/scorecards")
def admin_scorecards_page(request: Request) -> Response:
    session = _require_page_session(request)
    if isinstance(session, RedirectResponse):
        return session
    return _page_response("scorecard_admin.html")


@app.post("/api/archive/{upload_id}/apply")
def apply_archive(upload_id: str, request: ArchiveApplyRequest, focus_club_id: str | None = None, x_auth_token: str | None = Header(default=None)) -> dict[str, Any]:
    user_row, _ = _require_permission(x_auth_token, "manage_scorecards")
    store = load_store()
    try:
        upload = get_archive_or_404(store, upload_id)
        match = get_match_or_404(store, request.match_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))

    if not _archive_matches_fixture_season(upload, match):
        raise HTTPException(
            status_code=400,
            detail=(
                f"{upload.get('season') or 'This archive'} belongs to {_archive_year(upload) or 'a different season'} "
                f"and cannot be applied to the {match.get('date_label')} 2026 fixture. "
                "Keep historical scorecards in Archive and leave the 2026 schedule untouched."
            ),
        )

    inferred_club = _resolve_archive_club(upload, store.get("clubs", []))
    if inferred_club:
        upload["club_id"] = inferred_club.get("id", upload.get("club_id", ""))
        upload["club_name"] = inferred_club.get("name", upload.get("club_name", ""))
    upload["club_id"] = upload.get("club_id") or (focus_club_id or "")
    existing_club_ids, existing_club_names = archive_club_context(upload, store.get("clubs", []), store.get("members", []), store.get("fixtures", []))
    club_ids = _archive_match_club_ids(store, upload.get("club_id", ""), request.match_id)
    if not club_ids:
        club_ids = [str(upload.get("club_id") or "").strip()]
    upload["club_ids"] = list(dict.fromkeys([*(existing_club_ids or []), *(club_ids or []), str(upload.get("club_id") or "").strip()]))
    club_names = [name for name in existing_club_names if name]
    for club_id in upload["club_ids"]:
        club_item = _club_by_identifier(store.get("clubs", []), club_id)
        if club_item:
            club_names.append(str(club_item.get("name") or club_item.get("short_name") or "").strip())
    upload["club_names"] = list(dict.fromkeys(name for name in club_names if name))
    auto_register_players_from_archive(store, upload, match_id=request.match_id, club_id=upload.get("club_id", ""))
    match["scorecard"].update(
        {
            "heartlake_runs": request.heartlake_runs,
            "heartlake_wickets": request.heartlake_wickets,
            "heartlake_overs": request.heartlake_overs,
            "opponent_runs": request.opponent_runs,
            "opponent_wickets": request.opponent_wickets,
            "opponent_overs": request.opponent_overs,
            "result": request.result or "Recovered from uploaded scorecard",
            "live_summary": request.source_note or "Offline scorecard synced into online records",
        }
    )
    match["status"] = "Completed"
    existing_performances = [
        item for item in match.get("performances", []) if item.get("archive_upload_id") != upload_id
    ]
    for suggested in upload.get("suggested_performances", []):
        existing_performances.append(
            {
                "id": str(uuid.uuid4())[:8],
                "player_name": resolve_member_name(store, suggested.get("player_name", "")),
                "runs": int(suggested.get("runs", 0) or 0),
                "balls": int(suggested.get("balls", 0) or 0),
                "wickets": int(suggested.get("wickets", 0) or 0),
                "catches": int(suggested.get("catches", 0) or 0),
                "fours": int(suggested.get("fours", 0) or 0),
                "sixes": int(suggested.get("sixes", 0) or 0),
                "notes": suggested.get("notes", "Recovered from archive OCR"),
                "source": "archive-ocr",
                "archive_upload_id": upload_id,
            }
        )
    match["performances"] = existing_performances
    upload["status"] = "Approved"
    upload["applied_to_match_id"] = request.match_id
    _touch_fixture_audit(match, user_row)
    save_store(store)
    _audit_event(
        "archive.apply",
        "archive_upload",
        upload_id,
        actor=user_row,
        club_id=str(upload.get("club_id") or ""),
        club_name=str(upload.get("club_name") or ""),
        details={
            "match_id": request.match_id,
            "file_name": upload.get("file_name") or "",
            "result": request.result or "",
        },
        source="api",
    )
    return current_dashboard(load_store(), focus_club_id or upload.get("club_id"))


@app.get("/api/admin/review-queue")
def admin_review_queue(x_auth_token: str | None = Header(default=None)) -> dict[str, Any]:
    user_row, current_club_id = _require_permission(x_auth_token, "manage_scorecards")
    store = load_store()
    club = _selected_club(store, current_club_id)
    role = _effective_role_name(user_row, current_club_id)
    if role != "superadmin":
        raise HTTPException(status_code=403, detail="Only superadmin can open the admin review queue.")
    queue: list[dict[str, Any]] = []
    for upload in canonical_archive_uploads(store.get("archive_uploads", [])):
        status = str(upload.get("status") or "").strip().lower()
        if status in {"approved", "applied to match", "deleted"}:
            continue
        club_ids, club_names = archive_club_context(upload, store.get("clubs", []), store.get("members", []), store.get("fixtures", []))
        inferred_club = _resolve_archive_club(upload, store.get("clubs", []))
        queue.append(
            {
                **upload,
                "resolved_club_id": str((club_ids[0] if club_ids else upload.get("club_id")) or (inferred_club.get("id") if inferred_club else "") or "").strip(),
                "resolved_club_name": " / ".join(club_names) if club_names else str(upload.get("club_name") or (inferred_club.get("name") if inferred_club else "") or "Unassigned").strip() or "Unassigned",
                "resolved_club_ids": club_ids,
                "resolved_club_names": club_names,
                "scorecard_preview": _scorecard_from_archive(upload),
            }
        )
    return {
        "user": _auth_user_payload(user_row, current_club_id),
        "club": club,
        "queue": queue,
    }


@app.get("/api/admin/audit-log")
def admin_audit_log(
    limit: int = 50,
    club_id: str = "",
    x_auth_token: str | None = Header(default=None),
) -> dict[str, Any]:
    user_row, current_club_id = _require_permission(x_auth_token, "manage_scorecards")
    role = _effective_role_name(user_row, current_club_id)
    if role != "superadmin":
        raise HTTPException(status_code=403, detail="Only superadmin can open the audit log.")
    clean_limit = max(1, min(200, int(limit or 50)))
    clean_club_id = str(club_id or "").strip()
    with _auth_connection() as connection:
        if clean_club_id:
            rows = connection.execute(
                """
                SELECT *
                FROM app_audit_log
                WHERE club_id = ?
                ORDER BY created_at DESC, id DESC
                LIMIT ?
                """,
                (clean_club_id, clean_limit),
            ).fetchall()
        else:
            rows = connection.execute(
                """
                SELECT *
                FROM app_audit_log
                ORDER BY created_at DESC, id DESC
                LIMIT ?
                """,
                (clean_limit,),
            ).fetchall()
    return {
        "user": _auth_user_payload(user_row, current_club_id),
        "club": _selected_club(load_store(), clean_club_id or current_club_id),
        "entries": [
            {
                "id": row["id"],
                "created_at": row["created_at"],
                "actor_user_id": row["actor_user_id"],
                "actor_display_name": row["actor_display_name"],
                "club_id": row["club_id"],
                "club_name": row["club_name"],
                "action": row["action"],
                "entity_type": row["entity_type"],
                "entity_id": row["entity_id"],
                "details": json.loads(row["details_json"] or "{}"),
                "source": row["source"],
            }
            for row in rows
        ],
    }


@app.post("/api/admin/archive/{upload_id}/approve")
def approve_archive(
    upload_id: str,
    request: ArchiveReviewRequest | None = None,
    x_auth_token: str | None = Header(default=None),
) -> dict[str, Any]:
    user_row, current_club_id = _require_permission(x_auth_token, "manage_scorecards")
    logger.debug("Archive approve requested. upload_id=%s club_id=%s has_text=%s", upload_id, current_club_id or "", bool(request and str(request.text or "").strip()))
    store = load_store()
    try:
        upload = get_archive_or_404(store, upload_id)
    except ValueError as exc:
        logger.error("Archive approve failed. upload_id=%s error=%s", upload_id, exc)
        raise HTTPException(status_code=404, detail=str(exc))
    club = _selected_club(store, current_club_id)
    inferred_club = _resolve_archive_club(upload, store.get("clubs", [])) or club
    upload["club_id"] = upload.get("club_id") or inferred_club.get("id", "") or club.get("id", "")
    upload["club_name"] = upload.get("club_name") or inferred_club.get("name", "") or club.get("name", "")
    if request and str(request.text or "").strip():
        _apply_archive_review_text(store, upload, request.text, user_row=user_row)
    existing_club_ids, existing_club_names = archive_club_context(upload, store.get("clubs", []), store.get("members", []), store.get("fixtures", []))
    club_ids = [str(upload.get("club_id") or club.get("id") or "").strip()]
    upload["club_ids"] = list(dict.fromkeys([*(existing_club_ids or []), *(club_ids or [])]))
    club_names = [name for name in existing_club_names if name]
    for club_id in upload["club_ids"]:
        club_item = _club_by_identifier(store.get("clubs", []), club_id)
        if club_item:
            club_names.append(str(club_item.get("name") or club_item.get("short_name") or "").strip())
    upload["club_names"] = list(dict.fromkeys(name for name in club_names if name))
    upload["status"] = "Approved"
    upload["reviewed_by"] = user_row["display_name"] or user_row["mobile"] or "admin"
    upload["reviewed_at"] = now_iso()
    auto_register_players_from_archive(store, upload, club_id=upload.get("club_id", ""))
    # the teams on a published scorecard become clubs (with their players) if they aren't yet, e.g. "Amit CC"
    try:
        _register_played_fixture_teams(store)
    except Exception:
        logger.exception("Club registration from scorecard %s failed", upload.get("id"))
    try:
        _sync_fixture_results_from_scorecards(store)
    except Exception:
        logger.exception("Fixture result sync from scorecard %s failed", upload.get("id"))
    save_store(store)
    refreshed = load_store()
    updated = get_archive_or_404(refreshed, upload_id)
    _audit_event(
        "archive.approve",
        "archive_upload",
        upload_id,
        actor=user_row,
        club_id=str(updated.get("club_id") or club.get("id") or ""),
        club_name=str(updated.get("club_name") or club.get("name") or ""),
        details={
            "file_name": updated.get("file_name") or "",
            "status": updated.get("status") or "",
            "reviewed_by": updated.get("reviewed_by") or "",
        },
        source="api",
    )
    return {
        "message": f"{updated['file_name']} approved and added to reviewed history.",
        "archive": updated,
        "queue": [
            item
            for item in canonical_archive_uploads(refreshed.get("archive_uploads", []))
            if str(item.get("club_id") or "").strip() == str(updated.get("club_id") or club.get("id") or "").strip()
            and str(item.get("status") or "").strip().lower().startswith("pending")
        ],
        "dashboard": current_dashboard(refreshed, updated.get("club_id") or club.get("id", "")),
    }


@app.post("/api/admin/archive/{upload_id}/approve-form")
def approve_archive_form(
    request: Request,
    upload_id: str,
    text: str = Form(default=""),
) -> Response:
    try:
        logger.debug("Archive approve form submitted. upload_id=%s text_len=%s", upload_id, len(text or ""))
        result = approve_archive(
            upload_id,
            ArchiveReviewRequest(text=text) if text else None,
            x_auth_token=_auth_token_from_request(request),
        )
        archive = result.get("archive", {}) if isinstance(result, dict) else {}
        return _redirect_to_admin_center(
            str(archive.get("club_id") or result.get("dashboard", {}).get("club", {}).get("id") or ""),
            result.get("message", "Archive approved."),
            "success",
        )
    except HTTPException as exc:
        return _redirect_to_admin_center("", str(exc.detail), "error")


@app.delete("/api/admin/archive/{upload_id}")
def delete_archive(upload_id: str, published: bool = False, x_auth_token: str | None = Header(default=None)) -> dict[str, Any]:
    user_row, current_club_id = _auth_user_from_token(x_auth_token)
    if upload_id.startswith("a-"):
        upload_id = upload_id[2:]
    store = load_store()
    try:
        upload = get_archive_or_404(store, upload_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    upload_club_id = str(upload.get("club_id") or "").strip()
    roles = set(_user_role_names(user_row, current_club_id))
    upload_roles = set(_user_role_names(user_row, upload_club_id)) if upload_club_id else set()
    if not roles.union(upload_roles).intersection({"club_admin", "superadmin"}):
        raise HTTPException(status_code=403, detail="Only club admins or the superadmin can delete scorecards.")
    if _archive_scorecard_is_published(upload) and not published:
        # Nov 2 2026 (Amit): a wrong published scorecard can be deleted too, when asked for on purpose.
        raise HTTPException(status_code=409, detail="This scorecard is published. Confirm that you want to delete a published scorecard.")
    is_site_admin = "superadmin" in roles or "superadmin" in upload_roles
    upload_club = _selected_club(store, upload_club_id or current_club_id)
    if not is_site_admin:
        allowed_clubs = set(_user_club_ids(store, user_row, current_club_id)) | {
            str(user_row["primary_club_id"] or ""),
            str(current_club_id or ""),
        }
        if upload_club_id not in allowed_clubs or not upload_roles.intersection({"club_admin"}):
            raise HTTPException(status_code=403, detail="This incomplete scorecard belongs to a different club.")
    if not is_site_admin and not archive_belongs_to_club(upload, upload_club, store.get("clubs", []), store.get("members", []), store.get("fixtures", [])):
        raise HTTPException(status_code=403, detail="This archive belongs to a different club.")
    file_path = str(upload.get("file_path") or "").strip()
    if file_path:
        try:
            resolved_path = Path(file_path).resolve()
            upload_dir = UPLOAD_DIR.resolve()
            if resolved_path.exists() and (resolved_path == upload_dir or upload_dir in resolved_path.parents):
                resolved_path.unlink()
                logger.debug("Deleted archive upload file from disk.", extra={"file_path": str(resolved_path)})
        except Exception as exc:
            logger.warning("Could not delete archive upload file from disk: %s", exc)

    store["archive_uploads"] = [
        item for item in store.get("archive_uploads", []) if str(item.get("id") or "").strip() != upload_id
    ]
    store["duplicate_uploads"] = [
        item
        for item in store.get("duplicate_uploads", [])
        if str(item.get("original_upload_id") or "").strip() != upload_id
        and str(item.get("duplicate_upload_id") or "").strip() != upload_id
    ]
    save_store(store)
    refreshed = load_store()
    return {
        "message": f"{upload['file_name']} removed from archives.",
        "dashboard": current_dashboard(refreshed, upload_club.get("id", "")),
    }


# ---------------------------------------------------------------------------
# Database backups (Amit, Nov 5 2026: "We need a backup plan for the DB, once we go live we cannot afford to
# lose the data"). README "Database backups".
#   * a verified copy of the live SQLite file is made at start-up and every BACKUP_EVERY_HOURS (default 6),
#     with SQLite's own backup API (safe while the app is running), checked with PRAGMA integrity_check, and
#     kept in BACKUP_DIR (Azure: next to the live file on /home, which survives restarts and deploys)
#   * kept: the newest 48 copies + one per day for 30 days
#   * optional off-site copy: set CRICKETCLUBAPP_BACKUP_BLOB_SAS to an Azure Blob container SAS URL and every
#     backup is also uploaded there (survives even if the App Service storage is lost)
#   * the live file is checked at start-up; if it is damaged, site admins are told straight away
#   * superadmin page /admin/backups: list, "Back up now", download any copy
# ---------------------------------------------------------------------------
BACKUP_DIR = Path(os.getenv("CRICKETCLUBAPP_BACKUP_DIR", str(DATABASE_FILE.parent / "backups")))
BACKUP_EVERY_HOURS = max(1.0, float(os.getenv("CRICKETCLUBAPP_BACKUP_EVERY_HOURS", "6") or 6))
BACKUP_KEEP_RECENT = 48
BACKUP_KEEP_DAYS = 30
_BACKUP_LOCK = threading.Lock()
_BACKUP_NAME_RE = re.compile(r"^cricketclubapp-\d{8}T\d{6}Z-[a-z0-9-]{1,30}\.db$")


def _database_is_healthy(path: Path) -> tuple[bool, str]:
    try:
        connection = sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=30)
        try:
            result = [str(row[0]) for row in connection.execute("PRAGMA integrity_check").fetchall()]
            tables = connection.execute("SELECT COUNT(*) FROM sqlite_master WHERE type = 'table'").fetchone()[0]
        finally:
            connection.close()
    except sqlite3.DatabaseError as exc:
        return False, str(exc)
    if result != ["ok"]:
        return False, "; ".join(result[:5])
    if not tables:
        return False, "no tables"
    return True, "ok"


def _upload_backup_offsite(path: Path) -> str:
    """PUT the copy to an Azure Blob container SAS URL (CRICKETCLUBAPP_BACKUP_BLOB_SAS). Returns "" or the error."""
    sas = str(os.getenv("CRICKETCLUBAPP_BACKUP_BLOB_SAS") or "").strip()
    if not sas:
        return "off-site copy not set up"
    base, _, query = sas.partition("?")
    url = f"{base.rstrip('/')}/{path.name}" + (f"?{query}" if query else "")
    try:
        import httpx

        with path.open("rb") as handle:
            response = httpx.put(url, content=handle.read(), headers={"x-ms-blob-type": "BlockBlob"}, timeout=120)
        if response.status_code >= 300:
            return f"off-site upload failed ({response.status_code})"
        return ""
    except Exception as exc:  # never let an off-site problem stop the local backup
        return f"off-site upload failed ({exc.__class__.__name__})"


def _prune_backups() -> None:
    files = sorted(BACKUP_DIR.glob("cricketclubapp-*.db"), key=lambda item: item.name, reverse=True)
    keep: set[str] = {item.name for item in files[:BACKUP_KEEP_RECENT]}
    days_seen: set[str] = set()
    cutoff = (datetime.utcnow() - timedelta(days=BACKUP_KEEP_DAYS)).strftime("%Y%m%d")
    for item in files:
        day = item.name.split("-")[1][:8]
        if day >= cutoff and day not in days_seen:
            days_seen.add(day)
            keep.add(item.name)
    for item in files:
        if item.name not in keep:
            try:
                item.unlink()
            except OSError:
                logger.warning("Couldn't remove old backup %s", item.name)


def make_database_backup(reason: str = "scheduled") -> dict[str, Any]:
    """A verified copy of the live database. Returns {ok, file, bytes, offsite, error}."""
    reason = re.sub(r"[^a-z0-9-]+", "-", str(reason or "manual").lower()).strip("-")[:30] or "manual"
    if not _BACKUP_LOCK.acquire(timeout=300):
        return {"ok": False, "error": "another backup is running"}
    try:
        BACKUP_DIR.mkdir(parents=True, exist_ok=True)
        if not DATABASE_FILE.exists():
            return {"ok": False, "error": "no database file yet"}
        name = f"cricketclubapp-{datetime.utcnow().strftime('%Y%m%dT%H%M%SZ')}-{reason}.db"
        target = BACKUP_DIR / name
        partial = BACKUP_DIR / (name + ".partial")
        _sqlite_copy(DATABASE_FILE, partial)
        # A backup is a single self-contained file: switch the copy to the rollback journal so restoring it on
        # Azure Files never brings WAL (and its -wal/-shm side files) back.
        connection = sqlite3.connect(str(partial), timeout=60)
        try:
            connection.execute("PRAGMA journal_mode=DELETE")
        finally:
            connection.close()
        for side in (Path(str(partial) + "-wal"), Path(str(partial) + "-shm")):
            side.unlink(missing_ok=True)
        healthy, detail = _database_is_healthy(partial)
        if not healthy:
            partial.unlink(missing_ok=True)
            logger.error("Backup NOT kept: the copy failed its check (%s). The live database may be damaged.", detail)
            _notify_site_admins("system", "Database backup failed its check", f"The copy didn't pass the integrity check: {detail}. Check the live database now.", "/admin/backups")
            return {"ok": False, "error": f"copy failed its check: {detail}"}
        partial.replace(target)
        offsite = _upload_backup_offsite(target)
        _prune_backups()
        logger.info("Database backup %s (%s bytes). %s", name, target.stat().st_size, offsite or "Off-site copy uploaded.")
        return {"ok": True, "file": name, "bytes": target.stat().st_size, "offsite": offsite or "uploaded"}
    except Exception as exc:
        logger.exception("Database backup failed")
        return {"ok": False, "error": str(exc)}
    finally:
        _BACKUP_LOCK.release()


def _list_database_backups() -> list[dict[str, Any]]:
    if not BACKUP_DIR.exists():
        return []
    rows = []
    for item in sorted(BACKUP_DIR.glob("cricketclubapp-*.db"), key=lambda path: path.name, reverse=True):
        stat = item.stat()
        rows.append({"file": item.name, "bytes": stat.st_size, "created_at": datetime.utcfromtimestamp(stat.st_mtime).strftime("%Y-%m-%dT%H:%M:%SZ")})
    return rows


def _backup_loop() -> None:
    """Start-up check + backup, then a backup every BACKUP_EVERY_HOURS."""
    try:
        if DATABASE_FILE.exists():
            healthy, detail = _database_is_healthy(DATABASE_FILE)
            if not healthy:
                logger.error("The live database failed its start-up check: %s", detail)
                _notify_site_admins("system", "The database failed its start-up check", f"{detail}. Restore the newest good copy from /admin/backups (README 'Database backups').", "/admin/backups")
            else:
                make_database_backup("startup")
    except Exception:
        logger.exception("Start-up database check failed")
    while True:
        time_module.sleep(BACKUP_EVERY_HOURS * 3600)
        make_database_backup("scheduled")


@app.get("/api/admin/backups")
def admin_backups(x_auth_token: str | None = Header(default=None)) -> dict[str, Any]:
    _require_superadmin(x_auth_token)
    healthy, detail = _database_is_healthy(DATABASE_FILE) if DATABASE_FILE.exists() else (False, "no database file")
    return {
        "backups": _list_database_backups(),
        "backup_dir": str(BACKUP_DIR),
        "every_hours": BACKUP_EVERY_HOURS,
        "offsite": bool(str(os.getenv("CRICKETCLUBAPP_BACKUP_BLOB_SAS") or "").strip()),
        "live_database": {"healthy": healthy, "detail": detail, "bytes": DATABASE_FILE.stat().st_size if DATABASE_FILE.exists() else 0},
    }


@app.post("/api/admin/backups")
def admin_backup_now(x_auth_token: str | None = Header(default=None)) -> dict[str, Any]:
    user_row, _ = _require_superadmin(x_auth_token)
    result = make_database_backup("manual")
    _audit_event("database.backup", "database", result.get("file") or "", actor=user_row, details=result, source="api")
    if not result.get("ok"):
        raise HTTPException(status_code=500, detail=result.get("error") or "Backup failed.")
    return result


@app.get("/api/admin/backups/{file_name}")
def admin_backup_download(file_name: str, request: Request, x_auth_token: str | None = Header(default=None)) -> Response:
    token = _auth_token_from_request(request, x_auth_token)
    _require_superadmin(token)
    if not _BACKUP_NAME_RE.match(file_name):
        raise HTTPException(status_code=404, detail="Backup not found.")
    path = BACKUP_DIR / file_name
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Backup not found.")
    return FileResponse(path, media_type="application/octet-stream", filename=file_name)


@app.get("/admin/backups")
def admin_backups_page(request: Request) -> Response:
    """Superadmin page: database health, the backups kept, "Back up now" and downloads."""
    session = _require_page_session(request)
    if isinstance(session, RedirectResponse):
        return session
    try:
        _require_superadmin(_auth_token_from_request(request))
    except HTTPException:
        return RedirectResponse("/admin-center", status_code=303)
    healthy, detail = _database_is_healthy(DATABASE_FILE) if DATABASE_FILE.exists() else (False, "no database file")
    rows = "".join(
        f"<tr><td>{html.escape(item['file'])}</td><td>{item['created_at']}</td><td>{item['bytes'] // 1024:,} KB</td>"
        f"<td><a href=\"/api/admin/backups/{html.escape(item['file'])}\">Download</a></td></tr>"
        for item in _list_database_backups()
    ) or '<tr><td colspan="4">No backups yet.</td></tr>'
    offsite = "on (Azure Blob)" if str(os.getenv("CRICKETCLUBAPP_BACKUP_BLOB_SAS") or "").strip() else "not set up yet (CRICKETCLUBAPP_BACKUP_BLOB_SAS)"
    page = f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="UTF-8" /><meta name="viewport" content="width=device-width, initial-scale=1" />
<title>Database backups</title>
<style>
body {{ font-family: Roboto, system-ui, sans-serif; margin: 0; padding: 16px; background: #f8fafc; color: #0f172a; }}
main {{ max-width: 900px; margin: 0 auto; }}
.card {{ background: #fff; border: 1px solid #e2e8f0; border-radius: 14px; padding: 16px; margin-bottom: 14px; }}
table {{ width: 100%; border-collapse: collapse; font-size: 0.92rem; }}
td, th {{ text-align: left; padding: 8px 6px; border-bottom: 1px solid #e2e8f0; overflow-wrap: anywhere; }}
.ok {{ color: #15803d; font-weight: 700; }} .bad {{ color: #b91c1c; font-weight: 700; }}
button {{ min-height: 44px; padding: 0 16px; border-radius: 12px; border: 0; background: #0f172a; color: #fff; font-weight: 700; cursor: pointer; }}
</style></head><body><main>
<p><a href="/admin-center">‹ Admin Center</a></p>
<h1>Database backups</h1>
<section class="card">
<p>Live database: <span class="{'ok' if healthy else 'bad'}">{'healthy' if healthy else 'DAMAGED: ' + html.escape(detail)}</span></p>
<p>Automatic backups: at start-up and every {BACKUP_EVERY_HOURS:g} hours, each one checked before it is kept. Kept: newest {BACKUP_KEEP_RECENT} + one per day for {BACKUP_KEEP_DAYS} days.</p>
<p>Off-site copy: {html.escape(offsite)}</p>
<button type="button" id="backupNow">Back up now</button> <span id="backupMsg" role="status"></span>
</section>
<section class="card"><table><thead><tr><th>File</th><th>Made (UTC)</th><th>Size</th><th></th></tr></thead><tbody>{rows}</tbody></table></section>
</main>
<script>
document.getElementById("backupNow").addEventListener("click", async (event) => {{
  const msg = document.getElementById("backupMsg");
  event.target.disabled = true; msg.textContent = "Backing up…";
  try {{
    const token = localStorage.getItem("cricketClubAppAuthToken") || "";
    const response = await fetch("/api/admin/backups", {{ method: "POST", headers: {{ "X-Auth-Token": token }} }});
    const data = await response.json().catch(() => ({{}}));
    if (!response.ok) throw new Error(data.detail || "Backup failed.");
    msg.textContent = "Saved " + data.file; setTimeout(() => location.reload(), 900);
  }} catch (error) {{ msg.textContent = error.message; event.target.disabled = false; }}
}});
</script></body></html>"""
    return HTMLResponse(page)


if __name__ == "__main__":
    import socket
    import sys

    import uvicorn

    _port = int(os.getenv("PORT", os.getenv("WEBSITES_PORT", "8090")))
    # Two copies of the app on one port (an old window still open) answer requests in turn on Windows, and the
    # old copy doesn't know about new matches: "Match not found." (Dhruvika, Oct 30). Refuse to start a second one.
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as _probe:
        _probe.settimeout(1)
        if _probe.connect_ex(("127.0.0.1", _port)) == 0:
            print(f"\nThe app is already running on port {_port} in another window.")
            print("Close that window (or press Ctrl+C in it) and then start the app again.\n")
            sys.exit(1)

    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=_port,
        log_level="info",
    )
