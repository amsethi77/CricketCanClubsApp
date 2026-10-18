import os
import sqlite3
import unittest
from datetime import timedelta
from unittest.mock import patch

from app import subscriptions


class DefaultPlanTests(unittest.TestCase):
    def setUp(self) -> None:
        self.previous_env_cache = subscriptions._ENV_CACHE
        subscriptions._ENV_CACHE = {}
        self.default_plan_env = patch.dict(os.environ, {"CRICKETCLUBAPP_DEFAULT_PLAN": "premium"})
        self.default_plan_env.start()
        self.addCleanup(self.default_plan_env.stop)
        self.addCleanup(setattr, subscriptions, "_ENV_CACHE", self.previous_env_cache)

        self.connection = sqlite3.connect(":memory:")
        self.connection.row_factory = sqlite3.Row
        self.connection.executescript(
            """
            CREATE TABLE app_users (
                id INTEGER PRIMARY KEY,
                created_at TEXT
            );
            CREATE TABLE app_audit_log (
                actor_user_id INTEGER,
                action TEXT,
                created_at TEXT
            );
            """
        )
        subscriptions.ensure_schema(self.connection)

    def tearDown(self) -> None:
        self.connection.close()

    def _create_user(self, created_at: str | None = None) -> sqlite3.Row:
        created_at = created_at or subscriptions._iso(
            subscriptions.launch_at(self.connection) + timedelta(seconds=1)
        )
        cursor = self.connection.execute(
            "INSERT INTO app_users (created_at) VALUES (?)", (created_at,)
        )
        return self.connection.execute(
            "SELECT * FROM app_users WHERE id = ?", (cursor.lastrowid,)
        ).fetchone()

    def test_default_plan_can_switch_without_changing_manual_assignments(self) -> None:
        user = self._create_user()

        self.assertEqual(
            subscriptions.effective_plan(self.connection, user)["plan"],
            "pro",
        )

        os.environ["CRICKETCLUBAPP_DEFAULT_PLAN"] = "free"
        self.assertEqual(
            subscriptions.effective_plan(self.connection, user)["plan"],
            "free",
        )

        subscriptions.set_plan(self.connection, user, "free", source="admin")
        os.environ["CRICKETCLUBAPP_DEFAULT_PLAN"] = "premium"
        self.assertEqual(
            subscriptions.effective_plan(self.connection, user)["plan"],
            "free",
        )

    def test_legacy_automatic_free_plan_uses_configured_default(self) -> None:
        user = self._create_user()
        now = subscriptions._iso(subscriptions._now())
        self.connection.execute(
            """INSERT INTO app_subscriptions
               (user_id, plan, status, source, started_at, updated_at)
               VALUES (?, 'free', 'active', 'free', ?, ?)""",
            (user["id"], now, now),
        )

        self.assertEqual(
            subscriptions.effective_plan(self.connection, user)["plan"],
            "pro",
        )

    def test_invalid_default_plan_is_rejected(self) -> None:
        os.environ["CRICKETCLUBAPP_DEFAULT_PLAN"] = "enterprise"
        with self.assertRaisesRegex(ValueError, "CRICKETCLUBAPP_DEFAULT_PLAN"):
            subscriptions.configured_default_plan()


if __name__ == "__main__":
    unittest.main()
