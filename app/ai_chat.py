"""AI Assistant chat brain (Oct 2026). README: "AI Assistant answers (Gemini)".

The AI Assistant (AI Muse) used to answer only with the built-in data lookups (or Ollama when it was
running), so "hello", "what is a no ball?" or "how do I mark availability?" got an unrelated club
answer. This module sends those questions to the same free Google Gemini key that reads scorecard
photos (GEMINI_API_KEY in .env), then Claude (ANTHROPIC_API_KEY), with:

  * APP_GUIDE - how CricketCanClubs works (menu, plans, scoring, uploads, availability...),
  * cricket basics the model already knows (laws, terms, scoring, formats),
  * the club's own data the app looked up for this question ("data notes") and today's context.

So it can greet people, explain the app and cricket, and answer club questions from real data.
It never makes up club numbers: anything about this club must come from the data notes.

complete() is also used for the AI Assistant's command planning (JSON mode) when Ollama isn't running.
"""

from __future__ import annotations

import logging
import time
from typing import Any

import httpx

try:
    from . import ai_vision, subscriptions  # type: ignore
except ImportError:  # running as a script from app/
    import ai_vision  # type: ignore
    import subscriptions  # type: ignore

logger = logging.getLogger("CricketClubApp.ai_chat")

GEMINI_CHAT_MODELS = ("gemini-3.8-flash", "gemini-3.6-flash", "gemini-3.5-flash-lite", "gemini-3-flash-preview")

APP_GUIDE = """You are the AI Assistant inside CricketCanClubs, a web app for community cricket clubs in Canada.
Be friendly, short and clear (2-6 short sentences or a few bullet points). Plain words, no jargon.
Use **bold** for names and key numbers. Use the same language the person writes in (e.g. Hindi or Punjabi in English letters).

How the app works (use this to help people):
- Menu after sign-in: Home (live matches, recent results, coming up), Clubs (pick or switch your club),
  Matches (upcoming games and availability), Score (score a match ball by ball), Scorecards (all published
  scorecards, upload a photo), Stats (season rankings, team roster; Pro also sees season-by-season trends), Plans.
  Profile, Plan and Sign out are in the account menu (initials, top right). After signing in you pick your club on Clubs.
  New users get a short app tour once, after their first sign-in.
- Before sign-in anyone can see Live scores, Fixtures, Scorecards and Rankings, and score a quick guest match by hand.
- Plans: Free ($0) = live scoring, stats, scorecards, 2 scorecard photo uploads a month and ONE free AI try
  (one match with the AI Assistant / AI Scorer, or one scorecard photo read by AI).
  Pro = $9 a month or $90 a year (2 months free): availability, Playing XI, alerts, AI Assistant, AI Scorer,
  unlimited uploads read by AI, analysis. Upgrade on the Plans page.
- Availability: open Matches and tap Available, Maybe or Not available for each game (Pro, or a club whose captain is on Pro).
  You can also tell the assistant "mark me available Saturday".
- Scoring: Score -> choose the match -> set both line-ups (2-11 players each) -> tap 0-6, Wd, Nb, B, LB or W after every ball. Undo fixes mistakes.
  Captains, club admins and site admins score club matches; anyone can score a guest match with a match code.
- Scorecard photos: Scorecards -> Upload a scorecard (captains / club admins). The app reads the photo, shows the digital
  scorecard, you check it, fix anything with Edit and tap Publish. "RO" on our cards means Retired Out.
- The assistant can do tasks after you confirm: mark availability, ask everyone for availability, send reminders,
  save a match score ("We scored 145/6 in 20 overs, they made 120/9").
- Signing in: mobile number or email the club has; no password needed if you never set one.

Rules for answering:
- Greetings and small talk: reply warmly and say what you can help with.
- General cricket questions (laws, terms like no ball, LBW, strike rate, DLS, formats, tips): answer from your own knowledge.
- Questions about THIS club, its players, scores, fixtures or stats: use ONLY the club facts in "Context" and
  "Club data" below. Give the actual names and numbers straight away (like "<name> has the most runs: <runs> in <season>").
  "Me", "my", "I" mean the person asking (named in Context). If the answer isn't there, say you don't have it
  yet and where in the app to look (Stats, Scorecards, Matches). Never invent names, scores or numbers.
- Follow-up questions ("and wickets?", "what about last year?") refer to the earlier messages - answer them in that light.
- If the question is unclear, give your best short answer and ask one short question to check.
- Questions about using the app: answer from the guide above.
- Anything unrelated to cricket or the app (homework, coding, news...): answer briefly if it is harmless and simple, then steer back to cricket.
- Never share anyone's phone number, email or age.
"""


