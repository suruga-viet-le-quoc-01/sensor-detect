from __future__ import annotations

import argparse
import os
import signal
import sqlite3
import threading
from datetime import datetime
from datetime import time as dt_time

from dotenv import load_dotenv

from src.protocol import (
    DistanceWindow,
    MalformedFrameError,
    SensorParameters,
    build_enable_config,
    build_end_config,
    build_read_parameters,
    parse_next_data_frame,
    parse_read_parameters_ack,
    presence_in_range,
)
from src.sensor.command_io import send_command
from src.sensor.transport import SensorTransport, create_transport
from src.session import END_REASON_SHIFT_END, END_REASON_SIGNAL_LOST, Session, SessionStateMachine
from src.storage import cleanup_retention, init_db, insert_session, sync_pending, upsert_machine_status

# How often the plain 0/1 presence line is printed (seconds). One line per second stays readable
# and keeps a redirected log manageable, unlike printing every frame (~10/s).
_PRESENCE_LOG_INTERVAL_S = 1.0


# Parse an optional numeric .env value, returning None when it's unset/blank. Strips a trailing
# "# comment" first: some dotenv versions leave the comment text as the value when the value
# itself is blank, which would otherwise turn into a bogus number here.
def _parse_optional_float(value: str) -> float | None:
    cleaned = value.split("#", 1)[0].strip()
    if not cleaned:
        return None

    return float(cleaned)


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
# `state_machine`. Returns (leftover buffer, presence of the last frame, whether any frame was
# decoded) -- the caller uses the last flag to know whether the sensor is still responding.
def _drain_frames(
    buffer: bytes,
    state_machine: SessionStateMachine,
    now: datetime,
    sqlite_conn: sqlite3.Connection | None,
    verbose: bool,
    window: DistanceWindow,
) -> tuple[bytes, bool, bool]:
    last_present = False
    got_frame = False

    while True:
        frame, buffer = parse_next_data_frame(buffer)
        if frame is None:
            return buffer, (last_present if got_frame else False), got_frame

        got_frame = True
        last_present = presence_in_range(frame, window)
        # The per-frame line is a tuning aid (~10/s) -- too noisy to read and it bloats a
        # redirected log, so by default only the once-per-second 0/1 line in _run_loop is printed.
        # `raw` is presence before the distance filter, so it's obvious when a target was seen but
        # rejected for being outside the configured band.
        if verbose:
            print(
                f"{now.isoformat()} present={int(last_present)} raw={int(frame.present)} "
                f"state={frame.target_state} moving_cm={frame.moving_distance_cm} "
                f"static_cm={frame.static_distance_cm}"
            )
        session = state_machine.update(last_present, now)
        if session is not None:
            _handle_session(session, sqlite_conn)


# Read the sensor's current configuration from its flash (enable config -> read -> end config).
# Best-effort: a sensor that doesn't answer must not stop the reader from running, so failures are
# reported and None is returned. Config mode is ALWAYS left again -- staying in it would stop the
# data-output stream the reader depends on. This only READS; it never writes flash.
def _read_sensor_parameters(transport: SensorTransport) -> SensorParameters | None:
    try:
        enable_ack = send_command(transport, build_enable_config())
    except (TimeoutError, MalformedFrameError) as exc:
        print(f"警告: センサー設定を読み出せませんでした（設定モードに入れません）: {exc}")
        return None

    if not enable_ack.ok:
        print("警告: センサーが設定モードを拒否したため、設定の読み出しをスキップします。")
        return None

    try:
        ack = send_command(transport, build_read_parameters())
        if not ack.ok:
            print("警告: センサーが設定の読み出しを拒否しました。")
            return None

        return parse_read_parameters_ack(ack)
    except (TimeoutError, MalformedFrameError) as exc:
        print(f"警告: センサー設定の読み出しに失敗しました: {exc}")
        return None
    finally:
        try:
            send_command(transport, build_end_config())
        except (TimeoutError, MalformedFrameError) as exc:
            print(f"警告: 設定モードを終了できませんでした（データ受信に影響する可能性があります）: {exc}")


