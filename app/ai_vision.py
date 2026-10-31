"""
Read a scorecard photo (including handwritten paper scorecards) with an AI vision model.

Providers, first one configured wins:
  1. Google Gemini  - GEMINI_API_KEY (free tier from https://aistudio.google.com/apikey, no card needed;
                      free-tier requests may be used by Google to improve its products).
                      Optional GEMINI_VISION_MODEL (default gemini-3.8-flash).
  2. Anthropic Claude - ANTHROPIC_API_KEY (paid per photo). Optional ANTHROPIC_VISION_MODEL.
  3. Ollama on this computer - free and offline. Install Ollama, then `ollama pull qwen3-vl:8b`
                      (or set OLLAMA_VISION_MODEL). Found automatically while the Ollama app runs.
With none of these the upload uses Tesseract (can't read handwriting) and the "Type in the scorecard" form.

Used by POST /api/scorecards/upload and POST /api/scorecards/{id}/ai-read in app/main.py.
Documented in MD/README.md -> "Reading handwritten scorecards automatically".

Switched OFF until ANTHROPIC_API_KEY is set (in .env next to the app folder, or as an environment
variable). Optional: ANTHROPIC_VISION_MODEL (default claude-sonnet-5-5). Each photo is one API call,
roughly 3-6 thousand tokens (a few US cents with Sonnet).

The model returns the app's scorecard template JSON (meta / match / innings / validation), the same
shape as a typed-in scorecard, so the normal import, digital scorecard and checks all work unchanged.
When the key is missing or the call fails, the upload falls back to the local reader (Ollama vision
model if installed, else Tesseract) and the "Type in the scorecard" form.
"""

from __future__ import annotations

import base64
import contextvars
import datetime as _dt
import difflib
import io
import json
import logging
import re
from pathlib import Path
from typing import Any

import httpx

try:
    from . import subscriptions  # type: ignore
except ImportError:  # running as a script from app/
    import subscriptions  # type: ignore

logger = logging.getLogger("CricketClubApp.ai_vision")

DEFAULT_BASE_URL = "https://api.anthropic.com"
DEFAULT_MODEL = "claude-sonnet-5-5"
MAX_EDGE = 1568  # the API scales larger images down to about this anyway


GEMINI_DEFAULT_MODEL = "gemini-3.8-flash"
GEMINI_FALLBACK_MODELS = ("gemini-3.6-flash", "gemini-3-flash-preview", "gemini-3.5-flash-lite")
# Scorecard photos are never read with the "lite" model: in the Oct 22 re-read it got extras and totals wrong
# (e.g. extras 52 instead of 43). When the better models hit today's free limit, reading stops and is tried
# again later instead (README "How the AI reader learns").
GEMINI_SCORECARD_MODELS = ("gemini-3.8-flash", "gemini-3.6-flash", "gemini-3-flash-preview")
# Bump when the reading instructions/checks change, so "Re-read all" can skip cards the newest reader already read.
READER_VERSION = "2026-10-27"


def api_key() -> str:
    return subscriptions.setting("ANTHROPIC_API_KEY")


def gemini_key() -> str:
    return subscriptions.setting("GEMINI_API_KEY") or subscriptions.setting("GOOGLE_API_KEY")


def model_name() -> str:
    return subscriptions.setting("ANTHROPIC_VISION_MODEL", DEFAULT_MODEL)


# Free and offline: a vision model in Ollama on this computer (e.g. `ollama pull qwen3-vl:8b`).
OLLAMA_VISION_MODELS = (
    "qwen3-vl:8b", "qwen3-vl:latest", "qwen3-vl", "qwen3-vl:4b", "qwen2.5vl:7b", "qwen2.5vl:latest",
    "qwen2.5vl", "llama3.2-vision:latest", "llama3.2-vision", "minicpm-v:latest", "llava:latest",
    # Gemma 4: Google's free offline model family (Gemini's open sibling), reads images. e4b fits a laptop.
    "gemma4:e4b", "gemma4:latest", "gemma4", "gemma4:e2b", "gemma4:26b",
)
_OLLAMA_CACHE: dict[str, Any] = {"at": 0.0, "model": ""}


def ollama_base_url() -> str:
    return (subscriptions.setting("OLLAMA_BASE_URL") or "http://127.0.0.1:11434").rstrip("/")


def ollama_model() -> str:
    """The Ollama vision model to use ('' when Ollama isn't running or has no vision model). Cached 60 s."""
    import time

    if time.time() - _OLLAMA_CACHE["at"] < 60:
        return _OLLAMA_CACHE["model"]
    model = ""
    try:
        tags = httpx.get(f"{ollama_base_url()}/api/tags", timeout=2.0).json().get("models") or []
        names = [str(item.get("name") or "") for item in tags]
        configured = subscriptions.setting("OLLAMA_VISION_MODEL")
        if configured and configured in names:
            model = configured
        else:
            model = next((name for name in OLLAMA_VISION_MODELS if name in names), "")
    except Exception:
        model = ""
    _OLLAMA_CACHE.update({"at": time.time(), "model": model})
    return model


def provider() -> str:
    if gemini_key():
        return "gemini"
    if api_key():
        return "claude"
    if ollama_model():
        return "ollama"
    return ""


def enabled() -> bool:
    return bool(provider())


# What the short form "RO" means on a club's paper scorecards. Club scorers often write "RO" for
# RETIRED OUT (batters retire at a set score), not run out. Set SCORECARD_RO_MEANS=run out in .env to change.
RO_FORMS = {"ro", "r.o", "r.o.", "r/o", "r o"}


def ro_meaning() -> str:
    value = (subscriptions.setting("SCORECARD_RO_MEANS") or "").strip().lower().replace("_", " ")
    return "run out" if value == "run out" else "retired out"


def is_ro(text: Any) -> bool:
    return str(text or "").strip().lower() in RO_FORMS


def _zoomed_halves(path: Path, max_edge: int = 3072) -> list[tuple[str, str]]:
    """Top and bottom half of the photo at higher resolution (JPEG, base64), so small handwriting in the batting
    table and the bowling boxes is sharper than in the whole-page image. [] if the photo can't be opened."""
    try:
        from PIL import Image, ImageOps

        try:
            from pillow_heif import register_heif_opener

            register_heif_opener()
        except Exception:
            pass
        out = []
        with Image.open(path) as image:
            image = ImageOps.exif_transpose(image).convert("RGB")
            width, height = image.size
            if max(width, height) <= MAX_EDGE * 1.2:
                return []  # small photo: the whole-page image is already full size
            for box in ((0, 0, width, int(height * 0.56)), (0, int(height * 0.44), width, height)):
                part = image.crop(box)
                part.thumbnail((max_edge, max_edge))
                buffer = io.BytesIO()
                part.save(buffer, format="JPEG", quality=88)
                out.append(("image/jpeg", base64.b64encode(buffer.getvalue()).decode("ascii")))
        return out
    except Exception:
        return []


def _image_payload(path: Path) -> tuple[str, str]:
    """(media_type, base64 data) — phone photos (HEIC, rotated, huge) become an upright JPEG."""
    try:
        from PIL import Image, ImageOps

        try:
            from pillow_heif import register_heif_opener

            register_heif_opener()
        except Exception:
            pass
        with Image.open(path) as image:
            image = ImageOps.exif_transpose(image).convert("RGB")
            image.thumbnail((MAX_EDGE, MAX_EDGE))
            buffer = io.BytesIO()
            image.save(buffer, format="JPEG", quality=90)
            return "image/jpeg", base64.b64encode(buffer.getvalue()).decode("ascii")
    except Exception:
        suffix = path.suffix.lower()
        media = {".png": "image/png", ".webp": "image/webp", ".gif": "image/gif"}.get(suffix, "image/jpeg")
        return media, base64.b64encode(path.read_bytes()).decode("ascii")