def provider() -> str:
    if ai_vision.gemini_key():
        return "gemini"
    if ai_vision.api_key():
        return "claude"
    return ""


def enabled() -> bool:
    return bool(provider())


def _gemini(system: str, messages: list[dict[str, str]], *, json_mode: bool, timeout: float) -> str:
    key = ai_vision.gemini_key()
    base = subscriptions.setting("GEMINI_BASE_URL", "https://generativelanguage.googleapis.com").rstrip("/")
    configured = subscriptions.setting("GEMINI_CHAT_MODEL")
    models = [configured] if configured else list(GEMINI_CHAT_MODELS)
    contents = [
        {"role": "model" if m["role"] == "assistant" else "user", "parts": [{"text": m["text"]}]}
        for m in messages
        if m.get("text")
    ]
    config: dict[str, Any] = {"temperature": 0 if json_mode else 0.4, "maxOutputTokens": 700}
    if json_mode:
        config["responseMimeType"] = "application/json"
    body = {"systemInstruction": {"parts": [{"text": system}]}, "contents": contents, "generationConfig": config}
    last = ""
    for model in models:
        for pause in (0, 2):
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
                last = f"couldn't reach Google ({exc.__class__.__name__})"
                continue
            if response.status_code in {500, 502, 503, 504}:
                last = f"{model} busy"
                continue
            if response.status_code in {404, 429}:
                last = f"{model} {'not available' if response.status_code == 404 else 'free limit reached'}"
                break  # next model
            if response.status_code != 200:
                last = f"HTTP {response.status_code}: {response.text[:200]}"
                break
            parts = (((response.json().get("candidates") or [{}])[0].get("content") or {}).get("parts") or [])
            text = "".join(str(part.get("text") or "") for part in parts).strip()
            if text:
                return text
            last = f"{model} gave an empty answer"
            break
    raise RuntimeError(f"Gemini didn't answer ({last})")


def _claude(system: str, messages: list[dict[str, str]], *, json_mode: bool, timeout: float) -> str:
    base = subscriptions.setting("ANTHROPIC_BASE_URL", ai_vision.DEFAULT_BASE_URL).rstrip("/")
    model = subscriptions.setting("ANTHROPIC_CHAT_MODEL") or ai_vision.model_name()
    turns = [{"role": "assistant" if m["role"] == "assistant" else "user", "content": m["text"]} for m in messages if m.get("text")]
    while turns and turns[0]["role"] != "user":
        turns.pop(0)
    response = httpx.post(
        f"{base}/v1/messages",
        json={"model": model, "max_tokens": 700, "system": system + ("\nReply with JSON only." if json_mode else ""), "messages": turns},
        headers={"x-api-key": ai_vision.api_key(), "anthropic-version": "2023-06-01", "content-type": "application/json"},
        timeout=timeout,
    )
    if response.status_code != 200:
        raise RuntimeError(f"Claude answered {response.status_code}")
    return "".join(block.get("text", "") for block in response.json().get("content", []) if block.get("type") == "text").strip()


