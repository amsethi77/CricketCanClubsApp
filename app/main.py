import hashlib
import json
import html
import os
import re
import secrets
import sqlite3
from urllib import request
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any


from fastapi import FastAPI, File, Form, Header, HTTPException, Request, Response, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

import sqlite3
import logging

logger = logging.getLogger("CricketClubApp")

if not logger.handlers:
    logging.basicConfig(
        level=logging.DEBUG,
        format="%(asctime)s [%(levelname)s] [%(name)s] %(message)s",
    )

try:
    from cricket_brain import answer_question, get_llm_status
    from cricket_store import (
        BASE_DIR,
        CACHE_FILE,
        DATABASE_FILE,
        DASHBOARD_CACHE_FILE,
        DUPLICATE_DIR,
        UPLOAD_DIR,
        archive_record_from_file,
        build_dashboard,
        canonical_phone,
        canonical_archive_uploads,
        create_duplicate_record_from_bytes,
        default_scorecard,
        default_match_scorebook,
        auto_register_players_from_archive,
        club_season_year,
        extract_archive_by_id,
        fixture_season_year,
        get_archive_or_404,
        get_match_or_404,
        load_store,
        member_initials,
        now_iso,
        normalize_scorebook_ball,
        _resolve_archive_club,
        reset_score_data,
        resolve_member_name,
        save_store,
        scoped_store_for_club,
        summarize_innings_scorebook,
        sync_fixture_scorecard_from_scorebook,
    )
except ModuleNotFoundError:
    from app.cricket_brain import answer_question, get_llm_status
    from app.cricket_store import (
        BASE_DIR,
        CACHE_FILE,
        DATABASE_FILE,
        DASHBOARD_CACHE_FILE,
        DUPLICATE_DIR,
        UPLOAD_DIR,
        archive_record_from_file,
        build_dashboard,
        canonical_phone,
        canonical_archive_uploads,
        create_duplicate_record_from_bytes,
        default_scorecard,
        default_match_scorebook,
        auto_register_players_from_archive,
        club_season_year,
        extract_archive_by_id,
        fixture_season_year,
        get_archive_or_404,
        get_match_or_404,
        load_store,
        member_initials,
        now_iso,
        normalize_scorebook_ball,
        _resolve_archive_club,
        reset_score_data,
        resolve_member_name,
        save_store,
        scoped_store_for_club,
        summarize_innings_scorebook,
        sync_fixture_scorecard_from_scorebook,
    )


STATIC_DIR = BASE_DIR / "static"


app = FastAPI(
    title="Heartlake Cricket Club",
    version="0.2.0",
    description="Local website for club operations, scoring, availability, archive recovery, and AI-assisted queries.",
)

MIN_SEASON_SETUP_YEAR = 2026

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

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

def normalize_name(name: str) -> str:
    return (name or "").strip().lower()

def _set_auth_cookies(response: Response, token: str, club_id: str = "") -> None:
    response.set_cookie("heartlakeAuthToken", token, httponly=False, samesite="lax", path="/")
    response.set_cookie("heartlakePrimaryClubId", club_id or "", httponly=False, samesite="lax", path="/")


def _clear_auth_cookies(response: Response) -> None:
    response.delete_cookie("heartlakeAuthToken", path="/")
    response.delete_cookie("heartlakePrimaryClubId", path="/")


def _auth_token_from_request(request: Request, x_auth_token: str | None = None) -> str:
    token = str(x_auth_token or "").strip()
    if token:
        return token
    return str(request.cookies.get("heartlakeAuthToken") or "").strip()


def _clubs_page_html(request: Request, search: str = "", focus_club_id: str = "") -> HTMLResponse:
    store = load_store()
    token = _auth_token_from_request(request)
    current_club_id = focus_club_id or str(store.get("viewer_profile", {}).get("primary_club_id") or "")
    dashboard = current_dashboard(store, current_club_id)
    member_club_ids: list[str] = []
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
                    for archive in store.get("archive_uploads", []):
                        if year and str(archive.get("archive_year") or "").strip() != str(year).strip():
                            continue
                        if club_id and str(archive.get("club_id") or "").strip() != str(club_id).strip():
                            continue
                        for performance in archive.get("suggested_performances", []) or []:
                            if not _performance_matches_member(performance.get("player_name") or ""):
                                continue
                            runs = int(performance.get("runs") or 0)
                            highest = runs if highest is None else max(highest, runs)
                    return highest

                snapshot_stats = next(
                    (item for item in dashboard.get("member_summary_stats", []) if item.get("player_name") == member_name),
                    None,
                ) or next(
                    (item for item in dashboard.get("all_combined_player_stats", []) if item.get("player_name") == member_name),
                    {"runs": 0, "wickets": 0, "catches": 0},
                )
                all_fixtures = dashboard.get("all_fixtures", []) or []
                appearances = [
                    fixture
                    for fixture in all_fixtures
                    if any((performance.get("player_name") or "") == member_name for performance in fixture.get("performances", []))
                ]
                appearances.sort(key=lambda item: str(item.get("date") or ""), reverse=True)
                last_game = appearances[0] if appearances else None
                upcoming_games = [
                    fixture
                    for fixture in all_fixtures
                    if str(fixture.get("status") or "").lower() == "scheduled"
                    and any((performance.get("player_name") or "") == member_name for performance in fixture.get("performances", []))
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
                            and (
                                str(item.get("player_name") or "").strip() == member_name
                                or str(item.get("player_name") or "").strip().lower() == member_name.lower()
                            )
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
          <small>{html.escape(str(club.get('short_name', '') or ''))}</small>
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
    topbar = """
      <header class="page-topbar">
        <nav class="top-nav">
          <a href="/dashboard">Dashboard</a>
          <a href="/clubs" aria-current="page">Clubs</a>
          <a href="/season-setup">Season setup</a>
          <a href="/player-availability">Availability</a>
          <a href="/player-profile">Profile</a>
        </nav>
        <div class="topbar-actions">
          <a id="dashboardLink" class="primary-link" href="/dashboard">Open club dashboard</a>
          <a class="secondary-button" href="/signout">Sign out</a>
        </div>
      </header>
    """
    body = f"""
    <!DOCTYPE html>
    <html lang="en">
      <head>
        <meta charset="UTF-8" />
        <meta name="viewport" content="width=device-width, initial-scale=1.0" />
        <title>Select Club · Heartlake Clubs</title>
        <link rel="stylesheet" href="/assets/styles.css?v=20260424e" />
      </head>
      <body>
        <div class="page-shell">
          {topbar}
          <section class="panel onboarding-panel">
            <div class="stack-card">
              <p class="section-kicker">Club Selection</p>
              <h1 id="clubsGreeting">Welcome, {html.escape(viewer_display_name)}</h1>
              <p id="selectedClubSummary" class="lede">Choose your current club. Your primary club is the default.</p>
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
                <a id="seasonSetupLink" class="primary-link" href="/season-setup">Season setup</a>
                <a id="playerAvailabilityLink" class="primary-link" href="/player-availability">Player availability</a>
                <a id="playerProfileLink" class="primary-link" href="/player-profile">Player profile</a>
              </div>
            </div>
          </section>
        </div>
        <script src="/assets/multipage.js?v=20260424d"></script>
        <script src="/assets/clubs.js?v=20260424d"></script>
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
    team_name: str = "Heartlake"
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


class ChatRequest(BaseModel):
    question: str
    session_id: str | None = None
    history: list[dict[str, str]] = []
    focus_club_id: str | None = None


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
    primary_club_id: str = ""
    member_name: str = ""


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
    role: str = ""
    batting_style: str = ""
    bowling_style: str = ""
    phone: str = ""
    email: str = ""
    notes: str = ""
    aliases: list[str] | str = []
    team_memberships: list[str] | str = []
    primary_club_id: str = ""


def current_dashboard(store: dict[str, Any], focus_club_id: str | None = None) -> dict[str, Any]:
    return build_dashboard(store, get_llm_status(), focus_club_id or "")


def _selected_club(store: dict[str, Any], focus_club_id: str | None = None) -> dict[str, Any]:
    requested = str(
        focus_club_id
        or store.get("viewer_profile", {}).get("primary_club_id")
        or ""
    ).strip()

    logger.debug("🔍 Selecting club → requested=%s", requested)

    club = next(
        (
            club
            for club in store.get("clubs", [])
            if str(club.get("id") or "").strip() == requested
        ),
        None,
    )

    if not club:
        logger.warning("⚠️ Club not found → fallback used")

    return club or store.get("club", {})


def _auth_connection() -> sqlite3.Connection:
    logger.debug("🗄️ Opening DB connection: %s", DATABASE_FILE)
    DATABASE_FILE.parent.mkdir(exist_ok=True)
    connection = sqlite3.connect(DATABASE_FILE)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


DEFAULT_ROLE_PERMISSIONS: dict[str, dict[str, str]] = {
    "player": {},
    "captain": {
        "view_admin": "View admin center and club controls",
        "manage_club": "Update club-level details",
        "manage_fixtures": "Create and edit fixtures",
    },
    "club_admin": {
        "view_admin": "View admin center and club controls",
        "manage_club": "Update club-level details",
        "manage_fixtures": "Create and edit fixtures",
        "manage_scorecards": "Review and approve scorecards",
        "manage_players": "Update player records",
        "manage_roles": "Assign club roles",
    },
    "superadmin": {
        "view_admin": "View admin center and club controls",
        "manage_club": "Update club-level details",
        "manage_fixtures": "Create and edit fixtures",
        "manage_scorecards": "Review and approve scorecards",
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


def ensure_auth_schema() -> None:
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
              PRIMARY KEY (user_id, club_id),
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
            """
        )
        _seed_role_catalog(connection)


