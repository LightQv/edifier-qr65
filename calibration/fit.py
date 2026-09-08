"""Fit the QR65 inverse color profile from subjective ConneX matches."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

GAMMA = 0.7498942093324559
RIDGE = 0.07847599703514607
CLOSEST_WEIGHT = 0.25


def parse_rgb(value: str) -> np.ndarray:
    """Convert strict #RRGGBB text to normalized channels."""
    if len(value) != 7 or value[0] != "#":
        raise ValueError(f"invalid RGB value: {value!r}")
    return np.array([int(value[index : index + 2], 16) for index in (1, 3, 5)]) / 255


def saturation(colors: np.ndarray) -> np.ndarray:
    """Return HSV saturation without converting the other components."""
    peak = colors.max(axis=1)
    return np.divide(
        peak - colors.min(axis=1), peak, out=np.zeros_like(peak), where=peak != 0
    )


def kernel(left: np.ndarray, right: np.ndarray) -> np.ndarray:
    """Return the fixed radial basis feature matrix."""
    distances = np.sum((left[:, None, :] - right[None, :, :]) ** 2, axis=2)
    return np.exp(-GAMMA * distances)


def fit(rows: list[dict[str, object]]) -> tuple[np.ndarray, np.ndarray]:
    """Fit saturation-scaled residuals around literal RGB."""
    centers = np.stack([parse_rgb(str(row["target"])) for row in rows])
    commands = np.stack([parse_rgb(str(row["command"])) for row in rows])
    sample_saturation = saturation(centers)
    chromatic = sample_saturation > 0.05
    centers = centers[chromatic]
    commands = commands[chromatic]
    sample_saturation = sample_saturation[chromatic]
    weights = np.array(
        [CLOSEST_WEIGHT if row["closest"] else 1.0 for row in rows]
    )[chromatic]

    features = kernel(centers, centers)
    residuals = (commands - centers) / sample_saturation[:, None]
    coefficients = np.linalg.solve(
        features.T @ (weights[:, None] * features)
        + RIDGE * np.eye(features.shape[1]),
        features.T @ (weights[:, None] * residuals),
    )
    return centers, coefficients


def predict(
    colors: np.ndarray, centers: np.ndarray, coefficients: np.ndarray
) -> np.ndarray:
    """Apply a fitted model to normalized RGB rows."""
    correction = saturation(colors)[:, None] * kernel(colors, centers) @ coefficients
    return np.clip(colors + correction, 0, 1)


def metrics(label: str, predicted: np.ndarray, expected: np.ndarray) -> None:
    """Print command-space diagnostics for one model."""
    delta = (predicted - expected) * 255
    sample_error = np.linalg.norm(delta, axis=1)
    print(
        f"{label}: RMSE={np.sqrt(np.mean(delta**2)):.1f}, "
        f"MAE={np.mean(np.abs(delta)):.1f}, "
        f"median-L2={np.median(sample_error):.1f}, max-L2={sample_error.max():.1f}"
    )


def literal(values: np.ndarray, *, integer: bool = False) -> str:
    """Format a tuple constant for direct inclusion in color.py."""
    def format_value(value: float) -> str:
        return str(round(value)) if integer else f"{value:.17g}"

    rows = ",\n".join(
        "    (" + ", ".join(format_value(channel) for channel in row) + ")"
        for row in values
    )
    return "(\n" + rows + "\n)"


def main() -> None:
    """Validate the held-out set, then print the final all-sample profile."""
    path = Path(__file__).with_name("measurements.json")
    rows = json.loads(path.read_text(encoding="utf-8"))["measurements"]
    if len(rows) != 32 or any(row["command"] is None for row in rows):
        raise ValueError("calibration requires 32 complete measurements")

    fitting = [row for row in rows if row["role"] == "fit"]
    validation = [row for row in rows if row["role"] == "validation"]
    centers, coefficients = fit(fitting)
    targets = np.stack([parse_rgb(row["target"]) for row in validation])
    commands = np.stack([parse_rgb(row["command"]) for row in validation])
    metrics("raw validation", targets, commands)
    metrics("fitted validation", predict(targets, centers, coefficients), commands)

    centers, coefficients = fit(rows)
    print(f"\nPROFILE_GAMMA = {GAMMA!r}")
    print("PROFILE_CENTERS = " + literal(centers * 255, integer=True))
    print("PROFILE_COEFFICIENTS = " + literal(coefficients))


if __name__ == "__main__":
    main()
