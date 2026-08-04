from __future__ import annotations

import serial

from .base import SensorTransport


# Send/receive LD2410C frames over a COM port (pyserial).
class SerialTransport(SensorTransport):
    # Store the COM port and baud rate; the port is opened later in connect().
    def __init__(self, port: str, baudrate: int = 256000) -> None:
        self._port = port
        self._baudrate = baudrate
        self._conn: serial.Serial | None = None

    # Open the serial port.
    def connect(self) -> None:
        self._conn = serial.Serial(self._port, self._baudrate, timeout=1)

    # Close the serial port if open (safe to call twice).
    def disconnect(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    # Write one frame to the port.
    def send(self, frame: bytes) -> None:
        if self._conn is None:
            raise RuntimeError("SerialTransport.connect() must be called first")

        self._conn.write(frame)

    # Return bytes received within `timeout`s, or None if nothing arrived.
    def read(self, timeout: float) -> bytes | None:
        if self._conn is None:
            raise RuntimeError("SerialTransport.connect() must be called first")

        # Read at least 1 byte (blocks up to timeout), then drain the rest already buffered.
        self._conn.timeout = timeout
        data = self._conn.read(max(self._conn.in_waiting, 1))
        return data or None
