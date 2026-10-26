"""Clean up the scorecard uploads and read every photo again with the AI reader.

README: "Clean up and re-read all scorecards" (Oct 20 2026).

Run from the project folder with the app STOPPED (Ctrl + C first):

    python scripts\\scorecards_reread_all.py --dry-run     # only shows what would happen
    python scripts\\scorecards_reread_all.py               # does it (backup first, then clean up, then re-read)
    python scripts\\scorecards_reread_all.py --samples     # test the AI on the 3 sample cards (answer key)

What it does:
 1. Backs up the database to DB-Backup/before_reread_<date-time>/.
 2. Deletes uploads whose photo is not on this computer (not in app/uploads or img/).
 3. Keeps one upload per photo (same file, or the same photo saved twice) and deletes the extra copies.
 4. Adds photos from img/ that aren't in the app yet (club: Heartlake), skipping copies of photos already there.
 5. Reads every photo again with the AI reader (Gemini), runs the smart checks, and saves after each card.
 6. Writes a report to scorecard_reports/reread_<date-time>.md.
Needs GEMINI_API_KEY in .env. Safe to run again: --skip-done skips cards the AI already read today.
"""
from __future__ import annotations

import argparse
import copy
import io
import json
import logging
import shutil
import sys
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "app"))

IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".heic", ".heif", ".webp"}
DEFAULT_CLUB = "club-heartlake"


def quiet_logs() -> None:
    logging.getLogger().setLevel(logging.WARNING)
    for name in list(logging.root.manager.loggerDict):
        logging.getLogger(name).setLevel(logging.WARNING)


def photo_hash(path: Path) -> str:
    """Average hash of the upright photo (works for HEIC too), to spot the same photo saved twice."""
    try:
        from PIL import Image, ImageOps

        try:
            from pillow_heif import register_heif_opener

            register_heif_opener()
        except Exception:
            pass
        with Image.open(path) as image:
            small = ImageOps.exif_transpose(image).convert("L").resize((17, 16))
            pixels = list(small.get_flattened_data()) if hasattr(small, "get_flattened_data") else list(small.getdata())
    except Exception:
        return ""
    # 16 x 16 "difference hash": 256 bits, robust to resizing / HEIC-to-PNG copies.
    bits = 0
    for row in range(16):
        for col in range(16):
            bits = (bits << 1) | (1 if pixels[row * 17 + col] > pixels[row * 17 + col + 1] else 0)
    return f"{bits:064x}"


def same_photo(a: str, b: str) -> bool:
    if not a or not b:
        return False
    return bin(int(a, 16) ^ int(b, 16)).count("1") <= 20  # same photo: 0-11 bits differ; different cards: 40+


def find_photo(upload: dict, upload_dir: Path, img_dir: Path) -> Path | None:
    for raw in (upload.get("file_path"), upload.get("file_name")):
        name = Path(str(raw or "").replace("\\", "/")).name
        if not name:
            continue
        for folder in (upload_dir, img_dir):
            if (folder / name).is_file():
                return folder / name
    return None


def backup_database(main) -> Path:
    stamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    target = ROOT / "DB-Backup" / f"before_reread_{stamp}"
    target.mkdir(parents=True, exist_ok=True)
    db = Path(main.DATABASE_FILE)
    for suffix in ("", "-wal", "-shm"):
        source = Path(str(db) + suffix)
        if source.is_file():
            shutil.copy2(source, target / source.name)
    return target


