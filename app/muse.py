"""AI Muse: the club's chat agent.

AI Muse understands a few "actions" on top of the normal assistant chat:

* Score entry by text or voice, e.g.
  "Heartlake 145/6 in 20 overs, Imran XI 120/9. Heartlake won by 25 runs. Amit S 45 off 30, Nick 3 wickets"
  -> a draft scorecard the admin confirms before it is saved.
* Availability requests, e.g. "Ask everyone for availability for the next match"
  -> an in-app notification to every player of the club.
* Availability summary, e.g. "Who is available for the next match?"
* Scorecard photo upload is handled by the chat UI (it posts to /api/scorecards/upload).

It also owns the in-app notifications (bell icon) and the live score alerts
(match started, wickets, fifties/hundreds, innings finished).

See README.md -> "AI Muse and notifications" for how it all fits together.
"""

from __future__ import annotations

import json
import re
import sqlite3
import uuid
from datetime import date, datetime, timezone
from typing import Any, Callable


# ---------------------------------------------------------------------------
# Notifications (stored in the main SQLite database)
# ---------------------------------------------------------------------------
NOTIFICATION_SCHEMA = """
CREATE TABLE IF NOT EXISTS app_notifications (
  id TEXT PRIMARY KEY,
  club_id TEXT,
  target_user_id INTEGER,
  kind TEXT NOT NULL,
  title TEXT NOT NULL,
  body TEXT,
  link TEXT,
  match_id TEXT,
  created_by TEXT,
  created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_app_notifications_club ON app_notifications(club_id, created_at);
CREATE TABLE IF NOT EXISTS app_notification_reads (
  notification_id TEXT NOT NULL,
  user_id INTEGER NOT NULL,
  read_at TEXT NOT NULL,
  PRIMARY KEY (notification_id, user_id)
);
"""


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def ensure_notification_schema(connection: sqlite3.Connection) -> None:
    connection.executescript(NOTIFICATION_SCHEMA)


