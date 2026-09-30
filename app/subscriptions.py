"""
Subscription plans, feature limits and Stripe billing for CricketCanClubs.

Model (from "Cricket App Subscription & Feature Model", Sept 2026):
  Free     $0            live scoring, player/club stats, scorecards, 2 scorecard image uploads a month
  Super    $4.99/month   + 5 uploads a month, multi-club, rosters, availability, Playing XI,
                           alerts, live score updates, AI Muse assistant, analysis
  Premium  $100/year     + unlimited uploads, AI Live Scorer, match intelligence,
                           cross-club stats, advanced analysis, priority support

Rules:
  * Plans belong to a user. A club counts as "paid" when one of its captains or club admins
    is on Super or Premium; its players then get availability marking and alerts too.
  * Site admins (superadmin) always have Premium.
  * Users who existed when plans were switched on get a 60-day Premium trial.
  * Stripe is OFF until STRIPE_SECRET_KEY and the two price ids are set (environment or .env).
    Until then a site admin changes plans by hand on /pricing (Admin: set a user's plan).

Documented in README.md -> "Subscriptions and plans".
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import sqlite3
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

TRIAL_DAYS = 60
PLAN_ORDER = ["free", "super", "premium"]

FEATURES: dict[str, dict[str, str]] = {
    # key: label, minimum plan
    "live_scoring": {"label": "Live match scoring", "plan": "free"},
    "stats": {"label": "Player and club statistics", "plan": "free"},
    "scorecards": {"label": "View scorecards", "plan": "free"},
    "basic_insights": {"label": "Basic player and club analysis", "plan": "free"},
    "multi_club": {"label": "Multi-club selection", "plan": "super"},
    "match_roster": {"label": "Match roster management", "plan": "super"},
    "availability": {"label": "Player availability marking", "plan": "super"},
    "playing_xi": {"label": "Playing XI / team management", "plan": "super"},
    "alerts": {"label": "Alerts and player notifications", "plan": "super"},
    "score_updates": {"label": "Live score updates to players", "plan": "super"},
    "ai_assistant": {"label": "AI Muse assistant", "plan": "super"},
    "analysis": {"label": "Historical, player and club analysis", "plan": "super"},
    "ai_extraction": {"label": "AI scorecard extraction", "plan": "super"},
    "retro_help": {"label": "Help with old score uploads", "plan": "super"},
    "ai_live_scorer": {"label": "AI Live Scorer (hands-free)", "plan": "premium"},
    "match_intelligence": {"label": "Match intelligence", "plan": "premium"},
    "cross_club_stats": {"label": "Cross-club statistics", "plan": "premium"},
    "advanced_analysis": {"label": "Advanced analysis", "plan": "premium"},
    "priority_support": {"label": "Priority support", "plan": "premium"},
}

PLANS: dict[str, dict[str, Any]] = {
    "free": {
        "id": "free",
        "name": "Free",
        "price": "$0",
        "price_note": "forever",
        "amount_cents": 0,
        "interval": "",
        "tagline": "For every cricket player",
        "upload_limit": 2,
        "highlights": [
            "Unlimited live scoring",
            "Player statistics",
            "Club statistics",
            "Scorecard history",
            "2 historical scorecard uploads/month",
        ],
    },
    "super": {
        "id": "super",
        "name": "Super",
        "price": "$4.99",
        "price_note": "per month",
        "amount_cents": 499,
        "interval": "month",
        "tagline": "For active players & teams",
        "upload_limit": 5,
        "highlights": [
            "Everything in Free, plus:",
            "5 historical scorecard uploads/month",
            "Multi-club support",
            "Rosters, availability and Playing XI",
            "Player alerts and live score updates",
            "AI Muse assistant",
            "Historical and player analysis",
        ],
    },
    "premium": {
        "id": "premium",
        "name": "Premium",
        "price": "$100",
        "price_note": "per year (about $8.33/month)",
        "amount_cents": 10000,
        "interval": "year",
        "tagline": "For serious players, captains & clubs",
        "upload_limit": None,
        "highlights": [
            "Everything in Super, plus:",
            "Unlimited historical uploads",
            "AI Live Scorer: say \"four\" and the scorecard updates",
            "Match intelligence",
            "Cross-club statistics",
            "Advanced analysis",
            "Retro-score assistance and priority support",
        ],
    },
}


def plan_rank(plan: str) -> int:
    return PLAN_ORDER.index(plan) if plan in PLAN_ORDER else 0


def plan_features(plan: str) -> list[str]:
    rank = plan_rank(plan)
    return [key for key, info in FEATURES.items() if plan_rank(info["plan"]) <= rank]


def feature_min_plan(feature: str) -> str:
    return FEATURES.get(feature, {}).get("plan", "premium")


def upgrade_message(feature: str) -> str:
    plan = PLANS[feature_min_plan(feature)]
    label = FEATURES.get(feature, {}).get("label", "This feature")
    return f"{label} is part of the {plan['name']} plan ({plan['price']} {plan['price_note']}). See /pricing to upgrade."


# ---------------------------------------------------------------------------
# Settings (.env next to README.md, or real environment variables)
# ---------------------------------------------------------------------------
_ENV_CACHE: dict[str, str] | None = None


def _env_file_values() -> dict[str, str]:
    global _ENV_CACHE
    if _ENV_CACHE is not None:
        return _ENV_CACHE
    values: dict[str, str] = {}
    path = Path(__file__).resolve().parent.parent / ".env"
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            values[key.strip()] = value.strip().strip('"').strip("'")
    except OSError:
        pass
    _ENV_CACHE = values
    return values


def setting(name: str, default: str = "") -> str:
    return str(os.environ.get(name) or _env_file_values().get(name) or default).strip()


def stripe_config() -> dict[str, str]:
    return {
        "secret_key": setting("STRIPE_SECRET_KEY"),
        "webhook_secret": setting("STRIPE_WEBHOOK_SECRET"),
        "price_super": setting("STRIPE_PRICE_SUPER"),
        "price_premium": setting("STRIPE_PRICE_PREMIUM"),
        "base_url": setting("APP_BASE_URL").rstrip("/"),
    }


def stripe_enabled() -> bool:
    config = stripe_config()
    return bool(config["secret_key"] and config["price_super"] and config["price_premium"])


def stripe_test_mode() -> bool:
    return stripe_config()["secret_key"].startswith("sk_test_")


# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------
def _now() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def _iso(value: datetime | None) -> str:
    return value.isoformat().replace("+00:00", "Z") if value else ""


def _parse(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def ensure_schema(connection: sqlite3.Connection) -> None:
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS app_subscriptions (
          user_id INTEGER PRIMARY KEY,
          plan TEXT NOT NULL DEFAULT 'free',
          status TEXT NOT NULL DEFAULT 'active',
          source TEXT NOT NULL DEFAULT 'free',
          started_at TEXT NOT NULL,
          current_period_end TEXT,
          cancel_at_period_end INTEGER NOT NULL DEFAULT 0,
          stripe_customer_id TEXT,
          stripe_subscription_id TEXT,
          note TEXT,
          updated_at TEXT NOT NULL,
          FOREIGN KEY (user_id) REFERENCES app_users(id) ON DELETE CASCADE
        );
        CREATE TABLE IF NOT EXISTS app_subscription_meta (
          key TEXT PRIMARY KEY,
          value TEXT
        );
        CREATE TABLE IF NOT EXISTS app_payment_events (
          id TEXT PRIMARY KEY,
          type TEXT,
          user_id INTEGER,
          created_at TEXT NOT NULL,
          payload TEXT
        );
        """
    )
    row = connection.execute("SELECT value FROM app_subscription_meta WHERE key = 'launch_at'").fetchone()
    if not row:
        connection.execute("INSERT INTO app_subscription_meta (key, value) VALUES ('launch_at', ?)", (_iso(_now()),))


