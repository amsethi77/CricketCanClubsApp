"""
Smart checks for uploaded scorecard photos (soft launch, Oct 2026).

Used by POST /api/scorecards/upload and the site-admin duplicate report in app/main.py.
Documented in MD/README.md -> "Scorecard uploads: checks, review and duplicates".

  * image_fingerprint()  - a small "looks the same" hash of the photo (8x8 average hash).
                           Catches the same photo saved again, resized or re-compressed,
                           which the exact file hash misses.
  * match_signature()    - date + both team names + both scores from the digital scorecard.
                           Two uploads with the same signature are the same match.
  * quality_problems()   - things that make a scorecard "not proper": no date, no teams,
                           no scores, impossible numbers, batting runs that don't add up.
  * llm_same_match()     - optional: asks the local Ollama model whether two scorecards are
                           the same match. Skipped (returns None) when Ollama isn't running.
"""

from __future__ import annotations

import io
import json
import re
import urllib.request
from typing import Any, Callable

try:  # Pillow is already used by the OCR pipeline; HEIC photos need pillow-heif.
    from PIL import Image

    try:
        from pillow_heif import register_heif_opener

        register_heif_opener()
    except Exception:  # pragma: no cover - optional
        pass
except Exception:  # pragma: no cover - Pillow missing
    Image = None  # type: ignore[assignment]

FINGERPRINT_SAME = 5  # bits out of 64; at or below this the photos are the same picture


def image_fingerprint(content: bytes) -> str:
    """16-hex-digit average hash of the photo, or '' when it can't be read."""
    if Image is None or not content:
        return ""
    try:
        with Image.open(io.BytesIO(content)) as image:
            small = image.convert("L").resize((8, 8))
            pixels = list(small.getdata())
    except Exception:
        return ""
    average = sum(pixels) / len(pixels)
    bits = 0
    for value in pixels:
        bits = (bits << 1) | (1 if value >= average else 0)
    return f"{bits:016x}"


def fingerprint_distance(first: str, second: str) -> int:
    try:
        return bin(int(first, 16) ^ int(second, 16)).count("1")
    except (TypeError, ValueError):
        return 64


def _name(value: Any) -> str:
    text = re.sub(r"[^a-z0-9 ]+", " ", str(value or "").lower())
    text = re.sub(r"\b(cricket|club|cc|xi|team|the)\b", " ", text)
    return " ".join(text.split())


def match_signature(card: dict[str, Any]) -> str:
    """'date|team a|team b|score a|score b' (teams sorted), or '' when there isn't enough to compare."""
    date = str(card.get("date") or "")
    innings = [item for item in card.get("innings") or [] if isinstance(item, dict)]
    sides = sorted(
        (_name(item.get("team")), f"{item.get('runs')}/{item.get('wickets')}")
        for item in innings
        if item.get("runs") is not None
    )
    if not date or len(sides) < 2 or not all(team for team, _ in sides):
        return ""
    return "|".join([date, sides[0][0], sides[1][0], sides[0][1], sides[1][1]])


def _overs_balls(value: Any) -> int | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        whole, _, part = text.partition(".")
        return int(whole) * 6 + (int(part[:1]) if part else 0)
    except ValueError:
        return None


def _template_of(record: dict[str, Any]) -> dict[str, Any]:
    """The scorecard JSON that was imported (AI read / typed in), if any."""
    raw = str(record.get("raw_extracted_text") or "").strip()
    if raw.startswith("{"):
        try:
            data = json.loads(raw)
            if isinstance(data, dict) and isinstance(data.get("match"), dict):
                return data
        except ValueError:
            pass
    return {}


