# Second-pass visual observations

Recorded from the guided session on 2026-09-09. These are subjective app-command
comparisons, not instrumental measurements. The accepted candidate-1 profile was
subsequently integrated and installed locally; see the deployment record below.

## Conditions and source data

- Saturated-hue export:
  `/home/lightqv/Downloads/qr65-hue-pass-2026-09-09T20-19-36.953Z.json`.
  All 15 observations are complete; its session-conditions field is empty.
- The user confirmed the comparisons used 50% speaker brightness with monitor
  night light disabled. Monitor brightness was 75% and will remain at 75%.
  These are the reference conditions for fitting and subsequent visual validation.
- White photo: `/home/lightqv/Downloads/IMG_5500.HEIC`. The user increased photo
  saturation to better represent the in-person appearance and photographed in
  darkness to avoid reflections from room LED lamps. Do not derive numerical
  channel corrections from this edited photo.

## White trials

| Command | User observation |
| --- | --- |
| `#FFFFFF` | Blue appearance represented by the photo |
| `#FFFFC0` | Almost no change |
| `#FFFF80` | Less blue, more neutral in initial coarse comparison |
| `#FFFF40` | Neutral/yellowish |
| `#FFFF00` | Yellow-green |
| `#FFFFA0` | Preferred in subsequent refinement; `#FFFF90` nearly indistinguishable; slightly cold white |
| `#FFE0A0` | Slight improvement after reducing green; still cold white |
| `#FFE080` | Closest provisional neutral anchor; tiny residual bluish appearance |

The later comparisons supersede the initial coarse ranking. Not every proposed
trial received an individual assessment. The anchor is approximate and must not
be treated as a universal RGB multiplier.

## Mauve saturation/preference trials

Reference used in the guided comparison: Catppuccin Mocha mauve `#CBA6F7`, from
the original dataset. The active theme's actual accent has not been independently
confirmed during this session.

| Candidate command | Observation |
| --- | --- |
| `#D798AC` | Softer candidate; not selected |
| `#C369BF` | Preferred region between this and `#B03AD2`, closer to the latter |
| `#B03AD2` | Close, but slightly too blue and lacking purple |
| `#B444CE` | Intermediate candidate; no separate assessment |
| `#BC44C6` | Better, but still slightly too blue and lacking red |
| `#C244C0` | User confirmed: “is good” |

Accepted subjective tuning pair: **`#CBA6F7` → `#C244C0`**.
This is a tuning observation, not a withheld validation result. Candidate commands
were exploratory; no general saturation curve has yet been fitted or validated.

## Pastel green saturation/preference trials

Displayed reference requested: Catppuccin Mocha green `#A6E3A1`.

| Candidate command | Observation |
| --- | --- |
| `#ACE080` | Softer candidate; not selected |
| `#8EE05A` | Slightly too much blue |
| `#70E034` | Too saturated |
| `#7FE047` | Midpoint; user confirmed “good enough” |

Accepted subjective tuning pair: **`#A6E3A1` → `#7FE047`**.
The preference is intermediate saturation rather than maximum saturation.

## Next

The warm pastel comparison below completes the initial three-family preference
pass. Build and evaluate a candidate mapping, preserving additional theme accents
as withheld visual validation cases.
At the end of the measurement pass, no live matching changes had yet been made.

## Peach saturation/preference trials

Displayed reference requested: Catppuccin Mocha peach `#FAB387`.

| Candidate command | Observation |
| --- | --- |
| `#FF9850` | Softer candidate; not selected |
| `#FF8038` | Intermediate candidate; not selected |
| `#FF6820` | Not bad, but needs slightly more saturation |
| `#FF6414` | User confirmed “this is matching the peach” |

Accepted subjective tuning pair: **`#FAB387` → `#FF6414`**.
This is a tuning observation, not independent validation.

## Candidate-1 withheld visual validation

- Sky target `#89DCEB`, candidate command `#53CA79`, previewed through the daemon
  in static mode with matching disabled at 50% brightness.
- User assessment: “a tiny bit too much saturated but honestly good”.
- Retain this unmodified as a positive first-pass result with mild excess
  saturation. No literal/old-profile A/B comparison has been completed yet.
- Do not tune this sample before checking the other withheld hues.
- Pink target `#F5C2E7`, candidate command `#F6775B`, under the same preview
  conditions: user assessment “Good but lack a bit of saturation this time.”
  Retain the candidate unchanged for the remaining first-pass comparison. Sky
  and pink preferences point in opposite saturation directions, so a global
  saturation adjustment is not yet justified.
- Yellow target `#F9E2AF`, candidate command `#FC9A2F`, under the same preview
  conditions: user assessment “Good, lack i tiny bit of saturation but not that
  much.” All three first-pass validation hues were described as good, with small
  saturation preference differences. Comparative improvement over the installed
  profile and literal commands remains to be assessed.
- Sky old/new comparison: installed profile applied `#B2CDA2`; after switching
  back to candidate `#53CA79`, the user preferred the candidate, while reiterating
  that it is slightly too saturated. This is a positive comparative result for
  one hue, not evidence of overall superiority across themes.
- Pink old/new comparison: installed profile applied `#FF9EAB`; candidate
  `#F6775B` was “way better”, with a tiny remaining lack of saturation.
  This is the second positive comparative result; the candidate remains unchanged.
- Yellow old/new comparison: installed profile applied `#FFAD5E`; candidate
  `#FC9A2F` was “way better”, with only a very slight saturation shortfall.
  The user preferred candidate-1 on all three withheld old/new comparisons.
  Retain candidate-1 unchanged: sky needs slightly less saturation, whereas pink
  and yellow need slightly more. These small preferences do not justify a global
  boost or establish a validated hue-dependent adjustment.
- Yellow brightness check: candidate `#FC9A2F` at 25% retained the same yellow
  hue; user assessment “its good”. This supports stability for this color between
  25% and 50%, not a general conclusion for all hues or brightness settings.
- Orange regression comparison: target `#E68E0D`, installed output `#FD3600`,
  candidate `#E64003`, at 50%. User confirmed “new is better”. This known accent
  was not used to tune candidate-1; it is a regression check against the original
  profile, not a new second-pass training anchor.

## Local deployment

- Integrated candidate-1 without further saturation changes after visual checks.
- 130 tests passed, including fitting/runtime agreement over 4,096 RGB inputs.
- Installed managed release `0.1.0.Os8h4G`; previous release `0.1.0.IzTsXO`
  remains available for rollback. Source changes are local and uncommitted.
- Restored dynamic mode, matching enabled, brightness 50%, configured static
  color `#FFB86C`, and original theme request `#E68E0D`.
- Live status confirmed connected with requested `#E68E0D`, applied `#E64003`.
- A subsequent service restart preserved those settings and reconnected with the
  same requested/applied colors and brightness.
- The original profile is archived as `calibration/legacy_color.py`; the original
  dataset and fitter remain available.
- Remaining validation: broader real themes, dark/near-neutral targets, additional
  brightness/hue combinations, and literal-command comparisons. Small saturation
  preferences from sky/pink/yellow are recorded, not silently fitted into the model.
