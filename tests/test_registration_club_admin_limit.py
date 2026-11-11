from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
import sqlite3
import tempfile
import threading
import unittest
from pathlib import Path

from fastapi import HTTPException

from app.main import _check_club_admin_capacity
from tests.test_local_qa import LocalQATestCase


class ClubAdminCapacityTests(unittest.TestCase):
    def setUp(self) -> None:
        self.connection = sqlite3.connect(":memory:")
        self.connection.row_factory = sqlite3.Row
        self.connection.executescript(
            """
            CREATE TABLE app_users (id INTEGER PRIMARY KEY, primary_club_id TEXT, role TEXT);
            CREATE TABLE app_user_club_roles (user_id INTEGER, club_id TEXT, role_name TEXT);
            """
        )

    def tearDown(self) -> None:
        self.connection.close()

    def test_counts_distinct_base_and_club_roles_per_club(self) -> None:
        self.connection.executemany(
            "INSERT INTO app_users VALUES (?, ?, ?)",
            [(1, "a", "club_admin"), (2, "b", "player"), (3, "a", "superadmin")],
        )
        self.connection.executemany(
            "INSERT INTO app_user_club_roles VALUES (?, ?, ?)",
            [(1, "a", "club_admin"), (2, "a", "club_admin"), (2, "b", "captain")],
        )
        with self.assertRaises(HTTPException) as error:
            _check_club_admin_capacity(self.connection, "a")
        self.assertEqual(error.exception.status_code, 409)
        _check_club_admin_capacity(self.connection, "a", user_id=1)
        _check_club_admin_capacity(self.connection, "b")

    def test_concurrent_admin_claims_cannot_take_the_last_slot_twice(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "capacity.db"
            with closing(sqlite3.connect(path)) as connection, connection:
                connection.executescript(
                    """
                    CREATE TABLE app_users (id INTEGER PRIMARY KEY, primary_club_id TEXT, role TEXT);
                    CREATE TABLE app_user_club_roles (user_id INTEGER, club_id TEXT, role_name TEXT);
                    INSERT INTO app_users VALUES (1, 'a', 'club_admin');
                    """
                )
            ready = threading.Barrier(2)

            def claim(user_id: int) -> str:
                with closing(sqlite3.connect(path, timeout=10)) as connection, connection:
                    connection.row_factory = sqlite3.Row
                    ready.wait(timeout=10)
                    connection.execute("BEGIN IMMEDIATE")
                    try:
                        _check_club_admin_capacity(connection, "a")
                    except HTTPException as error:
                        self.assertEqual(error.status_code, 409)
                        return "full"
                    connection.execute("INSERT INTO app_users VALUES (?, 'a', 'club_admin')", (user_id,))
                    return "registered"

            with ThreadPoolExecutor(max_workers=2) as pool:
                results = list(pool.map(claim, (2, 3)))
            self.assertCountEqual(results, ["registered", "full"])
            with closing(sqlite3.connect(path)) as connection:
                self.assertEqual(connection.execute("SELECT COUNT(*) FROM app_users").fetchone()[0], 2)


class RegistrationClubAdminLimitTests(LocalQATestCase):
    def test_registration_enforces_two_per_club_and_keeps_other_roles_available(self) -> None:
        def register(number: int, role: str, **extra: object):
            payload = {
                "display_name": f"Limit QA Player {number}",
                "email": f"limit-qa-{number}@example.invalid",
                "password": "pass1234",
                "role": role,
                **extra,
            }
            return self.client.post("/api/auth/register", json=payload)

        first = register(1, "player", club_name="Limit QA Club", club_city="Toronto", club_country="Canada")
        self.assertEqual(first.status_code, 200, first.text)
        self.assertEqual(first.json()["user"]["role"], "club_admin")
        club_id = first.json()["user"]["primary_club_id"]

        second = register(2, "club_admin", primary_club_id=club_id)
        self.assertEqual(second.status_code, 200, second.text)
        third = register(3, "club_admin", primary_club_id=club_id)
        self.assertEqual(third.status_code, 409, third.text)
        self.assertIn("two club admins", third.json()["detail"])
        multi = register(4, "player", roles=["player", "club_admin"], primary_club_id=club_id.upper())
        self.assertEqual(multi.status_code, 409, multi.text)
        player = register(5, "player", primary_club_id=club_id)
        self.assertEqual(player.status_code, 200, player.text)
        captain = register(6, "captain", primary_club_id=club_id)
        self.assertEqual(captain.status_code, 200, captain.text)

        with self.main._auth_connection() as connection:
            admins = connection.execute(
                "SELECT COUNT(DISTINCT user_id) FROM app_user_club_roles WHERE club_id = ? AND role_name = 'club_admin'",
                (club_id,),
            ).fetchone()[0]
            self.assertEqual(admins, 2)
            self.assertIsNone(connection.execute("SELECT id FROM app_users WHERE email = ?", ("limit-qa-3@example.invalid",)).fetchone())
        self.assertFalse(any(m.get("name") == "Limit QA Player 3" for m in self.main.load_store()["members"]))
