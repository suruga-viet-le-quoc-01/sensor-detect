from __future__ import annotations

from dataclasses import dataclass

from .frames import MalformedFrameError

# Frame markers for the auto-emitted sensor data-output stream (distinct from the command/ACK
# channel -- these headers/footers never overlap with CMD_HEADER/CMD_FOOTER in frames.py).
DATA_HEADER = bytes.fromhex("F4F3F2F1")
DATA_FOOTER = bytes.fromhex("F8F7F6F5")

# In-payload tail marker that must sit right before the frame footer (protocol doc SS8.5).
_TAIL_MARKER = bytes.fromhex("5500")

# target_state values that mean "a person is present" (Table 14).
_PRESENT_STATES = (0x01, 0x02, 0x03)

# Sanity cap on the declared payload length: real frames are at most 35 bytes (engineering
# mode with 8 gates). Anything far beyond that with a real-looking header is corrupt, not a
# frame we should wait forever for.
_MAX_PAYLOAD_LEN = 64

# Minimum target-data size: target_state(1) + moving dist(2) + moving energy(1)
# + static dist(2) + static energy(1) + detection dist(2).
_BASIC_TARGET_DATA_LEN = 9


# True when `state` means a person is present (moving, stationary, or both).
def presence(state: int) -> bool:
    return state in _PRESENT_STATES


# One decoded data-output frame's basic target info (engineering-mode per-gate energy fields
# are deferred until the 0x0062/0x0063 engineering-mode commands are implemented).
@dataclass(frozen=True, slots=True)
class DataFrame:
    data_type: int
    target_state: int
    moving_distance_cm: int
    moving_energy: int
    static_distance_cm: int
    static_energy: int
    detection_distance_cm: int

    # True when this frame's target_state means a person is present.
    @property
    def present(self) -> bool:
        return presence(self.target_state)


# Decode the target-data portion of a data-output payload into a DataFrame.
def _decode_target_data(data_type: int, target_data: bytes) -> DataFrame:
    if len(target_data) < _BASIC_TARGET_DATA_LEN:
        raise MalformedFrameError("data-output target data is shorter than the minimum 9 bytes")

    return DataFrame(
        data_type=data_type,
        target_state=target_data[0],
        moving_distance_cm=int.from_bytes(target_data[1:3], "little"),
        moving_energy=target_data[3],
        static_distance_cm=int.from_bytes(target_data[4:6], "little"),
        static_energy=target_data[6],
        detection_distance_cm=int.from_bytes(target_data[7:9], "little"),
    )


# Scan `buffer` for the next valid data-output frame, skipping any garbage bytes and any frame
# whose footer or in-payload tail marker doesn't check out. Returns (frame_or_None, remaining) --
# `remaining` is what the caller should keep buffering on the next read.
def parse_next_data_frame(buffer: bytes) -> tuple[DataFrame | None, bytes]:
    while True:
        start = buffer.find(DATA_HEADER)
        if start == -1:
            # No header anywhere: keep only a short tail in case it holds a split header,
            # so a stream of pure noise doesn't grow this buffer forever.
            keep = min(len(buffer), len(DATA_HEADER) - 1)
            return None, buffer[len(buffer) - keep :]

        buffer = buffer[start:]  # drop any garbage before the header

        if len(buffer) < 6:
            return None, buffer  # need more bytes for the length field

        length = int.from_bytes(buffer[4:6], "little")
        if length > _MAX_PAYLOAD_LEN:
            # A real-looking header with an implausible length is corrupt, not a frame we
            # should stall waiting for -- drop this false start and keep scanning.
            buffer = buffer[1:]
            continue

        frame_end = 6 + length + len(DATA_FOOTER)
        if len(buffer) < frame_end:
            return None, buffer  # need more bytes for the full frame

        payload = buffer[6 : 6 + length]
        footer = buffer[6 + length : frame_end]

        if footer == DATA_FOOTER and payload[-2:] == _TAIL_MARKER:
            frame = _decode_target_data(payload[0], payload[2:-2])
            return frame, buffer[frame_end:]

        # False start (bad footer or bad in-payload tail marker): drop just this header byte
        # and keep scanning -- a real frame may start right after it.
        buffer = buffer[1:]
