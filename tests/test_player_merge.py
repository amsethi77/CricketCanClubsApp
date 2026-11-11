import unittest

from app.player_merge import MergeError, merge_members_in_store
from tests.test_local_qa import LocalQATestCase

PLAYER_MOBILE = "4375590105"
SUPERADMIN_MOBILE = "14164508695"


def _store() -> dict:
    return {
        "members": [
            {"id": "m1", "player_id": "P1", "name": "Ann Lee", "aliases": ["A Lee"], "club_memberships": [{"club_id": "c1", "club_name": "Alpha"}]},
            {"id": "m2", "player_id": "P2", "name": "Ann  Lee", "aliases": ["Annie Lee"], "club_memberships": [{"club_id": "c2", "club_name": "Beta"}]},
            {"id": "m3", "player_id": "P3", "name": "Bo Chan", "aliases": [], "club_memberships": [{"club_id": "c2", "club_name": "Beta"}]},
        ],
        "fixtures": [
            {
                "id": "f1",
                "heartlake_captain_member_id": "m2",
                "selected_playing_xi_member_ids": ["m2", "m3"],
                "innings": [{"batters": [{"member_id": "m2", "player_name": "Ann Lee", "runs": 5}]}],
            }
        ],
        "archive_uploads": [{"id": "a1", "players": [{"member_id": "m2", "player_name": "Annie Lee"}]}],
    }


def _shared_store() -> dict:
    store = _store()
    store["fixtures"].append({"id": "f2", "selected_playing_xi_member_ids": ["m1", "m3"]})
    return store


