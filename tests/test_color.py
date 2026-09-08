import math

import pytest

from edifier_qr65.color import match_rgb


@pytest.mark.parametrize(
    ("target", "expected"),
    [
        ((0xE6, 0x8E, 0x0D), (0xFD, 0x36, 0x00)),
        ((0xBD, 0x93, 0xF9), (0xE2, 0x66, 0xA0)),
        ((0x50, 0xFA, 0x7B), (0x8A, 0xFF, 0x41)),
        ((0x8B, 0xE9, 0xFD), (0xB6, 0xD9, 0xAC)),
    ],
)
def test_matching_uses_calibrated_profile(target, expected) -> None:
    assert match_rgb(*target) == expected


@pytest.mark.parametrize("value", [0, 32, 128, 255])
def test_matching_preserves_neutral_colors(value: int) -> None:
    assert match_rgb(value, value, value) == (value, value, value)


def test_profile_stays_close_to_recorded_calibration_matches() -> None:
    samples = [
        ("#CBA6F7", "#FF40A6"),
        ("#94E2D5", "#96FF71"),
        ("#F1FA8C", "#FF8F17"),
        ("#6272A4", "#C68AFF"),
        ("#A6E3A1", "#CCFF3D"),
        ("#FAB387", "#FF4514"),
        ("#8BE9FD", "#B1FFDE"),
        ("#F38BA8", "#FF2923"),
    ]

    def channels(value: str) -> tuple[int, int, int]:
        return tuple(int(value[index : index + 2], 16) for index in (1, 3, 5))

    raw_errors = []
    matched_errors = []
    for target_text, command_text in samples:
        target = channels(target_text)
        command = channels(command_text)
        raw_errors.extend(left - right for left, right in zip(target, command))
        matched_errors.extend(
            left - right for left, right in zip(match_rgb(*target), command)
        )

    raw_rmse = math.sqrt(sum(value**2 for value in raw_errors) / len(raw_errors))
    matched_rmse = math.sqrt(
        sum(value**2 for value in matched_errors) / len(matched_errors)
    )
    assert matched_rmse < raw_rmse * 0.55


@pytest.mark.parametrize("rgb", [(-1, 0, 0), (0, 256, 0), (1.0, 0, 0)])
def test_matching_rejects_invalid_channels(rgb) -> None:
    with pytest.raises(ValueError, match="RGB channels"):
        match_rgb(*rgb)