def create_notification(
    connection: sqlite3.Connection,
    *,
    club_id: str,
    kind: str,
    title: str,
    body: str = "",
    link: str = "",
    match_id: str = "",
    target_user_id: int | None = None,
    created_by: str = "",
) -> str:
    ensure_notification_schema(connection)
    notification_id = uuid.uuid4().hex[:12]
    connection.execute(
        """
        INSERT INTO app_notifications (id, club_id, target_user_id, kind, title, body, link, match_id, created_by, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (notification_id, club_id, target_user_id, kind, title, body, link, match_id, created_by, _now()),
    )
    return notification_id


def list_notifications(connection: sqlite3.Connection, user_id: int, club_ids: list[str], limit: int = 30) -> list[dict[str, Any]]:
    ensure_notification_schema(connection)
    placeholders = ",".join("?" for _ in club_ids) or "''"
    rows = connection.execute(
        f"""
        SELECT n.*, r.read_at
        FROM app_notifications n
        LEFT JOIN app_notification_reads r ON r.notification_id = n.id AND r.user_id = ?
        WHERE n.target_user_id = ? OR (n.target_user_id IS NULL AND n.club_id IN ({placeholders}))
        ORDER BY n.created_at DESC
        LIMIT ?
        """,
        (user_id, user_id, *club_ids, limit),
    ).fetchall()
    return [
        {
            "id": row["id"],
            "club_id": row["club_id"] or "",
            "kind": row["kind"],
            "title": row["title"],
            "body": row["body"] or "",
            "link": row["link"] or "",
            "match_id": row["match_id"] or "",
            "created_at": row["created_at"],
            "read": bool(row["read_at"]),
        }
        for row in rows
    ]


def mark_notifications_read(connection: sqlite3.Connection, user_id: int, ids: list[str]) -> int:
    ensure_notification_schema(connection)
    count = 0
    for notification_id in ids:
        cursor = connection.execute(
            "INSERT OR IGNORE INTO app_notification_reads (notification_id, user_id, read_at) VALUES (?, ?, ?)",
            (notification_id, user_id, _now()),
        )
        count += cursor.rowcount or 0
    return count


# ---------------------------------------------------------------------------
# Live score alerts
# ---------------------------------------------------------------------------
def live_score_events(
    match: dict[str, Any],
    innings: dict[str, Any],
    before: dict[str, Any],
    after: dict[str, Any],
    ball: dict[str, Any],
) -> list[tuple[str, str, str]]:
    """Compare the innings summary before/after a ball and return (kind, title, body) alerts."""
    events: list[tuple[str, str, str]] = []
    batting = str(innings.get("batting_team") or match.get("club_name") or "Batting side")
    opponent = str(match.get("opponent") or "Opponent")
    fixture = f"{match.get('club_name') or 'Club'} vs {opponent}"
    score = f"{after.get('runs', 0)}/{after.get('wickets', 0)} ({after.get('overs', '0.0')} ov)"

    first_ball_of_match = int(innings.get("inning_number") or 1) == 1 and int(before.get("legal_balls") or 0) == 0 and not before.get("runs") and not before.get("wickets")
    if first_ball_of_match:
        events.append(("live_start", f"Live now: {fixture}", "The match has started. Follow it ball by ball."))
    if int(innings.get("inning_number") or 1) == 2 and int(before.get("legal_balls") or 0) == 0 and not before.get("runs"):
        target = innings.get("target_runs")
        events.append(("live_innings", f"Second innings under way: {fixture}", f"{batting} need {target} to win." if target else f"{batting} are batting."))

    if int(after.get("wickets") or 0) > int(before.get("wickets") or 0):
        out = str(ball.get("wicket_player") or ball.get("striker") or "Batter")
        how = str(ball.get("wicket_type") or "out").replace("_", " ")
        bowler = str(ball.get("bowler") or "")
        events.append(("live_wicket", f"Wicket! {out} {how}{f' ({bowler})' if bowler else ''}", f"{batting} {score} · {fixture}"))

    # Milestones for the striker
    striker = str(ball.get("striker") or "")
    if striker:
        before_runs = _batter_runs(before, striker)
        after_runs = _batter_runs(after, striker)
        for milestone in (50, 100):
            if before_runs < milestone <= after_runs:
                events.append(("live_milestone", f"{striker} reaches {milestone}!", f"{batting} {score} · {fixture}"))

    status_before = str(before.get("status") or "")
    if str(innings.get("status") or "") == "Completed" and status_before != "Completed":
        events.append(("live_innings_end", f"Innings over: {batting} {after.get('runs', 0)}/{after.get('wickets', 0)}", fixture))
    return events


def _batter_runs(summary: dict[str, Any], name: str) -> int:
    for row in summary.get("batting", []) or []:
        if str(row.get("player_name") or "") == name:
            return int(row.get("runs") or 0)
    return 0


# ---------------------------------------------------------------------------
# Score message parsing ("Heartlake 145/6 in 20 overs ...")
# ---------------------------------------------------------------------------
_TEAM_SCORE = re.compile(
    r"(?P<team>[A-Za-z][A-Za-z0-9 .&'\-]{1,40}?)\s*(?:[:\-–]\s*|\s+(?:scored|made|posted|were|got|reached)\s+)?"
    r"(?P<runs>\d{1,3})\s*(?:/|-|for|all\s*out)\s*(?P<wkts>\d{1,2})?"
    r"(?:\s*(?:\(|in|off|from)\s*(?P<overs>\d{1,2}(?:\.\d)?)\s*(?:overs?|ov|o)?\)?)?",
    re.IGNORECASE,
)
_ALL_OUT = re.compile(r"(?P<team>[A-Za-z][A-Za-z0-9 .&'\-]{1,40}?)\s+(?:were\s+)?all\s*out\s+(?:for\s+)?(?P<runs>\d{1,3})", re.IGNORECASE)
_RESULT = re.compile(
    r"(?P<winner>[A-Za-z][A-Za-z0-9 .&'\-]{1,40}?)\s+won\s+by\s+(?P<margin>\d{1,3})\s*(?P<unit>runs?|wickets?|wkts?)",
    re.IGNORECASE,
)
_BAT = re.compile(
    r"(?P<name>[A-Za-z][A-Za-z.'\-]*(?:\s+[A-Za-z][A-Za-z.'\-]*){0,2})\s+(?P<runs>\d{1,3})(?P<notout>\*)?\s*(?:runs?\s*)?(?:\(|off|from)\s*(?P<balls>\d{1,3})\s*(?:balls?|b)?\)?",
    re.IGNORECASE,
)
_BAT_NO_BALLS = re.compile(
    r"(?P<name>[A-Za-z][A-Za-z.'\-]*(?:\s+[A-Za-z][A-Za-z.'\-]*){0,2})\s+(?:scored|made|hit)\s+(?P<runs>\d{1,3})(?P<notout>\*)?",
    re.IGNORECASE,
)
_WKTS = re.compile(
    r"(?P<name>[A-Za-z][A-Za-z.'\-]*(?:\s+[A-Za-z][A-Za-z.'\-]*){0,2})\s+(?:took\s+|got\s+)?(?P<wkts>\d{1,2})\s*(?:wickets?|wkts?|w\b|for\s+\d{1,3})",
    re.IGNORECASE,
)
_CATCHES = re.compile(
    r"(?P<name>[A-Za-z][A-Za-z.'\-]*(?:\s+[A-Za-z][A-Za-z.'\-]*){0,2})\s+(?:took\s+)?(?P<n>\d{1,2})\s*catch(?:es)?",
    re.IGNORECASE,
)
_STOP_WORDS = {"and", "with", "by", "in", "off", "the", "for", "won", "score", "scores", "match", "vs", "v", "against"}


def _clean_name(value: str) -> str:
    words = [word for word in re.split(r"\s+", str(value or "").strip()) if word]
    while words and words[0].lower() in _STOP_WORDS:
        words.pop(0)
    return " ".join(words).strip(" .,-")


def looks_like_score_message(text: str) -> bool:
    lowered = text.lower()
    return bool(re.search(r"\b\d{1,3}\s*(?:/|-|for)\s*\d{1,2}\b", lowered) or " all out" in lowered) and (
        "won by" in lowered or "overs" in lowered or re.search(r"\b\d{1,3}\s*/\s*\d{1,2}\b", lowered) is not None
    )


_VERBS = {"took", "got", "scored", "made", "hit", "had", "with", "picked", "grabbed"}
_WE_WORDS = {"we", "us", "our team", "our side", "ours", "we all"}


def _segments(raw: str) -> list[str]:
    """Split a message into clauses so one clause = one team score or one player figure."""
    text = re.sub(r"(?<=\d)\.(?=\d)", "\u2024", raw)  # protect overs like 19.4
    parts = re.split(r"[,;!?\n]|\.(?=\s|$)|\s+and\s+|\s+while\s+|\s+but\s+", text, flags=re.IGNORECASE)
    return [part.replace("\u2024", ".").strip() for part in parts if part and part.strip()]


def parse_score_message(
    text: str,
    club_names: list[str],
    resolve_player: Callable[[str], str | None],
) -> dict[str, Any]:
    """Pull team totals, result and player figures out of a free-text / voice message."""
    raw = " ".join(str(text or "").split())
    segments = _segments(raw)
    teams: list[dict[str, Any]] = []
    result = ""
    players: dict[str, dict[str, Any]] = {}

    def resolve_loose(name: str) -> str | None:
        """Try the name, then drop leading words ('wickets amit' -> 'amit') and trailing verbs."""
        words = [w for w in _clean_name(name).split() if w.lower() not in _VERBS]
        for start in range(len(words)):
            candidate = " ".join(words[start:])
            resolved = resolve_player(candidate) if candidate else None
            if resolved:
                return resolved
        return None

    def entry(name: str) -> dict[str, Any] | None:
        resolved = resolve_loose(name)
        if not resolved:
            return None
        return players.setdefault(resolved, {"player_name": resolved, "runs": 0, "balls": 0, "wickets": 0, "catches": 0, "not_out": False})

    for segment in segments:
        result_match = _RESULT.search(segment)
        if result_match:
            winner = _clean_name(re.sub(r"^.*?\b(?:overs?|ov|wickets?|runs?)\b", "", result_match.group("winner"), flags=re.IGNORECASE)) or _clean_name(result_match.group("winner"))
            result = f"{winner} won by {result_match.group('margin')} {result_match.group('unit').lower()}"
        elif re.search(r"\b(tied|tie)\b", segment, re.IGNORECASE):
            result = "Match tied"
        elif re.search(r"\bno result\b|\babandoned\b|\bwashed out\b", segment, re.IGNORECASE):
            result = "No result"
        scan = segment[: result_match.start()] + " " + segment[result_match.end():] if result_match else segment

        for all_out in _ALL_OUT.finditer(scan):
            teams.append({"name": _clean_name(all_out.group("team")), "runs": all_out.group("runs"), "wickets": "10", "overs": ""})
        if not _ALL_OUT.search(scan):
            for team_match in _TEAM_SCORE.finditer(scan):
                if team_match.group("wkts") is None:
                    continue
                name = _clean_name(team_match.group("team"))
                if not name or name.lower() in _STOP_WORDS or resolve_loose(name):
                    continue
                teams.append({"name": name, "runs": team_match.group("runs"), "wickets": team_match.group("wkts"), "overs": team_match.group("overs") or ""})

        for bat in list(_BAT.finditer(scan)) + list(_BAT_NO_BALLS.finditer(scan)):
            row = entry(bat.group("name"))
            if row is not None and not row["runs"]:
                row["runs"] = int(bat.group("runs"))
                row["balls"] = int(bat.groupdict().get("balls") or 0)
                row["not_out"] = bool(bat.group("notout"))
        for wkts in _WKTS.finditer(scan):
            row = entry(wkts.group("name"))
            if row is not None:
                row["wickets"] = int(wkts.group("wkts"))
        for catches in _CATCHES.finditer(scan):
            row = entry(catches.group("name"))
            if row is not None:
                row["catches"] = int(catches.group("n"))

    # Which side is "our club"?
    club_keys = [re.sub(r"[^a-z0-9]", "", name.lower()) for name in club_names if name]

    def is_club(team_name: str) -> bool:
        lowered = team_name.lower().strip()
        if lowered in _WE_WORDS:
            return True
        key = re.sub(r"[^a-z0-9]", "", lowered)
        first = re.sub(r"[^a-z0-9]", "", lowered.split()[0]) if lowered.split() else ""
        return any(key and (key in club or club in key) for club in club_keys) or any(len(first) >= 4 and club.startswith(first) for club in club_keys)

    ours = next((team for team in teams if is_club(team["name"])), None)
    theirs = next((team for team in teams if team is not ours), None)
    if ours is None and teams:
        ours = teams[0]
        theirs = teams[1] if len(teams) > 1 else None
    if ours and club_names and is_club(ours["name"]):
        ours["name"] = club_names[0]
    for side in (ours, theirs):
        if side and side["name"] == side["name"].lower():
            side["name"] = side["name"].title().replace(" Xi", " XI").replace(" Cc", " CC")
    if result:
        winner = result.split(" won by ")[0].lower() if " won by " in result else ""
        if winner in _WE_WORDS and club_names:
            result = club_names[0] + result[len(winner):]

    return {
        "club_side": ours,
        "opponent_side": theirs,
        "result": result,
        "performances": list(players.values()),
        "teams_found": len(teams),
    }


# ---------------------------------------------------------------------------
# Intent detection
# ---------------------------------------------------------------------------
def detect_intent(text: str) -> str:
    lowered = f" {str(text or '').lower()} "
    if re.search(r"\b(ask|request|remind|send|notify|ping|message)\b.*\bavailab", lowered) or "availability request" in lowered:
        return "availability_request"
    if re.search(r"\b(who|how many)\b.*\b(available|availability|coming|playing)\b", lowered) or "availability summary" in lowered:
        return "availability_summary"
    if re.search(r"\b(upload|attach|add)\b.*\b(scorecard|photo|picture|image)\b", lowered):
        return "upload_help"
    if re.search(r"\b(live scor(e|ing)|start scoring|score (the|a|this|our) match|ball by ball|quick score)\b", lowered):
        return "scoring_help"
    if re.search(r"\b(notify|alert|notification)s?\b", lowered):
        return "alerts_help"
    if looks_like_score_message(lowered):
        return "score_entry"
    return "chat"


# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------
def pick_fixture(fixtures: list[dict[str, Any]], text: str, *, prefer: str = "upcoming") -> dict[str, Any] | None:
    """Find the fixture a message is about: by date, opponent name, else next upcoming / latest past."""
    lowered = str(text or "").lower()
    today = date.today().isoformat()
    date_match = re.search(r"\b(20\d{2}-\d{2}-\d{2})\b", lowered)
    if date_match:
        found = [fixture for fixture in fixtures if str(fixture.get("date") or "") == date_match.group(1)]
        if found:
            return found[0]
    by_opponent = [
        fixture
        for fixture in fixtures
        if str(fixture.get("opponent") or "").strip()
        and str(fixture.get("opponent") or "").lower().split()[0] in lowered
        and len(str(fixture.get("opponent") or "").split()[0]) >= 3
    ]
    pool = by_opponent or fixtures
    upcoming = sorted(
        [f for f in pool if str(f.get("date") or "") >= today and str(f.get("status") or "").lower() != "completed"],
        key=lambda f: str(f.get("date") or ""),
    )
    past = sorted([f for f in pool if str(f.get("date") or "") <= today], key=lambda f: str(f.get("date") or ""), reverse=True)
    if prefer == "upcoming":
        return (upcoming or past or [None])[0]
    return (past or upcoming or [None])[0]


def availability_summary(fixture: dict[str, Any], member_names: list[str]) -> dict[str, Any]:
    statuses = {str(name).strip().lower(): str(status or "").strip().lower() for name, status in (fixture.get("availability_statuses") or {}).items()}
    groups: dict[str, list[str]] = {"available": [], "maybe": [], "unavailable": [], "no response": []}
    for name in member_names:
        status = statuses.get(str(name).strip().lower(), "")
        if status.startswith("avail"):
            groups["available"].append(name)
        elif status.startswith("maybe"):
            groups["maybe"].append(name)
        elif "not" in status or status.startswith("unavail"):
            groups["unavailable"].append(name)
        else:
            groups["no response"].append(name)
    return groups


def fixture_label(fixture: dict[str, Any]) -> str:
    return f"{fixture.get('date_label') or fixture.get('date') or 'Date TBD'} vs {fixture.get('opponent') or 'Opponent'}"


def draft_to_json(draft: dict[str, Any]) -> str:
    return json.dumps(draft, sort_keys=True)
