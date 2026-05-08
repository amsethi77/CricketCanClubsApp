import html as html_lib
import importlib
import os
import re
import shutil
import sys
import tempfile
import time
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient


REPO_ROOT = Path(__file__).resolve().parents[1]
SOURCE_DATA_DIR = REPO_ROOT / "app" / "data"
SOURCE_SEED_FILE = SOURCE_DATA_DIR / "seed.json"
SOURCE_DB_FILE = SOURCE_DATA_DIR / "cricketclubapp.db"
SOURCE_CACHE_FILE = SOURCE_DATA_DIR / "store_cache.json"
SOURCE_DASHBOARD_CACHE_FILE = SOURCE_DATA_DIR / "dashboard_cache.json"


def _clear_app_modules() -> None:
    for name in list(sys.modules):
        if name == "app" or name.startswith("app."):
            sys.modules.pop(name, None)


def _copy_runtime_files(runtime_root: Path) -> dict[str, Path]:
    data_root = runtime_root / "data"
    uploads_root = runtime_root / "uploads"
    duplicates_root = runtime_root / "duplicates"
    data_root.mkdir(parents=True, exist_ok=True)
    uploads_root.mkdir(parents=True, exist_ok=True)
    duplicates_root.mkdir(parents=True, exist_ok=True)

    shutil.copy2(SOURCE_SEED_FILE, data_root / "seed.json")
    shutil.copy2(SOURCE_DB_FILE, data_root / "cricketclubapp.db")
    shutil.copy2(SOURCE_CACHE_FILE, data_root / "store_cache.json")
    shutil.copy2(SOURCE_DASHBOARD_CACHE_FILE, data_root / "dashboard_cache.json")

    return {
        "data_root": data_root,
        "db_file": data_root / "cricketclubapp.db",
        "cache_file": data_root / "store_cache.json",
        "dashboard_cache_file": data_root / "dashboard_cache.json",
        "seed_file": data_root / "seed.json",
        "uploads_dir": uploads_root,
        "duplicates_dir": duplicates_root,
    }


def _extract_snapshot_title(page_html: str) -> str:
    match = re.search(
        r'id="clubsPlayerSnapshotTitle">(.*?)</strong>',
        page_html,
        flags=re.S,
    )
    return html_lib.unescape(match.group(1).strip()) if match else ""


