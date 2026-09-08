# QR65 Display-to-Light Calibration

Open `index.html` in a color-managed browser and complete all 32 samples. The
dataset contains 24 role-tagged fitting samples and eight role-tagged validation
samples, presented in one shuffled sequence. Four fit samples are neutral-color
observations excluded from coefficient fitting, leaving 20 chromatic rows. The
model family is evaluated on the eight withheld samples before its final
coefficients are refitted on all 28 chromatic observations. Neutral preservation
is imposed separately by the runtime model because the measurements indicate
that the QR65 cannot reproduce neutral light at this brightness.

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