def _password_hash(password: str) -> str:
    return hashlib.sha256(password.encode("utf-8")).hexdigest()


def _role_permissions(connection: sqlite3.Connection, role_name: str) -> set[str]:
    rows = connection.execute(
        "SELECT permission FROM app_role_permissions WHERE role_name = ?",
        (role_name,),
    ).fetchall()
    return {str(row["permission"] or "").strip() for row in rows if str(row["permission"] or "").strip()}


def _effective_role_name(user_row: sqlite3.Row, current_club_id: str = "") -> str:
    role_name = str(user_row["role"] or "player").strip() or "player"
    club_id = str(current_club_id or "").strip()
    if not club_id:
        return role_name
    with _auth_connection() as connection:
        row = connection.execute(
            """
            SELECT role_name
            FROM app_user_club_roles
            WHERE user_id = ? AND club_id = ?
            """,
            (int(user_row["id"]), club_id),
        ).fetchone()
        if row and row["role_name"]:
            return str(row["role_name"]).strip() or role_name
    return role_name


def _user_permissions(user_row: sqlite3.Row, current_club_id: str = "") -> set[str]:
    role_name = _effective_role_name(user_row, current_club_id)
    with _auth_connection() as connection:
        permissions = _role_permissions(connection, role_name)
        if role_name == "superadmin":
            permissions |= {
                "view_admin",
                "manage_club",
                "manage_fixtures",
                "manage_scorecards",
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
    permissions = sorted(_user_permissions(user_row, current_club_id))
    return {
        "id": int(user_row["id"]),
        "display_name": user_row["display_name"] or "",
        "mobile": user_row["mobile"] or "",
        "email": user_row["email"] or "",
        "role": user_row["role"] or "player",
        "effective_role": effective_role,
        "permissions": permissions,
        "member_id": user_row["member_id"] or "",
        "primary_club_id": user_row["primary_club_id"] or "",
        "current_club_id": current_club_id or user_row["primary_club_id"] or "",
    }

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


def _auth_user_from_token(token: str | None) -> tuple[sqlite3.Row, str]:
    ensure_auth_schema()
    if not token:
        raise HTTPException(status_code=401, detail="Sign in first.")
    with _auth_connection() as connection:
        row = connection.execute(
            """
            SELECT u.*, s.current_club_id
            FROM app_auth_sessions s
            JOIN app_users u ON u.id = s.user_id
            WHERE s.token = ?
            """,
            (token,),
        ).fetchone()
    if not row:
        raise HTTPException(status_code=401, detail="Session expired. Sign in again.")
    return row, row["current_club_id"] or row["primary_club_id"] or ""


def _require_admin(token: str | None) -> tuple[sqlite3.Row, str]:
    return _require_permission(token, "view_admin")


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


def _club_choices(store: dict[str, Any]) -> list[dict[str, str]]:
    return [
        {
            "id": str(club.get("id") or ""),
            "name": str(club.get("name") or ""),
            "short_name": str(club.get("short_name") or ""),
            "season": str(club.get("season") or ""),
        }
        for club in store.get("clubs", [])
    ]


def _sorted_club_choices(store: dict[str, Any], preferred_club_id: str = "") -> list[dict[str, str]]:
    return sorted(
        _club_choices(store),
        key=lambda club: (
            0 if str(club.get("id") or "").strip() == str(preferred_club_id or "").strip() else 1,
            str(club.get("name") or ""),
        ),
    )


def _primary_club_for_member(store: dict[str, Any], member: dict[str, Any]) -> dict[str, Any]:
    for membership in member.get("team_memberships", []):
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

def normalize_name(name: str) -> str:
    return (name or "").strip().lower()

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

    batting_team = _string_value(first_innings.get("batting_team") or match_block.get("teams", {}).get("batting"))
    bowling_team = _string_value(match_block.get("teams", {}).get("bowling"))
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
    else:
        fallback = _parse_imported_text_fallback(store, raw_text)
        draft = fallback["draft_scorecard"]
        suggested = fallback["suggested_performances"]

    return {
        "draft_scorecard": draft,
        "suggested_performances": suggested,
        "raw_extracted_text": raw_text[:12000],
        "ocr_engine": "manual-import",
        "ocr_pipeline": "Imported from ChatGPT/manual extraction",
        "confidence": "Imported review",
        "extracted_summary": f"Imported pasted extraction with {len(suggested)} player score entries for review.",
    }


@app.get("/")
def root() -> FileResponse:
    return _page_response("signin.html")


@app.on_event("startup")
def startup_tasks() -> None:
    ensure_auth_schema()


@app.get("/signin")
def signin_page() -> FileResponse:
    return _page_response("signin.html")


def _admin_center_html(request: Request) -> HTMLResponse:
    user_row, current_club_id = _auth_user_from_token(_auth_token_from_request(request))
    if "view_admin" not in _user_permissions(user_row, current_club_id):
        raise HTTPException(status_code=403, detail="Only club administrators can open the admin center.")
    store = load_store()
    club = _selected_club(store, current_club_id)
    role = _effective_role_name(user_row, current_club_id)
    review_uploads: list[dict[str, Any]] = []
    for upload in canonical_archive_uploads(store.get("archive_uploads", [])):
        status = str(upload.get("status") or "").strip().lower()
        if status in {"approved", "applied to match", "deleted"}:
            continue
        inferred_club = _resolve_archive_club(upload, store.get("clubs", []))
        resolved_club_id = str(upload.get("club_id") or (inferred_club.get("id") if inferred_club else "") or "").strip()
        resolved_club_name = str(upload.get("club_name") or (inferred_club.get("name") if inferred_club else "") or "Unassigned").strip() or "Unassigned"
        if role != "superadmin" and resolved_club_id != str(club.get("id") or "").strip():
            continue
        review_uploads.append(
            {
                **upload,
                "resolved_club_id": resolved_club_id,
                "resolved_club_name": resolved_club_name,
            }
        )
    club_options = "\n".join(
        f'<option value="{html.escape(item["id"])}">{html.escape(item["name"])} · {html.escape(item["season"] or "Season TBD")}</option>'
        for item in _sorted_club_choices(store, current_club_id)
    )
    review_groups: dict[str, list[dict[str, Any]]] = {}
    for upload in review_uploads:
        key = f'{upload.get("resolved_club_id") or ""}::{upload.get("resolved_club_name") or "Unassigned"}'
        review_groups.setdefault(key, []).append(upload)
    review_queue_html = ""
    if review_uploads:
        review_queue_html = "".join(
            f"""
            <section class="admin-review-group">
              <div class="panel-head compact-head">
                <div>
                  <p class="section-kicker">Club review queue</p>
                  <h3>{html.escape(group[0].get('resolved_club_name') or 'Unassigned')} · {len(group)}</h3>
                </div>
              </div>
              <div class="archive-list">
                {''.join(
                    f'''
                      <article class="detail-card" data-admin-upload="{html.escape(str(upload.get('id') or ''))}">
                        <strong>{html.escape(upload.get('file_name') or '')}</strong>
                        <p>{html.escape(upload.get('club_name') or upload.get('resolved_club_name') or 'Club TBD')} · {html.escape(upload.get('season') or 'Season TBD')}</p>
                        <small>{html.escape(upload.get('archive_date') or 'Date TBD')} · {html.escape(upload.get('status') or 'Pending review')}</small>
                        <p>{html.escape(upload.get('extracted_summary') or 'Review the extracted draft before approving.')}</p>
                        <label class="stack-label">
                          Reviewed extraction JSON
                          <textarea class="admin-review-text" rows="10" spellcheck="false">{html.escape(json.dumps({
                              "meta": {
                                  "source": upload.get("ocr_engine") or "manual-review",
                                  "confidence": upload.get("confidence") or "review",
                                  "status": upload.get("status") or "Pending review",
                              },
                              "archive": {
                                  "id": upload.get("id"),
                                  "file_name": upload.get("file_name"),
                                  "season": upload.get("season"),
                                  "club_name": upload.get("club_name") or upload.get("resolved_club_name") or "Unassigned",
                                  "archive_date": upload.get("archive_date"),
                                  "archive_year": upload.get("archive_year"),
                              },
                              "draft_scorecard": upload.get("draft_scorecard") or {},
                              "suggested_performances": upload.get("suggested_performances") or [],
                              "raw_extracted_text": upload.get("raw_extracted_text") or "",
                          }, indent=2))}</textarea>
                        </label>
                        <div class="inline-actions">
                          <button class="secondary-button" type="button" data-action="extract">Re-extract</button>
                          <button class="secondary-button" type="button" data-action="save">Save review</button>
                          <button class="primary-button" type="button" data-action="approve">Approve</button>
                          <button class="secondary-button" type="button" data-action="delete">Delete</button>
                        </div>
                      </article>
                    '''
                    for upload in group
                )}
              </div>
            </section>
            """
            for group in review_groups.values()
        )
    else:
        review_queue_html = '<p class="empty-state">No archives match this club or search.</p>'
    body = f"""
    <!DOCTYPE html>
    <html lang="en">
      <head>
        <meta charset="UTF-8" />
        <meta name="viewport" content="width=device-width, initial-scale=1.0" />
        <title>Admin Center · Heartlake Clubs</title>
        <link rel="stylesheet" href="/assets/styles.css?v=20260423b" />
      </head>
      <body>
        <div class="page-shell">
          <header class="page-topbar">
            <nav class="top-nav">
              <a href="/dashboard">Dashboard</a>
              <a href="/clubs">Clubs</a>
              <a href="/season-setup">Season setup</a>
              <a href="/player-availability">Availability</a>
              <a href="/player-profile">Profile</a>
              <a href="/admin-center" aria-current="page">Admin center</a>
            </nav>
            <div class="topbar-actions">
              <a class="primary-link" href="/dashboard">Back to dashboard</a>
              <a class="secondary-button" href="/signout">Sign out</a>
            </div>
          </header>
          <section class="panel onboarding-panel">
            <div class="stack-card">
              <p class="section-kicker">Admin Center</p>
              <h1>{html.escape(club.get('name', 'Selected club'))} control room</h1>
              <p class="lede">Select a club, review that club’s data, edit fixtures, and manage archives from one place.</p>
              <div id="adminCenterStatus" class="status-banner" hidden></div>
              <div class="summary-grid compact-summary-grid" id="adminClubStats"></div>
              <div class="toolbar-actions">
                <select id="adminClubSelect">{club_options}</select>
                <button id="adminLoadClubButton" class="secondary-button" type="button">Load club</button>
              </div>
              <div id="adminClubDetail" class="detail-stack"></div>
            </div>

            <div class="detail-stack">
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
            </div>
          </section>
        </div>
        <script src="/assets/multipage.js?v=20260429a"></script>
        <script src="/assets/admin_center.js?v=20260429a"></script>
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
def admin_center_page(request: Request) -> HTMLResponse:
    return _admin_center_html(request)


@app.get("/admin")
def admin_page_alias(request: Request) -> HTMLResponse:
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
              window.localStorage.setItem("heartlakeAuthToken", {safe_token});
              window.localStorage.setItem("heartlakePrimaryClubId", {safe_club_id});
              document.cookie = "heartlakeAuthToken=" + encodeURIComponent({safe_token}) + "; path=/; samesite=lax";
              document.cookie = "heartlakePrimaryClubId=" + encodeURIComponent({safe_club_id}) + "; path=/; samesite=lax";
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
def clubs_page(request: Request, search: str = "", focus_club_id: str = "") -> HTMLResponse:
    return _clubs_page_html(request, search, focus_club_id)


@app.post("/clubs/select")
def clubs_select(request: Request, club_id: str = Form(...), search: str = Form(default="")) -> Response:
    token = _auth_token_from_request(request)
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
    _auth_user_from_token(token)
    store = load_store()
    selected_club = _selected_club(store, club_id)
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
def signout_page() -> HTMLResponse:
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
              window.localStorage.removeItem("heartlakeAuthToken");
              window.localStorage.removeItem("heartlakePrimaryClubId");
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
def season_setup_page() -> FileResponse:
    return _page_response("season_setup.html")


@app.get("/player-availability")
def player_availability_page() -> FileResponse:
    return _page_response("player_availability.html")


@app.get("/player-profile")
def player_profile_page() -> FileResponse:
    return _page_response("player_profile.html")


@app.get("/dashboard")
def dashboard_page() -> FileResponse:
    return _page_response("index.html")


@app.get("/api/health")
def health() -> dict[str, Any]:
    return {"status": "ok", "llm": get_llm_status()}


@app.get("/api/dashboard")
def dashboard(request: Request, focus_club_id: str | None = None) -> dict[str, Any]:
    resolved_focus_club_id = (
        focus_club_id
        or str(request.cookies.get("heartlakePrimaryClubId") or "").strip()
        or None
    )
    return current_dashboard(load_store(), resolved_focus_club_id)


@app.get("/api/auth/options")
def auth_options() -> dict[str, Any]:
    store = load_store()
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
    return {
        "clubs": _sorted_club_choices(store, str(store.get("viewer_profile", {}).get("primary_club_id") or "")),
        "members": [
            {
                "id": member.get("id", ""),
                "name": member.get("name", ""),
                "full_name": member.get("full_name", ""),
                "team_name": member.get("team_name", ""),
            }
            for member in store.get("members", [])
            if str(member.get("id") or "").strip() not in linked_member_ids
            and normalize_name(str(member.get("name") or "")) not in linked_member_name_keys
            and normalize_name(str(member.get("full_name") or "")) not in linked_member_name_keys
        ],
        "roles": roles,
    }


@app.get("/api/auth/roles")
def auth_roles() -> dict[str, Any]:
    ensure_auth_schema()
    with _auth_connection() as connection:
        return {"roles": _role_catalog(connection)}

@app.post("/api/auth/register")
def register(request: RegisterRequest, response: Response) -> dict[str, Any]:
    ensure_auth_schema()

    logger.debug("🔵 [START] Register API called")

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
        role = (request.role or "player").strip().lower()
        member_roles = {"player", "captain", "club_admin", "admin"}

        # -----------------------------
        # ✅ NAME NORMALIZATION
        # -----------------------------
        raw_name = request.member_name or request.display_name or ""
        input_name = raw_name.strip()
        normalized_input = normalize_name(input_name)

        logger.debug("👤 Input → %s | normalized → %s", input_name, normalized_input)

        member = None
        member_id = None
        member_to_create = None  # 🔥 IMPORTANT

        # -----------------------------
        # ✅ MEMBER LOOKUP ONLY (NO CREATE)
        # -----------------------------
        if input_name:
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

            if member and normalize_name(input_name) != normalize_name(str(member.get("name") or "")):
                aliases = [str(alias or "").strip() for alias in (member.get("aliases") or []) if str(alias or "").strip()]
                if input_name not in aliases:
                    aliases.append(input_name)
                    member["aliases"] = aliases
                    save_store(store)

        # -----------------------------
        # ✅ PREPARE MEMBER (DO NOT SAVE YET)
        # -----------------------------
        if role in member_roles and not member:
            display_name = request.display_name.strip() or input_name or "Player"
            normalized_display = normalize_name(display_name)

            member_to_create = {
                "id": str(uuid.uuid4()),
                "name": display_name,
                "normalized_name": normalized_display,
                "full_name": display_name,
                "aliases": [],
                "created_at": now_iso(),
            }

            logger.debug("🆕 Prepared member (not saved yet) → %s", display_name)

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
                "SELECT id FROM app_users WHERE mobile = ? OR email = ?",
                (mobile or None, email or None),
            ).fetchone()

            if existing:
                raise HTTPException(status_code=409, detail="User already exists.")

            existing_user_for_member = None

            # -----------------------------
            # ✅ CREATE MEMBER NOW (SAFE POINT)
            # -----------------------------
            if member_to_create:
                store.setdefault("members", []).append(member_to_create)
                save_store(store)

                member = member_to_create
                logger.info("✅ Member created → %s", member["name"])

            if member:
                member_id = member.get("id")

            existing_user_for_member = _existing_user_for_member(connection, member_id or "")

            # -----------------------------
            # ✅ CREATE OR REUSE USER
            # -----------------------------
            if existing_user_for_member:
                user_id = int(existing_user_for_member["id"])
                connection.execute(
                    """
                    UPDATE app_users
                    SET display_name = ?, mobile = ?, email = ?, role = ?, member_id = ?
                    WHERE id = ?
                    """,
                    (
                        request.display_name.strip() or input_name or existing_user_for_member["display_name"],
                        mobile or None,
                        email or None,
                        role,
                        member_id,
                        user_id,
                    ),
                )
            else:
                cursor = connection.execute(
                    """
                    INSERT INTO app_users (
                      display_name, mobile, email, password_hash, role, member_id, primary_club_id, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        request.display_name.strip() or input_name or "User",
                        mobile or None,
                        email or None,
                        _password_hash(request.password.strip()),
                        role,
                        member_id,
                        None,
                        now_iso(),
                    ),
                )

                user_id = int(cursor.lastrowid)

            connection.execute(
                """
                INSERT INTO app_auth_sessions (token, user_id, current_club_id, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (token, user_id, None, now_iso()),
            )

            user_row = connection.execute(
                "SELECT * FROM app_users WHERE id = ?", (user_id,)
            ).fetchone()

        # -----------------------------
        # ✅ RESPONSE
        # -----------------------------
        _set_auth_cookies(response, token, "")

        logger.info("🎉 SUCCESS → user_id=%s", user_id)

        return {
            "token": token,
            "user": _auth_user_payload(user_row, ""),
            "member": member,
            "clubs": _sorted_club_choices(store, ""),
        }

    # -----------------------------
    # ❌ ERROR HANDLING (FIXED)
    # -----------------------------
    except sqlite3.IntegrityError as e:
        logger.warning("⚠️ Integrity error: %s", str(e))

        raise HTTPException(
            status_code=409,
            detail="Duplicate member or user."
        )

    except Exception:
        logger.exception("🔥 Register API FAILED")

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

    logger.debug("🔐 Signin attempt → identifier=%s player=%s", identifier, player_name)

    store = load_store()

    identifier_phone = "".join(filter(str.isdigit, identifier)) if identifier else ""
    identifier_email = identifier.lower() if "@" in identifier else ""

    with _auth_connection() as connection:
        user_row = None

        # ✅ STEP 1 — PASSWORD LOGIN
        if password:
            logger.debug("🔑 Trying password login")

            user_row = connection.execute(
                """
                SELECT * FROM app_users
                WHERE (mobile = ? OR lower(email) = lower(?))
                  AND password_hash = ?
                """,
                (identifier_phone or None, identifier_email or None, _password_hash(password)),
            ).fetchone()

            if user_row:
                logger.debug("✅ Password login success → user_id=%s", user_row["id"])

        # ✅ STEP 2 — DIRECT USER LOGIN (NO PASSWORD)
        if not user_row:
            logger.debug("📱 Trying direct user lookup")

            user_row = connection.execute(
                """
                SELECT * FROM app_users
                WHERE mobile = ? OR lower(email) = lower(?)
                ORDER BY id
                LIMIT 1
                """,
                (identifier_phone or None, identifier_email or None),
            ).fetchone()

            if user_row:
                logger.debug("✅ Direct user match → user_id=%s", user_row["id"])

        # ✅ STEP 3 — MEMBER NAME LOGIN
        if not user_row and player_name:
            logger.debug("🔍 Falling back to player name lookup")

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
                logger.debug("👤 Member matched → %s", member.get("name"))

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
                    logger.debug("♻️ Reusing existing user → id=%s", existing_user["id"])
                    user_row = existing_user

                else:
                    logger.debug("🆕 Creating user from member")

                    cursor = connection.execute(
                        """
                        INSERT INTO app_users (
                          display_name, mobile, email, password_hash, role, member_id, primary_club_id, created_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            member.get("full_name") or member.get("name"),
                            identifier_phone or None,
                            identifier_email or None,
                            _password_hash(secrets.token_urlsafe(24)),
                            "player",
                            member.get("id"),
                            primary_club.get("id") if primary_club else None,
                            now_iso(),
                        ),
                    )

                    user_row = connection.execute(
                        "SELECT * FROM app_users WHERE id = ?",
                        (int(cursor.lastrowid),),
                    ).fetchone()

        # ❌ FINAL FAILURE
        if not user_row:
            logger.warning("❌ Login failed")
            raise HTTPException(
                status_code=401,
                detail="Invalid sign-in. Use mobile/email or player name."
            )

        # ✅ CREATE SESSION
        token = secrets.token_urlsafe(24)
        current_club_id = user_row["primary_club_id"] or ""

        connection.execute(
            """
            INSERT INTO app_auth_sessions (token, user_id, current_club_id, created_at)
            VALUES (?, ?, ?, ?)
            """,
            (token, int(user_row["id"]), current_club_id or None, now_iso()),
        )

    logger.info("🎉 Login successful → user_id=%s", user_row["id"])

    _set_auth_cookies(response, token, current_club_id)

    return {
        "token": token,
        "user": _auth_user_payload(user_row, current_club_id),
        "clubs": _sorted_club_choices(store, current_club_id),
    }

