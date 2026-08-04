from __future__ import annotations

import os
import sqlite3
from datetime import date, datetime
from typing import Any

import oracledb

from .sqlite_buffer import fetch_unsynced, mark_sync_error, mark_synced

# Pushes the local SQLite buffer up to Oracle (docs/data-sync/rules.md). Every write here is a
# MERGE keyed on the table's natural key, so retrying the same row after a failure is always safe.


# Raised when the Oracle connection can't be established for this sync attempt.
class SyncError(RuntimeError):
    pass


# Open a short-lived Oracle connection. Catches OSError alongside oracledb.Error -- a bad
# host/unreachable network raises a plain socket-level OSError before oracledb ever gets far
# enough to raise its own error type (same reasoning as src/web_api/db.py's _connect(), kept as a
# separate copy here since storage/ writes and web_api/ only reads -- different bounded contexts).
def _connect() -> Any:
    try:
        return oracledb.connect(
            user=os.environ["ORACLE_USER"],
            password=os.environ["ORACLE_PASSWORD"],
            dsn=os.environ["ORACLE_DSN"],
        )
    except (oracledb.Error, OSError) as exc:
        raise SyncError(str(exc)) from exc


_MERGE_SESSION_SQL = """
MERGE INTO machine_sessions dst
USING (
  SELECT
    :session_id AS session_id,
    :machine_id AS machine_id,
    :session_date AS session_date,
    :start_time AS start_time,
    :end_time AS end_time,
    :duration_min AS duration_min,
    :end_reason AS end_reason
  FROM dual
) src
ON (dst.machine_id = src.machine_id AND dst.start_time = src.start_time)
WHEN MATCHED THEN UPDATE SET
  dst.end_time = src.end_time,
  dst.duration_min = src.duration_min,
  dst.end_reason = src.end_reason,
  dst.session_date = src.session_date
WHEN NOT MATCHED THEN INSERT (session_id, machine_id, session_date, start_time, end_time, duration_min, end_reason)
  VALUES (src.session_id, src.machine_id, src.session_date, src.start_time, src.end_time, src.duration_min, src.end_reason)
"""


# Push one buffered row to Oracle. Binds native datetime/date objects (not formatted strings) so
# there's no TO_TIMESTAMP format-string mismatch to worry about.
def _merge_session(conn: Any, row: sqlite3.Row) -> None:
    cursor = conn.cursor()
    cursor.execute(
        _MERGE_SESSION_SQL,
        {
            "session_id": row["session_id"],
            "machine_id": row["machine_id"],
            "session_date": date.fromisoformat(row["session_date"]),
            "start_time": datetime.fromisoformat(row["start_time"]),
            "end_time": datetime.fromisoformat(row["end_time"]) if row["end_time"] else None,
            "duration_min": row["duration_min"],
            "end_reason": row["end_reason"],
        },
    )


# Sweep every unsynced row in the SQLite buffer and try pushing each to Oracle -- used both for
# the per-session immediate push and the periodic retry cycle (docs/data-sync/rules.md).
# - Oracle rejects the row (e.g. a constraint violation) -> mark_sync_error (synced=-1), never
#   auto-retried, keep going with the remaining rows (this row's problem, not the connection's).
# - Network/connection failure -> leave synced=0, stop the sweep (every remaining row would hit
#   the same broken connection; next cycle retries all of them).
def sync_pending(sqlite_conn: sqlite3.Connection) -> None:
    rows = fetch_unsynced(sqlite_conn)
    if not rows:
        return

    try:
        oracle_conn = _connect()
    except SyncError as exc:
        print(f"警告: Oracle に接続できません。同期を次回に持ち越します。詳細: {exc}")
        return

    try:
        for row in rows:
            try:
                _merge_session(oracle_conn, row)
                oracle_conn.commit()
            except oracledb.IntegrityError as exc:
                print(f"エラー: セッション {row['session_id']} が Oracle に拒否されました（要確認）。詳細: {exc}")
                mark_sync_error(sqlite_conn, row["session_id"])
                continue
            except (oracledb.Error, OSError) as exc:
                print(f"警告: Oracle への同期が失敗しました。次回サイクルで再試行します。詳細: {exc}")
                return

            mark_synced(sqlite_conn, row["session_id"], datetime.now())
    finally:
        oracle_conn.close()


_MERGE_STATUS_SQL = """
MERGE INTO machine_status dst
USING (
  SELECT
    :machine_id AS machine_id,
    :last_seen AS last_seen,
    :present_now AS present_now,
    :sensor_ok AS sensor_ok,
    :session_start AS session_start
  FROM dual
) src
ON (dst.machine_id = src.machine_id)
WHEN MATCHED THEN UPDATE SET
  dst.last_seen = src.last_seen,
  dst.present_now = src.present_now,
  dst.sensor_ok = src.sensor_ok,
  dst.session_start = src.session_start
WHEN NOT MATCHED THEN INSERT (machine_id, last_seen, present_now, sensor_ok, session_start)
  VALUES (src.machine_id, src.last_seen, src.present_now, src.sensor_ok, src.session_start)
"""


# Heartbeat for the Giám sát web tab (docs/data-sync/schema.md): upserts this machine's current
# presence + sensor health. `session_start` is the start_time of the currently-open session (or
# None when nobody is present) -- lets the dashboard add the open session's live elapsed time on
# top of closed-session totals. A missed heartbeat isn't fatal (next call retries naturally) so
# failures are logged and swallowed rather than raised.
def upsert_machine_status(
    machine_id: str, present_now: bool, sensor_ok: bool, session_start: datetime | None = None
) -> None:
    try:
        conn = _connect()
    except SyncError as exc:
        print(f"警告: 機器状態の送信に失敗しました（Oracle 接続不可）。詳細: {exc}")
        return

    try:
        conn.cursor().execute(
            _MERGE_STATUS_SQL,
            {
                "machine_id": machine_id,
                "last_seen": datetime.now(),
                "present_now": int(present_now),
                "sensor_ok": int(sensor_ok),
                "session_start": session_start,
            },
        )
        conn.commit()
    except (oracledb.Error, OSError) as exc:
        print(f"警告: 機器状態の送信に失敗しました。詳細: {exc}")
    finally:
        conn.close()
