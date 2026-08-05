// Frame markers for the command/ACK channel (host <-> radar configuration).
export const CMD_HEADER = Uint8Array.of(0xfd, 0xfc, 0xfb, 0xfa);
export const CMD_FOOTER = Uint8Array.of(0x04, 0x03, 0x02, 0x01);

// Frame markers for the auto-emitted sensor data-output stream (never overlaps CMD_HEADER/FOOTER).
export const DATA_HEADER = Uint8Array.of(0xf4, 0xf3, 0xf2, 0xf1);
export const DATA_FOOTER = Uint8Array.of(0xf8, 0xf7, 0xf6, 0xf5);

// Bit OR'd into a command word to form its ACK word (send 0x0060 -> ACK word 0x0160).
const ACK_BIT = 0x0100;

// Sanity caps on declared payload length -- a "header" with a wildly larger declared length is
// corrupt, not something worth waiting for (real ACKs/data frames are at most a few dozen bytes).
const MAX_ACK_PAYLOAD_LEN = 64;
const MAX_DATA_PAYLOAD_LEN = 64;

// In-payload tail marker that must sit right before the data-output frame footer (protocol doc §8.5).
const TAIL_MARKER = Uint8Array.of(0x55, 0x00);

// target_state values that mean "a person is present" (Table 14).
const PRESENT_STATES = new Set([0x01, 0x02, 0x03]);

// Minimum target-data size: target_state(1) + moving dist(2) + moving energy(1)
// + static dist(2) + static energy(1) + detection dist(2).
const BASIC_TARGET_DATA_LEN = 9;

// Raised when a command/ACK or data-output frame doesn't match the expected
// header/footer/length/ACK-bit shape.
export class MalformedFrameError extends Error {}

// Concatenate any number of byte arrays into one new Uint8Array.
function concatBytes(...parts) {
  const total = parts.reduce((sum, part) => sum + part.length, 0);
  const result = new Uint8Array(total);
  let offset = 0;
  for (const part of parts) {
    result.set(part, offset);
    offset += part.length;
  }
  return result;
}

// Encode a number as 2 little-endian bytes.
function u16le(value) {
  return Uint8Array.of(value & 0xff, (value >> 8) & 0xff);
}

// Read 2 little-endian bytes starting at `offset` as an unsigned integer.
function readU16LE(bytes, offset) {
  return bytes[offset] | (bytes[offset + 1] << 8);
}

function bytesEqual(a, b) {
  if (a.length !== b.length) return false;

  for (let i = 0; i < a.length; i++) {
    if (a[i] !== b[i]) return false;
  }

  return true;
}

function startsWith(buffer, prefix) {
  return buffer.length >= prefix.length && bytesEqual(buffer.subarray(0, prefix.length), prefix);
}

function endsWith(buffer, suffix) {
  return buffer.length >= suffix.length && bytesEqual(buffer.subarray(buffer.length - suffix.length), suffix);
}

// Find the first index of `pattern` inside `buffer`, or -1 if absent (like Python's bytes.find).
function indexOfSequence(buffer, pattern) {
  outer: for (let i = 0; i <= buffer.length - pattern.length; i++) {
    for (let j = 0; j < pattern.length; j++) {
      if (buffer[i + j] !== pattern[j]) continue outer;
    }
    return i;
  }
  return -1;
}

// Build one command frame: header + length + command word + value + footer.
export function buildCommand(word, value = new Uint8Array()) {
  const body = concatBytes(u16le(word), value);
  return concatBytes(CMD_HEADER, u16le(body.length), body, CMD_FOOTER);
}