@app.post("/signin/quick")
def signin_quick_form(
    identifier: str = Form(...),
    password: str = Form(default=""),
    player_name: str = Form(default=""),
) -> HTMLResponse:
    logger.debug(
        "🔐 Quick signin → identifier=%s player=%s",
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
            "✅ Quick signin success → user_id=%s club=%s",
            user.get("id"),
            club_id
        )

        # ✅ Create redirect response
        redirect = _signin_redirect_page(token, club_id)

        # ✅ Set cookies ONLY here (correct place)
        _set_auth_cookies(redirect, token, club_id)

        return redirect

    except HTTPException as exc:
        logger.warning("❌ Quick signin failed → %s", exc.detail)
        return _signin_error_page(str(exc.detail))

    except Exception:
        logger.exception("🔥 Quick signin unexpected error")
        return _signin_error_page("Unexpected error during sign-in")

@app.get("/api/auth/me")
def auth_me(x_auth_token: str | None = Header(default=None)) -> dict[str, Any]:
    user_row, current_club_id = _auth_user_from_token(x_auth_token)
    store = load_store()
    return {
        "user": _auth_user_payload(user_row, current_club_id),
        "clubs": _sorted_club_choices(store, current_club_id),
    }


@app.post("/api/auth/select-club")
def select_club(request: SelectClubRequest, x_auth_token: str | None = Header(default=None)) -> dict[str, Any]:
    user_row, _ = _auth_user_from_token(x_auth_token)
    store = load_store()
    selected_club = _selected_club(store, request.club_id)
    with _auth_connection() as connection:
        connection.execute(
            "UPDATE app_auth_sessions SET current_club_id = ? WHERE token = ?",
            (selected_club.get("id", "") or None, x_auth_token),
        )
    return {
        "user": _auth_user_payload(user_row, selected_club.get("id", "")),
        "club": selected_club,
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
    return current_dashboard(store, viewer_profile.get("primary_club_id"))


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
def season_setup_data(x_auth_token: str | None = Header(default=None)) -> dict[str, Any]:
    user_row, current_club_id = _auth_user_from_token(x_auth_token)
    store = load_store()
    club = _selected_club(store, current_club_id)
    scoped = scoped_store_for_club(store, club)
    fixtures = sorted(scoped.get("fixtures", []), key=lambda fixture: (str(fixture.get("date") or ""), str(fixture.get("opponent") or "")))
    season_years = sorted(
        {
            fixture_season_year(fixture)
            for fixture in fixtures
            if fixture_season_year(fixture) and int(fixture_season_year(fixture)) >= MIN_SEASON_SETUP_YEAR
        }
    )
    selected_year = season_years[-1] if season_years else str(MIN_SEASON_SETUP_YEAR)
    return {
        "user": _auth_user_payload(user_row, current_club_id),
        "club": club,
        "fixtures": fixtures,
        "season_years": season_years,
        "selected_year": selected_year,
        "clubs": _sorted_club_choices(store, club.get("id", "")),
    }


@app.post("/api/season-setup/fixtures")
def create_season_fixture(request: SeasonFixtureRequest, x_auth_token: str | None = Header(default=None)) -> dict[str, Any]:
    user_row, current_club_id = _require_permission(x_auth_token, "manage_fixtures")
    store = load_store()
    club = _selected_club(store, request.club_id or current_club_id)
    season_year = int(request.season_year)
    if season_year < MIN_SEASON_SETUP_YEAR:
        raise HTTPException(
            status_code=400,
            detail=f"Season setup is only available for {MIN_SEASON_SETUP_YEAR} and later.",
        )
    season_label = f"{season_year} Season"
    created_at = now_iso()

    new_fixture = {
        "id": str(uuid.uuid4())[:8],
        "club_id": club.get("id", ""),
        "club_name": club.get("name", ""),
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
        "scorebook": default_match_scorebook({"opponent": request.opponent.strip(), "details": {"overs": request.overs.strip() or "20"}}),
    }
    _touch_fixture_audit(new_fixture, user_row, created=True)
    store.setdefault("fixtures", []).append(new_fixture)
    save_store(store)
    return season_setup_data(x_auth_token)


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
    fixture.update(
        {
            "club_id": club.get("id", ""),
            "club_name": club.get("name", ""),
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
    return season_setup_data(x_auth_token)


@app.delete("/api/admin/clubs/{club_id}/fixtures/{fixture_id}")
def delete_season_fixture(
    club_id: str,
    fixture_id: str,
    x_auth_token: str | None = Header(default=None),
) -> dict[str, Any]:
    _require_permission(x_auth_token, "manage_fixtures")
    store = load_store()
    club = _selected_club(store, club_id)
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
    return season_setup_data(x_auth_token)


@app.get("/api/player/availability-data")
def player_availability_data(x_auth_token: str | None = Header(default=None)) -> dict[str, Any]:
    user_row, current_club_id = _auth_user_from_token(x_auth_token)
    store = load_store()
    club = _selected_club(store, current_club_id)
    scoped = scoped_store_for_club(store, club)
    active_year = club_season_year(club)
    fixtures = [
        fixture
        for fixture in scoped.get("fixtures", [])
        if (not active_year or fixture_season_year(fixture) == active_year) and fixture.get("status") != "Completed"
    ]
    fixtures.sort(key=lambda fixture: (str(fixture.get("date") or ""), str(fixture.get("opponent") or "")))
    member = _member_for_user(store, user_row)
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
    club = _selected_club(store, request.club_id or current_club_id)
    if str(match.get("club_id") or "").strip() and str(match.get("club_id") or "").strip() != str(club.get("id") or "").strip():
        raise HTTPException(status_code=403, detail="This match is not in your selected club.")
    match["availability_statuses"][member["name"]] = request.status
    if request.note.strip():
        match["availability_notes"][member["name"]] = request.note.strip()
    else:
        match["availability_notes"].pop(member["name"], None)
    save_store(store)
    return player_availability_data(x_auth_token)


@app.post("/api/player/season-availability")
def save_player_season_availability(
    request: PlayerSeasonAvailabilityRequest,
    x_auth_token: str | None = Header(default=None),
) -> dict[str, Any]:
    user_row, current_club_id = _auth_user_from_token(x_auth_token)
    store = load_store()
    club = _selected_club(store, request.club_id or current_club_id)
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
    return player_availability_data(x_auth_token)


@app.get("/api/player/profile-data")
def player_profile_data(x_auth_token: str | None = Header(default=None)) -> dict[str, Any]:
    user_row, current_club_id = _auth_user_from_token(x_auth_token)
    store = load_store()
    club = _selected_club(store, current_club_id)
    member = _member_for_user(store, user_row)
    return {
        "user": _auth_user_payload(user_row, current_club_id),
        "club": club,
        "member": member,
        "clubs": _sorted_club_choices(store, club.get("id", "")),
    }


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
    updates["role"] = str(updates.get("role", "") or "").strip()
    updates["batting_style"] = str(updates.get("batting_style", "") or "").strip()
    updates["bowling_style"] = str(updates.get("bowling_style", "") or "").strip()
    updates["notes"] = str(updates.get("notes", "") or "").strip()
    updates["age"] = int(updates.get("age", 0) or 0)
    updates["team_memberships"] = list(updates.get("team_memberships") or [])
    updates["aliases"] = list(updates.get("aliases") or [])
    selected_primary_club_id = str(updates.pop("primary_club_id", "") or "").strip()

    for key, value in updates.items():
        member[key] = value
    if member.get("team_memberships"):
        member["team_name"] = member["team_memberships"][0]

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

    return player_profile_data(x_auth_token)


@app.get("/api/cache-status")
def cache_status() -> dict[str, Any]:
    return {
        "store_cache": str(CACHE_FILE),
        "dashboard_cache": str(DASHBOARD_CACHE_FILE),
        "store_cache_exists": CACHE_FILE.exists(),
        "dashboard_cache_exists": DASHBOARD_CACHE_FILE.exists(),
    }


@app.post("/api/members")
def create_member(request: MemberCreateRequest, x_auth_token: str | None = Header(default=None)) -> dict[str, Any]:
    _require_permission(x_auth_token, "manage_players")
    store = load_store()
    phone = canonical_phone(request.phone)
    if phone and any(canonical_phone(member.get("phone", "")) == phone for member in store["members"]):
        raise HTTPException(status_code=409, detail="A player with this mobile number already exists.")
    aliases = request.aliases
    if isinstance(aliases, str):
        aliases = [alias.strip() for alias in aliases.split(",") if alias.strip()]
    team_memberships = request.team_memberships
    if isinstance(team_memberships, str):
        team_memberships = [team.strip() for team in team_memberships.split(",") if team.strip()]
    member = {
        "id": str(uuid.uuid4())[:8],
        "name": request.name,
        "full_name": request.full_name,
        "gender": _normalize_gender(request.gender),
        "team_name": request.team_name or "Heartlake",
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
    save_store(store)
    return current_dashboard(load_store())


@app.post("/api/members/{member_id}")
def update_member(member_id: str, request: MemberUpdateRequest, x_auth_token: str | None = Header(default=None)) -> dict[str, Any]:
    _require_permission(x_auth_token, "manage_players")
    store = load_store()
    member = next((item for item in store["members"] if item.get("id") == member_id), None)
    if not member:
        raise HTTPException(status_code=404, detail="Player not found.")

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
    return current_dashboard(load_store())


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
    return current_dashboard(load_store())


@app.post("/api/matches/{match_id}/availability")
def update_availability(match_id: str, request: AvailabilityUpdateRequest, x_auth_token: str | None = Header(default=None)) -> dict[str, Any]:
    user_row, current_club_id = _auth_user_from_token(x_auth_token)
    store = load_store()
    try:
        match = get_match_or_404(store, match_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))

    member = _member_for_user(store, user_row)
    if not member:
        raise HTTPException(status_code=400, detail="This signed-in account is not linked to a player profile.")
    effective_role = _effective_role_name(user_row, current_club_id)
    can_edit_other_availability = effective_role in {"captain", "superadmin"}
    requested_player_name = resolve_member_name(store, request.player_name) if request.player_name else ""
    player_name = member.get("name", "")
    if can_edit_other_availability and requested_player_name:
        player_name = requested_player_name
    elif requested_player_name and requested_player_name != player_name:
        raise HTTPException(status_code=403, detail="Only captains or superadmins can update another player's availability.")
    match["availability_statuses"][player_name] = request.status
    if request.note.strip():
        match["availability_notes"][player_name] = request.note.strip()
    else:
        match["availability_notes"].pop(player_name, None)
    _touch_fixture_audit(match, user_row)
    save_store(store)
    return current_dashboard(load_store(), request.club_id or match.get("club_id") or "")


@app.post("/api/matches/{match_id}/scorecard")
def update_scorecard(match_id: str, request: ScorecardUpdateRequest, x_auth_token: str | None = Header(default=None)) -> dict[str, Any]:
    user_row, _ = _require_permission(x_auth_token, "manage_scorecards")
    store = load_store()
    try:
        match = get_match_or_404(store, match_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))

    updates = request.model_dump(exclude_none=True)
    for key, value in updates.items():
        if key == "status":
            match["status"] = value
        else:
            match["scorecard"][key] = value
    _touch_fixture_audit(match, user_row)
    save_store(store)
    return current_dashboard(load_store())


@app.post("/api/matches/{match_id}/performances")
def add_performance(match_id: str, request: PerformanceCreateRequest, x_auth_token: str | None = Header(default=None)) -> dict[str, Any]:
    user_row, _ = _require_permission(x_auth_token, "manage_scorecards")
    store = load_store()
    try:
        match = get_match_or_404(store, match_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))

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
    user_row, _ = _require_permission(x_auth_token, "manage_scorecards")
    store = load_store()
    try:
        match = get_match_or_404(store, match_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))

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
def update_scorebook_setup(match_id: str, request: ScorebookSetupRequest, x_auth_token: str | None = Header(default=None)) -> dict[str, Any]:
    user_row, _ = _require_permission(x_auth_token, "manage_scorecards")
    store = load_store()
    try:
        match = get_match_or_404(store, match_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))

    scorebook = _match_scorebook(match)
    innings_index = max(1, min(2, int(request.innings_number or 1))) - 1
    innings = scorebook["innings"][innings_index]
    innings["inning_number"] = innings_index + 1
    innings["batting_team"] = request.batting_team.strip()
    innings["bowling_team"] = request.bowling_team.strip()
    innings["overs_limit"] = max(1, int(request.overs_limit or 20))
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
    return current_dashboard(load_store())


