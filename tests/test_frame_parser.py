from src.protocol.data_frame import (
    DATA_HEADER,
    DataFrame,
    DistanceWindow,
    parse_next_data_frame,
    presence,
    presence_in_range,
)

_VALID_BASIC_FRAME = bytes.fromhex(
    "F4 F3 F2 F1 0D 00 02 AA 02 51 00 00 00 00 3B 00 00 55 00 F8 F7 F6 F5"
)


def test_parse_basic_frame_stationary_present():
    frame, remaining = parse_next_data_frame(_VALID_BASIC_FRAME)
    assert frame == DataFrame(
        data_type=0x02,
        target_state=2,
        moving_distance_cm=81,
        moving_energy=0,
        static_distance_cm=0,
        static_energy=0x3B,
        detection_distance_cm=0,
    )
    assert frame.present is True
    assert remaining == b""


def test_presence_matrix_over_all_documented_states():
    assert presence(0) is False
    assert presence(1) is True
    assert presence(2) is True
    assert presence(3) is True
    assert presence(4) is False
    assert presence(5) is False
    assert presence(6) is False


def test_frame_with_no_target_state_is_not_present():
    frame_bytes = bytearray(_VALID_BASIC_FRAME)
    frame_bytes[8] = 0x00  # target_state byte (after F4F3F2F1 len data_type AA)

    frame, _ = parse_next_data_frame(bytes(frame_bytes))
    assert frame.target_state == 0
    assert frame.present is False


def test_frame_with_moving_and_stationary_state_is_present():
    frame_bytes = bytearray(_VALID_BASIC_FRAME)
    frame_bytes[8] = 0x03  # target_state byte

    frame, _ = parse_next_data_frame(bytes(frame_bytes))
    assert frame.target_state == 3
    assert frame.present is True


def test_resync_skips_garbage_before_header():
    buffer = bytes.fromhex("AA BB") + _VALID_BASIC_FRAME
    frame, remaining = parse_next_data_frame(buffer)

    assert frame.target_state == 2
    assert frame.moving_distance_cm == 81
    assert remaining == b""


def test_rejects_frame_with_bad_tail_marker():
    frame_bytes = bytearray(_VALID_BASIC_FRAME)
    frame_bytes[17] = 0x56  # corrupt the 55 -> 56 in-payload tail marker

    frame, remaining = parse_next_data_frame(bytes(frame_bytes))
    assert frame is None
    assert len(remaining) <= len(DATA_HEADER) - 1


def test_incomplete_frame_waits_for_more_bytes():
    partial = _VALID_BASIC_FRAME[:10]
    frame, remaining = parse_next_data_frame(partial)
    assert frame is None
    assert remaining == partial


def test_no_header_at_all_trims_buffer():
    noise = bytes([0xAA, 0xBB]) * 100
    frame, remaining = parse_next_data_frame(noise)
    assert frame is None
    assert len(remaining) <= len(DATA_HEADER) - 1


def test_oversized_declared_length_is_treated_as_corrupt():
    buffer = bytes.fromhex("F4 F3 F2 F1 FF FF") + b"\x00" * 10
    frame, remaining = parse_next_data_frame(buffer)
    assert frame is None
    assert len(remaining) <= len(DATA_HEADER) - 1


def _frame(target_state: int, moving_cm: int, static_cm: int) -> DataFrame:
    return DataFrame(
        data_type=0x02,
        target_state=target_state,
        moving_distance_cm=moving_cm,
        moving_energy=50,
        static_distance_cm=static_cm,
        static_energy=50,
        detection_distance_cm=moving_cm,
    )


def test_presence_in_range_open_window_matches_plain_presence():
    window = DistanceWindow()
    assert presence_in_range(_frame(1, 500, 0), window) is True
    assert presence_in_range(_frame(0, 500, 0), window) is False


def test_presence_in_range_accepts_moving_target_inside_window():
    window = DistanceWindow(min_cm=40, max_cm=60)
    assert presence_in_range(_frame(1, 50, 0), window) is True


def test_presence_in_range_rejects_moving_target_outside_window():
    window = DistanceWindow(min_cm=40, max_cm=60)
    assert presence_in_range(_frame(1, 85, 0), window) is False
    assert presence_in_range(_frame(1, 20, 0), window) is False


def test_presence_in_range_accepts_static_target_inside_window():
    window = DistanceWindow(min_cm=40, max_cm=60)
    assert presence_in_range(_frame(2, 0, 55), window) is True
    assert presence_in_range(_frame(2, 0, 90), window) is False


# target_state=3 means both channels report a target; either one inside the band is enough.
def test_presence_in_range_both_channels_needs_only_one_inside():
    window = DistanceWindow(min_cm=40, max_cm=60)
    assert presence_in_range(_frame(3, 50, 200), window) is True
    assert presence_in_range(_frame(3, 200, 55), window) is True
    assert presence_in_range(_frame(3, 200, 200), window) is False


def test_presence_in_range_supports_open_ended_bounds():
    assert presence_in_range(_frame(1, 300, 0), DistanceWindow(min_cm=100)) is True
    assert presence_in_range(_frame(1, 50, 0), DistanceWindow(min_cm=100)) is False
    assert presence_in_range(_frame(1, 50, 0), DistanceWindow(max_cm=100)) is True
    assert presence_in_range(_frame(1, 300, 0), DistanceWindow(max_cm=100)) is False


# Regression: 0x05/0x06 are noise-calibration states whose bits overlap the moving/static flags
# (0x05 sets bit0, 0x06 sets bit1). They must never be read as a target, filter or no filter.
def test_presence_in_range_ignores_noise_calibration_states():
    window = DistanceWindow(min_cm=40, max_cm=60)
    for state in (4, 5, 6):
        assert presence_in_range(_frame(state, 50, 50), window) is False
        assert presence_in_range(_frame(state, 50, 50), DistanceWindow()) is False
