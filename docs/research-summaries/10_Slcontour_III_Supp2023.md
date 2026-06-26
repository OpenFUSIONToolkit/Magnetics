# SLCONTOUR (III): 2-Axis Arrays — Supplementary Topics

**Source:** `Strait_Magnetics_20230720_Slcontour(III)_Supp.pdf`
**Author / footer:** "E. Strait / DIII-D Magnetics / July 20, 2023" (appears on every page). Title slide also reads "Ted Strait" and "July 20, 2023".
**Length:** 24 pages.
**Producer metadata:** macOS Quartz PDFContext; created/modified 2023-07-20.

> NOTE ON GROUNDING: All plots in this deck are vector graphics. The only raster images embedded in the PDF are the slide-template background and the DIII-D National Fusion Facility logo (confirmed by image extraction on page 11). Therefore all figure descriptions below are reconstructed from the OCR text of the slides, which is fragmented (axis labels, tick numbers and curve labels are interleaved). Where OCR is ambiguous, I say so explicitly and do not invent values.

---

## Document overview

This is a **supplement** to a prior talk, "SLCONTOUR (III): 2-Axis Sensor Arrays" given June 21, 2023. The title slide lists a presentation series (verbatim):
- "(Apr. 20, 2023) SLCONTOUR (I): 1-D Sensor Arrays"
- "(May 3, 2023) SLCONTOUR (II): 2-D Sensor Arrays"
- "(June 21, 2023) SLCONTOUR (III): 2-Axis Sensor Arrays"

It covers "Supplementary Topics (Not presented on June 21)", enumerated on page 1 as:
1. "SLCONTOUR2 version updated"
2. "Relationship of 1-axis and 2-axis analysis"
3. "Spatial averaging by sensors"
4. "SLCONTOUR2 commands for 2-axis analysis"

The deck is organized as four numbered sections matching that list.

---

## Magnetic sensors / hardware

Covered mainly on **page 9** ("(3) 2-Axis Analysis Must Account for Spatial Averaging"). The slide contains a sensor-layout figure (a plot of "Distance along vessel wall (m)" vs "q (deg.)" from 0 to 360) with these labels: "INBOARD", "OUTBOARD", "TOP", "High Field Side", "Low Field Side". The vertical axis ("Distance along vessel wall (m)") shows tick values -2, -1, 0, 1, 2, 3, 4, 5 (OCR order). Text states (verbatim):
- "70 Bp probes (MPI)" — labeled "Bp sensors"
- "64 Br loops (ISL)" — labeled "Br sensors"
- "Br sensors average over a large area"
- "Bp sensors are more nearly point-like"
- "MPI67A layout includes changes in 2020"

Page 22 figure title references the sensor set used for the example contour plots: "174436 2axis Pairs t = 3550.0" (a "2axis Pairs" array).

Page 18/19 name a specific array: "Array = MPISLD_LFS ( 2axis Pairs 2D LFS R0,R1,R2 )".

Sensor types referenced throughout: **Bp probes (MPI)**, **Br saddle loops / loops (ISL)**.

---

## SLCONTOUR / SLCONTOUR2

### Section 1 — Version update (page 2)
- "The most up-to-date version has been renamed 'SLCONTOUR2'"
- "'SLCONTOUR2_TEST' (mentioned in the June 21 presentation) no longer exists"
- "SLCONTOUR is limited to 1-axis arrays"
- "SLCONTOUR2 is the only version that includes 2-axis arrays"
- "SLCONTOUR and SLCONTOUR2 will eventually be combined"

### Section 2 — 2-axis fitting method (pages 3–8)
Describes how SLCONTOUR2 currently fits 2-axis data and argues it could be simplified.
- Present algorithm (page 3, repeated page 8): "1. Direct fit of B_in(θ,φ) and B_ex(θ,φ) to 2-axis measurements of B_r and B_p. 2. Combine the fitted B_in and B_ex results to reconstruct B_r(θ,φ) and B_p(θ,φ)." Page 3 comment: "This approach may have been unnecessarily complicated …"
- Page 8: "The reconstructed B_r(θ,φ) and B_p(θ,φ) are identical to single-axis array results using SLCONTOUR – As expected."
- Page 8 proposed simpler method: "1. Fit B_r and B_p arrays separately, using the same set of (m,n) harmonics. 2. Combine the fitted results to obtain B_in(θ,φ) and B_ex(θ,φ)."
(See "Analysis methods / math" below for the supporting derivation on pages 4–7.)