@app.post("/api/matches/{match_id}/scorebook/ball")
def add_scorebook_ball(match_id: str, request: ScorebookBallRequest, x_auth_token: str | None = Header(default=None)) -> dict[str, Any]:
    user_row, _ = _require_permission(x_auth_token, "manage_scorecards")
    store = load_store()
    try:
        match = get_match_or_404(store, match_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))

    scorebook = _match_scorebook(match)
    innings_index = max(1, min(2, int(request.innings_number or 1))) - 1
    innings = scorebook["innings"][innings_index]
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
        }
    )
    innings["balls"] = [item for item in innings.get("balls", []) if item.get("id") != ball["id"]]
    innings["balls"].append(ball)
    innings["balls"].sort(key=lambda item: (int(item.get("over_number", 1) or 1), int(item.get("ball_number", 1) or 1), str(item.get("created_at", ""))))

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
    if summary["runs"] or summary["wickets"] or summary["legal_balls"]:
        innings["status"] = "Live"
    if summary["wickets"] >= 10 or summary["legal_balls"] >= int(innings.get("overs_limit", 20) or 20) * 6:
        innings["status"] = "Completed"
    sync_fixture_scorecard_from_scorebook(match)
    _touch_fixture_audit(match, user_row)
    save_store(store)
    return current_dashboard(load_store())