def launch_at(connection: sqlite3.Connection) -> datetime:
    row = connection.execute("SELECT value FROM app_subscription_meta WHERE key = 'launch_at'").fetchone()
    return _parse(row[0] if row else "") or _now()


def _subscription_row(connection: sqlite3.Connection, user_id: int) -> sqlite3.Row | None:
    connection.row_factory = sqlite3.Row
    return connection.execute("SELECT * FROM app_subscriptions WHERE user_id = ?", (user_id,)).fetchone()


def _ensure_row(connection: sqlite3.Connection, user_row: Any) -> sqlite3.Row:
    """Create the user's subscription row the first time we see them (trial for existing users)."""
    user_id = int(user_row["id"])
    row = _subscription_row(connection, user_id)
    if row:
        return row
    launched = launch_at(connection)
    created = _parse(user_row["created_at"]) if "created_at" in user_row.keys() else None
    now = _iso(_now())
    if created is None or created <= launched:
        trial_end = launched + timedelta(days=TRIAL_DAYS)
        connection.execute(
            """INSERT OR IGNORE INTO app_subscriptions (user_id, plan, status, source, started_at, current_period_end, note, updated_at)
               VALUES (?, 'premium', 'trialing', 'trial', ?, ?, ?, ?)""",
            (user_id, _iso(launched), _iso(trial_end), f"{TRIAL_DAYS}-day Premium trial for existing members", now),
        )
    else:
        connection.execute(
            """INSERT OR IGNORE INTO app_subscriptions (user_id, plan, status, source, started_at, updated_at)
               VALUES (?, 'free', 'active', 'free', ?, ?)""",
            (user_id, now, now),
        )
    return _subscription_row(connection, user_id)


