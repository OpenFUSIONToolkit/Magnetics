# Analysis of 2-axis Magnetic Data Using SLCONTOUR

**Source PDF:** `resources/DIII-D IDL Command Line Tools/Strait_3DSPmeeting_20190715 Analysis of 2-axis Magnetic Data  Using SLCONTOUR.pdf`
**Author:** Ted Strait (E.J. Strait)
**Venue:** DIII-D 3D and Stability Physics Meeting (3DSP)
**Date:** July 15, 2019 (note on title slide: "7/24/19: Minor updates to slides 35-39")
**Length:** 39 pages (PowerPoint → PDF). Note: this PDF's text is reliably extractable; values and command syntax below are quoted/transcribed directly from the slide text. Where slide-text layout interleaves figure labels and bullets, axis ranges are reported only where they appear unambiguously as tick/axis labels.

> **Accuracy note:** This summary reports only what is literally present in the extracted slide text. Many slides marked their own figures "Figure is for illustration only. Some details may not be accurate." — that disclaimer is reproduced where it appears. Plot axis ranges are inferred from numeric tick labels embedded in the text stream and are flagged as such; exact color scales are NOT stated in text (see Visualizations section).

---

## Document overview

A talk describing a **major upgrade of the SLCONTOUR IDL analysis tool** (the new version is called **SLCONTOUR2**) to handle **2-axis magnetic data** — i.e., simultaneous fitting of radial (Br) and poloidal (Bp) magnetic field measurements. The key new capability is **Gauss' algorithm**, which decomposes measured 3D magnetic field data into **internally sourced (B_in)** and **externally sourced (B_ex)** contributions.

Stated purposes (p.2, verbatim bullets):
- "Describe a major upgrade of SLCONTOUR for 2-axis data — Gauss' algorithm for decomposition of magnetic field data into contributions from internal and external sources"
- "Demonstrate the application of this tool to DIII-D data — Locked mode → Distinguish plasma mode / induced wall currents; C-coil field → Distinguish plasma response / driving perturbation; I-coil field"
- "Discuss briefly the possible application to disruption warning — Candidate for use in DIII-D ONFR system?"

