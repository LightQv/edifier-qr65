"""Subjective hue matching with compensated white and pastel preferences."""

from __future__ import annotations

from colorsys import rgb_to_hsv

from ._color_profile import (
    BOUNDARY,
    EPSILON,
    NEUTRAL_BLEND_END,
    NEUTRAL_SATURATION,
    POWER,
    RESIDUALS,
    WHITE,
)


def _smooth(value: float) -> float:
    """Return a smooth bounded interpolation weight."""
    return value * value * (3 - 2 * value)


def _edge(hue: float) -> tuple[float, float, float]:
    """Interpolate command RGB along the periodic measured hue boundary."""
    for index, (left_hue, left) in enumerate(BOUNDARY):
        right_hue, right = BOUNDARY[(index + 1) % len(BOUNDARY)]
        if index == len(BOUNDARY) - 1:
            right_hue += 1
        if left_hue <= hue <= right_hue:
            amount = (hue - left_hue) / (right_hue - left_hue)
            return tuple(a + amount * (b - a) for a, b in zip(left, right, strict=True))
    raise ValueError("hue outside calibrated unit interval")


def match_rgb(red: int, green: int, blue: int) -> tuple[int, int, int]:
    """Map display RGB to a bounded, subjectively calibrated speaker command.

    Neutral targets use the measured white anchor; black remains black. Near
    neutral, correction fades continuously to that anchor. HSV value scaling is
    an approximation, not a photometric brightness calibration.

    Args:
        red: Display red channel, integer from 0 to 255.
        green: Display green channel, integer from 0 to 255.
        blue: Display blue channel, integer from 0 to 255.

    Returns:
        Calibrated red, green, and blue command channels.

    Raises:
        ValueError: A channel is not an integer in the supported range.
    """
    channels = (red, green, blue)
    if any(type(value) is not int or not 0 <= value <= 255 for value in channels):
        raise ValueError("RGB channels must be integers between 0 and 255")
    hue, saturation, value = rgb_to_hsv(*(channel / 255 for channel in channels))
    if value == 0:
        return (0, 0, 0)

    amount = ((saturation + EPSILON) ** POWER - EPSILON ** POWER) / (
        (1 + EPSILON) ** POWER - EPSILON ** POWER)
    result = [a + amount * (b - a) for a, b in zip(WHITE, _edge(hue), strict=True)]
    for anchor_hue, anchor_saturation, residual in RESIDUALS:
        distance = abs(hue - anchor_hue)
        distance = min(distance, 1 - distance)
        hue_weight = _smooth(max(0, 1 - distance * 6))
        radial = saturation / anchor_saturation if saturation <= anchor_saturation else (
            (1 - saturation) / (1 - anchor_saturation))
        weight = hue_weight * _smooth(radial)
        for index in range(3):
            result[index] += weight * residual[index]
    neutral_position = min(
        1.0,
        max(
            0.0,
            (saturation - NEUTRAL_SATURATION)
            / (NEUTRAL_BLEND_END - NEUTRAL_SATURATION),
        ),
    )
    chromatic_weight = _smooth(neutral_position)
    result = [
        white + chromatic_weight * (channel - white)
        for white, channel in zip(WHITE, result, strict=True)
    ]
    return tuple(round(255 * min(1.0, max(0.0, value * channel))) for channel in result)