def quality_problems(card: dict[str, Any], record: dict[str, Any]) -> list[str]:
    """Plain-English reasons this upload needs a site admin to look at it ([] = looks proper)."""
    problems: list[str] = []
    engine = str(record.get("ocr_engine") or "").lower()
    if "fallback" in engine or "unreadable" in engine or str(record.get("confidence") or "").lower() in {"filename draft", "unreadable"}:
        problems.append("The photo couldn't be read clearly.")
    if not card.get("date") or (_template_of(record) and not (_template_of(record).get("match") or {}).get("date")):
        problems.append("The match date isn't on the photo: add it with ✏️ Edit scorecard (until then it shows the upload date).")
    innings = [item for item in card.get("innings") or [] if isinstance(item, dict)]
    teams = [str(item.get("team") or "").strip() for item in innings]
    if len([team for team in teams if team and team.lower() not in {"opponent", "club", "opponent name"}]) < 2:
        problems.append("The other team's name isn't on the photo: add it with ✏️ Edit scorecard.")
    scored = [item for item in innings if item.get("runs") is not None]
    if len(scored) < 2:
        problems.append("Only one innings is on this photo: add the other team's innings (✏️ Edit scorecard) if you have it.")
    limit_balls = _overs_balls(card.get("overs_limit"))
    for item in innings:
        team = str(item.get("team") or "Innings")
        wickets = item.get("wickets")
        if isinstance(wickets, int) and wickets > 10:
            problems.append(f"{team}: {wickets} wickets is more than 10.")
        balls = _overs_balls(item.get("overs"))
        if balls is not None and limit_balls and balls > limit_balls:
            problems.append(f"{team}: {item.get('overs')} overs is more than the {card.get('overs_limit')}-over limit.")
        detail_numbers = [int(n) for n in re.findall(r"\d+", str(item.get("extras_detail") or ""))]
        if isinstance(item.get("extras"), int) and detail_numbers and item["extras"] - sum(detail_numbers) > 2:
            problems.append(
                f"{team}: the extras written on the card ({item.get('extras_detail')}) add up to {sum(detail_numbers)}, "
                f"but extras says {item['extras']}. A batter's runs may have been misread."
            )
        batting = [row for row in item.get("batting") or [] if isinstance(row, dict)]
        bat_runs = [row.get("runs") for row in batting]
        if item.get("runs") is not None and batting and all(isinstance(value, int) for value in bat_runs):
            extras = item.get("extras") if isinstance(item.get("extras"), int) else 0
            added = sum(bat_runs) + extras
            if added != item["runs"]:
                problems.append(f"{team}: batters' runs plus extras make {added}, but the total says {item['runs']}.")
        if isinstance(wickets, int) and batting:
            outs = sum(1 for row in batting if row.get("dismissal") and not row.get("not_out"))
            if outs and outs > wickets + 1:
                problems.append(f"{team}: {outs} batters are out but the score shows {wickets} wickets.")
    return problems


def find_duplicates(
    archives: list[dict[str, Any]],
    record: dict[str, Any],
    card_for: Callable[[dict[str, Any]], dict[str, Any]],
) -> list[dict[str, Any]]:
    """Earlier uploads that look like the same scorecard as `record`."""
    found: list[dict[str, Any]] = []
    fingerprint = str(record.get("image_fingerprint") or "")
    try:
        signature = match_signature(card_for(record))
    except Exception:
        signature = ""
    for other in archives:
        if not isinstance(other, dict) or other.get("id") == record.get("id"):
            continue
        if str(other.get("status") or "").lower() in {"rejected", "duplicate"}:
            continue
        reason = ""
        if record.get("file_hash") and other.get("file_hash") == record.get("file_hash"):
            reason = "Same photo file"
        elif fingerprint and other.get("image_fingerprint") and fingerprint_distance(fingerprint, str(other["image_fingerprint"])) <= FINGERPRINT_SAME:
            reason = "Same photo (saved again)"
        elif signature:
            try:
                if match_signature(card_for(other)) == signature:
                    reason = "Same date, teams and scores"
            except Exception:
                reason = ""
        if reason:
            found.append({"id": other.get("id"), "file_name": other.get("original_file_name") or other.get("file_name"), "status": other.get("status"), "reason": reason})
    return found


