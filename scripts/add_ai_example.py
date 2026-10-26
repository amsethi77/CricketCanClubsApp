"""Add a checked scorecard as a worked example for the AI reader ("training" that is committed to git).

README: "How the AI reader learns" -> "Worked examples" (Oct 27 2026).

Only use a card whose numbers a person checked against the photo digit by digit (fix it with Edit first).
Run from the project folder:

    python scripts\\add_ai_example.py <upload id> "lesson one" "lesson two"

It copies a smaller copy of the photo and the card's current JSON into app/ai_examples/ and adds it to
app/ai_examples/examples.json. Commit app/ai_examples/ to git so every copy of the app (local, Azure) reads
scorecards with the same examples. Keep 2-3 examples: each one is sent with every read.
"""
from __future__ import annotations

import json
import sqlite3
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EXAMPLES = ROOT / "app" / "ai_examples"
DB = ROOT / "app" / "data" / "cricketclubapp.db"


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 1
    upload_id, lessons = sys.argv[1], sys.argv[2:]
    con = sqlite3.connect(DB)
    row = con.execute("select file_name, file_path, review_template_json from archives where id = ?", (upload_id,)).fetchone()
    if not row:
        print(f"No upload with id {upload_id}.")
        return 1
    file_name, file_path, template_json = row
    photo = Path(file_path or "")
    if not photo.is_file():
        photo = ROOT / "app" / "uploads" / str(file_name)
    if not photo.is_file():
        print(f"Photo not found: {file_path}")
        return 1
    from PIL import Image, ImageOps
    try:
        from pillow_heif import register_heif_opener

        register_heif_opener()
    except Exception:
        pass
    index_path = EXAMPLES / "examples.json"
    index = json.loads(index_path.read_text(encoding="utf-8")) if index_path.exists() else {"examples": []}
    number = len(index["examples"]) + 1
    while (EXAMPLES / f"example_{number}.jpg").exists():
        number += 1
    EXAMPLES.mkdir(parents=True, exist_ok=True)
    image = ImageOps.exif_transpose(Image.open(photo)).convert("RGB")
    image.thumbnail((2048, 2048))
    image.save(EXAMPLES / f"example_{number}.jpg", quality=80)
    template = json.loads(template_json or "{}")
    template.setdefault("meta", {})["source"] = "checked-example"
    (EXAMPLES / f"example_{number}.json").write_text(json.dumps(template, indent=1), encoding="utf-8")
    index["examples"].append({
        "photo": f"example_{number}.jpg",
        "answer": f"example_{number}.json",
        "source_file": str(file_name),
        "checked_by": f"added {date.today().isoformat()}",
        "lessons": lessons,
    })
    index_path.write_text(json.dumps(index, indent=1), encoding="utf-8")
    print(f"Added example_{number} from {file_name}. Commit app/ai_examples/ to git.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
