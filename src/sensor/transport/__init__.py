from __future__ import annotations

import os

from .base import SensorTransport
from .serial_transport import SerialTransport


# Strip a trailing "# comment" from an optional .env value. Some dotenv versions don't strip
# inline comments when the value itself is blank, leaving the literal "# ..." text as the
# value instead of an empty string -- this guards against that regardless of dotenv's behavior.
def _clean_env(value: str) -> str:
    return value.split("#", 1)[0].strip()


# Build the transport selected by the TRANSPORT env var ('serial' or 'ble').
# This is the single place that decides Serial vs BLE; the rest of the code only
# sees the SensorTransport interface (Dependency Inversion).
def create_transport() -> SensorTransport:
    kind = _clean_env(os.environ.get("TRANSPORT", "serial")).lower()
    if kind == "serial":
        return SerialTransport(
            port=os.environ["COM_PORT"],
            baudrate=int(os.environ.get("BAUD_RATE", "256000")),
        )
    if kind == "ble":
        from .ble_transport import BleTransport

        return BleTransport(
            address=_clean_env(os.environ.get("BLE_DEVICE_ADDRESS", "")),
            service_uuid=_clean_env(os.environ.get("BLE_SERVICE_UUID", "")),
            write_char_uuid=_clean_env(os.environ.get("BLE_WRITE_CHAR_UUID", "")),
            notify_char_uuid=_clean_env(os.environ.get("BLE_NOTIFY_CHAR_UUID", "")),
            scan_timeout_s=float(os.environ.get("BLE_SCAN_TIMEOUT_S", "10")),
        )
    raise ValueError(f"TRANSPORT が不正です: {kind!r}（'serial' または 'ble' のみ）")


__all__ = ["SensorTransport", "SerialTransport", "create_transport"]
