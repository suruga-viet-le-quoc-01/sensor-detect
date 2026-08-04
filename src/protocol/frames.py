from __future__ import annotations

from dataclasses import dataclass

# Frame markers for the command/ACK channel (host <-> radar configuration).
CMD_HEADER = bytes.fromhex("FDFCFBFA")
CMD_FOOTER = bytes.fromhex("04030201")

# Bit OR'd into a command word to form its ACK word (send 0x0060 -> ACK word 0x0160).
_ACK_BIT = 0x0100

# Sanity cap on a declared ACK payload length -- real ACKs are at most a few dozen bytes
# (the largest documented one, read-parameters, is 28). A "header" with a wildly larger
# declared length is corrupt, not something worth waiting for.
_MAX_ACK_PAYLOAD_LEN = 64


# Raised when a command/ACK frame doesn't match the expected header/footer/length/ACK-bit shape.
class MalformedFrameError(ValueError):
    pass


# Build one command frame: header + length + command word + value + footer.
def build_command(word: int, value: bytes = b"") -> bytes:
    body = word.to_bytes(2, "little") + value
    return CMD_HEADER + len(body).to_bytes(2, "little") + body + CMD_FOOTER


# Parsed result of one ACK frame: which command it answers, whether it succeeded, and any extra
# payload beyond the 2-byte status (e.g. protocol version + buffer size for enable-config).
@dataclass(frozen=True, slots=True)
class AckResult:
    command_word: int
    ok: bool
    extra: bytes


# Parse one complete ACK frame (already extracted from the byte stream) into an AckResult.
# Never raises on a failure *status* (0=success, nonzero=fail) -- only on structural corruption.
# Escalating a failure status into an exception is a separate, deliberate step (see
# commands.raise_for_ack) so this decode step stays pure and always succeeds on well-formed input.
def parse_ack(frame: bytes) -> AckResult:
    if not frame.startswith(CMD_HEADER) or not frame.endswith(CMD_FOOTER):
        raise MalformedFrameError("ACK frame is missing the FD FC FB FA header or 04 03 02 01 footer")

    length = int.from_bytes(frame[4:6], "little")
    body = frame[6 : 6 + length]
    if len(body) != length or len(frame) != 6 + length + len(CMD_FOOTER):
        raise MalformedFrameError("ACK frame length field doesn't match the actual payload size")

    ack_word = int.from_bytes(body[0:2], "little")
    if not ack_word & _ACK_BIT:
        raise MalformedFrameError(f"0x{ack_word:04X} is not an ACK word (bit 0x0100 not set)")

    command_word = ack_word & ~_ACK_BIT
    status = int.from_bytes(body[2:4], "little")
    return AckResult(command_word=command_word, ok=status == 0, extra=body[4:])


# Scan `buffer` for the next valid ACK frame, skipping any interleaved data-output frames
# (header F4 F3 F2 F1, never matches CMD_HEADER) or garbage. Mirrors
# data_frame.parse_next_data_frame's resync strategy: drop 1 byte and keep scanning past any
# false start (bad structure) instead of stalling or crashing. Returns (ack_or_None, remaining).
def parse_next_ack_frame(buffer: bytes) -> tuple[AckResult | None, bytes]:
    while True:
        start = buffer.find(CMD_HEADER)
        if start == -1:
            keep = min(len(buffer), len(CMD_HEADER) - 1)
            return None, buffer[len(buffer) - keep :]

        buffer = buffer[start:]  # drop any garbage (or data-output frames) before the header

        if len(buffer) < 6:
            return None, buffer  # need more bytes for the length field

        length = int.from_bytes(buffer[4:6], "little")
        if length > _MAX_ACK_PAYLOAD_LEN:
            buffer = buffer[1:]
            continue

        frame_end = 6 + length + len(CMD_FOOTER)
        if len(buffer) < frame_end:
            return None, buffer  # need more bytes for the full frame

        try:
            ack = parse_ack(buffer[:frame_end])
        except MalformedFrameError:
            # False start (bad footer / bad ACK bit): drop just this header byte and keep
            # scanning -- a real ACK frame may start right after it.
            buffer = buffer[1:]
            continue

        return ack, buffer[frame_end:]
