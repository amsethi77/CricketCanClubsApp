import base64
import html as html_lib
import importlib
import io
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


def _tiny_png_bytes() -> bytes:
    return base64.b64decode(
        b"iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO2b5XQAAAAASUVORK5CYII="
    )


def _tiny_unique_png_bytes() -> bytes:
    return _tiny_png_bytes() + b"qa-mobile-upload"


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
    def test_registration_options_register_clubs_and_players_from_scored_fixtures(self) -> None:
        captain = self.signin("2222222222")
        previous_day = (self.main._current_local_date() - timedelta(days=1)).isoformat()
        created = self.create_fixture(captain["token"], opponent="Afghan QA Eagles")
        fixture = next(item for item in created["fixtures"] if item["opponent"] == "Afghan QA Eagles")
        store = self.main.load_store()
        stored = next(item for item in store["fixtures"] if item["id"] == fixture["id"])
        stored["date"] = previous_day
        stored["status"] = "Completed"
        stored["scorebook"] = {
            "innings": [
                {
                    "inning_number": 1,
                    "batting_team": "Afghan QA Eagles",
                    "bowling_team": stored["club_name"],
                    "batters": [{"slot_number": 1, "player_name": "Afghan QA Batter"}],
                    "bowlers": [{"slot_number": 1, "player_name": "Home QA Bowler"}],
                    "balls": [
                        {
                            "striker": "Afghan QA Batter",
                            "bowler": "Home QA Bowler",
                            "fielder": "Home QA Fielder",
                            "wicket": True,
                            "wicket_type": "caught",
                            "wicket_player": "Afghan QA Batter",
                            "runs_bat": 1,
                        }
                    ],
                },
                {
                    "inning_number": 2,
                    "batting_team": stored["club_name"],
                    "bowling_team": "Afghan QA Eagles",
                    "batters": [{"slot_number": 1, "player_name": "Home QA Batter"}],
                    "bowlers": [{"slot_number": 1, "player_name": "Afghan QA Bowler"}],
                    "balls": [
                        {
                            "striker": "Home QA Batter",
                            "bowler": "Afghan QA Bowler",
                            "runs_bat": 1,
                        }
                    ],
                },
            ]
        }
        self.main.save_store(store)

        options = self.client.get("/api/auth/options")
        self.assertEqual(options.status_code, 200, options.text)
        payload = options.json()
        afghan_club = next(club for club in payload["clubs"] if club["name"] == "Afghan QA Eagles")
        members = {member["name"]: member for member in payload["members"]}
        self.assertIn("Afghan QA Batter", members)
        self.assertIn("Afghan QA Bowler", members)
        self.assertIn("Home QA Bowler", members)
        self.assertIn("Home QA Fielder", members)
        self.assertIn("Home QA Batter", members)

        saved = self.main.load_store()
        stored_members = {member["name"]: member for member in saved["members"]}
        for name in ("Afghan QA Batter", "Afghan QA Bowler"):
            self.assertTrue(
                any(item.get("club_id") == afghan_club["id"] for item in stored_members[name]["club_memberships"])
            )
        for name in ("Home QA Bowler", "Home QA Fielder", "Home QA Batter"):
            self.assertFalse(
                any(item.get("club_id") == afghan_club["id"] for item in stored_members[name]["club_memberships"])
            )

        self.assertEqual(
            sum(1 for club in saved["clubs"] if club["name"] == "Afghan QA Eagles"),
            1,
        )
        self.client.get("/api/auth/options")
        saved_again = self.main.load_store()
        self.assertEqual(
            sum(1 for member in saved_again["members"] if member["name"] == "Afghan QA Batter"),
            1,
        )

    def test_past_scored_fixture_is_listed_in_the_date_and_season_scorecard_archive(self) -> None:
        captain = self.signin("2222222222")
        previous_day = (self.main._current_local_date() - timedelta(days=1)).isoformat()
        created = self.create_fixture(captain["token"], opponent="Archive Fixture XI")
        fixture = next(item for item in created["fixtures"] if item["opponent"] == "Archive Fixture XI")
        store = self.main.load_store()
        stored = next(item for item in store["fixtures"] if item["id"] == fixture["id"])
        stored["date"] = previous_day
        stored["date_label"] = previous_day
        stored["status"] = "Live"
        stored["scorebook"] = {
            "innings": [
                {
                    "inning_number": 1,
                    "batting_team": stored["club_name"],
                    "bowling_team": stored["opponent"],
                    "overs_limit": 20,
                    "batters": [{"slot_number": 1, "player_name": "player1"}],
                    "bowlers": [{"slot_number": 1, "player_name": "Opponent Bowler"}],
                    "balls": [
                        {
                            "striker": "player1",
                            "non_striker": "Player Two",
                            "bowler": "Opponent Bowler",
                            "runs_bat": 4,
                            "extras_type": "none",
                            "extras_runs": 0,
                        }
                    ],
                }
            ]
        }
        self.main.save_store(store)

        response = self.client.get(
            "/api/public/scorecards",
            params={"date": previous_day, "club_id": fixture["club_id"], "year": previous_day[:4]},
        )
        self.assertEqual(response.status_code, 200, response.text)
        cards = response.json()["scorecards"]
        archived = next(item for item in cards if item["id"] == f"f-{fixture['id']}")
        self.assertEqual(archived["source"], "fixture")
        self.assertEqual(archived["date"], previous_day)
        self.assertEqual(archived["year"], previous_day[:4])
        season_setup = self.client.get(
            "/api/season-setup/data",
            headers=self.auth_headers(captain["token"]),
        )
        self.assertTrue(
            next(item for item in season_setup.json()["fixtures"] if item["id"] == fixture["id"])["can_delete_incomplete"]
        )

        detail = self.client.get(f"/api/public/scorecards/{archived['id']}")
        self.assertEqual(detail.status_code, 200, detail.text)
        innings = detail.json()["scorecard"]["innings"]
        self.assertEqual(innings[0]["batting"][0]["runs"], 4)
        self.assertIn("player1", innings[0]["batting"][0]["name"])

    def test_my_availability_marks_historical_played_fixture_available_and_locked(self) -> None:
        captain = self.signin("2222222222")
        previous_day = (self.main._current_local_date() - timedelta(days=1)).isoformat()
        created = self.create_fixture(captain["token"], opponent="Afghan Eagles")
        fixture = next(item for item in created["fixtures"] if item["opponent"] == "Afghan Eagles")
        store = self.main.load_store()
        stored = next(item for item in store["fixtures"] if item["id"] == fixture["id"])
        stored["date"] = previous_day
        stored["date_label"] = previous_day
        stored["scorebook"] = {
            "innings": [
                {
                    "inning_number": 1,
                    "batters": [{"slot_number": 1, "player_name": "player1"}],
                    "bowlers": [],
                    "balls": [{"striker": "player1", "runs_bat": 1, "extras_type": "none"}],
                }
            ]
        }
        self.main.save_store(store)

        player = self.signin("1111111111")
        response = self.client.get("/api/player/availability-data", headers=self.auth_headers(player["token"]))
        self.assertEqual(response.status_code, 200, response.text)
        played = next(item for item in response.json()["fixtures"] if item["id"] == fixture["id"])
        self.assertTrue(played["availability_read_only"])
        self.assertEqual(played["availability_statuses"]["player1"], "Available")
        saved = next(item for item in self.main.load_store()["fixtures"] if item["id"] == fixture["id"])
        self.assertEqual(saved["availability_statuses"]["player1"], "Available")

    def test_captain_can_delete_incomplete_archive_upload_but_not_approved_scorecard(self) -> None:
        captain = self.signin("2222222222")
        fixture_data = self.client.get(
            "/api/season-setup/data",
            headers=self.auth_headers(captain["token"]),
        )
        self.assertEqual(fixture_data.status_code, 200, fixture_data.text)
        club = fixture_data.json()["club"]
        store = self.main.load_store()
        store.setdefault("archive_uploads", []).extend(
            [
                {
                    "id": "qa-pending-delete",
                    "status": "Pending Review",
                    "file_name": "pending-scorecard.jpg",
                    "club_id": club["id"],
                    "club_name": club["name"],
                    "uploaded_by_user_id": self.main._auth_user_from_token(captain["token"])[0]["id"],
                },
                {
                    "id": "qa-approved-keep",
                    "status": "Approved",
                    "file_name": "approved-scorecard.jpg",
                    "club_id": club["id"],
                    "club_name": club["name"],
                    "uploaded_by_user_id": self.main._auth_user_from_token(captain["token"])[0]["id"],
                },
            ]
        )
        self.main.save_store(store)

        pending_preview = self.client.get(
            "/api/scorecards/qa-pending-delete/preview",
            headers=self.auth_headers(captain["token"]),
        )
        self.assertEqual(pending_preview.status_code, 200, pending_preview.text)
        self.assertTrue(pending_preview.json()["can_delete"])
        deleted = self.client.delete(
            "/api/admin/archive/qa-pending-delete",
            headers=self.auth_headers(captain["token"]),
        )
        self.assertEqual(deleted.status_code, 200, deleted.text)
        pending_ids = {item["id"] for item in self.main.load_store()["archive_uploads"]}
        self.assertNotIn("qa-pending-delete", pending_ids)

        kept = self.client.delete(
            "/api/admin/archive/qa-approved-keep",
            headers=self.auth_headers(captain["token"]),
        )
        self.assertEqual(kept.status_code, 409, kept.text)
        self.assertIn("qa-approved-keep", {item["id"] for item in self.main.load_store()["archive_uploads"]})
        approved_preview = self.client.get(
            "/api/scorecards/qa-approved-keep/preview",
            headers=self.auth_headers(captain["token"]),
        )
        self.assertEqual(approved_preview.status_code, 200, approved_preview.text)
        self.assertFalse(approved_preview.json()["can_delete"])

    def test_public_match_scorecard_pdf_is_a_downloadable_complete_pdf(self) -> None:
        fixture = {
            "club_name": "TestClub",
            "opponent": "PDF Test XI",
            "date_label": "1 Nov 2026",
            "venue": "QA Ground",
            "match_type": "Friendly",
            "overs": "20",
            "result": "TestClub won by 3 runs",
            "scorebook": {
                "innings": [
                    {
                        "inning_number": 1,
                        "batting_team": "TestClub",
                        "summary": {
                            "runs": 120,
                            "wickets": 1,
                            "legal_balls": 120,
                            "overs": "20.0",
                            "run_rate": 6.0,
                            "extras": 5,
                            "byes": 1,
                            "batting": [
                                {"player_name": "Batter One", "runs": 65, "balls": 40, "fours": 6, "sixes": 2, "status": "out"},
                                {"player_name": "Batter Two", "runs": 50, "balls": 35, "fours": 4, "sixes": 1, "status": "batting"},
                            ],
                            "bowling": [
                                {"player_name": "Bowler One", "legal_balls": 24, "overs": "4.0", "maidens": 0, "runs_conceded": 25, "wickets": 1, "economy": 6.25},
                            ],
                        },
                        "balls": [
                            {"striker": "Batter One", "non_striker": "Batter Two", "runs_bat": 0, "extras_runs": 0, "extras_type": "none"},
                            {"striker": "Batter One", "non_striker": "Batter Two", "runs_bat": 0, "extras_runs": 0, "extras_type": "none", "wicket": True, "wicket_type": "bowled", "wicket_player": "Batter One", "bowler": "Bowler One"},
                        ],
                    }
                ]
            },
        }
        pdf = self.main.scorecard_pdf.build_scorecard_pdf(fixture)
        self.assertTrue(pdf.startswith(b"%PDF-"))
        self.assertGreater(len(pdf), 1000)
        self.assertEqual(
            self.main.scorecard_pdf.scorecard_pdf_filename(fixture),
            "testclub-vs-pdf-test-xi-scorecard.pdf",
        )
        self.assertEqual(self.main.scorecard_pdf._pdf_text(0), "0")

        with patch.object(self.main, "load_store", return_value={"fixtures": []}), patch.object(
            self.main, "_public_match_payload", return_value=fixture
        ):
            response = self.client.get("/api/public/match/pdf-test-id/scorecard.pdf")
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.headers["content-type"], "application/pdf")
        self.assertIn('filename="testclub-vs-pdf-test-xi-scorecard.pdf"', response.headers["content-disposition"])
        self.assertTrue(response.content.startswith(b"%PDF-"))

        with patch.object(self.main, "load_store", return_value={"fixtures": []}), patch.object(
            self.main, "_public_match_payload", side_effect=ValueError("Match not found.")
        ):
            missing = self.client.get("/api/public/match/missing-pdf-id/scorecard.pdf")
        self.assertEqual(missing.status_code, 404)

    def test_ai_scorer_treats_retired_out_as_temporary_without_wicket_or_ball(self) -> None:
        events = self.main.ai_scorer.interpret("retired out")["events"]
        accepted, problems = self.main.ai_scorer.validate(
            events,
            {"runs": 12, "wickets": 2, "legal_balls": 6},
            20,
        )

        self.assertFalse(problems)
        self.assertEqual(len(accepted), 1)
        self.assertEqual(self.main.ai_scorer.describe(accepted[0]), "Retired out")
        self.assertEqual(accepted[0]["projected"], "12/2 (1.0)")
        self.assertEqual(accepted[0]["extras_type"], "retired_out")

    def test_u00_heic_scorecard_preview_is_browser_compatible(self) -> None:
        from PIL import Image

        image_path = self.main.UPLOAD_DIR / "qa-scorecard.heic"
        Image.new("RGB", (3, 2), (220, 40, 40)).save(image_path, format="PNG")

        preview_url = self.main._scorecard_photo_url({"preview_url": "/uploads/qa-scorecard.heic"})
        self.assertRegex(preview_url, r"^/uploads/\.previews/[0-9a-f]{24}\.jpg$")

        response = self.client.get(preview_url)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.headers["content-type"], "image/jpeg")
        with Image.open(io.BytesIO(response.content)) as preview:
            self.assertEqual(preview.size, (3, 2))

    def test_scorecard_vision_selects_tagged_ollama_model(self) -> None:
        store_module = importlib.import_module(self.main.extract_archive_by_id.__module__)
        with patch.object(store_module, "available_ollama_models", return_value=["llama3.2:latest", "qwen3-vl:8b-q4_K_M"]):
            self.assertEqual(store_module.preferred_vision_llm_model(), "qwen3-vl:8b-q4_K_M")

    def test_scorecard_vision_preprocessing_converts_phone_image_without_sips(self) -> None:
        from PIL import Image

        store_module = importlib.import_module(self.main.extract_archive_by_id.__module__)
        source_path = self.main.UPLOAD_DIR / "qa-phone-scorecard.heic"
        Image.new("RGB", (24, 36), (30, 80, 140)).save(source_path, format="PNG")
        converted_path = store_module._image_path_for_llm(source_path, self._tempdir_path())

        with Image.open(converted_path) as converted:
            self.assertEqual(converted.format, "JPEG")
            self.assertEqual(converted.size, (24, 36))

    def test_scorecard_vision_extractor_sends_focused_images_and_json_prompt(self) -> None:
        from PIL import Image
        from unittest.mock import Mock

        store_module = importlib.import_module(self.main.extract_archive_by_id.__module__)
        image_path = self.main.UPLOAD_DIR / "qa-vision-scorecard.png"
        Image.new("RGB", (320, 480), (235, 238, 240)).save(image_path)
        model_response = {
            "message": {
                "content": (
                    '{"match":{"date":null,"venue":"QA Ground","teams":{"team_1":"TestClub","team_2":"Opposition"},'
                    '"overs_limit":20},"innings":[{"inning_number":1,"batting_team":"TestClub",'
                    '"bowling_team":"Opposition","summary":{"runs":145,"wickets":6,"overs":20,"balls":120},'
                    '"batting":[{"player":{"name":"player1"},"runs":45,"balls":30,"fours":4,"sixes":1,'
                    '"strike_rate":150,"dismissal":{"type":"caught","fielder":"Nick","bowler":"Sam"}}],'
                    '"bowling":[{"player":{"name":"Sam"},"overs":4,"runs_conceded":25,"wickets":2,"economy":6.25}],'
                    '"extras":{"wides":3,"no_balls":0,"byes":1,"leg_byes":0,"penalties":0,"total":4}}]}'
                )
            }
        }
        response = Mock()
        response.json.return_value = model_response
        with (
            patch.object(store_module, "preferred_vision_llm_model", return_value="qwen3-vl:8b"),
            patch.object(store_module, "extract_text_from_image", return_value="TestClub 145/6"),
            patch.object(store_module.httpx, "post", return_value=response) as post,
        ):
            result = store_module.extract_scorecard_with_vision_llm(image_path, [{"name": "player1"}])

        self.assertIsNotNone(result)
        request = post.call_args.kwargs["json"]
        self.assertEqual(request["format"], "json")
        self.assertEqual(request["options"]["num_ctx"], 8192)
        self.assertEqual(len(request["messages"][0]["images"]), 4)
        self.assertIn('"bowling"', request["messages"][0]["content"])
        self.assertIn("focused crops", request["messages"][0]["content"])

    def test_scorecard_vision_populates_full_review_json_and_reextract_replaces_old_json(self) -> None:
        import json
        from PIL import Image

        store_module = importlib.import_module(self.main.extract_archive_by_id.__module__)
        image_path = self.main.UPLOAD_DIR / "qa-reextract-scorecard.png"
        Image.new("RGB", (40, 60), (255, 255, 255)).save(image_path)
        payload = {
            "match": {
                "date": "2024-06-01",
                "venue": "QA Ground",
                "teams": {"team_1": "TestClub", "team_2": "Opposition"},
                "overs_limit": 20,
            },
            "innings": [
                {
                    "inning_number": 1,
                    "batting_team": "TestClub",
                    "bowling_team": "Opposition",
                    "summary": {"runs": 145, "wickets": 6, "overs": 20, "balls": 120},
                    "batting": [
                        {
                            "player": {"name": "player1"},
                            "runs": 45,
                            "balls": 30,
                            "fours": 4,
                            "sixes": 1,
                            "strike_rate": 150,
                            "dismissal": {"type": "caught", "fielder": "Nick", "bowler": "Sam"},
                        }
                    ],
                    "bowling": [
                        {"player": {"name": "Sam"}, "overs": 4, "runs_conceded": 25, "wickets": 2, "economy": 6.25}
                    ],
                    "extras": {"wides": 3, "no_balls": 0, "byes": 1, "leg_byes": 0, "penalties": 0, "total": 4},
                }
            ],
        }
        archive = {
            "id": "qa-reextract",
            "file_name": image_path.name,
            "original_file_name": image_path.name,
            "file_path": str(image_path),
            "status": "Pending review",
            "club_id": "club-testclub",
            "club_name": "TestClub",
            "draft_scorecard": {"result": "Old extraction"},
            "extraction_template": {"meta": {}, "match": {}, "innings": [], "validation": {}},
            "review_template_json": '{"old": true}',
            "review_source_json": '{"old review": true}',
            "suggested_performances": [],
        }
        store = {"members": [{"id": "member-1", "name": "player1", "club_memberships": [{"club_id": "club-testclub"}]}], "archive_uploads": [archive]}
        with patch.object(
            store_module,
            "extract_scorecard_with_vision_llm",
            return_value={"model": "qwen3-vl:8b", "content": json.dumps(payload), "payload": payload, "ocr_hint": ""},
        ):
            extracted = store_module.extract_archive_by_id(store, "qa-reextract")

        template = extracted["extraction_template"]
        self.assertEqual(template["match"]["teams"]["team_1"], "TestClub")
        self.assertEqual(template["innings"][0]["summary"]["runs"], 145)
        self.assertEqual(template["innings"][0]["batting"][0]["player"]["member_id"], "member-1")
        self.assertEqual(template["innings"][0]["batting"][0]["dismissal"]["fielder"], "Nick")
        self.assertEqual(template["innings"][0]["bowling"][0]["wickets"], 2)
        self.assertEqual(template["innings"][0]["extras"]["total"], 4)
        self.assertEqual(json.loads(extracted["review_template_json"]), template)
        self.assertNotIn('"old": true', extracted["review_template_json"])
        self.assertIn("1 innings", extracted["extracted_summary"])

    def _tempdir_path(self) -> Path:
        directory = Path(self._tempdir.name) / "vision-temp"
        directory.mkdir(exist_ok=True)
        return directory

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
        captain_queue_response = self.client.get(
            "/api/admin/review-queue",
            headers=self.auth_headers(captain_auth["token"]),
        )
        self.assertEqual(captain_queue_response.status_code, 403, captain_queue_response.text)
        superadmin_auth = self.signin("14164508695")
        superadmin_response = self.client.get("/admin-center", headers=self.auth_headers(superadmin_auth["token"]))
        self.assertEqual(superadmin_response.status_code, 200, superadmin_response.text)
        self.assertIn("Admin center", superadmin_response.text)
        self.assertIn('data-scorecard-original="', superadmin_response.text)
        self.assertIn("admin-original-scorecard-image", superadmin_response.text)
        queue_response = self.client.get(
            "/api/admin/review-queue",
            headers=self.auth_headers(superadmin_auth["token"]),
        )
        self.assertEqual(queue_response.status_code, 200, queue_response.text)
        queue = queue_response.json()["queue"]
        self.assertTrue(queue, "the fixture archive should be available to the superadmin review queue")
        preview = queue[0]["scorecard_preview"]
        self.assertEqual(preview["id"], f"a-{queue[0]['id']}")
        self.assertEqual(len(preview["innings"]), 2)
        self.assertIn("photo_url", preview)
        public_response = self.client.get(f"/api/public/scorecards/{preview['id']}")
        self.assertEqual(public_response.status_code, 404, public_response.text)


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

    def test_f05a_captain_cannot_create_duplicate_future_fixture(self) -> None:
        auth = self.signin("2222222222")
        token = auth["token"]
        fixture_args = {
            "club_id": "club-testclub",
            "season_year": int(str(datetime.utcnow().year)),
            "date": (datetime.utcnow().date() + timedelta(days=7)).isoformat(),
            "date_label": (datetime.utcnow().date() + timedelta(days=7)).strftime("%d %b %Y"),
            "opponent": "Duplicate Block Test",
            "venue": "QA Ground",
            "match_type": "Friendly",
            "scheduled_time": "09:00",
            "overs": "20",
        }
        response1 = self.client.post("/api/season-setup/fixtures", json=fixture_args, headers=self.auth_headers(token))
        self.assertEqual(response1.status_code, 200, response1.text)
        response2 = self.client.post("/api/season-setup/fixtures", json=fixture_args, headers=self.auth_headers(token))
        self.assertEqual(response2.status_code, 409, response2.text)
        self.assertIn("already exists", response2.text)

    def test_f05b_coca_cola_archive_dashboard_is_club_scoped(self) -> None:
        dashboard = self.main.current_dashboard(self.main.load_store(), "club-coca-cola-xi", "2024")
        archive_uploads = dashboard.get("archive_uploads") or []
        self.assertTrue(archive_uploads, "expected Coca Cola archives to be present")
        self.assertTrue(all(str(item.get("club_id") or "").strip() == "club-coca-cola-xi" for item in archive_uploads))
        self.assertTrue(all("Heartlake Cricket Club" not in str(item.get("club_name") or "") for item in archive_uploads))

    def test_f05c_mobile_style_image_upload_returns_success_message(self) -> None:
        payload = self.signin("14164508695", "Amit S")
        response = self.client.post(
            "/api/scorecards/upload",
            headers={"X-Auth-Token": payload["token"]},
            files={
                "file": (
                    "mobile-scorecard.heic",
                    _tiny_unique_png_bytes(),
                    "image/heic",
                )
            },
            data={
                "season": "2025 Season",
                "focus_club_id": "club-coca-cola-xi",
            },
        )
        self.assertEqual(response.status_code, 200, response.text)
        response_payload = response.json()
        self.assertIn("uploaded successfully", str(response_payload.get("message") or "").lower())
        self.assertEqual(str(response_payload.get("upload", {}).get("original_file_name") or ""), "mobile-scorecard.heic")

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
        store = self.main.load_store()
        stored = next(item for item in store["fixtures"] if item["id"] == fixture_id)
        stored["date"] = datetime.utcnow().date().isoformat()
        stored["status"] = "Live"
        self.main.save_store(store)
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
                "bowlers": ["player2", "player3", "", "", "", "", "", "", "", "", ""],
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
                "bowler": "player2",
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

    def test_f11_captain_can_correct_past_scorecard_summary(self) -> None:
        captain = self.signin("2222222222")
        yesterday = (datetime.utcnow().date() - timedelta(days=1)).isoformat()
        self.create_fixture(
            captain["token"],
            date=yesterday,
            date_label=yesterday,
            season_year=int(yesterday[:4]),
            opponent="Past Scorecard Team",
        )
        fixture = next(item for item in self.main.load_store()["fixtures"] if item["opponent"] == "Past Scorecard Team")
        user_row, _ = self.main._auth_user_from_token(captain["token"])
        store = self.main.load_store()
        stored_fixture = next(item for item in store["fixtures"] if item["id"] == fixture["id"])
        stored_fixture["heartlake_captain"] = user_row["display_name"]
        self.main.save_store(store)
        response = self.client.post(
            f"/api/matches/{fixture['id']}/scorecard",
            json={
                "heartlake_runs": "120",
                "heartlake_wickets": "4",
                "opponent_runs": "98",
                "opponent_wickets": "8",
                "result": "Club won",
                "status": fixture["status"],
            },
            headers=self.auth_headers(captain["token"]),
        )
        self.assertEqual(response.status_code, 200, response.text)
        updated = next(item for item in self.main.load_store()["fixtures"] if item["id"] == fixture["id"])
        self.assertEqual(updated["scorecard"]["heartlake_runs"], "120")
        self.assertEqual(updated["scorecard"]["result"], "Club won")

    def test_f12_players_cannot_edit_past_scorecard_summary(self) -> None:
        captain = self.signin("2222222222")
        yesterday = (datetime.utcnow().date() - timedelta(days=1)).isoformat()
        self.create_fixture(
            captain["token"],
            date=yesterday,
            date_label=yesterday,
            season_year=int(yesterday[:4]),
            opponent="Past Scorecard Permission Team",
        )
        fixture = next(item for item in self.main.load_store()["fixtures"] if item["opponent"] == "Past Scorecard Permission Team")
        player = self.signin("1111111111")
        response = self.client.post(
            f"/api/matches/{fixture['id']}/scorecard",
            json={"heartlake_runs": "120"},
            headers=self.auth_headers(player["token"]),
        )
        self.assertEqual(response.status_code, 403, response.text)

    def test_f13_assigned_game_captain_can_correct_past_scorecard_summary(self) -> None:
        organizer = self.signin("2222222222")
        yesterday = (datetime.utcnow().date() - timedelta(days=1)).isoformat()
        self.create_fixture(
            organizer["token"],
            date=yesterday,
            date_label=yesterday,
            season_year=int(yesterday[:4]),
            opponent="Assigned Captain Scorecard Team",
        )
        store = self.main.load_store()
        fixture = next(item for item in store["fixtures"] if item["opponent"] == "Assigned Captain Scorecard Team")
        captain = self.signin("1111111111")
        user_row, _ = self.main._auth_user_from_token(captain["token"])
        fixture["heartlake_captain"] = user_row["display_name"]
        self.main.save_store(store)
        response = self.client.post(
            f"/api/matches/{fixture['id']}/scorecard",
            json={"heartlake_runs": "120"},
            headers=self.auth_headers(captain["token"]),
        )
        self.assertEqual(response.status_code, 200, response.text)

    def test_f14_only_incomplete_fixtures_can_be_deleted_by_captains(self) -> None:
        captain = self.signin("2222222222")
        self.create_fixture(captain["token"], opponent="Incomplete Delete Team")
        store = self.main.load_store()
        fixture = next(item for item in store["fixtures"] if item["opponent"] == "Incomplete Delete Team")
        user_row, _ = self.main._auth_user_from_token(captain["token"])
        fixture["heartlake_captain"] = user_row["display_name"]
        self.main.save_store(store)
        deleted = self.client.delete(
            f"/api/admin/clubs/{fixture['club_id']}/fixtures/{fixture['id']}",
            headers=self.auth_headers(captain["token"]),
        )
        self.assertEqual(deleted.status_code, 200, deleted.text)
        self.assertNotIn(fixture["id"], {item["id"] for item in self.main.load_store()["fixtures"]})

        self.create_fixture(captain["token"], opponent="Completed Keep Team")
        store = self.main.load_store()
        completed = next(item for item in store["fixtures"] if item["opponent"] == "Completed Keep Team")
        stored_fixture = next(item for item in store["fixtures"] if item["id"] == completed["id"])
        stored_fixture["status"] = "Completed"
        stored_fixture["heartlake_captain"] = user_row["display_name"]
        self.main.save_store(store)
        rejected = self.client.delete(
            f"/api/admin/clubs/{completed['club_id']}/fixtures/{completed['id']}",
            headers=self.auth_headers(captain["token"]),
        )
        self.assertEqual(rejected.status_code, 409, rejected.text)
        self.assertIn(completed["id"], {item["id"] for item in self.main.load_store()["fixtures"]})

        self.create_fixture(captain["token"], opponent="Completed Innings Keep Team")
        store = self.main.load_store()
        completed_innings_fixture = next(item for item in store["fixtures"] if item["opponent"] == "Completed Innings Keep Team")
        completed_innings_fixture["scorebook"] = {
            "innings": [{"status": "Completed"}, {"status": "Finished"}],
        }
        completed_innings_fixture["heartlake_captain"] = user_row["display_name"]
        self.main.save_store(store)
        rejected_completed_innings = self.client.delete(
            f"/api/admin/clubs/{completed_innings_fixture['club_id']}/fixtures/{completed_innings_fixture['id']}",
            headers=self.auth_headers(captain["token"]),
        )
        self.assertEqual(rejected_completed_innings.status_code, 409, rejected_completed_innings.text)
        self.assertIn(completed_innings_fixture["id"], {item["id"] for item in self.main.load_store()["fixtures"]})

        self.create_fixture(captain["token"], opponent="Assigned Captain Delete Team")
        store = self.main.load_store()
        assigned_captain_fixture = next(item for item in store["fixtures"] if item["opponent"] == "Assigned Captain Delete Team")
        assigned_captain_auth = self.signin("1111111111")
        assigned_captain_user, _ = self.main._auth_user_from_token(assigned_captain_auth["token"])
        assigned_captain_fixture["heartlake_captain"] = assigned_captain_user["display_name"]
        self.main.save_store(store)
        deleted_by_assigned_captain = self.client.delete(
            f"/api/admin/clubs/{assigned_captain_fixture['club_id']}/fixtures/{assigned_captain_fixture['id']}",
            headers=self.auth_headers(assigned_captain_auth["token"]),
        )
        self.assertEqual(deleted_by_assigned_captain.status_code, 200, deleted_by_assigned_captain.text)
        self.assertNotIn(
            assigned_captain_fixture["id"],
            {item["id"] for item in self.main.load_store()["fixtures"]},
        )

    def test_live_scorecard_offers_delete_for_started_incomplete_match_only(self) -> None:
        captain = self.signin("2222222222")
        self.create_fixture(captain["token"], opponent="Started Incomplete Delete Team")
        store = self.main.load_store()
        fixture = next(item for item in store["fixtures"] if item["opponent"] == "Started Incomplete Delete Team")
        fixture["status"] = "Live"
        fixture["scorebook"]["innings"][0]["balls"] = [
            {
                "striker": "player1",
                "bowler": "player2",
                "runs_bat": 1,
                "extras_type": "none",
            }
        ]
        self.main.save_store(store)

        authorized = self.client.get(
            f"/api/public/match/{fixture['id']}",
            headers=self.auth_headers(captain["token"]),
        )
        self.assertEqual(authorized.status_code, 200, authorized.text)
        self.assertTrue(authorized.json()["match"]["can_delete_incomplete"])
        quick_score = self.client.get(
            f"/api/quick-score/{fixture['id']}",
            headers=self.auth_headers(captain["token"]),
        )
        self.assertTrue(quick_score.json()["can_delete_incomplete"])
        self.client.cookies.clear()
        public = self.client.get(f"/api/public/match/{fixture['id']}")
        self.assertFalse(public.json()["match"]["can_delete_incomplete"])

        deleted = self.client.delete(
            f"/api/admin/clubs/{fixture['club_id']}/fixtures/{fixture['id']}",
            headers=self.auth_headers(captain["token"]),
        )
        self.assertEqual(deleted.status_code, 200, deleted.text)
        self.assertNotIn(fixture["id"], {item["id"] for item in self.main.load_store()["fixtures"]})

        self.create_fixture(captain["token"], opponent="Completed Live Delete Protection Team")
        store = self.main.load_store()
        completed = next(item for item in store["fixtures"] if item["opponent"] == "Completed Live Delete Protection Team")
        completed["status"] = "Completed"
        self.main.save_store(store)
        completed_payload = self.client.get(
            f"/api/public/match/{completed['id']}",
            headers=self.auth_headers(captain["token"]),
        )
        self.assertFalse(completed_payload.json()["match"]["can_delete_incomplete"])

    def test_f27_past_fixture_with_recorded_scores_appears_in_recent_results(self) -> None:
        captain = self.signin("2222222222")
        yesterday = (datetime.utcnow().date() - timedelta(days=1)).isoformat()
        self.create_fixture(
            captain["token"],
            date=yesterday,
            date_label=yesterday,
            season_year=int(yesterday[:4]),
            opponent="Past Scored Recent Team",
        )
        store = self.main.load_store()
        fixture = next(item for item in store["fixtures"] if item["opponent"] == "Past Scored Recent Team")
        fixture["heartlake_score"] = "106/3"
        fixture["opponent_score"] = "205/7"
        fixture["scorecard"] = {
            "heartlake_runs": "106",
            "heartlake_wickets": "3",
            "opponent_runs": "205",
            "opponent_wickets": "7",
            "result": "TBD",
        }
        fixture["scorebook"]["innings"][0]["balls"] = [{"runs_bat": 1, "extras_type": "none"}]
        self.main.save_store(store)

        fixtures_response = self.client.get("/api/public/fixtures-page")
        self.assertEqual(fixtures_response.status_code, 200, fixtures_response.text)
        fixture_card = next(
            item for item in fixtures_response.json()["fixtures"] if item["id"] == fixture["id"]
        )
        self.assertTrue(fixture_card["is_past"])
        self.assertTrue(fixture_card["heartlake_score"])

        recent_response = self.client.get("/api/public/live-page")
        self.assertEqual(recent_response.status_code, 200, recent_response.text)
        recent_ids = {item["id"] for item in recent_response.json()["recent_results"]}
        self.assertIn(fixture["id"], recent_ids)

    def test_retired_out_is_temporary_without_wicket_delivery_or_bowler_credit(self) -> None:
        captain = self.signin("2222222222")
        created = self.create_fixture(captain["token"], opponent="Retired Out Scoring Team")
        fixture = next(item for item in created["fixtures"] if item["opponent"] == "Retired Out Scoring Team")
        fixture_id = fixture["id"]
        store = self.main.load_store()
        stored = next(item for item in store["fixtures"] if item["id"] == fixture_id)
        stored["date"] = datetime.utcnow().date().isoformat()
        stored["status"] = "Live"
        self.main.save_store(store)
        scorer = self.signin("14164508695")

        setup = self.client.post(
            f"/api/matches/{fixture_id}/scorebook/setup",
            json={
                "innings_number": 1,
                "batting_team": "TestClub",
                "bowling_team": "Retired Out Scoring Team",
                "overs_limit": 20,
                "target_runs": None,
                "status": "Live",
                "batters": ["Club Player 1", "Club Player 2", "Club Player 3"],
                "bowlers": ["Opponent Player 1", "Opponent Player 2"],
            },
            headers=self.auth_headers(scorer["token"]),
        )
        self.assertEqual(setup.status_code, 200, setup.text)

        first_delivery = self.client.post(
            f"/api/matches/{fixture_id}/scorebook/ball",
            json={
                "innings_number": 1,
                "over_number": 1,
                "ball_number": 1,
                "striker": "Club Player 1",
                "non_striker": "Club Player 2",
                "bowler": "Opponent Player 1",
                "runs_bat": 1,
            },
            headers=self.auth_headers(scorer["token"]),
        )
        self.assertEqual(first_delivery.status_code, 200, first_delivery.text)

        retired = self.client.post(
            f"/api/matches/{fixture_id}/scorebook/ball",
            json={
                "innings_number": 1,
                "over_number": 1,
                "ball_number": 2,
                "striker": "Club Player 2",
                "non_striker": "Club Player 1",
                "bowler": "",
                "extras_type": "none",
                "wicket": True,
                "wicket_type": "retired_out",
                "wicket_player": "Club Player 1",
                "new_batter": "Club Player 3",
            },
            headers=self.auth_headers(scorer["token"]),
        )
        self.assertEqual(retired.status_code, 200, retired.text)

        store = self.main.load_store()
        stored = next(item for item in store["fixtures"] if item["id"] == fixture_id)
        innings = stored["scorebook"]["innings"][0]
        summary = self.main.summarize_innings_scorebook(innings)
        retired_ball = innings["balls"][-1]
        self.assertEqual((summary["runs"], summary["wickets"], summary["legal_balls"]), (1, 0, 1))
        before_summary = self.main.summarize_innings_scorebook({**innings, "balls": innings["balls"][:-1]})
        alerts = self.main.muse.live_score_events(stored, innings, before_summary, summary, retired_ball)
        retired_alert = next(event for event in alerts if event[0] == "live_retired_out")
        self.assertIn("Retired out: Club Player 1", retired_alert[1])
        self.assertNotIn("Wicket!", retired_alert[1])
        self.assertNotIn("Opponent Player 1", retired_alert[1])
        self.assertEqual(
            (retired_ball["runs_bat"], retired_ball["extras_runs"], retired_ball["extras_type"], retired_ball["bowler"]),
            (0, 0, "retired_out", ""),
        )
        self.assertFalse(retired_ball["wicket"])
        batters = {row["player_name"]: row for row in summary["batting"]}
        self.assertEqual((batters["Club Player 1"]["balls"], batters["Club Player 1"]["status"]), (1, "retired_out"))
        self.assertEqual(batters["Club Player 2"]["balls"], 0)
        bowler = next(row for row in summary["bowling"] if row["player_name"] == "Opponent Player 1")
        self.assertEqual((bowler["legal_balls"], bowler["runs_conceded"], bowler["wickets"]), (1, 1, 0))
        legacy_innings = {
            **innings,
            "balls": [{**ball} for ball in innings["balls"]],
        }
        legacy_innings["balls"][-1]["bowler"] = "Opponent Player 1"
        legacy_bowler = next(
            row
            for row in self.main.summarize_innings_scorebook(legacy_innings)["bowling"]
            if row["player_name"] == "Opponent Player 1"
        )
        self.assertEqual(
            (legacy_bowler["legal_balls"], legacy_bowler["runs_conceded"], legacy_bowler["wickets"]),
            (1, 1, 0),
        )
        live_state = importlib.import_module("app.cricket_store").build_scorebook_live_state(innings)
        self.assertEqual(live_state["current_striker"], "Club Player 2")
        self.assertEqual(live_state["current_non_striker"], "Club Player 3")
        self.assertEqual(live_state["this_over_balls"][-1], "RO")
        self.assertIn("Club Player 3", self.main._match_lineups(fixture_id)["club"])

        second_retired = self.client.post(
            f"/api/matches/{fixture_id}/scorebook/ball",
            json={
                "innings_number": 1,
                "over_number": 1,
                "ball_number": 2,
                "striker": "Club Player 2",
                "non_striker": "Club Player 3",
                "bowler": "",
                "extras_type": "retired_out",
                "wicket": True,
                "wicket_type": "retired_out",
                "wicket_player": "Club Player 2",
                "new_batter": "Club Player 1",
            },
            headers=self.auth_headers(scorer["token"]),
        )
        self.assertEqual(second_retired.status_code, 200, second_retired.text)

        third_retired = self.client.post(
            f"/api/matches/{fixture_id}/scorebook/ball",
            json={
                "innings_number": 1,
                "over_number": 1,
                "ball_number": 2,
                "striker": "Club Player 1",
                "non_striker": "Club Player 3",
                "bowler": "",
                "extras_type": "retired_out",
                "wicket": True,
                "wicket_type": "retired_out",
                "wicket_player": "Club Player 3",
                "new_batter": "Club Player 2",
            },
            headers=self.auth_headers(scorer["token"]),
        )
        self.assertEqual(third_retired.status_code, 200, third_retired.text)
        store = self.main.load_store()
        stored = next(item for item in store["fixtures"] if item["id"] == fixture_id)
        innings = stored["scorebook"]["innings"][0]
        self.assertEqual(self.main.scorebook_wickets_for_all_out(innings), 0)
        self.assertFalse(self.main._innings_is_over(stored, innings, self.main._match_lineups(fixture_id)))

        returned = self.client.post(
            f"/api/matches/{fixture_id}/scorebook/ball",
            json={
                "innings_number": 1,
                "over_number": 1,
                "ball_number": 2,
                "striker": "Club Player 1",
                "non_striker": "Club Player 2",
                "bowler": "Opponent Player 1",
                "runs_bat": 4,
            },
            headers=self.auth_headers(scorer["token"]),
        )
        self.assertEqual(returned.status_code, 200, returned.text)
        store = self.main.load_store()
        stored = next(item for item in store["fixtures"] if item["id"] == fixture_id)
        summary = self.main.summarize_innings_scorebook(stored["scorebook"]["innings"][0])
        returned_batter = next(row for row in summary["batting"] if row["player_name"] == "Club Player 1")
        second_returned_batter = next(row for row in summary["batting"] if row["player_name"] == "Club Player 2")
        still_retired_batter = next(row for row in summary["batting"] if row["player_name"] == "Club Player 3")
        self.assertEqual((returned_batter["runs"], returned_batter["balls"], returned_batter["status"]), (5, 2, "batting"))
        self.assertEqual(second_returned_batter["status"], "batting")
        self.assertEqual(still_retired_batter["status"], "retired_out")
        self.assertEqual((summary["runs"], summary["wickets"]), (5, 0))

        for invalid_new_batter in (
            {"wicket": False, "wicket_player": "", "new_batter": "Club Player 1"},
            {"wicket": True, "wicket_player": "Club Player 1", "new_batter": "Club Player 1"},
        ):
            with self.assertRaises(self.main.HTTPException):
                self.main._validate_retired_out_ball(invalid_new_batter)

        invalid = self.client.post(
            f"/api/matches/{fixture_id}/scorebook/ball",
            json={
                "innings_number": 1,
                "over_number": 1,
                "ball_number": 2,
                "striker": "Club Player 2",
                "non_striker": "Club Player 3",
                "bowler": "Opponent Player 1",
                "runs_bat": 1,
                "wicket": True,
                "wicket_type": "retired_out",
                "wicket_player": "Club Player 2",
            },
            headers=self.auth_headers(scorer["token"]),
        )
        self.assertEqual(invalid.status_code, 400, invalid.text)

    def test_f28_authorized_edit_mode_corrects_and_deletes_past_deliveries(self) -> None:
        captain = self.signin("2222222222")
        created = self.create_fixture(captain["token"], opponent="Past Ball Edit Team")
        fixture = next(item for item in created["fixtures"] if item["opponent"] == "Past Ball Edit Team")
        fixture_id = fixture["id"]
        store = self.main.load_store()
        stored = next(item for item in store["fixtures"] if item["id"] == fixture_id)
        stored["date"] = datetime.utcnow().date().isoformat()
        stored["status"] = "Live"
        self.main.save_store(store)

        scorer = self.signin("14164508695")
        setup_response = self.client.post(
            f"/api/matches/{fixture_id}/scorebook/setup",
            json={
                "innings_number": 1,
                "batting_team": "TestClub",
                "bowling_team": "Past Ball Edit Team",
                "overs_limit": 20,
                "target_runs": None,
                "status": "Live",
                "batters": ["Club Player 1", "Club Player 2"],
                "bowlers": ["Opponent Player 1", "Opponent Player 2"],
            },
            headers=self.auth_headers(scorer["token"]),
        )
        self.assertEqual(setup_response.status_code, 200, setup_response.text)
        for ball_number, runs in ((1, 1), (2, 2)):
            response = self.client.post(
                f"/api/matches/{fixture_id}/scorebook/ball",
                json={
                    "innings_number": 1,
                    "over_number": 1,
                    "ball_number": ball_number,
                    "striker": "Club Player 1",
                    "non_striker": "Club Player 2",
                    "bowler": "Opponent Player 1",
                    "runs_bat": runs,
                },
                headers=self.auth_headers(scorer["token"]),
            )
            self.assertEqual(response.status_code, 200, response.text)
        store = self.main.load_store()
        stored = next(item for item in store["fixtures"] if item["id"] == fixture_id)
        first_ball, second_ball = stored["scorebook"]["innings"][0]["balls"]
        second_ball_id = second_ball["id"]
        stored["date"] = (datetime.utcnow().date() - timedelta(days=1)).isoformat()
        stored["status"] = "Completed"
        self.main.save_store(store)

        normal_write = self.client.post(
            f"/api/matches/{fixture_id}/scorebook/ball",
            json={
                "id": first_ball["id"],
                "innings_number": 1,
                "over_number": 1,
                "ball_number": 1,
                "striker": "Club Player 1",
                "non_striker": "Club Player 2",
                "bowler": "Opponent Player 1",
                "runs_bat": 4,
            },
            headers=self.auth_headers(scorer["token"]),
        )
        self.assertEqual(normal_write.status_code, 400, normal_write.text)

        state = self.client.get(
            f"/api/quick-score/{fixture_id}",
            headers=self.auth_headers(scorer["token"]),
        )
        self.assertEqual(state.status_code, 200, state.text)
        self.assertTrue(state.json()["can_edit_scorebook"])

        correction = self.client.post(
            f"/api/matches/{fixture_id}/scorebook/ball?edit_mode=true",
            json={
                "id": first_ball["id"],
                "innings_number": 1,
                "over_number": 1,
                "ball_number": 1,
                "striker": "Club Player 1",
                "non_striker": "Club Player 2",
                "bowler": "Opponent Player 1",
                "runs_bat": 4,
            },
            headers=self.auth_headers(scorer["token"]),
        )
        self.assertEqual(correction.status_code, 200, correction.text)
        store = self.main.load_store()
        stored = next(item for item in store["fixtures"] if item["id"] == fixture_id)
        self.assertEqual(len(stored["scorebook"]["innings"][0]["balls"]), 2)
        self.assertEqual(stored["scorebook"]["innings"][0]["balls"][0]["runs_bat"], 4)

        with (
            patch.object(self.main.muse, "live_score_events") as live_events,
            patch.object(self.main, "_notify") as notify,
        ):
            appended = self.client.post(
                f"/api/matches/{fixture_id}/scorebook/ball?edit_mode=true",
                json={
                    "innings_number": 1,
                    "over_number": 1,
                    "ball_number": 3,
                    "striker": "Club Player 1",
                    "non_striker": "Club Player 2",
                    "bowler": "Opponent Player 1",
                    "runs_bat": 4,
                },
                headers=self.auth_headers(scorer["token"]),
            )
        self.assertEqual(appended.status_code, 200, appended.text)
        live_events.assert_not_called()
        notify.assert_not_called()
        store = self.main.load_store()
        stored = next(item for item in store["fixtures"] if item["id"] == fixture_id)
        appended_balls = stored["scorebook"]["innings"][0]["balls"]
        self.assertEqual(len(appended_balls), 3)
        self.assertEqual(self.main.summarize_innings_scorebook(stored["scorebook"]["innings"][0])["runs"], 10)
        self.assertEqual(stored["scorebook"]["innings"][0]["status"], "Live")
        appended_ball_id = appended_balls[-1]["id"]

        wide_run_out = self.client.post(
            f"/api/matches/{fixture_id}/scorebook/ball?edit_mode=true",
            json={
                "innings_number": 1,
                "over_number": 1,
                "ball_number": 4,
                "striker": "Club Player 1",
                "non_striker": "Club Player 2",
                "bowler": "Opponent Player 1",
                "extras_type": "wide",
                "extras_runs": 3,
                "wicket": True,
                "wicket_type": "run_out",
                "wicket_player": "Club Player 1",
                "fielder": "Opponent Player 2",
            },
            headers=self.auth_headers(scorer["token"]),
        )
        self.assertEqual(wide_run_out.status_code, 200, wide_run_out.text)
        store = self.main.load_store()
        stored = next(item for item in store["fixtures"] if item["id"] == fixture_id)
        first_innings = stored["scorebook"]["innings"][0]
        self.assertEqual(self.main.summarize_innings_scorebook(first_innings)["runs"], 13)
        self.assertEqual(self.main.summarize_innings_scorebook(first_innings)["wickets"], 1)
        self.assertEqual(first_innings["status"], "Completed")
        wide_run_out_id = first_innings["balls"][-1]["id"]

        second_setup = self.client.post(
            f"/api/matches/{fixture_id}/scorebook/setup?edit_mode=true",
            json={
                "innings_number": 2,
                "batting_team": "Past Ball Edit Team",
                "bowling_team": "TestClub",
                "overs_limit": 20,
                "target_runs": 13,
                "status": "Live",
                "batters": ["Opponent Player 1", "Opponent Player 2"],
                "bowlers": ["Club Player 1", "Club Player 2"],
            },
            headers=self.auth_headers(scorer["token"]),
        )
        self.assertEqual(second_setup.status_code, 200, second_setup.text)
        second_innings_ball = self.client.post(
            f"/api/matches/{fixture_id}/scorebook/ball?edit_mode=true",
            json={
                "innings_number": 2,
                "over_number": 1,
                "ball_number": 1,
                "striker": "Opponent Player 1",
                "non_striker": "Opponent Player 2",
                "bowler": "Club Player 1",
                "runs_bat": 1,
            },
            headers=self.auth_headers(scorer["token"]),
        )
        self.assertEqual(second_innings_ball.status_code, 200, second_innings_ball.text)
        updated_fixture = next(item for item in self.main.load_store()["fixtures"] if item["id"] == fixture_id)
        self.assertEqual(updated_fixture["result"], "TBD")

        no_ball_run_out = self.client.post(
            f"/api/matches/{fixture_id}/scorebook/ball?edit_mode=true",
            json={
                "innings_number": 2,
                "over_number": 1,
                "ball_number": 2,
                "striker": "Opponent Player 1",
                "non_striker": "Opponent Player 2",
                "bowler": "Club Player 1",
                "runs_bat": 2,
                "extras_type": "no_ball",
                "extras_runs": 1,
                "wicket": True,
                "wicket_type": "run_out",
                "wicket_player": "Opponent Player 1",
                "fielder": "Club Player 2",
            },
            headers=self.auth_headers(scorer["token"]),
        )
        self.assertEqual(no_ball_run_out.status_code, 200, no_ball_run_out.text)
        updated_fixture = next(item for item in self.main.load_store()["fixtures"] if item["id"] == fixture_id)
        self.assertNotEqual(updated_fixture["result"], "TBD")

        store = self.main.load_store()
        stored = next(item for item in store["fixtures"] if item["id"] == fixture_id)
        stored["heartlake_captain"] = "Unassigned test captain"
        stored["heartlake_captain_member_id"] = ""
        self.main.save_store(store)
        player = self.signin("1111111111")
        with self.main._auth_connection() as connection:
            player_row = connection.execute(
                "SELECT id FROM app_users WHERE mobile = ?",
                ("1111111111",),
            ).fetchone()
            self.assertIsNotNone(player_row)
            connection.execute("UPDATE app_users SET role = 'player' WHERE id = ?", (player_row["id"],))
            connection.execute("DELETE FROM app_user_club_roles WHERE user_id = ?", (player_row["id"],))
        denied = self.client.post(
            f"/api/matches/{fixture_id}/scorebook/ball?edit_mode=true",
            json={
                "innings_number": 2,
                "over_number": 1,
                "ball_number": 3,
                "striker": "Opponent Player 1",
                "non_striker": "Opponent Player 2",
                "bowler": "Club Player 1",
                "runs_bat": 6,
            },
            headers=self.auth_headers(player["token"]),
        )
        self.assertEqual(denied.status_code, 403, denied.text)

        removed = self.client.delete(
            f"/api/matches/{fixture_id}/scorebook/ball?edit_mode=true&innings_number=1&ball_id={first_ball['id']}",
            headers=self.auth_headers(scorer["token"]),
        )
        self.assertEqual(removed.status_code, 200, removed.text)
        updated = next(item for item in self.main.load_store()["fixtures"] if item["id"] == fixture_id)
        remaining = updated["scorebook"]["innings"][0]["balls"]
        self.assertEqual(
            [ball["id"] for ball in remaining],
            [second_ball_id, appended_ball_id, wide_run_out_id],
        )

    def test_f15_signout_invalidates_session(self) -> None:
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
        self.assertIn("2024", answer)
        self.assertIn("2025", answer)
        self.assertIn("55", answer)
        self.assertIn("113", answer)
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
        self.assertIn("Coca Cola XI", answer)
        self.assertIn("2024", answer)
        self.assertIn("2025", answer)
        self.assertIn("2026", answer)
        self.assertNotIn("amit sethi", answer.lower())
        self.assertNotIn("amit gaba", answer.lower())
        self.assertNotIn("heartlake", answer.lower())

    def test_f18_captain_questions_recommend_provisional_candidate_for_club(self) -> None:
        brain = importlib.import_module("app.cricket_brain")
        store = self.main.load_store()
        answer = brain.answer_question("who should be the captain of Coca Cola team in 2026", store, history=[], session_id="captain-qa")
        self.assertEqual(answer.get("mode"), "heuristic")
        self.assertIn("provisional captain recommendation", answer.get("answer", "").lower())
        self.assertIn("coca cola", answer.get("answer", "").lower())
        self.assertNotIn("unassigned", answer.get("answer", "").lower())

    def test_f19_total_score_for_2025_across_all_clubs_is_year_scoped(self) -> None:
        brain = importlib.import_module("app.cricket_brain")
        store = self.main.load_store()
        answer = brain.answer_question("what was Amit Sethi total score for 2025 across all clubs", store, history=[], session_id="total-score-qa")
        self.assertEqual(answer.get("mode"), "heuristic")
        self.assertIn("113 runs", answer.get("answer", ""))
        self.assertIn("4 confirmed match(es)", answer.get("answer", ""))
        self.assertNotIn("168 runs", answer.get("answer", ""))

    def test_f20_history_pronoun_resolves_previous_player_for_2024_followup(self) -> None:
        brain = importlib.import_module("app.cricket_brain")
        store = self.main.load_store()
        answer = brain.answer_question(
            "how was his score in 2024?",
            store,
            history=[{"role": "user", "text": "how is Amit Sethi's performance going to be in 2026 season"}],
            session_id="score-followup-qa",
        )
        self.assertEqual(answer.get("mode"), "heuristic")
        self.assertIn("Amit Sethi", answer.get("answer", ""))
        self.assertIn("55 runs", answer.get("answer", ""))
        self.assertIn("2 confirmed match(es)", answer.get("answer", ""))

    def test_f21_club_question_ignores_prior_player_history(self) -> None:
        brain = importlib.import_module("app.cricket_brain")
        store = self.main.load_store()
        answer = brain.answer_question(
            "how is Heartlake's performance looking in 2026",
            store,
            history=[{"role": "user", "text": "how is Amit Sethi's performance going to be in 2026 season"}],
            session_id="club-forecast-qa",
        )
        self.assertEqual(answer.get("mode"), "forecast")
        self.assertIn("Heartlake Cricket Club", answer.get("answer", ""))
        self.assertNotIn("Amit Sethi", answer.get("answer", ""))
        self.assertNotIn("Amit Gaba", answer.get("answer", ""))

    def test_f22_save_store_refreshes_llm_document_index(self) -> None:
        store = self.main.load_store()
        self.main.save_store(store)
        refreshed = self.main.load_store()
        llm_documents = refreshed.get("llm_documents", [])
        self.assertTrue(llm_documents, "saving the store should rebuild the indexed LLM document corpus")
        self.assertTrue(any(doc.get("doc_type") == "prompt" for doc in llm_documents))

    def test_f23_database_export_and_import_round_trip(self) -> None:
        superadmin_auth = self.signin("14164508695")
        headers = self.auth_headers(superadmin_auth["token"])
        export_response = self.client.get("/api/admin/db/export", headers=headers)
        self.assertEqual(export_response.status_code, 200, export_response.text)
        self.assertGreater(len(export_response.content), 0)

        import_response = self.client.post(
            "/api/admin/db/import",
            files={"database": ("cricketclubapp.db", export_response.content, "application/x-sqlite3")},
            headers=headers,
        )
        self.assertEqual(import_response.status_code, 200, import_response.text)
        payload = import_response.json()
        self.assertTrue(payload.get("ok"))
        self.assertGreater(payload.get("members", 0), 0)
        self.assertGreater(payload.get("fixtures", 0), 0)

        refreshed = self.main.load_store()
        self.assertGreater(len(refreshed.get("members", [])), 0)
        self.assertGreater(len(refreshed.get("fixtures", [])), 0)

    def test_f24_llm_registry_and_status_endpoints(self) -> None:
        status = self.client.get("/api/llm/status")
        prompts = self.client.get("/api/llm/prompts")
        documents = self.client.get("/api/llm/documents", params={"limit": 5})
        self.assertEqual(status.status_code, 200, status.text)
        self.assertEqual(prompts.status_code, 200, prompts.text)
        self.assertEqual(documents.status_code, 200, documents.text)
        self.assertGreaterEqual(status.json().get("prompt_count", 0), 1)
        self.assertIn("SYSTEM_PROMPT", [item.get("name") for item in prompts.json().get("prompts", [])])

    def test_f25_llm_infer_endpoint_uses_registry_prompt(self) -> None:
        llm_service = importlib.import_module("app.llm_service")

        class _FakeResponse:
            def raise_for_status(self) -> None:
                return None

            def json(self) -> dict[str, dict[str, str]]:
                return {
                    "message": {
                        "content": "Forecast: the club outlook is stable and grounded in the stored records."
                    }
                }

        with (
            patch.object(
                llm_service,
                "get_llm_status",
                return_value={
                    "available": True,
                    "provider": "ollama",
                    "model": "llama3.2:latest",
                    "base_url": "http://127.0.0.1:11434",
                    "embedding_model": "nomic-embed-text",
                    "embeddings_available": True,
                },
            ),
            patch.object(llm_service.httpx, "post", return_value=_FakeResponse()),
        ):
            response = self.client.post(
                "/api/llm/infer",
                json={
                    "question": "Predict the club performance outlook for 2026",
                    "prompt_name": "CLUB_PERFORMANCE",
                    "focus_club_id": "club-heartlake",
                    "mode": "forecast",
                    "template_args": {"club_data": "club: Heartlake Cricket Club"},
                },
            )

        self.assertEqual(response.status_code, 200, response.text)
        payload = response.json()
        self.assertIn("result", payload)
        self.assertEqual(payload["result"].get("source_provider"), "ollama")
        self.assertEqual(payload["result"].get("prompt_name"), "CLUB_PERFORMANCE")
        self.assertIn("club outlook", payload["result"].get("answer", "").lower())

    def test_f26_llm_cache_clear_endpoint_resets_cached_answers(self) -> None:
        response = self.client.post("/api/llm/cache/clear", headers=self.auth_headers(self.signin("1111111111")["token"]))
        self.assertEqual(response.status_code, 200, response.text)
        payload = response.json()
        self.assertIn("cleared", payload.get("message", "").lower())
        self.assertIn("updated_at", payload)


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
