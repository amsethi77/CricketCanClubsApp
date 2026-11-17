"""Write MD/API.md - the list of every API the web site and the mobile apps use, grouped by feature (Nov 16 2026,
Amit: "All these features that we build should be an API so that it can be used with mobile apps").

Run from the project folder after adding or changing an API, so the guide stays complete:

    python scripts\\api_guide.py

The live, clickable version is /docs on the running site (and /openapi.json for code generators).
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))

import main  # noqa: E402

INTRO = """# CricketCanClubs API (web site and mobile apps)

Every feature of the app works through these JSON APIs - the web pages call them too, so the iOS and Android apps
can do everything the site does. This file is made by `python scripts\\api_guide.py` (run it again after adding or
changing an API). The live, clickable version is **/docs** on the running site (for example
https://cricketcanclubs-web.azurewebsites.net/docs), and **/openapi.json** for code generators.

## How to call it

1. Sign in: `POST /api/auth/signin` with `{"identifier": "<mobile or email>", "password": "..."}`. The answer has
   `token`, the `user` (roles, club) and the clubs he can switch to.
2. Send the token on every call as the header `X-Auth-Token: <token>`. A token stays valid until
   `POST /api/auth/signout` or until it is idle too long (then sign in again: the API answers 401).
3. Switch club: `POST /api/auth/select-club` `{"club_id": "..."}` - club pages, stats and admin lists follow the
   current club.
4. Bodies are JSON (`Content-Type: application/json`); photo uploads are `multipart/form-data` (field `file`).
5. Errors: HTTP 4xx with `{"detail": "a message you can show to the person"}`.

Paths starting `/api/public/` need no sign-in. `/api/admin/...` needs a club admin of that club or the superadmin.

## Main screens -> APIs

| Screen | APIs |
| --- | --- |
| Sign in / register | `POST /api/auth/signin`, `GET /api/auth/options`, `POST /api/auth/register`, `GET /api/auth/me` |
| Home | `GET /api/dashboard`, `GET /api/weather?lat=&lon=`, `GET /api/notifications` |
| Scorecards list / one card | `GET /api/public/scorecards`, `GET /api/public/scorecards/{id}` (names carry `tags` C/VC/WK and `playing_role`) |
| Upload a scorecard photo | `POST /api/scorecards/upload` (answers at once, read in the background), then poll `GET /api/scorecards/{id}/processing`, `GET /api/scorecards/{id}/preview` |
| Fix a read card / confirm names | `POST /api/scorecards/{id}/...` (edit, publish, name-identity, people) - see "Scorecards" below |
| Live scoring | `GET /api/public/match/{id}`, `POST /api/matches/{id}/...` (balls, line-ups, man of the match) |
| Stats | `GET /api/rankings`, `GET /api/stats/captains?year=` |
| Admin: clubs, people & roles | `GET /api/admin/club-management`, `GET /api/admin/clubs/{club_id}/people`, `POST .../people/{user_id}/club-role`, `POST .../people/members/{member_id}/playing-role` |
| Admin: duplicates | `GET /api/admin/name-matches`, `POST /api/admin/name-matches/reject`, member merges |

## Every API, by feature
"""


def main_() -> None:
    schema = main.app.openapi()
    groups: dict[str, list[tuple[str, str, str]]] = {}
    for path, operations in schema.get("paths", {}).items():
        for method, op in operations.items():
            if method not in {"get", "post", "put", "patch", "delete"}:
                continue
            tag = (op.get("tags") or ["Other"])[0]
            text = (op.get("description") or op.get("summary") or "").strip().split("\n")[0]
            groups.setdefault(tag, []).append((method.upper(), path, text.replace("|", "/")[:160]))
    order = list(dict.fromkeys(group for _prefix, group in main.API_GROUPS))
    lines = [INTRO]
    total = 0
    for group in sorted(groups, key=lambda g: order.index(g) if g in order else 99):
        rows = sorted(groups[group], key=lambda r: (r[1], r[0]))
        total += len(rows)
        lines.append(f"\n### {group} ({len(rows)})\n\n| Method | Path | What it does |\n| --- | --- | --- |")
        lines += [f"| {m} | `{p}` | {t} |" for m, p, t in rows]
    lines.append(f"\n{total} APIs.\n")
    out = ROOT / "MD" / "API.md"
    out.write_text("\n".join(lines), encoding="utf-8")
    print(f"Wrote {out} ({total} APIs in {len(groups)} groups).")


if __name__ == "__main__":
    main_()