PROMPT = """You are reading a photo of a cricket scorecard (often a handwritten paper scoring book page).
Copy what is written into JSON. Accuracy matters more than completeness.

How a paper scorecard is laid out:
- "PLAYED BETWEEN ... AND ..." gives the two teams; "DAY & DATE" the date; "VENUE"; "INNINGS OF" says who batted.
- Each batting row: batter name, the ball-by-ball scribbles (1 4 . 2 6 ...), then HOW OUT, BOWLER and the TOTAL column.
  ROWS: HOW OUT, BOWLER and TOTAL belong to the batter on the SAME printed row (row numbers 1-11 are printed on the
  left). Count the rows; never shift a value up or down to the batter above or below. An empty BOWLER cell = null.
  A circled number next to a name is a shirt number, not runs. A circled number written alone in the BOWLER column
  (e.g. "(12)") means the bowler wearing that number: find the same circled number beside a name in the bowling
  list and use that name.
  Use the TOTAL column for runs (in some books it is called RUNS or TOTAL RUNS, at the right end of the row).
  If a number is written there it wins, even if the ball-by-ball looks different. Only if it is empty, add up
  that batter's ball-by-ball runs.
  Marks drawn after the ball-by-ball like "7", "77", ">", ">>" or a long line are TICKS (end of innings / spare
  balls), NOT runs - never add them. A "7" that is part of the ball-by-ball is a 7 only if it stands alone
  among other single digits.
  A number at the very bottom of the TOTAL column is usually the batters' runs added up (no extras): the
  grand total is the TOTAL SCORE / G. TOTAL box, or that number plus the extras.
  The TOTAL column is often written as RUNS(BALLS): "34(42)" = 34 runs off 42 balls, "4(17)" = 4 runs off 17 balls.
  Put the number in brackets in "balls". Read bracket digits as carefully as the runs (1 and 7, 2 and 7 look alike).
- HOW OUT words: caught / c, bowled / b, LBW, run out, stumped / st, not out / NO, retired out, retired hurt,
  did not bat (a name with nothing written). Put the dismissal type in "type" and the bowler's name in "bowler".
- Caught and bowled: "c & b SINGH", "c&b Singh", "ct & b", "C+B", "caught & bowled" all mean the bowler took the
  catch himself. Write type "caught and bowled" with BOTH "fielder" and "bowler" = that bowler's name. Never write
  "caught" with the fielder missing when the card says "& b".
- Printed / typed scorecards (a table with Batter, How out, R, B, 4s, 6s, SR): copy every number exactly as printed.
  The How out text gives the parts: "c Shah b Khan" = caught, fielder Shah, bowler Khan; "b Patel" = bowled, bowler
  Patel; "lbw b Khan" = lbw, bowler Khan; "st Rao b Gill" = stumped, fielder Rao, bowler Gill; "run out (Ali)" =
  run out, fielder Ali, NO bowler; "hit wicket b X" = hit wicket, bowler X; "not out"; "retired hurt". Put the
  4s and 6s in "fours" / "sixes" and the B column in "balls". "Did not bat:" names go in batting with type "did not
  bat" and runs null. Copy the bowling table (O M R W) row by row, and every extras part (b, lb, w, nb).
- In HOW OUT, "RO" (or "R.O.", "R/O") on this club's cards means "{ro}" - write "{ro}" for it.
  Always also copy exactly what is written in HOW OUT into "written_as" (e.g. "RO", "Retired out", "LBW").
- Grand total: the "G. TOTAL" box, a circled number, or the last value in the running score column.
  Wickets = batters who are out (retired out counts; not out / retired hurt / did not bat don't).
- Extras: copy what is written in the BYES / LEG BYES / WIDES / NO BALLS / PENALTY boxes. Each box often holds a
  TALLY - one digit per extra ball, e.g. WIDES "1112111" = 8 - and a circled number at its end that is the box's
  total: use the circled number when there is one, else add up the tally digits. Write that total in the field and
  the tally exactly as written in "written_as". Extras total = the TOTAL EXTRAS box, or else the sum of the boxes. NEVER change extras just to make the sum work: if batters +
  extras don't equal the grand total, one of the batters' TOTAL numbers is probably misread - look again
  (3 and 8, 1 and 7, 0 and 6 are easily confused). Only if no extras boxes are filled in at all may you use
  extras = grand total minus the batters' runs.
- The bowling analysis lists the other team's bowlers (every row with marks, even if the name is only a circled
  shirt number or a nickname - use what is written). If the BOWLING SUMMARY columns (overs / maidens / runs /
  wickets) are filled in, copy them. If they are empty, work them out from the BOWLING ANALYSIS boxes: each box with
  marks in it is one over (so overs = number of used boxes; all bowlers' overs add up to the innings' overs).
  A small circled number in the corner of a box is that bowler's running total of runs conceded: the last one is
  his runs. If there are no circled totals, runs = every digit in the box, dots = 0, plus wides and no balls.
  Wickets in the boxes are written as CT / C, B / BOW, LB / LBW, ST, or a W next to such a word. A plain "W" or
  "w2" in a box is often a WIDE on these cards, not a wicket - so take wickets from the batting BOWLER column
  (caught, bowled, LBW, stumped, hit wicket - not run out or retired) and make the boxes agree with it.
  Use null for any number you can't work out - never guess.
- A page usually holds ONE innings. Only add a second innings if it is really on the photo.

Double-checking (important):
- Before you answer, check the card against itself and look again at anything that doesn't fit:
  batters' runs + extras = total; bowlers' runs add up to the total minus byes and leg byes; bowlers' overs add up to
  the innings overs; each bowler's wickets = the batters out "b / c ... b / lbw / st / hit wicket" to him; 4s x 4 +
  6s x 6 is never more than a batter's runs; wickets = batters out.
- For every batter also add up the runs in their ball-by-ball scribbles (dots = 0, | = 1) and put it in
  "ball_runs_sum" (null if you can't read them). It should match the TOTAL column; if it doesn't, look at both again.
- Also count that batter's deliveries in the scribbles (every dot, digit and W is one ball; ignore crossed-out lines)
  and put it in "ball_count". It should match the balls in brackets; if not, look at the brackets again.
- Dates: read the year digit by digit (0 and 6, 1 and 7 look alike). Write the date as YYYY-MM-DD.
- Set "unsure": true on any batter (or on extras) where a digit is hard to read, so a person checks it.

Rules:
- Never invent names or numbers. If you can't read something, use null. Spell names as written (fix obvious
  letter mix-ups only, e.g. "SARABJEET").
- Read each name letter by letter, especially the first letter. In handwritten capitals H and M, K and R, U and V,
  I and L, S and 5, O and D look alike: H has two straight sides and one bar, M has a pointed middle. Prefer the
  spelling that is a common first name or surname (e.g. "HESHAD", not "MESHAD").
- Known players of this club (use these spellings when a written name clearly matches one): {roster}
- Club that uploaded the photo: {club}. When the card names this club in any spelling (e.g. "HEART LAKE"), write
  it exactly as "{club}". If the other team's name isn't written, use null for it - never put this club twice.

Reply with ONLY this JSON, no other text:
{{
  "meta": {{"source": "claude-vision", "confidence": "high|medium|low", "status": "template"}},
  "match": {{"match_type": "club", "date": "YYYY-MM-DD or null", "venue": null, "teams": {{"team_1": "team batting first", "team_2": "other team"}}, "overs_limit": null}},
  "innings": [
    {{
      "inning_number": 1,
      "batting_team": "...", "bowling_team": "...",
      "summary": {{"runs": 0, "wickets": 0, "overs": null, "balls": null}},
      "batting": [{{"player": {{"name": "..."}}, "runs": 0, "balls": null, "fours": null, "sixes": null, "dismissal": {{"type": "caught", "fielder": null, "bowler": "...", "written_as": "CAUGHT"}}, "ball_runs_sum": null, "ball_count": null, "unsure": false}}],
      "bowling": [{{"player": {{"name": "..."}}, "overs": null, "maidens": null, "runs_conceded": null, "wickets": null}}],
      "extras": {{"wides": null, "no_balls": null, "byes": null, "leg_byes": null, "penalties": null, "total": 0, "written_as": "exactly what is written in the extras boxes, e.g. 'W 52'", "unsure": false}}
    }}
  ],
  "validation": {{"inning_1_total": 0, "inning_2_total": null, "expected_result": "", "notes": "anything you were unsure about"}}
}}"""


# ---------------------------------------------------------------------------
# "Training" from the club's own data (README "How the AI reader learns"):
#   - known names: roster + aliases + players on the club's earlier scorecards + names corrected before,
#   - corrections: wrong -> right names the club fixed with Edit (learned in app/main.py),
#   - photo date: when the photo was taken / uploaded, so the year isn't misread.
# Passed by read_scorecard(); the read_* functions build the prompt with _prompt().
# ---------------------------------------------------------------------------
_HINTS: contextvars.ContextVar[dict[str, Any]] = contextvars.ContextVar("scorecard_hints", default={})

# Worked examples: real scorecard photos that a person checked digit by digit, with the right answer. They are sent
# with every Gemini / Claude read ("here is a card and how to read it, now read this one") - this is how the reader
# is trained, and because the files are in git every copy of the app (local, Azure) gets the same training.
# Add one with: python scripts/add_ai_example.py <upload id>  (README "How the AI reader learns" -> "Worked examples").
EXAMPLES_DIR = Path(__file__).resolve().parent / "ai_examples"
_EXAMPLES_CACHE: dict[str, Any] = {}


