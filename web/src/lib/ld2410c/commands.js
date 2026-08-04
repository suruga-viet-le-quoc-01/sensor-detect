import { buildCommand } from "./frames.js";

// Command words used by this project (see docs/references/ld2410c-protocol.md §2).
export const CMD_ENABLE_CONFIG = 0x00ff;
export const CMD_END_CONFIG = 0x00fe;
export const CMD_SET_MAX_GATE = 0x0060;
export const CMD_READ_PARAMETERS = 0x0061;
export const CMD_ENGINEERING_MODE_ON = 0x0062;
export const CMD_ENGINEERING_MODE_OFF = 0x0063;
export const CMD_SET_SENSITIVITY = 0x0064;
export const CMD_FACTORY_RESET = 0x00a2;
export const CMD_RESTART = 0x00a3;
export const CMD_SET_RANGE_RESOLUTION = 0x00aa;
export const CMD_QUERY_RANGE_RESOLUTION = 0x00ab;
export const CMD_START_AUTO_CALIBRATE = 0x000b;
export const CMD_QUERY_CALIBRATE_STATUS = 0x001b;
export const CMD_GET_BLUETOOTH_ACCESS = 0x00a8;

// Range resolution selection index (§6 in configurable-items.md / ld2410c-protocol.md).
const RESOLUTION_INDEX = { 0.75: 0x0000, 0.2: 0x0001 };

// Parameter words used inside the set-max-gate command value (§3).
const PARAM_MAX_MOVING_GATE = 0x0000;
const PARAM_MAX_STATIC_GATE = 0x0001;
const PARAM_NO_ONE_DURATION = 0x0002;

// Parameter words used inside the set-sensitivity command value (§5).
const PARAM_GATE = 0x0000;
const PARAM_MOTION_SENSITIVITY = 0x0001;
const PARAM_STATIC_SENSITIVITY = 0x0002;

// Gate-word sentinel meaning "apply to every distance gate at once" (§5).
export const ALL_GATES = 0xffff;

// Operator-facing hint suggested when the sensor rejects a max-gate command -- the sensor's own
// docs disagree on whether gate=1 is valid (see docs/references/ld2410c-protocol.md §3).
export const MAX_GATE_ACK_HINT = "gate の値を 2 以上にして再試行してください。";

// Pack one (parameter word, 4-byte value) pair for a config command's value section.
function param(word, value) {
  return Uint8Array.of(word & 0xff, (word >> 8) & 0xff, value & 0xff, (value >> 8) & 0xff, (value >> 16) & 0xff, (value >> 24) & 0xff);
}

function concat(...parts) {
  const total = parts.reduce((sum, part) => sum + part.length, 0);
  const result = new Uint8Array(total);
  let offset = 0;
  for (const part of parts) {
    result.set(part, offset);
    offset += part.length;
  }
  return result;
}

// Build the "enable configuration" command -- must be sent before any other config command.
export function buildEnableConfig() {
  return buildCommand(CMD_ENABLE_CONFIG, Uint8Array.of(0x01, 0x00));
}

// Build the "end configuration" command -- sent after all config commands are done.
export function buildEndConfig() {
  return buildCommand(CMD_END_CONFIG);
}

// Build the set-max-gate command: max moving/static distance gate + no-one duration (seconds).
// NOTE: the sensor's own docs disagree on the minimum gate value (1 vs 2) -- see
// docs/references/ld2410c-protocol.md §3. This function does NOT validate the range; send the
// frame and let the sensor's ACK decide (see raiseForAck + MAX_GATE_ACK_HINT).
export function buildSetMaxGate(movingGate, staticGate, noOneDurationS) {
  const value = concat(
    param(PARAM_MAX_MOVING_GATE, movingGate),
    param(PARAM_MAX_STATIC_GATE, staticGate),
    param(PARAM_NO_ONE_DURATION, noOneDurationS),
  );
  return buildCommand(CMD_SET_MAX_GATE, value);
}

// Build the set-sensitivity command for one gate (or ALL_GATES for every gate at once).
export function buildSetSensitivity(gate, motion, staticSensitivity) {
  const value = concat(
    param(PARAM_GATE, gate),
    param(PARAM_MOTION_SENSITIVITY, motion),
    param(PARAM_STATIC_SENSITIVITY, staticSensitivity),
  );
  return buildCommand(CMD_SET_SENSITIVITY, value);
}