def clean_up(main, store: dict, dry_run: bool, report: list[str]) -> list[dict]:
    upload_dir = Path(main.UPLOAD_DIR)
    img_dir = ROOT / "img"
    uploads = store.get("archive_uploads", []) or []
    keep, missing, dupes = [], [], []
    seen_names: dict[str, dict] = {}
    seen_hashes: list[tuple[str, dict]] = []
    # Oldest first, so the first upload of a photo is the one kept.
    for upload in sorted(uploads, key=lambda item: str(item.get("created_at") or "")):
        photo = find_photo(upload, upload_dir, img_dir)
        if not photo:
            missing.append(upload)
            continue
        key = photo.name.lower()
        fingerprint = photo_hash(photo)
        twin = seen_names.get(key) or next((item for h, item in seen_hashes if same_photo(h, fingerprint)), None)
        if twin:
            dupes.append((upload, twin))
            continue
        seen_names[key] = upload
        seen_hashes.append((fingerprint, upload))
        upload["_photo"] = photo
        upload["_hash"] = fingerprint
        keep.append(upload)
    report.append(f"## Clean-up\n\n- Uploads before: {len(uploads)}")
    report.append(f"- Deleted, photo not on this computer: {len(missing)}")
    for upload in missing:
        report.append(f"  - {upload.get('id')} {Path(str(upload.get('file_path') or upload.get('file_name') or '').replace(chr(92), '/')).name}")
    report.append(f"- Deleted, extra copy of the same photo: {len(dupes)}")
    for upload, twin in dupes:
        report.append(f"  - {upload.get('id')} (same photo as {twin.get('id')})")

    # Photos in img/ that aren't in the app yet.
    added = []
    clubs = {str(club.get("id")): club for club in store.get("clubs", []) or []}
    club = clubs.get(DEFAULT_CLUB) or (store.get("clubs") or [{}])[0]
    for path in sorted(img_dir.iterdir()) if img_dir.is_dir() else []:
        if path.suffix.lower() not in IMAGE_SUFFIXES or not path.is_file():
            continue
        if path.name.lower() in seen_names:
            continue
        fingerprint = photo_hash(path)
        twin = next((item for h, item in seen_hashes if same_photo(h, fingerprint)), None)
        if twin:
            report.append(f"  - img/{path.name} skipped: same photo as upload {twin.get('id')}")
            continue
        added.append(path)
        seen_names[path.name.lower()] = {"id": f"img/{path.name}"}
        seen_hashes.append((fingerprint, {"id": f"img/{path.name}"}))
    report.append(f"- Added from img/: {len(added)}")
    for path in added:
        report.append(f"  - {path.name}")

    if dry_run:
        return keep + [{"id": f"(new) {path.name}", "_photo": path, "_new": True} for path in added]

    removed_ids = {str(item.get("id")) for item in missing} | {str(item.get("id")) for item, _ in dupes}
    store["archive_uploads"] = [item for item in uploads if str(item.get("id")) not in removed_ids]
    store["duplicate_uploads"] = [
        item
        for item in store.get("duplicate_uploads", []) or []
        if str(item.get("original_upload_id") or "") not in removed_ids and str(item.get("duplicate_upload_id") or "") not in removed_ids
    ]
    # Photos that only exist in img/ are copied into app/uploads (the app reads photos from there).
    from cricket_store import file_sha256

    for upload in keep:
        photo = upload["_photo"]
        target = upload_dir / photo.name
        if photo.parent != upload_dir and not target.exists():
            shutil.copy2(photo, target)
        # Point every kept upload at its photo in app/uploads (older ones still had Mac paths), so the app
        # doesn't add the same photo again as a new upload.
        upload["_photo"] = target
        upload["file_path"] = str(target)
        upload["file_name"] = target.name
        upload["file_hash"] = file_sha256(target)
        upload["file_size"] = target.stat().st_size
        upload["preview_url"] = f"/uploads/{target.name}"
    for path in added:
        target = upload_dir / path.name
        if not target.exists():
            shutil.copy2(path, target)
        record = main.archive_record_from_file(
            target,
            club.get("season") or store["club"]["season"],
            source="img-folder",
            club_id=str(club.get("id") or ""),
            club_name=str(club.get("name") or ""),
        )
        record["original_file_name"] = path.name
        record["status"] = "Pending review"
        record["uploaded_by"] = "Re-read script (img folder)"
        record["file_path"] = str(target)
        record["_photo"] = target
        record["_new"] = True
        store["archive_uploads"].append(record)
        keep.append(record)
    return keep