def worked_examples(skip_photo: Path | None = None) -> list[dict[str, Any]]:
    """[{"name", "media_type", "data", "answer" (JSON text), "lessons"}] from app/ai_examples/examples.json.
    The photo being read is skipped if it is one of the examples (it would just copy the answer)."""
    index = EXAMPLES_DIR / "examples.json"
    if not index.exists():
        return []
    try:
        stamp = index.stat().st_mtime
        if _EXAMPLES_CACHE.get("stamp") != stamp:
            items = []
            for entry in json.loads(index.read_text(encoding="utf-8")).get("examples") or []:
                photo = EXAMPLES_DIR / str(entry.get("photo") or "")
                answer = EXAMPLES_DIR / str(entry.get("answer") or "")
                if not photo.is_file() or not answer.is_file():
                    continue
                media = "image/png" if photo.suffix.lower() == ".png" else "image/jpeg"
                items.append({
                    "name": photo.name,
                    "source_file": str(entry.get("source_file") or ""),
                    "media_type": media,
                    "data": base64.b64encode(photo.read_bytes()).decode("ascii"),
                    "answer": json.dumps(json.loads(answer.read_text(encoding="utf-8"))),
                    "lessons": [str(x) for x in entry.get("lessons") or []],
                })
            _EXAMPLES_CACHE.update({"stamp": stamp, "items": items})
        items = list(_EXAMPLES_CACHE.get("items") or [])
    except Exception as exc:  # a broken example must never stop reading
        logger.warning("AI worked examples not loaded: %s", exc)
        return []
    if skip_photo is not None:
        own = Path(skip_photo).name.lower()
        items = [item for item in items if own not in {item["name"].lower(), item["source_file"].lower()}]
    limit = subscriptions.setting("AI_WORKED_EXAMPLES", "3").strip()
    return items[: int(limit) if limit.isdigit() else 3]


def _example_intro(example: dict[str, Any]) -> str:
    lessons = "".join(f"\n- {lesson}" for lesson in example.get("lessons") or [])
    return (
        "WORKED EXAMPLE (a different scorecard, already checked by a person). Study how it was read, then read the "
        "new photo the same way. Do not copy its names or numbers into the new card."
        + (f"\nWhat this example teaches:{lessons}" if lessons else "")
    )


def _prompt(roster: list[str] | None, club_name: str) -> str:
    hints = _HINTS.get() or {}
    text = PROMPT.format(roster=", ".join((roster or [])[:120]) or "(none)", club=club_name or "(unknown)", ro=ro_meaning())
    extra: list[str] = []
    photo_date = str(hints.get("photo_date") or "")[:10]
    if photo_date:
        extra.append(
            f"- The photo was taken/uploaded on {photo_date}. The match was played on or before that day, usually within "
            f"a few days. If a digit of the year is hard to read it is most likely {photo_date[:4]}. Never give a date after {photo_date}."
        )
    corrections = hints.get("corrections") or {}
    if corrections:
        pairs = "; ".join(f'"{wrong}" is really "{right}"' for wrong, right in list(corrections.items())[:60])
        extra.append(f"- Names this club corrected on earlier cards (use the corrected spelling): {pairs}.")
    known = [name for name in hints.get("known_names") or [] if name not in (roster or [])]
    if known:
        extra.append("- Other players seen on this club's scorecards (opponents too): " + ", ".join(known[:150]) + ".")
    if not extra:
        return text
    return text + "\n\nExtra help for this club:\n" + "\n".join(extra)


def _all_known_names(roster: list[str] | None) -> list[str]:
    hints = _HINTS.get() or {}
    names = list(roster or []) + list(hints.get("known_names") or []) + list((hints.get("corrections") or {}).values())
    seen: dict[str, str] = {}
    for name in names:
        clean = " ".join(str(name or "").split())
        if len(clean) >= 3 and clean.lower() not in seen:
            seen[clean.lower()] = clean
    return list(seen.values())


def _apply_learning(template: dict[str, Any], roster: list[str] | None) -> list[str]:
    """Fix names with the club's earlier corrections and near-miss known names; check the date against the
    photo date and balls against the ball-by-ball count. Returns notes for the person checking."""
    hints = _HINTS.get() or {}
    notes: list[str] = []
    corrections = {str(k).strip().lower(): str(v).strip() for k, v in (hints.get("corrections") or {}).items() if str(v).strip()}
    known = _all_known_names(roster)
    known_lower = {name.lower(): name for name in known}

    def fix(name: Any) -> Any:
        text = " ".join(str(name or "").split())
        if not text:
            return name
        low = text.lower()
        if low in corrections:
            if corrections[low] != text:
                notes.append(f"'{text}' was changed to '{corrections[low]}' (corrected on an earlier card).")
            return corrections[low]
        if low in known_lower or len(low) < 5:
            return text
        # Only fix a clear one-letter-ish misread of ONE known player (e.g. MESHAD -> Heshad, DILLON -> Dhillon).
        # A first name shared by several players ("AMIT": Amit S / Amit G) or a different real name
        # ("Simran" is not "Imran") is left as written (README "How the AI reader learns").
        if sum(1 for name in known_lower if name.split()[0] == low or name.startswith(low + " ")) > 0:
            return text
        scored = sorted(((difflib.SequenceMatcher(None, low, name).ratio(), name) for name in known_lower), reverse=True)
        if not scored:
            return text
        best_ratio, best = scored[0]
        second = scored[1][0] if len(scored) > 1 else 0.0
        # One letter added/dropped keeps the first letter (DILLON/Dhillon, Kiron/Kirron); a misread first letter
        # keeps the length (MESHAD/Heshad). "Simran" vs "Imran" is neither, so it stays.
        close_shape = (len(best) == len(low)) or (abs(len(best) - len(low)) == 1 and best[:1] == low[:1] and best_ratio >= 0.9)
        if best_ratio >= 0.83 and close_shape and best_ratio - second >= 0.1:
            notes.append(f"'{text}' was read; changed to the known player '{known_lower[best]}'. Check it against the photo.")
            return known_lower[best]
        return text

    club_key = _team_key(hints.get("club_name") or "")

    def ours(team: Any) -> bool:
        key = _team_key(team)
        return bool(club_key and key and (club_key in key or key in club_key))

    for inn in template.get("innings") or []:
        if not isinstance(inn, dict):
            continue
        # Our players' names are only matched on our side: our batters when we bat, our bowlers and fielders
        # when we bowl. The other team's "DILLON" is not our Dhillon. (Corrections people made apply everywhere.)
        bat_ours = ours(inn.get("batting_team")) or not club_key
        bowl_ours = ours(inn.get("bowling_team")) or not club_key

        def fix_side(name: Any, our_side: bool) -> Any:
            low = " ".join(str(name or "").split()).lower()
            if our_side or low in corrections:
                return fix(name)
            return name

        for rows, our_side in ((inn.get("batting") or [], bat_ours), (inn.get("bowling") or [], bowl_ours)):
            for row in rows:
                if isinstance(row, dict) and isinstance(row.get("player"), dict) and row["player"].get("name"):
                    fixed = fix_side(row["player"]["name"], our_side)
                    if fixed != row["player"]["name"]:
                        row["player"]["name"] = fixed
                        row["player"]["normalized_name"] = str(fixed).lower()
        for row in inn.get("batting") or []:
            dismissal = row.get("dismissal") if isinstance(row, dict) and isinstance(row.get("dismissal"), dict) else None
            if dismissal:
                for key in ("bowler", "fielder"):
                    if dismissal.get(key):
                        dismissal[key] = fix_side(dismissal[key], bowl_ours)
            # TOTAL column left empty on the card: use the batter's ball-by-ball runs.
            if isinstance(row, dict) and row.get("runs") in (None, 0) and isinstance(row.get("ball_runs_sum"), int) and row["ball_runs_sum"] > 0:
                notes.append(f"{(row.get('player') or {}).get('name')}'s TOTAL was empty; used the ball-by-ball runs ({row['ball_runs_sum']}). Check it.")
                row["runs"] = row["ball_runs_sum"]

    # Balls and bowlers' wickets from what is already on the card (no guessing):
    #  - a batter with no balls in brackets gets the ball-by-ball count,
    #  - a bowler with no wickets gets the dismissals credited to them in the batting BOWLER column.
    credited = ("caught", "bowled", "lbw", "stumped", "hit wicket", "c ", "b ", "st ")
    for inn in template.get("innings") or []:
        if not isinstance(inn, dict):
            continue
        wickets: dict[str, int] = {}
        for row in inn.get("batting") or []:
            if not isinstance(row, dict):
                continue
            count = row.get("ball_count")
            if row.get("balls") in (None, "", 0) and isinstance(count, int) and count > 0:
                row["balls"] = count
            dismissal = row.get("dismissal") if isinstance(row.get("dismissal"), dict) else {}
            kind = str(dismissal.get("type") or "").strip().lower()
            bowler = " ".join(str(dismissal.get("bowler") or "").split()).lower()
            if bowler and (kind.startswith(credited) or kind in {"c", "b", "st"}) and "run" not in kind and "retired" not in kind:
                wickets[bowler] = wickets.get(bowler, 0) + 1
        for row in inn.get("bowling") or []:
            if not isinstance(row, dict) or not isinstance(row.get("player"), dict):
                continue
            name = " ".join(str(row["player"].get("name") or "").split()).lower()
            found = wickets.get(name)
            if found is None:
                continue
            if row.get("wickets") in (None, ""):
                row["wickets"] = found
            elif isinstance(row.get("wickets"), int) and row["wickets"] != found:
                notes.append(f"Check {row['player'].get('name')}'s wickets: the bowling figures say {row['wickets']}, the batting card credits {found}.")

    # Grand total read as the batters' runs only (the sum at the bottom of the TOTAL column): add the extras.
    for inn in template.get("innings") or []:
        if not isinstance(inn, dict):
            continue
        summary = inn.get("summary") if isinstance(inn.get("summary"), dict) else None
        extras_total = (inn.get("extras") or {}).get("total") if isinstance(inn.get("extras"), dict) else None
        batted = [row.get("runs") for row in inn.get("batting") or [] if isinstance(row, dict)]
        if summary and isinstance(summary.get("runs"), int) and isinstance(extras_total, int) and extras_total > 0 and batted and all(isinstance(x, int) or x is None for x in batted):
            bat_sum = sum(x or 0 for x in batted)
            if summary["runs"] == bat_sum:
                notes.append(f"{summary['runs']} is the batters' runs only; added the extras ({extras_total}): total {bat_sum + extras_total}. Check it.")
                summary["runs"] = bat_sum + extras_total

    notes.extend(reconcile_totals(template))

    # Date: never after the photo; a year far from the photo's year with a day/month just before it was misread.
    photo_text = str(hints.get("photo_date") or "")[:10]
    match_info = template.get("match") if isinstance(template.get("match"), dict) else {}
    try:
        photo_day = _dt.date.fromisoformat(photo_text) if photo_text else None
        card_day = _dt.date.fromisoformat(str(match_info.get("date") or "")[:10]) if match_info.get("date") else None
    except ValueError:
        photo_day = card_day = None
    if photo_day and card_day and card_day.year != photo_day.year:
        try:
            same_year = card_day.replace(year=photo_day.year)
        except ValueError:
            same_year = None
        # Only a handwriting mix-up of the last digit (0/6, 1/7, 3/8, 4/9) is fixed: a card from
        # 2024 photographed in 2026 is a real 2024 match, not a misread (Oct 24: IMG_1894 22-SEP-2024).
        look_alike = {frozenset(pair) for pair in ("06", "17", "38", "49")}
        same_decade = card_day.year // 10 == photo_day.year // 10
        confusable = same_decade and frozenset(f"{card_day.year % 10}{photo_day.year % 10}") in look_alike
        if same_year and confusable and 0 <= (photo_day - same_year).days <= 45:
            notes.append(f"The year was read as {card_day.year}, but the photo is from {photo_day:%d %b %Y}; changed the date to {same_year:%d %b %Y}. Check it.")
            match_info["date"] = same_year.isoformat()
        elif card_day > photo_day:
            notes.append(f"Check the date: {card_day:%d %b %Y} is after the photo was taken ({photo_day:%d %b %Y}).")
    return notes