// Build the set-range-resolution command. `resolutionM` must be 0.75 or 0.2 (meters per gate).
// Takes effect only after a restart -- caller's responsibility to restart (see buildRestart).
export function buildSetRangeResolution(resolutionM) {
  const index = RESOLUTION_INDEX[resolutionM];
  if (index === undefined) {
    throw new RangeError(`resolutionM は 0.75 か 0.2 を指定してください（渡された値: ${resolutionM}）`);
  }

  return buildCommand(CMD_SET_RANGE_RESOLUTION, Uint8Array.of(index & 0xff, (index >> 8) & 0xff));
}

// Build the query-range-resolution command (0x00AB), so read-back can reflect the sensor's actual
// resolution on the UI (the read-parameters response §4 does NOT include resolution).
export function buildQueryRangeResolution() {
  return buildCommand(CMD_QUERY_RANGE_RESOLUTION);
}

// Decode the query-range-resolution ACK into meters-per-gate. The response byte layout isn't
// documented, so this mirrors the SET command's index (0x0000=0.75m, 0x0001=0.2m) read from the
// first 2 extra bytes, and returns null for anything unexpected so the caller can leave the UI
// unchanged rather than guess wrong.
export function parseRangeResolutionAck(ack) {
  const index = (ack.extra?.[0] ?? 0xff) | ((ack.extra?.[1] ?? 0xff) << 8);
  if (index === 0x0000) return 0.75;
  if (index === 0x0001) return 0.2;
  return null;
}

// Build the restart-module command. The module restarts itself right after sending the ACK.
export function buildRestart() {
  return buildCommand(CMD_RESTART);
}

// Build the read-parameters command -- current sensor config, for the "Đọc lại" (read back) flow.
export function buildReadParameters() {
  return buildCommand(CMD_READ_PARAMETERS);
}

// Decode a successful read-parameters ACK's `extra` payload (docs/references §4):
// 0xAA head + max gate N (1B) + max moving gate (1B) + max static gate (1B)
// + motion sensitivity gate 0..8 (9B) + static sensitivity gate 0..8 (9B) + no-one duration (2B).
export function parseReadParametersAck(ack) {
  const extra = ack.extra;
  const maxGate = extra[1];
  const maxMovingGate = extra[2];
  const maxStaticGate = extra[3];
  const motionSensitivity = Array.from(extra.subarray(4, 13));
  const staticSensitivity = Array.from(extra.subarray(13, 22));
  const noOneDurationS = extra[22] | (extra[23] << 8);

  return { maxGate, maxMovingGate, maxStaticGate, motionSensitivity, staticSensitivity, noOneDurationS };
}

// Build the enable/disable engineering-mode commands (volatile -- lost on power-off). Engineering
// mode adds per-gate energy to the data-output stream (§8.3), needed for the live tune chart.
export function buildEngineeringModeOn() {
  return buildCommand(CMD_ENGINEERING_MODE_ON);
}

export function buildEngineeringModeOff() {
  return buildCommand(CMD_ENGINEERING_MODE_OFF);
}

// Build the background-noise auto-calibration command (optional flow -- requires an empty room
// for the full duration). `durationS` is a 2-byte value per docs/references §2.
export function buildAutoCalibrate(durationS) {
  return buildCommand(CMD_START_AUTO_CALIBRATE, Uint8Array.of(durationS & 0xff, (durationS >> 8) & 0xff));
}

// Build the query-calibration-progress command. The ACK's first extra byte is the status
// (0=not started, 1=running, 2=done) per docs/references §2.
export function buildQueryCalibrateProgress() {
  return buildCommand(CMD_QUERY_CALIBRATE_STATUS);
}

export function parseCalibrateStatus(ack) {
  return ack.extra[0];
}

// Build the factory-reset command. Takes effect after a restart.
export function buildFactoryReset() {
  return buildCommand(CMD_FACTORY_RESET);
}

// Build the BLE authentication command (0x00A8, §2) -- 6-byte password, default "HiLink". Its ACK
// only ever comes back over the BLE channel (never serial), per the reference doc.
export function buildGetBluetoothAccess(password) {
  const bytes = new TextEncoder().encode(password);
  if (bytes.length !== 6) {
    throw new RangeError(`BLE パスワードは6バイトである必要があります（渡された値: ${password}）`);
  }

  return buildCommand(CMD_GET_BLUETOOTH_ACCESS, bytes);
}

// Raised when the sensor's ACK reports failure for a command we sent.
export class AckError extends Error {}

// Raise AckError if `ack` reports failure, including `hint` (an operator-facing suggestion) in
// the message. Does nothing if the ack succeeded -- success never raises or warns.
export function raiseForAck(ack, hint = "") {
  if (ack.ok) return;

  let message = `センサーがコマンド 0x${ack.commandWord.toString(16).toUpperCase().padStart(4, "0")} を拒否しました。`;
  if (hint) message += ` ${hint}`;
  throw new AckError(message);
}
