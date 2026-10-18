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
  Use the TOTAL column for runs. Only if TOTAL is empty, add up that batter's ball-by-ball runs.
- HOW OUT words: caught / c, bowled / b, LBW, run out, stumped / st, not out / NO, retired out, retired hurt,
  did not bat (a name with nothing written). Put the dismissal type in "type" and the bowler's name in "bowler".
- In HOW OUT, "RO" (or "R.O.", "R/O") on this club's cards means "{ro}" - write "{ro}" for it.
  Always also copy exactly what is written in HOW OUT into "written_as" (e.g. "RO", "Retired out", "LBW").
- Grand total: the "G. TOTAL" box, a circled number, or the last value in the running score column.
  Wickets = batters who are out (retired out counts; not out / retired hurt / did not bat don't).
- Extras: copy what is written in the BYES / LEG BYES / WIDES / NO BALLS / PENALTY boxes. Extras total = the
  TOTAL EXTRAS box, or else the sum of those boxes. NEVER change extras just to make the sum work: if batters +
  extras don't equal the grand total, one of the batters' TOTAL numbers is probably misread - look again
  (3 and 8, 1 and 7, 0 and 6 are easily confused). Only if no extras boxes are filled in at all may you use
  extras = grand total minus the batters' runs.
- The bowling analysis lists the other team's bowlers. Copy names; copy overs / maidens / runs / wickets only when
  the BOWLING SUMMARY columns are filled in, otherwise leave them null.
- A page usually holds ONE innings. Only add a second innings if it is really on the photo.

Double-checking (important):
- For every batter also add up the runs in their ball-by-ball scribbles (dots = 0, | = 1) and put it in
  "ball_runs_sum" (null if you can't read them). It should match the TOTAL column; if it doesn't, look at both again.
- Set "unsure": true on any batter (or on extras) where a digit is hard to read, so a person checks it.

Rules:
- Never invent names or numbers. If you can't read something, use null. Spell names as written (fix obvious
  letter mix-ups only, e.g. "SARABJEET").
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
      "batting": [{{"player": {{"name": "..."}}, "runs": 0, "balls": null, "fours": null, "sixes": null, "dismissal": {{"type": "caught", "fielder": null, "bowler": "...", "written_as": "CAUGHT"}}, "ball_runs_sum": null, "unsure": false}}],
      "bowling": [{{"player": {{"name": "..."}}, "overs": null, "maidens": null, "runs_conceded": null, "wickets": null}}],
      "extras": {{"wides": null, "no_balls": null, "byes": null, "leg_byes": null, "penalties": null, "total": 0, "written_as": "exactly what is written in the extras boxes, e.g. 'W 52'", "unsure": false}}
    }}
  ],
  "validation": {{"inning_1_total": 0, "inning_2_total": null, "expected_result": "", "notes": "anything you were unsure about"}}
}}"""


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


def read_scorecard(path: Path, *, roster: list[str] | None = None, club_name: str = "", timeout: float = 120.0) -> dict[str, Any]:
    """{"template": {...}, "model": ...} on success, {"error": "..."} otherwise. Never raises.

    If the batters' runs + extras don't add up to the total, the model is asked once more to look at
    the photo again, told exactly which numbers don't add up (a second "checking" pass)."""
    first = _read_once(Path(path), roster=roster, club_name=club_name, timeout=timeout)
    template = first.get("template")
    if not template:
        return first
    _fix_team_names(template, club_name)
    problems = sum_problems(template) + [note for note in review_notes(template) if "ball-by-ball" in note or "card shows" in note]
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
        return _read_with_gemini(path, roster=roster, club_name=club_name, timeout=timeout, extra=extra)
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
        if isinstance(extras.get("total"), int) and numbers and max(numbers) != extras["total"] and sum(numbers) != extras["total"]:
            notes.append(f"Check the extras: the card shows '{written}' but extras was read as {extras['total']}.")
    return notes[:8]


def sum_problems(template: dict[str, Any]) -> list[str]:
    """Innings where batters' runs + extras != total (only when all those numbers are present)."""
    problems: list[str] = []
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
    prompt = PROMPT.format(roster=", ".join((roster or [])[:120]) or "(none)", club=club_name or "(unknown)", ro=ro_meaning()) + extra
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


def _read_with_gemini(path: Path, *, roster: list[str] | None, club_name: str, timeout: float, extra: str = "") -> dict[str, Any]:
    key = gemini_key()
    try:
        media_type, data = _image_payload(path)
    except Exception as exc:
        return {"error": f"Couldn't open the photo: {exc}"}
    prompt = PROMPT.format(roster=", ".join((roster or [])[:120]) or "(none)", club=club_name or "(unknown)", ro=ro_meaning()) + extra
    body = {
        "contents": [{"role": "user", "parts": [{"inline_data": {"mime_type": media_type, "data": data}}, {"text": prompt}]}],
        "generationConfig": {"temperature": 0, "responseMimeType": "application/json"},
    }
    base = subscriptions.setting("GEMINI_BASE_URL", "https://generativelanguage.googleapis.com").rstrip("/")
    configured = subscriptions.setting("GEMINI_VISION_MODEL")
    models = [configured] if configured else [GEMINI_DEFAULT_MODEL, *GEMINI_FALLBACK_MODELS]
    import time

    last_error = ""
    busy = False
    for model in models:
        response = None
        # "High demand" (503) and similar hiccups are usually gone within seconds: wait and retry,
        # then try the next free model instead of giving up.
        for attempt, pause in enumerate((0, 3, 8)):
            if pause:
                time.sleep(pause)
            try:
                response = httpx.post(
                    f"{base}/v1beta/models/{model}:generateContent",
                    json=body,
                    headers={"x-goog-api-key": key, "content-type": "application/json"},
                    timeout=timeout,
                )
            except httpx.HTTPError as exc:
                last_error = f"couldn't reach Google ({exc.__class__.__name__})"
                response = None
                continue
            if response.status_code in {500, 502, 503, 504}:
                busy = True
                last_error = f"{model} is busy"
                continue
            break
        if response is None or response.status_code in {500, 502, 503, 504}:
            continue  # still busy: try the next free model
        if response.status_code == 404:
            last_error = f"model {model} not available"
            continue
        if response.status_code == 429:
            last_error = f"{model} free limit reached"
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
    if busy:
        return {"error": "Google's free AI is very busy right now. Tap “Read with AI” again in a few minutes, or type the scorecard in."}
    if "limit" in last_error:
        return {"error": "Today's free AI limit is used up. Tap “Read with AI” again tomorrow, or type the scorecard in."}
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
    prompt = PROMPT.format(roster=", ".join((roster or [])[:120]) or "(none)", club=club_name or "(unknown)", ro=ro_meaning()) + extra
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
