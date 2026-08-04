from __future__ import annotations

import asyncio
import queue
import threading

from .base import SensorTransport

# UUID NOT YET CONFIRMED — the protocol PDF only documents UART, not the BLE GATT
# profile. Must be discovered via `python -m src.workflows.ble_discover` first
# (see docs/sensor-config/ble-transport.md), then filled into .env.
_PLACEHOLDER_UUID = "00000000-0000-0000-0000-000000000000"


# Raised when a BLE UUID/address is still missing or a placeholder — see docs/sensor-config/ble-transport.md.
class BleConfigError(RuntimeError):
    pass


# Send/receive LD2410C frames over BLE (bleak). SCAFFOLD — see docs/sensor-config/ble-transport.md.
class BleTransport(SensorTransport):
    # Store BLE address + GATT UUIDs; fail fast if any is still a placeholder.
    # Raising here surfaces a missing/placeholder UUID immediately with a setup hint,
    # instead of a confusing timeout later during connect().
    def __init__(
        self,
        address: str,
        service_uuid: str,
        write_char_uuid: str,
        notify_char_uuid: str,
        scan_timeout_s: float = 10.0,
    ) -> None:
        for name, value in (
            ("BLE_DEVICE_ADDRESS", address),
            ("BLE_SERVICE_UUID", service_uuid),
            ("BLE_WRITE_CHAR_UUID", write_char_uuid),
            ("BLE_NOTIFY_CHAR_UUID", notify_char_uuid),
        ):
            if not value or value == _PLACEHOLDER_UUID:
                raise BleConfigError(
                    f"{name} が未確認です。`python -m src.workflows.ble_discover` で調べて "
                    f".env に設定してください — docs/sensor-config/ble-transport.md 参照。"
                )

        self._address = address
        self._service_uuid = service_uuid
        self._write_char_uuid = write_char_uuid
        self._notify_char_uuid = notify_char_uuid
        self._scan_timeout_s = scan_timeout_s
        self._rx_queue: queue.Queue[bytes] = queue.Queue()
        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread: threading.Thread | None = None
        self._client = None

    # Connect over BLE and subscribe to notifications.
    # bleak is async, so we run its event loop on a background thread and bridge calls with
    # run_coroutine_threadsafe — keeping this transport's API synchronous like SerialTransport.
    def connect(self) -> None:
        import bleak

        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(target=self._loop.run_forever, daemon=True)
        self._thread.start()

        # Open the client and start notifications (runs on the background loop).
        async def _connect() -> bleak.BleakClient:
            client = bleak.BleakClient(self._address, timeout=self._scan_timeout_s)
            await client.connect()
            await client.start_notify(self._notify_char_uuid, self._on_notify)
            return client

        self._client = asyncio.run_coroutine_threadsafe(_connect(), self._loop).result(
            self._scan_timeout_s
        )

    # Push each incoming notification payload onto the receive queue.
    def _on_notify(self, _sender: object, data: bytearray) -> None:
        self._rx_queue.put(bytes(data))

    # Disconnect the client and stop the background event loop/thread.
    def disconnect(self) -> None:
        if self._client is not None and self._loop is not None:
            asyncio.run_coroutine_threadsafe(self._client.disconnect(), self._loop).result()
        if self._loop is not None:
            self._loop.call_soon_threadsafe(self._loop.stop)
        if self._thread is not None:
            self._thread.join(timeout=2)
        self._client = None

    # Write one frame to the write characteristic.
    def send(self, frame: bytes) -> None:
        if self._client is None or self._loop is None:
            raise RuntimeError("BleTransport.connect() must be called first")

        asyncio.run_coroutine_threadsafe(
            self._client.write_gatt_char(self._write_char_uuid, frame), self._loop
        ).result()

    # Return the next notification payload within `timeout`s, or None if none arrived.
    def read(self, timeout: float) -> bytes | None:
        try:
            return self._rx_queue.get(timeout=timeout)
        except queue.Empty:
            return None
