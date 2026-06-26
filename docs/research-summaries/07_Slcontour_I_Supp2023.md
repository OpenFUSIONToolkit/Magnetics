# SLCONTOUR (Part I) — Supplementary Topics

**Source PDF:** `resources/DIII-D IDL Command Line Tools/Strait_Magnetics_20230426_Slcontour(I)_Supp.pdf`
**Title (verbatim, p.1):** "Introduction to SLCONTOUR: Supplementary Topics"
**Author:** Ted Strait
**Date:** April 26, 2023
**Pages:** 13
**Footer on every page (verbatim):** "E. Strait / DIII-D Magnetics / Apr. 26, 2023"

> ACCURACY NOTE: All content below is taken directly from the document's extracted text. The figure-bearing slides (pp. 7, 10, 12) are vector-graphics plots whose text labels were extracted but whose pixel content was NOT extractable as a raster image (the only embedded raster images in the PDF are the DIII-D logo, a blue header band, and decorative gray arrows). Plot descriptions below are reconstructed from the extracted axis/label text only; where the extracted text is fragmentary/interleaved I say so rather than inventing detail. Numeric tables on pp. 8, 9, 11, 13 are extracted text and are quoted as-is.

---

## Document overview

This is an explicitly labeled **supplement** to the SLCONTOUR Part I introduction. Per p.1, these are "Supplementary Topics (Not presented on April 20)," and the two topics are (verbatim bullets, p.1):
- "More information on baseline subtraction options"
- "Spotting Bad Data in 3D Magnetics"

Structure: pp.2–5 cover baseline subtraction (`btype`) options in detail; p.6 is an overview of the bad-data workflow; pp.7–13 are a worked case study on shot 194444 demonstrating how to detect and remove bad magnetic probe data.

---

## Magnetic sensors / hardware

Described in the context of the case study rather than as a standalone hardware section:
- The case study uses the **MPID** array — "Bp Pairs" (poloidal-field probe pairs). Header text (p.10): "Shot 194444 MPID: Bp, Pairs, Tor, LFS, R0, delta-B (G)" (Tor = toroidal; LFS = low-field side; R0 = ... [abbreviation not expanded in document]).
- 10 probes / 10 pairs are used: MPID66M020, M067, M097, M127, M157, M200, M247, M277, M307, M340 (the "66M" series; numeric suffix = approximate toroidal angle).
- p.10: "MPID66M07 and MPID66M247 have zero signal" (note: "MPID66M07" appears to be a typo in the slide for MPID66M067) ... "These pairs both use the probe MPI66M247 (known to be bad)".
- p.10 hardware-failure explanation (verbatim): "Probably the integrator output is saturated at 10 V à baseline subtraction leads to a constant value of zero."
- The `list` command output (p.11) gives per-probe geometry columns: **Mask, Name, R(m), Z(m), Theta(deg), Phi1(deg), Phi2(deg)**. R ≈ 2.411–2.413 m, Z ≈ 0 (all near midplane), Theta ≈ 0. "Phi1/Phi2" are the "Toroidal locations of probes in a pair" (annotation on p.11).

---

## SLCONTOUR

This supplement adds detail in two areas: the `btype` baseline-subtraction option set, and a bad-data diagnosis workflow using specific commands.

### Baseline subtraction — the `btype` command (pp.2–5)

Command usage notes (p.2, verbatim fragments):
- `--> btype` — "Without argument: list the options"
- `--> btype=1` — "Select baseline algorithm ("baseline type")"; annotated "Default value – best for most cases"
- `--> base=100` — "Select baseline time interval (ms)"; annotated "Default value – good for many cases"
- `--> tbmin=2200,tbmax=2800` — "Baseline start, end times (ms)"; "Optional, only applies to btype = 11 to 13"; "Timing for btype = 1 to 3 is set by tmin, tmax"

**Full `btype` value list (verbatim, p.2):**
```
0 = No baseline subtraction
1 = baseline: early data, ∆t=base
2 = baseline: late data
3 = baseline: interpolated
4 = baseline: running average
5 = baseline: running ave., lag=base
6 = baseline: running ave., lag=2xbase
7 = baseline: RC filter, tau=base
8 = baseline: RC filter, lag=base
9 = single-freq. sine fit, period=base
10 = single-freq. square fit, period=base
11 = average on interval [tbmin, tbmax]
12 = linear fit on interval [tbmin, tbmax]
13 = interpolate tbmin+[0,base] to tbmax-[base,0]
```

