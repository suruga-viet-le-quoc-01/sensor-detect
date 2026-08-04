import pytest

from src.protocol.commands import (
    ALL_GATES,
    CMD_ENABLE_CONFIG,
    CMD_SET_MAX_GATE,
    MAX_GATE_ACK_HINT,
    AckError,
    build_enable_config,
    build_end_config,
    build_restart,
    build_set_max_gate,
    build_set_range_resolution,
    build_set_sensitivity,
    raise_for_ack,
)
from src.protocol.frames import (
    AckResult,
    MalformedFrameError,
    build_command,
    parse_ack,
    parse_next_ack_frame,
)


def test_build_command_default_empty_value():
    frame = build_command(0x1234)
    assert frame == bytes.fromhex("FD FC FB FA 02 00 34 12 04 03 02 01")


def test_build_command_with_value():
    frame = build_command(0x1234, bytes.fromhex("AA BB"))
    assert frame == bytes.fromhex("FD FC FB FA 04 00 34 12 AA BB 04 03 02 01")


def test_build_enable_config_matches_reference_bytes():
    assert build_enable_config() == bytes.fromhex("FD FC FB FA 04 00 FF 00 01 00 04 03 02 01")


def test_build_end_config_matches_reference_bytes():
    assert build_end_config() == bytes.fromhex("FD FC FB FA 02 00 FE 00 04 03 02 01")


def test_build_set_range_resolution_020m_matches_reference_bytes():
    frame = build_set_range_resolution(0.2)
    assert frame == bytes.fromhex("FD FC FB FA 04 00 AA 00 01 00 04 03 02 01")


def test_build_set_range_resolution_075m_matches_reference_bytes():
    frame = build_set_range_resolution(0.75)
    assert frame == bytes.fromhex("FD FC FB FA 04 00 AA 00 00 00 04 03 02 01")


def test_build_set_range_resolution_rejects_invalid_value():
    with pytest.raises(ValueError):
        build_set_range_resolution(0.5)


def test_build_restart_matches_reference_bytes():
    assert build_restart() == bytes.fromhex("FD FC FB FA 02 00 A3 00 04 03 02 01")


def test_parse_next_ack_frame_reads_clean_ack():
    buffer = bytes.fromhex("FD FC FB FA 04 00 60 01 00 00 04 03 02 01")
    ack, remaining = parse_next_ack_frame(buffer)
    assert ack == AckResult(command_word=CMD_SET_MAX_GATE, ok=True, extra=b"")
    assert remaining == b""


def test_parse_next_ack_frame_skips_interleaved_data_output_frame():
    data_frame = bytes.fromhex(
        "F4 F3 F2 F1 0D 00 02 AA 02 51 00 00 00 00 3B 00 00 55 00 F8 F7 F6 F5"
    )
    ack_frame = bytes.fromhex("FD FC FB FA 04 00 60 01 00 00 04 03 02 01")
    ack, remaining = parse_next_ack_frame(data_frame + ack_frame)
    assert ack is not None
    assert ack.command_word == CMD_SET_MAX_GATE
    assert remaining == b""


def test_parse_next_ack_frame_waits_for_more_bytes_when_incomplete():
    partial = bytes.fromhex("FD FC FB FA 04 00 60 01")
    ack, remaining = parse_next_ack_frame(partial)
    assert ack is None
    assert remaining == partial


def test_parse_next_ack_frame_no_header_trims_buffer():
    noise = bytes([0xAA, 0xBB]) * 50
    ack, remaining = parse_next_ack_frame(noise)
    assert ack is None
    assert len(remaining) <= 3


def test_build_set_max_gate_matches_spec_example():
    frame = build_set_max_gate(moving_gate=8, static_gate=8, no_one_duration_s=5)
    expected = bytes.fromhex(
        "FD FC FB FA 14 00 60 00 00 00 08 00 00 00 01 00 08 00 00 00 02 00 05 00 00 00 04 03 02 01"
    )
    assert frame == expected


def test_build_set_max_gate_1_does_not_raise():
    frame = build_set_max_gate(moving_gate=1, static_gate=1, no_one_duration_s=5)
    assert frame.startswith(bytes.fromhex("FD FC FB FA"))


def test_build_set_sensitivity_single_gate_matches_spec_example():
    frame = build_set_sensitivity(gate=3, motion=40, static=40)
    expected = bytes.fromhex(
        "FD FC FB FA 14 00 64 00 00 00 03 00 00 00 01 00 28 00 00 00 02 00 28 00 00 00 04 03 02 01"
    )
    assert frame == expected


