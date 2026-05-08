#!/usr/bin/env python3
"""Seed TestClub data into the main local runtime.

This script writes directly to the normal app database and cache files used by
the 8090 development app. It avoids standalone QA bundles or alternate ports.
"""

from __future__ import annotations

import importlib
import base64
import json
import os
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient


REPO_ROOT = Path(__file__).resolve().parents[1]


def _clear_app_modules() -> None:
    for name in list(sys.modules):
        if name == "app" or name.startswith("app."):
            sys.modules.pop(name, None)


def _load_app():
    if str(REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(REPO_ROOT))
    _clear_app_modules()
    return importlib.import_module("app.main")


def _signin(client: TestClient, identifier: str) -> dict[str, Any]:
    response = client.post(
        "/api/auth/signin",
        json={"identifier": identifier, "password": "", "player_name": ""},
    )
    response.raise_for_status()
    return response.json()


def _auth_headers(token: str) -> dict[str, str]:
    return {"x-auth-token": token}


def _fixture_match(fixtures: list[dict[str, Any]], *, club_id: str, opponent: str, fixture_date: str) -> dict[str, Any] | None:
    for fixture in fixtures:
        if str(fixture.get("club_id") or "").strip() != club_id:
            continue
        if str(fixture.get("opponent") or "").strip() != opponent:
            continue
        if str(fixture.get("date") or "").strip() != fixture_date:
            continue
        return fixture
    return None


def _ensure_fixture(
    client: TestClient,
    token: str,
    *,
    club_id: str,
    fixture_date: str,
    opponent: str,
    venue: str,
    match_type: str,
    scheduled_time: str,
    overs: str,
) -> dict[str, Any]:
    store = client.app.state.main.load_store()
    existing = _fixture_match(store.get("fixtures", []), club_id=club_id, opponent=opponent, fixture_date=fixture_date)
    if existing:
        return existing

    response = client.post(
        "/api/season-setup/fixtures",
        json={
            "club_id": club_id,
            "season_year": int(fixture_date[:4]),
            "date": fixture_date,
            "date_label": datetime.fromisoformat(fixture_date).strftime("%d %b %Y"),
            "opponent": opponent,
            "venue": venue,
            "match_type": match_type,
            "scheduled_time": scheduled_time,
            "overs": overs,
        },
        headers=_auth_headers(token),
    )
    response.raise_for_status()
    payload = response.json()
    for fixture in payload.get("fixtures", []):
        if str(fixture.get("opponent") or "").strip() == opponent and str(fixture.get("date") or "").strip() == fixture_date:
            return fixture
    raise RuntimeError(f"Could not find newly created fixture for {opponent!r} on {fixture_date}.")


def _update_match_details(client: TestClient, token: str, fixture_id: str, **fields: Any) -> None:
    response = client.post(
        f"/api/matches/{fixture_id}/details",
        json=fields,
        headers=_auth_headers(token),
    )
    response.raise_for_status()


def _update_scorecard(client: TestClient, token: str, fixture_id: str, **fields: Any) -> None:
    response = client.post(
        f"/api/matches/{fixture_id}/scorecard",
        json=fields,
        headers=_auth_headers(token),
    )
    response.raise_for_status()


def _setup_scorebook(client: TestClient, token: str, fixture_id: str) -> None:
    response = client.post(
        f"/api/matches/{fixture_id}/scorebook/setup",
        json={
            "innings_number": 1,
            "batting_team": "TestClub",
            "bowling_team": "QA Opponent",
            "overs_limit": 20,
            "target_runs": 0,
            "status": "In progress",
            "batters": [
                "player1",
                "captain1",
                "clubadmin1",
                "guest_bat_4",
                "guest_bat_5",
                "guest_bat_6",
                "guest_bat_7",
                "guest_bat_8",
                "guest_bat_9",
                "guest_bat_10",
                "guest_bat_11",
            ],
            "bowlers": [
                "clubadmin1",
                "captain1",
                "guest_bowler_3",
                "guest_bowler_4",
                "guest_bowler_5",
                "guest_bowler_6",
                "guest_bowler_7",
                "guest_bowler_8",
                "guest_bowler_9",
                "guest_bowler_10",
                "guest_bowler_11",
            ],
        },
        headers=_auth_headers(token),
    )
    response.raise_for_status()


