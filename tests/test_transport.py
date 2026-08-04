import pytest

from src.sensor.transport import SerialTransport, create_transport
from src.sensor.transport.ble_transport import BleConfigError


def test_create_transport_serial(monkeypatch):
    monkeypatch.setenv("TRANSPORT", "serial")
    monkeypatch.setenv("COM_PORT", "COM3")
    transport = create_transport()
    assert isinstance(transport, SerialTransport)


def test_create_transport_ble_missing_uuid_raises(monkeypatch):
    monkeypatch.setenv("TRANSPORT", "ble")
    monkeypatch.setenv("BLE_DEVICE_ADDRESS", "AA:BB:CC:DD:EE:FF")
    monkeypatch.delenv("BLE_SERVICE_UUID", raising=False)
    monkeypatch.delenv("BLE_WRITE_CHAR_UUID", raising=False)
    monkeypatch.delenv("BLE_NOTIFY_CHAR_UUID", raising=False)
    with pytest.raises(BleConfigError):
        create_transport()


def test_create_transport_ble_placeholder_uuid_raises(monkeypatch):
    monkeypatch.setenv("TRANSPORT", "ble")
    monkeypatch.setenv("BLE_DEVICE_ADDRESS", "AA:BB:CC:DD:EE:FF")
    placeholder = "00000000-0000-0000-0000-000000000000"
    monkeypatch.setenv("BLE_SERVICE_UUID", placeholder)
    monkeypatch.setenv("BLE_WRITE_CHAR_UUID", placeholder)
    monkeypatch.setenv("BLE_NOTIFY_CHAR_UUID", placeholder)
    with pytest.raises(BleConfigError):
        create_transport()


def test_create_transport_invalid_kind(monkeypatch):
    monkeypatch.setenv("TRANSPORT", "carrier-pigeon")
    with pytest.raises(ValueError):
        create_transport()


def test_create_transport_ble_blank_value_with_trailing_comment_raises(monkeypatch):
    # Regression: some dotenv versions don't strip a trailing "# comment" when the value is
    # blank, leaving the literal comment text as the value instead of "". Must still be
    # treated as unset (BleConfigError), not accepted as a real UUID.
    monkeypatch.setenv("TRANSPORT", "ble")
    monkeypatch.setenv("BLE_DEVICE_ADDRESS", "AA:BB:CC:DD:EE:FF")
    monkeypatch.setenv("BLE_SERVICE_UUID", "  # TODO: CHƯA XÁC NHẬN — xem docs/sensor-config/ble-transport.md")
    monkeypatch.setenv("BLE_WRITE_CHAR_UUID", "  # TODO: CHƯA XÁC NHẬN")
    monkeypatch.setenv("BLE_NOTIFY_CHAR_UUID", "  # TODO: CHƯA XÁC NHẬN")
    with pytest.raises(BleConfigError):
        create_transport()