**Baseline options grouped by use case:**

- *Transient events (p.3):* "Use the average value on a specified time interval before or after the transient as the "zero" level."
  - btype = 1: "Average over an interval of duration "base" at the start of the plotted time window."
  - btype = 2: "Average over an interval of duration "base" at the end of the plotted time window."
  - btype = 3: "Interpolate between the two averages."
  - btype = 11/12/13 "decouple the baseline times from the time window limits": 11 = "Average on an arbitrary interval [tbmin, tbmax]"; 12 = "Interpolate/extrapolate from a linear fit on interval [tbmin, tbmax]"; 13 = "Interpolate between averages on tbmin+[0,base] and tbmax-[base,0]".

- *Long-pulse data (p.4):* "Subtract a running average over a time interval of duration "base"":
  - btype = 4: "Centered at data sample time"
  - btype = 5: "Lag by Dt= base"
  - btype = 6: "Lag by Dt= 2 x base"
  - "Subtract single-pole filtered data, with time constant = base": btype = 7: "Filter up to the data sample time (t = base)"; btype = 8: "Lag by Dt= base".
  - Note (verbatim): "options 5-8 are causal, 4 is not."

- *Periodic data, period = T (p.5):* "Set base = T for all of these options":
  - btype = 4: "Subtracts non-periodic contributions (see previous slide)"
  - btype = 9: "Fit one period of a sine wave around each time sample"
  - btype = 10: "Fit one period of a square wave around each sample"

### Bad-data diagnosis workflow (pp.6–13)

Three-step method (p.6, verbatim):
1. "Check the standard deviation of the fit (printed to the screen) – Compare to the mode amplitudes from the fit"
2. "Check the details of the fit – Using the "residuals" command"
3. "Check the raw data visually to confirm possible bad signals – Remove bad signals using the "omit" command"

Caveats (p.6, verbatim):
- "Removing bad probes is likely to increase the condition number of the fit – Make sure that it is still in an acceptable range – If not, it will be necessary to reduce the number of fitting parameters"
- "Note that the condition number gives no information about bad probes – It is a function only of the quantity and locations of the sensors, not the data"

**Commands demonstrated (verbatim from slides):**
- `--> residuals` (p.9) — prints per-sensor table: Sensor, Flag, Residual, Fit, Measured. Flags entries with `*`; footnote: "* 4 residuals > 10% max fitted value".
- `--> omit MPID66M067 MPID66M247` (p.11) — "Omit the bad sensors"
- `--> list` (p.11) — shows Mask column where `O`/`0` marks an omitted sensor vs `1` active. (Note: text shows "O" in the MPID66M067 row description and "0" in the MPID66M247 row; both denote omitted.)
- `--> add MPID66M067 MPID66M247` (p.11) — "Restore them to the fits, if desired"
- `--> add all` (p.11) — "Restore all omitted sensors"

---

## MODESPEC

Not covered. (MODESPEC is not mentioned anywhere in this document.)

---

## Analysis methods / math

- **Baseline subtraction algorithms** — full list above (averaging windows, running averages, single-pole/RC filtering with time constant, single-frequency sine/square fits, linear fits, interpolation). Distinction drawn between causal (btype 5–8) and non-causal (btype 4) filters (p.4).
- **n-mode fit of 3D magnetics** — the case-study fit decomposes the toroidal-array signal into toroidal harmonics n = 1, 2, 3, each with amplitude and phase, broken out by poloidal index "m" (the example uses m = 0). See screen output p.8.
- **Standard deviation of fit** — primary metric for fit quality; "Compare to the mode amplitudes" / "a significant fraction of the largest mode amplitude (n=1)... Suggests a bad fit" (p.8).
- **Condition number of the array** — "a function only of the quantity and locations of the sensors, not the data" (p.6); used to confirm the fit remains well-conditioned after omitting sensors.
- **Residuals** — "difference of measured and fitted values" (p.9); large residuals (>10% of max fitted value) flag suspect probes.

---

## Visualizations to reproduce

> Plots are vector graphics; descriptions below come from extracted axis/label text only. Pixel-level styling (colors, marker shapes) was NOT recoverable from the PDF — do not assume colors.