def _set_scorebook_innings(
    client: TestClient,
    token: str,
    fixture_id: str,
    *,
    innings_number: int,
    batting_team: str,
    bowling_team: str,
    batters: list[str],
    bowlers: list[str],
    target_runs: int = 0,
    status: str = "In progress",
) -> None:
    response = client.post(
        f"/api/matches/{fixture_id}/scorebook/setup",
        json={
            "innings_number": innings_number,
            "batting_team": batting_team,
            "bowling_team": bowling_team,
            "overs_limit": 20,
            "target_runs": target_runs,
            "status": status,
            "batters": batters,
            "bowlers": bowlers,
        },
        headers=_auth_headers(token),
    )
    response.raise_for_status()


def _ensure_scorebook_ball(client: TestClient, token: str, fixture_id: str) -> None:
    store = client.app.state.main.load_store()
    fixture = next((item for item in store.get("fixtures", []) if item.get("id") == fixture_id), None)
    if not fixture:
        raise RuntimeError(f"Fixture {fixture_id} not found.")
    scorebook = fixture.get("scorebook") or {}
    innings = (scorebook.get("innings") or [{}])[0]
    balls = innings.get("balls") or []
    if balls:
        return
    response = client.post(
        f"/api/matches/{fixture_id}/scorebook/ball",
        json={
            "innings_number": 1,
            "over_number": 1,
            "ball_number": 1,
            "striker": "player1",
            "non_striker": "captain1",
            "bowler": "clubadmin1",
            "runs_bat": 1,
            "commentary": "TestClub QA seed ball",
        },
        headers=_auth_headers(token),
    )
    response.raise_for_status()


def _ensure_scorebook_ball_for_innings(
    client: TestClient,
    token: str,
    fixture_id: str,
    *,
    innings_number: int,
    over_number: int,
    ball_number: int,
    striker: str,
    non_striker: str,
    bowler: str,
    runs_bat: int,
    commentary: str,
) -> None:
    response = client.post(
        f"/api/matches/{fixture_id}/scorebook/ball",
        json={
            "innings_number": innings_number,
            "over_number": over_number,
            "ball_number": ball_number,
            "striker": striker,
            "non_striker": non_striker,
            "bowler": bowler,
            "runs_bat": runs_bat,
            "commentary": commentary,
        },
        headers=_auth_headers(token),
    )
    response.raise_for_status()


def _placeholder_png_bytes() -> bytes:
    return base64.b64decode(
        b"iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO2b5XQAAAAASUVORK5CYII="
    )


def _scorecard_template_json(
    *,
    batting_team: str,
    bowling_team: str,
    opponent_team: str,
    result: str,
    innings1_runs: int,
    innings1_wickets: int,
    innings2_runs: int,
    innings2_wickets: int,
) -> dict[str, Any]:
    def batting_row(player_name: str, runs: int, balls: int, dismissal_type: str = "not out") -> dict[str, Any]:
        return {
            "player": {"name": player_name},
            "runs": runs,
            "balls": balls,
            "fours": 0,
            "sixes": 0,
            "dismissal": {"type": dismissal_type},
        }

    def bowling_row(player_name: str, overs: str, runs: int, wickets: int) -> dict[str, Any]:
        return {
            "player": {"name": player_name},
            "overs": overs,
            "runs": runs,
            "wickets": wickets,
        }

    batting_order_1 = [
        ("player1", 33, 25, "c and b"),
        ("captain1", 19, 17, "lbw"),
        ("clubadmin1", 11, 12, "run out"),
    ] + [("", 0, 0, "did not bat") for _ in range(4, 12)]

    batting_order_2 = [
        ("opponent_open_1", 17, 21, "caught"),
        ("opponent_open_2", 14, 18, "bowled"),
        ("opponent_middle_3", 9, 13, "lbw"),
    ] + [("", 0, 0, "did not bat") for _ in range(4, 12)]

    return {
        "meta": {
            "source": "manual-import",
            "processed_by": "scripts/seed_testclub_main.py",
            "confidence": "seeded",
        },
        "match": {
            "teams": {"team_1": batting_team, "team_2": opponent_team},
            "date": date.today().isoformat(),
            "venue": "TestClub Ground",
        },
        "innings": [
            {
                "batting_team": batting_team,
                "bowling_team": bowling_team,
                "summary": {"runs": str(innings1_runs), "wickets": str(innings1_wickets), "overs": "20"},
                "extras": {"total": "8"},
                "batting": [
                    batting_row(name, runs, balls, dismissal)
                    for name, runs, balls, dismissal in batting_order_1
                ],
                "bowling": [
                    bowling_row("clubadmin1", "4.0", 14, 1),
                    bowling_row("captain1", "4.0", 19, 1),
                ] + [bowling_row("", "0.0", 0, 0) for _ in range(3, 12)],
                "did_not_bat": [],
            },
            {
                "batting_team": opponent_team,
                "bowling_team": batting_team,
                "summary": {"runs": str(innings2_runs), "wickets": str(innings2_wickets), "overs": "20"},
                "extras": {"total": "6"},
                "batting": [
                    batting_row(name, runs, balls, dismissal)
                    for name, runs, balls, dismissal in batting_order_2
                ],
                "bowling": [
                    bowling_row("player1", "4.0", 10, 2),
                    bowling_row("captain1", "4.0", 16, 1),
                ] + [bowling_row("", "0.0", 0, 0) for _ in range(3, 12)],
                "did_not_bat": [],
            },
        ],
        "validation": {
            "expected_result": result,
        },
    }


