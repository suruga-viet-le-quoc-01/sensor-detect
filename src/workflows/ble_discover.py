from __future__ import annotations

import argparse
import asyncio

from bleak import BleakClient, BleakScanner

# Enable configuration frame (0x00FF), used to verify the UUIDs — see docs/references/ld2410c-protocol.md §2.2.1
_ENABLE_CONFIG_FRAME = bytes.fromhex("FDFCFBFA0400FF00010004030201")
_ENABLE_CONFIG_ACK_PREFIX = bytes.fromhex("FDFCFBFA0800FF0100")


# Scan for nearby BLE devices and print each address + advertised name.
async def _scan(timeout: float) -> None:
    devices = await BleakScanner.discover(timeout=timeout)
    if not devices:
        print("BLEデバイスが見つかりません。センサーのBluetooth（0x00A4）が有効か確認してください。")
        return

    for device in devices:
        print(f"{device.address}  {device.name or '(名称なし)'}")


# Connect to one device, list its GATT services/characteristics, and — when both verify
# UUIDs are given — send Enable config and check the ACK to confirm the UUIDs.
async def _inspect(address: str, timeout: float, write_uuid: str | None, notify_uuid: str | None) -> None:
    async with BleakClient(address, timeout=timeout) as client:
        print(f"接続しました: {address}\n")
        for service in client.services:
            print(f"Service {service.uuid}")
            for char in service.characteristics:
                props = ",".join(char.properties)
                print(f"  Characteristic {char.uuid}  [{props}]")

        if not write_uuid or not notify_uuid:
            return

        # Collect notification payloads while we send one Enable config and wait for the ACK.
        print("\n--- 検証: Enable config を送信し、notify で ACK を待機 ---")
        received: list[bytes] = []

        def _on_notify(_sender: object, data: bytearray) -> None:
            received.append(bytes(data))

        await client.start_notify(notify_uuid, _on_notify)
        await client.write_gatt_char(write_uuid, _ENABLE_CONFIG_FRAME)
        await asyncio.sleep(2.0)
        await client.stop_notify(notify_uuid)

        if not received:
            print("notify から応答がありません — UUID が違うか、先に 0x00A8 認証が必要な可能性があります。")
            return

        # Compare each received frame against the expected Enable-config ACK prefix.
        for frame in received:
            hex_str = frame.hex(" ").upper()
            matched = frame.startswith(_ENABLE_CONFIG_ACK_PREFIX)
            verdict = "期待どおりの ACK と一致 — UUID とBLE経由プロトコルの前提は正しい" if matched else "期待した ACK と不一致"
            print(f"受信: {hex_str}\n=> {verdict}")


# Parse CLI args: with --address, inspect that device; otherwise scan for devices.
def main() -> None:
    parser = argparse.ArgumentParser(
        description="LD2410C センサーの BLE デバイス + GATT service/characteristic を探索 "
        "（docs/sensor-config/ble-transport.md 参照）"
    )
    parser.add_argument("--address", help="デバイスの MAC/アドレス。省略時は周辺デバイスのスキャンのみ実行。")
    parser.add_argument("--timeout", type=float, default=10.0)
    parser.add_argument("--verify-write-uuid", dest="write_uuid", help="Enable config 送信を試す characteristic UUID")
    parser.add_argument("--verify-notify-uuid", dest="notify_uuid", help="ACK 受信を試す characteristic UUID")
    args = parser.parse_args()

    if args.address:
        asyncio.run(_inspect(args.address, args.timeout, args.write_uuid, args.notify_uuid))
    else:
        asyncio.run(_scan(args.timeout))


if __name__ == "__main__":
    main()
