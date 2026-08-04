from __future__ import annotations

from datetime import datetime
from enum import Enum, auto

from .session import END_REASON_LEFT, Session

# Internal FSM states (see docs/realtime-reader/rules.md): IDLE -> CANDIDATE -> ACTIVE -> (CLOSING) -> IDLE.
class _State(Enum):
    IDLE = auto()
    CANDIDATE = auto()
    ACTIVE = auto()
    CLOSING = auto()


# Turns a stream of presence samples into completed Session records: filters out brief
# passers-by (must stay present >= presence_min_duration_s before a session opens) and
# tolerates brief signal drops (must stay absent >= debounce_s before a session auto-closes).
class SessionStateMachine:
    # Store the thresholds and start in IDLE with no session open.
    def __init__(self, machine_id: str, presence_min_duration_s: float, debounce_s: float) -> None:
        self._machine_id = machine_id
        self._presence_min_duration_s = presence_min_duration_s
        self._debounce_s = debounce_s
        self._state = _State.IDLE
        self._candidate_start: datetime | None = None
        self._session_start: datetime | None = None
        self._lost_at: datetime | None = None

    # True while a session is open (ACTIVE or CLOSING) -- for callers that just want to know
    # "is someone present right now" without closing anything (e.g. a status display).
    @property
    def is_active(self) -> bool:
        return self._state in (_State.ACTIVE, _State.CLOSING)

    # start_time of the currently open session, or None if no session is open.
    @property
    def session_start(self) -> datetime | None:
        return self._session_start

    # Process one presence sample. Returns a completed Session if this call closed one
    # (only the debounce-timeout path closes a session here; see close() for forced closes).
    def update(self, present: bool, now: datetime) -> Session | None:
        if self._state is _State.IDLE:
            if present:
                self._state = _State.CANDIDATE
                self._candidate_start = now
            return None

        if self._state is _State.CANDIDATE:
            if not present:
                self._state = _State.IDLE
                self._candidate_start = None
                return None

            assert self._candidate_start is not None
            if (now - self._candidate_start).total_seconds() >= self._presence_min_duration_s:
                self._state = _State.ACTIVE
                self._session_start = self._candidate_start
                self._candidate_start = None

            return None

        if self._state is _State.ACTIVE:
            if not present:
                self._state = _State.CLOSING
                self._lost_at = now

            return None

        # _State.CLOSING
        if present:
            self._state = _State.ACTIVE
            self._lost_at = None
            return None

        assert self._lost_at is not None
        if (now - self._lost_at).total_seconds() >= self._debounce_s:
            return self._close(END_REASON_LEFT, self._lost_at)

        return None

    # Force-close a currently open session (ACTIVE or CLOSING) with the given reason and
    # end_time=now. No-op (returns None) if no session is open. Used for shutdown/shift-end/
    # sensor-timeout, none of which can be expressed as a plain presence sample.
    def close(self, reason: str, now: datetime) -> Session | None:
        if self._state not in (_State.ACTIVE, _State.CLOSING):
            return None

        return self._close(reason, now)

    # Build the Session record and reset to IDLE.
    def _close(self, reason: str, end_time: datetime) -> Session:
        assert self._session_start is not None
        session = Session(
            machine_id=self._machine_id,
            session_date=self._session_start.date().isoformat(),
            start_time=self._session_start,
            end_time=end_time,
            duration_min=round((end_time - self._session_start).total_seconds() / 60, 2),
            end_reason=reason,
        )
        self._state = _State.IDLE
        self._session_start = None
        self._lost_at = None
        return session
