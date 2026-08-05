import { describe, expect, it } from "vitest";

import { DATA_HEADER, parseNextDataFrame, presence, presenceInRange } from "../src/lib/ld2410c/frames.js";
import { hexToBytes } from "./helpers.js";

// Same basic-mode fixture as tests/test_frame_parser.py (Python side), byte-exact from
// docs/references/ld2410c-protocol.md §8.4.
const VALID_BASIC_FRAME = hexToBytes(
  "F4 F3 F2 F1 0D 00 02 AA 02 51 00 00 00 00 3B 00 00 55 00 F8 F7 F6 F5",
);

// Engineering-mode fixture (§8.4's own worked example, `23 00` = 35 bytes, elides the middle
// gate-energy bytes with "..." in the doc) reconstructed byte-exact: maxMovingGate/maxStaticGate
// = 8 (9 gates each) is derivable from the declared length (35 = 4 fixed header/tail bytes +
// 9 basic target-data bytes + 2 gate-count bytes + 2*(N+1) energy bytes => N=8), and the
// elided energy values are filled with distinct numbers so the decode can be asserted precisely.
const VALID_ENGINEERING_FRAME = hexToBytes(
  "F4 F3 F2 F1 23 00 01 AA 03 1E 00 3C 00 00 39 00 00 08 08 " +
    "32 2D 28 23 1E 19 14 0F 0A " + // moving gate 0..8 energies: 50 45 40 35 30 25 20 15 10
    "30 2C 27 22 1D 18 13 0E 09 " + // static gate 0..8 energies: 48 44 39 34 29 24 19 14 9
    "60 01 55 00 F8 F7 F6 F5",
);

describe("parseNextDataFrame - basic mode", () => {
  it("decodes a stationary-present frame", () => {
    const [frame, remaining] = parseNextDataFrame(VALID_BASIC_FRAME);
    expect(frame.dataType).toBe(0x02);
    expect(frame.targetState).toBe(2);
    expect(frame.movingDistanceCm).toBe(81);
    expect(frame.movingEnergy).toBe(0);
    expect(frame.staticDistanceCm).toBe(0);
    expect(frame.staticEnergy).toBe(0x3b);
    expect(frame.detectionDistanceCm).toBe(0);
    expect(frame.present).toBe(true);
    expect(remaining).toHaveLength(0);
  });

  it("reports not-present for target_state 0", () => {
    const bytes = Uint8Array.from(VALID_BASIC_FRAME);
    bytes[8] = 0x00; // target_state byte (after F4F3F2F1 len data_type AA)

    const [frame] = parseNextDataFrame(bytes);
    expect(frame.targetState).toBe(0);
    expect(frame.present).toBe(false);
  });

  it("reports present for target_state 3 (moving + stationary)", () => {
    const bytes = Uint8Array.from(VALID_BASIC_FRAME);
    bytes[8] = 0x03;

    const [frame] = parseNextDataFrame(bytes);
    expect(frame.targetState).toBe(3);
    expect(frame.present).toBe(true);
  });

  it("skips garbage bytes before the header", () => {
    const buffer = new Uint8Array([0xaa, 0xbb, ...VALID_BASIC_FRAME]);
    const [frame, remaining] = parseNextDataFrame(buffer);

    expect(frame.targetState).toBe(2);
    expect(frame.movingDistanceCm).toBe(81);
    expect(remaining).toHaveLength(0);
  });

  it("rejects a frame with a corrupted in-payload tail marker", () => {
    const bytes = Uint8Array.from(VALID_BASIC_FRAME);
    bytes[17] = 0x56; // corrupt the 55 -> 56 in-payload tail marker

    const [frame, remaining] = parseNextDataFrame(bytes);
    expect(frame).toBeNull();
    expect(remaining.length).toBeLessThanOrEqual(DATA_HEADER.length - 1);
  });

  it("waits for more bytes on an incomplete frame", () => {
    const partial = VALID_BASIC_FRAME.subarray(0, 10);
    const [frame, remaining] = parseNextDataFrame(partial);

    expect(frame).toBeNull();
    expect(remaining).toEqual(partial);
  });

  it("trims the buffer when no header is present at all", () => {
    const noise = new Uint8Array(200).fill(0).map((_, i) => (i % 2 === 0 ? 0xaa : 0xbb));
    const [frame, remaining] = parseNextDataFrame(noise);

    expect(frame).toBeNull();
    expect(remaining.length).toBeLessThanOrEqual(DATA_HEADER.length - 1);
  });

  it("treats an oversized declared length as corrupt instead of stalling", () => {
    const buffer = new Uint8Array([...hexToBytes("F4 F3 F2 F1 FF FF"), ...new Uint8Array(10)]);
    const [frame, remaining] = parseNextDataFrame(buffer);

    expect(frame).toBeNull();
    expect(remaining.length).toBeLessThanOrEqual(DATA_HEADER.length - 1);
  });
});

