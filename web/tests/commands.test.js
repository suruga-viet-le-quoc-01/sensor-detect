import { describe, expect, it } from "vitest";

import {
  ALL_GATES,
  CMD_ENABLE_CONFIG,
  CMD_SET_MAX_GATE,
  MAX_GATE_ACK_HINT,
  AckError,
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
} from "../src/lib/ld2410c/commands.js";
import { MalformedFrameError, buildCommand, parseAck, parseNextAckFrame } from "../src/lib/ld2410c/frames.js";
import { hexToBytes } from "./helpers.js";

describe("frames.js generic envelope", () => {
  it("builds a command with the default empty value", () => {
    expect(buildCommand(0x1234)).toEqual(hexToBytes("FD FC FB FA 02 00 34 12 04 03 02 01"));
  });

  it("builds a command with a value", () => {
    expect(buildCommand(0x1234, hexToBytes("AA BB"))).toEqual(
      hexToBytes("FD FC FB FA 04 00 34 12 AA BB 04 03 02 01"),
    );
  });

  it("reads a clean ACK frame via parseNextAckFrame", () => {
    const buffer = hexToBytes("FD FC FB FA 04 00 60 01 00 00 04 03 02 01");
    const [ack, remaining] = parseNextAckFrame(buffer);
    expect(ack).toEqual({ commandWord: CMD_SET_MAX_GATE, ok: true, extra: new Uint8Array() });
    expect(remaining).toHaveLength(0);
  });

  it("skips an interleaved data-output frame while scanning for an ACK", () => {
    const dataFrame = hexToBytes("F4 F3 F2 F1 0D 00 02 AA 02 51 00 00 00 00 3B 00 00 55 00 F8 F7 F6 F5");
    const ackFrame = hexToBytes("FD FC FB FA 04 00 60 01 00 00 04 03 02 01");
    const [ack, remaining] = parseNextAckFrame(new Uint8Array([...dataFrame, ...ackFrame]));

    expect(ack).not.toBeNull();
    expect(ack.commandWord).toBe(CMD_SET_MAX_GATE);
    expect(remaining).toHaveLength(0);
  });

  it("waits for more bytes when an ACK frame is incomplete", () => {
    const partial = hexToBytes("FD FC FB FA 04 00 60 01");
    const [ack, remaining] = parseNextAckFrame(partial);
    expect(ack).toBeNull();
    expect(remaining).toEqual(partial);
  });

  it("trims the buffer when no ACK header is present at all", () => {
    const noise = new Uint8Array(100).fill(0).map((_, i) => (i % 2 === 0 ? 0xaa : 0xbb));
    const [ack, remaining] = parseNextAckFrame(noise);
    expect(ack).toBeNull();
    expect(remaining.length).toBeLessThanOrEqual(3);
  });

  it("parses a successful ACK", () => {
    const ack = parseAck(hexToBytes("FD FC FB FA 04 00 60 01 00 00 04 03 02 01"));
    expect(ack).toEqual({ commandWord: CMD_SET_MAX_GATE, ok: true, extra: new Uint8Array() });
  });

  it("parses a failure-status ACK", () => {
    const ack = parseAck(hexToBytes("FD FC FB FA 04 00 60 01 01 00 04 03 02 01"));
    expect(ack.commandWord).toBe(CMD_SET_MAX_GATE);
    expect(ack.ok).toBe(false);
  });

  it("parses the enable-config ACK's extra payload", () => {
    const ack = parseAck(hexToBytes("FD FC FB FA 08 00 FF 01 00 00 01 00 40 00 04 03 02 01"));
    expect(ack.commandWord).toBe(CMD_ENABLE_CONFIG);
    expect(ack.ok).toBe(true);
    expect(ack.extra).toEqual(hexToBytes("01 00 40 00"));
  });

  it.each([
    ["bad header", "00 FC FB FA 04 00 60 01 00 00 04 03 02 01"],
    ["bad footer", "FD FC FB FA 04 00 60 01 00 00 04 03 02 00"],
    ["length mismatch", "FD FC FB FA 06 00 60 01 00 00 04 03 02 01"],
    ["ACK bit not set", "FD FC FB FA 04 00 60 00 00 00 04 03 02 01"],
  ])("rejects a malformed ACK frame (%s)", (_label, hex) => {
    expect(() => parseAck(hexToBytes(hex))).toThrow(MalformedFrameError);
  });
});

