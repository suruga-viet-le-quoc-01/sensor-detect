import {
  ALL_GATES,
  MAX_GATE_ACK_HINT,
  buildAutoCalibrate,
  buildEnableConfig,
  buildEndConfig,
  buildEngineeringModeOff,
  buildEngineeringModeOn,
  buildFactoryReset,
  buildGetBluetoothAccess,
  buildQueryCalibrateProgress,
  buildQueryRangeResolution,
  buildReadParameters,
  buildRestart,
  buildSetMaxGate,
  buildSetRangeResolution,
  buildSetSensitivity,
  parseCalibrateStatus,
  parseRangeResolutionAck,
  parseReadParametersAck,
  raiseForAck,
} from "./commands.js";
import { CMD_HEADER, DATA_HEADER, parseNextAckFrame, parseNextDataFrame } from "./frames.js";

const ACK_TIMEOUT_MS = 3000;

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

// Retry `fn` a few times with a delay between attempts -- used right after Restart, where the
// module is still rebooting for an unpredictable moment and the first command or two can time
// out even though the sensor is fine a second later.
async function retry(fn, { attempts = 5, delayMs = 1000 } = {}) {
  let lastErr;
  for (let i = 0; i < attempts; i++) {
    try {
      return await fn();
    } catch (err) {
      lastErr = err;
      await sleep(delayMs);
    }
  }
  throw lastErr;
}

function concatBytes(a, b) {
  const result = new Uint8Array(a.length + b.length);
  result.set(a, 0);
  result.set(b, a.length);
  return result;
}

// Hex-dump helper for diagnosing protocol offset bugs against real hardware -- the read-parameters
// ACK layout was never validated against a byte-exact example (the reference PDF only describes it
// in prose), unlike every other command this project has a hex fixture for.
function bytesToHex(bytes) {
  return Array.from(bytes)
    .map((b) => b.toString(16).padStart(2, "0").toUpperCase())
    .join(" ");
}

// Find the first index of `header` inside `buffer`, or -1 if absent.
function findHeaderIndex(buffer, header) {
  outer: for (let i = 0; i <= buffer.length - header.length; i++) {
    for (let j = 0; j < header.length; j++) {
      if (buffer[i + j] !== header[j]) continue outer;
    }
    return i;
  }
  return -1;
}

// High-level LD2410C config flow, transport-agnostic: takes any object shaped like
// SerialTransport/BleTransport (async connect/write/read/disconnect) -- same dependency-inversion
// principle as the Python side's SensorTransport (docs/coding-standards.md), so this class never
// imports pyserial/Web-Serial or bleak/Web-Bluetooth specifics directly. Keeps a background
// read-loop that demuxes the byte stream into ACK frames (resolving whichever command is
// waiting) and data-output frames (forwarded live to the caller's onFrame callback for the
// energy chart). Mirrors the hard-won command ordering already validated on real hardware in
// src/workflows/configure.py (Restart sent BEFORE End config, never after).
export class SensorConfigClient {
  #transport;
  #buffer = new Uint8Array();
  #pendingAck = null;
  #stopReadLoop = false;
  #readLoopPromise = null;
  onFrame = null;
  // Called when the read loop ends on its own (device unplugged / stream closed), NOT via a
  // deliberate disconnect() -- lets the UI leave the "connected" state instead of freezing.
  onClosed = null;

  constructor(transport) {
    this.#transport = transport;
  }

  // Open the transport and start receiving live data. `transportOptions` is passed straight
  // through to the transport's own connect() (e.g. baudRate for SerialTransport,
  // serviceUuid/writeUuid/notifyUuid for BleTransport). `onClosed` fires if the stream drops
  // unexpectedly.
  async connect(onFrame, transportOptions, onClosed) {
    this.onFrame = onFrame;
    this.onClosed = onClosed;
    await this.#transport.connect(transportOptions);
    this.#stopReadLoop = false;
    this.#readLoopPromise = this.#runReadLoop();
    // Best-effort: presence data still works in basic mode even if this fails, so a rejected ACK
    // here shouldn't fail the whole connect -- it only means the Output panel's per-gate energy
    // table stays empty (frames keep arriving as dataType=0x02 instead of 0x01).
    await this.#sendConfigCommand(buildEngineeringModeOn).catch(() => {});
  }

  // BLE-only step: some sensors require 0x00A8 authentication before accepting config commands
  // over Bluetooth (docs/sensor-config/ble-transport.md). No-op-safe to call after connect().
  async authenticateBluetooth(password) {
    const ack = await this.#sendCommand(buildGetBluetoothAccess(password));
    raiseForAck(ack);
  }

