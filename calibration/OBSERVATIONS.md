# Subjective Color Observations

These observations produced the accepted `subjective-v1` profile. They compare
display targets with QR65 commands selected by eye, not instrument measurements.

## Conditions

- Speaker brightness: 50%
- Monitor brightness: 75%
- Night light: disabled
- QR65 global model controlled through Edifier ConneX static lighting
- Display and room conditions held stable during each comparison

The accepted source data is retained in `observations.json`. It was curated from
the guided hue-pass export and subsequent manual white and pastel trials; local
timestamps, paths, and session notes were intentionally omitted. It contains 12
saturated hue anchors, three repeated primaries, one white anchor, and three
pastel preference anchors.

## White Compensation

Literal `#FFFFFF` appeared blue. Progressive trials reduced blue and then green:

| Command | Observation |
| --- | --- |
| `#FFFFFF` | Clearly blue |
| `#FFFF80` | More neutral |
| `#FFFF40` | Neutral to yellowish |
| `#FFFFA0` | Slightly cold |
| `#FFE0A0` | Improved, still cold |
| `#FFE080` | Closest tested neutral white |

The accepted white anchor is approximate and is not a universal RGB multiplier.

## Pastel Preferences

| Display target | Accepted QR65 command | Assessment |
| --- | --- | --- |
| Mauve `#CBA6F7` | `#C244C0` | Good |
| Green `#A6E3A1` | `#7FE047` | Good enough |
| Peach `#FAB387` | `#FF6414` | Matching the displayed peach |

These are tuning anchors, not independent validation samples.

## Visual Comparisons

The accepted profile was compared with the superseded matrix profile on colors
not used as hue or pastel anchors:

| Display target | Old command | Accepted command | Assessment |
| --- | --- | --- | --- |
| Sky `#89DCEB` | `#B2CDA2` | `#53CA79` | Accepted command preferred; slightly oversaturated |
| Pink `#F5C2E7` | `#FF9EAB` | `#F6775B` | Accepted command much better; slightly undersaturated |
| Yellow `#F9E2AF` | `#FFAD5E` | `#FC9A2F` | Accepted command much better; slightly undersaturated |
| Orange `#E68E0D` | `#FD3600` | `#E64003` | Accepted command preferred |

Yellow retained its hue when speaker brightness changed from 50% to 25%. This
single check does not establish behavior for other colors or brightness levels.

## Limitations

- Results are subjective and specific to the tested speaker and viewing setup.
- Dark and near-neutral targets need broader validation.
- HSV value scaling is an approximation, not photometric calibration.
- Brightness behavior is not characterized beyond the yellow check above.
- Small, conflicting saturation preferences were recorded rather than fitted
  into an unsupported global or hue-dependent adjustment.

The previous matrix implementation and its raw experiment remain recoverable
from Git history but are intentionally absent from the active calibration tree.
