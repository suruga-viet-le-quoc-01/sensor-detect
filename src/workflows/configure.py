from __future__ import annotations

import argparse
import os

from dotenv import load_dotenv

from src.protocol import (
    ALL_GATES,
    MAX_GATE_ACK_HINT,
    build_enable_config,
    build_restart,
    build_set_max_gate,
    build_set_range_resolution,
    build_set_sensitivity,
    raise_for_ack,
)
from src.sensor.command_io import send_command
from src.sensor.transport import SensorTransport, create_transport


# Strip a trailing "# comment" from an optional .env value. Some dotenv versions don't strip
# inline comments when the value itself is blank, leaving the literal "# ..." text as the
# value instead of an empty string -- this guards against that regardless of dotenv's behavior.
def _clean_env(value: str) -> str:
    return value.split("#", 1)[0].strip()


# Send one command frame, wait for its ACK, raise on failure, and print a one-line result.
def _send(transport: SensorTransport, frame: bytes, label: str, hint: str = "") -> None:
    ack = send_command(transport, frame)
    raise_for_ack(ack, hint=hint)
    print(f"OK: {label}")


# Entry point: python -m src.workflows.configure [--port COM3]
# One-time sensor setup: range resolution + max gate + unmanned duration (+ sensitivity if set),
# all read from .env. See docs/sensor-config/rules.md for the full command sequence rationale.
def main() -> None:
    load_dotenv()

    parser = argparse.ArgumentParser(description="Configure the LD2410C sensor once at install time")
    parser.add_argument("--port", help="Override COM_PORT from .env")
    args = parser.parse_args()

    if args.port:
        os.environ["COM_PORT"] = args.port
    os.environ.setdefault("TRANSPORT", "serial")

    resolution = float(os.environ.get("RANGE_RESOLUTION", "0.75"))
    max_moving_gate = int(os.environ["MAX_MOVING_GATE"])
    max_static_gate = int(os.environ["MAX_STATIC_GATE"])
    no_one_duration_s = int(os.environ.get("NO_ONE_DURATION_S", "5"))
    motion_sensitivity = _clean_env(os.environ.get("MOTION_SENSITIVITY", ""))
    static_sensitivity = _clean_env(os.environ.get("STATIC_SENSITIVITY", ""))

    transport = create_transport()

    with transport:
        _send(transport, build_enable_config(), "enable config")

        _send(
            transport,
            build_set_range_resolution(resolution),
            f"set range resolution = {resolution}m",
        )

        _send(
            transport,
            build_set_max_gate(max_moving_gate, max_static_gate, no_one_duration_s),
            f"set max gate = {max_moving_gate}/{max_static_gate}, no-one duration = {no_one_duration_s}s",
            hint=MAX_GATE_ACK_HINT,
        )

        if motion_sensitivity and static_sensitivity:
            _send(
                transport,
                build_set_sensitivity(ALL_GATES, int(motion_sensitivity), int(static_sensitivity)),
                f"set sensitivity (all gates) motion={motion_sensitivity} static={static_sensitivity}",
            )

        # Restart must be sent WHILE STILL in config mode, i.e. BEFORE end config -- confirmed
        # against real hardware: End config makes the radar "resume working mode" (exit config
        # mode), and Restart sent after that gets ACK-rejected as an invalid out-of-config-mode
        # command. The restart itself reboots the module, which already exits config mode on
        # its own -- End config is skipped here since it would be redundant/unsafe after this.
        # Range resolution only takes effect after this restart -- always sent since
        # RANGE_RESOLUTION is a required (non-blank) .env value above.
        _send(transport, build_restart(), "restart module")

    print("Configuration complete. Sensor is restarting.")


if __name__ == "__main__":
    main()