def card_problems(record: dict) -> list[str]:
    """What looks wrong in a card the AI read: runs don't add up, wickets don't match the batters out, or the
    other team's name is missing. [] when it looks right (or was never read)."""
    template = record.get("extraction_template")
    if not isinstance(template, dict):
        try:
            template = json.loads(record.get("review_template_json") or "{}")
        except ValueError:
            template = {}
    problems = []
    for inn in template.get("innings") or []:
        if not isinstance(inn, dict):
            continue
        summary = inn.get("summary") or {}
        extras = (inn.get("extras") or {}).get("total") or 0
        batting = inn.get("batting") or []
        bat_sum = sum((row.get("runs") or 0) for row in batting if isinstance(row, dict))
        outs = sum(
            1 for row in batting if isinstance(row, dict)
            and str((row.get("dismissal") or {}).get("type") or "").lower() not in ("", "not out", "not_out", "retired hurt", "did not bat", "dnb", "none")
        )
        if isinstance(summary.get("runs"), int) and summary["runs"] != bat_sum + extras:
            problems.append(f"runs add to {bat_sum + extras}, total {summary['runs']}")
        if isinstance(summary.get("wickets"), int) and outs and summary["wickets"] != outs:
            problems.append(f"{outs} out, {summary['wickets']} wickets")
    teams = (template.get("match") or {}).get("teams") or {}
    if not teams.get("team_2") or any("opponent" in str(name).lower() for name in teams.values()):
        problems.append("other team missing")
    return problems


