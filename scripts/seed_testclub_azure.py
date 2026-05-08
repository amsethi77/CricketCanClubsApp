#!/usr/bin/env python3
"""Seed the Azure-hosted CricketClubApp with the shared TestClub QA scenario."""

from __future__ import annotations

import argparse
import base64
import json
from datetime import date, timedelta
from typing import Any

import httpx


def _placeholder_png_bytes() -> bytes:
    return base64.b64decode(
        b"iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO2b5XQAAAAASUVORK5CYII="
    )


def _request_json(client: httpx.Client, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
    response = client.request(method, path, **kwargs)
    response.raise_for_status()
    if not response.content:
        return {}
    return response.json()


def _register(
    client: httpx.Client,
    *,
    display_name: str,
    member_name: str,
    mobile: str,
    password: str,
    role: str,
    club_name: str = "",
    club_city: str = "",
    club_country: str = "",
    primary_club_id: str = "",
) -> dict[str, Any]:
    payload = {
        "display_name": display_name,
        "member_name": member_name,
        "mobile": mobile,
        "email": f"{member_name.lower()}@testclub.local",
        "password": password,
        "role": role,
        "primary_club_id": primary_club_id,
        "club_name": club_name,
        "club_city": club_city,
        "club_country": club_country,
    }
    return _request_json(client, "POST", "/api/auth/register", json=payload)


def _signin(client: httpx.Client, identifier: str) -> dict[str, Any]:
    return _request_json(
        client,
        "POST",
        "/api/auth/signin",
        json={"identifier": identifier, "password": "", "player_name": ""},
    )


def _ensure_account(
    client: httpx.Client,
    *,
    display_name: str,
    member_name: str,
    mobile: str,
    password: str,
    role: str,
    club_name: str = "",
    club_city: str = "",
    club_country: str = "",
    primary_club_id: str = "",
) -> dict[str, Any]:
    try:
        return _signin(client, mobile)
    except httpx.HTTPStatusError:
        return _register(
            client,
            display_name=display_name,
            member_name=member_name,
            mobile=mobile,
            password=password,
            role=role,
            club_name=club_name,
            club_city=club_city,
            club_country=club_country,
            primary_club_id=primary_club_id,
        )


def _auth_headers(token: str) -> dict[str, str]:
    return {"x-auth-token": token}


def _select_club(client: httpx.Client, club_id: str) -> None:
    response = client.post("/clubs/select", data={"club_id": club_id})
    response.raise_for_status()


def _create_fixture(
    client: httpx.Client,
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
    existing = _season_setup_data(client, token, club_id).get("fixtures", [])
    for fixture in existing:
        if str(fixture.get("date") or "").strip() == fixture_date and str(fixture.get("opponent") or "").strip() == opponent:
            return fixture
    payload = {
        "club_id": club_id,
        "season_year": int(fixture_date[:4]),
        "date": fixture_date,
        "date_label": date.fromisoformat(fixture_date).strftime("%d %b %Y"),
        "opponent": opponent,
        "venue": venue,
        "match_type": match_type,
        "scheduled_time": scheduled_time,
        "overs": overs,
    }
    data = _request_json(client, "POST", "/api/season-setup/fixtures", json=payload, headers=_auth_headers(token))
    for fixture in data.get("fixtures", []):
        if str(fixture.get("date") or "").strip() == fixture_date and str(fixture.get("opponent") or "").strip() == opponent:
            return fixture
    raise RuntimeError(f"Could not create fixture for {opponent} on {fixture_date}.")


def _season_setup_data(client: httpx.Client, token: str, club_id: str) -> dict[str, Any]:
    return _request_json(
        client,
        "GET",
        "/api/season-setup/data",
        params={"club_id": club_id},
        headers=_auth_headers(token),
    )


def _update_match_details(client: httpx.Client, token: str, fixture_id: str, **fields: Any) -> None:
    _request_json(client, "POST", f"/api/matches/{fixture_id}/details", json=fields, headers=_auth_headers(token))


def _update_scorecard(client: httpx.Client, token: str, fixture_id: str, **fields: Any) -> None:
    _request_json(client, "POST", f"/api/matches/{fixture_id}/scorecard", json=fields, headers=_auth_headers(token))


def _add_commentary(client: httpx.Client, token: str, fixture_id: str, mode: str, text: str) -> None:
    _request_json(
        client,
        "POST",
        f"/api/matches/{fixture_id}/commentary",
        json={"mode": mode, "text": text},
        headers=_auth_headers(token),
    )


def _set_scorebook_innings(
    client: httpx.Client,
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
    _request_json(
        client,
        "POST",
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


def _add_scorebook_ball(
    client: httpx.Client,
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
    _request_json(
        client,
        "POST",
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


def _add_performance(
    client: httpx.Client,
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
    _request_json(
        client,
        "POST",
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


def _set_availability(
    client: httpx.Client,
    token: str,
    *,
    club_id: str,
    fixture_id: str,
    player_id: str,
    status: str,
    note: str,
) -> None:
    _request_json(
        client,
        "POST",
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


def _upload_and_apply_scorecard(
    client: httpx.Client,
    token: str,
    *,
    club_id: str,
    match_id: str,
    upload_name: str,
    result: str,
    heartlake_runs: str,
    heartlake_wickets: str,
    heartlake_overs: str,
    opponent_runs: str,
    opponent_wickets: str,
    opponent_overs: str,
) -> dict[str, Any]:
    upload = _request_json(
        client,
        "POST",
        "/api/scorecards/upload",
        params={"match_id": match_id, "focus_club_id": club_id},
        files={"file": (upload_name, _placeholder_png_bytes(), "image/png")},
        headers=_auth_headers(token),
    )
    upload_id = upload.get("upload", {}).get("id")
    if not upload_id:
        raise RuntimeError("Image upload did not return an upload id.")

    imported_template = {
        "meta": {
            "source": "azure-seed",
            "processed_by": "scripts/seed_testclub_azure.py",
            "confidence": "seeded",
        },
        "match": {
            "teams": {"team_1": "TestClub", "team_2": "QA Image Scorecard Opponent"},
            "date": date.today().isoformat(),
            "venue": "TestClub Ground",
        },
        "innings": [
            {
                "batting_team": "TestClub",
                "bowling_team": "QA Image Scorecard Opponent",
                "summary": {"runs": 74, "wickets": 5, "overs": "20"},
                "extras": {"total": 4},
                "batting": [{"player": {"name": "player1"}, "runs": 30, "balls": 20, "dismissal": {"type": "caught"}}],
                "bowling": [{"player": {"name": "captain1"}, "overs": "4.0", "runs": 18, "wickets": 2}],
            }
        ],
        "validation": {"expected_result": result},
    }

    _request_json(
        client,
        "POST",
        f"/api/archive/{upload_id}/import-extraction",
        params={"focus_club_id": club_id},
        json={"text": json.dumps(imported_template, indent=2)},
        headers=_auth_headers(token),
    )
    return _request_json(
        client,
        "POST",
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
            "source_note": "Azure QA seed scorecard applied into the live records.",
        },
        headers=_auth_headers(token),
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", required=True, help="Azure app base URL, e.g. https://example.azurewebsites.net")
    args = parser.parse_args()
    base_url = args.base_url.rstrip("/")

    completed_date = (date.today() - timedelta(days=2)).isoformat()
    image_scorecard_date = (date.today() - timedelta(days=1)).isoformat()
    upcoming_date = (date.today() + timedelta(days=7)).isoformat()

    with httpx.Client(base_url=base_url, timeout=300.0, follow_redirects=True) as client:
        print("Seeding TestClub on Azure...")
        clubadmin_reg = _ensure_account(
            client,
            display_name="clubadmin1",
            member_name="clubadmin1",
            mobile="3333333333",
            password="testclub",
            role="club_admin",
            club_name="TestClub",
            club_city="Toronto",
            club_country="Canada",
        )
        club_id = str(clubadmin_reg.get("user", {}).get("primary_club_id") or clubadmin_reg.get("clubs", [{}])[0].get("id") or "").strip()
        if not club_id:
            raise RuntimeError("TestClub club id was not created.")

        player_reg = _ensure_account(
            client,
            display_name="player1",
            member_name="player1",
            mobile="1111111111",
            password="testclub",
            role="player",
            primary_club_id=club_id,
        )
        captain_reg = _ensure_account(
            client,
            display_name="captain1",
            member_name="captain1",
            mobile="2222222222",
            password="testclub",
            role="captain",
            primary_club_id=club_id,
        )

        clubadmin_auth = _signin(client, "3333333333")
        player_auth = _signin(client, "1111111111")
        captain_auth = _signin(client, "2222222222")
        superadmin_auth = _signin(client, "14164508695")
        _select_club(client, club_id)

        print(f"Using club id: {club_id}")
        completed_fixture = _create_fixture(
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
        image_fixture = _create_fixture(
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
        upcoming_fixture = _create_fixture(
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
        print("Fixtures ready.")

        _update_match_details(
            client,
            clubadmin_auth["token"],
            completed_fixture["id"],
            heartlake_captain="captain1",
            venue="TestClub Ground",
            match_type="Friendly",
            scheduled_time="10:00",
            overs="20",
            scorer="clubadmin1",
            status="Completed",
            notes="Azure QA seed completed fixture",
        )
        print("Completed fixture details updated.")
        _set_scorebook_innings(
            client,
            superadmin_auth["token"],
            completed_fixture["id"],
            innings_number=1,
            batting_team="TestClub",
            bowling_team="QA Completed Opponent",
            batters=["player1", "captain1", "clubadmin1"] + [""] * 8,
            bowlers=["clubadmin1", "captain1"] + [""] * 9,
        )
        _set_scorebook_innings(
            client,
            clubadmin_auth["token"],
            completed_fixture["id"],
            innings_number=2,
            batting_team="QA Completed Opponent",
            bowling_team="TestClub",
            target_runs=68,
            status="In progress",
            batters=["opponent_open_1", "opponent_open_2", "opponent_middle_3"] + [""] * 8,
            bowlers=["player1", "captain1"] + [""] * 9,
        )
        print("Scorebook innings configured.")
        _add_scorebook_ball(
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
            commentary="Azure QA seed ball, innings 1",
        )
        _add_scorebook_ball(
            client,
            clubadmin_auth["token"],
            completed_fixture["id"],
            innings_number=2,
            over_number=1,
            ball_number=1,
            striker="opponent_open_1",
            non_striker="opponent_open_2",
            bowler="player1",
            runs_bat=0,
            commentary="Azure QA seed ball, innings 2",
        )
        print("Scorebook balls added.")

        _add_commentary(client, superadmin_auth["token"], completed_fixture["id"], "text", "Azure QA text scoring note for TestClub.")
        _add_commentary(client, superadmin_auth["token"], completed_fixture["id"], "voice", "Azure QA voice scoring transcript for TestClub.")
        print("Commentary saved.")

        _add_performance(client, superadmin_auth["token"], completed_fixture["id"], player_name="player1", runs=42, balls=29, fours=5, sixes=1, notes="Azure QA seed batting")
        _add_performance(client, superadmin_auth["token"], completed_fixture["id"], player_name="captain1", runs=18, balls=16, wickets=1, notes="Azure QA seed bowling")
        _add_performance(client, superadmin_auth["token"], completed_fixture["id"], player_name="clubadmin1", runs=7, balls=8, catches=1, notes="Azure QA seed fielding")
        print("Player performances saved.")
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
            live_summary="Completed Azure QA seed scorecard",
            status="Completed",
        )
        print("Completed scorecard synced.")

        upload_result = _upload_and_apply_scorecard(
            client,
            superadmin_auth["token"],
            club_id=club_id,
            match_id=image_fixture["id"],
            upload_name="match2-scorecard.png",
            result="TestClub won by 6 runs",
            heartlake_runs="74",
            heartlake_wickets="5",
            heartlake_overs="20",
            opponent_runs="68",
            opponent_wickets="8",
            opponent_overs="20",
        )
        print("Uploaded-image scorecard applied.")

        _set_availability(
            client,
            player_auth["token"],
            club_id=club_id,
            fixture_id=upcoming_fixture["id"],
            player_id=player_auth["user"]["member_id"],
            status="Available",
            note="Azure QA seed availability",
        )
        _set_availability(
            client,
            captain_auth["token"],
            club_id=club_id,
            fixture_id=upcoming_fixture["id"],
            player_id=captain_auth["user"]["member_id"],
            status="Available",
            note="Azure QA seed captain availability",
        )
        _set_availability(
            client,
            clubadmin_auth["token"],
            club_id=club_id,
            fixture_id=upcoming_fixture["id"],
            player_id=clubadmin_auth["user"]["member_id"],
            status="Maybe",
            note="Azure QA seed club admin availability",
        )
        print("Availability saved.")

        dashboard = _request_json(
            client,
            "GET",
            "/api/dashboard",
            params={"focus_club_id": club_id, "selected_season_year": "2026"},
            headers=_auth_headers(clubadmin_auth["token"]),
        )
        profile = _request_json(client, "GET", "/api/player/profile-data", headers=_auth_headers(player_auth["token"]))
        chat = _request_json(
            client,
            "POST",
            "/api/chat",
            json={
                "question": "Who is the top ranked player with runs?",
                "session_id": "azure-qa",
                "history": [],
                "focus_club_id": club_id,
            },
        )
        signin_stats = _request_json(client, "GET", "/api/public/signin-stats")
        print("QA verification endpoints loaded.")

    report = {
        "base_url": base_url,
        "club_id": club_id,
        "registered": {
            "clubadmin1": clubadmin_reg.get("user", {}).get("display_name", ""),
            "player1": player_reg.get("user", {}).get("display_name", ""),
            "captain1": captain_reg.get("user", {}).get("display_name", ""),
        },
        "fixtures": [
            {
                "id": completed_fixture["id"],
                "date": completed_date,
                "opponent": "QA Completed Opponent",
            },
            {
                "id": image_fixture["id"],
                "date": image_scorecard_date,
                "opponent": "QA Image Scorecard Opponent",
            },
            {
                "id": upcoming_fixture["id"],
                "date": upcoming_date,
                "opponent": "QA Upcoming Opponent",
            },
        ],
        "archive_upload": {
            "message": upload_result.get("message", ""),
            "archive_id": upload_result.get("archive", {}).get("id", ""),
            "status": upload_result.get("archive", {}).get("status", ""),
        },
        "dashboard_summary": {
            "club_name": dashboard.get("club", {}).get("name", ""),
            "selected_season_year": dashboard.get("selected_season_year", ""),
            "scorecards": dashboard.get("scorecard_count", 0),
            "commentary_count": dashboard.get("commentary_count", 0),
        },
        "profile_summary": {
            "player_name": profile.get("member", {}).get("name", ""),
            "recent_history": len(profile.get("recent_history", [])),
        },
        "chat_answer": chat.get("answer", ""),
        "signin_stats": {
            "batting": len(signin_stats.get("batting", [])),
            "bowling": len(signin_stats.get("bowling", [])),
            "clubs": len(signin_stats.get("clubs", [])),
        },
    }
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
