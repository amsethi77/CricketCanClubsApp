import re
from contextlib import closing

from tests.test_local_qa import LocalQATestCase


CLAIM_NAME = "Zanzibar Quelch"
PLAYER_MOBILE = "4375590105"
SUPERADMIN_MOBILE = "14164508695"


class PlayerClaimTests(LocalQATestCase):
    def _player_member(self, token: str) -> dict:
        store = self.main.load_store()
        user_row, _ = self.main._auth_user_from_token(token)
        member = self.main._member_for_user(store, user_row)
        self.assertIsNotNone(member, "test player should be linked to a member record")
        return member

    def _member_snapshot(self, member_id: str) -> tuple[int, list]:
        store = self.main.load_store()
        member = self.main._member_by_id(store, member_id)
        return len(store.get("members", []) or []), list((member or {}).get("aliases") or [])

    def _claim(self, token: str, name: str = CLAIM_NAME):
        return self.client.post("/api/player/name-suggestions/claim", json={"name": name}, headers=self.auth_headers(token))

    def _claim_row_statuses(self, name: str) -> list[str]:
        with closing(self.main._auth_connection()) as connection:
            rows = connection.execute(
                "SELECT status FROM app_name_claims WHERE claimed_name_norm = ? ORDER BY id",
                (self.main.normalize_name(name),),
            ).fetchall()
        return [str(row["status"]) for row in rows]

    def test_claim_creates_pending_request_and_leaves_members_untouched(self) -> None:
        player = self.signin(PLAYER_MOBILE)
        member = self._player_member(player["token"])
        before = self._member_snapshot(str(member["id"]))

        response = self._claim(player["token"])
        self.assertEqual(response.status_code, 200, response.text)
        payload = response.json()
        self.assertEqual(payload["status"], "pending")
        self.assertEqual(self._member_snapshot(str(member["id"])), before)
        self.assertEqual(self._claim_row_statuses(CLAIM_NAME), ["pending"])

        again = self._claim(player["token"])
        self.assertEqual(again.status_code, 200, again.text)
        self.assertEqual(again.json()["claim_id"], payload["claim_id"])
        self.assertEqual(self._claim_row_statuses(CLAIM_NAME), ["pending"])

    def test_superadmin_approval_adds_alias_only_and_keeps_member_records(self) -> None:
        player = self.signin(PLAYER_MOBILE)
        admin = self.signin(SUPERADMIN_MOBILE)
        member = self._player_member(player["token"])
        self._claim(player["token"])

        listed = self.client.get("/api/admin/name-claims", headers=self.auth_headers(admin["token"]))
        self.assertEqual(listed.status_code, 200, listed.text)
        claim = next(item for item in listed.json()["claims"] if item["claimed_name"] == CLAIM_NAME)
        count_before, _ = self._member_snapshot(str(member["id"]))

        decision = self.client.post(
            f"/api/admin/name-claims/{claim['id']}/decision",
            json={"decision": "approve", "note": "same player"},
            headers=self.auth_headers(admin["token"]),
        )
        self.assertEqual(decision.status_code, 200, decision.text)
        self.assertEqual(decision.json()["status"], "approved")
        count_after, aliases = self._member_snapshot(str(member["id"]))
        self.assertEqual(count_after, count_before, "approval must not delete or merge member records")
        self.assertIn(CLAIM_NAME, aliases)
        self.assertEqual(self._claim_row_statuses(CLAIM_NAME), ["approved"])

        second = self.client.post(
            f"/api/admin/name-claims/{claim['id']}/decision",
            json={"decision": "reject"},
            headers=self.auth_headers(admin["token"]),
        )
        self.assertEqual(second.status_code, 404, second.text)

    def test_rejection_leaves_aliases_unchanged(self) -> None:
        player = self.signin(PLAYER_MOBILE)
        admin = self.signin(SUPERADMIN_MOBILE)
        member = self._player_member(player["token"])
        self._claim(player["token"])
        claim = next(
            item for item in self.client.get("/api/admin/name-claims", headers=self.auth_headers(admin["token"])).json()["claims"]
            if item["claimed_name"] == CLAIM_NAME
        )
        before = self._member_snapshot(str(member["id"]))

        decision = self.client.post(
            f"/api/admin/name-claims/{claim['id']}/decision",
            json={"decision": "reject", "note": "not this player"},
            headers=self.auth_headers(admin["token"]),
        )
        self.assertEqual(decision.status_code, 200, decision.text)
        self.assertEqual(self._member_snapshot(str(member["id"])), before)
        self.assertEqual(self._claim_row_statuses(CLAIM_NAME), ["rejected"])

    def test_player_without_manage_players_cannot_list_or_decide_claims(self) -> None:
        player = self.signin(PLAYER_MOBILE)
        self._claim(player["token"])
        headers = self.auth_headers(player["token"])

        listed = self.client.get("/api/admin/name-claims", headers=headers)
        self.assertEqual(listed.status_code, 403, listed.text)
        decided = self.client.post("/api/admin/name-claims/1/decision", json={"decision": "approve"}, headers=headers)
        self.assertEqual(decided.status_code, 403, decided.text)
        self.assertEqual(self._claim_row_statuses(CLAIM_NAME), ["pending"])

    def test_name_matches_is_read_only_and_restricted_to_managers(self) -> None:
        player = self.signin(PLAYER_MOBILE)
        admin = self.signin(SUPERADMIN_MOBILE)
        denied = self.client.get("/api/admin/name-matches", headers=self.auth_headers(player["token"]))
        self.assertEqual(denied.status_code, 403, denied.text)

        store = self.main.load_store()
        count_before = len(store.get("members", []) or [])
        response = self.client.get("/api/admin/name-matches", headers=self.auth_headers(admin["token"]))
        self.assertEqual(response.status_code, 200, response.text)
        payload = response.json()
        self.assertIn("groups", payload)
        for group in payload["groups"]:
            self.assertIn(group["match_type"], {"exact", "similar"})
            self.assertGreaterEqual(len(group["members"]), 2)
            for member in group["members"]:
                self.assertEqual(set(member), {"id", "player_id", "name", "clubs"})
        self.assertEqual(len(self.main.load_store().get("members", []) or []), count_before)

    def test_normalize_name_is_one_shared_implementation(self) -> None:
        from app import cricket_store

        self.assertIs(self.main.normalize_name, cricket_store.normalize_name)

    def test_normalize_name_matches_previous_behaviour_on_existing_records(self) -> None:
        store = self.main.load_store()
        names: list[str] = []
        for member in store.get("members", []) or []:
            names.extend(str(value or "") for value in [member.get("name"), member.get("full_name"), *(member.get("aliases") or [])])
        names = [name for name in names if name.strip()]
        self.assertTrue(names)

        def previous(value: str) -> str:
            return (value or "").strip().lower()

        for name in names:
            with self.subTest(name=name):
                if previous(name) != self.main.normalize_name(name):
                    # the only intended difference: runs of inner whitespace now collapse to one space
                    self.assertRegex(name.strip(), r"\s{2,}|[\t\r\n]")
                    self.assertEqual(self.main.normalize_name(name), re.sub(r"\s+", " ", previous(name)))


if __name__ == "__main__":
    import unittest

    unittest.main()