def reread(main, store: dict, records: list[dict], args, report: list[str], progress=None) -> bool:
    """Returns True when it stopped early because the AI wasn't answering."""
    say = progress or (lambda info: None)
    from scorecard_checks import image_fingerprint

    report.append(f"\n## Re-read with AI ({main.ai_vision.provider() or 'no AI set up'})\n")
    report.append("| # | Upload | Photo | Read | Match | Date | Score | Checks |")
    report.append("|---|---|---|---|---|---|---|---|")
    clubs = {str(club.get("id")): club for club in store.get("clubs", []) or []}
    total = len(records)
    stuck = 0
    for number, (record, photo, is_new) in enumerate(records, 1):
        # Never overwrite a person's work: published cards and cards typed in / fixed with Edit are kept (Oct 27).
        status = str(record.get("status") or "").lower()
        typed = str(record.get("ocr_engine") or "") in {"manual-entry", "manual-import"} or '"manual-entry"' in str(record.get("review_template_json") or "")
        if status in {"approved", "applied to match"} or typed:
            print(f"[{number}/{total}] {record.get('id')} published or fixed by a person - kept")
            continue
        if getattr(args, "only_problems", False) and not card_problems(record):
            print(f"[{number}/{total}] {record.get('id')} adds up - skipped")
            continue
        if args.skip_done and f"reader {main.ai_vision.READER_VERSION}" in str(record.get("ocr_pipeline") or ""):
            print(f"[{number}/{total}] {record.get('id')} already re-read - skipped")
            continue
        club = clubs.get(str(record.get("club_id") or "")) or clubs.get(DEFAULT_CLUB) or {}
        print(f"[{number}/{total}] Reading {Path(str(photo)).name} ...", end=" ", flush=True)
        say({"stage": "reading", "number": number, "total": total, "file": Path(str(photo)).name, "message": f"Reading {number} of {total}: {Path(str(photo)).name}"})
        started = time.time()
        try:
            if not record.get("image_fingerprint"):
                record["image_fingerprint"] = image_fingerprint(Path(photo).read_bytes())
            before = copy.deepcopy(record)
            old_problems = card_problems(before) if str(before.get("ocr_engine") or "").startswith("ai:") else None
            reason = main._scorecard_ai_read(store, record, Path(photo), club)
            # Never make a card worse: if the new reading has more problems than the earlier AI reading,
            # keep the earlier one (Gemini can read the same photo a little differently each time).
            if not reason and old_problems is not None and len(card_problems(record)) > len(old_problems):
                record.clear()
                record.update(before)
                print("(earlier reading was better - kept it)", end=" ")
                report.append(f"| {number} | {record.get('id')} | {Path(str(photo)).name} | kept the earlier reading (new one had more problems) | | | | |")
        except Exception as exc:  # keep going with the next card
            reason = f"error: {exc}"
        seconds = round(time.time() - started)
        if reason:
            print(f"not read ({reason}) {seconds}s")
            if any(word in reason.lower() for word in ("couldn't reach", "limit", "busy", "no gemini vision model")):
                stuck += 1
            if stuck >= 2:
                report.append(f"| {number} | {record.get('id')} | {Path(str(photo)).name} | ❌ {reason[:80]} | | | | |")
                main.save_store(store)
                print("\nThe AI isn't answering (busy, no internet, or today's free limit is used up). Stopped here.")
                print("Run again later with:  python scripts\\scorecards_reread_all.py --skip-done")
                report.append("\nStopped early: the AI wasn't answering. Run again tomorrow with --skip-done (or tick the skip box in the Admin Center).")
                return True
            report.append(f"| {number} | {record.get('id')} | {Path(str(photo)).name} | ❌ {reason[:80]} | | | | |")
            main.save_store(store)
            continue
        if is_new:
            # Photos added from img/ start as Heartlake: move them to the club named on the card, if it's another club.
            teams = [main.normalize_name(str(name or "")) for name in ((record.get("extraction_template") or {}).get("match") or {}).get("teams", {}).values()]
            for other in clubs.values():
                names = {main.normalize_name(str(other.get(k) or "")) for k in ("name", "short_name")} - {""}
                if any(team and (team in names or any(n in team for n in names)) for team in teams):
                    if str(other.get("id")) == str(club.get("id")):
                        break
                    if not any(n in team for team in teams for n in {main.normalize_name(str(club.get("name") or ""))} if n):
                        record["club_id"], record["club_name"] = str(other.get("id")), str(other.get("name"))
                        break
        try:
            checks = main._scorecard_upload_checks(store, record)
            card = checks.get("scorecard") or {}
        except Exception as exc:
            checks, card = {"flags": [f"checks failed: {exc}"]}, {}
        stuck = 0
        main.save_store(store)
        score = " · ".join(f"{item.get('team')} {item.get('score')}" for item in card.get("innings") or [])
        flags = "; ".join(str(flag.get("message") if isinstance(flag, dict) else flag) for flag in checks.get("flags") or [])[:160]
        engine = str(record.get("ocr_engine") or "").replace("ai:", "")
        backup = " (Ollama backup - check it)" if "ollama" in str(record.get("ocr_pipeline") or "").lower() else ""
        print(f"done {seconds}s  {card.get('title') or ''}  {score}  [{engine}]{backup}")
        say({"stage": "reading", "number": number, "total": total, "file": Path(str(photo)).name, "done": f"{card.get('title') or ''} {score}{backup}".strip()})
        report.append(f"| {number} | {record.get('id')} | {Path(str(photo)).name} | ✅ {seconds}s {engine}{backup} | {card.get('title') or ''} | {card.get('date') or ''} | {score} | {flags or 'OK'} |")
        time.sleep(args.pause)
    return False


