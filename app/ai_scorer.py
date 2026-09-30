"""
AI Live Scorer (Premium): turns what the scorer says into structured ball events.

    "Four."                         -> [RUNS 4]
    "Wide, then two runs"           -> [WIDE 1, RUNS 2]
    "no ball and a six"             -> [NO_BALL + 6 off the bat]
    "two leg byes then a dot"       -> [LEG_BYE 2, RUNS 0]
    "caught by Rahul"               -> [WICKET caught, fielder Rahul]

The AI only produces events. The normal scoring engine (/api/matches/{id}/scorebook/ball)
does all cricket maths: totals, overs, strike rotation, bowler changes.
Documented in README.md -> "Subscriptions and plans" -> "AI Live Scorer".
"""

from __future__ import annotations

import re
from typing import Any

_NUMBER_WORDS = {
    "zero": 0, "nil": 0, "no": 0, "one": 1, "a": 1, "an": 1, "single": 1, "two": 2, "double": 2, "couple": 2,
    "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7,
}
_SPLIT = re.compile(r"\s*(?:,|;|\.|\bthen\b|\band then\b|\bafter that\b|\bnext ball\b|\bfollowed by\b|\bnext\b)\s*")
_WICKET_KINDS = [
    (re.compile(r"\bcaught(?: and)? bowled\b|\bc ?& ?b\b"), "caught_and_bowled"),
    (re.compile(r"\bcaught\b|\bcatch\b|\bholds? it\b|\btaken\b"), "caught"),
    (re.compile(r"\bl\s?b\s?w\b|\bleg before\b"), "lbw"),
    (re.compile(r"\brun ?out\b"), "run_out"),
    (re.compile(r"\bstumped\b"), "stumped"),
    (re.compile(r"\bhit ?wicket\b"), "hit_wicket"),
    (re.compile(r"\bbowled\b|\bclean bowled\b|\bcleaned up\b|\bstumps? (?:broken|flying)\b"), "bowled"),
    (re.compile(r"\bwicket\b|\bout\b|\bgone\b|\bdismissed\b"), "caught"),
]


def _num(token: str) -> int | None:
    token = token.strip().lower()
    if token.isdigit():
        return int(token)
    return _NUMBER_WORDS.get(token)


def _count_before(text: str, noun: str) -> int | None:
    match = re.search(rf"\b(\d+|zero|one|a|an|two|three|four|five|six|seven)\s+(?:more\s+)?{noun}", text)
    return _num(match.group(1)) if match else None


def _runs_in(text: str) -> int | None:
    """Runs off the bat mentioned in a clause, or None."""
    if re.search(r"\b(six|maximum|sixer)\b", text) and not re.search(r"\bsix (?:runs|byes|leg byes|wides)\b", text):
        return 6
    if re.search(r"\b(four|boundary|fourer)\b", text) and not re.search(r"\bfour (?:runs|byes|leg byes|wides|overs)\b", text):
        return 4
    match = re.search(r"\b(\d|zero|one|two|three|four|five|six|seven)\s+runs?\b", text)
    if match:
        return _num(match.group(1))
    if re.search(r"\b(dot|no run|nothing|defended|blocked|beaten|left alone|leave)\b", text):
        return 0
    if re.search(r"\b(single|quick one|one run)\b", text):
        return 1
    if re.search(r"\b(double|couple|two)\b", text):
        return 2
    if re.search(r"\b(three|triple)\b", text):
        return 3
    match = re.fullmatch(r"\s*(\d)\s*", text)
    if match:
        return int(match.group(1))
    return None


def _fielder(text: str, original: str) -> str:
    match = re.search(r"\b(?:caught|catch|stumped|run ?out)\s+(?:by|at \w+ by)\s+([a-z][a-z .'-]{1,40})", text)
    if not match:
        return ""
    name = re.split(r"\b(?:at|in|off|on|the|and)\b", match.group(1))[0].strip(" .")
    # Use the scorer's own capitalisation when we can find it.
    found = re.search(re.escape(name), original, re.IGNORECASE)
    return (found.group(0) if found else name.title()).strip()


