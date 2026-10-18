"""
AI Assistant agent: turns what people say into tasks the app can carry out.

Works like an assistant that "does it for you":

    "Mark me available for Saturday"            -> mark_availability (you)
    "Rahul and Nick are out for the next match"  -> mark_availability (captain / admin)
    "Ask everyone for availability"              -> request_availability (notification)
    "Remind the players who haven't replied"     -> remind_pending
    "Who is available for Sunday?"               -> availability_summary (answers straight away)
    "Pick the best XI for the next match"        -> pick_xi (suggests, then saves on Confirm)
    "Add a match vs Imran XI on Oct 12 at 10am"  -> create_fixture
    "We are 85/3 after 12 overs"                 -> live_update (today's match)
    "Heartlake 145/6, Imran XI 120/9, we won"    -> record_result (today's match)

Every task that changes data comes back as a plan with a Confirm button; nothing is saved
until the person taps Confirm (POST /api/muse/execute), and the server checks permissions,
the plan and the "past matches are locked" rule again at that point.

Commands are understood by fast rules first. When the rules don't recognise a command and
the local LLM (Ollama) is running, the LLM is asked to pick the tool (llm_plan). Everything
else is answered by the normal LLM assistant (cricket_brain.answer_question).

Documented in MD/README.md -> "AI Assistant and notifications" -> "AI Assistant as an agent".
"""

from __future__ import annotations

import json
import re
from datetime import date, timedelta
from typing import Any, Callable

TOOLS: dict[str, str] = {
    "mark_availability": "Set Available / Maybe / Not available for the speaker or named players for a fixture. args: players (list of names or ['me']), status (available|maybe|unavailable), when (date words or opponent, optional)",
    "request_availability": "Send every player an availability request for a fixture. args: when (optional)",
    "remind_pending": "Remind players who have not replied about availability. args: when (optional)",
    "availability_summary": "Say who is available for a fixture. args: when (optional)",
    "pick_xi": "Suggest and save the best playing XI for a fixture. args: when (optional)",
    "create_fixture": "Add a fixture. args: opponent, date (YYYY-MM-DD or words), time (e.g. 10:00 AM), overs, venue",
    "live_update": "Update today's live score summary. args: runs, wickets, overs, team ('us' or 'them')",
    "record_result": "Save today's final score from a message. args: text",
    "chat": "Anything else: answer the question.",
}

_WEEKDAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
_MONTHS = {m: i for i, m in enumerate(["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], start=1)}
_STATUS_WORDS = [
    (re.compile(r"\b(not available|unavailable|can'?t (?:make it|play|come)|cannot (?:play|come)|won'?t (?:be able|make it|play)|not (?:coming|playing)|count (?:me|him|her|them) out|out)\b"), "unavailable"),
    (re.compile(r"\b(maybe|might|not sure|unsure|tentative|probably)\b"), "maybe"),
    (re.compile(r"\b(available|can play|i'?m in|count (?:me|him|her|them) in|coming|playing|in)\b"), "available"),
]


# ---------------------------------------------------------------------------
# Dates and times
# ---------------------------------------------------------------------------
def parse_when(text: str, today: date) -> date | None:
    """'today', 'tomorrow', 'saturday', 'next sunday', 'oct 12', '12 october', '2026-10-12'."""
    lowered = f" {str(text or '').lower()} "
    iso = re.search(r"\b(20\d{2})-(\d{1,2})-(\d{1,2})\b", lowered)
    if iso:
        try:
            return date(int(iso.group(1)), int(iso.group(2)), int(iso.group(3)))
        except ValueError:
            return None
    if re.search(r"\b(today|tonight)\b", lowered):
        return today
    if re.search(r"\btomorrow\b", lowered):
        return today + timedelta(days=1)
    month_first = re.search(r"\b(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?\s+(\d{1,2})(?:st|nd|rd|th)?\b", lowered)
    day_first = re.search(r"\b(\d{1,2})(?:st|nd|rd|th)?\s+(?:of\s+)?(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\b", lowered)
    found = None
    if month_first:
        found = (_MONTHS[month_first.group(1)], int(month_first.group(2)))
    elif day_first:
        found = (_MONTHS[day_first.group(2)], int(day_first.group(1)))
    if found:
        month, day = found
        try:
            candidate = date(today.year, month, day)
        except ValueError:
            return None
        if candidate < today - timedelta(days=60):
            candidate = date(today.year + 1, month, day)
        return candidate
    for index, name in enumerate(_WEEKDAYS):
        if re.search(rf"\b{name[:3]}(?:{name[3:]})?\b", lowered) and not re.search(rf"\b{name[:3]}\w*\s+\d", lowered):
            ahead = (index - today.weekday()) % 7
            if re.search(rf"\bnext\s+{name[:3]}", lowered) and ahead == 0:
                ahead = 7
            return today + timedelta(days=ahead)
    return None


def parse_time(text: str) -> str:
    match = re.search(r"\b(\d{1,2})(?::(\d{2}))?\s*(am|pm|a\.m\.|p\.m\.)", str(text or "").lower())
    if not match:
        return ""
    hour = int(match.group(1))
    minute = int(match.group(2) or 0)
    if not 1 <= hour <= 12 or minute > 59:
        return ""
    return f"{hour}:{minute:02d} {'AM' if match.group(3).startswith('a') else 'PM'}"


# ---------------------------------------------------------------------------
# Rule-based command parser
# ---------------------------------------------------------------------------
def _status_in(text: str) -> str:
    for pattern, status in _STATUS_WORDS:
        if pattern.search(text):
            return status
    return ""


def _names_before_status(text: str) -> list[str]:
    """'mark Rahul, Nick and Sam available' -> ['Rahul', 'Nick', 'Sam']."""
    match = re.search(
        r"^(?:please\s+)?(?:can you\s+)?(?:mark|set|put|make)\s+(.+?)\s+(?:as\s+)?(?:not available|unavailable|available|maybe|out|in)\b",
        text.strip(),
        re.IGNORECASE,
    )
    if not match:
        match = re.search(r"^(.+?)\s+(?:is|are)\s+(?:not available|unavailable|available|maybe|out|in)\b", text.strip(), re.IGNORECASE)
    if not match:
        return []
    chunk = re.sub(r"\b(for|on)\b.*$", "", match.group(1), flags=re.IGNORECASE)
    parts = [part.strip(" .") for part in re.split(r",|\band\b|&", chunk) if part.strip(" .")]
    return [part for part in parts if part.lower() not in {"me", "myself", "i"}][:15]


def parse_command(message: str, today: date, looks_like_score: Callable[[str], bool] | None = None) -> dict[str, Any] | None:
    """Return {'tool': ..., 'args': {...}} for a recognised command, or None."""
    text = " ".join(str(message or "").split())
    lowered = f" {text.lower()} "
    if not text:
        return None

    # Availability requests / reminders (before "who is available")
    if re.search(r"\b(remind|chase|nudge|follow up)\b", lowered) and re.search(r"\b(haven'?t|not|no) (replied|responded|answered|reply|response)|pending|yet to reply\b", lowered):
        return {"tool": "remind_pending", "args": {"when": text}}
    if re.search(r"\b(ask|request|send|notify|ping|message|remind)\b.*\bavailab", lowered) or "availability request" in lowered:
        return {"tool": "request_availability", "args": {"when": text}}
    if re.search(r"\b(who|how many|show|list)\b.*\b(available|availability|coming|playing|replied)\b", lowered) or "availability summary" in lowered:
        return {"tool": "availability_summary", "args": {"when": text}}

    # Playing XI
    if re.search(r"\b(pick|select|choose|set|make|build|name|suggest)\b.*\b(xi|eleven|11|playing team|team for|squad|line ?up)\b", lowered) or re.search(r"\bbest (xi|eleven|team)\b", lowered):
        return {"tool": "pick_xi", "args": {"when": text}}

    # New fixture
    if re.search(r"\b(add|create|schedule|set up|book|arrange|fix)\b.*\b(match|game|fixture)\b", lowered) and re.search(r"\b(vs\.?|v|versus|against|with)\b", lowered):
        opponent = ""
        opp = re.search(r"\b(?:vs\.?|v|versus|against|with)\s+(.+?)(?=\s+(?:on|at|this|next|tomorrow|today|for|in|,)\b|[.,]|$)", text, re.IGNORECASE)
        if opp:
            opponent = opp.group(1).strip(" .")
        overs = re.search(r"\b(\d{1,2})\s*(?:-\s*)?overs?\b|\bt(\d{2})\b", lowered)
        venue = re.search(r"\b(?:at|venue)\s+([A-Z][\w' ]{2,40}?(?:ground|park|field|oval|stadium|centre|center))\b", text, re.IGNORECASE)
        when = parse_when(text, today)
        return {
            "tool": "create_fixture",
            "args": {
                "opponent": opponent,
                "date": when.isoformat() if when else "",
                "time": parse_time(text),
                "overs": (overs.group(1) or overs.group(2)) if overs else "20",
                "venue": venue.group(1).strip() if venue else "",
            },
        }

    # Live score update for today's game ("we are 85/3 after 12 overs", "update score 85/3 in 12 ov")
    live = re.search(r"\b(\d{1,3})\s*/\s*(\d{1,2})\b(?:.*?\b(?:after|in|from|off)\s+(\d{1,2}(?:\.\d)?)\s*(?:overs?|ov)\b)?", lowered)
    if live and re.search(r"\b(we are|we're|we're at|score is|update (the )?(live )?score|live score|currently|right now|now at|they are|they're)\b", lowered) and not re.search(r"\b(won|lost|tied|beat|all out)\b", lowered):
        return {
            "tool": "live_update",
            "args": {
                "runs": live.group(1),
                "wickets": live.group(2),
                "overs": live.group(3) or "",
                "team": "them" if re.search(r"\b(they|they're|opponent|opposition)\b", lowered) else "us",
            },
        }

    # Final score
    if looks_like_score and looks_like_score(lowered):
        return {"tool": "record_result", "args": {"text": text}}

    # Availability for me / named players
    self_patterns = [
        re.compile(r"\b(?:i'?m|i am|i'?ll be|i will be)\s+(not\s+)?(available|unavailable|in|out|playing|coming|free|busy|away|a maybe|maybe)\b"),
        re.compile(r"\bi\s+(can'?t|cannot|won'?t|can|will)\s+(make it|play|come)\b"),
        re.compile(r"\bcount me (in|out)\b"),
        re.compile(r"^\s*(?:please\s+)?(?:mark|set|put)\s+me\b.*\b(not available|unavailable|available|maybe|out|in)\b"),
    ]
    for pattern in self_patterns:
        found = pattern.search(lowered)
        if not found:
            continue
        phrase = found.group(0)
        if re.search(r"\b(not|unavailable|out|busy|away|can'?t|cannot|won'?t)\b", phrase):
            status = "unavailable"
        elif "maybe" in phrase:
            status = "maybe"
        else:
            status = "available"
        return {"tool": "mark_availability", "args": {"players": ["me"], "status": status, "when": text}}
    names = _names_before_status(text)
    if names and re.search(r"\b(match|game|fixture|saturday|sunday|monday|tuesday|wednesday|thursday|friday|today|tomorrow|next|weekend|available|unavailable|maybe)\b", lowered):
        status = _status_in(lowered[lowered.find(names[-1].lower()) + len(names[-1]):]) or _status_in(lowered)
        if status:
            return {"tool": "mark_availability", "args": {"players": names, "status": status, "when": text}}
    return None


_COMMAND_START = re.compile(
    r"^(please\s+)?(can you|could you|would you|pls|kindly)?\s*(mark|set|put|add|create|schedule|ask|send|remind|pick|select|choose|update|record|save|enter|notify|tell|book|cancel|change|make|let)\b",
    re.IGNORECASE,
)


def looks_like_command(message: str) -> bool:
    return bool(_COMMAND_START.search(str(message or "").strip()))


# ---------------------------------------------------------------------------
# LLM planner (local Ollama), used only when the rules don't recognise a command
# ---------------------------------------------------------------------------
def llm_plan(message: str, context: str, call_llm: Callable[[str, str], str]) -> dict[str, Any] | None:
    """Ask the LLM to choose one tool and fill its arguments. Returns None if it can't."""
    tool_lines = "\n".join(f"- {name}: {desc}" for name, desc in TOOLS.items())
    system = (
        "You are AI Assistant, the assistant inside a cricket club app. Decide which ONE tool carries out the user's request. "
        "Reply with JSON only, like {\"tool\": \"mark_availability\", \"args\": {...}}. Use \"chat\" if it is a question "
        "or no tool fits. Never invent player names or scores that the user did not say.\n\nTools:\n" + tool_lines
    )
    user = f"Context: {context}\nUser: {message}"
    try:
        raw = call_llm(system, user)
    except Exception:
        return None
    match = re.search(r"\{.*\}", str(raw or ""), re.DOTALL)
    if not match:
        return None
    try:
        plan = json.loads(match.group(0))
    except (ValueError, TypeError):
        return None
    tool = str(plan.get("tool") or "").strip()
    args = plan.get("args") if isinstance(plan.get("args"), dict) else {}
    if tool not in TOOLS or tool == "chat":
        return None
    if tool == "mark_availability":
        players = args.get("players") or ["me"]
        if isinstance(players, str):
            players = [players]
        status = str(args.get("status") or "").lower()
        status = "unavailable" if "not" in status or "un" in status else "maybe" if "maybe" in status else "available" if status else ""
        if not status:
            return None
        args = {"players": [str(p) for p in players][:15], "status": status, "when": f"{args.get('when') or ''} {message}"}
    elif tool in {"request_availability", "remind_pending", "availability_summary", "pick_xi"}:
        args = {"when": f"{args.get('when') or ''} {message}"}
    elif tool == "record_result":
        args = {"text": message}
    plan = {"tool": tool, "args": args, "planner": "llm"}
    return plan