def sample_test(main, args) -> None:
    """Read the 3 sample cards and compare with sample_scorecards/answer_key.json."""
    folder = ROOT / "sample_scorecards"
    key = json.loads((folder / "answer_key.json").read_text(encoding="utf-8"))
    store = main.load_store()
    clubs = {str(club.get("id")): club for club in store.get("clubs", []) or []}
    club = clubs.get(DEFAULT_CLUB) or {}
    lines = ["# AI reader test on the sample scorecards", "", f"Run {datetime.now():%Y-%m-%d %H:%M} with {main.ai_vision.provider()}", ""]
    grand_ok = grand_all = 0
    for file_name, answer in key.items():
        print(f"Reading {file_name} ...", end=" ", flush=True)
        started = time.time()
        result = main.ai_vision.read_scorecard(
            folder / file_name,
            roster=main._club_member_names(store, club),
            club_name=str(club.get("name") or ""),
            known_names=main._ai_known_names(store, club),
            corrections=main._ai_corrections(str(club.get("id") or "")),
            photo_date=answer["date"],
        )
        seconds = round(time.time() - started)
        template = result.get("template")
        if not template:
            print(f"not read: {result.get('error')}")
            lines += [f"## {file_name}", "", f"Not read: {result.get('error')}", ""]
            continue
        inn = (template.get("innings") or [{}])[0]
        got_bat = {main.normalize_name(str((row.get("player") or {}).get("name") or "")): row for row in inn.get("batting") or []}
        got_bowl = {main.normalize_name(str((row.get("player") or {}).get("name") or "")): row for row in inn.get("bowling") or []}
        checks: list[tuple[str, bool, str]] = []
        summary = inn.get("summary") or {}
        want_runs, want_wkts = (int(x) for x in answer["total"].split("/"))
        checks.append(("Total", summary.get("runs") == want_runs and summary.get("wickets") == want_wkts, f"{summary.get('runs')}/{summary.get('wickets')} (should be {answer['total']})"))
        checks.append(("Extras", (inn.get("extras") or {}).get("total") == answer["extras"]["total"], f"{(inn.get('extras') or {}).get('total')} (should be {answer['extras']['total']})"))
        checks.append(("Date", str((template.get("match") or {}).get("date") or "")[:10] == answer["date"], f"{(template.get('match') or {}).get('date')} (should be {answer['date']})"))
        for bat in answer["batting"]:
            if bat["how_out"] == "did not bat":
                continue
            row = got_bat.get(main.normalize_name(bat["name"]))
            if not row:
                checks.append((bat["name"], False, "name not found"))
                continue
            how = str((row.get("dismissal") or {}).get("type") or "").lower()
            ok_runs = row.get("runs") == bat["runs"]
            ok_balls = row.get("balls") == bat["balls"]
            ok_how = bat["how_out"].split()[0] in how or (bat["how_out"] == "retired out" and "retired" in how)
            checks.append((bat["name"], ok_runs and ok_balls and ok_how, f"{row.get('runs')}({row.get('balls')}) {how} - should be {bat['runs']}({bat['balls']}) {bat['how_out']}"))
        for bowl in answer["bowling"]:
            row = got_bowl.get(main.normalize_name(bowl["name"]))
            ok = bool(row) and row.get("wickets") == bowl["wickets"]
            detail = f"{row.get('overs')}-{row.get('maidens')}-{row.get('runs_conceded')}-{row.get('wickets')}" if row else "not found"
            checks.append((f"Bowler {bowl['name']} wickets", ok, f"{detail} - should be {bowl['overs']}-{bowl['maidens']}-{bowl['runs']}-{bowl['wickets']}"))
        ok_count = sum(1 for _, ok, _ in checks if ok)
        grand_ok += ok_count
        grand_all += len(checks)
        print(f"{ok_count}/{len(checks)} right ({seconds}s)")
        lines += [f"## {file_name}: {ok_count}/{len(checks)} right ({seconds}s)", "", "| Check | | What the AI read |", "|---|---|---|"]
        lines += [f"| {name} | {'✅' if ok else '❌'} | {detail} |" for name, ok, detail in checks]
        if result.get("notes"):
            lines += ["", "Notes: " + "; ".join(result["notes"])]
        lines.append("")
        time.sleep(args.pause)
    if grand_all:
        lines.insert(3, f"**Overall: {grand_ok}/{grand_all} right ({round(100 * grand_ok / grand_all)}%)**\n")
        print(f"Overall: {grand_ok}/{grand_all} right ({round(100 * grand_ok / grand_all)}%)")
    out = folder / "AI_TEST_RESULTS.md"
    out.write_text("\n".join(lines), encoding="utf-8")
    print(f"Results saved in {out}")