describe("parseNextDataFrame - engineering mode", () => {
  it("decodes per-gate energies, photosensitive and OUT pin using the frame's own gate count", () => {
    const [frame, remaining] = parseNextDataFrame(VALID_ENGINEERING_FRAME);

    expect(frame.dataType).toBe(0x01);
    expect(frame.targetState).toBe(3);
    expect(frame.movingDistanceCm).toBe(30);
    expect(frame.movingEnergy).toBe(60);
    expect(frame.staticDistanceCm).toBe(0);
    expect(frame.staticEnergy).toBe(57);
    expect(frame.present).toBe(true);

    expect(frame.maxMovingGate).toBe(8);
    expect(frame.maxStaticGate).toBe(8);
    expect(frame.movingGateEnergies).toEqual([50, 45, 40, 35, 30, 25, 20, 15, 10]);
    expect(frame.staticGateEnergies).toEqual([48, 44, 39, 34, 29, 24, 19, 14, 9]);
    expect(frame.photosensitive).toBe(0x60);
    expect(frame.outPinStatus).toBe(1);
    expect(remaining).toHaveLength(0);
  });
});

describe("presence", () => {
  it("matches the documented state matrix", () => {
    expect(presence(0)).toBe(false);
    expect(presence(1)).toBe(true);
    expect(presence(2)).toBe(true);
    expect(presence(3)).toBe(true);
    expect(presence(4)).toBe(false);
    expect(presence(5)).toBe(false);
    expect(presence(6)).toBe(false);
  });
});

describe("presenceInRange", () => {
  const frame = (targetState, movingDistanceCm, staticDistanceCm) => ({
    targetState,
    movingDistanceCm,
    staticDistanceCm,
    present: [1, 2, 3].includes(targetState),
  });

  it("matches plain presence when no bound is set", () => {
    expect(presenceInRange(frame(1, 500, 0), "", "")).toBe(true);
    expect(presenceInRange(frame(0, 500, 0), "", "")).toBe(false);
  });

  it("accepts a moving target inside the window and rejects one outside", () => {
    expect(presenceInRange(frame(1, 112, 0), 100, 130)).toBe(true);
    expect(presenceInRange(frame(1, 185, 0), 100, 130)).toBe(false);
    expect(presenceInRange(frame(1, 40, 0), 100, 130)).toBe(false);
  });

  it("accepts a stationary target inside the window", () => {
    expect(presenceInRange(frame(2, 0, 120), 100, 130)).toBe(true);
    expect(presenceInRange(frame(2, 0, 300), 100, 130)).toBe(false);
  });

  it("needs only one channel inside the window when both report a target", () => {
    expect(presenceInRange(frame(3, 110, 400), 100, 130)).toBe(true);
    expect(presenceInRange(frame(3, 400, 125), 100, 130)).toBe(true);
    expect(presenceInRange(frame(3, 400, 400), 100, 130)).toBe(false);
  });

  it("supports open-ended bounds", () => {
    expect(presenceInRange(frame(1, 300, 0), 100, "")).toBe(true);
    expect(presenceInRange(frame(1, 50, 0), 100, "")).toBe(false);
    expect(presenceInRange(frame(1, 50, 0), "", 100)).toBe(true);
  });

  // Regression: 0x05/0x06 are noise-calibration states whose bits overlap the moving/static flags.
  it("never treats noise-calibration states as a target", () => {
    for (const state of [4, 5, 6]) {
      expect(presenceInRange(frame(state, 110, 110), 100, 130)).toBe(false);
      expect(presenceInRange(frame(state, 110, 110), "", "")).toBe(false);
    }
  });
});
