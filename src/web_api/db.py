from __future__ import annotations

import os
from collections.abc import Generator
from contextlib import contextmanager
from typing import Any

import oracledb


# Raised when the Oracle connection can't be established -- converted to a 503 JSON
# response by the exception handler registered in main.py.
class DBUnavailableError(RuntimeError):
    pass


# Open the Oracle connection. Credentials come from .env, never from the client.
# Catches OSError alongside oracledb.Error -- a bad host/unreachable network (DNS failure,
# connection refused, timeout) raises a plain socket-level OSError before oracledb ever gets far
# enough to raise its own error type, and that's just as much "DB unavailable" as a rejected login.
def _connect() -> Any:
    try:
        return oracledb.connect(
            user=os.environ["ORACLE_USER"],
            password=os.environ["ORACLE_PASSWORD"],
            dsn=os.environ["ORACLE_DSN"],
        )
    except (oracledb.Error, OSError) as exc:
        raise DBUnavailableError(str(exc)) from exc


# A short-lived Oracle connection for one request, always closed on exit. Routes call this
# explicitly (not via FastAPI Depends()) AFTER validating their own input, so a bad request
# never has to wait on -- or get masked by -- a DB connection attempt. See main.py.
@contextmanager
def connection_scope() -> Generator[Any, None, None]:
    conn = _connect()
    try:
        yield conn
    finally:
        conn.close()