describe("commands.js domain builders", () => {
  it("builds enable-config matching the reference bytes", () => {
    expect(buildEnableConfig()).toEqual(hexToBytes("FD FC FB FA 04 00 FF 00 01 00 04 03 02 01"));
  });

  it("builds end-config matching the reference bytes", () => {
    expect(buildEndConfig()).toEqual(hexToBytes("FD FC FB FA 02 00 FE 00 04 03 02 01"));
  });

  it("builds set-range-resolution for 0.2m matching the reference bytes", () => {
    expect(buildSetRangeResolution(0.2)).toEqual(hexToBytes("FD FC FB FA 04 00 AA 00 01 00 04 03 02 01"));
  });

  it("builds set-range-resolution for 0.75m matching the reference bytes", () => {
    expect(buildSetRangeResolution(0.75)).toEqual(hexToBytes("FD FC FB FA 04 00 AA 00 00 00 04 03 02 01"));
  });

  it("rejects an invalid range resolution", () => {
    expect(() => buildSetRangeResolution(0.5)).toThrow(RangeError);
  });

  it("builds restart matching the reference bytes", () => {
    expect(buildRestart()).toEqual(hexToBytes("FD FC FB FA 02 00 A3 00 04 03 02 01"));
  });

  it("builds set-max-gate matching the spec example", () => {
    const frame = buildSetMaxGate(8, 8, 5);
    expect(frame).toEqual(
      hexToBytes("FD FC FB FA 14 00 60 00 00 00 08 00 00 00 01 00 08 00 00 00 02 00 05 00 00 00 04 03 02 01"),
    );
  });

  it("builds set-max-gate for gate=1 without validating (sensor's own ACK decides)", () => {
    const frame = buildSetMaxGate(1, 1, 5);
    expect(frame.subarray(0, 4)).toEqual(hexToBytes("FD FC FB FA"));
  });

  it("builds set-sensitivity for a single gate matching the spec example", () => {
    const frame = buildSetSensitivity(3, 40, 40);
    expect(frame).toEqual(
      hexToBytes("FD FC FB FA 14 00 64 00 00 00 03 00 00 00 01 00 28 00 00 00 02 00 28 00 00 00 04 03 02 01"),
    );
  });

  it("builds set-sensitivity for all gates matching the spec example", () => {
    const frame = buildSetSensitivity(ALL_GATES, 40, 40);
    expect(frame).toEqual(
      hexToBytes("FD FC FB FA 14 00 64 00 00 00 FF FF 00 00 01 00 28 00 00 00 02 00 28 00 00 00 04 03 02 01"),
    );
  });

  it("composes independent zoning frames (baseline=100, gate3/4=20)", () => {
    const baseline = buildSetSensitivity(ALL_GATES, 100, 100);
    const gate3 = buildSetSensitivity(3, 20, 20);
    const gate4 = buildSetSensitivity(4, 20, 20);

    expect(baseline.subarray(0, 12)).toEqual(hexToBytes("FD FC FB FA 14 00 64 00 00 00 FF FF"));
    expect(gate3.subarray(0, 12)).toEqual(hexToBytes("FD FC FB FA 14 00 64 00 00 00 03 00"));
    expect(gate4.subarray(0, 12)).toEqual(hexToBytes("FD FC FB FA 14 00 64 00 00 00 04 00"));
  });

  it("builds read-parameters and decodes its ACK payload", () => {
    expect(buildReadParameters()).toEqual(hexToBytes("FD FC FB FA 02 00 61 00 04 03 02 01"));

    // status(2B, already stripped into ack.ok) + AA + maxGate + maxMovingGate + maxStaticGate
    // + 9B motion sensitivity + 9B static sensitivity + noOneDuration(2B) = 24 extra bytes (§4).
    const extra = hexToBytes(
      "AA 08 08 08 32 28 1E 14 0F 0F 0F 0F 0F 32 28 28 1E 14 14 14 14 14 05 00",
    );
    const ack = { commandWord: 0x0061, ok: true, extra };
    const parsed = parseReadParametersAck(ack);

    expect(parsed.maxGate).toBe(8);
    expect(parsed.maxMovingGate).toBe(8);
    expect(parsed.maxStaticGate).toBe(8);
    expect(parsed.motionSensitivity).toEqual([50, 40, 30, 20, 15, 15, 15, 15, 15]);
    expect(parsed.staticSensitivity).toEqual([50, 40, 40, 30, 20, 20, 20, 20, 20]);
    expect(parsed.noOneDurationS).toBe(5);
  });

  it("builds engineering-mode on/off", () => {
    expect(buildEngineeringModeOn()).toEqual(hexToBytes("FD FC FB FA 02 00 62 00 04 03 02 01"));
    expect(buildEngineeringModeOff()).toEqual(hexToBytes("FD FC FB FA 02 00 63 00 04 03 02 01"));
  });

  it("builds auto-calibrate + query-progress and decodes progress status", () => {
    expect(buildAutoCalibrate(10)).toEqual(hexToBytes("FD FC FB FA 04 00 0B 00 0A 00 04 03 02 01"));
    expect(buildQueryCalibrateProgress()).toEqual(hexToBytes("FD FC FB FA 02 00 1B 00 04 03 02 01"));

    expect(parseCalibrateStatus({ commandWord: 0x001b, ok: true, extra: Uint8Array.of(2) })).toBe(2);
  });

  it("builds factory-reset", () => {
    expect(buildFactoryReset()).toEqual(hexToBytes("FD FC FB FA 02 00 A2 00 04 03 02 01"));
  });

  it("builds query-range-resolution", () => {
    expect(buildQueryRangeResolution()).toEqual(hexToBytes("FD FC FB FA 02 00 AB 00 04 03 02 01"));
  });

  it("decodes query-range-resolution ACK to meters-per-gate", () => {
    expect(parseRangeResolutionAck({ extra: Uint8Array.of(0x00, 0x00) })).toBe(0.75);
    expect(parseRangeResolutionAck({ extra: Uint8Array.of(0x01, 0x00) })).toBe(0.2);
    expect(parseRangeResolutionAck({ extra: Uint8Array.of(0x09, 0x00) })).toBeNull();
    expect(parseRangeResolutionAck({ extra: new Uint8Array() })).toBeNull();
  });

  it("builds the BLE-auth command with the default HiLink password", () => {
    expect(buildGetBluetoothAccess("HiLink")).toEqual(
      hexToBytes("FD FC FB FA 08 00 A8 00 48 69 4C 69 6E 6B 04 03 02 01"),
    );
  });

  it("rejects a BLE password that isn't exactly 6 bytes", () => {
    expect(() => buildGetBluetoothAccess("short")).toThrow(RangeError);
  });
});