class LocalQATestCase(unittest.TestCase):
    maxDiff = None

    def setUp(self) -> None:
        self._original_env = {
            "APP_ENV": os.environ.get("APP_ENV"),
            "CRICKETCLUBAPP_DATA_ROOT": os.environ.get("CRICKETCLUBAPP_DATA_ROOT"),
            "CRICKETCLUBAPP_DATABASE_FILE": os.environ.get("CRICKETCLUBAPP_DATABASE_FILE"),
            "CRICKETCLUBAPP_CACHE_FILE": os.environ.get("CRICKETCLUBAPP_CACHE_FILE"),
            "CRICKETCLUBAPP_DASHBOARD_CACHE_FILE": os.environ.get("CRICKETCLUBAPP_DASHBOARD_CACHE_FILE"),
            "CRICKETCLUBAPP_SEED_FILE": os.environ.get("CRICKETCLUBAPP_SEED_FILE"),
            "CRICKETCLUBAPP_UPLOAD_DIR": os.environ.get("CRICKETCLUBAPP_UPLOAD_DIR"),
            "CRICKETCLUBAPP_DUPLICATE_DIR": os.environ.get("CRICKETCLUBAPP_DUPLICATE_DIR"),
        }
        self._tempdir = tempfile.TemporaryDirectory(prefix="cricketclubapp-qa-")
        runtime_root = Path(self._tempdir.name)
        runtime_paths = _copy_runtime_files(runtime_root)
        os.environ["APP_ENV"] = "local"
        os.environ["CRICKETCLUBAPP_DATA_ROOT"] = str(runtime_paths["data_root"])
        os.environ["CRICKETCLUBAPP_DATABASE_FILE"] = str(runtime_paths["db_file"])
        os.environ["CRICKETCLUBAPP_CACHE_FILE"] = str(runtime_paths["cache_file"])
        os.environ["CRICKETCLUBAPP_DASHBOARD_CACHE_FILE"] = str(runtime_paths["dashboard_cache_file"])
        os.environ["CRICKETCLUBAPP_SEED_FILE"] = str(runtime_paths["seed_file"])
        os.environ["CRICKETCLUBAPP_UPLOAD_DIR"] = str(runtime_root / "uploads")
        os.environ["CRICKETCLUBAPP_DUPLICATE_DIR"] = str(runtime_root / "duplicates")

        _clear_app_modules()
        self.main = importlib.import_module("app.main")
        self.client = TestClient(self.main.app)

    def tearDown(self) -> None:
        try:
            self.client.close()
        except Exception:
            pass
        _clear_app_modules()
        self._tempdir.cleanup()
        for key, value in self._original_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    def signin(self, identifier: str, player_name: str = "") -> dict:
        response = self.client.post(
            "/api/auth/signin",
            json={
                "identifier": identifier,
                "password": "",
                "player_name": player_name,
            },
        )
        self.assertEqual(response.status_code, 200, response.text)
        payload = response.json()
        self.assertTrue(payload.get("token"), "sign-in should return a session token")
        return payload

    def auth_headers(self, token: str) -> dict[str, str]:
        return {"x-auth-token": token}

    def create_fixture(self, token: str, **overrides: object) -> dict:
        today = datetime.utcnow().date()
        fixture_date = (today + timedelta(days=7)).isoformat()
        year = int(fixture_date[:4])
        body = {
            "club_id": "club-testclub",
            "season_year": year,
            "date": fixture_date,
            "date_label": (today + timedelta(days=7)).strftime("%d %b %Y"),
            "opponent": f"QA Opponent {fixture_date}",
            "venue": "QA Ground",
            "match_type": "Friendly",
            "scheduled_time": "09:00",
            "overs": "20",
        }
        body.update(overrides)
        response = self.client.post("/api/season-setup/fixtures", json=body, headers={"x-auth-token": token})
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def fixture_by_opponent(self, fixtures: list[dict], opponent: str) -> dict | None:
        return next((item for item in fixtures if item.get("opponent") == opponent), None)