def complete(system: str, user: str, *, history: list[dict[str, Any]] | None = None, json_mode: bool = False, timeout: float = 25.0) -> str:
    """One answer from the configured chat model. Raises RuntimeError when none is set up or it fails."""
    messages: list[dict[str, str]] = []
    for item in (history or [])[-8:]:
        if not isinstance(item, dict):
            continue
        text = " ".join(str(item.get("text") or item.get("content") or "").split())[:1200]
        if text:
            messages.append({"role": "assistant" if item.get("role") in {"assistant", "bot"} else "user", "text": text})
    messages.append({"role": "user", "text": user})
    chosen = provider()
    if chosen == "gemini":
        return _gemini(system, messages, json_mode=json_mode, timeout=timeout)
    if chosen == "claude":
        return _claude(system, messages, json_mode=json_mode, timeout=timeout)
    raise RuntimeError("No chat model set up (add GEMINI_API_KEY to .env)")


def answer(question: str, *, data_notes: str = "", context: str = "", history: list[dict[str, Any]] | None = None) -> str | None:
    """Friendly answer for the AI Assistant, or None when no model is available / it failed
    (the caller then shows the built-in data answer)."""
    if not enabled():
        return None
    system = APP_GUIDE + f"\nContext: {context or 'none'}\n\nClub data the app looked up for this question (may be empty or not relevant):\n{data_notes or '(none)'}\n"
    try:
        return complete(system, question, history=history) or None
    except Exception as exc:  # never break the chat because the AI is busy
        logger.warning("AI chat failed: %s", exc)
        return None


# ---------------------------------------------------------------------------
# Built-in basic answers (work with no AI at all, e.g. when Gemini is busy or not set up).
# kind "chat": greetings / thanks / help - answered straight away.
# kind "howto" / "cricket": tried with Gemini first for a fuller answer; this text is the fallback.
# ---------------------------------------------------------------------------
import re as _re

_HELP = (
    "I can help with:\n"
    "• Your club: results, top run scorers and wicket takers, upcoming matches, scorecards\n"
    "• Tasks: “mark me available Saturday”, “ask everyone for availability”, “we scored 145/6, they made 120/9”\n"
    "• The app: how to score a match, upload a scorecard photo, mark availability, plans\n"
    "• Cricket questions: rules and terms like no ball, LBW, strike rate"
)