def _create_uploaded_image_scorecard(
    client: TestClient,
    token: str,
    *,
    club_id: str,
    match_id: str,
    upload_name: str,
    imported_template: dict[str, Any],
    result: str,
    heartlake_runs: str,
    heartlake_wickets: str,
    heartlake_overs: str,
    opponent_runs: str,
    opponent_wickets: str,
    opponent_overs: str,
) -> dict[str, Any]:
    upload_response = client.post(
        "/api/scorecards/upload",
        params={"match_id": match_id, "focus_club_id": club_id},
        files={"file": (upload_name, _placeholder_png_bytes(), "image/png")},
        headers=_auth_headers(token),
    )
    upload_response.raise_for_status()
    upload = upload_response.json().get("upload", {})
    upload_id = upload.get("id")
    if not upload_id:
        raise RuntimeError("Upload did not return an archive upload id.")

    import_response = client.post(
        f"/api/archive/{upload_id}/import-extraction",
        params={"focus_club_id": club_id},
        json={"text": json.dumps(imported_template, indent=2)},
        headers=_auth_headers(token),
    )
    import_response.raise_for_status()

    apply_response = client.post(
        f"/api/archive/{upload_id}/apply",
        params={"focus_club_id": club_id},
        json={
            "match_id": match_id,
            "heartlake_runs": heartlake_runs,
            "heartlake_wickets": heartlake_wickets,
            "heartlake_overs": heartlake_overs,
            "opponent_runs": opponent_runs,
            "opponent_wickets": opponent_wickets,
            "opponent_overs": opponent_overs,
            "result": result,
            "source_note": "Uploaded image scorecard applied into the main runtime.",
        },
        headers=_auth_headers(token),
    )
    apply_response.raise_for_status()
    return apply_response.json()


def _add_performance(
    client: TestClient,
    token: str,
    fixture_id: str,
    *,
    player_name: str,
    runs: int,
    balls: int,
    wickets: int = 0,
    catches: int = 0,
    fours: int = 0,
    sixes: int = 0,
    notes: str = "",
) -> None:
    store = client.app.state.main.load_store()
    fixture = next((item for item in store.get("fixtures", []) if item.get("id") == fixture_id), None)
    if not fixture:
        raise RuntimeError(f"Fixture {fixture_id} not found.")
    for performance in fixture.get("performances", []) or []:
        if (
            str(performance.get("player_name") or "").strip() == player_name
            and int(performance.get("runs") or 0) == runs
            and int(performance.get("balls") or 0) == balls
            and int(performance.get("wickets") or 0) == wickets
            and int(performance.get("catches") or 0) == catches
            and str(performance.get("notes") or "").strip() == notes
        ):
            return
    response = client.post(
        f"/api/matches/{fixture_id}/performances",
        json={
            "player_name": player_name,
            "runs": runs,
            "balls": balls,
            "wickets": wickets,
            "catches": catches,
            "fours": fours,
            "sixes": sixes,
            "notes": notes,
            "source": "seed",
        },
        headers=_auth_headers(token),
    )
    response.raise_for_status()


def _ensure_availability(
    client: TestClient,
    token: str,
    *,
    club_id: str,
    fixture_id: str,
    player_id: str,
    status: str,
    note: str,
) -> None:
    response = client.post(
        "/api/player/availability",
        json={
            "club_id": club_id,
            "fixture_id": fixture_id,
            "player_id": player_id,
            "status": status,
            "note": note,
        },
        headers=_auth_headers(token),
    )
    response.raise_for_status()