The talk is organized as: motivation/background (pp.1-8), three worked examples (Example #1 locked mode pp.9-15; Example #2 C-coil vacuum field pp.16-21; Example #3 I-coil vacuum field pp.22-31), disruption-warning discussion (pp.32-33), conclusions (p.34), and EXTRA SLIDES giving "How to use SLCONTOUR2" (pp.35-39).

**References cited (p.3):**
- J.D. King et al., "An upgrade of the magnetic diagnostic system of the DIII-D tokamak for nonaxisymmetric measurements," RSI 85, 083503 (2014).
- E.J. Strait et al., "Spatial and temporal analysis of DIII-D 3D magnetic diagnostic data," RSI 87, 11D423 (2016).
- E.J. Strait, "A brief summary of the SLCONTOUR analysis tool for 3D magnetics," 3DSP Meeting slides (Feb. 4, 2019).
- R.M. Sweeney and E.J. Strait, "Decomposing magnetic field measurements into internally and externally sourced components in toroidal plasma devices," Phys. Plasmas 26, 012509 (2019).
- E.J. Strait and R.M. Sweeney, "Separating internal and external sources of measured 3D magnetic fields," Friday Science Meeting slides (Aug. 17, 2018).

---

## Magnetic sensors / hardware

From p.4 ("DIII-D '3D' magnetic diagnostics provide 2-axis measurements over most of the wall"):
- "n ≤ 3 resolution at 5 poloidal locations; n ≤ 4 at Low Field Side midplane"
- "Sensors are connected in differential pairs to eliminate n=0"
- "m resolution up to at least 6 is provided by 15 poloidal locations"
- Diagnostic counts shown on the figure: **66 Bp probes**, **64 Br loops**.
- The p.4 figure axes (from text labels): vertical axis "Distance along vessel wall (m)" with tick values spanning roughly -2 to 5 m; horizontal axis "φ (deg.)" 0 to 360. Poloidal region labels shown: INBOARD, HFS, TOP, LFS, OUTBOARD.

From Example #1 (p.9, "This example uses all of the in-vessel '3D' arrays"):
- "130 sensors making 114 differential pairs"
- Pair counts table (verbatim):
  - LFS: Br = 32, Bp = 34
  - HFS: Br = 24, Bp = 24

Sensor surfaces are referred to by labels **R-2, R-1, R0, R+1, R+2** (poloidal rows), e.g. "Br peak at R0 surface (LFS midplane), ±Bp peaks at R±1 surfaces" (p.18).

---

## SLCONTOUR (focus: 2-axis = 2D toroidal + poloidal analysis)

### Basis set / fitting model
SLCONTOUR fits the data to a "simple basis set" of cylindrical Fourier harmonics (pp.5-6):

> "δB(φ,θ) = Σ b_nm exp(inφ − imθ)   cylindrical Fourier harmonics in φ and θ"
> "For differential pairs, the basis functions are actually field differences"
> "These basis functions are a device for fitting periodic data. They do not necessarily correspond to plasma modes." (verbatim, p.5/p.6)

Here φ = toroidal angle, θ = poloidal angle. The 2D contour plots are therefore Theta (deg.) vs Phi (deg.) maps — the "2-axis" / 2D toroidal+poloidal representation.

### Existing (pre-upgrade) capability (p.6)
- "2/1 locked mode fit to 66 Bp probes — n=1, 2  m=1, 2, 3, 4, 5"
- Open question motivating the upgrade: "But how much of the field is generated by the plasma?"

### New algorithm — basis functions indexed by source location (p.8)
> "Basis set: Cylindrical Fourier harmonics in φ and θ, indexed by (m, n, s). At the observation surface:
> δB_r(φ,θ) = Σ b_snm exp(inφ − ihmθ)
> δB_θ(φ,θ) = Σ −ihps b_snm exp(inφ − ihmθ)"

Index definitions (verbatim, p.8):
- "s = ±1 indexes the source location: internal / external"
- "h = ±1 is dominant helicity of the harmonics: right / left handed"
- "p = m / |m| = ±1"
- "Positive m ⟺ harmonics with dominant helicity"
- "δB_θ and δB_r data are fit simultaneously to the functions above, to yield b_snm = (m,n) amplitudes of B_r^int (s=+1) and B_r^ext (s=-1)"
- "B_θ and B_r can be recovered by linear combinations of B_r^int and B_r^ext"

### SLCONTOUR2 — status and how to use (EXTRA SLIDES, pp.35-39)

**Status (p.36):**
- "SLCONTOUR2 includes all the functionality of the existing SLCONTOUR."
- "2-axis analysis is applied automatically when a 2-axis array is selected. No special command or setup is needed."
- "SLCONTOUR2 is still under development. There may be bugs in the new features, or in the old features. → Please notify me of any problems"
- "When SLCONTOUR2 is stable, the two versions will be merged."

**Launch sequence (p.37, verbatim):**
```
$ module load slcontour      (Set the environment; or include this line in .cshrc)
$ idl                        (Launch idl)
IDL> slcontour2              (Run slcontour2)
```
"For an introduction to SLCONTOUR and basic commands, please see ... E.J. Strait, 3DSP Meeting slides (Feb. 4, 2019)."

**New SLCONTOUR2 commands related to 2-axis data (p.38, verbatim):**
```
--> find 2axis          List 2-axis arrays
--> dctype = #          Decomposition type
                          1 = Bp / Br (default)
                          2 = B_in / B_ex
--> fittype = #         Type of internal/external fit
                          0 = B_in / B_ex (default)
                          1 = B_in only
                          2 = B_ex only
                          3 = B_in/B_ex with I-coil correction*
        *valid only if I-coils are the only external source of n≠0 field
```

**New SLCONTOUR2 commands for general purposes (p.39, verbatim):**
```
--> plotprobes = #      Show sensors on 2D contour plot
                          0 = No   1 = Yes (default)
--> plotcoils = #       Show coils on 2D contour plot
                          0 = None (default)  1 = C-coils
                          2 = I-coils         3 = C- and I-coils
--> mlist = # # # # #    Enter arbitrary list of m's to fit
--> mdefault            Use a default list of m's to fit, depending on the current array.
```
Also noted (p.39): "mmin2, mmax2, mstep2 — These commands have been dropped in SLCONTOUR2."

> Note: The `find 2axis`, `dctype`, `fittype`, `plotprobes`, `plotcoils`, `mlist`, `mdefault` syntax and option values above are transcribed exactly from the slides. No other command syntax is given in the document.

---

## MODESPEC

**Not covered.** The string "MODESPEC" does not appear anywhere in this document. (This talk is exclusively about SLCONTOUR / SLCONTOUR2. The other legacy tools named in the project brief — MODESPEC and OMFIT magnetics — are not discussed here.)

---

## Analysis methods / math

### Gauss' algorithm — physical principle (p.7)
> "Phase shifts distinguish the location of sources with respect to an observation surface."
> "Sinusoidally varying field: the normal (B_r) and tangential (B_θ) components have a 90º phase shift. Sign of the phase shift depends on the location of the source." (verbatim, p.7)

For a field represented by a sum of cylindrical harmonics, with an observation surface at r = a, the internal/external contributions for each (m,n) are (p.7, as written):
> "b_int = (b_r + i b_θ)/2 ,  with B_θ = (r/φ) B_r" and "b_ext = (b_r − i b_θ)/2"

(The slide text mangles the layout of these formulas; the clear content is the two combinations b_int = (b_r + i b_θ)/2 and b_ext = (b_r − i b_θ)/2.)

### Spatial-resolution trade-off (pp.14-15)
- "In general, there is no benefit in spatial resolution — Br & Bp data → 2x data measurements, but Bin & Bex analysis → 2x degrees of freedom to fit"
- "IF Bin or Bex can be ignored (e.g. after locking), then 2x measurements are available to fit the other"
- p.15: "In this example, with 1 ≤ m ≤ 6, fitting to Bin only allows a well-conditioned fit with n ≤ 3 — Fitting to both Bin & Bex allows only n=1"

### Coils in the measurement surface — degenerate case (pp.26-29)
- "When coils are located in the measurement surface, B_in / B_ex decomposition → equal amplitudes of each. Occurs when measured tangential field is zero — Reinforced by location of Bp probes at nodes of Bp."
- "B_θ = 0 leads to B_int = B_ext = B_r/2", with b_int = b_r/2, b_ext = b_r/2.
- Simple correction (p.28, verbatim): "Valid when the I-coil is the only external source of n=1 field.
  Assume: B_in = B_plasma + B_(I-coil)^meas / 2 ;  B_ex = B_(I-coil)^meas / 2.
  Then: B_plasma = B_in^meas − B_ex^meas ;  B_(I-coil) = 2 B_ex^meas."

### Spatial aliasing of the I-coil field (pp.22-25, 30-31)
- "The I-coils create additional challenges for Gauss' algorithm: 1. The coils are at the measurement surface, not clearly outside or inside. 2. The Bp probes are located at nodes of the Bp field: measured Bp is ~zero. 3. The LFS magnetic arrays cannot resolve the spatial structure of the I-coil field."
- "From R-2 to R+2, the field of the I-coil includes ~3 periods of Br variation (m ~ 6) — 5 rows of magnetic sensors from R-2 to R+2 can resolve only ~2.5 periods of Br variation → Result: Spatial aliasing!"
- "Solutions exist for these problems, but only under some conditions."

---

## Visualizations to reproduce

> **Color scale caveat:** The slide text does NOT specify the colormap names or explicit color-scale limits as words. What appears in the text stream are the numeric **colorbar tick labels** beside each 2D contour figure (e.g. a vertical sequence like 10/5/0/−5/−10). I report those tick values as the apparent contour scale range, but the exact colormap is not stated and should not be invented.

### 1. Paired 2D toroidal–poloidal contour maps (B_ex / B_in stacked), title slide & pp.12-13
- Two stacked contour panels labeled **B_ex** (top) and **B_in** (bottom), both tagged "Gauss".
- Each panel: x-axis "Phi (deg.)" 0–360 (ticks 0, 90, 180, 270, 360); y-axis "Theta (deg.)" with ticks -90, 0, 90, 180, 270 and poloidal-region labels BOT / INBOARD / TOP / OUTBOARD / BOT around the θ axis.
- Title text: "163060 2axis Pairs t = 2740.0".
- Colorbar tick labels shown: 10, 5, 0, −5, −10 (units Gauss). Caption (pp.12-13): "Spatial distribution shows m/n=2/1 mode structure."

### 2. Br/Bp decomposition at LFS midplane — Example #1 (p.10)
- Header: "Shot 163060 MPISLD_ALL 2axis Pairs  solid/square = B_r  dash/diamond = B_p".
- Multiple sub-plots:
  - A **fit-vs-sensor scatter** ("Sensor data" vs "Fit", "Measured") with axes spanning about −30 to 30 (delta-B, G); legend "m = 1 2 3 4 5 6", "n = 1".
  - A **Phase (deg) plot** with vertical axis ticks 0..300 (range ~ -10 to 300+).
  - A **time history** "delta-B (G)" vs "Time (ms)" from 2700 to 2800 ms, with curves labeled Bp and Br and an event marker "Locking"; vertical range ~0 to 40 G.
  - A **toroidal profile** "delta-B (G)" vs "Phi (deg.)" (0–360) at "t=2740.0, Theta=0.0", curves B_p and B_r.
- Caption: "Br is 'shielded' during mode rotation, then 'penetrates'."

### 3. B_in/B_ex decomposition time/space — Example #1 (p.11)
- Header: "shot 163060 MPISLD_ALL 2axis Pairs  solid/square = B_in  dash/diamond = B_ex".
- Sub-plots analogous to p.10: fit/measured scatter (±30 G); Phase (deg) panel; time history "delta-B (G)" 2700–2800 ms with "Locking" marker, curves B_in and B_ex, vertical ticks 0..30; toroidal profile at "t=2740.0, Theta=0.0" with B_ex and B_in curves (Phi 0–360).
- Caption: "Wall field mirrors mode during rotation, then decreases."

### 4. Constrained-fit demonstration — Example #1 (pp.14-15)
- "Shot 163060 MPISLD_ALL 2axis Pairs", "t=2780.0, Theta=0.0".
- Legend "m = 1 2 3 4 5 6", "n = 1 2 3".
- p.14 note on figure: "B_ex is constrained to be zero in this fit." Stacked B_ex/B_in toroidal profiles (Phi 0–360); time history 2700–2800 ms; scatter ±30.
- p.15 adds a **Condition Number plot**: y-axis "Condition Number" (ticks 0,10,20,30,40), x-axis "n (max)" (0..4 / 0..3), two curves "Fit Bin & Bex" and "Fit Bin only".

### 5. C-coil example fit & contours — Example #2 (pp.17-21)
- Header (p.17): "176317 MPISLD_ALL 2axis Pairs  solid/square = B_in  dash/diamond = B_ex".
- p.17 scatter: legend "m = -3 -2 -1 0 1 2 3", "n = 1", axes "Sensor data"/"Fit"/"Measured" spanning −40 to 40.
- pp.18-19 contour pair: stacked **B_p** (top) and **B_r** (bottom) "Gauss"; title "176317 2axis Pairs t = -200.0"; Phi (deg.) 0–360, Theta (deg.) (-90..270 with BOT/INBOARD/TOP/OUTBOARD); colorbar ticks 40, 20, 0, −20, −40 (G). Caption: "Br peak at R0 surface (LFS midplane), ±Bp peaks at R±1 surfaces."
- p.19 adds an **m-spectrum bar chart**: y-axis "δB (G)" (ticks 0,4,8,12), x-axis "m" (-3..3), bars for Br and Bp. Caption: "Spectrum is symmetric with respect to ±m."
- pp.20-21 contour pair: stacked **B_ex** (top) / **B_in** (bottom) "Gauss"; same title/axes; colorbar ticks 40,20,0,−20,−40 (G). p.21 also shows a **poloidal/phase line plot** "delta-B (G)" (−60..60) at "t=-200.0, Phi=65.0" with curves Bin and Bex. Caption: "B_in / B_ex decomposition correctly identifies the C-coil field as entirely from external sources — Separation of B_in and B_ex is accurate to about 10% — Fitted B_in is < 5G."
- All Example #2 slides carry the disclaimer: "Figure is for illustration only. Some details may not be accurate."

### 6. I-coil example fits & contours — Example #3 (pp.24-31)
- Title across these: "162627 2axis Pairs t = 400.0".
- pp.24-25: stacked **B_p** / **B_r** contour panels (TOP/OUTBOARD poloidal labels, Theta ticks -90,-45,0,45,90; Phi 0–360) plus a fit/measured scatter (legend "m = -6 -4 0 4 6", "n = 1"; axes about −60..40 for Bp and −100..100 for Br "delta-B (G)"). p.25 annotates the B_r panel "Not justified by data alone." Caption: "Restricting the fit to higher m (±4, ±6) yields a plausible fit for the I-coil vacuum field [here: n=1, 240º quartets]."
- p.27, p.29: stacked **B_ex** / **B_in** contour panels; p.29 colorbar ticks ~100/50/0/−50 (B_ex) and a similar split for B_in. Caption (p.29): "Separation of B_in and B_ex is accurate to ~10%."
- pp.30-31: full stacked **B_ex** / **B_in** contour pair (INBOARD/TOP/OUTBOARD/BOT poloidal labels; Phi 0–360; Theta -90..270); colorbar ticks 100, 50, 0, −50, −100 (G). Caption: "Gauss' algorithm separates B_in / B_ex even with spatial aliasing — Despite poor reconstruction of I-coil field." p.31 sidebar lists the fit recipe (see Notable quotes).

### 7. Disruption-warning time-series — pp.32-33 (shot 163060)
- Top panel: y-axis quantities "βN" and "I_P (MA)" (ticks 0.0, 0.5, 1.0, 1.5, 2.0); label "163060".
- Middle panel: "δB (Gauss)" (ticks 0..50) with curves B_in and B_ex.
- Bottom panel: "δB (Gauss)" (ticks 0..50) with traces labeled "n1rms" and "dusbradial".
- All three share x-axis "Time (ms)" from 2000 to 3200.

---

## Concrete example values (only as they appear)

- **Shot 163060** — Example #1 (rotating → locked mode), MPISLD_ALL 2axis Pairs.
  - Spatial snapshots at **t = 2740.0** (ms); also **t = 2780.0** for the constrained-fit slide.
  - Time histories span **2700–2800 ms** (Examples) and **2000–3200 ms** (disruption-warning slides).
  - Mode identified as **m/n = 2/1**; harmonics fit "m = 1 2 3 4 5 6", "n = 1" (and n = 1 2 3 on pp.14-15).
  - "Theta = 0.0" for the LFS-midplane line plots.
  - 130 sensors / 114 differential pairs; LFS Br=32, Bp=34; HFS Br=24, Bp=24.
- **Shot 176317** — Example #2 (C-coil vacuum field), MPISLD_ALL 2axis Pairs.
  - Time **t = -200.0** (ms); line plot at "Phi = 65.0".
  - C-coil "applies an n=1 horizontal field at the midplane."
  - Fit uses "-3 ≤ m ≤ 3" with n = 1; "Fitting with n=1 helical harmonics requires equal amplitudes of positive & negative m."
  - "Separation of B_in and B_ex is accurate to about 10%"; "Fitted B_in is < 5G."
- **Shot 162627** — Example #3 (I-coil vacuum field), 2axis Pairs.
  - Time **t = 400.0** (ms).
  - Higher-m fit: "m = -6 -4 0 4 6", n = 1, "240º quartets."
  - Full-set fit recipe (p.31): "n = 1, 0 ≤ m ≤ 6."
  - "Separation of B_in and B_ex is accurate to ~10%."
- **Disruption-warning candidate sensor set (p.33):** "Full R0 arrays; 3 Br, 3 Bp pairs at R+1 and R-1; Can resolve n = 1, m = 2, 4, 6."
- Field-amplitude scales appearing on plots (from tick labels): roughly ±10 G (locked-mode contours), ±40 G (C-coil contours and scatter), ±100 G (I-coil contours/scatter), 0–50 Gauss (disruption-warning δB traces).

---

## Notable quotes (verbatim, with page numbers)

- (p.1, title) "Analysis of 2-axis Magnetic Data Using SLCONTOUR — by Ted Strait — DIII-D 3D and Stability Physics Meeting — July 15, 2019"; title-slide note "7/24/19: Minor updates to slides 35-39".
- (p.2) "Describe a major upgrade of SLCONTOUR for 2-axis data – Gauss' algorithm for decomposition of magnetic field data into contributions from internal and external sources"
- (p.2) "Discuss briefly the possible application to disruption warning – Candidate for use in DIII-D ONFR system?"
- (p.5) "These basis functions are a device for fitting periodic data. They do not necessarily correspond to plasma modes."
- (p.6) "But how much of the field is generated by the plasma?"
- (p.7) "Phase shifts distinguish the location of sources with respect to an observation surface"
- (p.7) "the normal (B_r) and tangential (B_θ) components have a 90º phase shift  Sign of the phase shift depends on the location of the source"
- (p.10) "Br is 'shielded' during mode rotation, then 'penetrates'"
- (p.11) "Wall field mirrors mode during rotation, then decreases"
- (pp.12-13) "Spatial distribution shows m/n=2/1 mode structure"
- (p.14) "B_ex is constrained to be zero in this fit"
- (p.15) "In this example, with 1 ≤ m ≤ 6, fitting to Bin only allows a well-conditioned fit with n ≤ 3 – Fitting to both Bin & Bex allows only n=1"
- (p.16/17) "The C-coil applies an n=1 horizontal field at the midplane – No plasma → B_int = 0: should detect only an external field"
- (pp.16-21, recurring) "Figure is for illustration only. Some details may not be accurate."
- (p.20/21) "B_in / B_ex decomposition correctly identifies the C-coil field as entirely from external sources – Separation of B_in and B_ex is accurate to about 10% – Fitted B_in is < 5G"
- (p.23) "Result: Spatial aliasing!" and "Solutions exist for these problems, – but only under some conditions."
- (p.25) "Not justified by data alone"
- (p.26) "When coils are located in the measurement surface, B_in / B_ex decomposition → equal amplitudes of each • Occurs when measured tangential field is zero"
- (p.30/31) "Gauss' algorithm separates B_in / B_ex even with spatial aliasing • Procedures outlined here successfully separate B_in, B_ex – Despite poor reconstruction of I-coil field"
- (p.31) "Requires that I-coils are the only (time-varying) external n=1 source"
- (p.32) "Just one signal – no handoff from Mirnov to LM detector – Single calibration reduces ambiguity in thresholds"
- (p.34) "Analysis of rotating and locked modes seems to work well – Candidate for use in DIII-D ONFR system?"
- (p.34) "C-coil: should work well / I-coil: OK, with limitations" and "Conclusions from vacuum field data: Testing with plasma data still needed."
- (p.36) "2-axis analysis is applied automatically when a 2-axis array is selected. No special command or setup is needed."
- (p.36) "SLCONTOUR2 is still under development. There may be bugs in the new features, or in the old features."

---

## Digest (unique content)

This 2019 talk by Ted Strait documents the SLCONTOUR → **SLCONTOUR2** upgrade, whose defining new feature is **2-axis fitting**: simultaneously fitting radial (Br) and poloidal (Bp) field data to cylindrical Fourier harmonics indexed by (m, n, s), where **Gauss' algorithm** uses the 90° phase relationship between normal and tangential field components to split the field into **internal (B_in, plasma/mode) and external (B_ex, wall-current/coil) sources**. Three real DIII-D examples ground the method: a rotating→locked **m/n = 2/1 mode (shot 163060, t≈2740–2780 ms)** showing Br "shielded then penetrating" and wall field "mirroring then decreasing"; the **C-coil vacuum field (shot 176317, t=-200 ms, n=1, -3≤m≤3)** correctly identified as ~100% external (B_in <5 G, ~10% accuracy); and the harder **I-coil vacuum field (shot 162627, t=400 ms)** where the coil sits in the measurement surface and the Bp probes lie at field nodes, causing spatial aliasing — addressed by an equal-split correction (B_plasma = B_in − B_ex, B_I-coil = 2·B_ex) valid only when the I-coil is the sole external n≠0 source. The talk proposes Gauss' algorithm as a single-signal **disruption-warning / ONFR** detector and the EXTRA SLIDES give the exact SLCONTOUR2 invocation (`module load slcontour` → `idl` → `slcontour2`) and new commands (`find 2axis`, `dctype`, `fittype`, `plotprobes`, `plotcoils`, `mlist`, `mdefault`; with `mmin2/mmax2/mstep2` dropped). Note that **MODESPEC is not mentioned anywhere** in this document, and several example figures carry the author's own disclaimer that they are "for illustration only."

---

*Summary written to: `docs/research-summaries/05_SLCONTOUR_2axis2019.md`*
