from __future__ import annotations

from typing import Any

# Read-only SQL against the Oracle schema in docs/data-sync/schema.md. Each function takes an
# already-open connection (see db.get_connection) and returns raw DB-API rows -- shaping into
# response models happens in main.py, keeping this module a thin, easily mockable data-access
# layer (no Pydantic/FastAPI knowledge here).


# Current presence + sensor health for every machine, for the "Giám sát" tab's status poll.
def fetch_machine_status(conn: Any) -> list[tuple[Any, ...]]:
    cursor = conn.cursor()
    cursor.execute(
        "SELECT machine_id, present_now, last_seen, sensor_ok, session_start "
        "FROM machine_status ORDER BY machine_id"
    )
    return cursor.fetchall()


# One machine's sessions for one day, ordered by start_time.
def fetch_sessions(conn: Any, machine_id: str, date: str) -> list[tuple[Any, ...]]:
    cursor = conn.cursor()
    cursor.execute(
        "SELECT start_time, end_time, duration_min, end_reason "
        "FROM machine_sessions "
        "WHERE machine_id = :machine_id AND session_date = TO_DATE(:target_date, 'YYYY-MM-DD') "
        "ORDER BY start_time",
        {"machine_id": machine_id, "target_date": date},
    )
    return cursor.fetchall()


# Total present minutes per machine for one day (machine_id filter optional). LEFT JOINs from
# machine_status so a machine with zero sessions that day still gets a present_min=0 row,
# instead of being silently omitted.
def fetch_fte(conn: Any, date: str, machine_id: str | None) -> list[tuple[Any, ...]]:
    cursor = conn.cursor()
    cursor.execute(
        "SELECT ms.machine_id, NVL(SUM(s.duration_min), 0) "
        "FROM machine_status ms "
        "LEFT JOIN machine_sessions s "
        "  ON s.machine_id = ms.machine_id AND s.session_date = TO_DATE(:target_date, 'YYYY-MM-DD') "
        "WHERE (:machine_id IS NULL OR ms.machine_id = :machine_id) "
        "GROUP BY ms.machine_id "
        "ORDER BY ms.machine_id",
        {"target_date": date, "machine_id": machine_id},
    )
    return cursor.fetchall()
