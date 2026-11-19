"""What the paid services are used for, and roughly what they cost (Nov 18 2026, Amit: "track costs - Gemini, Azure,
WhatsApp"). README "Costs (Admin Center)".

Every call the app makes to Google's Gemini (or Claude) goes through httpx.post; install() wraps that one function
so each answered call is written to the table app_ai_usage: when, which model, what it was for (scorecard reading,
bowling re-read, same-match check, AI assistant) and the tokens Google counted. Nothing about the call changes - if
writing the row fails, the call still answers as before.

WhatsApp messages are already in app_whatsapp_log (one row per message). Azure is a fixed monthly plan, so its
cost is the plan price typed in the Admin Center (Costs tab), not something the app can measure.
"""
from __future__ import annotations

import datetime as _dt
import logging
import sqlite3
import sys
from typing import Any, Callable

import httpx

logger = logging.getLogger("CricketClubStore")

_CONNECT: Callable[[], sqlite3.Connection] | None = None
_ORIGINAL_POST: Callable[..., Any] | None = None

CREATE_SQL = (
    "CREATE TABLE IF NOT EXISTS app_ai_usage (id INTEGER PRIMARY KEY AUTOINCREMENT, at TEXT NOT NULL, provider TEXT NOT NULL, "
    "model TEXT NOT NULL DEFAULT '', purpose TEXT NOT NULL DEFAULT '', input_tokens INTEGER NOT NULL DEFAULT 0, "
    "output_tokens INTEGER NOT NULL DEFAULT 0, thinking_tokens INTEGER NOT NULL DEFAULT 0, ok INTEGER NOT NULL DEFAULT 1)"
)

# which app function made the call -> what it is for (the first match walking up the stack wins)
PURPOSES = (
    ("_read_bowling_only", "Bowling re-read"),
    ("same_match", "Same-match check (duplicates)"),
    ("_ask_text", "AI text check"),
    ("_read_with_gemini", "Scorecard reading"),
    ("_read_with_claude", "Scorecard reading"),
    ("answer", "AI assistant (✨)"),
    ("_gemini", "AI assistant (✨)"),
    ("_claude", "AI assistant (✨)"),
)
APP_MODULES = {"ai_vision", "ai_chat", "ai_duplicate_engine", "ai_scorer", "cricket_brain", "cricket_store", "llm_service", "muse", "muse_agent", "main"}


def _provider(url: str) -> str:
    if "generativelanguage.googleapis.com" in url or ":generateContent" in url:
        return "gemini"
    if "anthropic.com" in url or url.rstrip("/").endswith("/v1/messages"):
        return "claude"
    return ""


def _purpose() -> str:
    names: list[str] = []
    frame = sys._getframe(2)
    while frame is not None and len(names) < 12:
        module = str(frame.f_globals.get("__name__") or "").rsplit(".", 1)[-1]
        if module in APP_MODULES:
            names.append(frame.f_code.co_name)
        frame = frame.f_back
    for function, label in PURPOSES:
        if function in names:
            return label
    return names[0] if names else "other"


def _model(url: str, body: Any) -> str:
    if "/models/" in url:
        return url.split("/models/", 1)[1].split(":", 1)[0]
    if isinstance(body, dict):
        return str(body.get("model") or "")
    return ""


def record(provider: str, model: str, purpose: str, input_tokens: int, output_tokens: int, thinking_tokens: int = 0, ok: bool = True) -> None:
    if _CONNECT is None:
        return
    try:
        connection = _CONNECT()
        with connection:
            connection.execute(CREATE_SQL)
            connection.execute(
                "INSERT INTO app_ai_usage (at, provider, model, purpose, input_tokens, output_tokens, thinking_tokens, ok) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (_dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds"), provider, model, purpose, int(input_tokens or 0), int(output_tokens or 0), int(thinking_tokens or 0), 1 if ok else 0),
            )
        connection.close()
    except Exception as exc:  # never let counting break the call
        logger.debug("AI usage not recorded: %s", exc)


def _metered_post(url: Any, *args: Any, **kwargs: Any) -> Any:
    response = _ORIGINAL_POST(url, *args, **kwargs)  # type: ignore[misc]
    try:
        text_url = str(url)
        provider = _provider(text_url)
        if provider:
            ok = response.status_code == 200
            usage: dict[str, Any] = {}
            if ok:
                payload = response.json()
                usage = (payload.get("usageMetadata") if provider == "gemini" else payload.get("usage")) or {}
            if provider == "gemini":
                record(provider, _model(text_url, kwargs.get("json")), _purpose(), usage.get("promptTokenCount") or 0,
                       usage.get("candidatesTokenCount") or 0, usage.get("thoughtsTokenCount") or 0, ok)
            else:
                record(provider, _model(text_url, kwargs.get("json")), _purpose(), usage.get("input_tokens") or 0, usage.get("output_tokens") or 0, 0, ok)
    except Exception as exc:
        logger.debug("AI usage not recorded: %s", exc)
    return response


def install(connect: Callable[[], sqlite3.Connection]) -> None:
    """Start counting (called once by main.py). `connect` opens the app's database."""
    global _CONNECT, _ORIGINAL_POST
    _CONNECT = connect
    if _ORIGINAL_POST is None:
        _ORIGINAL_POST = httpx.post
        httpx.post = _metered_post  # type: ignore[assignment]


def summary(connection: sqlite3.Connection, since: str) -> list[dict[str, Any]]:
    """AI calls since `since` (ISO time), by provider, model and purpose."""
    connection.execute(CREATE_SQL)
    rows = connection.execute(
        "SELECT provider, model, purpose, COUNT(*) AS calls, SUM(ok) AS answered, SUM(input_tokens) AS input_tokens, "
        "SUM(output_tokens) AS output_tokens, SUM(thinking_tokens) AS thinking_tokens FROM app_ai_usage WHERE at >= ? "
        "GROUP BY provider, model, purpose ORDER BY calls DESC",
        (since,),
    ).fetchall()
    keys = ("provider", "model", "purpose", "calls", "answered", "input_tokens", "output_tokens", "thinking_tokens")
    return [dict(zip(keys, (row[0], row[1], row[2], *(int(value or 0) for value in row[3:])))) for row in rows]