class PlayerMergeTests(unittest.TestCase):
    def test_older_record_survives_and_references_follow_it(self) -> None:
        store = _store()
        summary = merge_members_in_store(store, "m2", "m1")

        self.assertEqual(summary["kept_member_id"], "m1")
        self.assertEqual(summary["removed_member_id"], "m2")
        self.assertEqual([member["id"] for member in store["members"]], ["m1", "m3"])
        fixture = store["fixtures"][0]
        self.assertEqual(fixture["heartlake_captain_member_id"], "m1")
        self.assertEqual(fixture["selected_playing_xi_member_ids"], ["m1", "m3"])
        self.assertEqual(fixture["innings"][0]["batters"][0]["member_id"], "m1")
        self.assertEqual(store["archive_uploads"][0]["players"][0]["member_id"], "m1")
        self.assertEqual(summary["references_rewritten"], 4)

    def test_scorecard_names_are_not_changed(self) -> None:
        store = _store()
        merge_members_in_store(store, "m1", "m2")
        self.assertEqual(store["fixtures"][0]["innings"][0]["batters"][0]["player_name"], "Ann Lee")
        self.assertEqual(store["archive_uploads"][0]["players"][0]["player_name"], "Annie Lee")

    def test_aliases_and_club_links_are_folded_into_survivor(self) -> None:
        store = _store()
        summary = merge_members_in_store(store, "m1", "m2")
        survivor = store["members"][0]
        self.assertEqual(survivor["aliases"], ["A Lee", "Annie Lee"])
        self.assertEqual(summary["aliases_added"], ["Annie Lee"])
        self.assertEqual([link["club_name"] for link in survivor["club_memberships"]], ["Alpha", "Beta"])

    def test_name_plus_initial_counts_as_a_match(self) -> None:
        from app.main import _names_look_same
        self.assertTrue(_names_look_same("Bim", "Bim B"))
        self.assertTrue(_names_look_same("Amit", "Amit S"))
        self.assertFalse(_names_look_same("Amit", "Amit Sharma"))
        self.assertFalse(_names_look_same("Am", "Amit S"))
        self.assertFalse(_names_look_same("Bim", ""))

    def test_aliases_count_for_name_matching(self) -> None:
        from app.main import _members_look_same
        bim = {"name": "Bim", "aliases": ["Bim B"]}
        self.assertTrue(_members_look_same(bim, {"name": "Bim B"}))
        self.assertFalse(_members_look_same(bim, {"name": "Carl Dunn"}))

    def test_candidate_score_is_75_percent_or_more(self) -> None:
        from app.main import PLAYER_MERGE_SUGGEST_MIN_SCORE
        from app.ai_duplicate_engine import AIDuplicateEngine
        self.assertEqual(PLAYER_MERGE_SUGGEST_MIN_SCORE, 0.75)
        engine = AIDuplicateEngine()
        self.assertGreaterEqual(engine.score({"name": "Michael Jones"}, {"name": "Michael Jone"}).score, 0.75)
        self.assertLess(engine.score({"name": "Ann Lee"}, {"name": "Zed Quartermain"}).score, 0.75)

    def test_engine_suggests_initial_match_only_with_club_evidence(self) -> None:
        from app.ai_duplicate_engine import AIDuplicateEngine
        engine = AIDuplicateEngine()
        bim = {"name": "Bim", "primary_club_id": "c1", "club_memberships": [{"club_id": "c1"}]}
        same_club = {"name": "Bim B", "primary_club_id": "c1", "club_memberships": [{"club_id": "c1"}]}
        other_club = {"name": "Bim B", "primary_club_id": "c2", "club_memberships": [{"club_id": "c2"}]}
        self.assertGreater(engine.score(bim, same_club).score, 0.75)
        self.assertLessEqual(engine.score(bim, other_club).score, 0.75)
        self.assertIn("same primary club", engine.score(bim, same_club).reasons)

    def test_engine_uses_secondary_clubs(self) -> None:
        from app.ai_duplicate_engine import AIDuplicateEngine
        engine = AIDuplicateEngine()
        first = {"name": "Sam Ray", "primary_club_id": "c1", "club_memberships": [{"club_id": "c1"}, {"club_id": "c3"}]}
        second = {"name": "Sam Ray", "primary_club_id": "c2", "club_memberships": [{"club_id": "c2"}, {"club_id": "c3"}]}
        pair = engine.score(first, second)
        self.assertEqual(pair.club_score, 0.6)
        self.assertIn("shares a club (primary or secondary)", pair.reasons)

    def test_engine_vetoes_two_names_batting_in_the_same_match(self) -> None:
        from app.ai_duplicate_engine import AIDuplicateEngine
        engine = AIDuplicateEngine([{"amit", "amit s"}])
        amit = {"name": "Amit", "primary_club_id": "c1", "club_memberships": [{"club_id": "c1"}]}
        amit_s = {"name": "Amit S", "primary_club_id": "c1", "club_memberships": [{"club_id": "c1"}]}
        pair = engine.score(amit, amit_s)
        self.assertTrue(pair.vetoed)
        self.assertEqual(pair.score, 0.0)
        self.assertFalse(engine.score(amit, amit_s, check_matches=False).vetoed)

    def test_player_can_choose_which_record_survives(self) -> None:
        store = {"members": [
            {"id": "older-rec", "name": "Bim", "aliases": [], "club_memberships": []},
            {"id": "newer-rec", "name": "Bim B", "aliases": [], "club_memberships": []},
        ]}
        summary = merge_members_in_store(store, "older-rec", "newer-rec", keep_id="newer-rec")
        self.assertEqual(summary["kept_member_id"], "newer-rec")
        self.assertEqual([m["id"] for m in store["members"]], ["newer-rec"])

    def test_upload_names_flag_aliases_and_possible_duplicates(self) -> None:
        from app.main import _card_name_matches, _name_match_notice
        store = {"clubs": [], "members": [
            {"id": "m1", "name": "Amit Sethi", "aliases": ["Amit S"], "club_memberships": []},
            {"id": "b1", "name": "Michael Jones", "aliases": [], "club_memberships": []},
            {"id": "b2", "name": "Michael Jone", "aliases": [], "club_memberships": []},
        ]}
        card = {"innings": [{"batting": [{"name": "Amit S"}, {"name": "Michael Jones"}], "bowling": [{"name": "Zed Nobody"}]}]}
        matches = _card_name_matches(store, card)

        self.assertEqual([m["kind"] for m in matches], ["recognised", "duplicate"])
        self.assertEqual(matches[0]["members"][0]["id"], "m1")
        self.assertEqual([m["id"] for m in matches[1]["members"]], ["b1", "b2"])
        self.assertFalse(matches[1]["can_merge"])
        notice = _name_match_notice(matches)
        self.assertIn("'Amit S' is recognised as Amit Sethi", notice)
        self.assertIn("'Michael Jones' and 'Michael Jone' look like the same player", notice)
        self.assertEqual(_name_match_notice([]), "")

    def test_stats_add_up_after_merge_through_alias(self) -> None:
        from app.cricket_store import _build_materialized_member_stats

        def performance(name: str, runs: int, balls: int, wickets: int) -> dict:
            return {"player_name": name, "runs": runs, "balls": balls, "wickets": wickets, "catches": 0, "fours": 1, "sixes": 0, "notes": "out"}

        store = {
            "clubs": [{"id": "c1", "name": "Alpha"}],
            "members": [
                {"id": "m1", "player_id": "1000", "name": "Bim", "aliases": [], "club_memberships": [{"club_id": "c1", "club_name": "Alpha"}]},
                {"id": "m2", "player_id": "1001", "name": "Bim B", "aliases": [], "club_memberships": [{"club_id": "c1", "club_name": "Alpha"}]},
            ],
            "fixtures": [
                {"id": "f1", "date": "2026-08-01", "status": "completed", "performances": [performance("Bim", 20, 15, 0)]},
                {"id": "f2", "date": "2026-08-08", "status": "completed", "performances": [performance("Bim B", 30, 25, 1)]},
            ],
            "archive_uploads": [],
        }
        merge_members_in_store(store, "m1", "m2")
        row = next(item for item in _build_materialized_member_stats(store)[0] if item["member_id"] == "m1")
        self.assertEqual((row["runs"], row["matches"], row["wickets"]), (50, 2, 1))

    def test_refuses_when_both_players_appear_in_one_record(self) -> None:
        store = _shared_store()
        with self.assertRaises(MergeError):
            merge_members_in_store(store, "m1", "m3")
        self.assertEqual([member["id"] for member in store["members"]], ["m1", "m2", "m3"])

    def test_rejects_same_player_and_unknown_player(self) -> None:
        with self.assertRaises(MergeError):
            merge_members_in_store(_store(), "m1", "m1")
        with self.assertRaises(MergeError):
            merge_members_in_store(_store(), "m1", "missing")


