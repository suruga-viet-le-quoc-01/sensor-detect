from __future__ import annotations

from .frames import AckResult, build_command

# Command words used by this project (see docs/references/ld2410c-protocol.md SS2).
CMD_ENABLE_CONFIG = 0x00FF
CMD_END_CONFIG = 0x00FE
CMD_SET_MAX_GATE = 0x0060
CMD_SET_SENSITIVITY = 0x0064
CMD_SET_RANGE_RESOLUTION = 0x00AA
CMD_RESTART = 0x00A3

# Range resolution selection index (SS6 in configurable-items.md / ld2410c-protocol.md).
_RESOLUTION_INDEX = {0.75: 0x0000, 0.2: 0x0001}

# Parameter words used inside the set-max-gate command value (SS3).
_PARAM_MAX_MOVING_GATE = 0x0000
_PARAM_MAX_STATIC_GATE = 0x0001
_PARAM_NO_ONE_DURATION = 0x0002

# Parameter words used inside the set-sensitivity command value (SS5).
_PARAM_GATE = 0x0000
_PARAM_MOTION_SENSITIVITY = 0x0001
_PARAM_STATIC_SENSITIVITY = 0x0002

# Gate-word sentinel meaning "apply to every distance gate at once" (SS5).
ALL_GATES = 0xFFFF

# Operator-facing hint suggested when the sensor rejects a max-gate command -- the sensor's own
# docs disagree on whether gate=1 is valid (see docs/references/ld2410c-protocol.md SS3).
MAX_GATE_ACK_HINT = "gate の値を 2 以上にして再試行してください。"


# Pack one (parameter word, 4-byte value) pair for a config command's value section.
def _param(word: int, value: int) -> bytes:
    return word.to_bytes(2, "little") + value.to_bytes(4, "little")


# Build the "enable configuration" command -- must be sent before any other config command.
def build_enable_config() -> bytes:
    return build_command(CMD_ENABLE_CONFIG, (1).to_bytes(2, "little"))


# Build the "end configuration" command -- sent after all config commands are done.
def build_end_config() -> bytes:
    return build_command(CMD_END_CONFIG)


# Build the set-max-gate command: max moving/static distance gate + no-one duration (seconds).
# NOTE: the sensor's own docs disagree on the minimum gate value (1 vs 2) -- see
# docs/references/ld2410c-protocol.md SS3. This function does NOT validate the range; send the
# frame and let the sensor's ACK decide (see raise_for_ack + MAX_GATE_ACK_HINT).
def build_set_max_gate(moving_gate: int, static_gate: int, no_one_duration_s: int) -> bytes:
    value = (
        _param(_PARAM_MAX_MOVING_GATE, moving_gate)
        + _param(_PARAM_MAX_STATIC_GATE, static_gate)
        + _param(_PARAM_NO_ONE_DURATION, no_one_duration_s)
    )
    return build_command(CMD_SET_MAX_GATE, value)


# Build the set-sensitivity command for one gate (or ALL_GATES for every gate at once).
def build_set_sensitivity(gate: int, motion: int, static: int) -> bytes:
    value = (
        _param(_PARAM_GATE, gate)
        + _param(_PARAM_MOTION_SENSITIVITY, motion)
        + _param(_PARAM_STATIC_SENSITIVITY, static)
    )
    return build_command(CMD_SET_SENSITIVITY, value)


# Build the set-range-resolution command. `resolution_m` must be 0.75 or 0.2 (meters per gate).
# Takes effect only after a restart (see build_restart) -- caller's responsibility to restart.
def build_set_range_resolution(resolution_m: float) -> bytes:
    if resolution_m not in _RESOLUTION_INDEX:
        raise ValueError(f"resolution_m must be 0.75 or 0.2, got {resolution_m!r}")

    index = _RESOLUTION_INDEX[resolution_m]
    return build_command(CMD_SET_RANGE_RESOLUTION, index.to_bytes(2, "little"))


# Build the restart-module command. The module restarts itself right after sending the ACK.
def build_restart() -> bytes:
    return build_command(CMD_RESTART)


# Raised when the sensor's ACK reports failure for a command we sent.
class AckError(RuntimeError):
    pass


# Raise AckError if `ack` reports failure, including `hint` (an operator-facing suggestion) in
# the message. Does nothing if the ack succeeded -- success never raises or warns.
def raise_for_ack(ack: AckResult, hint: str = "") -> None:
    if ack.ok:
        return

    message = f"センサーがコマンド 0x{ack.command_word:04X} を拒否しました。"
    if hint:
        message += f" {hint}"
    raise AckError(message)