@app.post("/api/chat")
def chat(request: ChatRequest) -> dict[str, Any]:
    store = load_store()
    focused_store = scoped_store_for_club(
        store,
        next((club for club in store.get("clubs", []) if club.get("id") == request.focus_club_id), store.get("club", {})),
    ) if request.focus_club_id else store
    return answer_question(request.question, focused_store, history=request.history, session_id=request.session_id)


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
    _require_permission(x_auth_token, "manage_scorecards")
    store = load_store()
    try:
        extracted = extract_archive_by_id(store, upload_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    save_store(store)
    refreshed = load_store()
    extracted = get_archive_or_404(refreshed, upload_id)
    return {
        "message": f"Processed {extracted['file_name']} for OCR review.",
        "archive": extracted,
        "dashboard": current_dashboard(refreshed, focus_club_id or extracted.get("club_id")),
    }


@app.post("/api/archive/{upload_id}/import-extraction")
def import_archive_extraction(upload_id: str, request: ArchiveImportRequest, focus_club_id: str | None = None, x_auth_token: str | None = Header(default=None)) -> dict[str, Any]:
    _require_permission(x_auth_token, "manage_scorecards")
    store = load_store()
    selected_club = _selected_club(store, focus_club_id)
    try:
        upload = get_archive_or_404(store, upload_id)
    except ValueError as exc:
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
    refreshed = load_store()
    updated = get_archive_or_404(refreshed, upload_id)
    return {
        "message": f"Imported extracted scorecard into {updated['file_name']} for review.",
        "archive": updated,
        "dashboard": current_dashboard(refreshed, focus_club_id or updated.get("club_id")),
    }


@app.post("/api/admin/archive/{upload_id}/review")
def save_archive_review(upload_id: str, request: ArchiveReviewRequest, x_auth_token: str | None = Header(default=None)) -> dict[str, Any]:
    user_row, current_club_id = _require_permission(x_auth_token, "manage_scorecards")
    store = load_store()
    try:
        upload = get_archive_or_404(store, upload_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))

    club = _selected_club(store, current_club_id)
    upload["club_id"] = upload.get("club_id") or club.get("id", "")
    upload["club_name"] = upload.get("club_name") or club.get("name", "")

    raw_text = request.text.strip()
    if not raw_text:
        raise HTTPException(status_code=400, detail="Paste the reviewed scorecard JSON first.")

    try:
        payload = json.loads(raw_text)
    except json.JSONDecodeError:
        payload = None

    if isinstance(payload, dict):
        if "draft_scorecard" in payload:
            draft = payload.get("draft_scorecard")
            if isinstance(draft, dict):
                upload["draft_scorecard"] = draft
            if isinstance(payload.get("suggested_performances"), list):
                upload["suggested_performances"] = [
                    item for item in payload.get("suggested_performances", []) if isinstance(item, dict)
                ]
        elif "match" in payload or "innings" in payload:
            parsed = parse_imported_extraction(store, raw_text)
            upload.update(parsed)
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

        upload["raw_extracted_text"] = str(_extract_field(payload, "raw_extracted_text") or raw_text)[:12000]
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
    else:
        upload["raw_extracted_text"] = raw_text[:12000]
        upload["ocr_engine"] = upload.get("ocr_engine") or "manual-review"
        upload["ocr_pipeline"] = upload.get("ocr_pipeline") or "Admin reviewed extraction"
        upload["confidence"] = upload.get("confidence") or "review"

    inferred_club = _resolve_archive_club(upload, store.get("clubs", []))
    if inferred_club:
        upload["club_id"] = inferred_club.get("id", upload.get("club_id", ""))
        upload["club_name"] = inferred_club.get("name", upload.get("club_name", ""))

    upload["status"] = "Pending review"
    upload["reviewed_by"] = user_row["display_name"] or user_row["mobile"] or "admin"
    upload["reviewed_at"] = now_iso()
    save_store(store)
    refreshed = load_store()
    updated = get_archive_or_404(refreshed, upload_id)
    return {
        "message": f"Reviewed draft saved for {updated['file_name']}.",
        "archive": updated,
        "dashboard": current_dashboard(refreshed, club.get("id", "")),
    }


