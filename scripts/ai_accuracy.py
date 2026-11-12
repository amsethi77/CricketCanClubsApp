"""How accurate is the AI scorecard reader? (Nov 11 2026, Amit: "AI should be accurate 99.999% with batsman names,
runs, balls faced, 4s, 6s, 1s 2s 3s, bowling overs, runs, wickets, the match date, innings 1 or 2, captains and the
man of the match").

It reads the photos of published scorecards that a person checked (typed in or fixed with Edit, and the batters +
extras add up to the total) AGAIN with the AI, and compares every field with the checked card. Nothing is saved to
the scorecards - only a report. README: "How the AI reader learns" -> "Measuring accuracy".

Run from the project folder (needs GEMINI_API_KEY in .env, uses the free daily limit - about 1-2 reads per card):

    python scripts\\ai_accuracy.py               3 checked cards (each takes 1-3 minutes - leave it running)
    python scripts\\ai_accuracy.py --limit 10    10 cards
    python scripts\\ai_accuracy.py --ids 9800443f d922564e

The report is printed and saved in app/data/ai_accuracy/ (not in git). Run it again after changing the reader or
adding examples, and compare the overall %.
"""
from __future__ import annotations

import argparse
import difflib
import json
import os
import re
import sys
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "app"))
os.chdir(ROOT)


def norm(value) -> str:
    return re.sub(r"[^a-z0-9]", "", str(value or "").lower())


def num(value):
    text = str(value if value is not None else "").strip()
    try:
        return float(text) if text else None
    except ValueError:
        return None


def overs_text(summary) -> str | None:
    summary = summary or {}
    overs = str(summary.get("overs") if summary.get("overs") is not None else "").strip()
    if not overs:
        return None
    whole, _, part = overs.partition(".")
    balls = part[:1] if part.strip("0") else str(summary.get("balls") or "")
    balls = balls if balls.isdigit() and 0 < int(balls) < 6 else "0"
    return f"{int(float(whole or 0))}.{balls}"


def same_name(a, b) -> bool:
    x, y = norm(a), norm(b)
    return bool(x and y and (x == y or difflib.SequenceMatcher(None, x, y).ratio() >= 0.85))


def person_checked(upload: dict, template: dict, adds_up) -> bool:
    engine = str(upload.get("ocr_engine") or "")
    # Nov 11 2026: only cards a PERSON typed in or fixed with Edit. An approved AI read is not the truth (Imrans XI v
    # Heartlake was an old AI read: it had RAJ with 3 fours where the photo shows two 4s and a 6).
    return bool(template.get("innings")) and adds_up(template) and engine in {"manual-entry", "manual-import"}


class Score:
    def __init__(self) -> None:
        self.fields: dict[str, list[int]] = {}
        self.misses: list[str] = []

    def add(self, field: str, truth, read, label: str) -> None:
        if truth in (None, "", []):
            return  # nothing to compare against
        right = (num(truth) == num(read)) if num(truth) is not None else same_name(truth, read)
        ok, total = self.fields.setdefault(field, [0, 0])
        self.fields[field] = [ok + int(right), total + 1]
        if not right:
            self.misses.append(f"{label} {field}: card {truth!r}, AI {read!r}")

    def merge(self, other: "Score") -> None:
        for field, (ok, total) in other.fields.items():
            mine = self.fields.setdefault(field, [0, 0])
            self.fields[field] = [mine[0] + ok, mine[1] + total]