def uploads_this_month(connection: sqlite3.Connection, user_id: int) -> int:
    month = _now().strftime("%Y-%m")
    row = connection.execute(
        "SELECT COUNT(*) FROM app_audit_log WHERE actor_user_id = ? AND action = 'archive.upload' AND substr(created_at, 1, 7) = ?",
        (user_id, month),
    ).fetchone()
    return int(row[0] or 0) if row else 0


def effective_plan(connection: sqlite3.Connection, user_row: Any, role_names: list[str] | None = None) -> dict[str, Any]:
    """The plan the user has right now, with features and quota."""
    row = _ensure_row(connection, user_row)
    plan = str(row["plan"] or "free")
    status = str(row["status"] or "active")
    source = str(row["source"] or "free")
    period_end = _parse(row["current_period_end"])
    now = _now()
    active = status in {"active", "trialing", "past_due"}
    if period_end and period_end < now and source in {"trial", "admin"}:
        active = False
    if plan != "free" and not active:
        plan, expired_from = "free", str(row["plan"])
    else:
        expired_from = ""
    if "superadmin" in (role_names or []):
        plan, source, status = "premium", "site_admin", "active"
    info = PLANS[plan]
    used = uploads_this_month(connection, int(user_row["id"]))
    limit = info["upload_limit"]
    days_left = None
    if period_end and plan != "free" and source != "site_admin":
        days_left = max(0, (period_end - now).days)
    return {
        "plan": plan,
        "plan_name": info["name"],
        "price": info["price"],
        "price_note": info["price_note"],
        "status": status if plan != "free" else "active",
        "source": source if plan != "free" else ("expired" if expired_from else "free"),
        "is_trial": source == "trial" and plan != "free",
        "expired_from": expired_from,
        "period_end": _iso(period_end) if plan != "free" and source != "site_admin" else "",
        "days_left": days_left,
        "cancel_at_period_end": bool(row["cancel_at_period_end"]),
        "has_stripe_customer": bool(row["stripe_customer_id"]),
        "features": plan_features(plan),
        "upload_limit": limit,
        "uploads_used": used,
        "uploads_left": None if limit is None else max(0, limit - used),
    }


def has_feature(connection: sqlite3.Connection, user_row: Any, feature: str, role_names: list[str] | None = None) -> bool:
    return feature in effective_plan(connection, user_row, role_names)["features"]


def set_plan(
    connection: sqlite3.Connection,
    user_row: Any,
    plan: str,
    *,
    source: str,
    status: str = "active",
    period_end: datetime | None = None,
    note: str = "",
    stripe_customer_id: str | None = None,
    stripe_subscription_id: str | None = None,
    cancel_at_period_end: bool | None = None,
) -> None:
    if plan not in PLANS:
        raise ValueError(f"Unknown plan '{plan}'.")
    _ensure_row(connection, user_row)
    fields = {
        "plan": plan,
        "status": status,
        "source": source,
        "current_period_end": _iso(period_end) if period_end else None,
        "note": note,
        "updated_at": _iso(_now()),
    }
    if stripe_customer_id is not None:
        fields["stripe_customer_id"] = stripe_customer_id
    if stripe_subscription_id is not None:
        fields["stripe_subscription_id"] = stripe_subscription_id
    if cancel_at_period_end is not None:
        fields["cancel_at_period_end"] = 1 if cancel_at_period_end else 0
    assignments = ", ".join(f"{key} = ?" for key in fields)
    connection.execute(f"UPDATE app_subscriptions SET {assignments} WHERE user_id = ?", (*fields.values(), int(user_row["id"])))


