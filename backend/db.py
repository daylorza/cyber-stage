"""SQLite store: listings (structured JSON), jobs (async pipeline queue), simulated reservations.

SQLite is enough for the hackathon. Migration path: the three tables map 1:1 to Postgres,
with `data` as JSONB and `claim_next_job` as SELECT ... FOR UPDATE SKIP LOCKED.
"""

import json
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import UTC, datetime
from typing import Any, Iterator

import config

SCHEMA = """
CREATE TABLE IF NOT EXISTS listings (
    id TEXT PRIMARY KEY,
    status TEXT NOT NULL,
    source TEXT NOT NULL,
    data TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS jobs (
    id TEXT PRIMARY KEY,
    listing_id TEXT NOT NULL REFERENCES listings(id),
    kind TEXT NOT NULL,
    status TEXT NOT NULL,
    stage TEXT,
    progress INTEGER NOT NULL DEFAULT 0,
    error TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS jobs_by_status ON jobs(status, created_at);
CREATE TABLE IF NOT EXISTS reservations (
    id TEXT PRIMARY KEY,
    listing_id TEXT NOT NULL REFERENCES listings(id),
    status TEXT NOT NULL,
    simulated INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL
);
"""


def now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


@contextmanager
def connect() -> Iterator[sqlite3.Connection]:
    conn = sqlite3.connect(config.settings.db_path, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        with conn:
            yield conn
    finally:
        conn.close()


def init() -> None:
    with connect() as conn:
        conn.execute("PRAGMA journal_mode = WAL")
        conn.executescript(SCHEMA)


def _listing(row: sqlite3.Row | None) -> dict[str, Any] | None:
    return json.loads(row["data"]) if row else None


def insert_listing(conn: sqlite3.Connection, listing: dict[str, Any]) -> None:
    ts = now()
    listing.setdefault("created_at", ts)
    listing["updated_at"] = ts
    conn.execute(
        "INSERT INTO listings (id, status, source, data, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?)",
        (listing["id"], listing["status"], listing["source"], json.dumps(listing), listing["created_at"], ts),
    )


def save_listing(listing: dict[str, Any]) -> dict[str, Any]:
    listing["updated_at"] = now()
    with connect() as conn:
        conn.execute(
            "UPDATE listings SET status = ?, data = ?, updated_at = ? WHERE id = ?",
            (listing["status"], json.dumps(listing), listing["updated_at"], listing["id"]),
        )
    return listing


def get_listing(listing_id: str) -> dict[str, Any] | None:
    with connect() as conn:
        return _listing(conn.execute("SELECT data FROM listings WHERE id = ?", (listing_id,)).fetchone())


def list_listings() -> list[dict[str, Any]]:
    with connect() as conn:
        rows = conn.execute("SELECT data FROM listings ORDER BY created_at DESC").fetchall()
    return [json.loads(r["data"]) for r in rows]


def delete_listing(listing_id: str) -> None:
    with connect() as conn:
        conn.execute("DELETE FROM listings WHERE id = ?", (listing_id,))


def listing_exists(conn: sqlite3.Connection, listing_id: str) -> bool:
    return conn.execute("SELECT 1 FROM listings WHERE id = ?", (listing_id,)).fetchone() is not None


def insert_job(conn: sqlite3.Connection, job_id: str, listing_id: str, kind: str) -> None:
    ts = now()
    conn.execute(
        "INSERT INTO jobs (id, listing_id, kind, status, stage, progress, created_at, updated_at)"
        " VALUES (?, ?, ?, 'queued', NULL, 0, ?, ?)",
        (job_id, listing_id, kind, ts, ts),
    )


def get_job(job_id: str) -> dict[str, Any] | None:
    with connect() as conn:
        row = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
    return dict(row) if row else None


def list_jobs(listing_id: str) -> list[dict[str, Any]]:
    with connect() as conn:
        rows = conn.execute(
            "SELECT * FROM jobs WHERE listing_id = ? ORDER BY created_at, id", (listing_id,)
        ).fetchall()
    return [dict(row) for row in rows]


def claim_next_job() -> dict[str, Any] | None:
    with connect() as conn:
        row = conn.execute(
            "UPDATE jobs SET status = 'running', updated_at = ?"
            " WHERE id = (SELECT id FROM jobs WHERE status = 'queued' ORDER BY created_at LIMIT 1)"
            " RETURNING *",
            (now(),),
        ).fetchone()
    return dict(row) if row else None


def update_job(job_id: str, **fields: Any) -> None:
    fields["updated_at"] = now()
    cols = ", ".join(f"{k} = ?" for k in fields)
    with connect() as conn:
        conn.execute(f"UPDATE jobs SET {cols} WHERE id = ?", (*fields.values(), job_id))


def requeue_interrupted_jobs() -> int:
    with connect() as conn:
        return conn.execute(
            "UPDATE jobs SET status = 'queued', updated_at = ? WHERE status = 'running'", (now(),)
        ).rowcount


def insert_reservation(listing_id: str) -> dict[str, Any]:
    reservation = {
        "id": new_id("res"),
        "listing_id": listing_id,
        "status": "pending_broker_confirmation",
        "simulated": True,
        "created_at": now(),
    }
    with connect() as conn:
        conn.execute(
            "INSERT INTO reservations (id, listing_id, status, simulated, created_at) VALUES (?, ?, ?, 1, ?)",
            (reservation["id"], listing_id, reservation["status"], reservation["created_at"]),
        )
    return reservation