class UnitQATests(LocalQATestCase):
    def test_u01_auth_scoping_player1(self) -> None:
        auth = self.signin("1111111111")
        visible_clubs = auth.get("visible_clubs") or []
        self.assertEqual(auth["user"]["viewer_member_name"], "player1")
        self.assertEqual({club["name"] for club in visible_clubs}, {"TestClub"})

    def test_u02_auth_scoping_amit_s(self) -> None:
        auth = self.signin("14164508695")
        visible_clubs = auth.get("visible_clubs") or []
        self.assertEqual(auth["user"]["viewer_member_name"], "Amit S")
        self.assertEqual(
            {club["name"] for club in visible_clubs},
            {"Heartlake Cricket Club", "Coca Cola XI"},
        )

    def test_u03_visible_clubs_are_deduped(self) -> None:
        auth = self.signin("14164508695")
        token = auth["token"]
        user_row, current_club_id = self.main._auth_user_from_token(token)
        store = self.main.load_store()
        visible = self.main._visible_club_choices_for_user(store, user_row, current_club_id)
        club_ids = [club["id"] for club in visible]
        self.assertEqual(len(club_ids), len(set(club_ids)))
        self.assertEqual(
            {club["name"] for club in visible},
            {"Heartlake Cricket Club", "Coca Cola XI"},
        )

    def test_u04_public_auth_options_hides_superadmin(self) -> None:
        options = self.client.get("/api/auth/options")
        self.assertEqual(options.status_code, 200, options.text)
        payload = options.json()
        role_names = {role.get("role_name") for role in payload.get("roles", [])}
        self.assertNotIn("superadmin", role_names)
        self.assertTrue({"player", "captain", "club_admin"}.issubset(role_names))
        linked_member_names = {member.get("name") for member in payload.get("members", [])}
        self.assertNotIn("player1", linked_member_names)
        self.assertNotIn("captain1", linked_member_names)
        self.assertNotIn("clubadmin1", linked_member_names)

    def test_u05_season_setup_data_includes_current_year_and_scoped_fixtures(self) -> None:
        auth = self.signin("2222222222")
        response = self.client.get("/api/season-setup/data?club_id=club-testclub", headers=self.auth_headers(auth["token"]))
        self.assertEqual(response.status_code, 200, response.text)
        payload = response.json()
        current_year = str(datetime.utcnow().year)
        self.assertEqual(payload["club"]["id"], "club-testclub")
        self.assertIn(current_year, payload.get("season_years", []))
        self.assertEqual(payload.get("selected_year"), current_year)
        self.assertTrue(all(fixture.get("club_id") == "club-testclub" for fixture in payload.get("fixtures", [])))

    def test_u06_player_profile_data_contains_contact_and_role(self) -> None:
        auth = self.signin("14164508695")
        response = self.client.get("/api/player/profile-data", headers=self.auth_headers(auth["token"]))
        self.assertEqual(response.status_code, 200, response.text)
        payload = response.json()
        member = payload.get("member") or {}
        self.assertIn("Amit", member.get("full_name") or member.get("name") or "")
        self.assertTrue(member.get("phone") or member.get("mobile"))
        self.assertTrue(member.get("email"))
        self.assertTrue(member.get("role"))
        self.assertIsInstance(payload.get("summary_stats"), dict)
        self.assertIsInstance(payload.get("year_stats"), list)
        self.assertIsInstance(payload.get("club_stats"), list)
        club_names = [row.get("club_name") for row in payload.get("club_stats", []) if row.get("club_name")]
        self.assertEqual(len(club_names), len(set(club_names)))

    def test_u07_dashboard_scopes_visible_clubs_and_selected_season(self) -> None:
        auth = self.signin("1111111111")
        current_year = str(datetime.utcnow().year)
        response = self.client.get(
            "/api/dashboard",
            params={"focus_club_id": "club-testclub", "selected_season_year": current_year},
            headers=self.auth_headers(auth["token"]),
        )
        self.assertEqual(response.status_code, 200, response.text)
        payload = response.json()
        self.assertEqual(payload["selected_season_year"], current_year)
        self.assertEqual(payload["club"]["id"], "club-testclub")
        self.assertEqual({club["name"] for club in payload.get("visible_clubs", [])}, {"TestClub"})
        self.assertTrue(payload.get("combined_player_stats"))

    def test_u08_register_can_create_new_club_and_seed_creator(self) -> None:
        response = self.client.post(
            "/api/auth/register",
            json={
                "display_name": "QA Player",
                "mobile": "5551234567",
                "email": "qa.player@example.com",
                "password": "pass1234",
                "role": "player",
                "primary_club_id": "",
                "member_name": "QA Player",
                "club_name": "QA United",
                "club_city": "Toronto",
                "club_country": "Canada",
            },
        )
        self.assertEqual(response.status_code, 200, response.text)
        payload = response.json()
        self.assertEqual(payload["user"]["role"], "club_admin")
        self.assertEqual(payload["user"]["primary_club_id"], payload["user"]["current_club_id"])
        self.assertEqual(payload["member"]["name"], "QA Player")
        self.assertTrue(any(club["name"] == "QA United" for club in payload.get("clubs", [])))

    def test_u09_admin_center_requires_superadmin(self) -> None:
        captain_auth = self.signin("2222222222")
        captain_response = self.client.get("/admin-center", headers=self.auth_headers(captain_auth["token"]))
        self.assertEqual(captain_response.status_code, 403, captain_response.text)
        superadmin_auth = self.signin("14164508695")
        superadmin_response = self.client.get("/admin-center", headers=self.auth_headers(superadmin_auth["token"]))
        self.assertEqual(superadmin_response.status_code, 200, superadmin_response.text)
        self.assertIn("Admin center", superadmin_response.text)


