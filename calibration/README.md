# QR65 Display-to-Light Calibration

## Second pass: saturated hues

Open `hue-pass.html` in a browser to begin the new experiment. Keep `hue-pass.js`
beside it. This standalone page requires no web server or dependencies.

The page guides 12 saturated hues and three repeat observations at 50% speaker
brightness. Release daemon control with `edifier-qr65 release`, connect ConneX,
and choose static lighting. Match hue using any app color, enter its HEX, and
record match quality. Keep display/room conditions stable and document them.

Progress uses a separate browser-storage key. Export JSON checkpoints regularly;
the page can import them to resume. Empty or unrated samples remain incomplete.
The version-2 exports are a separate dataset and are **not** input to `fit.py`.
Do not overwrite `measurements.json` with them.

After all 15 observations, export the JSON for review. Disconnect ConneX and run
`edifier-qr65 resume` to restore daemon control. Neutral compensation and saturation
preference trials follow once these observations are reviewed; this tool does not
change the active matching profile.

The overall plan is at
`/home/lightqv/Projects/edifier-qr65-color-calibration-plan.md`.

## Experimental second-pass candidate

`second-pass.json` preserves the 12 hue observations, three repeats, confirmed
conditions, provisional white anchor, and three accepted pastel pairs.
`second-pass-observations.md` retains the qualitative context.

Run without installing anything:

```bash
python calibration/candidate.py '#89DCEB' '#F5C2E7' '#F9E2AF'
python -m unittest discover -s calibration -p test_candidate.py
```

The offline fitter does not write configuration or control BLE. Its accepted
candidate-1 constants are now used by runtime matching; tests verify reproduction
and output agreement. It uses periodic piecewise-linear
interpolation around the saturated hue boundary, averaging repeated commands
equally. Green's disagreement is retained in the dataset rather than silently
choosing the later measurement.

The baseline blends compensated white toward that boundary using a regularized
power curve. Grid search over exponents 0.20–1.00 minimizes command-space error
against the three pastel preferences. The fitted exponent is 0.38; baseline RGB
command RMSE is approximately 15.56 on the 0–255 scale. This is not perceptual error.

Smooth local residuals reproduce the three pastel commands. Their influence tapers
to zero at neutral, at full saturation, and 60 degrees away in hue. That width and
the power-curve regularization of 0.02 are experimental assumptions, not measured
hardware characteristics. The pastel anchors are separated by more than 60 degrees;
adding closer anchors requires reconsidering overlapping residuals and refitting.

HSV value scales the output after compensation; this is an unvalidated brightness
assumption for dark targets. Final channels are clipped to legal RGB bounds. Near
neutral, the base curve has finite slope and residuals vanish smoothly. Black is
preserved. A tiny hue-dependent tint cannot become a fully saturated color.

Candidate agreement on training anchors is not validation. Begin visual checks
with unused second-pass targets `#89DCEB` (sky), `#F5C2E7` (pink), and `#F9E2AF`
(yellow). Compare literal HEX, installed matching, and candidate commands under
the same conditions. Once a validation target is used for tuning, stop counting it
as withheld validation. The user preferred candidate-1 over the old profile on
all three and on the original orange regression target. Later revisions need
fresh visual validation.

To preview candidate commands through the installed daemon, use static mode and
disable matching so the active model does not correct the command a second time.
Record the original mode, static color, dynamic requested color, brightness, and
matching setting first; restore all of them when finished.

## Original calibration procedure

Open `index.html` in a color-managed browser and complete all 32 samples. The
dataset contains 24 role-tagged fitting samples and eight role-tagged validation
samples, presented in one shuffled sequence. Four fit samples are neutral-color
observations excluded from coefficient fitting, leaving 20 chromatic rows. The
model family is evaluated on the eight withheld samples before its final
coefficients are refitted on all 28 chromatic observations. Neutral preservation
was imposed separately by the original runtime model. The second pass subsequently
found useful white compensation; the first observations did not establish that
neutral compensation was impossible.

Before measuring:

- Disable night light and other display color filters.
- Keep monitor brightness, room lighting, and viewing position unchanged.
- Release BLE control to ConneX.
- Select ConneX static lighting and set brightness to exactly 50%.
- Adjust RGB only. Do not compensate with the brightness control.

For each reference, enter the ConneX hex that makes the QR65 look closest to
the displayed swatch. Select the closest-match checkbox when the target is
outside the light's reproducible gamut. Progress remains in browser local
storage, and `Export JSON` can create a checkpoint at any time.
An empty current field is exported as an incomplete measurement; malformed hex
text must be corrected or cleared first.

All entries are subjective observations; leaving the checkbox clear means only
that no obvious gamut limit was reached, not that the match is instrumentally
exact. The fitting process regularizes these observations to reduce visual and
input noise.

The exported `qr65-calibration.json` contains the target-to-command pairs used
to fit and validate the replacement color model.

To reproduce the fitted coefficients and held-out metrics, install the optional
calibration dependency and run the fitter from the repository root:

```bash
python -m pip install '.[calibration]'
python calibration/fit.py
```