_CANDB = re.compile(r"^\s*(c|ct|caught)\s*(&|and|\+)\s*(b|bowled)\b", re.IGNORECASE)


def is_caught_and_bowled(dismissal: dict[str, Any]) -> bool:
    """True for "c & b X", "c&b", "ct & b", "C+B", "caught and bowled", or caught with the catcher = the bowler."""
    kind = str(dismissal.get("type") or "").strip().lower()
    written = str(dismissal.get("written_as") or "").strip()
    if _CANDB.match(kind) or _CANDB.match(written) or kind in {"caught and bowled", "caught & bowled"}:
        return True
    fielder = " ".join(str(dismissal.get("fielder") or "").split()).lower()
    bowler = " ".join(str(dismissal.get("bowler") or "").split()).lower()
    return kind.startswith("c") and "run" not in kind and bool(fielder) and fielder == bowler


def _same_player(a: Any, b: Any) -> bool:
    """'Khan' and 'S Khan', 'Dikshit' and 'Dikshit Goel' are the same bowler on one card."""
    x = [w for w in re.split(r"[^a-z0-9]+", str(a or "").lower()) if w]
    y = [w for w in re.split(r"[^a-z0-9]+", str(b or "").lower()) if w]
    if not x or not y:
        return False
    if x == y:
        return True
    short, long = (x, y) if len(x) <= len(y) else (y, x)
    long_words = set(long)
    return all(w in long_words or (len(w) == 1 and any(l.startswith(w) for l in long)) for w in short)


_OUT_TO_BOWLER = ("caught", "bowled", "lbw", "stumped", "hit wicket", "c ", "b ", "st ")


def _credited_to_bowler(dismissal: dict[str, Any]) -> bool:
    kind = str(dismissal.get("type") or "").strip().lower()
    return bool(dismissal.get("bowler")) and (kind.startswith(_OUT_TO_BOWLER) or kind in {"c", "b", "st"}) and "run" not in kind and "retired" not in kind


def cross_checks(template: dict[str, Any]) -> list[str]:
    """The card checked against itself (README "How the AI reader learns" -> "Cross-checks", Oct 30). Each problem
    means a number or name was misread; the reader then looks at the photo again. Only checked when the numbers
    are all there (handwritten books often leave the bowling summary empty)."""
    problems: list[str] = []
    for inn in template.get("innings") or []:
        if not isinstance(inn, dict):
            continue
        team = inn.get("batting_team") or f"Innings {inn.get('inning_number') or ''}".strip()
        summary = inn.get("summary") if isinstance(inn.get("summary"), dict) else {}
        extras = inn.get("extras") if isinstance(inn.get("extras"), dict) else {}
        batting = [row for row in inn.get("batting") or [] if isinstance(row, dict)]
        bowling = [row for row in inn.get("bowling") or [] if isinstance(row, dict)]
        total = summary.get("runs")
        # 1. bowlers' runs = total - byes - leg byes - penalties
        conceded = [row.get("runs_conceded") for row in bowling]
        parts = [extras.get(k) for k in ("byes", "leg_byes", "penalties")]
        if isinstance(total, int) and bowling and all(isinstance(x, int) for x in conceded) and all(isinstance(x, int) or x is None for x in parts):
            expected = total - sum(x or 0 for x in parts)
            if sum(conceded) != expected:
                problems.append(f"{team}: the bowlers' runs add up to {sum(conceded)}, but the total {total} minus byes and leg byes is {expected} - re-read the bowlers' R column and the byes / leg byes.")
        # 2. bowlers' overs = innings overs
        bowled = [row.get("overs") for row in bowling]
        innings_overs = summary.get("overs")
        if bowling and isinstance(innings_overs, (int, float)) and all(isinstance(x, (int, float)) for x in bowled):
            balls = sum(int(x) * 6 + round((float(x) - int(x)) * 10) for x in bowled)
            want = int(innings_overs) * 6 + round((float(innings_overs) - int(innings_overs)) * 10)
            if abs(balls - want) > 6:  # a whole over out is common on paper books (a bowler left off); more is a misread
                problems.append(f"{team}: the bowlers' overs add up to {balls // 6}.{balls % 6}, but the innings lasted {innings_overs} overs - re-read the O column.")
        # 3. each bowler's wickets = batters out to him
        if bowling and all(isinstance(row.get("wickets"), int) for row in bowling):
            credited: list[str] = [str((row.get("dismissal") or {}).get("bowler")) for row in batting if isinstance(row.get("dismissal"), dict) and _credited_to_bowler(row["dismissal"])]
            for row in bowling:
                name = (row.get("player") or {}).get("name")
                found = sum(1 for who in credited if _same_player(who, name))
                if found != row["wickets"]:
                    problems.append(f"{team}: {name} has {row['wickets']} wicket{'s' if row['wickets'] != 1 else ''} in the bowling, but {found} batter{'s were' if found != 1 else ' was'} out to him in How out - re-read both.")
            for who in credited:
                if not any(_same_player(who, (row.get("player") or {}).get("name")) for row in bowling):
                    problems.append(f"{team}: a batter was out to '{who}', but there is no bowler with that name - re-read the How out column.")
        # 4. boundaries can't be more than the runs
        for row in batting:
            runs, fours, sixes = row.get("runs"), row.get("fours"), row.get("sixes")
            if isinstance(runs, int) and isinstance(fours, int) and isinstance(sixes, int) and fours * 4 + sixes * 6 > runs:
                name = (row.get("player") or {}).get("name") or "A batter"
                problems.append(f"{team}: {name} has {fours} fours and {sixes} sixes ({fours * 4 + sixes * 6} runs) but only {runs} runs - re-read that row.")
        # 5. wickets = batters out
        outs = 0
        for row in batting:
            kind = str((row.get("dismissal") or {}).get("type") or "").lower() if isinstance(row.get("dismissal"), dict) else ""
            if kind and not any(word in kind for word in ("not out", "did not", "dnb", "retired hurt", "absent")) and kind != "retired":
                outs += 1
        if isinstance(summary.get("wickets"), int) and batting and outs != summary["wickets"]:
            problems.append(f"{team}: the total says {summary['wickets']} wickets, but {outs} batters are out in How out - re-read How out and the total.")
    return problems