def main() -> int:
    main_mod = _load_app()
    client = TestClient(main_mod.app)
    client.app.state.main = main_mod
    try:
        captain_auth = _signin(client, "2222222222")
        player_auth = _signin(client, "1111111111")
        clubadmin_auth = _signin(client, "3333333333")
        superadmin_auth = _signin(client, "14164508695")

        club_id = "club-testclub"
        today = date.today()
        completed_date = (today - timedelta(days=2)).isoformat()
        image_scorecard_date = (today - timedelta(days=1)).isoformat()
        upcoming_date = (today + timedelta(days=7)).isoformat()

        completed_fixture = _ensure_fixture(
            client,
            captain_auth["token"],
            club_id=club_id,
            fixture_date=completed_date,
            opponent="QA Completed Opponent",
            venue="TestClub Ground",
            match_type="Friendly",
            scheduled_time="10:00",
            overs="20",
        )
        image_fixture = _ensure_fixture(
            client,
            captain_auth["token"],
            club_id=club_id,
            fixture_date=image_scorecard_date,
            opponent="QA Image Scorecard Opponent",
            venue="TestClub Ground",
            match_type="Friendly",
            scheduled_time="11:30",
            overs="20",
        )
        upcoming_fixture = _ensure_fixture(
            client,
            captain_auth["token"],
            club_id=club_id,
            fixture_date=upcoming_date,
            opponent="QA Upcoming Opponent",
            venue="TestClub Ground",
            match_type="Friendly",
            scheduled_time="09:30",
            overs="20",
        )

        _update_match_details(
            client,
            superadmin_auth["token"],
            completed_fixture["id"],
            heartlake_captain="captain1",
            venue="TestClub Ground",
            match_type="Friendly",
            scheduled_time="10:00",
            overs="20",
            scorer="clubadmin1",
            status="Completed",
            notes="TestClub QA seed completed fixture",
        )
        _set_scorebook_innings(
            client,
            superadmin_auth["token"],
            completed_fixture["id"],
            innings_number=1,
            batting_team="TestClub",
            bowling_team="QA Completed Opponent",
            batters=[
                "player1",
                "captain1",
                "clubadmin1",
                "guest_bat_4",
                "guest_bat_5",
                "guest_bat_6",
                "guest_bat_7",
                "guest_bat_8",
                "guest_bat_9",
                "guest_bat_10",
                "guest_bat_11",
            ],
            bowlers=[
                "clubadmin1",
                "captain1",
                "guest_bowler_3",
                "guest_bowler_4",
                "guest_bowler_5",
                "guest_bowler_6",
                "guest_bowler_7",
                "guest_bowler_8",
                "guest_bowler_9",
                "guest_bowler_10",
                "guest_bowler_11",
            ],
        )
        _set_scorebook_innings(
            client,
            superadmin_auth["token"],
            completed_fixture["id"],
            innings_number=2,
            batting_team="QA Completed Opponent",
            bowling_team="TestClub",
            target_runs=68,
            status="In progress",
            batters=[
                "opponent_open_1",
                "opponent_open_2",
                "opponent_middle_3",
                "opponent_bat_4",
                "opponent_bat_5",
                "opponent_bat_6",
                "opponent_bat_7",
                "opponent_bat_8",
                "opponent_bat_9",
                "opponent_bat_10",
                "opponent_bat_11",
            ],
            bowlers=[
                "player1",
                "captain1",
                "guest_bowler_3",
                "guest_bowler_4",
                "guest_bowler_5",
                "guest_bowler_6",
                "guest_bowler_7",
                "guest_bowler_8",
                "guest_bowler_9",
                "guest_bowler_10",
                "guest_bowler_11",
            ],
        )
        _ensure_scorebook_ball_for_innings(
            client,
            superadmin_auth["token"],
            completed_fixture["id"],
            innings_number=1,
            over_number=1,
            ball_number=1,
            striker="player1",
            non_striker="captain1",
            bowler="clubadmin1",
            runs_bat=1,
            commentary="TestClub QA seed ball, innings 1",
        )
        _ensure_scorebook_ball_for_innings(
            client,
            superadmin_auth["token"],
            completed_fixture["id"],
            innings_number=2,
            over_number=1,
            ball_number=1,
            striker="opponent_open_1",
            non_striker="opponent_open_2",
            bowler="player1",
            runs_bat=0,
            commentary="TestClub QA seed ball, innings 2",
        )

        _add_performance(
            client,
            superadmin_auth["token"],
            completed_fixture["id"],
            player_name="player1",
            runs=42,
            balls=29,
            fours=5,
            sixes=1,
            notes="TestClub QA seed batting",
        )
        _add_performance(
            client,
            superadmin_auth["token"],
            completed_fixture["id"],
            player_name="captain1",
            runs=18,
            balls=16,
            wickets=1,
            notes="TestClub QA seed bowling",
        )
        _add_performance(
            client,
            superadmin_auth["token"],
            completed_fixture["id"],
            player_name="clubadmin1",
            runs=7,
            balls=8,
            catches=1,
            notes="TestClub QA seed fielding",
        )
        _update_scorecard(
            client,
            superadmin_auth["token"],
            completed_fixture["id"],
            heartlake_runs="67",
            heartlake_wickets="3",
            heartlake_overs="20",
            opponent_runs="52",
            opponent_wickets="8",
            opponent_overs="20",
            result="TestClub won by 15 runs",
            live_summary="Completed TestClub QA seed scorecard",
            status="Completed",
        )

        image_template = _scorecard_template_json(
            batting_team="TestClub",
            bowling_team="QA Image Scorecard Opponent",
            opponent_team="QA Image Scorecard Opponent",
            result="TestClub won by 6 runs",
            innings1_runs=74,
            innings1_wickets=5,
            innings2_runs=68,
            innings2_wickets=8,
        )
        _create_uploaded_image_scorecard(
            client,
            superadmin_auth["token"],
            club_id=club_id,
            match_id=image_fixture["id"],
            upload_name="match2-scorecard.png",
            imported_template=image_template,
            result="TestClub won by 6 runs",
            heartlake_runs="74",
            heartlake_wickets="5",
            heartlake_overs="20",
            opponent_runs="68",
            opponent_wickets="8",
            opponent_overs="20",
        )

        _ensure_availability(
            client,
            player_auth["token"],
            club_id=club_id,
            fixture_id=upcoming_fixture["id"],
            player_id=player_auth["user"]["member_id"],
            status="Available",
            note="TestClub QA seed availability",
        )
        _ensure_availability(
            client,
            captain_auth["token"],
            club_id=club_id,
            fixture_id=upcoming_fixture["id"],
            player_id=captain_auth["user"]["member_id"],
            status="Available",
            note="TestClub QA seed captain availability",
        )
        _ensure_availability(
            client,
            clubadmin_auth["token"],
            club_id=club_id,
            fixture_id=upcoming_fixture["id"],
            player_id=clubadmin_auth["user"]["member_id"],
            status="Maybe",
            note="TestClub QA seed club admin availability",
        )

        store = main_mod.load_store()
        fixtures = [item for item in store.get("fixtures", []) if str(item.get("club_id") or "").strip() == club_id]
        archives = [item for item in main_mod.canonical_archive_uploads(store.get("archive_uploads", [])) if str(item.get("club_id") or "").strip() == club_id]
        dashboard = main_mod.build_dashboard(store, main_mod.get_llm_status(), focus_club_id=club_id, requested_season_year=str(today.year))
        report = {
            "club": club_id,
            "fixtures": [
                {
                    "id": fixture.get("id", ""),
                    "date": fixture.get("date", ""),
                    "opponent": fixture.get("opponent", ""),
                    "status": fixture.get("status", ""),
                }
                for fixture in fixtures
            ],
            "archives": [
                {
                    "id": archive.get("id", ""),
                    "file_name": archive.get("file_name", ""),
                    "match_id": archive.get("match_id", ""),
                    "status": archive.get("status", ""),
                    "scorecard_date": archive.get("scorecard_date", ""),
                }
                for archive in archives
            ],
            "scorebook_innings": [
                {
                    "inning_number": inn.get("inning_number", ""),
                    "status": inn.get("status", ""),
                    "batters": len(inn.get("batters", [])),
                    "bowlers": len(inn.get("bowlers", [])),
                    "balls": len(inn.get("balls", [])),
                }
                for inn in (next((item for item in fixtures if item.get("id") == completed_fixture["id"]), {}) or {}).get("scorebook", {}).get("innings", [])
            ],
            "player_stats": [
                {
                    "player_name": row.get("player_name", ""),
                    "runs": row.get("runs", 0),
                    "wickets": row.get("wickets", 0),
                    "catches": row.get("catches", 0),
                    "matches": row.get("matches", 0),
                }
                for row in dashboard.get("combined_player_stats", [])[:5]
            ],
            "season_years": dashboard.get("season_years", []),
            "selected_season_year": dashboard.get("selected_season_year", ""),
            "llm": dashboard.get("llm", {}),
        }
        print(json.dumps(report, indent=2))
    finally:
        client.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
