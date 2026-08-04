from __future__ import annotations

import os
from datetime import datetime

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from starlette.requests import Request

from . import queries
from .db import DBUnavailableError, connection_scope
from .schemas import FteOut, MachineStatusOut, SessionOut

# uvicorn imports this module directly (no CLI wrapper like run_reader.py's main()), so .env
# must be loaded here at import time for ORACLE_*/SHIFT_DURATION_MIN to be readable below.
load_dotenv()

# Entry point: uvicorn src.web_api.main:app --reload
app = FastAPI(title="Machine Presence Web API")


# Raised by _parse_date() -- converted to a 400 JSON response, same shape family as
# DBUnavailableError's 503 below.
class InvalidDateError(ValueError):
    pass


# Reject a date string that isn't YYYY-MM-DD. Every route calls this BEFORE
# connection_scope(), as plain sequential code -- not a FastAPI Depends() -- so a bad date
# always reports 400 and never has to wait on (or get masked by) a DB connection attempt.
def _parse_date(date: str) -> str:
    try:
        datetime.strptime(date, "%Y-%m-%d")
    except ValueError:
        raise InvalidDateError(date) from None

    return date


@app.exception_handler(InvalidDateError)
def _handle_invalid_date(_request: Request, _exc: InvalidDateError) -> JSONResponse:
    return JSONResponse(status_code=400, content={"error": "invalid_date"})


# Oracle unreachable -> 503 with a stable error shape the frontend can key off of, instead of a
# generic 500 that would look like a bug in this API itself.
@app.exception_handler(DBUnavailableError)
def _handle_db_unavailable(_request: Request, _exc: DBUnavailableError) -> JSONResponse:
    return JSONResponse(status_code=503, content={"error": "db_unavailable"})


# GET /api/machines/status -- current presence + sensor health for every machine.
@app.get("/api/machines/status", response_model=list[MachineStatusOut])
def get_machines_status() -> list[MachineStatusOut]:
    with connection_scope() as conn:
        rows = queries.fetch_machine_status(conn)

    return [
        MachineStatusOut(
            machine_id=row[0],
            present_now=bool(row[1]),
            last_seen=row[2],
            sensor_ok=bool(row[3]),
            session_start=row[4],
        )
        for row in rows
    ]


# GET /api/machines/{machine_id}/sessions?date=YYYY-MM-DD -- one machine's sessions for one day.
@app.get("/api/machines/{machine_id}/sessions", response_model=list[SessionOut])
def get_machine_sessions(machine_id: str, date: str) -> list[SessionOut]:
    date = _parse_date(date)

    with connection_scope() as conn:
        rows = queries.fetch_sessions(conn, machine_id, date)

    return [
        SessionOut(start_time=row[0], end_time=row[1], duration_min=row[2], end_reason=row[3])
        for row in rows
    ]


# GET /api/fte?date=YYYY-MM-DD&machine_id=... -- FTE + occupancy per machine for one day.
# machine_id omitted means "every machine" (see queries.fetch_fte).
@app.get("/api/fte", response_model=list[FteOut])
def get_fte(date: str, machine_id: str | None = None) -> list[FteOut]:
    date = _parse_date(date)
    shift_min = int(os.environ.get("SHIFT_DURATION_MIN", "480"))

    with connection_scope() as conn:
        rows = queries.fetch_fte(conn, date, machine_id)

    result = []
    for row in rows:
        present_min = float(row[1])
        result.append(
            FteOut(
                machine_id=row[0],
                date=date,
                present_min=present_min,
                shift_min=shift_min,
                fte=round(present_min / shift_min, 2),
                occupancy_pct=round(present_min / shift_min * 100, 1),
            )
        )

    return result
