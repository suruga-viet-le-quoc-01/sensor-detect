from __future__ import annotations

from abc import ABC, abstractmethod


# Physical channel for sending/receiving LD2410C frames — Serial or BLE.
# The byte-level protocol (docs/references/ld2410c-protocol.md) is the same across transports.
class SensorTransport(ABC):
    # Open the channel and get ready to send/receive frames.
    @abstractmethod
    def connect(self) -> None: ...

    # Close the channel and release the port/connection.
    @abstractmethod
    def disconnect(self) -> None: ...

    # Send one complete frame (raw bytes) to the sensor.
    @abstractmethod
    def send(self, frame: bytes) -> None: ...

    # Return bytes received within `timeout` seconds, or None if nothing arrived.
    @abstractmethod
    def read(self, timeout: float) -> bytes | None: ...

    # Enter a `with` block: connect on entry.
    def __enter__(self) -> SensorTransport:
        self.connect()
        return self

    # Exit a `with` block: always disconnect.
    def __exit__(self, *exc_info: object) -> None:
        self.disconnect()
