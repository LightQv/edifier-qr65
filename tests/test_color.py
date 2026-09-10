import pytest

from edifier_qr65.color import match_rgb


@pytest.mark.parametrize(
    ("target", "expected"),
    [
        ((0xE6, 0x8E, 0x0D), (0xE6, 0x40, 0x03)),
        ((0xCB, 0xA6, 0xF7), (0xC2, 0x44, 0xC0)),
        ((0xA6, 0xE3, 0xA1), (0x7F, 0xE0, 0x47)),
        ((0xFA, 0xB3, 0x87), (0xFF, 0x64, 0x14)),
        ((0x89, 0xDC, 0xEB), (0x53, 0xCA, 0x79)),
        ((0xF5, 0xC2, 0xE7), (0xF6, 0x77, 0x5B)),
        ((0xF9, 0xE2, 0xAF), (0xFC, 0x9A, 0x2F)),
    ],
)
def test_matching_reproduces_visually_accepted_commands(target, expected) -> None:
    assert match_rgb(*target) == expected


@pytest.mark.parametrize("value", [0, 32, 128, 255])
def test_matching_uses_compensated_neutral_anchor(value: int) -> None:
    assert match_rgb(value, value, value) == (
        value, round(value * 224 / 255), round(value * 128 / 255)
    )


@pytest.mark.parametrize("rgb", [(-1, 0, 0), (0, 256, 0), (1.0, 0, 0), (True, 0, 0)])
def test_matching_rejects_invalid_channels(rgb) -> None:
    with pytest.raises(ValueError, match="RGB channels"):
        match_rgb(*rgb)