def paid_manager_count(connection: sqlite3.Connection, club_id: str) -> int:
    """Captains / club admins of this club who are on Super or Premium right now."""
    if not club_id:
        return 0
    connection.row_factory = sqlite3.Row
    rows = connection.execute(
        """SELECT u.* FROM app_users u
           WHERE (u.primary_club_id = ? AND u.role IN ('captain', 'club_admin'))
              OR u.id IN (SELECT user_id FROM app_user_club_roles WHERE club_id = ? AND role_name IN ('captain', 'club_admin'))""",
        (club_id, club_id),
    ).fetchall()
    count = 0
    for user_row in rows:
        if effective_plan(connection, user_row)["plan"] != "free":
            count += 1
    return count


# ---------------------------------------------------------------------------
# Stripe (REST API over urllib - no extra package needed)
# ---------------------------------------------------------------------------
class StripeError(RuntimeError):
    pass


def _stripe_request(method: str, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
    config = stripe_config()
    if not config["secret_key"]:
        raise StripeError("Stripe is not set up yet.")
    data = urllib.parse.urlencode(params or {}, doseq=True).encode() if params else None
    url = f"https://api.stripe.com/v1/{path.lstrip('/')}"
    if method == "GET" and data:
        url = f"{url}?{data.decode()}"
        data = None
    request = urllib.request.Request(url, data=data, method=method)
    request.add_header("Authorization", f"Bearer {config['secret_key']}")
    request.add_header("Content-Type", "application/x-www-form-urlencoded")
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        try:
            detail = json.loads(exc.read().decode("utf-8")).get("error", {}).get("message", "")
        except Exception:
            detail = ""
        raise StripeError(detail or f"Stripe error {exc.code}") from exc
    except urllib.error.URLError as exc:
        raise StripeError(f"Could not reach Stripe: {exc.reason}") from exc


def price_for_plan(plan: str) -> str:
    config = stripe_config()
    return config["price_super"] if plan == "super" else config["price_premium"] if plan == "premium" else ""


def plan_for_price(price_id: str) -> str:
    config = stripe_config()
    if price_id and price_id == config["price_premium"]:
        return "premium"
    if price_id and price_id == config["price_super"]:
        return "super"
    return ""


def create_checkout_session(user_row: Any, plan: str, base_url: str, customer_id: str = "") -> str:
    price = price_for_plan(plan)
    if not price:
        raise StripeError("This plan has no Stripe price set.")
    base = stripe_config()["base_url"] or base_url.rstrip("/")
    params: dict[str, Any] = {
        "mode": "subscription",
        "line_items[0][price]": price,
        "line_items[0][quantity]": 1,
        "success_url": f"{base}/pricing?checkout=success",
        "cancel_url": f"{base}/pricing?checkout=cancelled",
        "client_reference_id": str(int(user_row["id"])),
        "metadata[user_id]": str(int(user_row["id"])),
        "metadata[plan]": plan,
        "subscription_data[metadata][user_id]": str(int(user_row["id"])),
        "subscription_data[metadata][plan]": plan,
        "allow_promotion_codes": "true",
    }
    if customer_id:
        params["customer"] = customer_id
    elif user_row["email"]:
        params["customer_email"] = str(user_row["email"])
    session = _stripe_request("POST", "checkout/sessions", params)
    return str(session.get("url") or "")


def create_portal_session(customer_id: str, base_url: str) -> str:
    base = stripe_config()["base_url"] or base_url.rstrip("/")
    session = _stripe_request("POST", "billing_portal/sessions", {"customer": customer_id, "return_url": f"{base}/pricing"})
    return str(session.get("url") or "")


def verify_webhook(payload: bytes, signature_header: str, tolerance: int = 300) -> dict[str, Any]:
    secret = stripe_config()["webhook_secret"]
    if not secret:
        raise StripeError("STRIPE_WEBHOOK_SECRET is not set.")
    parts: dict[str, list[str]] = {}
    for item in str(signature_header or "").split(","):
        if "=" in item:
            key, value = item.split("=", 1)
            parts.setdefault(key.strip(), []).append(value.strip())
    timestamp = (parts.get("t") or [""])[0]
    if not timestamp or not parts.get("v1"):
        raise StripeError("Missing Stripe signature.")
    expected = hmac.new(secret.encode(), f"{timestamp}.".encode() + payload, hashlib.sha256).hexdigest()
    if not any(hmac.compare_digest(expected, candidate) for candidate in parts["v1"]):
        raise StripeError("Stripe signature did not match.")
    if abs(time.time() - int(timestamp)) > tolerance:
        raise StripeError("Stripe signature is too old.")
    return json.loads(payload.decode("utf-8"))


def _user_by_id(connection: sqlite3.Connection, user_id: Any) -> sqlite3.Row | None:
    try:
        clean = int(str(user_id or "").strip())
    except ValueError:
        return None
    connection.row_factory = sqlite3.Row
    return connection.execute("SELECT * FROM app_users WHERE id = ?", (clean,)).fetchone()


def _user_by_customer(connection: sqlite3.Connection, customer_id: str) -> sqlite3.Row | None:
    if not customer_id:
        return None
    connection.row_factory = sqlite3.Row
    return connection.execute(
        "SELECT u.* FROM app_users u JOIN app_subscriptions s ON s.user_id = u.id WHERE s.stripe_customer_id = ?",
        (customer_id,),
    ).fetchone()


def _from_unix(value: Any) -> datetime | None:
    try:
        return datetime.fromtimestamp(int(value), tz=timezone.utc)
    except (TypeError, ValueError):
        return None


def handle_stripe_event(connection: sqlite3.Connection, event: dict[str, Any]) -> dict[str, Any]:
    """Apply a verified Stripe webhook event. Safe to receive the same event twice."""
    event_id = str(event.get("id") or "")
    event_type = str(event.get("type") or "")
    obj = (event.get("data") or {}).get("object") or {}
    if event_id and connection.execute("SELECT 1 FROM app_payment_events WHERE id = ?", (event_id,)).fetchone():
        return {"ok": True, "duplicate": True}

    user_row = None
    result: dict[str, Any] = {"ok": True, "type": event_type}
    if event_type == "checkout.session.completed":
        metadata = obj.get("metadata") or {}
        user_row = _user_by_id(connection, obj.get("client_reference_id") or metadata.get("user_id"))
        plan = str(metadata.get("plan") or "")
        if user_row and plan in {"super", "premium"}:
            set_plan(
                connection,
                user_row,
                plan,
                source="stripe",
                status="active",
                period_end=None,
                note="Paid through Stripe Checkout",
                stripe_customer_id=str(obj.get("customer") or ""),
                stripe_subscription_id=str(obj.get("subscription") or ""),
                cancel_at_period_end=False,
            )
            result["plan"] = plan
    elif event_type in {"customer.subscription.created", "customer.subscription.updated", "customer.subscription.deleted"}:
        metadata = obj.get("metadata") or {}
        customer_id = str(obj.get("customer") or "")
        user_row = _user_by_id(connection, metadata.get("user_id")) or _user_by_customer(connection, customer_id)
        items = ((obj.get("items") or {}).get("data") or [])
        price_id = str(((items[0] if items else {}).get("price") or {}).get("id") or "")
        plan = plan_for_price(price_id) or str(metadata.get("plan") or "")
        status = str(obj.get("status") or "")
        period_end = _from_unix(obj.get("current_period_end") or ((items[0] if items else {}).get("current_period_end")))
        if user_row:
            if event_type == "customer.subscription.deleted" or status in {"canceled", "unpaid", "incomplete_expired"}:
                set_plan(connection, user_row, "free", source="stripe", status="canceled", note="Stripe subscription ended", stripe_customer_id=customer_id, cancel_at_period_end=False)
                result["plan"] = "free"
            elif plan in {"super", "premium"}:
                set_plan(
                    connection,
                    user_row,
                    plan,
                    source="stripe",
                    status=status or "active",
                    period_end=period_end,
                    note="Stripe subscription",
                    stripe_customer_id=customer_id,
                    stripe_subscription_id=str(obj.get("id") or ""),
                    cancel_at_period_end=bool(obj.get("cancel_at_period_end")),
                )
                result["plan"] = plan
    connection.execute(
        "INSERT OR IGNORE INTO app_payment_events (id, type, user_id, created_at, payload) VALUES (?, ?, ?, ?, ?)",
        (event_id or f"local-{time.time()}", event_type, int(user_row["id"]) if user_row else None, _iso(_now()), json.dumps(event)[:20000]),
    )
    result["user_id"] = int(user_row["id"]) if user_row else None
    return result


def public_catalog() -> dict[str, Any]:
    return {
        "plans": [
            {**{k: v for k, v in PLANS[plan].items()}, "features": plan_features(plan)}
            for plan in PLAN_ORDER
        ],
        "features": [{"key": key, **info} for key, info in FEATURES.items()],
        "stripe_enabled": stripe_enabled(),
        "stripe_test_mode": stripe_enabled() and stripe_test_mode(),
        "trial_days": TRIAL_DAYS,
    }