@app.post("/api/scorecards/upload")
async def upload_scorecard(
    match_id: str | None = None,
    season: str | None = None,
    focus_club_id: str | None = None,
    x_auth_token: str | None = Header(default=None),
    file: UploadFile = File(...),
) -> dict[str, Any]:
    _require_permission(x_auth_token, "manage_scorecards")
    store = load_store()
    selected_club = _selected_club(store, focus_club_id)
    suffix = Path(file.filename or "scorecard.jpg").suffix or ".jpg"
    content = await file.read()
    incoming_hash = file_sha256_from_bytes(content)
    for existing in store["archive_uploads"]:
        if existing.get("file_hash") == incoming_hash:
            duplicate_record = create_duplicate_record_from_bytes(
                original_path=Path(existing["file_path"]),
                duplicate_file_name=file.filename or f"duplicate{suffix}",
                duplicate_content=content,
                file_hash=incoming_hash,
                source="upload",
            )
            store.setdefault("duplicate_uploads", []).append(duplicate_record)
            save_store(store)
            return {
                "message": "Duplicate scorecard moved to duplicates review folder with the original.",
                "dashboard": current_dashboard(load_store(), selected_club.get("id", "")),
                "upload": existing,
                "duplicate_review": duplicate_record,
            }

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
    )
    record["original_file_name"] = file.filename or file_token
    record["status"] = "Pending review"
    store["archive_uploads"].append(record)
    save_store(store)
    return {
                "message": "Scorecard image uploaded for admin review.",
                "dashboard": current_dashboard(load_store(), selected_club.get("id", "")),
                "upload": record,
            }


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
    return current_dashboard(load_store(), focus_club_id or upload.get("club_id"))