### Section 4 — New SLCONTOUR2 commands (pages 14–24)
Page 14 lists "Some New Commands" (verbatim command + description):
- `dctype` — "Select Br/Bp or Bin/Bex decomposition (See June 21 presentation for examples)"
- `fittype` — "Special options for Bin/Bex decomposition"
- `mlist` — "Enter a list of poloidal harmonics to fit"
- `mdefault` — "Default list of poloidal harmonics for each array"
- `nplotmin, nplotmax` — "Range of n for plots of amplitude & phase vs. t"
- `plotcoils` — "Show I,C coil locations on the (φ,θ) contour plot"
- `plotprobes` — "Show sensor locations on the (φ,θ) contour plot"
- General usage note (verbatim): "In most cases, typing the command with no value (argument) following it will yield a list of options. Then type the command again with the desired value."

**Command examples shown (verbatim from the interactive prompts; `-->` is the program prompt):**

`dctype` (page 15):
```
--> DCTYPE
Select type of 2-axis decomposition: B_r B_p
1 = B_r B_p
2 = B_in B_ex
--> DCTYPE 2
```

`fittype` (page 16):
```
--> FITTYPE
Select type of 2-axis fit: B_in/B_ex
0 = B_in/B_ex   Arbitrary distribution of internal, external fields
1 = B_in only   Assume all fields are internal-source
2 = B_ex only   Assume all fields are external-source
3 = I-coil      Assume equal amplitudes internal and external
```
Warning (verbatim): "types 1, 2, 3 are for special cases and testing ! Not for normal physics analysis !! In general cases with both internal sources (plasma) and external sources (coils, wall currents) they will give incorrect results."

`mlist` (page 17):
```
—> MLIST 1 3 5
is equivalent to
—> MMIN 1, MMAX 5, MSTEP 2
```
"In this case, both call for fitting m = {1, 3, 5}. But mlist allows an arbitrary set of m values to be entered, not necessarily with equal spacing."

`mdefault` (pages 18–19): output for "Array = MPISLD_LFS ( 2axis Pairs 2D LFS R0,R1,R2 )":
```
--> mdefault   "Educated guess" for a set of m values to fit
Resetting m range: mmin = 1, mmax = 7, mstep = 2   -> New m values may not be optimal
s values = 1 -1
n values = 1 2 3
m values = 1 3 5 7
Condition number = 252.   Fit with this set of m,n is poorly conditioned
**** Fit is poorly conditioned. (Too few probes or too many modes) ****
**** Reduce mode number range or increase mode number step. ****
--> nmax 1   Reduce the range of n
s values = 1 -1
n values = 1
m values = 1 3 5 7
Condition number = 5.38   Fit with this set of m,n is well conditioned
```
Page 19 adds a caveat box (verbatim): "'mdefault' does not include the m>0 trick for 1-D array spatial averaging. Using this command with a 1-D array will set the m value to 0."

`nplotmin, nplotmax` (pages 20–21): "Fitting to multiple n (1, 2, 3) gives a cluttered plot of amplitude and phase vs. time." Then: "--> nplotmin=1, nplotmax=1 • Limits the plot to n=1 only – No effect on fitting." (Pages 20–21 show "amplitude and phase vs. time" plots that are vector graphics; specific axis numbers/ranges are NOT legible in the OCR, so I do not state them.)

`plotprobes` (page 23):
```
--> PLOTPROBES
Plot sensor locations: No
0 = No
1 = Yes
--> PLOTPROBES 0
```

`plotcoils` (page 24):
```
--> PLOTCOILS
Plot coil locations: I-coils
0 = None
1 = C-coils
2 = I-coils
3 = I & C-coils
--> PLOTCOILS 2
```

---

## MODESPEC

**Not covered.** MODESPEC is not mentioned anywhere in this document.

---

## Analysis methods / math

The mathematical content is in sections 2 and 3.