# Print the sensor's current detection settings, so an operator starting the reader can see which
# thresholds are actually loaded in the sensor's flash (they're configured from the web app, not
# from .env, so .env can't be used to answer this).
def _print_sensor_parameters(params: SensorParameters | None) -> None:
    if params is None:
        print("  センサー設定  : 読み出せませんでした")
        return

    motion = " ".join(f"G{gate}={value}" for gate, value in enumerate(params.motion_sensitivity))
    static = " ".join(f"G{gate}={value}" for gate, value in enumerate(params.static_sensitivity))
    print(f"  最大ゲート    : 移動={params.max_moving_gate}  静止={params.max_static_gate}")
    print(f"  無人判定      : {params.no_one_duration_s} 秒")
    print(f"  感度(移動)    : {motion}")
    print(f"  感度(静止)    : {static}")


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
    window: DistanceWindow,
) -> None:
    stop = _install_sigint_handler()
    buffer = b""
    last_frame_at = datetime.now()
    sensor_ok = True
    present = False
    # datetime.min guarantees the first loop iteration fires both immediately, instead of waiting
    # a full interval before the dashboard/Oracle sees anything.
    last_sync_at = datetime.min
    last_status_at = datetime.min
    last_presence_log_at = datetime.min

    with transport:
        _print_sensor_parameters(_read_sensor_parameters(transport))
        print("-" * 60)
        print("  時刻      在席  (0=不在 / 1=在席)   ※Ctrl+C で終了")
        print("-" * 60)

        while not stop.is_set():
            now = datetime.now()

            if shift_end_time is not None and now.time() >= shift_end_time:
                break

            chunk = transport.read(timeout=1.0)
            if chunk:
                buffer += chunk

            buffer, frame_present, got_frame = _drain_frames(
                buffer, state_machine, now, sqlite_conn, verbose, window
            )

            if got_frame:
                present = frame_present
                last_frame_at = now
                if not sensor_ok:
                    print("センサー再接続しました。")
                sensor_ok = True
            elif (now - last_frame_at).total_seconds() >= sensor_timeout_s:
                if sensor_ok:
                    print(f"警告: {sensor_timeout_s}秒間センサーからデータを受信していません。")
                sensor_ok = False
                present = False
                session = state_machine.close(END_REASON_SIGNAL_LOST, now)
                if session is not None:
                    _handle_session(session, sqlite_conn)

            # Plain 0/1 presence line, once per second -- the at-a-glance "is it detecting me?"
            # readout. --verbose adds the raw per-frame detail on top of this.
            if (now - last_presence_log_at).total_seconds() >= _PRESENCE_LOG_INTERVAL_S:
                print(f"  {now:%H:%M:%S}   {int(present)}")
                last_presence_log_at = now

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

    # Optional distance band a target must fall inside to count as present. Both blank = no
    # filtering (original behaviour). See docs/realtime-reader/rules.md for why this exists.
    window = DistanceWindow(
        min_cm=_parse_optional_float(os.environ.get("DETECT_MIN_CM", "")),
        max_cm=_parse_optional_float(os.environ.get("DETECT_MAX_CM", "")),
    )

    mode = "ドライラン（DB書き込みなし）" if args.dry_run else "本番（SQLite + Oracle 書き込み）"
    print("=" * 60)
    print(f"  LD2410C リーダー起動   機器: {machine_id}   モード: {mode}")
    print(f"  ポート: {os.environ.get('COM_PORT', '-')} @ {os.environ.get('BAUD_RATE', '-')} bps")
    print("=" * 60)
    print(f"  在席確定      : {presence_min_duration_s} 秒連続で検知 → セッション開始")
    print(f"  離席確定      : {debounce_s} 秒連続で未検知 → セッション終了")
    print(f"  センサー無応答 : {sensor_timeout_s} 秒で警告")
    if window.is_open:
        print("  検知距離      : 制限なし（全距離を検知）")
    else:
        print(f"  検知距離      : {window.min_cm or 0}〜{window.max_cm or '∞'} cm の範囲のみ検知")

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
        window=window,
    )


if __name__ == "__main__":
    main()
