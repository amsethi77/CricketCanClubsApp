#!/usr/bin/env python3
"""Lightweight local smoke checks for core cricket app scenarios.

This script does not mutate the live store. It exercises copied data to verify:
- unlinking a player from a club removes only that club linkage
- the player's overall historical stats remain intact
- review JSON can be saved and approved through the archive parser path
"""

from __future__ import annotations

import json
import sys
from copy import deepcopy
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
APP_DIR = REPO_ROOT / "app"
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

import main as app_main  # noqa: E402
from cricket_store import build_combined_player_stats, get_archive_or_404, load_store  # noqa: E402


def _pick_member_with_club(store: dict) -> tuple[dict, dict]:
    member = next((item for item in store.get("members", []) if item.get("club_memberships")), None)
    if not member:
        raise RuntimeError("No member with club memberships found.")
    club_membership = member["club_memberships"][0]
    club = {
        "id": str(club_membership.get("club_id") or "").strip(),
        "name": str(club_membership.get("club_name") or "").strip(),
        "short_name": str(club_membership.get("club_name") or "").strip(),
    }
    if not club["id"] or not club["name"]:
        raise RuntimeError("Picked member does not have a usable club membership.")
    return member, club


def test_unlink_preserves_player_stats() -> dict:
    store = load_store()
    member, club = _pick_member_with_club(store)
    member_name = str(member.get("name") or "").strip()

    overall_before = next(
        (row for row in build_combined_player_stats(store["fixtures"], store.get("archive_uploads", []), store["members"]) if row["player_name"] == member_name),
        None,
    )

    club_members = [
        item
        for item in store["members"]
        if any(str(mem.get("club_id") or "").strip() == club["id"] for mem in item.get("club_memberships", []))
    ]
    club_before = next(
        (
            row
            for row in build_combined_player_stats(
                [fixture for fixture in store["fixtures"] if str(fixture.get("club_id") or "").strip() == club["id"]],
                store.get("archive_uploads", []),
                club_members,
            )
            if row["player_name"] == member_name
        ),
        None,
    )

    copied_store = deepcopy(store)
    copied_member = next(item for item in copied_store["members"] if item.get("id") == member.get("id"))
    keep_member, _ = app_main._retarget_member_team_memberships(copied_member, club)
    overall_after = next(
        (row for row in build_combined_player_stats(copied_store["fixtures"], copied_store.get("archive_uploads", []), copied_store["members"]) if row["player_name"] == member_name),
        None,
    )
    club_members_after = [
        item
        for item in copied_store["members"]
        if any(str(mem.get("club_id") or "").strip() == club["id"] for mem in item.get("club_memberships", []))
    ]
    club_after = next(
        (
            row
            for row in build_combined_player_stats(
                [fixture for fixture in copied_store["fixtures"] if str(fixture.get("club_id") or "").strip() == club["id"]],
                copied_store.get("archive_uploads", []),
                club_members_after,
            )
            if row["player_name"] == member_name
        ),
        None,
    )

    assert keep_member is False, "unlink should clear the club from the member record"
    assert app_main.member_in_club(copied_member, club["id"], club["name"]) is False, "member must not remain in the club roster"
    assert copied_member.get("team_name", "") == "", "clubless member should not retain the old team_name"
    assert copied_member.get("club_memberships", []) == [], "clubless member should not retain club_memberships"
    assert overall_before and overall_after and overall_before["runs"] == overall_after["runs"], "overall player stats should remain intact"
    assert club_before is not None, "club stats should exist before unlink"
    assert club_after is None, "club stats should disappear after unlink"

    return {
        "player": member_name,
        "club": club["name"],
        "overall_runs": overall_before["runs"] if overall_before else 0,
    }


