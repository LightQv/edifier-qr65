import pytest

from edifier_qr65.protocol import (
    AMBIENT_LIGHT_QUERY,
    Frame,
    decode_ambient_light,
    decode_v2,
    encode_static_color,
    encode_v2,
)


def test_encode_v2_query() -> None:
    assert encode_v2(AMBIENT_LIGHT_QUERY) == bytes.fromhex("AA EC 6A 00 00 00")


def test_decode_v2_rejects_bad_checksum() -> None:
    with pytest.raises(ValueError, match="checksum"):
        decode_v2(bytes.fromhex("BB EC 6A 00 02 0B 01 00"))


def test_decode_ambient_light() -> None:
    frame = Frame(0xBB, 0xEC, 0x6A, bytes.fromhex("0B 01 01 FF 00 00 32 FF"))
    state = decode_ambient_light(frame)

    assert state.array_index == 11
    assert state.selected_mode == 1
    assert state.modes[0].red == 255
    assert state.modes[0].brightness == 50


def test_static_color_matches_captured_connex_packet() -> None:
    assert encode_static_color(0xFF, 0x2F, 0x15, 50) == bytes.fromhex(
        "AA EC 6B 00 07 04 07 FF 2F 15 32 FF 87"
    )


@pytest.mark.parametrize("color", [(-1, 0, 0), (0, 256, 0), (0, 0, 999)])
def test_static_color_rejects_invalid_channels(color: tuple[int, int, int]) -> None:
    with pytest.raises(ValueError, match="RGB"):
        encode_static_color(*color)