describe("raiseForAck", () => {
  it("does nothing on success even with a hint", () => {
    const ack = { commandWord: CMD_SET_MAX_GATE, ok: true, extra: new Uint8Array() };
    expect(() => raiseForAck(ack, MAX_GATE_ACK_HINT)).not.toThrow();
  });

  it("raises with the hint text on failure", () => {
    const ack = { commandWord: CMD_SET_MAX_GATE, ok: false, extra: new Uint8Array() };
    expect(() => raiseForAck(ack, MAX_GATE_ACK_HINT)).toThrow(AckError);
    try {
      raiseForAck(ack, MAX_GATE_ACK_HINT);
    } catch (err) {
      expect(err.message).toContain(MAX_GATE_ACK_HINT);
    }
  });

  it("raises without a hint", () => {
    const ack = { commandWord: CMD_SET_MAX_GATE, ok: false, extra: new Uint8Array() };
    expect(() => raiseForAck(ack)).toThrow(AckError);
  });

  it("raises with a hint when a real parsed failure ACK is escalated", () => {
    const ack = parseAck(hexToBytes("FD FC FB FA 04 00 60 01 01 00 04 03 02 01"));
    expect(() => raiseForAck(ack, MAX_GATE_ACK_HINT)).toThrow(AckError);
  });

  it("does not raise when a real parsed success ACK is escalated", () => {
    const ack = parseAck(hexToBytes("FD FC FB FA 04 00 60 01 00 00 04 03 02 01"));
    expect(() => raiseForAck(ack, MAX_GATE_ACK_HINT)).not.toThrow();
  });
});