def test_review_save_and_approve() -> dict:
    store = load_store()
    upload = next((item for item in store.get("archive_uploads", []) if str(item.get("status") or "").lower().startswith("pending")), None)
    if not upload:
        raise RuntimeError("No pending archive upload found.")

    review_json = json.dumps(
        {
            "meta": {
                "source": "vision+tesseract",
                "processed_by": "manual-review",
                "confidence": "high",
                "status": "template",
                "created_at": "2024-01-01T00:00:00Z",
                "updated_at": "2024-01-01T00:01:00Z",
            },
            "match": {
                "match_id": None,
                "match_type": "club",
                "format": None,
                "date": "2024-09-29",
                "venue": None,
                "teams": {"team_1": "Coca Cola XI", "team_2": "Heartlake Cricket Club"},
                "overs_limit": 30,
            },
            "innings": [
                {
                    "inning_number": 1,
                    "batting_team": "Coca Cola XI",
                    "bowling_team": "Heartlake Cricket Club",
                    "summary": {"runs": 120, "wickets": 6, "overs": "30", "balls": None},
                    "batting": [
                        {
                            "player": {"name": "TestPlayer", "normalized_name": "testplayer", "member_id": None},
                            "runs": 30,
                            "balls": 20,
                            "fours": 2,
                            "sixes": 1,
                            "strike_rate": 150.0,
                            "dismissal": {"type": None, "fielder": None, "bowler": None},
                        }
                    ]
                    + [
                        {
                            "player": {"name": None, "normalized_name": None, "member_id": None},
                            "runs": None,
                            "dismissal": {"type": None},
                        }
                        for _ in range(9)
                    ]
                    + [
                        {
                            "player": {"name": None, "normalized_name": None, "member_id": None},
                            "runs": None,
                            "dismissal": {"type": "did_not_bat"},
                        }
                    ],
                    "bowling": [
                        {
                            "player": {"name": None, "normalized_name": None},
                            "overs": None,
                            "runs_conceded": None,
                            "wickets": None,
                            "economy": None,
                        }
                    ],
                    "extras": {"wides": 0, "no_balls": 0, "byes": 0, "leg_byes": 0, "penalties": 0, "total": 0},
                },
                {
                    "inning_number": 2,
                    "batting_team": "Heartlake Cricket Club",
                    "bowling_team": "Coca Cola XI",
                    "summary": {"runs": 100, "wickets": 10, "overs": "30", "balls": None},
                    "batting": [
                        {
                            "player": {"name": None, "normalized_name": None, "member_id": None},
                            "runs": None,
                            "dismissal": {"type": None, "fielder": None, "bowler": None},
                        }
                        for _ in range(10)
                    ]
                    + [
                        {
                            "player": {"name": None, "normalized_name": None, "member_id": None},
                            "runs": None,
                            "dismissal": {"type": "did_not_bat"},
                        }
                    ],
                    "bowling": [
                        {
                            "player": {"name": None, "normalized_name": None},
                            "overs": None,
                            "runs_conceded": None,
                            "wickets": None,
                            "economy": None,
                        }
                    ],
                    "extras": {"wides": 0, "no_balls": 0, "byes": 0, "leg_byes": 0, "penalties": 0, "total": 0},
                },
            ],
            "validation": {
                "inning_1_total": 120,
                "inning_2_total": 100,
                "expected_result": "Coca Cola XI won by 20 runs",
                "is_consistent": True,
                "notes": "Template preserved for admin review.",
            },
        }
    )

    copied_store = load_store()
    copied_upload = get_archive_or_404(copied_store, upload["id"])
    app_main._apply_archive_review_text(copied_store, copied_upload, review_json, user_row={"display_name": "Amit S"})

    assert copied_upload.get("draft_scorecard"), "review save should populate draft_scorecard"
    assert copied_upload.get("suggested_performances"), "review save should populate suggested performances"
    assert copied_upload.get("extraction_template", {}).get("match", {}).get("date") == "2024-09-29", "review template should preserve the OCR date"
    assert copied_upload.get("extraction_template", {}).get("meta", {}).get("status") == "template", "review template should keep template status"

    copied_upload["status"] = "Approved"
    copied_upload["reviewed_by"] = "Amit S"
    copied_upload["reviewed_at"] = "now"

    assert copied_upload["status"] == "Approved", "approve should finalize the archive"
    assert copied_upload["reviewed_by"] == "Amit S", "approve should record reviewer"

    return {
        "upload_id": upload["id"],
        "date": copied_upload.get("extraction_template", {}).get("match", {}).get("date"),
        "suggested_players": len(copied_upload.get("suggested_performances", [])),
    }


def main() -> int:
    unlink_result = test_unlink_preserves_player_stats()
    review_result = test_review_save_and_approve()
    print(json.dumps({"unlink": unlink_result, "review": review_result}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