def _parse_json(text: str) -> dict[str, Any] | None:
    cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip(), flags=re.S)
    start, end = cleaned.find("{"), cleaned.rfind("}")
    if start < 0 or end <= start:
        return None
    try:
        data = json.loads(cleaned[start : end + 1])
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None


def _normalise(template: dict[str, Any], model: str) -> dict[str, Any] | None:
    innings = [item for item in template.get("innings") or [] if isinstance(item, dict)]
    if not innings:
        return None
    template["innings"] = innings
    meta = template.get("meta") if isinstance(template.get("meta"), dict) else {}
    meta.update({"source": f"ai:{model}", "processed_by": f"Read by AI ({model})", "status": "template"})
    template["meta"] = meta
    template.setdefault("match", {})
    if not isinstance(template["match"], dict):
        template["match"] = {}
    template["match"].setdefault("match_type", "club")
    template.setdefault("validation", {})
    if not isinstance(template["validation"], dict):
        template["validation"] = {}
    for index, inn in enumerate(innings):
        inn.setdefault("inning_number", index + 1)
        inn.setdefault("summary", {})
        inn.setdefault("batting", [])
        inn.setdefault("bowling", [])
        inn.setdefault("extras", {})
        for row in inn["batting"]:
            dismissal = row.get("dismissal") if isinstance(row.get("dismissal"), dict) else {}
            how = str(dismissal.get("type") or "").strip().lower()
            if is_ro(dismissal.get("written_as")) or is_ro(how):
                dismissal["type"] = how = ro_meaning()  # club rule for the short form "RO"
            if is_caught_and_bowled(dismissal):
                # "c & b Singh" (README "How the AI reader learns" -> checks): one name, bowler and catcher
                dismissal["type"] = how = "caught and bowled"
                who = dismissal.get("bowler") or dismissal.get("fielder")
                dismissal["bowler"] = dismissal["fielder"] = who
            if row.get("runs") in (None, "") and how in {"", "did not bat", "dnb", "none", "null"}:
                dismissal["type"] = "did not bat"  # a name with nothing written next to it
                row["runs"] = None
            row["dismissal"] = dismissal
        for row in inn["batting"] + inn["bowling"]:
            player = row.get("player") if isinstance(row.get("player"), dict) else {"name": row.get("name")}
            name = str(player.get("name") or "").strip()
            player["name"] = name or None
            player["normalized_name"] = name.lower() or None
            row["player"] = player
        # Fill extras from the total when the card only shows the grand total.
        runs = (inn.get("summary") or {}).get("runs")
        bat = [row.get("runs") for row in inn["batting"]]
        extras = inn["extras"] if isinstance(inn["extras"], dict) else {}
        parts = [extras.get(key) for key in ("wides", "no_balls", "byes", "leg_byes", "penalties")]
        if extras.get("total") is None and any(isinstance(v, int) for v in parts):
            extras["total"] = sum(v for v in parts if isinstance(v, int))
        if isinstance(runs, int) and extras.get("total") is None and bat and all(isinstance(v, int) for v in bat if v is not None):
            missing = runs - sum(v for v in bat if isinstance(v, int))
            if missing >= 0:
                extras["total"] = missing
        inn["extras"] = extras
    template["validation"].setdefault("inning_1_total", (innings[0].get("summary") or {}).get("runs"))
    return template


def read_scorecard(
    path: Path,
    *,
    roster: list[str] | None = None,
    club_name: str = "",
    timeout: float = 120.0,
    known_names: list[str] | None = None,
    corrections: dict[str, str] | None = None,
    photo_date: str = "",
) -> dict[str, Any]:
    """{"template": {...}, "model": ...} on success, {"error": "..."} otherwise. Never raises.

    known_names / corrections / photo_date are what the app learned about this club (see _prompt).
    If the batters' runs + extras don't add up to the total, the model is asked once more to look at
    the photo again, told exactly which numbers don't add up (a second "checking" pass)."""
    token = _HINTS.set({"known_names": list(known_names or []), "corrections": dict(corrections or {}), "photo_date": photo_date or "", "club_name": club_name or ""})
    try:
        result = _read_scorecard(path, roster=roster, club_name=club_name, timeout=timeout)
        template = result.get("template")
        if template:
            learned = _apply_learning(template, roster)
            result["notes"] = learned + [note for note in result.get("notes") or [] if note not in learned]
        return result
    finally:
        _HINTS.reset(token)


def _read_scorecard(path: Path, *, roster: list[str] | None, club_name: str, timeout: float) -> dict[str, Any]:
    first = _read_once(Path(path), roster=roster, club_name=club_name, timeout=timeout)
    template = first.get("template")
    if not template:
        return first
    _fix_team_names(template, club_name)
    if first.get("fallback"):
        # Read by the Ollama backup: no second look (it takes minutes); the card is flagged for checking.
        first["notes"] = ["Read by the local AI (Ollama) because Gemini's free limit was used up - check every number, or tap “Read again with AI” tomorrow."] + review_notes(template)
        return first
    # Second look only when the totals really don't add up, or two or more batters' runs don't match their
    # ball-by-ball (a single small mismatch or a balls-count difference stays a note): one read instead of two
    # on most cards, so uploads are about twice as fast (README "Faster photo reading", Oct 20).
    runs_notes = [note for note in review_notes(template) if "ball-by-ball adds up" in note or "card shows" in note]
    problems = sum_problems(template) + (runs_notes if len(runs_notes) >= 2 else [])
    if not problems:
        first["notes"] = review_notes(template)
        return first
    extra = (
        "\n\nYou already read this photo once and got:\n"
        + json.dumps(template)[:6000]
        + "\n\nThese numbers don't add up:\n- "
        + "\n- ".join(problems)
        + "\nLook at the photo again carefully. Re-read every batter's TOTAL column digit by digit "
        "(3 and 8, 1 and 7, 0 and 6, 4 and 9 are easily confused in handwriting), the extras boxes "
        "(wides, no balls, byes, leg byes) and the grand total. Correct the mistakes and reply with the "
        "full corrected JSON in the same format. If it really is written that way, keep it."
    )
    second = _read_once(Path(path), roster=roster, club_name=club_name, timeout=timeout, extra=extra)
    if second.get("template"):
        _fix_team_names(second["template"], club_name)
    if second.get("template") and len(sum_problems(second["template"])) <= len(sum_problems(template)):
        second["checked_twice"] = True
        second["notes"] = review_notes(second["template"])
        return second
    first["notes"] = review_notes(template)
    return first


def _read_once(path: Path, *, roster: list[str] | None, club_name: str, timeout: float, extra: str = "") -> dict[str, Any]:
    chosen = provider()
    if chosen == "gemini":
        result = _read_with_gemini(path, roster=roster, club_name=club_name, timeout=timeout, extra=extra)
        error = str(result.get("error") or "").lower()
        # Gemini's free daily limit used up (or Google busy): carry on with Ollama on this computer when it's
        # installed - free and unlimited, slower and less accurate (README "Ollama backup when Gemini's limit runs out").
        if error and any(word in error for word in ("limit", "busy", "couldn't reach", "no gemini vision model")) and ollama_model():
            backup = _read_with_ollama(path, roster=roster, club_name=club_name, extra=extra)
            if backup.get("template"):
                backup["fallback"] = "ollama"
                backup["fallback_reason"] = result.get("error")
                return backup
        return result
    if chosen == "ollama":
        return _read_with_ollama(path, roster=roster, club_name=club_name, extra=extra)
    return _read_with_claude(path, roster=roster, club_name=club_name, timeout=timeout, extra=extra)


