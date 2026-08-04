from __future__ import annotations

import argparse
import os
import signal
import sqlite3
import threading
from datetime import datetime
from datetime import time as dt_time

from dotenv import load_dotenv

from src.protocol import parse_next_data_frame
from src.sensor.transport import SensorTransport, create_transport
from src.session import END_REASON_SHIFT_END, END_REASON_SIGNAL_LOST, Session, SessionStateMachine
from src.storage import cleanup_retention, init_db, insert_session, sync_pending, upsert_machine_status


# Parse "HH:MM" from .env into a time, or None if unset (no shift-end auto-close).
def _parse_shift_end_time(value: str) -> dt_time | None:
    if not value:
        return None

    hour, minute = value.split(":")
    return dt_time(int(hour), int(minute))


# Print one completed session to stdout. Only machine_id + timestamps + reason -- no identifying
# data, per this project's privacy rule.
def _print_session(session: Session) -> None:
    print(
        f"session closed: machine_id={session.machine_id} date={session.session_date} "
        f"start={session.start_time.isoformat()} end={session.end_time.isoformat()} "
        f"duration_min={session.duration_min} reason={session.end_reason}"
    )


# Handle one just-closed session: always print it, and in prod mode (sqlite_conn set) buffer it
# locally then try an immediate push to Oracle -- the "per-session sync" from
# docs/data-sync/rules.md. `sqlite_conn` is None in --dry-run, where this is a pure no-op beyond
# the print.
def _handle_session(session: Session, sqlite_conn: sqlite3.Connection | None) -> None:
    _print_session(session)

    if sqlite_conn is not None:
        insert_session(sqlite_conn, session)
        sync_pending(sqlite_conn)


# Set a threading.Event on SIGINT (Ctrl+C) so the main loop can shut down cleanly instead of
# being killed mid-iteration.
def _install_sigint_handler() -> threading.Event:
    stop = threading.Event()

    def _handler(_signum: int, _frame: object) -> None:
        stop.set()

    signal.signal(signal.SIGINT, _handler)
    return stop


# Drain every complete frame currently sitting in `buffer`, feeding each one's presence into
# `state_machine`. Returns the leftover (incomplete) buffer and whether any frame was decoded --
# the caller uses the latter to know whether the sensor is still responding.
def _drain_frames(
    buffer: bytes,
    state_machine: SessionStateMachine,
    now: datetime,
    sqlite_conn: sqlite3.Connection | None,
    verbose: bool,
) -> tuple[bytes, bool]:
    got_frame = False

    while True:
        frame, buffer = parse_next_data_frame(buffer)
        if frame is None:
            return buffer, got_frame

        got_frame = True
        # The per-frame line is a tuning aid (~10/s). Skip it in prod so a long-running service
        # doesn't spend I/O printing and bloat its redirected log with ~864k lines/day.
        if verbose:
            print(
                f"{now.isoformat()} present={int(frame.present)} state={frame.target_state} "
                f"moving_cm={frame.moving_distance_cm} static_cm={frame.static_distance_cm}"
            )
        session = state_machine.update(frame.present, now)
        if session is not None:
            _handle_session(session, sqlite_conn)