def test_build_set_sensitivity_all_gates_matches_spec_example():
    frame = build_set_sensitivity(gate=ALL_GATES, motion=40, static=40)
    expected = bytes.fromhex(
        "FD FC FB FA 14 00 64 00 00 00 FF FF 00 00 01 00 28 00 00 00 02 00 28 00 00 00 04 03 02 01"
    )
    assert frame == expected


def test_build_set_sensitivity_zoning_composition():
    baseline = build_set_sensitivity(gate=ALL_GATES, motion=100, static=100)
    gate3 = build_set_sensitivity(gate=3, motion=20, static=20)
    gate4 = build_set_sensitivity(gate=4, motion=20, static=20)

    assert baseline.startswith(bytes.fromhex("FD FC FB FA 14 00 64 00 00 00 FF FF"))
    assert gate3.startswith(bytes.fromhex("FD FC FB FA 14 00 64 00 00 00 03 00"))
    assert gate4.startswith(bytes.fromhex("FD FC FB FA 14 00 64 00 00 00 04 00"))


def test_parse_ack_success():
    ack = parse_ack(bytes.fromhex("FD FC FB FA 04 00 60 01 00 00 04 03 02 01"))
    assert ack == AckResult(command_word=CMD_SET_MAX_GATE, ok=True, extra=b"")


def test_parse_ack_failure_status():
    ack = parse_ack(bytes.fromhex("FD FC FB FA 04 00 60 01 01 00 04 03 02 01"))
    assert ack.command_word == CMD_SET_MAX_GATE
    assert ack.ok is False


def test_parse_ack_enable_config_extra_payload():
    ack = parse_ack(bytes.fromhex("FD FC FB FA 08 00 FF 01 00 00 01 00 40 00 04 03 02 01"))
    assert ack.command_word == CMD_ENABLE_CONFIG
    assert ack.ok is True
    assert ack.extra == bytes.fromhex("01 00 40 00")


def test_parse_ack_bad_header_raises():
    with pytest.raises(MalformedFrameError):
        parse_ack(bytes.fromhex("00 FC FB FA 04 00 60 01 00 00 04 03 02 01"))


def test_parse_ack_bad_footer_raises():
    with pytest.raises(MalformedFrameError):
        parse_ack(bytes.fromhex("FD FC FB FA 04 00 60 01 00 00 04 03 02 00"))


def test_parse_ack_length_mismatch_raises():
    with pytest.raises(MalformedFrameError):
        parse_ack(bytes.fromhex("FD FC FB FA 06 00 60 01 00 00 04 03 02 01"))


def test_parse_ack_bit_not_set_raises():
    with pytest.raises(MalformedFrameError):
        parse_ack(bytes.fromhex("FD FC FB FA 04 00 60 00 00 00 04 03 02 01"))


def test_raise_for_ack_does_nothing_on_success():
    ack = AckResult(command_word=CMD_SET_MAX_GATE, ok=True, extra=b"")
    raise_for_ack(ack, hint=MAX_GATE_ACK_HINT)


def test_raise_for_ack_raises_with_hint_on_failure():
    ack = AckResult(command_word=CMD_SET_MAX_GATE, ok=False, extra=b"")
    with pytest.raises(AckError) as exc_info:
        raise_for_ack(ack, hint=MAX_GATE_ACK_HINT)
    assert MAX_GATE_ACK_HINT in str(exc_info.value)


def test_raise_for_ack_raises_without_hint():
    ack = AckResult(command_word=CMD_SET_MAX_GATE, ok=False, extra=b"")
    with pytest.raises(AckError):
        raise_for_ack(ack)


def test_max_gate_ack_failure_via_parse_ack_raises_with_hint():
    ack = parse_ack(bytes.fromhex("FD FC FB FA 04 00 60 01 01 00 04 03 02 01"))
    with pytest.raises(AckError) as exc_info:
        raise_for_ack(ack, hint=MAX_GATE_ACK_HINT)
    assert MAX_GATE_ACK_HINT in str(exc_info.value)


def test_max_gate_ack_success_via_parse_ack_does_not_raise():
    ack = parse_ack(bytes.fromhex("FD FC FB FA 04 00 60 01 00 00 04 03 02 01"))
    raise_for_ack(ack, hint=MAX_GATE_ACK_HINT)
