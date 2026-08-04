from __future__ import annotations

import os
import sqlite3
import uuid
from datetime import datetime

from src.session import Session

# Local SQLite buffer -- the source of truth written first, always, per docs/data-sync/rules.md.
# `synced`: 0 = not yet pushed to Oracle, 1 = pushed successfully, -1 = Oracle rejected it
# (needs manual review, never auto-retried).


# Open (creating if needed) the SQLite buffer at `path` and ensure the sessions table exists.
def init_db(path: str) -> sqlite3.Connection:
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)

    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS sessions (
          session_id    TEXT PRIMARY KEY,
          machine_id    TEXT NOT NULL,
          session_date  TEXT NOT NULL,
          start_time    TEXT NOT NULL,
          end_time      TEXT,
          duration_min  REAL NOT NULL,
          end_reason    TEXT NOT NULL,
          synced        INTEGER NOT NULL DEFAULT 0,
          synced_at     TEXT
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS ix_sessions_synced ON sessions (synced)")
    conn.commit()
    return conn


# Buffer one completed session locally (synced=0) -- called right after a session closes, before
# any Oracle push is attempted. Returns the generated session_id.
def insert_session(conn: sqlite3.Connection, session: Session) -> str:
    session_id = str(uuid.uuid4())
    conn.execute(
        "INSERT INTO sessions (session_id, machine_id, session_date, start_time, end_time, "
        "duration_min, end_reason, synced) VALUES (?, ?, ?, ?, ?, ?, ?, 0)",
        (
            session_id,
            session.machine_id,
            session.session_date,
            session.start_time.isoformat(),
            session.end_time.isoformat(),
            session.duration_min,
            session.end_reason,
        ),
    )
    conn.commit()
    return session_id


# Every row not yet successfully pushed to Oracle -- swept by both the per-session push and the
# periodic retry cycle.
def fetch_unsynced(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return conn.execute("SELECT * FROM sessions WHERE synced = 0").fetchall()


# Mark one row as successfully pushed to Oracle.
def mark_synced(conn: sqlite3.Connection, session_id: str, synced_at: datetime) -> None:
    conn.execute(
        "UPDATE sessions SET synced = 1, synced_at = ? WHERE session_id = ?",
        (synced_at.isoformat(), session_id),
    )
    conn.commit()


# Mark one row as rejected by Oracle (e.g. a constraint violation) -- needs manual review,
# never retried automatically.
def mark_sync_error(conn: sqlite3.Connection, session_id: str) -> None:
    conn.execute("UPDATE sessions SET synced = -1 WHERE session_id = ?", (session_id,))
    conn.commit()


# Delete rows that synced successfully more than `retention_days` ago. Never touches synced=0
# (not yet pushed) or synced=-1 (needs review), no matter how old. Returns the number deleted.
def cleanup_retention(conn: sqlite3.Connection, retention_days: int) -> int:
    cursor = conn.execute(
        "DELETE FROM sessions WHERE synced = 1 AND synced_at < datetime('now', ?)",
        (f"-{retention_days} days",),
    )
    conn.commit()
    return cursor.rowcount