class FunctionalQATests(LocalQATestCase):
    def test_f01_clubs_snapshot_for_amit_s_resolves_to_amit_sethi(self) -> None:
        auth = self.signin("14164508695")
        response = self.client.get("/clubs")
        self.assertEqual(response.status_code, 200, response.text)
        snapshot_title = _extract_snapshot_title(response.text)
        expected_title = auth["user"]["viewer_member_full_name"] or auth["user"]["viewer_member_name"]
        self.assertEqual(snapshot_title, expected_title)
        self.assertNotIn("Amit G (Amit Gaba)", response.text)

    def test_f02_clubs_snapshot_for_player1_resolves_to_player1(self) -> None:
        auth = self.signin("1111111111")
        response = self.client.get("/clubs")
        self.assertEqual(response.status_code, 200, response.text)
        snapshot_title = _extract_snapshot_title(response.text)
        expected_title = auth["user"]["viewer_member_full_name"] or auth["user"]["viewer_member_name"]
        self.assertEqual(snapshot_title, expected_title)

    def test_f03_signin_page_renders_leaders_and_form(self) -> None:
        response = self.client.get("/signin")
        self.assertEqual(response.status_code, 200, response.text)
        self.assertIn("Top 5 Batsmen", response.text)
        self.assertIn("Top 5 Bowlers", response.text)
        self.assertIn("Top 10 Clubs by Win Rate", response.text)
        self.assertIn('action="/signin/quick"', response.text)

    def test_f04_register_page_renders(self) -> None:
        response = self.client.get("/register")
        self.assertEqual(response.status_code, 200, response.text)
        self.assertIn("Register", response.text)

    def test_f05_captain_can_create_future_fixture_for_testclub(self) -> None:
        auth = self.signin("2222222222")
        token = auth["token"]
        result = self.create_fixture(token, opponent="Functional Fixture Team")
        fixtures = result.get("fixtures") or []
        created = next((item for item in fixtures if item.get("opponent") == "Functional Fixture Team"), None)
        self.assertIsNotNone(created)
        self.assertEqual(created["club_id"], "club-testclub")
        self.assertEqual(result["club"]["id"], "club-testclub")

    def test_f06_clubadmin_can_edit_future_fixture(self) -> None:
        captain_auth = self.signin("2222222222")
        create_result = self.create_fixture(captain_auth["token"], opponent="Editable Fixture Team")
        created = next((item for item in create_result.get("fixtures", []) if item.get("opponent") == "Editable Fixture Team"), None)
        self.assertIsNotNone(created)
        fixture_id = created["id"]

        clubadmin_auth = self.signin("3333333333")
        update_body = {
            "club_id": "club-testclub",
            "season_year": int(created["season_year"]),
            "date": created["date"],
            "date_label": created["date_label"],
            "opponent": "Updated Fixture Team",
            "venue": "Updated QA Ground",
            "match_type": "League",
            "scheduled_time": "10:30",
            "overs": "25",
        }
        response = self.client.put(
            f"/api/admin/clubs/club-testclub/fixtures/{fixture_id}",
            json=update_body,
            headers={"x-auth-token": clubadmin_auth["token"]},
        )
        self.assertEqual(response.status_code, 200, response.text)
        updated = next((item for item in response.json().get("fixtures", []) if item.get("id") == fixture_id), None)
        self.assertIsNotNone(updated)
        self.assertEqual(updated["opponent"], "Updated Fixture Team")
        self.assertEqual(updated.get("details", {}).get("venue"), "Updated QA Ground")

    def test_f07_scorebook_setup_and_ball_updates_fixture(self) -> None:
        captain_auth = self.signin("2222222222")
        create_result = self.create_fixture(captain_auth["token"], opponent="Scorebook Team")
        created = next((item for item in create_result.get("fixtures", []) if item.get("opponent") == "Scorebook Team"), None)
        self.assertIsNotNone(created)
        fixture_id = created["id"]
        superadmin_auth = self.signin("14164508695")
        setup_response = self.client.post(
            f"/api/matches/{fixture_id}/scorebook/setup",
            json={
                "innings_number": 1,
                "batting_team": "TestClub",
                "bowling_team": "Scorebook Team",
                "overs_limit": 20,
                "target_runs": 0,
                "status": "Not started",
                "batters": ["player1", "captain1", "clubadmin1", "", "", "", "", "", "", "", ""],
                "bowlers": ["clubadmin1", "", "", "", "", "", "", "", "", "", ""],
            },
            headers=self.auth_headers(superadmin_auth["token"]),
        )
        self.assertEqual(setup_response.status_code, 200, setup_response.text)
        ball_response = self.client.post(
            f"/api/matches/{fixture_id}/scorebook/ball",
            json={
                "innings_number": 1,
                "over_number": 1,
                "ball_number": 1,
                "striker": "player1",
                "non_striker": "captain1",
                "bowler": "clubadmin1",
                "runs_bat": 1,
                "commentary": "QA ball",
            },
            headers=self.auth_headers(superadmin_auth["token"]),
        )
        self.assertEqual(ball_response.status_code, 200, ball_response.text)
        store = self.main.load_store()
        updated = next((item for item in store.get("fixtures", []) if item.get("id") == fixture_id), None)
        self.assertIsNotNone(updated)
        scorebook = updated.get("scorebook") or {}
        self.assertEqual(len((scorebook.get("innings") or [])[0].get("balls", [])), 1)

    def test_f08_player_can_save_availability_for_upcoming_fixture(self) -> None:
        captain_auth = self.signin("2222222222")
        create_result = self.create_fixture(captain_auth["token"], opponent="Availability Team")
        created = next((item for item in create_result.get("fixtures", []) if item.get("opponent") == "Availability Team"), None)
        self.assertIsNotNone(created)
        player_auth = self.signin("1111111111")
        response = self.client.post(
            "/api/player/availability",
            json={
                "fixture_id": created["id"],
                "status": "Available",
                "note": "QA ready",
                "club_id": "club-testclub",
            },
            headers=self.auth_headers(player_auth["token"]),
        )
        self.assertEqual(response.status_code, 200, response.text)
        store = self.main.load_store()
        updated = next((item for item in store.get("fixtures", []) if item.get("id") == created["id"]), None)
        self.assertEqual((updated or {}).get("availability_statuses", {}).get("player1"), "Available")

    def test_f09_admin_center_opens_for_superadmin_only(self) -> None:
        superadmin_auth = self.signin("14164508695")
        superadmin_page = self.client.get("/admin-center", headers=self.auth_headers(superadmin_auth["token"]))
        self.assertEqual(superadmin_page.status_code, 200, superadmin_page.text)
        self.assertIn("Admin center", superadmin_page.text)
        captain_auth = self.signin("2222222222")
        forbidden = self.client.get("/admin-center", headers=self.auth_headers(captain_auth["token"]))
        self.assertEqual(forbidden.status_code, 403, forbidden.text)

    def test_f10_past_fixture_lock(self) -> None:
        auth = self.signin("2222222222")
        yesterday = (datetime.utcnow().date() - timedelta(days=1)).isoformat()
        create_result = self.create_fixture(
            auth["token"],
            date=yesterday,
            date_label=datetime.utcnow().date().strftime("%d %b %Y"),
            season_year=int(yesterday[:4]),
            opponent="Past Lock Team",
        )
        created = next((item for item in create_result.get("fixtures", []) if item.get("opponent") == "Past Lock Team"), None)
        self.assertIsNotNone(created)
        response = self.client.put(
            f"/api/admin/clubs/club-testclub/fixtures/{created['id']}",
            json={
                "club_id": "club-testclub",
                "season_year": int(created["season_year"]),
                "date": created["date"],
                "date_label": created["date_label"],
                "opponent": "Past Lock Team Updated",
                "venue": "Locked Ground",
                "match_type": "Friendly",
                "scheduled_time": "12:00",
                "overs": "20",
            },
            headers={"x-auth-token": auth["token"]},
        )
        self.assertEqual(response.status_code, 400, response.text)
        self.assertEqual(response.json()["detail"], "Past fixtures cannot be edited.")

    def test_f11_signout_invalidates_session(self) -> None:
        auth = self.signin("1111111111")
        token = auth["token"]
        me_before = self.client.get("/api/auth/me", headers={"x-auth-token": token})
        self.assertEqual(me_before.status_code, 200, me_before.text)
        signout = self.client.post("/api/auth/signout", headers={"x-auth-token": token})
        self.assertEqual(signout.status_code, 200, signout.text)
        me_after = self.client.get("/api/auth/me", headers={"x-auth-token": token})
        self.assertEqual(me_after.status_code, 401, me_after.text)

    def test_f12_chat_can_answer_basic_player_question(self) -> None:
        response = self.client.post(
            "/api/chat",
            json={
                "question": "What is Amit S full name?",
                "session_id": "qa-session",
                "history": [],
                "focus_club_id": "club-heartlake",
            },
        )
        self.assertEqual(response.status_code, 200, response.text)
        payload = response.json()
        self.assertTrue(payload.get("answer"))
        self.assertEqual(payload.get("session_id"), "qa-session")

    def test_f13_future_performance_questions_route_to_forecast(self) -> None:
        brain = importlib.import_module("app.cricket_brain")
        question = "how is Amit Sethi's performance going to be in 2026 season"
        self.assertTrue(brain._prediction_question_intent(question))
        store = self.main.load_store()
        with (
            patch.object(
                brain,
                "get_llm_status",
                return_value={"available": True, "provider": "ollama", "model": "llama3.2:latest"},
            ),
            patch.object(brain, "_forecast_answer", return_value="Forecast answer") as forecast_mock,
            patch.object(
                brain,
                "_heuristic_answer",
                side_effect=AssertionError("heuristic should not run for forecast prompts"),
            ),
        ):
            payload = brain.answer_question(question, store, history=[], session_id="forecast-qa")
        self.assertEqual(payload.get("mode"), "forecast")
        self.assertEqual(payload.get("source_provider"), "ollama")
        self.assertEqual(payload.get("answer"), "Forecast answer")
        forecast_mock.assert_called_once()

    def test_f14_hallucinated_forecast_numbers_fall_back_to_safe_text(self) -> None:
        brain = importlib.import_module("app.cricket_brain")
        question = "how is Amit Sethi's performance going to be in 2026 season"
        store = self.main.load_store()

        class _FakeResponse:
            def raise_for_status(self) -> None:
                return None

            def json(self) -> dict[str, dict[str, str]]:
                return {
                    "message": {
                        "content": (
                            "Amit Sethi will score 800+ runs, play 19 matches, and take 1-2 wickets in 2026."
                        )
                    }
                }

        with (
            patch.object(
                brain,
                "get_llm_status",
                return_value={"available": True, "provider": "ollama", "model": "llama3.2:latest"},
            ),
            patch.object(brain.httpx, "post", return_value=_FakeResponse()),
        ):
            answer = brain._forecast_answer(question, store, history=[])

        self.assertIsNotNone(answer)
        self.assertIn("cautious forecast", answer.lower())
        self.assertNotIn("800+", answer)
        self.assertNotIn("19 matches", answer)

    def test_f15_profanity_is_moderated_before_llm(self) -> None:
        brain = importlib.import_module("app.cricket_brain")
        store = self.main.load_store()
        payload = brain.answer_question("you are shit", store, history=[], session_id="moderation-qa")
        self.assertEqual(payload.get("mode"), "moderated")
        self.assertEqual(payload.get("source_label"), "Content filter")
        self.assertIn("respectful", payload.get("answer", "").lower())

    def test_f16_club_forecast_does_not_pull_in_player_snippets(self) -> None:
        brain = importlib.import_module("app.cricket_brain")
        store = self.main.load_store()
        question = "how about Coca Cola Club's performance in 2026"
        analysis_store = brain._global_analysis_store(store)
        with (
            patch.object(
                brain,
                "get_llm_status",
                return_value={"available": True, "provider": "ollama", "model": "llama3.2:latest"},
            ),
            patch.object(brain, "_forecast_rows_for_members", side_effect=AssertionError("player snippets should not be used for club-only forecasts")),
            patch.object(brain, "_forecast_club_snippets", return_value=[{"kind": "forecast-club", "key": "club", "text": "[forecast-club] Coca Cola XI\nseason: 2026\noverall: matches_played=2"}]),
            patch.object(brain.httpx, "post") as post_mock,
        ):
            post_mock.return_value.raise_for_status.return_value = None
            post_mock.return_value.json.return_value = {"message": {"content": "Coca Cola XI should remain stable in 2026."}}
            answer = brain._forecast_answer(question, store, history=[])

        self.assertIsNotNone(answer)
        self.assertNotIn("Amit Sethi", answer or "")
        self.assertNotIn("Amit Gaba", answer or "")
        self.assertIn("Coca Cola XI", answer or "")

    def test_f17_club_forecast_rejects_player_leakage(self) -> None:
        brain = importlib.import_module("app.cricket_brain")
        store = self.main.load_store()
        question = "how about Coca Cola Club's performance in 2026"

        class _FakeResponse:
            def raise_for_status(self) -> None:
                return None

            def json(self) -> dict[str, dict[str, str]]:
                return {
                    "message": {
                        "content": (
                            "Amit Sethi will lead Coca Cola XI, Amit Gaba will support Heartlake Cricket Club, "
                            "and TP Community will struggle."
                        )
                    }
                }

        with (
            patch.object(
                brain,
                "get_llm_status",
                return_value={"available": True, "provider": "ollama", "model": "llama3.2:latest"},
            ),
            patch.object(brain.httpx, "post", return_value=_FakeResponse()),
        ):
            answer = brain._forecast_answer(question, store, history=[])

        self.assertIsNotNone(answer)
        self.assertIn("cautious club forecast", answer.lower())
        self.assertNotIn("amit sethi", answer.lower())
        self.assertNotIn("amit gaba", answer.lower())
        self.assertNotIn("heartlake", answer.lower())