_BASIC: list[tuple[str, str, str]] = [
    # (kind, regex, answer)
    ("chat", r"^(hi+|hello+|hey+|hiya|yo|namaste|sat sri akal|good (morning|afternoon|evening)|howdy)\b[\s!.,?]*(there|muse|assistant)?[\s!.?]*$",
     "Hi! 👋 I'm your CricketCanClubs assistant.\n" + _HELP),
    ("chat", r"^(how are you|how r u|how's it going|what'?s up|sup)\b", "I'm doing great, thanks for asking! 🏏 How can I help you today?\n" + _HELP),
    ("chat", r"^(thanks|thank you|thx|ty|cheers|great|awesome|nice|cool|ok(ay)?|perfect)\b[\s!.]*$", "You're welcome! Anything else I can help with?"),
    ("chat", r"^(bye|good ?bye|see you|cya|good night)\b", "Bye! 👋 Enjoy your cricket."),
    ("chat", r"^(help|menu|options|what can you do|what do you do|who are you|what are you)\b", _HELP),
    ("howto", r"\b(mark|set|change|update)\b.*\bavailab", "Open **Matches** and tap Available, Maybe or Not available for each game. Or just tell me “mark me available Saturday” and I'll do it after you confirm."),
    ("howto", r"\bhow\b.*\b(score|scoring)\b", "Tap **Score**, choose the match, set both line-ups (2–11 players each), then tap 0–6, Wd, Nb, B, LB or W after every ball. ↶ Undo fixes a mistake. Captains and club admins score club matches; anyone can score a quick guest match."),
    ("howto", r"\b(upload|photo|picture)\b.*\bscore ?card|\bscore ?card\b.*\b(upload|photo|picture)", "Open **Scorecards** → 📷 Upload a scorecard (captains and club admins). The app reads the photo and shows the digital scorecard. Check it, fix anything with ✏️ Edit, then tap Publish. You can also tap 📎 here."),
    ("howto", r"\b(plan|plans|price|pricing|cost|pro|subscription|upgrade|pay)\b", "**Free** ($0): live scoring, stats, scorecards, 2 photo uploads a month and 1 free AI try.\n**Pro**: $9 a month or $90 a year (2 months free): availability, Playing XI, alerts, AI Assistant, AI Scorer, unlimited uploads read by AI. See **Plans**."),
    ("howto", r"\b(switch|change)\b.*\bclub\b", "Tap **Clubs** in the menu, then “Select club” next to your club."),
    ("howto", r"\b(where|how)\b.*\b(stats|statistics|rankings?|leaderboard|performances?)\b", "Tap **Stats** in the menu: season rankings for batting, bowling and fielding, and your team roster. Pick the season at the top. Pro members also see season-by-season numbers."),
    ("howto", r"\b(sign ?out|log ?out)\b", "Open your account menu (your initials, top right) and tap **Sign out**."),
    ("howto", r"\b(tour|tutorial|guide me|show me around)\b", "The app tour shows once, after your first sign-in. Quick recap: **Matches** to mark availability, **Score** to score a match, **Scorecards** to see or upload scorecards, and your initials (top right) for profile, clubs and plan. Ask me anything else!"),
    ("cricket", r"\bno ?-?ball\b", "A **no ball** is an illegal delivery (e.g. the bowler oversteps the crease or it's a high full toss). The batting side gets 1 extra run plus any runs scored, the ball doesn't count in the over, and in limited-overs games the next ball is a free hit."),
    ("cricket", r"\bwide\b", "A **wide** is a ball too far from the batter to hit with a normal shot. The batting side gets 1 extra run and the ball must be bowled again."),
    ("cricket", r"\blbw\b|leg before", "**LBW (leg before wicket)**: the batter is out if the ball would have hit the stumps but hit their body (usually the pad) first, it didn't pitch outside leg stump, and the batter was hit in line (or wasn't playing a shot)."),
    ("cricket", r"\bretired out\b|\bro\b", "**Retired out**: the batter leaves without the umpire's permission (in club games often at a set score). It counts as a wicket. On our scorecards “RO” means retired out. **Retired hurt** (injury) is not a wicket."),
    ("cricket", r"\brun ?out\b", "**Run out**: a fielder breaks the stumps with the ball while the batter is out of their ground going for a run. The bowler doesn't get the wicket."),
    ("cricket", r"\bstrike ?rate\b", "**Strike rate**: for a batter it's runs ÷ balls faced × 100 (e.g. 45 off 30 = 150). For a bowler it's balls bowled per wicket."),
    ("cricket", r"\beconomy\b", "**Economy rate**: runs a bowler gives away per over (runs ÷ overs). Under 6 is good in T20."),
    ("cricket", r"\bmaiden\b", "A **maiden** is an over where the bowler gives away no runs off the bat (and no wides or no balls)."),
    ("cricket", r"\bduck\b", "A **duck** is when a batter is out for 0. A golden duck is out first ball."),
    ("cricket", r"\bhat[- ]?trick\b", "A **hat-trick** is a bowler taking wickets with three balls in a row (in the same match)."),
    ("cricket", r"\bfree ?hit\b", "A **free hit** follows a no ball in limited-overs cricket: the batter can't be out bowled, caught, LBW or stumped on that ball (only run out and a few rare ways)."),
    ("cricket", r"\b(over|overs)\b.*\b(how many balls|balls in)\b|\bwhat is an over\b", "An **over** is 6 legal balls bowled by one bowler. Wides and no balls don't count, so they're bowled again."),
    ("cricket", r"\b(byes?|leg ?byes?)\b", "**Byes** are runs taken when the ball passes the batter and keeper without touching the bat or body. **Leg byes** are runs taken after the ball hits the batter's body (not the bat). Both go into extras."),
]


def basic_reply(message: str) -> tuple[str, str] | None:
    """(kind, answer) for greetings, help, app how-tos and common cricket terms, else None."""
    text = " ".join(str(message or "").lower().split())
    text = _re.sub(r"[🙂😀👋🏏]+", "", text).strip()
    if not text:
        return None
    for kind, pattern, answer_text in _BASIC:
        if _re.search(pattern, text):
            return kind, answer_text
    return None
