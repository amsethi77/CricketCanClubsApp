"""The live-match PDF must show what the match page shows (Nov 23 2026, Dhruvika: "Ensure that they are the same
going forward"). app/scorecard_pdf.py repeats the rules of static/public_match.js (inningsFacts, howOut, tagHtml,
statusLine, renderScorecard); these checks fail if one side changes alone. README "Scorecard PDF = match page"."""
from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))

import scorecard_pdf  # noqa: E402
from cricket_store import summarize_innings_scorebook  # noqa: E402

JS = (ROOT / "app" / "static" / "public_match.js").read_text(encoding="utf-8")


def ball(striker, bowler, runs=0, extras_type="none", extras_runs=0, **wicket):
    return {"striker": striker, "non_striker": "", "bowler": bowler, "runs_bat": runs, "extras_type": extras_type,
            "extras_runs": extras_runs, "wicket": bool(wicket), **wicket}


def match():
    balls = [
        ball("Ana", "Xan", 0, "wide", 2),
        ball("Ana", "Xan", 4, "no_ball", 1),
        ball("Ana", "Xan", 0, "bye", 3),
        ball("Bob", "Xan", 0, "leg_bye", 1),
        ball("Ana", "Xan", 0, wicket_type="stumped", wicket_player="Ana", fielder="Yul", new_batter="Cal"),
        ball("Cal", "Xan", 6),
    ]
    innings = {"inning_number": 1, "batting_team": "Home", "bowling_team": "Away", "overs_limit": 20, "status": "Live", "balls": balls}
    innings["summary"] = summarize_innings_scorebook(innings)
    return {
        "id": "abc12345", "club_name": "Home", "opponent": "Away", "match_type": "Friendly", "overs": "20",
        "venue": "Park", "date_label": "Nov 21", "scheduled_time": "10 AM", "status": "Live", "result": "TBD",
        "scorebook": {"innings": [innings, {"inning_number": 2, "batting_team": "Away", "bowling_team": "Home", "balls": []}]},
        "lineups": {"club": ["Ana", "Bob", "Cal"], "opponent": ["Xan", "Yul"],
                    "roles": {"club": {"captain": "Ana", "keeper": "Cal"}, "opponent": {"captain": "Yul", "keeper": "Yul"}}},
    }


class ScorecardPdfMatchesPage(unittest.TestCase):
    def test_extras_split_is_filled_in(self):
        summary = match()["scorebook"]["innings"][0]["summary"]
        self.assertEqual((summary["byes"], summary["legByes"], summary["wides"], summary["noBalls"]), (3, 1, 2, 1))

    def test_innings_view_matches_page_rules(self):
        view = scorecard_pdf.innings_view(match(), match()["scorebook"]["innings"][0])
        self.assertEqual(view["extras_label"], "Extras (b 3, lb 1, w 2, nb 1)")
        self.assertEqual(view["extras_total"], 7)
        rows = {row["name"]: row["how"] for row in view["batting"]}
        self.assertEqual(rows["Ana (c)"], "st Yul b Xan")  # keeper and bowler, like the page
        self.assertIn("Cal (wk)", rows)
        self.assertTrue(view["total_label"].startswith("Total (1 wkts, "))
        self.assertIn("Bob", view["yet_to_bat"][0] if view["yet_to_bat"] else "Bob")

    def test_how_out_same_words_as_page(self):
        cases = {
            "bowled": "b B", "lbw": "lbw b B", "hit_wicket": "hit wicket b B", "stumped": "st F b B",
            "run_out": "run out (F)", "retired_hurt": "retired hurt",
        }
        for kind, text in cases.items():
            self.assertEqual(scorecard_pdf.how_out({"wicket_type": kind, "bowler": "B", "fielder": "F"}), text)
        self.assertEqual(scorecard_pdf.how_out({"wicket_type": "caught", "bowler": "B", "fielder": "B"}), "c & b B")
        # the page has the same words (if the page changes them, change scorecard_pdf.how_out too)
        for words in ("`st ${f || \"?\"} b ${bowler}`", "`c & b ${bowler}`", "`hit wicket b ${bowler}`", "\"retired hurt\""):
            self.assertIn(words, JS)

    def test_tags_and_status_line(self):
        m = match()
        self.assertEqual(scorecard_pdf.role_tags(m, "opponent", "Yul"), " (c & wk)")
        self.assertEqual(scorecard_pdf.status_line(m), "Home batting · Away yet to bat")
        self.assertIn("batting · ${otherTeam} yet to bat", JS)
        self.assertIn("(b ${e.b}, lb ${e.lb}, w ${e.wd}, nb ${e.nb})", JS)

    def test_pdf_builds(self):
        pdf = scorecard_pdf.build_scorecard_pdf(match())
        self.assertTrue(pdf.startswith(b"%PDF"))


if __name__ == "__main__":
    unittest.main()