// Parse one complete ACK frame (already extracted from the byte stream) into
// {commandWord, ok, extra}. `commandWord` has the ACK bit (0x0100) stripped, so callers can
// compare directly against a plain command word (e.g. CMD_SET_MAX_GATE).
// Never throws on a failure *status* (0=success, nonzero=fail) -- only on structural corruption.
export function parseAck(frame) {
  if (!startsWith(frame, CMD_HEADER) || !endsWith(frame, CMD_FOOTER)) {
    throw new MalformedFrameError("ACK frame is missing the FD FC FB FA header or 04 03 02 01 footer");
  }

  const length = readU16LE(frame, 4);
  const body = frame.subarray(6, 6 + length);
  if (body.length !== length || frame.length !== 6 + length + CMD_FOOTER.length) {
    throw new MalformedFrameError("ACK frame length field doesn't match the actual payload size");
  }

  const ackWord = readU16LE(body, 0);
  if ((ackWord & ACK_BIT) === 0) {
    throw new MalformedFrameError(`0x${ackWord.toString(16)} is not an ACK word (bit 0x0100 not set)`);
  }

  const commandWord = ackWord & ~ACK_BIT & 0xffff;
  const status = readU16LE(body, 2);
  return { commandWord, ok: status === 0, extra: body.subarray(4) };
}

// Scan `buffer` for the next valid ACK frame, skipping any interleaved data-output frames or
// garbage. Returns [ackOrNull, remaining] -- mirrors parseNextDataFrame's resync strategy.
export function parseNextAckFrame(buffer) {
  while (true) {
    const start = indexOfSequence(buffer, CMD_HEADER);
    if (start === -1) {
      const keep = Math.min(buffer.length, CMD_HEADER.length - 1);
      return [null, buffer.subarray(buffer.length - keep)];
    }

    buffer = buffer.subarray(start); // drop any garbage (or data-output frames) before the header

    if (buffer.length < 6) return [null, buffer]; // need more bytes for the length field

    const length = readU16LE(buffer, 4);
    if (length > MAX_ACK_PAYLOAD_LEN) {
      buffer = buffer.subarray(1);
      continue;
    }

    const frameEnd = 6 + length + CMD_FOOTER.length;
    if (buffer.length < frameEnd) return [null, buffer]; // need more bytes for the full frame

    let ack;
    try {
      ack = parseAck(buffer.subarray(0, frameEnd));
    } catch (err) {
      if (!(err instanceof MalformedFrameError)) throw err;
      // False start (bad footer / bad ACK bit): drop just this header byte and keep scanning.
      buffer = buffer.subarray(1);
      continue;
    }

    return [ack, buffer.subarray(frameEnd)];
  }
}

// True when `state` means a person is present (moving, stationary, or both).
export function presence(state) {
  return PRESENT_STATES.has(state);
}

// Bit flags inside target_state: bit0 = a moving target is present, bit1 = a stationary one is.
// ONLY valid for the present states {1,2,3} -- 0x04-0x06 are noise-calibration states whose bits
// happen to overlap these flags (0x05 sets bit0, 0x06 sets bit1) and must never be read this way.
const MOVING_BIT = 0x01;
const STATIC_BIT = 0x02;

// A bound counts as "set" only when it's a real finite number -- an empty input box yields "" and
// must be treated as no bound at all.
function hasBound(value) {
  return typeof value === "number" && Number.isFinite(value);
}

function inWindow(distanceCm, minCm, maxCm) {
  if (hasBound(minCm) && distanceCm < minCm) return false;
  if (hasBound(maxCm) && distanceCm > maxCm) return false;
  return true;
}

// True when `frame` reports a person whose distance falls inside [minCm, maxCm]. Either bound may
// be left unset (open-ended); both unset means no distance filtering, i.e. plain presence().
// Mirrors presence_in_range() in src/protocol/data_frame.py -- keep the two in sync.
//
// WHY: presence() alone accepts a target at ANY distance the sensor still reports, and per-gate
// sensitivity zoning cannot isolate a distance band (a person's body reflects energy into
// neighbouring gates, so muting one gate doesn't stop that same person being picked up by the
// next). The per-target distance the sensor reports IS specific, so filtering on it is what
// actually restricts detection to one band.
export function presenceInRange(frame, minCm, maxCm) {
  if (!frame || frame.present !== true) return false;

  if (!hasBound(minCm) && !hasBound(maxCm)) return true;

  const movingInRange =
    (frame.targetState & MOVING_BIT) !== 0 && inWindow(frame.movingDistanceCm, minCm, maxCm);
  const staticInRange =
    (frame.targetState & STATIC_BIT) !== 0 && inWindow(frame.staticDistanceCm, minCm, maxCm);
  return movingInRange || staticInRange;
}