# Read + process sensor data until shift-end or Ctrl+C, tracking sensor connectivity and closing
# any open session with a reason appropriate to why the loop stopped. `sqlite_conn` is None in
# --dry-run; when set, also runs the periodic Oracle sync / retention cleanup / machine_status
# heartbeat from docs/data-sync/rules.md.
def _run_loop(
    transport: SensorTransport,
    state_machine: SessionStateMachine,
    machine_id: str,
    sensor_timeout_s: float,
    shift_end_time: dt_time | None,
    sqlite_conn: sqlite3.Connection | None,
    sync_interval_s: float,
    retention_days: int,
    status_interval_s: float,
    verbose: bool,
) -> None:
    stop = _install_sigint_handler()
    buffer = b""
    last_frame_at = datetime.now()
    sensor_ok = True
    # datetime.min guarantees the first loop iteration fires both immediately, instead of waiting
    # a full interval before the dashboard/Oracle sees anything.
    last_sync_at = datetime.min
    last_status_at = datetime.min

    with transport:
        while not stop.is_set():
            now = datetime.now()

            if shift_end_time is not None and now.time() >= shift_end_time:
                break

            chunk = transport.read(timeout=1.0)
            if chunk:
                buffer += chunk

            buffer, got_frame = _drain_frames(buffer, state_machine, now, sqlite_conn, verbose)

            if got_frame:
                last_frame_at = now
                if not sensor_ok:
                    print("sensor reconnected")
                sensor_ok = True
            elif (now - last_frame_at).total_seconds() >= sensor_timeout_s:
                if sensor_ok:
                    print(f"warning: no data from sensor for {sensor_timeout_s}s")
                sensor_ok = False
                session = state_machine.close(END_REASON_SIGNAL_LOST, now)
                if session is not None:
                    _handle_session(session, sqlite_conn)

            if sqlite_conn is not None:
                if (now - last_sync_at).total_seconds() >= sync_interval_s:
                    sync_pending(sqlite_conn)
                    cleanup_retention(sqlite_conn, retention_days)
                    last_sync_at = now

                if (now - last_status_at).total_seconds() >= status_interval_s:
                    upsert_machine_status(
                        machine_id,
                        present_now=state_machine.is_active,
                        sensor_ok=sensor_ok,
                        session_start=state_machine.session_start,
                    )
                    last_status_at = now

    session = state_machine.close(END_REASON_SHIFT_END, datetime.now())
    if session is not None:
        _handle_session(session, sqlite_conn)

    if sqlite_conn is not None:
        sync_pending(sqlite_conn)  # flush on exit
        # Mark the machine absent + clear the open-session marker on a clean exit, so the dashboard
        # doesn't keep showing "present" (and ticking worked time) after the reader stops. A crash
        # can't run this -- the dashboard also treats a stale last_seen as offline as a backstop.
        upsert_machine_status(machine_id, present_now=False, sensor_ok=sensor_ok, session_start=None)


# Entry point: python -m src.workflows.run_reader [--dry-run]
def main() -> None:
    load_dotenv()

    parser = argparse.ArgumentParser(description="Read LD2410C presence and record sessions")
    parser.add_argument("--dry-run", action="store_true", help="print sessions, do not write SQLite/Oracle")
    parser.add_argument(
        "--verbose", action="store_true", help="also print every decoded frame (implied by --dry-run)"
    )
    args = parser.parse_args()

    machine_id = os.environ["MACHINE_ID"]
    presence_min_duration_s = float(os.environ.get("PRESENCE_MIN_DURATION_S", "4"))
    debounce_s = float(os.environ.get("DEBOUNCE_S", "5"))
    sensor_timeout_s = float(os.environ.get("SENSOR_TIMEOUT_S", "30"))
    shift_end_time = _parse_shift_end_time(os.environ.get("SHIFT_END_TIME", ""))

    sqlite_conn = None
    sync_interval_s = float(os.environ.get("SYNC_INTERVAL_S", "60"))
    retention_days = int(os.environ.get("RETENTION_DAYS", "7"))
    status_interval_s = float(os.environ.get("STATUS_UPDATE_INTERVAL_S", "5"))
    if not args.dry_run:
        sqlite_conn = init_db(os.environ.get("SQLITE_BUFFER_PATH", "data/buffer.db"))

    transport = create_transport()
    state_machine = SessionStateMachine(
        machine_id=machine_id,
        presence_min_duration_s=presence_min_duration_s,
        debounce_s=debounce_s,
    )

    _run_loop(
        transport,
        state_machine,
        machine_id,
        sensor_timeout_s,
        shift_end_time,
        sqlite_conn,
        sync_interval_s,
        retention_days,
        status_interval_s,
        verbose=args.dry_run or args.verbose,
    )


if __name__ == "__main__":
    main()
