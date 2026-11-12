import unittest
import sqlite3
import gc
from copy import deepcopy
from datetime import timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from app import cricket_store, main


def example():
    day = (main._current_local_date() - timedelta(days=1)).isoformat()
    clubs = [{"id": "a", "name": "Alpha"}, {"id": "b", "name": "Beta"}]
    members = [
        {"id": "m1", "name": "Alice", "aliases": ["A Lee"], "club_memberships": [{"club_id": "a"}]},
        {"id": "m2", "name": "Bob", "aliases": [], "club_memberships": [{"club_id": "b"}]},
        {"id": "m3", "name": "Charlie", "aliases": [], "club_memberships": [{"club_id": "a"}]},
        {"id": "m4", "name": "Dana", "aliases": [], "club_memberships": [{"club_id": "b"}]},
    ]
    for member in members:
        club = clubs[0] if member["club_memberships"][0]["club_id"] == "a" else clubs[1]
        member.update(team_name=club["name"], primary_club_id=club["id"], primary_club_name=club["name"])
    fixture = {
        "id": "f1", "club_id": "a", "club_name": "Alpha", "opponent": "Beta", "date": day,
        "status": "Scheduled", "availability_statuses": {"Alice": "Unavailable"},
        "scorecard": {}, "details": {},
    }
    archive = {"id": "up1", "status": "Approved", "club_id": "a", "club_ids": ["a", "b"], "archive_date_source": "scorecard"}
    card = {
        "date": day, "teams": ["Alpha", "Beta"], "result": "",
        "innings": [{
            "team": "Alpha", "bowling_team": "Beta", "score": "125/5",
            "batting": [{"name": "A Lee", "dismissal": "c Dana b Bob"}],
            "did_not_bat": ["Charlie"], "bowling": [{"name": "Bob"}],
        }],
    }
    return {"clubs": clubs, "members": members, "fixtures": [fixture], "archive_uploads": [archive]}, card