def parse_clause(clause: str) -> list[dict[str, Any]]:
    original = clause.strip()
    text = original.lower().strip()
    if not text:
        return []
    if re.fullmatch(r"(undo|scratch that|cancel( that)?|delete last( ball)?)", text):
        return [{"type": "UNDO"}]

    # Wides: "wide", "two wides", "wide and four" (wide + 4 byes)
    if re.search(r"\bwides?\b", text):
        count = _count_before(text, r"wides?")
        rest = re.sub(r"\b(?:\d+|a|an|one|two|three|four|five)\s+wides?\b|\bwides?\b", " ", text).strip()
        if count and count > 1:
            total = count  # "five wides"
        else:
            total = 1 + (_runs_in(rest) or 0 if rest else 0)  # "wide and four" -> 5 wides
        return [{"type": "WIDE", "extras_type": "wide", "extras_runs": max(1, total), "runs_bat": 0}]

    # No ball, optionally with runs off the bat
    if re.search(r"\bno[ -]?balls?\b|\bfree hit\b", text):
        rest = re.sub(r"\bno[ -]?balls?\b", " ", text)
        runs = _runs_in(rest) or 0
        return [{"type": "NO_BALL", "extras_type": "no_ball", "extras_runs": 1, "runs_bat": runs}]

    # Leg byes / byes
    if re.search(r"\bleg[ -]?byes?\b", text):
        count = _count_before(text, r"leg[ -]?byes?") or _runs_in(re.sub(r"\bleg[ -]?byes?\b", " ", text)) or 1
        return [{"type": "LEG_BYE", "extras_type": "leg_bye", "extras_runs": max(1, count), "runs_bat": 0}]
    if re.search(r"\bbyes?\b", text):
        count = _count_before(text, r"byes?") or _runs_in(re.sub(r"\bbyes?\b", " ", text)) or 1
        return [{"type": "BYE", "extras_type": "bye", "extras_runs": max(1, count), "runs_bat": 0}]

    # Wickets (checked before runs: "caught at long on" etc.)
    for pattern, kind in _WICKET_KINDS:
        if pattern.search(text) and not re.search(r"\bnot out\b|\bdropped\b|\bmissed\b", text):
            event: dict[str, Any] = {"type": "WICKET", "wicket": True, "wicket_type": kind, "runs_bat": 0}
            fielder = _fielder(text, original)
            if fielder:
                event["fielder"] = fielder
            if kind == "run_out":
                runs = _runs_in(re.sub(r"\brun ?out\b", " ", text))
                if runs:
                    event["runs_bat"] = runs
            return [event]

    runs = _runs_in(text)
    if runs is not None and 0 <= runs <= 7:
        return [{"type": "RUNS", "runs_bat": runs, "extras_type": "none", "extras_runs": 0}]
    return []


def interpret(text: str) -> dict[str, Any]:
    """Split a spoken/typed phrase into clauses and turn each into ball events."""
    raw = str(text or "").strip()
    events: list[dict[str, Any]] = []
    unknown: list[str] = []
    for clause in [part for part in _SPLIT.split(raw) if part and part.strip()]:
        # "two dots" / "three singles" -> repeat
        repeat = re.fullmatch(r"\s*(two|three|four|five|six|\d)\s+(dots|singles|dot balls)\s*", clause.lower())
        if repeat:
            times = _num(repeat.group(1)) or 1
            runs = 0 if "dot" in repeat.group(2) else 1
            events.extend({"type": "RUNS", "runs_bat": runs, "extras_type": "none", "extras_runs": 0} for _ in range(min(times, 6)))
            continue
        parsed = parse_clause(clause)
        if parsed:
            for event in parsed:
                event["heard"] = clause.strip()
            events.extend(parsed)
        else:
            unknown.append(clause.strip())
    return {"text": raw, "events": events, "unknown": unknown}


def describe(event: dict[str, Any]) -> str:
    kind = event.get("type")
    if kind == "RUNS":
        runs = int(event.get("runs_bat") or 0)
        return "dot ball" if runs == 0 else "FOUR" if runs == 4 else "SIX" if runs == 6 else f"{runs} run{'s' if runs != 1 else ''}"
    if kind == "WIDE":
        return f"wide ({event.get('extras_runs')})"
    if kind == "NO_BALL":
        return f"no ball + {event.get('runs_bat') or 0}"
    if kind == "BYE":
        return f"{event.get('extras_runs')} bye{'s' if int(event.get('extras_runs') or 1) != 1 else ''}"
    if kind == "LEG_BYE":
        return f"{event.get('extras_runs')} leg bye{'s' if int(event.get('extras_runs') or 1) != 1 else ''}"
    if kind == "WICKET":
        who = f" by {event['fielder']}" if event.get("fielder") else ""
        return f"WICKET ({str(event.get('wicket_type') or 'out').replace('_', ' ')}{who})"
    if kind == "UNDO":
        return "undo last ball"
    return str(kind or "")


def validate(events: list[dict[str, Any]], summary: dict[str, Any], overs_limit: int, status: str = "") -> tuple[list[dict[str, Any]], list[str]]:
    """Check events against the current innings state; returns (accepted, problems) plus a projected score."""
    problems: list[str] = []
    accepted: list[dict[str, Any]] = []
    runs = int(summary.get("runs") or 0)
    wickets = int(summary.get("wickets") or 0)
    legal = int(summary.get("legal_balls") or 0)
    if str(status).lower() == "completed":
        return [], ["This innings is already complete."]
    for event in events:
        if event.get("type") == "UNDO":
            accepted.append(event)
            continue
        if wickets >= 10 or legal >= overs_limit * 6:
            problems.append("The innings is over, so the rest was ignored.")
            break
        extras_type = event.get("extras_type") or "none"
        runs += int(event.get("runs_bat") or 0) + int(event.get("extras_runs") or 0)
        if extras_type not in {"wide", "no_ball"}:
            legal += 1
        if event.get("wicket"):
            wickets += 1
        event["projected"] = f"{runs}/{wickets} ({legal // 6}.{legal % 6})"
        accepted.append(event)
    return accepted, problems