class PlayerMergeEndpointTests(LocalQATestCase):
    def _add_members(self) -> None:
        store = self.main.load_store()
        store.setdefault("members", []).extend([
            {"id": "qa-merge-older", "player_id": "QAMERGE1", "name": "Merge Test Zed", "aliases": [], "club_memberships": []},
            {"id": "qa-merge-newer", "player_id": "QAMERGE2", "name": "Merge Test Zedd", "aliases": ["Zed Test"], "club_memberships": []},
        ])
        self.main.save_store(store)

    def _member_ids(self) -> list[str]:
        return [str(member.get("id")) for member in self.main.load_store().get("members", []) or []]

    def test_superadmin_merge_then_undo(self) -> None:
        self._add_members()
        admin = self.signin(SUPERADMIN_MOBILE)
        player = self.signin(PLAYER_MOBILE)

        denied = self.client.post("/api/admin/name-matches/merge", json={"first_member_id": "qa-merge-newer", "second_member_id": "qa-merge-older"}, headers=self.auth_headers(player["token"]))
        self.assertEqual(denied.status_code, 403, denied.text)
        self.assertIn("qa-merge-newer", self._member_ids())

        merged = self.client.post("/api/admin/name-matches/merge", json={"first_member_id": "qa-merge-newer", "second_member_id": "qa-merge-older"}, headers=self.auth_headers(admin["token"]))
        self.assertEqual(merged.status_code, 200, merged.text)
        payload = merged.json()
        self.assertEqual(payload["kept_member_id"], "qa-merge-older")
        self.assertEqual(payload["removed_member_id"], "qa-merge-newer")
        self.assertIn("Zed Test", self.main._member_by_id(self.main.load_store(), "qa-merge-older")["aliases"])
        self.assertNotIn("qa-merge-newer", self._member_ids())

        undone = self.client.post(f"/api/admin/member-merges/{payload['merge_id']}/undo", headers=self.auth_headers(admin["token"]))
        self.assertEqual(undone.status_code, 200, undone.text)
        self.assertIn("qa-merge-newer", self._member_ids())
        again = self.client.post(f"/api/admin/member-merges/{payload['merge_id']}/undo", headers=self.auth_headers(admin["token"]))
        self.assertEqual(again.status_code, 409, again.text)

    def test_admin_can_keep_newer_record_when_merging(self) -> None:
        self._add_members()
        admin = self.signin(SUPERADMIN_MOBILE)
        merged = self.client.post("/api/admin/name-matches/merge", json={"first_member_id": "qa-merge-older", "second_member_id": "qa-merge-newer", "keep_member_id": "qa-merge-newer"}, headers=self.auth_headers(admin["token"]))
        self.assertEqual(merged.status_code, 200, merged.text)
        self.assertEqual(merged.json()["kept_member_id"], "qa-merge-newer")
        self.assertNotIn("qa-merge-older", self._member_ids())

    def test_admin_keep_choice_must_be_one_of_the_pair(self) -> None:
        self._add_members()
        admin = self.signin(SUPERADMIN_MOBILE)
        bad = self.client.post("/api/admin/name-matches/merge", json={"first_member_id": "qa-merge-older", "second_member_id": "qa-merge-newer", "keep_member_id": "someone-else"}, headers=self.auth_headers(admin["token"]))
        self.assertEqual(bad.status_code, 400, bad.text)
        self.assertIn("qa-merge-older", self._member_ids())

    def test_rejected_name_match_is_saved_and_hidden(self) -> None:
        self._add_members()
        admin = self.signin(SUPERADMIN_MOBILE)
        headers = self.auth_headers(admin["token"])

        def listed_pairs() -> list[set[str]]:
            data = self.client.get("/api/admin/name-matches", headers=headers).json()
            return [{str(member["id"]) for member in group["members"]} for group in data["groups"]]

        self.assertIn({"qa-merge-older", "qa-merge-newer"}, listed_pairs())
        rejected = self.client.post("/api/admin/name-matches/reject", json={"first_member_id": "qa-merge-newer", "second_member_id": "qa-merge-older"}, headers=headers)
        self.assertEqual(rejected.status_code, 200, rejected.text)
        self.assertNotIn({"qa-merge-older", "qa-merge-newer"}, listed_pairs())
        self.assertIn("qa-merge-newer", self._member_ids())

    def test_player_merge_request_is_decided_by_admin(self) -> None:
        player = self.signin(PLAYER_MOBILE)
        admin = self.signin(SUPERADMIN_MOBILE)
        store = self.main.load_store()
        user_row, _ = self.main._auth_user_from_token(player["token"])
        own = self.main._member_for_user(store, user_row)
        own_id, own_name = str(own["id"]), str(own["name"])
        store["members"].extend([
            {"id": "qa-req-dup", "player_id": "QAREQ2", "name": own_name, "aliases": [], "club_memberships": []},
            {"id": "qa-req-other", "player_id": "QAREQ3", "name": "Unrelated Person Zed", "aliases": [], "club_memberships": []},
        ])
        self.main.save_store(store)

        candidates = self.client.get("/api/player/merge-candidates", headers=self.auth_headers(player["token"])).json()
        self.assertIn("qa-req-dup", [item["id"] for item in candidates["candidates"]])
        self.assertNotIn("qa-req-other", [item["id"] for item in candidates["candidates"]])

        unrelated = self.client.post("/api/player/merge-requests", json={"target_member_id": "qa-req-other"}, headers=self.auth_headers(player["token"]))
        self.assertEqual(unrelated.status_code, 400, unrelated.text)

        sent = self.client.post("/api/player/merge-requests", json={"target_member_id": "qa-req-dup"}, headers=self.auth_headers(player["token"]))
        self.assertEqual(sent.status_code, 200, sent.text)
        request_id = sent.json()["request_id"]
        again = self.client.post("/api/player/merge-requests", json={"target_member_id": "qa-req-dup"}, headers=self.auth_headers(player["token"]))
        self.assertEqual(again.json()["request_id"], request_id)

        pending = self.client.get("/api/admin/merge-requests", headers=self.auth_headers(admin["token"])).json()["requests"]
        self.assertIn(request_id, [item["id"] for item in pending])

        player_decides = self.client.post(f"/api/admin/merge-requests/{request_id}/decision", json={"decision": "approve"}, headers=self.auth_headers(player["token"]))
        self.assertEqual(player_decides.status_code, 403, player_decides.text)

        approved = self.client.post(f"/api/admin/merge-requests/{request_id}/decision", json={"decision": "approve"}, headers=self.auth_headers(admin["token"]))
        self.assertEqual(approved.status_code, 200, approved.text)
        self.assertEqual(approved.json()["status"], "approved")
        self.assertNotIn("qa-req-dup", self._member_ids())
        self.assertIn(own_id, self._member_ids())

        decided_again = self.client.post(f"/api/admin/merge-requests/{request_id}/decision", json={"decision": "reject"}, headers=self.auth_headers(admin["token"]))
        self.assertEqual(decided_again.status_code, 404, decided_again.text)

    def test_admin_can_reject_merge_request(self) -> None:
        player = self.signin(PLAYER_MOBILE)
        admin = self.signin(SUPERADMIN_MOBILE)
        store = self.main.load_store()
        user_row, _ = self.main._auth_user_from_token(player["token"])
        own = self.main._member_for_user(store, user_row)
        own_name = str(own["name"])
        store["members"].append({"id": "qa-rej-dup", "player_id": "QAREJ2", "name": own_name, "aliases": [], "club_memberships": []})
        self.main.save_store(store)

        sent = self.client.post("/api/player/merge-requests", json={"target_member_id": "qa-rej-dup"}, headers=self.auth_headers(player["token"]))
        self.assertEqual(sent.status_code, 200, sent.text)
        request_id = sent.json()["request_id"]

        rejected = self.client.post(f"/api/admin/merge-requests/{request_id}/decision", json={"decision": "reject"}, headers=self.auth_headers(admin["token"]))
        self.assertEqual(rejected.status_code, 200, rejected.text)
        self.assertEqual(rejected.json()["status"], "rejected")
        self.assertIn("qa-rej-dup", self._member_ids())
        pending = self.client.get("/api/admin/merge-requests", headers=self.auth_headers(admin["token"])).json()["requests"]
        self.assertNotIn(request_id, [item["id"] for item in pending])

    def test_rejected_suggestion_is_saved_and_hidden(self) -> None:
        player = self.signin(PLAYER_MOBILE)
        store = self.main.load_store()
        user_row, _ = self.main._auth_user_from_token(player["token"])
        own = self.main._member_for_user(store, user_row)
        own_name = str(own["name"])
        store["members"].extend([
            {"id": "qa-dismiss-dup", "player_id": "QADIS2", "name": own_name, "full_name": own_name, "aliases": [], "club_memberships": []},
            {"id": "qa-dismiss-other", "player_id": "QADIS3", "name": "Unrelated Person Zed", "aliases": [], "club_memberships": []},
        ])
        self.main.save_store(store)
        headers = self.auth_headers(player["token"])

        before = self.client.get("/api/player/merge-candidates", headers=headers).json()["candidates"]
        self.assertIn("qa-dismiss-dup", [item["id"] for item in before])
        dup = next(item for item in before if item["id"] == "qa-dismiss-dup")
        self.assertIn("career", dup)
        self.assertIn("full_name", dup)

        details = self.client.get("/api/player/merge-candidates/qa-dismiss-dup/details", headers=headers)
        self.assertEqual(details.status_code, 200, details.text)
        self.assertEqual(details.json()["id"], "qa-dismiss-dup")
        hidden_details = self.client.get("/api/player/merge-candidates/qa-dismiss-other/details", headers=headers)
        self.assertEqual(hidden_details.status_code, 404, hidden_details.text)

        dismissed = self.client.post("/api/player/merge-suggestions/qa-dismiss-dup/dismiss", headers=headers)
        self.assertEqual(dismissed.status_code, 200, dismissed.text)
        again = self.client.post("/api/player/merge-suggestions/qa-dismiss-dup/dismiss", headers=headers)
        self.assertEqual(again.status_code, 200, again.text)

        after = self.client.get("/api/player/merge-candidates", headers=headers).json()["candidates"]
        self.assertNotIn("qa-dismiss-dup", [item["id"] for item in after])


if __name__ == "__main__":
    unittest.main()