def _team_key(name: Any) -> str:
    text = re.sub(r"[^a-z]", "", str(name or "").lower())
    for word in ("cricketclub", "cricket", "club", "xi"):
        text = text.replace(word, "")
    return text


def _fix_team_names(template: dict[str, Any], club_name: str) -> None:
    """"HEART LAKE" on the card -> the club's real name; never the same club on both sides."""
    club_key = _team_key(club_name)
    match = template.get("match") if isinstance(template.get("match"), dict) else {}
    teams = match.get("teams") if isinstance(match.get("teams"), dict) else {}

    def fixed(name: Any) -> Any:
        key = _team_key(name)
        if club_key and key and (key == club_key or key in club_key or club_key in key):
            return club_name
        return name

    names = {slot: fixed(teams.get(slot)) for slot in ("team_1", "team_2")}
    if names["team_1"] and names["team_1"] == names["team_2"]:
        names["team_2"] = None
    teams.update(names)
    match["teams"] = teams
    for inn in template.get("innings") or []:
        if not isinstance(inn, dict):
            continue
        inn["batting_team"] = fixed(inn.get("batting_team"))
        inn["bowling_team"] = fixed(inn.get("bowling_team"))
        if inn["batting_team"] and inn["batting_team"] == inn["bowling_team"]:
            inn["bowling_team"] = None


_EXTRA_LABELS = (
    ("leg_byes", r"l\.?\s*b(?:ye)?s?|leg\s*byes?|lbyes?"),
    ("no_balls", r"n\.?\s*b\.?|no\s*balls?"),
    ("penalties", r"pen(?:alty|alties|s)?"),
    ("wides", r"w(?:ide)?s?|wd"),
    ("byes", r"b(?:ye)?s?"),
)


def _written_extras(written: Any) -> dict[str, set[int]]:
    """'BYES 111, WIDES 1112111, NB 1' -> {"byes": {111, 3}, "wides": {1112111, 8}, "no_balls": {1}}: each box read
    both as a plain number and as a tally (one digit per extra ball). Used to check the extras total."""
    found: dict[str, set[int]] = {}
    for part in re.split(r"[,;/]|\band\b", str(written or ""), flags=re.I):
        part = part.strip()
        if not part:
            continue
        match = re.fullmatch(r"([A-Za-z][A-Za-z .]*?)\s*[:=]?\s*(\d[\d\s]*)", part)
        label = match.group(1).strip().lower() if match else ""
        key = next((name for name, pattern in _EXTRA_LABELS if re.fullmatch(pattern, label)), None) if match else None
        if not key:
            return {}  # something written we can't read for sure ("2-1", "HT HT 5"): don't use the boxes at all
        digits = match.group(2)
        compact = re.sub(r"\s+", "", digits)
        if not compact:
            continue
        options = {sum(int(ch) for ch in compact)}  # tally
        if len(compact) <= 2:
            options.add(int(compact))  # a plain number like 23
        found.setdefault(key, set()).update(options)
    return found


def _extras_options(extras: dict[str, Any]) -> set[int]:
    """Possible extras totals from what was written in the boxes (plain numbers or tallies)."""
    boxes = _written_extras(extras.get("written_as"))
    if not boxes:
        return set()
    totals = {0}
    for options in boxes.values():
        totals = {total + option for total in totals for option in options if total + option < 400}
    return totals


def reconcile_totals(template: dict[str, Any]) -> list[str]:
    """When batters' runs + extras don't make the grand total, try the readings the card itself offers: a batter's
    ball-by-ball sum instead of the TOTAL column, or the extras boxes read as tallies. If exactly ONE such change
    makes everything add up, use it and say so; otherwise leave the card for a person (no guessing)."""
    notes: list[str] = []
    for inn in template.get("innings") or []:
        if not isinstance(inn, dict):
            continue
        summary = inn.get("summary") if isinstance(inn.get("summary"), dict) else {}
        extras = inn.get("extras") if isinstance(inn.get("extras"), dict) else {}
        total = summary.get("runs")
        rows = [row for row in inn.get("batting") or [] if isinstance(row, dict)]
        runs = [row.get("runs") for row in rows]
        if not isinstance(total, int) or not rows or not all(isinstance(x, int) or x is None for x in runs):
            continue
        bat = sum(x or 0 for x in runs)
        extra_now = extras.get("total") if isinstance(extras.get("total"), int) else 0
        if bat + extra_now == total:
            continue
        team = inn.get("batting_team") or "This innings"
        fixes: list[tuple[str, Any]] = []
        for option in sorted(_extras_options(extras)):
            if option != extra_now and bat + option == total:
                fixes.append(("extras", option))
        for index, row in enumerate(rows):
            alt = row.get("ball_runs_sum")
            if isinstance(alt, int) and isinstance(row.get("runs"), int) and alt != row["runs"] and bat - row["runs"] + alt + extra_now == total:
                fixes.append(("batter", (index, alt)))
        if len(fixes) != 1:
            continue
        kind, value = fixes[0]
        if kind == "extras":
            notes.append(f"{team}: extras were read as {extra_now}, but the extras boxes ('{extras.get('written_as')}') make {value}, "
                         f"and with {value} the total {total} adds up - used {value}. Check it.")
            extras["total"] = value
        else:
            index, alt = value
            row = rows[index]
            name = (row.get("player") or {}).get("name") or "A batter"
            notes.append(f"{team}: {name}'s runs were read as {row['runs']}, but the ball-by-ball adds up to {alt}, and with {alt} "
                         f"the total {total} adds up - used {alt}. Check it.")
            row["runs"] = alt
    return notes


def bowling_notes(template: dict[str, Any]) -> list[str]:
    """Bowling figures that can't be right: more wickets than batters out to bowlers, or more overs than the innings."""
    notes: list[str] = []
    for inn in template.get("innings") or []:
        if not isinstance(inn, dict):
            continue
        team = inn.get("bowling_team") or "The bowlers"
        bowlers = [row for row in inn.get("bowling") or [] if isinstance(row, dict)]
        taken = sum(row["wickets"] for row in bowlers if isinstance(row.get("wickets"), int))
        out_to_bowlers = 0
        for row in inn.get("batting") or []:
            how = str(((row or {}).get("dismissal") or {}).get("type") or "").lower() if isinstance(row, dict) else ""
            if how and not any(word in how for word in ("not out", "did not", "run", "retired", "absent", "dnb")):
                out_to_bowlers += 1
        if bowlers and taken > out_to_bowlers:
            notes.append(f"{team}: the bowlers' wickets add up to {taken}, but only {out_to_bowlers} batters were out to a bowler - check the bowling figures.")
        overs = [row.get("overs") for row in bowlers if isinstance(row.get("overs"), (int, float))]
        innings_overs = (inn.get("summary") or {}).get("overs") if isinstance(inn.get("summary"), dict) else None
        if overs and isinstance(innings_overs, (int, float)) and sum(int(x) for x in overs) > int(innings_overs) + 1:
            notes.append(f"{team}: the bowlers' overs add up to {sum(int(x) for x in overs)}, more than the {innings_overs} overs batted - check the bowling figures.")
    return notes


def review_notes(template: dict[str, Any]) -> list[str]:
    """Things a person should check against the photo: numbers the model wasn't sure about, and batters
    whose TOTAL doesn't match their own ball-by-ball runs."""
    notes: list[str] = []
    for inn in template.get("innings") or []:
        if not isinstance(inn, dict):
            continue
        for row in inn.get("batting") or []:
            if not isinstance(row, dict):
                continue
            name = ((row.get("player") or {}).get("name")) or "A batter"
            runs, ball_sum = row.get("runs"), row.get("ball_runs_sum")
            if isinstance(runs, int) and isinstance(ball_sum, int) and abs(runs - ball_sum) > 2:
                notes.append(f"Check {name}: the runs column reads {runs}, but the ball-by-ball adds up to {ball_sum}.")
            balls, ball_count = row.get("balls"), row.get("ball_count")
            if isinstance(balls, int) and isinstance(ball_count, int) and ball_count > 0 and abs(balls - ball_count) > 2:
                notes.append(f"Check {name}'s balls: the card was read as {balls} balls, but the ball-by-ball count is {ball_count}.")
            if isinstance(runs, int) and isinstance(ball_sum, int) and abs(runs - ball_sum) > 2:
                pass
            elif row.get("unsure") is True:
                notes.append(f"Check {name}'s runs ({runs}) against the photo: the handwriting was hard to read.")
            dismissal = row.get("dismissal") if isinstance(row.get("dismissal"), dict) else {}
            if is_ro(dismissal.get("written_as")):
                notes.append(f"{name}: 'RO' on the card was read as {ro_meaning()}. If it was the other one, change it with Edit.")
        extras = inn.get("extras") if isinstance(inn.get("extras"), dict) else {}
        if extras.get("unsure") is True:
            notes.append(f"Check the extras ({extras.get('total')}) against the photo: the handwriting was hard to read.")
        written = str(extras.get("written_as") or "")
        numbers = [int(n) for n in re.findall(r"\d+", written)]
        total = (inn.get("summary") or {}).get("runs") if isinstance(inn.get("summary"), dict) else None
        bat = [row.get("runs") for row in inn.get("batting") or [] if isinstance(row, dict)]
        adds_up = isinstance(total, int) and isinstance(extras.get("total"), int) and all(isinstance(x, int) or x is None for x in bat) and sum(x or 0 for x in bat) + extras["total"] == total
        options = _extras_options(extras)
        if isinstance(extras.get("total"), int) and numbers and not adds_up and extras["total"] not in options and max(numbers) != extras["total"] and sum(numbers) != extras["total"]:
            notes.append(f"Check the extras: the card shows '{written}' but extras was read as {extras['total']}.")
    notes.extend(bowling_notes(template))
    notes.extend(note for note in cross_checks(template) if note not in notes)
    return notes[:10]


