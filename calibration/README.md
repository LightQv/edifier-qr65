# QR65 Display-to-Light Calibration

The accepted `subjective-v1` profile maps a requested display HEX color to the
RGB command that most closely reproduced it on the tested QR65. Literal RGB was
not sufficient: white appeared blue, several cyan/green hues shifted, and pastel
accents lost their intended character.

This directory contains only the accepted calibration pass:

- `observations.json`: source hue, repeat, white, and pastel observations
- `hue-pass.html` and `hue-pass.js`: standalone collection tool
- `model.py`: standard-library reproduction of the fitted profile
- `test_model.py`: model invariants and runtime agreement checks
- `OBSERVATIONS.md`: conditions, visual comparisons, and limitations

## Collection

Open `hue-pass.html` in a color-managed browser. No server or dependencies are
required. The page guides 12 saturated hues and three repeated primaries at 50%
speaker brightness.

1. Disable night light and other display color filters.
2. Keep monitor brightness, room lighting, and viewing position stable.
3. Run `edifier-qr65 release`, connect ConneX, and select static lighting.
4. For each displayed target, adjust the ConneX HEX until the light is closest.
5. Export JSON checkpoints regularly.
6. Close ConneX and run `edifier-qr65 resume` when finished.

The collection tool never changes daemon files or BLE state itself.

## Model

The model uses periodic piecewise-linear interpolation around the measured
saturated hue boundary. Repeated measurements receive equal weight. It blends
the compensated white anchor toward that boundary using a regularized saturation
power curve, then applies smooth local residuals for the three pastel anchors.

The fitted saturation exponent is `0.38`; the regularization epsilon is `0.02`.
Pastel influence fades to zero at neutral, at full saturation, and 60 degrees
away in hue. Targets at or below 10% HSV saturation use the compensated white
anchor to prevent unstable near-neutral hues from reintroducing the speaker's
blue cast. A smooth transition from 10% through 20% rejoins the fitted chromatic
model without changing the accepted samples above that range. Black is
preserved, output channels are bounded, and HSV value scales the result after
compensation.

These choices form a reproducible subjective mapping, not a physical LED or
colorimetric model. See `OBSERVATIONS.md` for evidence and limitations.

## Reproduction

Print model metadata and sample mappings without touching Bluetooth or daemon
configuration:

```bash
python calibration/model.py '#89DCEB' '#F5C2E7' '#F9E2AF'
```

Verify anchors, continuity, bounds, determinism, and agreement with the runtime
implementation over 4,096 RGB inputs:

```bash
PYTHONPATH=src python -m unittest discover -s calibration -p test_model.py
```

The calibration and runtime require only the Python standard library.