def main_cli() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dry-run", action="store_true", help="only show what would happen")
    parser.add_argument("--samples", action="store_true", help="test the AI on the 3 sample cards")
    parser.add_argument("--skip-done", action="store_true", help="skip cards already read by the newest AI reader (to continue after the free daily limit)")
    parser.add_argument("--since", default=datetime.utcnow().strftime("%Y-%m-%d"), help="with --skip-done: date YYYY-MM-DD")
    parser.add_argument("--only-problems", action="store_true", help="only re-read cards whose numbers don't add up")
    parser.add_argument("--no-cleanup", action="store_true", help="don't delete or add uploads, only re-read")
    parser.add_argument("--pause", type=float, default=4.0, help="seconds between cards (Gemini free limit)")
    args = parser.parse_args()

    import main as app_main  # noqa: E402  (the app's code; doesn't start the server)

    quiet_logs()
    if not app_main.ai_vision.enabled() and not args.dry_run:
        print("No AI reader is set up. Put GEMINI_API_KEY=... in the .env file, then run this again.")
        sys.exit(1)
    if args.samples:
        sample_test(app_main, args)
        return
    run(app_main, args)


def run(app_main, args, progress=None) -> dict:
    """Clean up (unless args.no_cleanup) and re-read. Used by this script and by the Admin Center button
    (POST /api/admin/scorecards/reread-all). progress(info) is called with what is happening."""
    say = progress or (lambda info: None)
    report = [f"# Scorecard clean-up and re-read", "", f"Run {datetime.now():%Y-%m-%d %H:%M}{' (dry run, nothing changed)' if args.dry_run else ''}", ""]
    if not args.dry_run:
        backup = backup_database(app_main)
        print(f"Database backed up to {backup}")
        report.append(f"Backup: {backup}\n")
    say({"stage": "cleanup", "message": "Cleaning up the uploads..."})
    store = app_main.load_store()
    if getattr(args, "no_cleanup", False):
        upload_dir, img_dir = Path(app_main.UPLOAD_DIR), ROOT / "img"
        records = []
        for upload in store.get("archive_uploads", []) or []:
            photo = find_photo(upload, upload_dir, img_dir)
            if photo and photo.parent == upload_dir:
                upload["_photo"] = photo
                records.append(upload)
        report.append(f"## Clean-up\n\n- Skipped (re-read only). Uploads with a photo: {len(records)}")
    else:
        records = clean_up(app_main, store, args.dry_run, report)
    print("\n".join(line for line in report if line.lstrip().startswith("-")))
    if args.dry_run:
        print(f"\nDry run: {len(records)} photos would be read with AI. Nothing was changed.")
        return {"records": len(records), "report": "\n".join(report)}
    # Remember which photo each upload uses, then drop the helper keys before saving.
    plan = [(str(record.get("id")), record.get("_photo"), bool(record.get("_new"))) for record in records]
    for item in store.get("archive_uploads", []) or []:
        for key in ("_photo", "_hash", "_new"):
            item.pop(key, None)
    app_main.save_store(store)
    store = app_main.load_store()
    by_id = {str(item.get("id")): item for item in store.get("archive_uploads", []) or []}
    fresh = []
    for record_id, photo, is_new in plan:
        item = by_id.get(record_id)
        if item is not None and photo and Path(photo).is_file():
            fresh.append((item, Path(photo), is_new))
    print(f"\nReading {len(fresh)} photos with AI. This takes a while (about half a minute each). Keep this window open.\n")
    say({"stage": "reading", "number": 0, "total": len(fresh), "message": f"Reading {len(fresh)} photos with AI..."})
    stopped = reread(app_main, store, fresh, args, report, progress=say)
    out_dir = ROOT / "scorecard_reports"
    out_dir.mkdir(exist_ok=True)
    out = out_dir / f"reread_{datetime.now():%Y-%m-%d_%H%M}.md"
    out.write_text("\n".join(report), encoding="utf-8")
    print(f"\nDone. Report saved in {out}")
    return {"records": len(fresh), "report_path": str(out), "stopped": bool(stopped)}

if __name__ == "__main__":
    main_cli()