class ScorecardFixtureAvailabilityTests(unittest.TestCase):
    def test_published_card_updates_fixture_and_players_idempotently(self):
        store, card = example()
        with patch.object(main, "_scorecard_from_archive", return_value=card):
            self.assertTrue(main._sync_fixture_results_from_scorecards(store))
            fixture = store["fixtures"][0]
            self.assertEqual(fixture["scorecard"]["heartlake_runs"], "125")
            self.assertEqual(fixture["status"], "Completed")
            self.assertEqual(fixture["availability_statuses"], {
                "Alice": "Available", "Bob": "Available", "Charlie": "Available", "Dana": "Available",
            })
            self.assertFalse(main._sync_fixture_results_from_scorecards(store))
            self.assertEqual(main._scorecard_participant_ids(store, fixture, card, store["clubs"][0]), {"m1", "m3"})
            self.assertEqual(main._scorecard_participant_ids(store, fixture, card, store["clubs"][1]), {"m2", "m4"})

    def test_existing_scores_are_preserved_but_participation_is_updated(self):
        store, card = example()
        fixture = store["fixtures"][0]
        fixture["scorecard"] = {"heartlake_runs": "99", "result": "Alpha won"}
        with patch.object(main, "_scorecard_from_archive", return_value=card):
            self.assertTrue(main._sync_fixture_results_from_scorecards(store))
        self.assertEqual(fixture["scorecard"]["heartlake_runs"], "99")
        self.assertEqual(fixture["availability_statuses"]["Alice"], "Available")

    def test_ambiguous_fixtures_and_cards_do_not_match(self):
        store, card = example()
        store["fixtures"].append({**deepcopy(store["fixtures"][0]), "id": "f2"})
        with patch.object(main, "_scorecard_from_archive", return_value=card):
            self.assertFalse(main._sync_fixture_results_from_scorecards(store))
        self.assertEqual(store["fixtures"][0]["availability_statuses"]["Alice"], "Unavailable")
        store["fixtures"].pop()
        store["archive_uploads"].append({**store["archive_uploads"][0], "id": "up2"})
        with patch.object(main, "_scorecard_from_archive", return_value=card):
            self.assertFalse(main._sync_fixture_results_from_scorecards(store))

    def test_today_is_matched_future_and_pending_are_not(self):
        store, card = example()
        today = main._current_local_date().isoformat()
        store["fixtures"][0]["date"] = card["date"] = today
        with patch.object(main, "_scorecard_from_archive", return_value=card):
            self.assertTrue(main._sync_fixture_results_from_scorecards(store))
        self.assertEqual(store["fixtures"][0]["status"], "Scheduled")
        self.assertEqual(store["fixtures"][0]["availability_statuses"]["Alice"], "Available")
        store, card = example()
        store["fixtures"][0]["date"] = card["date"] = (main._current_local_date() + timedelta(days=1)).isoformat()
        with patch.object(main, "_scorecard_from_archive", return_value=card):
            self.assertFalse(main._sync_fixture_results_from_scorecards(store))
        store["fixtures"][0]["date"] = card["date"] = today
        store["archive_uploads"][0]["status"] = "Pending review"
        with patch.object(main, "_scorecard_from_archive", return_value=card):
            self.assertFalse(main._sync_fixture_results_from_scorecards(store))

    def test_ambiguous_player_names_are_not_written(self):
        store, card = example()
        store["members"].append({"id": "m5", "name": "Other Alice", "aliases": ["A Lee"], "club_memberships": [{"club_id": "a"}]})
        with patch.object(main, "_scorecard_from_archive", return_value=card):
            main._sync_fixture_results_from_scorecards(store)
        self.assertEqual(store["fixtures"][0]["availability_statuses"]["Alice"], "Unavailable")

    def test_direct_match_and_untrusted_dates(self):
        store, card = example()
        store["archive_uploads"][0]["archive_date_source"] = "filesystem-modified"
        with patch.object(main, "_scorecard_from_archive", return_value=card):
            self.assertFalse(main._sync_fixture_results_from_scorecards(store))
            store["archive_uploads"][0]["match_id"] = "f1"
            self.assertTrue(main._sync_fixture_results_from_scorecards(store))

    def test_explicit_link_to_another_fixture_is_not_inferred(self):
        store, card = example()
        store["archive_uploads"][0]["match_id"] = "different"
        with patch.object(main, "_scorecard_from_archive", return_value=card):
            self.assertFalse(main._sync_fixture_results_from_scorecards(store))

    def test_different_dates_or_teams_do_not_match(self):
        for field in ("date", "teams"):
            with self.subTest(field=field):
                store, card = example()
                card[field] = "2020-01-01" if field == "date" else ["Alpha", "Other"]
                with patch.object(main, "_scorecard_from_archive", return_value=card):
                    self.assertFalse(main._sync_fixture_results_from_scorecards(store))

    def test_global_name_match_does_not_assign_a_player_to_wrong_team(self):
        store, card = example()
        store["members"][0]["club_memberships"] = [{"club_id": "b"}]
        with patch.object(main, "_scorecard_from_archive", return_value=card):
            main._sync_fixture_results_from_scorecards(store)
        self.assertEqual(store["fixtures"][0]["availability_statuses"]["Alice"], "Unavailable")

    def test_availability_response_and_save_for_opponent_club(self):
        store, card = example()
        member = store["members"][1]
        user = {"id": 7}
        saved = []
        with (
            patch.object(main, "_auth_user_from_token", return_value=(user, "b")),
            patch.object(main, "load_store", return_value=store),
            patch.object(main, "save_store", side_effect=lambda data: saved.append(deepcopy(data))),
            patch.object(main, "_scorecard_from_archive", return_value=card),
            patch.object(main, "_member_for_user", return_value=member),
            patch.object(main, "_auth_user_payload", return_value={}),
            patch.object(main, "_sorted_club_choices", return_value=[]),
            patch.object(main, "_player_season_availability", return_value={}),
        ):
            result = main.player_availability_data("token")
            self.assertEqual(len(result["fixtures"]), 1)
            fixture = result["fixtures"][0]
            self.assertEqual(fixture["opponent"], "Alpha")
            self.assertEqual(fixture["availability_statuses"]["Bob"], "Available")
            self.assertTrue(fixture["availability_read_only"])
            self.assertEqual(saved[0]["fixtures"][0]["availability_statuses"]["Bob"], "Available")
            main.player_availability_data("token")
            self.assertEqual(len(saved), 1)

    def test_same_day_played_availability_cannot_be_changed_by_post(self):
        store, card = example()
        store["fixtures"][0]["date"] = card["date"] = main._current_local_date().isoformat()
        request = main.PlayerAvailabilitySelfRequest(fixture_id="f1", status="Unavailable", club_id="a")
        with (
            patch.object(main, "_auth_user_from_token", return_value=({"id": 7}, "a")),
            patch.object(main, "load_store", return_value=store),
            patch.object(main, "_member_for_user", return_value=store["members"][0]),
            patch.object(main, "_require_feature"),
            patch.object(main, "_scorecard_from_archive", return_value=card),
            patch.object(main, "save_store") as save,
        ):
            with self.assertRaises(main.HTTPException) as error:
                main.save_player_availability(request, "token")
            self.assertEqual(error.exception.status_code, 409)
            save.assert_not_called()

    def test_participation_survives_database_reload(self):
        store, card = example()
        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "uploads").mkdir()
            with sqlite3.connect(root / "test.db") as connection:
                connection.executescript("""
                    CREATE TABLE app_users (id INTEGER PRIMARY KEY, member_id TEXT, primary_club_id TEXT, role TEXT, player_id TEXT);
                    CREATE TABLE app_auth_sessions (token TEXT PRIMARY KEY, current_club_id TEXT);
                    CREATE TABLE app_player_season_availability (user_id INTEGER, club_id TEXT, status TEXT, note TEXT, updated_at TEXT, PRIMARY KEY (user_id, club_id));
                """)
            connection.close()
            with (
                patch.object(cricket_store, "DATABASE_FILE", root / "test.db"),
                patch.object(cricket_store, "CACHE_FILE", root / "cache.json"),
                patch.object(cricket_store, "UPLOAD_DIR", root / "uploads"),
                patch.object(cricket_store, "_legacy_state_from_connection", return_value={"members": [], "fixtures": [], "clubs": []}),
                patch.object(cricket_store, "refresh_llm_document_index", return_value=[]),
                patch.object(cricket_store, "_STORE_CACHE_SIGNATURE", None),
                patch.object(cricket_store, "_STORE_CACHE_PAYLOAD", None),
                patch.object(main, "_scorecard_from_archive", return_value=card),
            ):
                main._sync_fixture_results_from_scorecards(store)
                cricket_store.save_store(store)
                cricket_store._STORE_CACHE_SIGNATURE = None
                cricket_store._STORE_CACHE_PAYLOAD = None
                reloaded = cricket_store.load_store()
                fixture = next(item for item in reloaded["fixtures"] if item["id"] == "f1")
                self.assertEqual(fixture["availability_statuses"]["Alice"], "Available")
                self.assertEqual(fixture["availability_statuses"]["Bob"], "Available")
                self.assertEqual(fixture["scorecard"]["heartlake_runs"], "125")
                self.assertIn("m1", main._scorecard_participant_ids(reloaded, fixture, card))
            gc.collect()
