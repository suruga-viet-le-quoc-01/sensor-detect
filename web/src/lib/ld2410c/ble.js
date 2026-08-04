// Web Bluetooth transport for the tab Cấu hình. The scan/pick step works with just the device's
// advertised name (no GATT UUID needed), so "Connect" can always find the physical sensor over
// BLE. Actually reading/writing config commands needs the real service + 2 characteristic UUIDs,
// which the protocol PDF never documented (UART-only) -- see docs/sensor-config/ble-transport.md.
// Those must be discovered once per deployment via `python -m src.workflows.ble_discover` and
// entered into the Bluetooth card's UUID fields (ConnectPanel.vue persists them in localStorage,
// the browser equivalent of this project's BLE_SERVICE_UUID/BLE_WRITE_CHAR_UUID/BLE_NOTIFY_CHAR_UUID
// .env vars).
const DEVICE_NAME_PREFIX = "HLK-LD2410";

export class BleTransport {
  #device = null;
  #notifyChar = null;
  #writeChar = null;
  #queue = [];
  #waiter = null;
  #disconnected = false;

  static isSupported() {
    return "bluetooth" in navigator;
  }

  // Scan for and pair with the sensor, then (only if all 3 UUIDs are supplied) open its GATT
  // service and subscribe to notifications. `deviceName` is set as soon as the user picks a
  // device, even if the UUIDs are missing/wrong -- so the caller can report "found X, but..."
  // instead of a bare failure.
  async connect({ serviceUuid, writeUuid, notifyUuid } = {}) {
    if (!BleTransport.isSupported()) {
      throw new Error("このブラウザは Web Bluetooth に対応していません。Android 版 Chrome など対応ブラウザをお使いください。");
    }

    let device;
    try {
      device = await navigator.bluetooth.requestDevice({
        filters: [{ namePrefix: DEVICE_NAME_PREFIX }],
        optionalServices: serviceUuid ? [serviceUuid] : [],
      });
    } catch {
      throw new Error("デバイスが選択されませんでした。センサーの Bluetooth が有効になっているか確認してください（0x00A4）。");
    }

    this.#device = device;
    this.deviceName = device.name || "(名称なし)";

    let server;
    try {
      server = await device.gatt.connect();
    } catch (err) {
      throw new Error(`${this.deviceName} への接続に失敗しました: ${err.message}`);
    }

    if (!serviceUuid || !writeUuid || !notifyUuid) {
      throw new Error(
        `${this.deviceName} が見つかりましたが、Service/Characteristic UUID が未確認のため通信できません。` +
          "python -m src.workflows.ble_discover で調べて入力してください（docs/sensor-config/ble-transport.md 参照）。",
      );
    }

    try {
      const service = await server.getPrimaryService(serviceUuid);
      this.#writeChar = await service.getCharacteristic(writeUuid);
      this.#notifyChar = await service.getCharacteristic(notifyUuid);
      await this.#notifyChar.startNotifications();
      this.#notifyChar.addEventListener("characteristicvaluechanged", this.#onNotify);
    } catch (err) {
      throw new Error(`Service/Characteristic UUID が正しくない可能性があります: ${err.message}`);
    }
  }

  #onNotify = (event) => {
    const value = new Uint8Array(event.target.value.buffer);
    if (this.#waiter) {
      const waiter = this.#waiter;
      this.#waiter = null;
      waiter.resolve({ value, done: false });
    } else {
      this.#queue.push(value);
    }
  };

  async write(bytes) {
    if (!this.#writeChar) throw new Error("Bluetooth 接続が確立していません。");
    await this.#writeChar.writeValue(bytes);
  }

  // Pull-style read() bridging the notify event stream to the same shape SerialTransport's
  // reader.read() returns -- so config.js's read loop works unchanged for either transport.
  async read() {
    if (this.#queue.length > 0) {
      return { value: this.#queue.shift(), done: false };
    }
    if (this.#disconnected) return { value: undefined, done: true };
    return new Promise((resolve) => {
      this.#waiter = { resolve };
    });
  }

  async disconnect() {
    this.#disconnected = true;
    if (this.#waiter) {
      this.#waiter.resolve({ value: undefined, done: true });
      this.#waiter = null;
    }
    if (this.#notifyChar) await this.#notifyChar.stopNotifications().catch(() => {});
    if (this.#device?.gatt?.connected) this.#device.gatt.disconnect();
  }
}
