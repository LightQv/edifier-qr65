"""Reproduce the accepted subjective profile without modifying the daemon.

This is a geometric interpolation hypothesis, not a physical LED model. Run with
HEX arguments to print profile commands; no BLE or configuration writes occur.
"""

from __future__ import annotations

import argparse
import colorsys
import json
import math
import re
from pathlib import Path


def rgb(value: str) -> tuple[float, float, float]:
    """Parse a strict HEX color into normalized channels."""
    if not isinstance(value, str) or re.fullmatch(r"#[0-9a-fA-F]{6}", value) is None:
        raise ValueError("color must be #RRGGBB")
    return tuple(int(value[index:index + 2], 16) / 255 for index in (1, 3, 5))


def mix(left, right, amount):
    """Interpolate equally sized channel vectors."""
    return tuple(a + amount * (b - a) for a, b in zip(left, right, strict=True))


def smooth(value):
    """Smooth a bounded weight without overshoot."""
    return value * value * (3 - 2 * value)


class Profile:
    """Interpolate hue boundaries, compensated white, and local pastel residuals."""

    def __init__(self, path: Path | None = None):
        data = json.loads((path or Path(__file__).with_name("observations.json")).read_text())
        if data["version"] != 1:
            raise ValueError("unsupported observation version")
        self.data = data
        self.white = rgb(data["white"])
        # Average repeat observations equally: green's two matches are uncertain.
        grouped = {}
        for row in data["hues"] + data["repeats"]:
            hue, saturation, value = colorsys.rgb_to_hsv(*rgb(row["target"]))
            if saturation != 1 or value != 1:
                raise ValueError("boundary targets must be fully saturated at full value")
            grouped.setdefault(hue, []).append(rgb(row["command"]))
        self.boundary = sorted((h, tuple(sum(c[i] for c in rows) / len(rows)
                                         for i in range(3))) for h, rows in grouped.items())
        self.pastels = [(colorsys.rgb_to_hsv(*rgb(row["target"])), rgb(row["command"]))
                        for row in data["pastels"]]
        # Fit one saturation exponent in command space. The finite-slope boost
        # remains continuous at neutral and does not amplify tiny tints infinitely.
        self.power = min((i / 100 for i in range(20, 101)), key=self.loss)
        self.residuals = []
        for (h, s, v), command in self.pastels:
            base = self.base(h, s, self.power)
            self.residuals.append((h, s, tuple(c / v - b for c, b in zip(command, base))))

    def edge(self, hue):
        """Interpolate the measured boundary periodically across red."""
        points = self.boundary
        for index, (left_hue, left) in enumerate(points):
            right_hue, right = points[(index + 1) % len(points)]
            if index == len(points) - 1:
                right_hue += 1
            position = hue if hue >= points[0][0] else hue + 1
            if left_hue <= position <= right_hue:
                return mix(left, right, (position - left_hue) / (right_hue - left_hue))
        raise ValueError("hue outside unit interval")

    def base(self, hue, saturation, power):
        """Blend white toward the hue boundary with a regularized power curve."""
        epsilon = 0.02
        amount = ((saturation + epsilon) ** power - epsilon ** power) / (
            (1 + epsilon) ** power - epsilon ** power)
        return mix(self.white, self.edge(hue), amount)

    def loss(self, power):
        """Score the base curve against preferred commands, not emitted colors."""
        return sum((v * predicted - expected) ** 2
                   for (h, s, v), command in self.pastels
                   for predicted, expected in zip(self.base(h, s, power), command))

    def predict(self, color: str) -> tuple[float, float, float]:
        """Return bounded command channels, preserving black and neutral continuity."""
        h, s, v = colorsys.rgb_to_hsv(*rgb(color))
        if v == 0:
            return (0.0, 0.0, 0.0)
        result = list(self.base(h, s, self.power))
        for anchor_hue, anchor_saturation, residual in self.residuals:
            distance = abs(h - anchor_hue)
            distance = min(distance, 1 - distance)
            # Local influence falls to zero at 60 degrees. This width is an
            # experimental assumption, to be evaluated on withheld hues.
            hue_weight = smooth(max(0, 1 - distance * 6))
            radial = s / anchor_saturation if s <= anchor_saturation else (
                (1 - s) / (1 - anchor_saturation))
            weight = hue_weight * smooth(radial)
            for index in range(3):
                result[index] += weight * residual[index]
        return tuple(min(1.0, max(0.0, v * channel)) for channel in result)

    def command(self, color: str) -> str:
        """Format a profile prediction as a HEX command."""
        return "#" + "".join(f"{round(channel * 255):02X}" for channel in self.predict(color))


def main():
    """Print reproducible model metadata and profile color commands."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("colors", nargs="*")
    args = parser.parse_args()
    model = Profile()
    print(json.dumps({"profile": model.data["profile"], "saturationPower": model.power,
                      "baseCommandRMSE": math.sqrt(
                          model.loss(model.power) / (len(model.pastels) * 3)
                      ) * 255,
                      "warning": "Subjective profile; training agreement is not visual validation."}))
    for color in args.colors or [row["target"] for row in model.data["pastels"]]:
        print(f"{color.upper()} -> {model.command(color)}")


if __name__ == "__main__":
    main()