class NonFunctionalQATests(LocalQATestCase):
    def test_n01_dashboard_latency(self) -> None:
        auth = self.signin("1111111111")
        token = auth["token"]
        started = time.perf_counter()
        response = self.client.get(
            "/api/dashboard",
            params={
                "focus_club_id": "club-testclub",
                "requested_season_year": str(datetime.utcnow().year),
            },
            headers={"x-auth-token": token},
        )
        elapsed = time.perf_counter() - started
        self.assertEqual(response.status_code, 200, response.text)
        self.assertLess(elapsed, 5.0, f"Dashboard response was too slow: {elapsed:.3f}s")

    def test_n02_health_endpoint(self) -> None:
        started = time.perf_counter()
        response = self.client.get("/api/health")
        elapsed = time.perf_counter() - started
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json().get("status"), "ok")
        self.assertLess(elapsed, 1.0, f"Health endpoint was too slow: {elapsed:.3f}s")

    def test_n03_pages_render_without_fallback_or_crash(self) -> None:
        self.signin("14164508695")
        signin_page = self.client.get("/signin")
        clubs_page = self.client.get("/clubs")
        season_page = self.client.get("/season-setup")
        self.assertEqual(signin_page.status_code, 200, signin_page.text)
        self.assertEqual(clubs_page.status_code, 200, clubs_page.text)
        self.assertEqual(season_page.status_code, 200, season_page.text)
        self.assertIn("Amit Sethi", clubs_page.text)
        self.assertNotIn("Amit G (Amit Gaba)", clubs_page.text)
        self.assertNotIn("Traceback", signin_page.text + clubs_page.text + season_page.text)

    def test_n04_signin_stats_endpoint_is_fast_and_populated(self) -> None:
        started = time.perf_counter()
        response = self.client.get("/api/public/signin-stats")
        elapsed = time.perf_counter() - started
        self.assertEqual(response.status_code, 200, response.text)
        payload = response.json()
        self.assertIsInstance(payload.get("batting_leaders"), list)
        self.assertIsInstance(payload.get("bowling_leaders"), list)
        self.assertIsInstance(payload.get("club_leaders"), list)
        self.assertGreater(len(payload.get("batting_leaders", [])), 0)
        self.assertGreater(len(payload.get("bowling_leaders", [])), 0)
        self.assertLess(elapsed, 2.5, f"Signin stats endpoint was too slow: {elapsed:.3f}s")

    def test_n05_season_setup_data_is_fast_and_has_year_list(self) -> None:
        auth = self.signin("2222222222")
        started = time.perf_counter()
        response = self.client.get("/api/season-setup/data?club_id=club-testclub", headers=self.auth_headers(auth["token"]))
        elapsed = time.perf_counter() - started
        self.assertEqual(response.status_code, 200, response.text)
        payload = response.json()
        self.assertTrue(payload.get("season_years"))
        self.assertLess(elapsed, 2.5, f"Season setup data was too slow: {elapsed:.3f}s")


if __name__ == "__main__":
    unittest.main(verbosity=2)
