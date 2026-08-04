from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel

# Response shapes matching docs/web-dashboard/api-contract.md exactly.


# One row of GET /api/machines/status.
class MachineStatusOut(BaseModel):
    machine_id: str
    present_now: bool
    last_seen: datetime | None
    sensor_ok: bool
    # start_time of the currently-open session (null when nobody is present) -- lets the frontend
    # add the open session's live elapsed time on top of closed-session totals.
    session_start: datetime | None = None


# One row of GET /api/machines/{machine_id}/sessions.
class SessionOut(BaseModel):
    start_time: datetime
    end_time: datetime
    duration_min: float
    end_reason: str


# One row of GET /api/fte.
class FteOut(BaseModel):
    machine_id: str
    date: str
    present_min: float
    shift_min: int
    fte: float
    occupancy_pct: float