def compare(truth: dict, read: dict) -> Score:
    score = Score()
    tm, rm = truth.get("match") or {}, read.get("match") or {}
    score.add("match date", tm.get("date"), rm.get("date"), "match")
    for key in ("team_1", "team_2"):
        score.add("captain", ((tm.get("captains") or {}).get(key)), ((rm.get("captains") or {}).get(key)), key)
    score.add("man of the match", tm.get("man_of_match"), rm.get("man_of_match"), "match")
    read_innings = [item for item in read.get("innings") or [] if isinstance(item, dict)]
    for index, inn in enumerate(item for item in truth.get("innings") or [] if isinstance(item, dict)):
        other = next((item for item in read_innings if same_name(item.get("batting_team"), inn.get("batting_team"))), None)
        if other is None and index < len(read_innings):
            other = read_innings[index]
        label = f"innings {index + 1} ({inn.get('batting_team') or '?'})"
        other = other or {}
        score.add("innings number", inn.get("inning_number"), other.get("inning_number"), label)
        score.add("batting team", inn.get("batting_team"), other.get("batting_team"), label)
        for key in ("runs", "wickets"):
            score.add(f"innings {key}", (inn.get("summary") or {}).get(key), (other.get("summary") or {}).get(key), label)
        # overs: "21.5" on the card = 21 overs + 5 balls; the AI may give overs 21 and balls 5 separately
        score.add("innings overs", overs_text(inn.get("summary")), overs_text(other.get("summary")), label)
        score.add("extras", (inn.get("extras") or {}).get("total"), (other.get("extras") or {}).get("total"), label)
        read_bat = list(other.get("batting") or [])
        for row in inn.get("batting") or []:
            name = (row.get("player") or {}).get("name") if isinstance(row.get("player"), dict) else row.get("name")
            if not name:
                continue
            match = next((item for item in read_bat if same_name(name, (item.get("player") or {}).get("name"))), None)
            score.add("batter name", name, (match.get("player") or {}).get("name") if match else None, label)
            if match:
                read_bat.remove(match)
                for key in ("runs", "balls", "fours", "sixes", "ones", "twos", "threes", "dots"):
                    score.add(f"batter {key}", row.get(key), match.get(key), f"{label} {name}")
        read_bowl = list(other.get("bowling") or [])
        for row in inn.get("bowling") or []:
            name = (row.get("player") or {}).get("name") if isinstance(row.get("player"), dict) else row.get("name")
            if not name:
                continue
            match = next((item for item in read_bowl if same_name(name, (item.get("player") or {}).get("name"))), None)
            score.add("bowler name", name, (match.get("player") or {}).get("name") if match else None, label)
            if match:
                read_bowl.remove(match)
                for key in ("overs", "maidens", "runs_conceded", "wickets"):
                    score.add(f"bowler {key}", row.get(key), match.get(key), f"{label} {name}")
    return score


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--limit", type=int, default=3)
    parser.add_argument("--ids", nargs="*", default=[])
    parser.add_argument("--pause", type=float, default=4.0, help="seconds between reads (free-tier rate limit)")
    args = parser.parse_args()

    import logging

    import main as app  # the app's own reader setup: roster, aliases, corrections, worked examples
    from ai_vision import _template_adds_up

    # only this script's lines on the screen (the app logs every step at DEBUG)
    logging.getLogger().setLevel(logging.WARNING)
    for name in list(logging.root.manager.loggerDict):
        logging.getLogger(name).setLevel(logging.WARNING)

    if not app.ai_vision.enabled():
        print("No AI reader is set up. Put GEMINI_API_KEY=... in the .env file first.")
        return 1
    store = app.load_store()
    cards = []
    for upload in store.get("archive_uploads", []) or []:
        if args.ids and str(upload.get("id")) not in args.ids:
            continue
        if not args.ids and str(upload.get("status") or "").lower() != "approved":
            continue
        template = app._scorecard_pick_template(upload) or {}
        path = app._upload_file_path(upload)
        if path is None or upload.get("second_photo_file"):
            continue  # a card on two photos would need both reads; keep the test simple
        if args.ids or person_checked(upload, template, _template_adds_up):
            cards.append((upload, template, path))
    cards = cards[: max(1, args.limit)] if not args.ids else cards
    if not cards:
        print("No published scorecard here was typed in or fixed by a person (with its photo on this computer), so there is\n"
              "nothing reliable to compare with. Open a card, fix it with Edit so it matches the photo exactly, publish it,\n"
              "and run this again - or run it on a copy of the data that has checked cards (Amit's has 13).")
        return 1

    total = Score()
    report = {"run_at": datetime.now().astimezone().isoformat(timespec="seconds"), "cards": []}
    print(f"Reading {len(cards)} checked scorecards again with the AI. Each one takes 1-3 minutes (the AI looks at the "
          "photo, zoomed copies and the worked examples). Leave this window open; Ctrl+C stops and shows what's done so far.\n")
    try:
        _run(app, store, cards, total, report, args)
    except KeyboardInterrupt:
        print("\nStopped (Ctrl+C). Results of the cards read so far:")
    _summary(total, report)
    return 0


def _run(app, store, cards, total, report, args) -> None:
    for number, (upload, truth, path) in enumerate(cards, 1):
        title = app._scorecard_from_archive(upload).get("title") or upload.get("id")
        print(f"[{number}/{len(cards)}] {upload.get('id')} {title} - reading...", flush=True)
        started = time.time()
        club = app._selected_club(store, str(upload.get("club_id") or ""))
        result = app._read_photo_with_ai(store, upload, path, club)
        if not result.get("template") and "limit" not in str(result.get("error") or "").lower():
            # Google busy (503) or a weaker fallback model gave no scorecard: wait a minute and try once more
            print(f"    not read ({result.get('error')}) - Google may be busy, trying again in 60s...", flush=True)
            time.sleep(60)
            app.ai_vision._GEMINI_SKIP.clear()
            result = app._read_photo_with_ai(store, upload, path, club)
        print(f"    read in {time.time() - started:.0f}s with {result.get('model') or 'no model'}")
        if not result.get("template"):
            print(f"    not read: {result.get('error')}")
            report["cards"].append({"id": upload.get("id"), "error": result.get("error")})
            if "limit" in str(result.get("error") or "").lower():
                break
            continue
        score = compare(truth, result["template"])
        total.merge(score)
        right = sum(ok for ok, _ in score.fields.values())
        checked = sum(n for _, n in score.fields.values())
        print(f"    {right}/{checked} fields right ({100 * right / max(1, checked):.1f}%)")
        for miss in score.misses[:12]:
            print(f"      - {miss}")
        report["cards"].append({"id": upload.get("id"), "title": title, "model": result.get("model"), "right": right, "checked": checked, "misses": score.misses})
        time.sleep(args.pause)


def _summary(total, report) -> None:
    if not total.fields:
        print("No card was read completely, so there is nothing to score yet.")
        return
    print("\nAccuracy by field (all cards):")
    for field, (ok, n) in sorted(total.fields.items()):
        print(f"  {field:<22} {ok:>4}/{n:<4} {100 * ok / max(1, n):6.1f}%")
    right = sum(ok for ok, _ in total.fields.values())
    checked = sum(n for _, n in total.fields.values())
    overall = 100 * right / max(1, checked)
    print(f"\nOVERALL: {right}/{checked} = {overall:.2f}%")
    report.update({"overall": overall, "fields": total.fields})
    folder = Path(os.getenv("CRICKETCLUBAPP_DATA_ROOT") or ROOT / "app" / "data") / "ai_accuracy"
    folder.mkdir(parents=True, exist_ok=True)
    out = folder / f"accuracy-{datetime.now().strftime('%Y%m%d-%H%M%S')}.json"
    out.write_text(json.dumps(report, indent=1), encoding="utf-8")
    print(f"Report saved: {out}")


if __name__ == "__main__":
    raise SystemExit(main())