def llm_same_match(text_a: str, text_b: str, *, model: str, base_url: str = "http://127.0.0.1:11434", timeout: float = 20.0) -> bool | None:
    """Ask the local Ollama model whether two scorecard texts are the same match. None = no answer."""
    if not (text_a.strip() and text_b.strip() and model):
        return None
    prompt = (
        "Two cricket scorecards were read from photos. Are they the SAME match (same date, same teams, same scores)? "
        'Answer only JSON like {"same": true} or {"same": false}.\n\nScorecard A:\n'
        + text_a[:2500]
        + "\n\nScorecard B:\n"
        + text_b[:2500]
    )
    body = json.dumps({"model": model, "prompt": prompt, "stream": False, "format": "json", "options": {"temperature": 0}}).encode()
    try:
        request = urllib.request.Request(f"{base_url.rstrip('/')}/api/generate", data=body, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(request, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
        answer = json.loads(str(payload.get("response") or "{}"))
        same = answer.get("same")
        return same if isinstance(same, bool) else None
    except Exception:
        return None


def duplicate_groups(
    archives: list[dict[str, Any]],
    card_for: Callable[[dict[str, Any]], dict[str, Any]],
) -> list[dict[str, Any]]:
    """Groups of uploads that are the same scorecard, for the site-admin clean-up report.

    In each group the 'keep' upload is the approved one (else the one with most detail, else the oldest)."""
    items = [item for item in archives if isinstance(item, dict) and str(item.get("status") or "").lower() not in {"rejected", "duplicate"}]
    parent = {str(item.get("id")): str(item.get("id")) for item in items}
    reasons: dict[str, set[str]] = {key: set() for key in parent}

    def root(key: str) -> str:
        while parent[key] != key:
            parent[key] = parent[parent[key]]
            key = parent[key]
        return key

    def join(a: str, b: str, reason: str) -> None:
        ra, rb = root(a), root(b)
        if ra != rb:
            parent[rb] = ra
        reasons[a].add(reason)
        reasons[b].add(reason)

    by_key: dict[tuple[str, str], str] = {}
    cards: dict[str, dict[str, Any]] = {}
    for item in items:
        key = str(item.get("id"))
        try:
            cards[key] = card_for(item)
        except Exception:
            cards[key] = {}
        for kind, value in (
            ("hash", str(item.get("file_hash") or "")),
            ("name", _file_stem(item)),
            ("match", match_signature(cards[key])),
        ):
            if not value:
                continue
            label = {"hash": "Same photo file", "name": "Same file name (please check)", "match": "Same date, teams and scores"}[kind]
            if (kind, value) in by_key:
                join(by_key[(kind, value)], key, label)
            else:
                by_key[(kind, value)] = key
    prints = [(str(item.get("id")), str(item.get("image_fingerprint") or "")) for item in items if item.get("image_fingerprint")]
    for index, (key, fingerprint) in enumerate(prints):
        for other_key, other_print in prints[index + 1 :]:
            if fingerprint_distance(fingerprint, other_print) <= FINGERPRINT_SAME:
                join(key, other_key, "Same photo (saved again)")

    groups: dict[str, list[dict[str, Any]]] = {}
    for item in items:
        groups.setdefault(root(str(item.get("id"))), []).append(item)

    def keep_rank(item: dict[str, Any]) -> tuple[int, int, str]:
        approved = 1 if str(item.get("status") or "").lower() in {"approved", "applied to match"} else 0
        card = cards.get(str(item.get("id"))) or {}
        detail = sum(len(inn.get("batting") or []) for inn in card.get("innings") or [] if isinstance(inn, dict))
        return (approved, detail, "~" + str(item.get("created_at") or ""))

    report = []
    for members in groups.values():
        if len(members) < 2:
            continue
        approved_or_detailed = sorted(members, key=lambda item: (-keep_rank(item)[0], -keep_rank(item)[1], str(item.get("created_at") or "")))
        keep = approved_or_detailed[0]
        card = cards.get(str(keep.get("id"))) or {}
        report.append(
            {
                "keep": _brief(keep, card),
                "duplicates": [_brief(item, cards.get(str(item.get("id"))) or {}) for item in approved_or_detailed[1:]],
                "reasons": sorted({reason for item in members for reason in reasons[str(item.get("id"))]}),
            }
        )
    report.sort(key=lambda group: -len(group["duplicates"]))
    return report


def _file_stem(item: dict[str, Any]) -> str:
    """'IMG_3261' from IMG_3261.HEIC / IMG_3261.png / IMG_3261.jpg (phone photo names only).
    The app's own random upload names (e.g. 'dabf3eff84.jpeg') are never matched by name."""
    name = str(item.get("original_file_name") or item.get("file_name") or "").strip()
    stem = name.rsplit(".", 1)[0].strip().lower()
    if not stem or re.fullmatch(r"[0-9a-f]{10}", stem):
        return ""
    return re.sub(r"[^a-z0-9 ]", "", stem)


def _brief(item: dict[str, Any], card: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": item.get("id"),
        "file_name": item.get("original_file_name") or item.get("file_name"),
        "status": item.get("status"),
        "created_at": item.get("created_at"),
        "club_name": item.get("club_name"),
        "title": card.get("title") or "",
        "date": card.get("date") or "",
        "photo_url": item.get("preview_url") or "",
    }


def card_summary(card: dict[str, Any]) -> str:
    """Short text of a digital scorecard for the AI duplicate check: date, teams, totals, batters' runs."""
    if not card:
        return ""
    lines = [f"Date: {card.get('date') or 'not written'}", f"Title: {card.get('title') or ''}"]
    for inn in card.get("innings") or []:
        if not isinstance(inn, dict):
            continue
        total = f"{inn.get('runs')}/{inn.get('wickets')}" if inn.get("runs") is not None else "no total"
        lines.append(f"{inn.get('team') or 'Unknown team'}: {total} in {inn.get('overs') or '?'} overs")
        batters = [
            f"{row.get('name')} {row.get('runs')}"
            for row in inn.get("batting") or []
            if isinstance(row, dict) and row.get("name") and row.get("runs") not in (None, "")
        ]
        if batters:
            lines.append("  Batters: " + ", ".join(batters[:11]))
    return "\n".join(lines)


def ai_candidates(record: dict[str, Any], others: list[dict[str, Any]], card_for: Callable[[dict[str, Any]], dict[str, Any]], limit: int = 4) -> list[dict[str, Any]]:
    """Other uploads worth asking the AI about: same date, or a shared team with a total within 10 runs."""
    try:
        card = card_for(record)
    except Exception:
        return []
    date = str(card.get("date") or "")
    teams = {_name(inn.get("team")) for inn in card.get("innings") or [] if isinstance(inn, dict) and inn.get("team")}
    totals = [inn.get("runs") for inn in card.get("innings") or [] if isinstance(inn, dict) and isinstance(inn.get("runs"), int)]
    picked = []
    for other in others:
        if not isinstance(other, dict) or other.get("id") == record.get("id"):
            continue
        if str(other.get("status") or "").lower() in {"rejected", "duplicate"}:
            continue
        try:
            other_card = card_for(other)
        except Exception:
            continue
        other_teams = {_name(inn.get("team")) for inn in other_card.get("innings") or [] if isinstance(inn, dict) and inn.get("team")}
        other_totals = [inn.get("runs") for inn in other_card.get("innings") or [] if isinstance(inn, dict) and isinstance(inn.get("runs"), int)]
        same_day = bool(date) and str(other_card.get("date") or "") == date
        close_total = any(abs(a - b) <= 10 for a in totals for b in other_totals)
        if same_day or (teams & other_teams and close_total):
            picked.append(other)
        if len(picked) >= limit:
            break
    return picked
