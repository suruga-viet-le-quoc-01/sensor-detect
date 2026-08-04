from datetime import datetime, timedelta

from src.session import Session
from src.storage.sqlite_buffer import (
    cleanup_retention,
    fetch_unsynced,
    init_db,
    insert_session,
    mark_sync_error,
    mark_synced,
)

_SESSION = Session(
    machine_id="CNC-07",
    session_date="2026-07-13",
    start_time=datetime(2026, 7, 13, 8, 0, 5),
    end_time=datetime(2026, 7, 13, 8, 42, 31),
    duration_min=42.43,
    end_reason="left",
)


def test_insert_session_is_buffered_as_unsynced(tmp_path):
    conn = init_db(str(tmp_path / "buffer.db"))

    session_id = insert_session(conn, _SESSION)
    rows = fetch_unsynced(conn)

    assert len(rows) == 1
    assert rows[0]["session_id"] == session_id
    assert rows[0]["machine_id"] == "CNC-07"
    assert rows[0]["synced"] == 0


def test_mark_synced_removes_row_from_unsynced(tmp_path):
    conn = init_db(str(tmp_path / "buffer.db"))
    session_id = insert_session(conn, _SESSION)

    mark_synced(conn, session_id, datetime(2026, 7, 13, 8, 43, 0))

    assert fetch_unsynced(conn) == []
    row = conn.execute("SELECT * FROM sessions WHERE session_id = ?", (session_id,)).fetchone()
    assert row["synced"] == 1
    assert row["synced_at"] == "2026-07-13T08:43:00"


def test_mark_sync_error_removes_row_from_unsynced_without_marking_synced(tmp_path):
    conn = init_db(str(tmp_path / "buffer.db"))
    session_id = insert_session(conn, _SESSION)

    mark_sync_error(conn, session_id)

    assert fetch_unsynced(conn) == []
    row = conn.execute("SELECT * FROM sessions WHERE session_id = ?", (session_id,)).fetchone()
    assert row["synced"] == -1


def _insert_with_synced_at(conn, synced: int, synced_at: str | None) -> str:
    session_id = insert_session(conn, _SESSION)
    conn.execute(
        "UPDATE sessions SET synced = ?, synced_at = ? WHERE session_id = ?",
        (synced, synced_at, session_id),
    )
    conn.commit()
    return session_id


def test_cleanup_retention_deletes_old_synced_rows(tmp_path):
    conn = init_db(str(tmp_path / "buffer.db"))
    old_synced_at = (datetime.now() - timedelta(days=8)).isoformat()
    _insert_with_synced_at(conn, synced=1, synced_at=old_synced_at)

    deleted = cleanup_retention(conn, retention_days=7)

    assert deleted == 1
    assert conn.execute("SELECT COUNT(*) FROM sessions").fetchone()[0] == 0


def test_cleanup_retention_keeps_recently_synced_rows(tmp_path):
    conn = init_db(str(tmp_path / "buffer.db"))
    recent_synced_at = (datetime.now() - timedelta(days=3)).isoformat()
    _insert_with_synced_at(conn, synced=1, synced_at=recent_synced_at)

    deleted = cleanup_retention(conn, retention_days=7)

    assert deleted == 0
    assert conn.execute("SELECT COUNT(*) FROM sessions").fetchone()[0] == 1


def test_cleanup_retention_never_deletes_unsynced_rows(tmp_path):
    conn = init_db(str(tmp_path / "buffer.db"))
    _insert_with_synced_at(conn, synced=0, synced_at=None)

    deleted = cleanup_retention(conn, retention_days=0)

    assert deleted == 0
    assert conn.execute("SELECT COUNT(*) FROM sessions").fetchone()[0] == 1


def test_cleanup_retention_never_deletes_error_rows(tmp_path):
    conn = init_db(str(tmp_path / "buffer.db"))
    old_synced_at = (datetime.now() - timedelta(days=30)).isoformat()
    _insert_with_synced_at(conn, synced=-1, synced_at=old_synced_at)

    deleted = cleanup_retention(conn, retention_days=7)

    assert deleted == 0
    assert conn.execute("SELECT COUNT(*) FROM sessions").fetchone()[0] == 1
