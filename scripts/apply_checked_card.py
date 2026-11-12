"""Put a checked scorecard (JSON) onto an uploaded card, the same as saving it with ✏️ Edit (Nov 11 2026).

    python scripts\\apply_checked_card.py <upload id> <checked json file>

The card keeps its status (a published card stays published), counts as typed in by a person (so the accuracy test
uses it as the right answer) and becomes a learned example for the AI reader. README "How the AI reader learns".
"""
from __future__ import annotations

import json
import os
import sys
from copy import deepcopy
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "app"))
os.chdir(ROOT)


def main() -> int:
    if len(sys.argv) != 3:
        print(__doc__)
        return 1
    import logging

    import main as app

    logging.getLogger().setLevel(logging.WARNING)
    for name in list(logging.root.manager.loggerDict):
        logging.getLogger(name).setLevel(logging.WARNING)
    upload_id, file_name = sys.argv[1].removeprefix("a-"), sys.argv[2]
    template = json.loads(Path(file_name).read_text(encoding="utf-8"))
    store = app.load_store()
    upload = app.get_archive_or_404(store, upload_id)
    status = upload.get("status")
    imported = app.parse_imported_extraction(store, json.dumps(template))
    upload.update(imported)
    upload["extraction_template"] = deepcopy(template)
    upload["review_template_json"] = json.dumps(template, indent=2)
    upload["review_source_json"] = json.dumps(template)[:12000]
    upload["ocr_engine"] = "manual-entry"
    upload["ocr_processed_at"] = app.now_iso()
    upload["status"] = status
    upload["review_flags"] = []
    app.save_store(store)
    path = app._upload_file_path(upload)
    taught = False
    if path is not None:
        teams = [str(value or "") for value in ((template.get("match") or {}).get("teams") or {}).values()]
        taught = app.ai_vision.save_learned_example(upload_id, path, template, [str(upload.get("club_name") or ""), *teams])
    card = app._scorecard_from_archive(app.get_archive_or_404(app.load_store(), upload_id))
    print(f"Saved {upload_id}: {card.get('title')} | {card.get('result')}")
    for innings in card.get("innings") or []:
        print(f"  {innings.get('team')}: {innings.get('score')} ({innings.get('overs')} ov), {len(innings.get('batting') or [])} batters")
    print("Kept as a learned example for the AI." if taught else "Not kept as an example (photo missing or the card doesn't add up).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