def sum_problems(template: dict[str, Any]) -> list[str]:
    """Innings where batters' runs + extras != total (only when all those numbers are present), plus the
    cross-checks (bowling runs, overs, wickets, boundaries)."""
    problems: list[str] = list(cross_checks(template))
    for inn in template.get("innings") or []:
        if not isinstance(inn, dict):
            continue
        total = (inn.get("summary") or {}).get("runs")
        runs = [row.get("runs") for row in inn.get("batting") or [] if isinstance(row, dict)]
        extras = (inn.get("extras") or {}).get("total") if isinstance(inn.get("extras"), dict) else None
        if not isinstance(total, int) or not runs:
            continue
        batted = sum(value for value in runs if isinstance(value, int))
        added = batted + (extras if isinstance(extras, int) else 0)
        team = inn.get("batting_team") or f"Innings {inn.get('inning_number') or ''}".strip()
        if added != total:
            problems.append(f"{team}: batters' runs add up to {batted}, extras {extras if isinstance(extras, int) else 'missing'}, together {added}, but the total is {total}.")
        parts = [(inn.get("extras") or {}).get(key) for key in ("wides", "no_balls", "byes", "leg_byes", "penalties")]
        written = sum(value for value in parts if isinstance(value, int))
        if isinstance(extras, int) and written and extras - written > 2:
            problems.append(
                f"{team}: the extras boxes add up to {written} but extras was given as {extras} - that looks like a batter's runs "
                "were misread (the extras were stretched to fit the total)."
            )
    return problems


def _read_with_ollama(path: Path, *, roster: list[str] | None, club_name: str, extra: str = "") -> dict[str, Any]:
    """Free, runs on this computer. On a PC without a graphics card this can take a few minutes."""
    model = ollama_model()
    if not model:
        return {"error": "No Ollama vision model found. Run: ollama pull qwen3-vl:8b"}
    try:
        _, data = _image_payload(path)
    except Exception as exc:
        return {"error": f"Couldn't open the photo: {exc}"}
    prompt = _prompt(roster, club_name) + extra
    body = {
        "model": model,
        "messages": [{"role": "user", "content": prompt, "images": [data]}],
        "stream": False,
        "format": "json",
        "options": {"temperature": 0, "num_ctx": 8192},
    }
    try:
        timeout = float(subscriptions.setting("OLLAMA_VISION_TIMEOUT", "600") or 600)
        response = httpx.post(f"{ollama_base_url()}/api/chat", json=body, timeout=timeout)
    except httpx.TimeoutException:
        return {"error": "The Ollama model took too long. Try again, or set OLLAMA_VISION_TIMEOUT higher in .env."}
    except httpx.HTTPError as exc:
        return {"error": f"Couldn't reach Ollama: {exc.__class__.__name__}. Is the Ollama app running?"}
    if response.status_code != 200:
        return {"error": f"Ollama answered {response.status_code}: {response.text[:200]}"}
    payload = response.json()
    text = str((payload.get("message") or {}).get("content") or "")
    template = _parse_json(text)
    template = _normalise(template, model) if template else None
    if not template:
        return {"error": "The Ollama model's answer wasn't a scorecard.", "raw": text[:2000]}
    return {"template": template, "model": model, "usage": {"input_tokens": payload.get("prompt_eval_count"), "output_tokens": payload.get("eval_count")}}


_GEMINI_SKIP: dict[str, float] = {}


def _read_with_gemini(path: Path, *, roster: list[str] | None, club_name: str, timeout: float, extra: str = "") -> dict[str, Any]:
    key = gemini_key()
    try:
        media_type, data = _image_payload(path)
    except Exception as exc:
        return {"error": f"Couldn't open the photo: {exc}"}
    prompt = _prompt(roster, club_name) + extra
    parts: list[dict[str, Any]] = [{"inline_data": {"mime_type": media_type, "data": data}}]
    halves = _zoomed_halves(path)
    for half_type, half_data in halves:
        parts.append({"inline_data": {"mime_type": half_type, "data": half_data}})
    if halves:
        prompt = ("Image 1 is the whole page. Images 2 and 3 are zoomed-in copies of its top half and bottom half - "
                  "use them to read small handwriting (names, ball-by-ball, TOTAL column, bowling boxes).\n\n") + prompt
    parts.append({"text": prompt})
    contents: list[dict[str, Any]] = []
    for example in worked_examples(path):
        contents.append({"role": "user", "parts": [
            {"inline_data": {"mime_type": example["media_type"], "data": example["data"]}},
            {"text": _example_intro(example) + "\n\nThe correct JSON for this example card is your next answer."},
        ]})
        contents.append({"role": "model", "parts": [{"text": example["answer"]}]})
    if contents:
        parts[-1] = {"text": "Now the NEW scorecard to read (the photos above in this message).\n\n" + prompt}
    body = {
        "contents": contents + [{"role": "user", "parts": parts}],
        "generationConfig": {"temperature": 0, "responseMimeType": "application/json"},
    }
    # Less "thinking" time: copying a scorecard needs careful reading, not long reasoning. Models that don't know
    # the setting answer 400; then we ask again without it (README "Faster photo reading").
    thinking = subscriptions.setting("GEMINI_THINKING", "low").strip().lower()
    base = subscriptions.setting("GEMINI_BASE_URL", "https://generativelanguage.googleapis.com").rstrip("/")
    configured = subscriptions.setting("GEMINI_VISION_MODEL")
    models = [configured] if configured else list(GEMINI_SCORECARD_MODELS)
    import time

    last_error = ""
    busy = False
    tried: list[str] = []  # "model: what happened" for the error message and the log
    now = time.time()
    # Models that just failed (timed out, busy, or out of free reads) are skipped for a while, so the next card
    # doesn't wait minutes on the same model again (README "Faster photo reading"). Last resort: try them anyway.
    ready = [model for model in models if _GEMINI_SKIP.get(model, 0) <= now]
    models = ready or models
    for model in models:
        response = None
        # "High demand" (503) and similar hiccups are usually gone within seconds: wait and retry once,
        # then try the next free model instead of giving up. A timeout moves straight to the next model.
        for attempt, pause in enumerate((0, 4)):
            if pause:
                time.sleep(pause)
            request_body = body
            if thinking and thinking not in {"off", "none", "default"}:
                config = dict(body["generationConfig"])
                config["thinkingConfig"] = {"thinkingBudget": 512} if "2.5" in model else {"thinkingLevel": thinking}
                request_body = {**body, "generationConfig": config}
            try:
                response = httpx.post(
                    f"{base}/v1beta/models/{model}:generateContent",
                    json=request_body,
                    headers={"x-goog-api-key": key, "content-type": "application/json"},
                    timeout=timeout,
                )
                if response.status_code == 400 and request_body is not body and "think" in response.text.lower():
                    thinking = ""  # this model doesn't take the setting: ask normally
                    response = httpx.post(
                        f"{base}/v1beta/models/{model}:generateContent",
                        json=body,
                        headers={"x-goog-api-key": key, "content-type": "application/json"},
                        timeout=timeout,
                    )
            except httpx.TimeoutException:
                last_error = f"{model} took too long"
                tried.append(f"{model}: no answer in {int(timeout)}s")
                response = None
                _GEMINI_SKIP[model] = time.time() + 20 * 60
                break
            except httpx.HTTPError as exc:
                last_error = f"couldn't reach Google ({exc.__class__.__name__})"
                response = None
                continue
            if response.status_code in {500, 502, 503, 504}:
                busy = True
                last_error = f"{model} is busy"
                try:
                    why = response.json().get("error", {}).get("message", "")
                except Exception:
                    why = response.text[:160]
                tried.append(f"{model}: {response.status_code} {why[:120]}")
                logger.warning("Gemini %s answered %s: %s", model, response.status_code, why[:300])
                # A 500 (not "busy") right after a big request with the worked examples: ask again without them.
                if response.status_code == 500 and contents and body.get("contents") is not None and len(body["contents"]) > 1:
                    body = {**body, "contents": body["contents"][-1:]}
                    body["contents"][0]["parts"][-1] = {"text": prompt}
                    tried.append(f"{model}: asked again without the worked examples")
                continue
            break
        if response is None or response.status_code in {500, 502, 503, 504}:
            if response is not None:
                _GEMINI_SKIP[model] = time.time() + 10 * 60
            continue  # still busy: try the next free model
        if response.status_code == 404:
            last_error = f"model {model} not available"
            continue
        if response.status_code == 429:
            tried.append(f"{model}: free daily limit reached")
            last_error = f"{model} free limit reached"
            _GEMINI_SKIP[model] = time.time() + 60 * 60
            continue  # each free model has its own daily limit
        if response.status_code != 200:
            try:
                detail = response.json().get("error", {}).get("message", "")
            except Exception:
                detail = response.text[:200]
            logger.warning("Gemini scorecard read HTTP %s: %s", response.status_code, detail)
            return {"error": f"Google's AI service answered {response.status_code}: {detail}"}
        payload = response.json()
        parts = (((payload.get("candidates") or [{}])[0].get("content") or {}).get("parts") or [])
        text = "".join(str(part.get("text") or "") for part in parts)
        template = _parse_json(text)
        template = _normalise(template, model) if template else None
        if not template:
            return {"error": "The AI answer wasn't a scorecard.", "raw": text[:2000]}
        usage = payload.get("usageMetadata") or {}
        return {"template": template, "model": model, "usage": {"input_tokens": usage.get("promptTokenCount"), "output_tokens": usage.get("candidatesTokenCount")}}
    detail = (" [" + "; ".join(tried[-6:]) + "]") if tried else ""
    if "limit" in last_error or (tried and all("limit" in item for item in tried)):
        return {"error": "Today's free AI limit is used up. Tap “Read with AI” again tomorrow, or type the scorecard in." + detail}
    if busy:
        return {"error": "Google's free AI is very busy right now. Tap “Read with AI” again in a few minutes, or type the scorecard in." + detail}
    return {"error": f"No Gemini vision model answered ({last_error}). Set GEMINI_VISION_MODEL in .env."}