@app.get("/api/admin/review-queue")
def admin_review_queue(x_auth_token: str | None = Header(default=None)) -> dict[str, Any]:
    user_row, current_club_id = _require_permission(x_auth_token, "view_admin")
    store = load_store()
    club = _selected_club(store, current_club_id)
    role = _effective_role_name(user_row, current_club_id)
    queue: list[dict[str, Any]] = []
    for upload in canonical_archive_uploads(store.get("archive_uploads", [])):
        status = str(upload.get("status") or "").strip().lower()
        if status in {"approved", "applied to match", "deleted"}:
            continue
        inferred_club = _resolve_archive_club(upload, store.get("clubs", []))
        queue.append(
            {
                **upload,
                "resolved_club_id": str(upload.get("club_id") or (inferred_club.get("id") if inferred_club else "") or "").strip(),
                "resolved_club_name": str(upload.get("club_name") or (inferred_club.get("name") if inferred_club else "") or "Unassigned").strip() or "Unassigned",
            }
        )
    if role != "superadmin":
        queue = [
            upload
            for upload in queue
            if str(upload.get("resolved_club_id") or upload.get("club_id") or "").strip() == str(club.get("id") or "").strip()
        ]
    return {
        "user": _auth_user_payload(user_row, current_club_id),
        "club": club,
        "queue": queue,
    }