**Page 7 — Case study "with bad data" (3-panel composite), title "Shot 194444 MPID (Bp Pairs)":**
- *Mode-amplitude time traces (left panel):* x-axis "Time (ms)" spanning roughly 3820–3880; y-axis "delta-B (G)" with ticks visible at 0, 10, 20, 30. Curves labeled for n = 1, 2, 3 (legend "n = 1 2 3"). Annotation "m = 0". Text says these "look OK" but "note the significant n=2 and 3 amplitudes."
- *Measured-vs-Fit scatter (labeled "Sensor data", upper right):* axes "Measured" vs "Fit", both delta-B in Gauss, range about −30 to +30 (ticks −30,−20,−10,0,10,20,30). Snapshot label "t=3890.0, Theta=0.0". Caption: "Measured and fitted values have some disagreement."
- *Phase / Phi plot (lower right):* y-axis "Phase (deg)" with secondary axis "Phi (deg.)" ticked 0, 90, 180, 270, 360; x-axis "delta-B (G)" range about −40 to +40 (ticks −40,−20,0,20,40). Also bears "m = 0".

**Page 10 — Raw-data stack, header "Shot 194444 MPID: Bp, Pairs, Tor, LFS, R0, delta-B (G)":**
- Ten stacked time-series panels, one per probe pair, each y-axis "delta-B (G)" with range −60 to +60 (ticks at −60, 0, 60). Shared x-axis "Time(msec)" 3820–3880.
- Panel labels (top→bottom): MPID66M020 "20- 97", M067 "68-246", M097 "97-278", M127 "128-307", M157 "158-340", M200 "200- 20", M247 "246-128", M277 "278-158", M307 "307-200", M340 "340- 68" (the two-number labels are the Phi1-Phi2 toroidal pair locations).
- Right-margin parameter box (verbatim): `array = MPID`, `smooth = 0.50`, `base = 20.0`, `btype = 1`, `baseline: early data`, `comp = N`.
- Visual point of the slide: MPID66M067 and MPID66M247 traces are flat zero lines.

**Page 12 — Case study after omitting bad sensors (same 3-panel layout as p.7), title "Shot 194444 MPID (Bp Pairs)":**
- Same panel set as p.7 (mode-amplitude time traces; Measured-vs-Fit "Sensor data" scatter with axes −30..30, snapshot "t=3890.0, Theta=0.0"; Phase/Phi plot 0–360 deg).
- Captions: "Measured and fitted values agree closely"; "The n=2 and 3 amplitudes are significantly reduced."

---

## Concrete example values (as appearing in the document)

- **Shot:** 194444 (case study throughout pp.7–13).
- **Array / diagnostic:** MPID, Bp probe pairs (10 pairs).
- **Snapshot time in scatter plots:** t = 3890.0 (ms), Theta = 0.0 (pp.7, 12).
- **Raw-data time window:** 3820–3880 ms (pp.7, 10, 12).
- **Toroidal harmonics fit:** n = 1, 2, 3; m = 0.
- **Parameter settings (p.10):** smooth = 0.50, base = 20.0, btype = 1, comp = N.

**Fit screen output — all 10 probes (verbatim, p.8):**
```
n =      1            2            3
       Ampl. Phase  Ampl. Phase  Ampl. Phase
All m  23.07 319.61  8.65 280.44  6.33 164.70
m = 0  23.07 319.61  8.65 280.44  6.33 164.70
-----------------------------------
Condition number of array = 1.83
Standard deviation of fit = 6.00
-----------------------------------
```

**Residuals table — all 10 probes (verbatim, p.9; columns Sensor / Flag / Residual / Fit / Measured):**
```
MPID66M020      -1.47    13.0    14.4
MPID66M067      -1.68   -1.68    0.000410
MPID66M097  *    3.36   -21.0   -24.3
MPID66M127      -1.81   -27.5   -25.7
MPID66M157       2.05   -17.4   -19.5
MPID66M200      -1.90   -9.83   -7.93
MPID66M247  *    6.90    6.90   -0.00123
MPID66M277  *   -6.71    16.3    23.0
MPID66M307  *    4.90    24.7    19.8
MPID66M340      -0.302   16.6    16.9
* 4 residuals > 10% max fitted value
```

