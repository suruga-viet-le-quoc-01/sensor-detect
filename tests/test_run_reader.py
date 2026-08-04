import sys
from datetime import datetime, time

import pytest

from src.session import SessionStateMachine
from src.workflows import run_reader
from src.workflows.run_reader import _drain_frames, _parse_shift_end_time

_VALID_BASIC_FRAME = bytes.fromhex(
    "F4 F3 F2 F1 0D 00 02 AA 02 51 00 00 00 00 3B 00 00 55 00 F8 F7 F6 F5"
)


def test_parse_shift_end_time_empty_returns_none():
    assert _parse_shift_end_time("") is None


def test_parse_shift_end_time_parses_hh_mm():
    assert _parse_shift_end_time("17:30") == time(17, 30)


def test_drain_frames_empty_buffer_reports_no_frame():
    sm = SessionStateMachine(machine_id="CNC-07", presence_min_duration_s=4, debounce_s=5)
    remaining, got_frame = _drain_frames(b"", sm, datetime.now(), None, False)
    assert got_frame is False
    assert remaining == b""


def test_drain_frames_feeds_presence_into_state_machine():
    sm = SessionStateMachine(machine_id="CNC-07", presence_min_duration_s=4, debounce_s=5)
    now = datetime(2026, 1, 1, 8, 0, 0)

    remaining, got_frame = _drain_frames(_VALID_BASIC_FRAME, sm, now, None, False)

    assert got_frame is True
    assert remaining == b""
    assert sm.is_active is False  # single sample, hasn't crossed presence_min_duration_s yet


def test_drain_frames_processes_multiple_frames_in_one_buffer():
    sm = SessionStateMachine(machine_id="CNC-07", presence_min_duration_s=4, debounce_s=5)
    now = datetime(2026, 1, 1, 8, 0, 0)
    buffer = _VALID_BASIC_FRAME + _VALID_BASIC_FRAME

    remaining, got_frame = _drain_frames(buffer, sm, now, None, False)

    assert got_frame is True
    assert remaining == b""


# Same verification style already established for configure.py in this project (see
# specs/test-cases.md): confirm prod-mode wiring runs all the way up to the hardware boundary
# (create_transport) without breaking anywhere above it -- not a full hardware integration test.
def test_main_prod_mode_initializes_sqlite_buffer_then_reaches_transport_boundary(tmp_path, monkeypatch):
    monkeypatch.setattr(sys, "argv", ["run_reader"])
    monkeypatch.setenv("MACHINE_ID", "CNC-07")
    buffer_path = tmp_path / "buffer.db"
    monkeypatch.setenv("SQLITE_BUFFER_PATH", str(buffer_path))

    def _boundary(*_args, **_kwargs):
        raise RuntimeError("reached transport boundary")

    monkeypatch.setattr(run_reader, "create_transport", _boundary)

    with pytest.raises(RuntimeError, match="reached transport boundary"):
        run_reader.main()

    assert buffer_path.exists()