**Cylindrical-harmonic fit (pages 4–7):** Experimental data are fitted to cylindrical harmonics. Verbatim form: "B_r^meas(θ,φ) = Σ_{m,n} b_r(m,n) e^{imθ} e^{inφ} … and similar for B_θ".

**Laplace relation between B_θ and B_r (page 4):** "To satisfy Laplace's equation, B_θ and B_r must be related by b_θ(m,n) = ± i b_r(m,n)", with "'–' applies to internal sources at r<a" and "'+' applies to external sources at r>a".

**Internal/external decomposition (page 4):** "Contributions from internal and external sources for each m,n are found by:" (OCR-fragmented; the slide gives, for m>0)
- b_r^int = (b_r + i b_θ)/2
- b_r^ext = (b_r − i b_θ)/2
- and corresponding b_θ^int, b_θ^ext expressions, with note "Use these eqs for m>0. Flip the signs of i for m<0."
Then: "sum the m,n terms to reconstruct B^int(θ,φ) and B^ext(θ,φ)."

**Equivalence proof (pages 5–8):** Key claims (verbatim):
- "The measurements of B_r and B_θ are independent and orthogonal. – The coefficients b_r(m,n) have no impact on fitting B_θ (and vice versa)."
- (page 5) "Fitting the data set [B_r^meas(θ,φ) ; B_θ^meas(θ,φ)] with coefficients [b_r(m,n) ; b_θ(m,n)] is equivalent to separate fits of data B_r^meas(θ,φ) with coefficients b_r(m,n) and data B_θ^meas(θ,φ) with coefficients b_θ(m,n)."
- (pages 6–7) "Fitting B_r and B_θ is Equivalent to Fitting B^int and B^ext." Internally-sourced field is "a linear combination of B_r and B_θ: B_r^int(θ,φ) = B_r(θ,φ) + i B_θ(θ,φ)" with similar relations for the coefficients.
- (page 7) The least-squares objective for directly fitting B^int to measurements of B_r and B_θ at sensor positions (θ_k, φ_k) is shown to split into two independent sums minimized by individual fits of B_r and B_θ — "QED". Footnote definition: "|A|^2 = A* A".

**Spatial averaging (pages 10–13):**
- Page 10: "Inductive magnetic sensors measure the total magnetic flux through the loop. Calibrated measurements of B represent an average over the sensor area A: B = Φ/A = (∫ B·dA)/A."
- For a harmonic field B(θ,φ) = B_mn e^{imθ} e^{inφ} on a sensor of poloidal width Δθ and toroidal width Δφ, the calibrated measurement equals the desired quantity times a **"Spatial averaging factor"** = [sin(mΔθ/2)/(mΔθ/2)] · [sin(nΔφ/2)/(nΔφ/2)]. Verbatim caveat: "The spatial averaging factor depends on the spatial variation of B, so it cannot simply be included in the calibration factor of the sensor."
- Page 12/13: 2-D array fit prediction includes the averaging factor: "B_pred^k(θ_k,φ_k) = Σ_{m,n} B_mn e^{imθ_k} e^{inφ_k} [sin(mΔθ_k/2)/(mΔθ_k/2)] [sin(nΔφ_k/2)/(nΔφ_k/2)]". "The values of (m,n) enter naturally as part of the 2-D fit."
- Page 12/13 "Problem": "A 1-D array (LFS midplane toroidal array, for example), has no poloidal resolution and consequently no information about poloidal averaging. – But ignoring spatial averaging may lead to inconsistent measured values of Bp and Br."
- Page 13 "Trick": "At present, the best solution is to guess a single m value and enter it by hand --> mmin = 3, mmax = 3 … is often a reasonable value." Cross-check method (verbatim): "Use a stationary MHD mode (f < 10 Hz!) in a similar shot as a rough check – Should show zero wall current B_ext, and consequently equal amplitudes B_p = B_r – Choose the m that minimizes B_ext or minimizes (B_p − B_r)."

---

## Visualizations to reproduce

> All descriptions below are from OCR of vector plots; numeric tick values are reported only where OCR clearly resolves them.