**Residuals table — after removing 2 bad probes (verbatim, p.9):**
```
MPID66M020      -0.290   14.2    14.4
MPID66M097      -0.202  -24.5   -24.3
MPID66M127      -0.129  -25.8   -25.7
MPID66M157      -0.0478 -19.5   -19.5
MPID66M200      -0.261  -8.19   -7.93
MPID66M277      -0.146   22.9    23.0
MPID66M307      -0.219   19.6    19.8
MPID66M340       0.0216  16.9    16.9
```

**`list` output geometry (verbatim, p.11; Mask / Name / R(m) / Z(m) / Theta(deg) / Phi1(deg) / Phi2(deg)):**
```
1  MPID66M020  2.411  -0.001  -0.1   19.5   97.4
O  MPID66M067  2.413   0.000   0.0   67.5  246.4
1  MPID66M097  2.413  -0.007  -0.6   97.4  277.5
1  MPID66M127  2.413   0.002   0.1  127.9  307.0
1  MPID66M157  2.413  -0.002  -0.1  157.6  339.7
1  MPID66M200  2.411   0.002   0.2  199.7   19.5
0  MPID66M247  2.413  -0.000  -0.0  246.4  127.9
1  MPID66M277  2.413  -0.005  -0.4  277.5  157.6
1  MPID66M307  2.412   0.002   0.2  307.0  199.7
1  MPID66M340  2.413   0.000   0.0  339.7   67.5
```

**Before/after fit-quality comparison (verbatim, p.13):**
```
Using all 10 pairs              Omitting 2 bad pairs
Condition number of array = 1.83  Condition number of array = 2.66
Standard deviation of fit = 6.00  Standard deviation of fit = 0.38
Omitted sensors: MPID66M067, MPID66M247
```

---

## Notable quotes (verbatim, with page numbers)

- (p.1) "Supplementary Topics (Not presented on April 20)"
- (p.2) "btype = 1 ... Default value – best for most cases"; "base=100 ... Default value – good for many cases"
- (p.4) "Note: options 5-8 are causal, 4 is not."
- (p.5) "Set base = T for all of these options"
- (p.6) "Note that the condition number gives no information about bad probes – It is a function only of the quantity and locations of the sensors, not the data"
- (p.6) "Removing bad probes is likely to increase the condition number of the fit"
- (p.8) "Standard deviation is large compared to typical mode amplitudes of a few Gauss ... è Suggests a bad fit, maybe caused by bad data"
- (p.9) "Two probes show measured values ≈0: suggests, but does not prove, bad data"
- (p.10) "Probably the integrator output is saturated at 10 V à baseline subtraction leads to a constant value of zero."
- (p.10) "These pairs both use the probe MPI66M247 (known to be bad)"
- (p.13) "Removing bad pairs improves standard deviation of the fit from 6.0 to 0.4 G – An order of magnitude improvement"
- (p.13) "Removing two inputs increases the condition number from 1.83 to 2.66 – Still a low value: well-conditioned for fitting n=1,2,3"

---

## Digest

This 13-slide supplement to the SLCONTOUR Part I introduction (Ted Strait, DIII-D, Apr. 26, 2023) covers two topics that were not in the main April 20 talk: detailed baseline-subtraction options and a practical workflow for spotting bad data in 3D magnetics. Its most reusable content is the complete enumeration of the `btype` command's 14 baseline algorithms (values 0–13: averaging windows, causal/non-causal running averages, RC/single-pole filters, sine/square periodic fits, and interval-based fits controlled by `base`, `tmin/tmax`, and `tbmin/tbmax`), grouped by transient, long-pulse, and periodic use cases. The remainder is a fully worked case study on **shot 194444** (MPID Bp probe pairs, n=1,2,3 toroidal fit at t=3890.0 ms) that walks through detecting bad data via the fit standard deviation, the `residuals` command, and visual inspection of raw traces, then removing two failed probes (MPID66M067 and MPID66M247, the latter a known-bad probe whose integrator saturated at 10 V) with the `omit`/`add`/`list` commands. The concrete payoff is quantified: omitting the two bad pairs drops the fit standard deviation from 6.00 G to 0.38 G (~10×) while only raising the array condition number from 1.83 to 2.66, still well-conditioned. The document contains verbatim screen output and geometry/residual tables that are valuable ground truth for reproducing both the analysis and the plots, though the actual plot figures are vector graphics whose colors/styling could not be extracted from the PDF.

**Output file:** `docs/research-summaries/07_Slcontour_I_Supp2023.md`
