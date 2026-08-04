// LD2410C's wiring default is 256000 baud (see docs/setup-and-run.md), but the sensor's own
// 0x00A1 command can change it -- so the baud rate is a caller-supplied choice, not hardcoded.
export const DEFAULT_BAUD_RATE = 256000;

// Every baud rate the sensor accepts for 0x00A1 (docs/references/ld2410c-protocol.md §6), for the
// connect-screen dropdown -- in case a technician previously changed it away from the default.
export const SUPPORTED_BAUD_RATES = [9600, 19200, 38400, 57600, 115200, 230400, 256000, 460800];

// Web Serial transport for the tab Cấu hình. Talks directly to the sensor's COM port from the
// browser -- no backend involved (docs/web-dashboard/rules.md "Tab Cấu hình").
export class SerialTransport {
  #port = null;
  #reader = null;
  #writer = null;

  static isSupported() {
    return "serial" in navigator;
  }

  // Ask the user to pick a COM port and open it. Throws a Japanese, operator-facing error when
  // the browser doesn't support Web Serial, no port was picked, or the port is already held by
  // another process (e.g. run_reader.py) -- per docs/web-dashboard/rules.md's documented edge case.
  async connect({ baudRate = DEFAULT_BAUD_RATE } = {}) {
    if (!SerialTransport.isSupported()) {
      throw new Error("このブラウザは Web Serial に対応していません。Chrome または Edge をお使いください。");
    }

    let port;
    try {
      port = await navigator.serial.requestPort();
    } catch {
      throw new Error("COM ポートが選択されませんでした。");
    }

    try {
      await port.open({ baudRate });
    } catch {
      throw new Error(
        "COM ポートを開けませんでした。run_reader.py が起動中の場合は停止してから再試行してください。",
      );
    }

    this.#port = port;
    this.#writer = port.writable.getWriter();
    this.#reader = port.readable.getReader();
  }

  // Send one complete frame (already built by frames.js/commands.js).
  async write(bytes) {
    if (!this.#writer) throw new Error("シリアルポートが接続されていません。");
    await this.#writer.write(bytes);
  }

  // Read the next available chunk. Returns { value: Uint8Array|undefined, done: boolean } --
  // `done` is true once the port has been closed out from under the reader.
  async read() {
    if (!this.#reader) throw new Error("シリアルポートが接続されていません。");
    return this.#reader.read();
  }

  // Release the reader/writer locks and close the port. Safe to call even if connect() never
  // fully succeeded.
  async disconnect() {
    if (this.#reader) {
      await this.#reader.cancel().catch(() => {});
      this.#reader.releaseLock();
      this.#reader = null;
    }

    if (this.#writer) {
      this.#writer.releaseLock();
      this.#writer = null;
    }

    if (this.#port) {
      await this.#port.close().catch(() => {});
      this.#port = null;
    }
  }
}
