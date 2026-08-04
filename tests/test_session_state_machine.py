from datetime import datetime, timedelta

from src.session.session import END_REASON_LEFT, END_REASON_SHIFT_END, END_REASON_SIGNAL_LOST
from src.session.state_machine import SessionStateMachine

_T0 = datetime(2026, 1, 1, 8, 0, 0)


def _at(seconds: float) -> datetime:
    return _T0 + timedelta(seconds=seconds)


def _machine(presence_min_duration_s: float = 4, debounce_s: float = 5) -> SessionStateMachine:
    return SessionStateMachine(
        machine_id="CNC-07",
        presence_min_duration_s=presence_min_duration_s,
        debounce_s=debounce_s,
    )


def test_brief_passerby_does_not_open_session():
    sm = _machine(presence_min_duration_s=4)

    assert sm.update(True, _at(0)) is None
    assert sm.update(False, _at(2)) is None
    assert sm.is_active is False


def test_sustained_presence_opens_session():
    sm = _machine(presence_min_duration_s=4)

    assert sm.update(True, _at(0)) is None
    assert sm.update(True, _at(2)) is None
    assert sm.update(True, _at(4)) is None

    assert sm.is_active is True
    assert sm.session_start == _at(0)


def test_brief_signal_drop_does_not_close_session():
    sm = _machine(presence_min_duration_s=4, debounce_s=5)
    sm.update(True, _at(0))
    sm.update(True, _at(4))  # session opens, start=t0

    assert sm.update(False, _at(10)) is None  # lost -> CLOSING
    assert sm.update(True, _at(13)) is None  # regained before debounce -> back to ACTIVE

    assert sm.is_active is True
    assert sm.session_start == _at(0)


def test_sustained_absence_closes_session_after_debounce():
    sm = _machine(presence_min_duration_s=4, debounce_s=5)
    sm.update(True, _at(0))
    sm.update(True, _at(4))  # session opens, start=t0

    assert sm.update(False, _at(10)) is None  # lost -> CLOSING

    session = sm.update(False, _at(15))  # still gone at debounce threshold -> closes

    assert session is not None
    assert session.machine_id == "CNC-07"
    assert session.start_time == _at(0)
    assert session.end_time == _at(10)  # end_time is when presence was lost, not now
    assert session.end_reason == END_REASON_LEFT
    assert sm.is_active is False


def test_force_close_on_shift_end():
    sm = _machine()
    sm.update(True, _at(0))
    sm.update(True, _at(4))  # session opens

    session = sm.close(END_REASON_SHIFT_END, _at(100))

    assert session is not None
    assert session.start_time == _at(0)
    assert session.end_time == _at(100)
    assert session.end_reason == END_REASON_SHIFT_END
    assert sm.is_active is False


def test_force_close_while_closing_uses_reason_from_caller():
    sm = _machine(presence_min_duration_s=4, debounce_s=5)
    sm.update(True, _at(0))
    sm.update(True, _at(4))
    sm.update(False, _at(10))  # -> CLOSING

    session = sm.close(END_REASON_SIGNAL_LOST, _at(12))

    assert session is not None
    assert session.end_time == _at(12)
    assert session.end_reason == END_REASON_SIGNAL_LOST


def test_force_close_with_nothing_open_is_a_no_op():
    sm = _machine()
    assert sm.close(END_REASON_SHIFT_END, _at(0)) is None

    sm.update(True, _at(0))  # only CANDIDATE, not yet ACTIVE
    assert sm.close(END_REASON_SHIFT_END, _at(1)) is None


def test_session_crossing_midnight_uses_start_date_and_correct_duration():
    sm = SessionStateMachine(machine_id="CNC-07", presence_min_duration_s=4, debounce_s=5)
    start = datetime(2026, 1, 1, 23, 50, 0)

    sm.update(True, start)
    sm.update(True, start + timedelta(seconds=4))  # session opens, start_time = `start`

    lost_at = datetime(2026, 1, 2, 0, 10, 0)  # 20 minutes later, past midnight
    sm.update(False, lost_at)  # -> CLOSING
    session = sm.update(False, lost_at + timedelta(seconds=5))  # debounce elapses -> closes

    assert session is not None
    assert session.session_date == "2026-01-01"  # date of START, not end
    assert session.duration_min == 20.0