1. **Title-slide contour (page 1):** Contour of "174436 2axis Pairs t = 3550.0", panel labeled "B_p". Vertical axis "Theta (deg.)" with tick labels 90, 45, 0, -45, -90 and edge labels "TOP" (top), "BOT" (bottom); also "OUTBOARD". Horizontal axis "Phi (deg.)" from 0 to 360 (ticks 0, 90, 180, 270, 360). (Color scale not legible on this slide.)

2. **Sensor layout (page 9):** y = "Distance along vessel wall (m)", ticks (OCR) -2,-1,0,1,2,3,4,5; x = "q (deg.)" 0–360 (ticks 0,90,180,270,360). Annotations: INBOARD, OUTBOARD, TOP, High Field Side, Low Field Side. Two sensor sets plotted: "Bp sensors" (70 Bp/MPI probes) and "Br sensors" (64 Br/ISL loops).

3. **Spatial-averaging-factor plots (page 11)** — title "Spatial averaging factors for typical LFS sensor dimensions." TWO panels:
   - **Left: "Poloidal Averaging Factor"** vs x = "m (poloidal mode #)", x ticks 0,1,2,3,4; y ticks (OCR) -0.2, 0.0, 0.2, 0.4, 0.6, 0.8, 1.0, 1.2. Two curves labeled "Bp" (stays near 1.0, small effect) and "Br" (drops; text: B_r → 0 at m ≈ 6).
   - **Right: "Toroidal Averaging Factor"** vs x = "n (toroidal mode #)", x ticks 0,2,4,6,8; y ticks 0.0–1.2. Curves "Bp" and "Br".
   - Note: the two panels share y-range ~ -0.2 to 1.2; OCR mixes the tick lists, but both axes clearly span 0.0–1.2. Curve labels Bp and Br both appear in each panel.

4. **Amplitude & phase vs. time (pages 20–21):** Plots of mode amplitude and phase versus time; page 20 shows the multi-n (n=1,2,3) "cluttered" version, page 21 shows the n=1-only version after `nplotmin=1, nplotmax=1`. Specific axis units/ranges NOT legible in OCR — do not reproduce numeric ranges.

5. **Two-panel B_p / B_r contour plots (pages 22, 23, 24):** Title "174436 2axis Pairs t = 3550.0". Upper panel labeled **"B_p"**, lower panel labeled **"B_r"**. Both panels: vertical axis "Theta (deg.)" ticks 90, 45, 0, -45, -90, with "TOP"/"BOT" at the extremes and "OUTBOARD" marked; horizontal axis "Phi (deg.)" 0–360 (ticks 0,90,180,270,360). **Color/value scale is labeled "Gauss"** with tick values **40, 20, 0, -20, -40** (OCR shows these on the B_r colorbar; the same -40…40 Gauss scale spans both panels). Pages 23–24 are the same plot pair used to demonstrate `plotprobes` (sensor markers on/off) and `plotcoils` (coil-location markers).

---

## Concrete example values (only as they appear)

- **Shot number: 174436** ("174436 2axis Pairs"), at **t = 3550.0** (units not stated on slide; presumably ms) — used for all example contour plots (pages 1, 22, 23, 24).
- Sensor counts: **70 Bp probes (MPI)**, **64 Br loops (ISL)** (page 9).
- "MPI67A layout includes changes in 2020" (page 9).
- Array name: **MPISLD_LFS ( 2axis Pairs 2D LFS R0,R1,R2 )** (pages 18–19).
- `mdefault` example output: m range reset to mmin=1, mmax=7, mstep=2; s values = 1, -1; n values = 1 2 3; m values = 1 3 5 7; **Condition number = 252.** ("poorly conditioned"). After `nmax 1`: n values = 1; **Condition number = 5.38** ("well conditioned"). (pages 18–19)
- `mlist 1 3 5` ≡ `MMIN 1, MMAX 5, MSTEP 2`, fitting m = {1,3,5} (page 17).
- 1-D-array spatial-averaging trick: "mmin = 3, mmax = 3 … is often a reasonable value" (page 13).
- Stationary-MHD cross-check frequency criterion: "f < 10 Hz" (page 13).
- Spatial averaging: "B_r → 0 at m ≈ 6"; Bp averaging "~negligible for m, n ≤ 3" (page 11).
- Color scale on contour plots: **Gauss, ticks -40 to 40** (pages 22–24).
- `fittype` options 0–3; `dctype` options 1 (B_r B_p) / 2 (B_in B_ex); `plotcoils` options 0–3; `plotprobes` options 0–1.