def _read_with_claude(path: Path, *, roster: list[str] | None, club_name: str, timeout: float, extra: str = "") -> dict[str, Any]:
    key = api_key()
    if not key:
        return {"error": "AI reading is off (no ANTHROPIC_API_KEY)."}
    model = model_name()
    try:
        media_type, data = _image_payload(Path(path))
    except Exception as exc:
        return {"error": f"Couldn't open the photo: {exc}"}
    prompt = _prompt(roster, club_name) + extra
    body = {
        "model": model,
        "max_tokens": 4096,
        "temperature": 0,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "image", "source": {"type": "base64", "media_type": media_type, "data": data}},
                    {"type": "text", "text": prompt},
                ],
            }
        ],
    }
    examples: list[dict[str, Any]] = []
    for example in worked_examples(Path(path)):
        examples.append({"role": "user", "content": [
            {"type": "image", "source": {"type": "base64", "media_type": example["media_type"], "data": example["data"]}},
            {"type": "text", "text": _example_intro(example) + "\n\nReply with the correct JSON for this example card."},
        ]})
        examples.append({"role": "assistant", "content": example["answer"]})
    if examples:
        body["messages"] = examples + body["messages"]
    try:
        base = subscriptions.setting("ANTHROPIC_BASE_URL", DEFAULT_BASE_URL).rstrip("/")
        response = httpx.post(
            f"{base}/v1/messages",
            json=body,
            headers={"x-api-key": key, "anthropic-version": "2023-06-01", "content-type": "application/json"},
            timeout=timeout,
        )
    except httpx.HTTPError as exc:
        logger.warning("AI scorecard read failed to connect: %s", exc)
        return {"error": f"Couldn't reach the AI service: {exc.__class__.__name__}"}
    if response.status_code != 200:
        detail = ""
        try:
            detail = response.json().get("error", {}).get("message", "")
        except Exception:
            detail = response.text[:200]
        logger.warning("AI scorecard read HTTP %s: %s", response.status_code, detail)
        return {"error": f"The AI service answered {response.status_code}: {detail}"}
    payload = response.json()
    text = "".join(part.get("text", "") for part in payload.get("content") or [] if part.get("type") == "text")
    template = _parse_json(text)
    template = _normalise(template, model) if template else None
    if not template:
        return {"error": "The AI answer wasn't a scorecard.", "raw": text[:2000]}
    return {"template": template, "model": model, "usage": payload.get("usage") or {}}


# ---------------------------------------------------------------------------
# Duplicate check: "are these two scorecards the same match?" (text only, no photo).
# Uses the same free provider as reading (Gemini, else Claude, else local Ollama).
# README: "Scorecard uploads: checks, review and duplicates" -> "AI duplicate check".
# ---------------------------------------------------------------------------
SAME_MATCH_PROMPT = """Two cricket scorecards were uploaded to a club app. Decide if they are the SAME match
(the same game uploaded twice, maybe read slightly differently: a misspelt name, one number off, a missing date or
team). Different matches between the same teams on different days are NOT the same.

Scorecard A:
{a}

Scorecard B:
{b}

Reply with ONLY this JSON: {{"same": true or false, "reason": "one short sentence"}}"""


def _ask_text(prompt: str, timeout: float = 40.0) -> tuple[str, str]:
    """(answer text, model) from the configured provider, or ("", "") when nothing answered."""
    which = provider()
    try:
        if which == "gemini":
            base = subscriptions.setting("GEMINI_BASE_URL", "https://generativelanguage.googleapis.com").rstrip("/")
            configured = subscriptions.setting("GEMINI_TEXT_MODEL") or subscriptions.setting("GEMINI_VISION_MODEL")
            body = {
                "contents": [{"role": "user", "parts": [{"text": prompt}]}],
                "generationConfig": {"temperature": 0, "responseMimeType": "application/json"},
            }
            for model in ([configured] if configured else [GEMINI_DEFAULT_MODEL, *GEMINI_FALLBACK_MODELS]):
                response = httpx.post(
                    f"{base}/v1beta/models/{model}:generateContent",
                    json=body,
                    headers={"x-goog-api-key": gemini_key(), "content-type": "application/json"},
                    timeout=timeout,
                )
                if response.status_code != 200:
                    continue  # busy / limit reached / not available: next free model
                parts = (((response.json().get("candidates") or [{}])[0].get("content") or {}).get("parts") or [])
                return "".join(str(part.get("text") or "") for part in parts), model
            return "", ""
        if which == "claude":
            base = subscriptions.setting("ANTHROPIC_BASE_URL", DEFAULT_BASE_URL).rstrip("/")
            response = httpx.post(
                f"{base}/v1/messages",
                json={"model": model_name(), "max_tokens": 200, "messages": [{"role": "user", "content": prompt}]},
                headers={"x-api-key": api_key(), "anthropic-version": "2023-06-01", "content-type": "application/json"},
                timeout=timeout,
            )
            if response.status_code != 200:
                return "", ""
            return "".join(block.get("text", "") for block in response.json().get("content") or []), model_name()
        if which == "ollama":
            model = ollama_model()
            response = httpx.post(
                f"{ollama_base_url()}/api/chat",
                json={"model": model, "messages": [{"role": "user", "content": prompt}], "stream": False, "format": "json", "options": {"temperature": 0}},
                timeout=max(timeout, 120.0),
            )
            if response.status_code != 200:
                return "", ""
            return str((response.json().get("message") or {}).get("content") or ""), model
    except httpx.HTTPError:
        return "", ""
    return "", ""


def same_match(summary_a: str, summary_b: str) -> dict[str, Any] | None:
    """{"same": bool, "reason": str, "model": str}, or None when no AI is set up or it didn't answer."""
    if not (summary_a.strip() and summary_b.strip() and enabled()):
        return None
    text, model = _ask_text(SAME_MATCH_PROMPT.format(a=summary_a[:3000], b=summary_b[:3000]))
    answer = _parse_json(text) if text else None
    if not answer or not isinstance(answer.get("same"), bool):
        return None
    return {"same": answer["same"], "reason": str(answer.get("reason") or "")[:200], "model": model}
