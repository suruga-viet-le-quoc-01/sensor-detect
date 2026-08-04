from datetime import datetime
from typing import Any

import oracledb
import pytest

from src.session import Session
from src.storage.oracle_sync import sync_pending, upsert_machine_status
from src.storage.sqlite_buffer import fetch_unsynced, init_db, insert_session

_SESSION = Session(
    machine_id="CNC-07",
    session_date="2026-07-13",
    start_time=datetime(2026, 7, 13, 8, 0, 5),
    end_time=datetime(2026, 7, 13, 8, 42, 31),
    duration_min=42.43,
    end_reason="left",
)


class _FakeCursor:
    def __init__(self, fail_with: Exception | None) -> None:
        self._fail_with = fail_with
        self.executed: list[tuple[str, dict[str, Any]]] = []

    def execute(self, sql: str, binds: dict[str, Any] | None = None) -> None:
        self.executed.append((sql, binds or {}))
        if self._fail_with is not None:
            raise self._fail_with


class _FakeConnection:
    def __init__(self, fail_with: Exception | None = None) -> None:
        self._cursor = _FakeCursor(fail_with)
        self.committed = False
        self.closed = False

    def cursor(self) -> _FakeCursor:
        return self._cursor

    def commit(self) -> None:
        self.committed = True

    def close(self) -> None:
        self.closed = True


@pytest.fixture(autouse=True)
def _oracle_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ORACLE_USER", "u")
    monkeypatch.setenv("ORACLE_PASSWORD", "p")
    monkeypatch.setenv("ORACLE_DSN", "host:1521/service")


def test_sync_pending_marks_row_synced_on_success(tmp_path, monkeypatch):
    sqlite_conn = init_db(str(tmp_path / "buffer.db"))
    session_id = insert_session(sqlite_conn, _SESSION)
    fake_oracle = _FakeConnection()
    monkeypatch.setattr(oracledb, "connect", lambda **_kwargs: fake_oracle)

    sync_pending(sqlite_conn)

    assert fetch_unsynced(sqlite_conn) == []
    row = sqlite_conn.execute("SELECT * FROM sessions WHERE session_id = ?", (session_id,)).fetchone()
    assert row["synced"] == 1
    assert row["synced_at"] is not None
    assert fake_oracle.committed is True


def test_sync_pending_keeps_row_unsynced_when_connect_fails(tmp_path, monkeypatch):
    sqlite_conn = init_db(str(tmp_path / "buffer.db"))
    insert_session(sqlite_conn, _SESSION)

    def _raise(**_kwargs: Any) -> None:
        raise oracledb.OperationalError("no listener")

    monkeypatch.setattr(oracledb, "connect", _raise)

    sync_pending(sqlite_conn)  # must not raise

    rows = fetch_unsynced(sqlite_conn)
    assert len(rows) == 1
    assert rows[0]["synced"] == 0


def test_sync_pending_keeps_row_unsynced_on_merge_network_error(tmp_path, monkeypatch):
    sqlite_conn = init_db(str(tmp_path / "buffer.db"))
    insert_session(sqlite_conn, _SESSION)
    fake_oracle = _FakeConnection(fail_with=oracledb.OperationalError("connection lost"))
    monkeypatch.setattr(oracledb, "connect", lambda **_kwargs: fake_oracle)

    sync_pending(sqlite_conn)  # must not raise

    rows = fetch_unsynced(sqlite_conn)
    assert len(rows) == 1
    assert rows[0]["synced"] == 0
    assert fake_oracle.closed is True  # connection still released even on failure


def test_sync_pending_marks_sync_error_when_oracle_rejects_row(tmp_path, monkeypatch):
    sqlite_conn = init_db(str(tmp_path / "buffer.db"))
    session_id = insert_session(sqlite_conn, _SESSION)
    fake_oracle = _FakeConnection(fail_with=oracledb.IntegrityError("ORA-02290: check constraint violated"))
    monkeypatch.setattr(oracledb, "connect", lambda **_kwargs: fake_oracle)

    sync_pending(sqlite_conn)  # must not raise

    assert fetch_unsynced(sqlite_conn) == []
    row = sqlite_conn.execute("SELECT * FROM sessions WHERE session_id = ?", (session_id,)).fetchone()
    assert row["synced"] == -1


def test_sync_pending_no_op_when_nothing_unsynced(tmp_path, monkeypatch):
    sqlite_conn = init_db(str(tmp_path / "buffer.db"))
    calls = []
    monkeypatch.setattr(oracledb, "connect", lambda **_kwargs: calls.append(1))

    sync_pending(sqlite_conn)  # must not raise, must not even try connecting

    assert calls == []


def test_upsert_machine_status_swallows_connection_failure(monkeypatch):
    def _raise(**_kwargs: Any) -> None:
        raise oracledb.OperationalError("no listener")

    monkeypatch.setattr(oracledb, "connect", _raise)

    upsert_machine_status("CNC-07", present_now=True, sensor_ok=True)  # must not raise


def test_upsert_machine_status_sends_expected_binds(monkeypatch):
    fake_oracle = _FakeConnection()
    monkeypatch.setattr(oracledb, "connect", lambda **_kwargs: fake_oracle)

    session_start = datetime(2026, 7, 24, 9, 0, 0)
    upsert_machine_status("CNC-07", present_now=True, sensor_ok=False, session_start=session_start)

    _sql, binds = fake_oracle.cursor().executed[0]
    assert binds["machine_id"] == "CNC-07"
    assert binds["present_now"] == 1
    assert binds["sensor_ok"] == 0
    assert binds["session_start"] == session_start
    assert fake_oracle.committed is True
    assert fake_oracle.closed is True