---

## Notable quotes (verbatim, with page #)

- (p.1) "Supplementary Topics (Not presented on June 21)"
- (p.2) "SLCONTOUR is limited to 1-axis arrays" / "SLCONTOUR2 is the only version that includes 2-axis arrays" / "SLCONTOUR and SLCONTOUR2 will eventually be combined"
- (p.3) "This approach may have been unnecessarily complicated …"
- (p.4) "To satisfy Laplace's equation, B_θ and B_r must be related by b_θ(m,n) = ± i b_r(m,n)"
- (p.5) "The measurements of B_r and B_θ are independent and orthogonal."
- (p.7) "But these two sums are minimized by individual fits of B_r(θ,φ) and B_θ(θ,φ) – QED"
- (p.8) "The reconstructed B_r(θ,φ) and B_θ(θ,φ) are identical to single-axis array results using SLCONTOUR – As expected"
- (p.9) "Br sensors average over a large area" / "Bp sensors are more nearly point-like"
- (p.10) "The spatial averaging factor depends on the spatial variation of B, so it cannot simply be included in the calibration factor of the sensor"
- (p.11) "Spatial averaging by Br saddle loops can significantly reduce measured B_r" / "Spatial averaging by Bp probes is a small effect … ~negligible for m, n ≤ 3"
- (p.13) "Trick: At present, the best solution is to guess a single m value and enter it by hand --> mmin = 3, mmax = 3 … is often a reasonable value"
- (p.13) "Use a stationary MHD mode (f < 10 Hz!) in a similar shot as a rough check"
- (p.14) "In most cases, typing the command with no value (argument) following it will yield a list of options. Then type the command again with the desired value."
- (p.16) "types 1, 2, 3 are for special cases and testing ! Not for normal physics analysis !!"
- (p.19) "'mdefault' does not include the m>0 trick for 1-D array spatial averaging. Using this command with a 1-D array will set the m value to 0"
- (p.21) "Limits the plot to n=1 only – No effect on fitting"

---

## Digest (4–6 sentences)

This is Ted (E.) Strait's July 20, 2023 supplement to his June 21 "SLCONTOUR (III): 2-Axis Sensor Arrays" talk, covering four topics the original omitted: a SLCONTOUR2 version/naming update, the equivalence between 1-axis and 2-axis fitting, sensor spatial averaging, and new SLCONTOUR2 commands. Its most distinctive analytic content is a derivation (pages 4–8) proving that fitting a 2-axis (B_r, B_p) array is mathematically equivalent to two independent 1-axis fits and to fitting internal/external (B_in, B_ex) components, via the Laplace relation b_θ = ±i b_r — implying SLCONTOUR2's current "direct B_in/B_ex fit then reconstruct" approach could be simplified to "fit B_r and B_p separately, then combine." It documents the sensor spatial-averaging correction with an explicit sinc-product averaging factor [sin(mΔθ/2)/(mΔθ/2)][sin(nΔφ/2)/(nΔφ/2)], notes Br saddle loops null out near m≈6 while Bp probes are nearly negligible for m,n≤3, and gives a practical "trick" (set mmin=mmax=3, or use a <10 Hz stationary MHD mode as a calibration check) for 1-D arrays that lack poloidal resolution. The final section is a concrete command reference for SLCONTOUR2 — `dctype`, `fittype`, `mlist`, `mdefault`, `nplotmin/nplotmax`, `plotprobes`, `plotcoils` — each shown with verbatim interactive prompts and option menus, plus a worked `mdefault` example showing condition numbers (252 → 5.38) that flag well- vs poorly-conditioned mode sets. All examples use shot 174436 at t=3550.0, contour plots are Theta(deg, -90..90) vs Phi(deg, 0..360) with a Gauss color scale (-40..40); MODESPEC is not mentioned at all in this document.

**Output file:** `docs/research-summaries/10_Slcontour_III_Supp2023.md`
