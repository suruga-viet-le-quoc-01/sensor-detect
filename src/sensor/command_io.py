from __future__ import annotations

import time

from src.protocol import AckResult, parse_next_ack_frame

from .transport.base import SensorTransport

# Request/response helper for the sensor's command channel, shared by the workflows that send
# config commands (configure.py, and run_reader.py's startup parameter read).


# Read the next ACK within `timeout_s`, accumulating bytes and skipping any interleaved
# data-output frames the sensor may still emit while in config mode.
def read_ack(transport: SensorTransport, timeout_s: float = 3.0) -> AckResult:
    deadline = time.monotonic() + timeout_s
    buffer = b""

    while time.monotonic() < deadline:
        chunk = transport.read(timeout=0.5)
        if chunk:
            buffer += chunk

        ack, buffer = parse_next_ack_frame(buffer)
        if ack is not None:
            return ack

    raise TimeoutError("no ACK received within timeout -- check wiring/baud/COM port")


# Send one command frame and return its ACK. Does NOT check the ACK status -- callers decide
# whether a failure is fatal (see protocol.raise_for_ack) or merely worth skipping.
def send_command(transport: SensorTransport, frame: bytes, timeout_s: float = 3.0) -> AckResult:
    transport.send(frame)
    return read_ack(transport, timeout_s)