@app.post("/api/admin/archive/{upload_id}/approve")
def approve_archive(upload_id: str, x_auth_token: str | None = Header(default=None)) -> dict[str, Any]:
    user_row, current_club_id = _require_permission(x_auth_token, "manage_scorecards")
    store = load_store()
    try:
        upload = get_archive_or_404(store, upload_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    club = _selected_club(store, current_club_id)
    inferred_club = _resolve_archive_club(upload, store.get("clubs", [])) or club
    upload["club_id"] = upload.get("club_id") or inferred_club.get("id", "") or club.get("id", "")
    upload["club_name"] = upload.get("club_name") or inferred_club.get("name", "") or club.get("name", "")
    upload["status"] = "Approved"
    upload["reviewed_by"] = user_row["display_name"] or user_row["mobile"] or "admin"
    upload["reviewed_at"] = now_iso()
    auto_register_players_from_archive(store, upload, club_id=upload.get("club_id", ""))
    save_store(store)
    refreshed = load_store()
    updated = get_archive_or_404(refreshed, upload_id)
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


@app.delete("/api/admin/archive/{upload_id}")
def delete_archive(upload_id: str, x_auth_token: str | None = Header(default=None)) -> dict[str, Any]:
    user_row, current_club_id = _require_permission(x_auth_token, "manage_scorecards")
    store = load_store()
    try:
        upload = get_archive_or_404(store, upload_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    club = _selected_club(store, current_club_id)
    if str(upload.get("club_id") or "").strip() and str(upload.get("club_id") or "").strip() != str(club.get("id") or "").strip():
        raise HTTPException(status_code=403, detail="This archive belongs to a different club.")
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
        "dashboard": current_dashboard(refreshed, club.get("id", "")),
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=int(os.getenv("PORT", os.getenv("WEBSITES_PORT", "8091"))),
        log_level="info",
    )
