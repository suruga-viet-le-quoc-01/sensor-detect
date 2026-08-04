import socket
from typing import Any

import oracledb
import pytest

from src.web_api.db import DBUnavailableError, connection_scope

# Credentials aren't read from a real .env here -- these tests only exercise db._connect()'s
# exception mapping, with oracledb.connect() itself monkeypatched to fail in different ways.


@pytest.fixture(autouse=True)
def _oracle_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ORACLE_USER", "u")
    monkeypatch.setenv("ORACLE_PASSWORD", "p")
    monkeypatch.setenv("ORACLE_DSN", "host:1521/service")


def test_connection_scope_raises_db_unavailable_on_oracledb_error(monkeypatch: pytest.MonkeyPatch) -> None:
    def _raise(**_kwargs: Any) -> None:
        raise oracledb.DatabaseError("ORA-12541: TNS:no listener")

    monkeypatch.setattr(oracledb, "connect", _raise)

    with pytest.raises(DBUnavailableError):
        with connection_scope():
            pass


# Regression: a bad host/unreachable network raises a plain socket-level OSError (e.g.
# socket.gaierror on DNS failure) before oracledb ever gets far enough to raise its own error
# type -- confirmed against a real placeholder DSN, where this used to leak out as an
# unhandled 500 instead of the intended 503 db_unavailable.
def test_connection_scope_raises_db_unavailable_on_os_error(monkeypatch: pytest.MonkeyPatch) -> None:
    def _raise(**_kwargs: Any) -> None:
        raise socket.gaierror("getaddrinfo failed")

    monkeypatch.setattr(oracledb, "connect", _raise)

    with pytest.raises(DBUnavailableError):
        with connection_scope():
            pass
