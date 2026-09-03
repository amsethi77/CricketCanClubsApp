#!/usr/bin/env python3
"""Synchronize the CricketClubApp SQLite database locally or against Azure.

Usage examples:

  # Push local database to Azure
  python3 scripts/db_sync.py --direction push --base-url https://cricketcanclubs-web.azurewebsites.net --token "$X_AUTH_TOKEN"

  # Pull Azure database down to the local machine
  python3 scripts/db_sync.py --direction pull --base-url https://cricketcanclubs-web.azurewebsites.net --token "$X_AUTH_TOKEN"

The script moves the raw SQLite database file so the two environments stay
bit-for-bit identical when you choose a direction. It is intentionally simple
and predictable: push local -> remote or pull remote -> local.
"""

from __future__ import annotations

import argparse
import os
import sqlite3
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

import httpx


DEFAULT_DB_NAME = "cricketclubapp.db"


def _default_local_db_path() -> Path:
    env_path = os.getenv("CRICKETCLUBAPP_DATABASE_FILE")
    if env_path:
        return Path(env_path)
    return Path(__file__).resolve().parents[1] / "app" / "data" / DEFAULT_DB_NAME


def _validate_database(path: Path) -> None:
    if not path.exists():
        raise FileNotFoundError(f"Database file not found: {path}")
    with sqlite3.connect(str(path)) as connection:
        connection.row_factory = sqlite3.Row
        integrity_row = connection.execute("PRAGMA integrity_check").fetchone()
        if not integrity_row or str(integrity_row[0] or "").strip().lower() != "ok":
            raise RuntimeError(f"Integrity check failed for {path}")


def _backup_path(path: Path) -> Path:
    return path.with_name(f"{path.stem}.backup{path.suffix}")


def _download_remote_db(base_url: str, token: str) -> bytes:
    with httpx.Client(timeout=120.0, follow_redirects=True) as client:
        response = client.get(
            f"{base_url.rstrip('/')}/api/admin/db/export",
            headers={"x-auth-token": token},
        )
        response.raise_for_status()
        return response.content


def _upload_remote_db(base_url: str, token: str, db_path: Path) -> dict[str, Any]:
    with httpx.Client(timeout=120.0, follow_redirects=True) as client:
        with db_path.open("rb") as handle:
            response = client.post(
                f"{base_url.rstrip('/')}/api/admin/db/import",
                headers={"x-auth-token": token},
                files={"database": (db_path.name, handle, "application/x-sqlite3")},
            )
        response.raise_for_status()
        return response.json()


def pull_remote_to_local(base_url: str, token: str, local_db: Path) -> None:
    payload = _download_remote_db(base_url, token)
    with TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir) / local_db.name
        temp_path.write_bytes(payload)
        _validate_database(temp_path)
        if local_db.exists():
            local_db.replace(_backup_path(local_db))
        temp_path.replace(local_db)
    _validate_database(local_db)
    print(f"Pulled remote database to {local_db}")


def push_local_to_remote(base_url: str, token: str, local_db: Path) -> None:
    _validate_database(local_db)
    result = _upload_remote_db(base_url, token, local_db)
    print(
        "Pushed local database to remote: "
        f"members={result.get('members', 0)} fixtures={result.get('fixtures', 0)} archives={result.get('archives', 0)}"
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Synchronize the CricketClubApp SQLite database.")
    parser.add_argument("--direction", choices=["push", "pull"], required=True, help="Push local to remote or pull remote to local.")
    parser.add_argument("--base-url", required=True, help="Remote app base URL, e.g. https://cricketcanclubs-web.azurewebsites.net")
    parser.add_argument("--token", default=os.getenv("X_AUTH_TOKEN", ""), help="Superadmin auth token for the remote app.")
    parser.add_argument("--local-db", default=str(_default_local_db_path()), help="Local SQLite database file path.")
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    local_db = Path(args.local_db)
    token = str(args.token or "").strip()
    if not token:
        raise SystemExit("A superadmin auth token is required via --token or X_AUTH_TOKEN.")

    if args.direction == "push":
        push_local_to_remote(args.base_url, token, local_db)
    else:
        pull_remote_to_local(args.base_url, token, local_db)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