  // Stop engineering mode and close the transport.
  async disconnect() {
    await this.#sendConfigCommand(buildEngineeringModeOff).catch(() => {});
    this.#stopReadLoop = true;
    await this.#transport.disconnect();
    if (this.#readLoopPromise) await this.#readLoopPromise.catch(() => {});
  }

  // Read the sensor's current configuration (0x0061) -- used by the "Đọc lại" button and to
  // verify a write.
  async readParameters() {
    const ack = await this.#sendConfigCommand(buildReadParameters);
    const params = { ...parseReadParametersAck(ack), rawExtraHex: bytesToHex(ack.extra) };

    // Resolution isn't part of the read-parameters response (§4) -- query it separately (0x00AB)
    // so the UI reflects the sensor's real resolution. Best-effort: if the sensor doesn't answer
    // as expected, leave resolutionM unset so the caller keeps the current form value.
    try {
      const resolutionM = parseRangeResolutionAck(await this.#sendConfigCommand(buildQueryRangeResolution));
      if (resolutionM !== null) params.resolutionM = resolutionM;
    } catch {
      // ignore -- resolution read-back is optional
    }

    return params;
  }

  // Restart also requires Enable config first, but -- unlike readParameters/factoryReset -- must
  // NOT be followed by End config: the module's own reboot already exits config mode, and
  // sending Restart after an ACK'd End config gets rejected by the sensor (hardware-confirmed,
  // see docs/sensor-config/rules.md).
  async restart() {
    raiseForAck(await this.#sendCommand(buildEnableConfig()));
    const ack = await this.#sendCommand(buildRestart());
    raiseForAck(ack);
  }

  async factoryReset() {
    await this.#sendConfigCommand(buildFactoryReset);
  }

  // Send one command wrapped in the mandatory Enable/End config bracket -- every command other
  // than Enable config itself is rejected by the sensor unless it's sent between Enable (0x00FF)
  // and End (0x00FE), docs/references/ld2410c-protocol.md §2.4 ("Không gửi Enable trước → mọi
  // lệnh khác vô hiệu"). Used by every config command except Restart, which must skip End.
  async #sendConfigCommand(buildFrame, hint) {
    raiseForAck(await this.#sendCommand(buildEnableConfig()));
    const ack = await this.#sendCommand(buildFrame());
    raiseForAck(ack, hint);
    await this.#sendCommand(buildEndConfig()).catch(() => {});
    return ack;
  }

  // Write resolution/gate/sensitivity config to flash, following the exact sequence validated on
  // real hardware: Enable config -> (resolution) -> max gate -> sensitivity -> Restart. No End
  // config is sent -- Restart's own reboot exits config mode, and sending Restart AFTER End
  // config is rejected by the sensor (see docs/sensor-config/rules.md).
  // `sensitivity` is either { motion, static } (applied to ALL_GATES) or an array of
  // { gate, motion, static } for per-gate overrides.
  async writeConfig({ resolutionM, movingGate, staticGate, noOneDurationS, sensitivity }) {
    const log = [];

    const step = async (label, commandPromise, hint) => {
      let ack;
      try {
        ack = await commandPromise;
        raiseForAck(ack, hint);
      } catch (err) {
        log.push({ ok: false, label, detail: err.message });
        throw err;
      }
      log.push({ ok: true, label });
      return ack;
    };

    await step("設定モード開始", this.#sendCommand(buildEnableConfig()));

    if (resolutionM !== undefined) {
      await step(`距離分解能を ${resolutionM}m に設定`, this.#sendCommand(buildSetRangeResolution(resolutionM)));
    }

    await step(
      `検知範囲を設定 (移動gate=${movingGate}, 静止gate=${staticGate}, 無人判定=${noOneDurationS}秒)`,
      this.#sendCommand(buildSetMaxGate(movingGate, staticGate, noOneDurationS)),
      MAX_GATE_ACK_HINT,
    );

    if (sensitivity) {
      const entries = Array.isArray(sensitivity)
        ? sensitivity
        : [{ gate: ALL_GATES, motion: sensitivity.motion, static: sensitivity.static }];

      for (const entry of entries) {
        await step(
          `感度を設定 (gate=${entry.gate === ALL_GATES ? "全て" : entry.gate})`,
          this.#sendCommand(buildSetSensitivity(entry.gate, entry.motion, entry.static)),
        );
      }
    }

    await step("モジュール再起動", this.#sendCommand(buildRestart()));

    // Restart reboots the sensor -- how long that takes varies, so retry instead of a single
    // fixed-delay attempt (a too-short wait here previously left engineering mode off and the
    // Output panel's energy bars stuck until the user manually disconnected/reconnected).
    await sleep(1500);
    const reEnabled = await retry(() => this.#sendConfigCommand(buildEngineeringModeOn))
      .then(() => true)
      .catch(() => false);
    log.push(
      reEnabled
        ? { ok: true, label: "再起動後にエンジニアリングモード再開" }
        : { ok: false, label: "再起動後にエンジニアリングモード再開", detail: "センサーの応答待ちがタイムアウトしました。" },
    );

    let params = null;
    try {
      params = await retry(() => this.readParameters());
      log.push({ ok: true, label: "読み戻し確認", detail: params });
    } catch (err) {
      log.push({ ok: false, label: "読み戻し確認", detail: err.message });
    }

    return { log, params };
  }

  // Optional flow: sensor auto-measures background noise and sets sensitivity itself. Requires
  // an empty room for the entire duration (docs/sensor-config/rules.md).
  async autoCalibrate(durationS, onProgress) {
    await this.#sendCommand(buildEnableConfig()).then((ack) => raiseForAck(ack));
    await this.#sendCommand(buildAutoCalibrate(durationS)).then((ack) => raiseForAck(ack));

    let status = 0;
    while (status !== 2) {
      await sleep(1000);
      const ack = await this.#sendCommand(buildQueryCalibrateProgress());
      raiseForAck(ack);
      status = parseCalibrateStatus(ack);
      onProgress?.(status);
    }

    await this.#sendCommand(buildEndConfig()).catch(() => {});
    return this.readParameters();
  }

  // Send one command frame and wait for its matching ACK (or reject on timeout/transport error).
  // Only one command may be in flight at a time, matching the sensor's half-duplex serial link.
  async #sendCommand(bytes) {
    if (this.#pendingAck) {
      throw new Error("別のコマンドが処理中です。しばらくしてから再試行してください。");
    }

    return new Promise((resolve, reject) => {
      const timer = setTimeout(() => {
        this.#pendingAck = null;
        reject(new Error("センサーからの応答がタイムアウトしました。"));
      }, ACK_TIMEOUT_MS);

      this.#pendingAck = {
        resolve: (ack) => {
          clearTimeout(timer);
          this.#pendingAck = null;
          resolve(ack);
        },
      };

      this.#transport.write(bytes).catch((err) => {
        clearTimeout(timer);
        this.#pendingAck = null;
        reject(err);
      });
    });
  }

  async #runReadLoop() {
    while (!this.#stopReadLoop) {
      let result;
      try {
        result = await this.#transport.read();
      } catch {
        break; // reader was cancelled by disconnect(), or the device dropped
      }

      const { value, done } = result;
      if (done) break;
      if (value && value.length) this.#feed(value);
    }

    // If the loop ended without a deliberate disconnect(), the stream dropped (device unplugged /
    // port closed) -- tell the UI so it can leave the connected state instead of freezing.
    if (!this.#stopReadLoop) this.onClosed?.();
  }

  // Demux the accumulated byte stream: whichever frame type's header appears first in the
  // buffer is parsed next (ACK frames and data-output frames use different headers and can be
  // interleaved on the wire). Stops as soon as neither parser can make progress, leaving the
  // remainder buffered for the next read.
  #feed(chunk) {
    this.#buffer = concatBytes(this.#buffer, chunk);

    while (true) {
      const dataIdx = findHeaderIndex(this.#buffer, DATA_HEADER);
      const ackIdx = findHeaderIndex(this.#buffer, CMD_HEADER);

      if (dataIdx === -1 && ackIdx === -1) {
        const keep = Math.min(this.#buffer.length, 3);
        this.#buffer = this.#buffer.subarray(this.#buffer.length - keep);
        return;
      }

      const preferAck = ackIdx !== -1 && (dataIdx === -1 || ackIdx <= dataIdx);

      if (preferAck) {
        const [ack, rest] = parseNextAckFrame(this.#buffer);
        this.#buffer = rest;
        if (ack === null) return;
        if (this.#pendingAck) this.#pendingAck.resolve(ack);
      } else {
        const [frame, rest] = parseNextDataFrame(this.#buffer);
        this.#buffer = rest;
        if (frame === null) return;
        this.onFrame?.(frame);
      }
    }
  }
}
