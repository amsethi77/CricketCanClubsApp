"""How often is the AI scorecard reader right? (Nov 18 2026, Amit: "accuracy is 60-70% today, it should keep learning
and reach 90%+"). README "AI accuracy (Admin Center)".

Every time a person fixes a card the AI read and saves it, the AI's own reading (kept in ai_read_json) is compared
field by field with the fixed card: batter names, runs, balls, 4s, 6s, bowler names, overs, runs, wickets, innings
totals, extras, date, captains, man of the match. No AI call is made - this only compares what is already saved, so
it costs nothing and the % moves as the reader learns (names it was taught, worked examples).

The same comparison as scripts/ai_accuracy.py (that script reads the photos AGAIN with today's reader).
"""
from __future__ import annotations

import difflib
import json
import re
from typing import Any

FIELD_GROUPS = {
    "Names": ("batter name", "bowler name", "captain", "man of the match", "batting team"),
    "Batting numbers": ("batter runs", "batter balls", "batter fours", "batter sixes", "batter ones", "batter twos", "batter threes", "batter dots"),
    "Bowling numbers": ("bowler overs", "bowler maidens", "bowler runs_conceded", "bowler wickets"),
    "Totals": ("innings runs", "innings wickets", "innings overs", "extras", "innings number", "match date"),
}


def norm(value: Any) -> str:
    return re.sub(r"[^a-z0-9]", "", str(value or "").lower())


def num(value: Any) -> float | None:
    text = str(value if value is not None else "").strip()
    try:
        return float(text) if text else None
    except ValueError:
        return None


def overs_text(summary: Any) -> str | None:
    summary = summary or {}
    overs = str(summary.get("overs") if summary.get("overs") is not None else "").strip()
    if not overs:
        return None
    whole, _, part = overs.partition(".")
    balls = part[:1] if part.strip("0") else str(summary.get("balls") or "")
    balls = balls if balls.isdigit() and 0 < int(balls) < 6 else "0"
    try:
        return f"{int(float(whole or 0))}.{balls}"
    except ValueError:
        return None


def same_name(a: Any, b: Any) -> bool:
    x, y = norm(a), norm(b)
    return bool(x and y and (x == y or difflib.SequenceMatcher(None, x, y).ratio() >= 0.85))


class Score:
    def __init__(self) -> None:
        self.fields: dict[str, list[int]] = {}
        self.misses: list[dict[str, str]] = []

    def add(self, field: str, truth: Any, read: Any, label: str) -> None:
        if truth in (None, "", []):
            return  # nothing to compare against
        right = (num(truth) == num(read)) if num(truth) is not None else same_name(truth, read)
        ok, total = self.fields.setdefault(field, [0, 0])
        self.fields[field] = [ok + int(right), total + 1]
        if not right:
            self.misses.append({"where": label, "field": field, "card": str(truth), "ai": "" if read is None else str(read)})

    def merge(self, other: "Score") -> None:
        for field, (ok, total) in other.fields.items():
            mine = self.fields.setdefault(field, [0, 0])
            self.fields[field] = [mine[0] + ok, mine[1] + total]

    @property
    def right(self) -> int:
        return sum(ok for ok, _ in self.fields.values())

    @property
    def checked(self) -> int:
        return sum(total for _, total in self.fields.values())


def _row_name(row: dict[str, Any]) -> Any:
    return (row.get("player") or {}).get("name") if isinstance(row.get("player"), dict) else row.get("name")


def compare(truth: dict[str, Any], read: dict[str, Any]) -> Score:
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
        label = f"Innings {index + 1} ({inn.get('batting_team') or '?'})"
        other = other or {}
        score.add("innings number", inn.get("inning_number"), other.get("inning_number"), label)
        score.add("batting team", inn.get("batting_team"), other.get("batting_team"), label)
        for key in ("runs", "wickets"):
            score.add(f"innings {key}", (inn.get("summary") or {}).get(key), (other.get("summary") or {}).get(key), label)
        score.add("innings overs", overs_text(inn.get("summary")), overs_text(other.get("summary")), label)
        score.add("extras", (inn.get("extras") or {}).get("total"), (other.get("extras") or {}).get("total"), label)
        read_bat = [item for item in other.get("batting") or [] if isinstance(item, dict)]
        for row in inn.get("batting") or []:
            if not isinstance(row, dict) or not _row_name(row):
                continue
            name = _row_name(row)
            match = next((item for item in read_bat if same_name(name, _row_name(item))), None)
            score.add("batter name", name, _row_name(match) if match else None, label)
            if match:
                read_bat.remove(match)
                for key in ("runs", "balls", "fours", "sixes", "ones", "twos", "threes", "dots"):
                    score.add(f"batter {key}", row.get(key), match.get(key), f"{label} · {name}")
        read_bowl = [item for item in other.get("bowling") or [] if isinstance(item, dict)]
        for row in inn.get("bowling") or []:
            if not isinstance(row, dict) or not _row_name(row):
                continue
            name = _row_name(row)
            match = next((item for item in read_bowl if same_name(name, _row_name(item))), None)
            score.add("bowler name", name, _row_name(match) if match else None, label)
            if match:
                read_bowl.remove(match)
                for key in ("overs", "maidens", "runs_conceded", "wickets"):
                    score.add(f"bowler {key}", row.get(key), match.get(key), f"{label} · {name}")
    return score


def _json(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    try:
        parsed = json.loads(str(value or ""))
    except (TypeError, ValueError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def is_ai_reading(template: dict[str, Any]) -> bool:
    meta = template.get("meta") if isinstance(template.get("meta"), dict) else {}
    return str(meta.get("source") or "").startswith("ai:") or str(meta.get("processed_by") or "").startswith("Read by AI")


def ai_reading(upload: dict[str, Any]) -> dict[str, Any]:
    """The AI's own reading of this card ({} if there is none)."""
    for key in ("ai_read_json", "review_source_json"):
        template = _json(upload.get(key))
        if template.get("innings") and is_ai_reading(template):
            return template
    return {}


def group_scores(fields: dict[str, list[int]]) -> list[dict[str, Any]]:
    rows = []
    for group, names in FIELD_GROUPS.items():
        ok = sum(fields.get(name, [0, 0])[0] for name in names)
        total = sum(fields.get(name, [0, 0])[1] for name in names)
        if total:
            rows.append({"group": group, "right": ok, "checked": total, "percent": round(100 * ok / total, 1)})
    return rows


def field_scores(fields: dict[str, list[int]]) -> list[dict[str, Any]]:
    return sorted(
        ({"field": name, "right": ok, "checked": total, "percent": round(100 * ok / total, 1)} for name, (ok, total) in fields.items() if total),
        key=lambda row: (row["percent"], -row["checked"]),
    )
