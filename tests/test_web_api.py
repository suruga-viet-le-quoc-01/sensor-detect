from contextlib import contextmanager
from datetime import datetime
from typing import Any

from fastapi.testclient import TestClient

import src.web_api.main as web_api_main
from src.web_api.db import DBUnavailableError

# Minimal DB-API stand-ins that ignore the SQL text and just return canned rows -- this is the
# "mock Oracle" the task asked for: it tests that the API layer shapes whatever the DB returns
# correctly, not that the SQL itself is valid against a real Oracle instance (no Oracle server
# is available in this sandbox).


class _FakeCursor:
    def __init__(self, rows: list[tuple[Any, ...]]) -> None:
        self._rows = rows

    def execute(self, _sql: str, _binds: dict[str, Any] | None = None) -> None:
        pass

    def fetchall(self) -> list[tuple[Any, ...]]:
        return self._rows

    def close(self) -> None:
        pass


class _FakeConnection:
    def __init__(self, rows: list[tuple[Any, ...]]) -> None:
        self._rows = rows

    def cursor(self) -> _FakeCursor:
        return _FakeCursor(self._rows)

    def close(self) -> None:
        pass


def _mock_connection_scope(monkeypatch: Any, rows: list[tuple[Any, ...]]) -> None:
    @contextmanager
    def _fake_scope():
        yield _FakeConnection(rows)

    monkeypatch.setattr(web_api_main, "connection_scope", _fake_scope)


def _mock_connection_scope_raises(monkeypatch: Any) -> None:
    @contextmanager
    def _fake_scope():
        raise DBUnavailableError("connection refused")
        yield  # pragma: no cover -- unreachable, makes this a generator function

    monkeypatch.setattr(web_api_main, "connection_scope", _fake_scope)


def test_machines_status_shape(monkeypatch):
    _mock_connection_scope(
        monkeypatch,
        [
            ("CNC-07", 1, datetime(2026, 7, 23, 9, 15, 2), 1, datetime(2026, 7, 23, 9, 0, 0)),
            ("CNC-09", 0, datetime(2026, 7, 23, 8, 40, 0), 0, None),
        ],
    )
    client = TestClient(web_api_main.app)

    response = client.get("/api/machines/status")

    assert response.status_code == 200
    body = response.json()
    assert body[0] == {
        "machine_id": "CNC-07",
        "present_now": True,
        "last_seen": "2026-07-23T09:15:02",
        "sensor_ok": True,
        "session_start": "2026-07-23T09:00:00",
    }
    assert body[1]["present_now"] is False
    assert body[1]["sensor_ok"] is False
    assert body[1]["session_start"] is None


def test_machine_sessions_shape(monkeypatch):
    _mock_connection_scope(
        monkeypatch,
        [(datetime(2026, 7, 23, 8, 0, 5), datetime(2026, 7, 23, 8, 42, 31), 42.43, "left")],
    )
    client = TestClient(web_api_main.app)

    response = client.get("/api/machines/CNC-07/sessions", params={"date": "2026-07-23"})

    assert response.status_code == 200
    assert response.json() == [
        {
            "start_time": "2026-07-23T08:00:05",
            "end_time": "2026-07-23T08:42:31",
            "duration_min": 42.43,
            "end_reason": "left",
        }
    ]


def test_machine_sessions_invalid_date_returns_400(monkeypatch):
    _mock_connection_scope(monkeypatch, [])
    client = TestClient(web_api_main.app)

    response = client.get("/api/machines/CNC-07/sessions", params={"date": "not-a-date"})

    assert response.status_code == 400
    assert response.json() == {"error": "invalid_date"}


def test_machine_sessions_empty_range_returns_empty_list(monkeypatch):
    _mock_connection_scope(monkeypatch, [])
    client = TestClient(web_api_main.app)

    response = client.get("/api/machines/CNC-07/sessions", params={"date": "2026-07-23"})

    assert response.status_code == 200
    assert response.json() == []


def test_fte_shape_matches_spec_example(monkeypatch):
    _mock_connection_scope(monkeypatch, [("CNC-07", 384.0)])
    client = TestClient(web_api_main.app)

    response = client.get("/api/fte", params={"date": "2026-07-13", "machine_id": "CNC-07"})

    assert response.status_code == 200
    assert response.json() == [
        {
            "machine_id": "CNC-07",
            "date": "2026-07-13",
            "present_min": 384.0,
            "shift_min": 480,
            "fte": 0.80,
            "occupancy_pct": 80.0,
        }
    ]


def test_fte_machine_with_no_sessions_still_returns_row_with_zero(monkeypatch):
    _mock_connection_scope(monkeypatch, [("CNC-08", 0.0)])
    client = TestClient(web_api_main.app)

    response = client.get("/api/fte", params={"date": "2026-07-13"})

    assert response.status_code == 200
    body = response.json()
    assert body[0]["present_min"] == 0.0
    assert body[0]["fte"] == 0.0


def test_db_unavailable_returns_503(monkeypatch):
    _mock_connection_scope_raises(monkeypatch)
    client = TestClient(web_api_main.app)

    response = client.get("/api/machines/status")

    assert response.status_code == 503
    assert response.json() == {"error": "db_unavailable"}


def test_invalid_date_returns_400_even_when_db_is_unreachable(monkeypatch):
    # Regression test: date must be validated before connection_scope() is ever entered, so a
    # bad date reports 400 (not a misleading 503) even when Oracle is down. This holds because
    # _parse_date() runs as plain sequential code in the route body BEFORE the `with
    # connection_scope():` line -- not because of any FastAPI dependency-ordering guarantee.
    _mock_connection_scope_raises(monkeypatch)
    client = TestClient(web_api_main.app)

    response = client.get("/api/machines/CNC-07/sessions", params={"date": "not-a-date"})

    assert response.status_code == 400
    assert response.json() == {"error": "invalid_date"}