// Decode the target-data portion of a data-output payload into a plain frame object. Basic
// fields are always present; engineering-mode fields (§8.3) are added only when dataType===1 and
// the payload actually carries them -- gate count is read from the frame itself, not hardcoded.
function decodeTargetData(dataType, targetData) {
  if (targetData.length < BASIC_TARGET_DATA_LEN) {
    throw new MalformedFrameError("data-output target data is shorter than the minimum 9 bytes");
  }

  const targetState = targetData[0];
  const frame = {
    dataType,
    targetState,
    movingDistanceCm: readU16LE(targetData, 1),
    movingEnergy: targetData[3],
    staticDistanceCm: readU16LE(targetData, 4),
    staticEnergy: targetData[6],
    detectionDistanceCm: readU16LE(targetData, 7),
    present: presence(targetState),
  };

  if (dataType === 0x01 && targetData.length > BASIC_TARGET_DATA_LEN) {
    let offset = BASIC_TARGET_DATA_LEN;
    const maxMovingGate = targetData[offset++];
    const maxStaticGate = targetData[offset++];
    const movingGateEnergies = Array.from(targetData.subarray(offset, offset + maxMovingGate + 1));
    offset += maxMovingGate + 1;
    const staticGateEnergies = Array.from(targetData.subarray(offset, offset + maxStaticGate + 1));
    offset += maxStaticGate + 1;

    frame.maxMovingGate = maxMovingGate;
    frame.maxStaticGate = maxStaticGate;
    frame.movingGateEnergies = movingGateEnergies;
    frame.staticGateEnergies = staticGateEnergies;
    frame.photosensitive = targetData[offset++];
    frame.outPinStatus = targetData[offset++];
  }

  return frame;
}

// Scan `buffer` for the next valid data-output frame, skipping any garbage bytes and any frame
// whose footer or in-payload tail marker doesn't check out. Returns [frameOrNull, remaining] --
// `remaining` is what the caller should keep buffering on the next read.
export function parseNextDataFrame(buffer) {
  while (true) {
    const start = indexOfSequence(buffer, DATA_HEADER);
    if (start === -1) {
      const keep = Math.min(buffer.length, DATA_HEADER.length - 1);
      return [null, buffer.subarray(buffer.length - keep)];
    }

    buffer = buffer.subarray(start); // drop any garbage before the header

    if (buffer.length < 6) return [null, buffer]; // need more bytes for the length field

    const length = readU16LE(buffer, 4);
    if (length > MAX_DATA_PAYLOAD_LEN) {
      // A real-looking header with an implausible length is corrupt -- drop this false start.
      buffer = buffer.subarray(1);
      continue;
    }

    const frameEnd = 6 + length + DATA_FOOTER.length;
    if (buffer.length < frameEnd) return [null, buffer]; // need more bytes for the full frame

    const payload = buffer.subarray(6, 6 + length);
    const footer = buffer.subarray(6 + length, frameEnd);

    if (bytesEqual(footer, DATA_FOOTER) && bytesEqual(payload.subarray(-2), TAIL_MARKER)) {
      const frame = decodeTargetData(payload[0], payload.subarray(2, -2));
      return [frame, buffer.subarray(frameEnd)];
    }

    // False start (bad footer or bad in-payload tail marker): drop just this header byte and
    // keep scanning -- a real frame may start right after it.
    buffer = buffer.subarray(1);
  }
}
