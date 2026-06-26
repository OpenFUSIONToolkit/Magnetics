# Poloidal Mode Identification Using MODESPEC

**Source PDF:** `resources/DIII-D IDL Command Line Tools/Strait_3DSP_20200803 Poloidal Mode Identification Using MODESPEC.pdf`
**Author / venue:** Ted (E.) Strait, presented at the DIII-D 3D and Stability Physics (3DSP) Meeting, Aug. 3, 2020.
**Length:** 50 pages (PowerPoint export). Pages 44-50 are an "EXTRA SLIDES" appendix.

> Accuracy note: this summary reports only what is actually in the document. PowerPoint-exported text has scrambled word/number order in places (axis labels, equation fragments, table columns interleaved). Where I reconstruct meaning I say so; where a value or label is verbatim I quote it. All figures in this deck are line plots (phase-vs-angle, θ*−θ curves, q(R)/pitch profiles, flux-surface cross-sections); there are no color spectrogram screenshots beyond the standard MODESPEC time-series panels on pp.5 and 19.

---

## Document overview

The talk asks whether DIII-D's MODESPEC poloidal mode-number (m) identification can be improved beyond its simple cylindrical model. The stated goal (p.2) is **"control-room level mode identification – based only on external magnetic data and equilibrium reconstruction."**

Arc of the argument:
1. MODESPEC currently fits a cylindrical model δB(φ,θ) ~ exp[i(mθ − nφ)] using geometrical angles (pp.2, 5).
2. Toroidal n-identification is easy (toroidal symmetry); poloidal m-identification is hard because of toroidicity and shaping (pp.6-8).
3. A "straight field line" coordinate θ* (PEST-like) is proposed to account for toroidicity/shaping, derived three ways: field-line-tracing integral from EFIT, the analytic "Merezhkin correction," and experimental fitting (pp.11-18).
4. Tested on a low-β circular case (146035): the straight-field-line model works well (pp.14-30).
5. Tested on more shaped cases (174446 ITER-like; 182685 high-triangularity QH): the field-line θ* prediction **fails** to match data, even though a θ* *functional-form fit* with free amplitudes works (pp.31-50).
6. Conclusion: cylindrical model is imperfect but often adequate; the physics-based straight-field-line model is **not** consistent with data; the most defensible approach is to fit data to the general θ* functional form, with caution (pp.40-43).

---

## Magnetic sensors / hardware

From p.4 (slide title: *"Mode identification uses poloidal and toroidal arrays of magnetic probes measuring dBp/dt"*):

- **322° poloidal array** ("322° Poloidal Array Mag Probes"): **includes 31 probes**.
  - **"Ideally should resolve poloidal modes up to m ~ 15."**
  - Poloidal positions designated by the **geometric poloidal angle θ**.
  - **Origin at R = 1.695 m, Z = 0.**
- **Outboard midplane toroidal array** ("LFS TOROIDAL ARRAY"): **includes 14 probes**.
- The talk concerns **mainly the poloidal array data**.
- Probes measure **dBp/dt** (poloidal field time derivative). The accompanying figure on p.4 is a poloidal cross-section (Z vs R, roughly 0-3 m in R, −2 to +2 m in Z) showing probe locations around the vessel with θ measured about the origin.

Named individual probe channels appearing in the deck (used as the two MODESPEC reference/comparison probes):
- `MPI66M307D`, `MPI66M340D` (shot 174446, p.5)
- `MPI66M307E`, `MPI66M340E` (shot 146035, p.19)

Coherence behavior (pp.6-7): on the toroidal array all channels have high coherence with the reference; on the poloidal array, **"Probes at the top and bottom have poor coherence vs. the reference at the midplane ⟹ larger error bars."**

---

## SLCONTOUR

**Not covered.** SLCONTOUR is not mentioned anywhere in this document. (This deck is exclusively about MODESPEC and the poloidal-mode-fitting problem.)

---

## MODESPEC (poloidal m identification method)

### Baseline cylindrical model
- Model (p.2): **δB(φ,θ) ~ e^{i(mθ − nφ)}** with geometrical angles φ, θ. Described as "Useful, but oversimplified."
- Mode numbers obtained (p.5) by **fitting the measured phase with a linear dependence on angles φ and θ:**
  Φ(φ,θ) − Φ(φ₀,θ₀)_ref = mθ − nφ  (p.5)
- Toroidal n-fit (p.6): Φ = nφ. **"Excellent fit to model,"** because the toroidal array shows linear phase vs. angular position and high coherence on all channels. Measured amplitude is roughly constant with position → carries no m information.
- Poloidal m-fit (p.7): Φ = mθ. Phase variation is **"only roughly linear with angular position."** Measured amplitude varies strongly with position "for reasons not necessarily related to mode structure," so **"Mode analysis uses only the measured phase"** (amplitude is discarded).

### Why the cylinder fails (p.8)
**"The plasma is not a simple cylinder!"** Asymmetries from toroidicity and shaping → strong variation of the **poloidal wavelength λ**: longer λ at low-field side (LFS), shorter λ at high-field side (HFS), even shorter λ at top and bottom.

### Straight-field-line coordinate θ* (pp.11-13)
- Hypothesis (p.11): *"If the measured δB of a tearing mode is due to perturbed currents on a rational surface, then curves of constant mode phase should be aligned with the magnetic field on the rational surface."*
- Modified poloidal angle θ* gives a linear field-line trajectory within a flux surface: dθ*/dφ = 1/q ⟹ θ* − (n/m)φ = const (reconstructed from scrambled p.12 text; q = m/n at the rational surface). **"Equivalent to PEST coordinates [J.K. Park, 2008]."**
- In (ψ, φ, θ*) the cylindrical expression is valid at the rational surface: **Φ(φ,θ) = mθ* − nφ + Φ₀** (p.12).
- A **linear fit of poloidal-array phase data to Φ(θ) − Φ₀ = mθ*** may give a more realistic m estimate (p.12).
- θ* from a **field-line-tracing integral** (p.13):
  θ*(θ) = 2π · [∫₀^θ dθ·J·R] / [∫₀^{2π} dθ·J·R], using Jacobian J = (∂θ/∂ψ ∂ψ/∂z − ∂ψ/∂θ ∂θ/...) computed from ψ(R,z) from EFIT. Cites [Zohm, 1992; Schittenhelm, 1997]. (The Jacobian expression on p.13 is garbled by extraction; the key point is J built from EFIT ψ(R,z) derivatives in (R,z).)

### MODESPEC `fittype` command (p.41 — concrete software interface)
Slide title: *"Fitting options in MODESPEC – command 'fittype'."* Example call:
`IDL> modespec,shot=182685,t0=4100,dx=10,df=.4`, then sub-command `mode`, then `fittype`.

`fittype` with no argument lists **Poloidal phase fitting options:**
- `0 = No modulation (straight, circular)`
- `1 = m=1 modulation (toroidicity)`  [verbatim has typo "torodicity"]
- `2 = m=1,m=2 modulation (toroidicity & elongation)`

The best-fit amplitudes returned correspond to **λ₁, λ₂** in the talk's notation. The slide shows side-by-side output of `fittype 0` vs `fittype 2` (see Concrete example values), demonstrating that **"Including toroidicity and elongation terms changes the best-fit value of m."**

---

## Analysis methods / math

### How m is fit
- Phase data from the 31-probe poloidal array vs. θ are fit to a linear model in either θ (cylindrical) or θ* (straight-field-line). The slope gives m. Toroidal array fit in φ gives n. Only **phase** is used, not amplitude.
- A "best fit" is chosen by minimizing residual standard deviation (rad.) across candidate m values; the p.41 table lists per-m `stdev (rad.)` with the minimum flagged `*`.

### θ*−θ structure and the Merezhkin correction (pp.16-18, 31-32)
- **θ*−θ varies like sin θ** for toroidicity (pp.16-17).
- Analytic circular-cross-section result [Merezhkin, 1978] (p.17):
  **θ* ≈ θ − λ_M sin θ**, with **λ_M = (a/R)·(2 + Λ)/2** and **Λ = β_P + ℓ_i/2 − 1** (reconstructed from scrambled fragments: "λ = (a/2R)(2 + Λ)", "Λ = β_P + ℓ_i/2 − 1"). Called the **"Merezhkin correction."**
- Toroidicity → **m=1 modulation of B_θ**: stronger at θ = 0 (LFS), weaker at θ = 180 (HFS) (pp.9-10).
- Elongation → **m=2 modulation of B_θ**: stronger at θ = 0, 180; weaker at θ = 90, 270; model **θ* = θ − λ₂ sin 2θ** (pp.10, 31). The "straight tokamak" limit (a/R → 0) separates elongation from toroidicity (p.31): faster variation of θ* (larger dθ*/dθ) in the low-B_p regions at top and bottom.
- General Fourier expansion (pp.32, 40, 42):
  **θ* = θ − λ₁ sin θ − λ₂ sin 2θ + λ₃ sin 3θ + λ₄ sin 4θ + ...**
  with the labeled physical correspondences: **λ₁ = toroidicity, λ₂ = elongation, λ₃ = triangularity, λ₄ = squareness.** λ₁ ≈ λ_M. Analytic expressions for λ₂, λ₃ "have also been proposed" [Zohm, 1992; Testa, 2003] but "appear to differ between the two references, and have not been well tested vs experiment." Up-down-asymmetric (cos θ, ...) terms could be added. The talk uses **only the sin θ and sin 2θ terms** ("Usually sufficient for good fits").
- **λ_M treated as a free variable** (p.18) rather than its predicted flux-surface value, because θ*−θ amplitude varies strongly with flux surface (keeps similar functional form) and non-resonant (kink) response at other surfaces can also affect the amplitude.

### Mode-pitch vs. field-line-pitch test (pp.25-28, 37-39, 50)
- Local field pitch defined (p.25) as **dφ/dθ = ∮q (local analog of safety factor, integrated along B)**; at the midplane → dφ/dθ → (r·B_φ)/(R·B_θ) ∝ a·B_t/(R·B_p).
- The test (p.26-28, 37-39, 50): compare the **measured mode pitch at the wall** to the **EFIT local field-line pitch profile** a·B_t/(R·B_p) across R, checking whether the mode pitch matches the field pitch at the mode's rational surface (q = m/n).
- Effect of Shafranov shift (p.14-15): poloidal variation of field-line pitch. Inboard (θ=180): weaker B_θ/B_φ → smaller dθ/dφ → faster variation of phase dΦ/dθ. Outboard (θ=0): stronger B_θ/B_φ → larger dθ/dφ → slower variation. Φ ∝ θ*.

### Why the prediction fails (p.43)
Most likely explanation: response of the rest of the plasma between the rational surface and the wall. Greatest discrepancy is on the LFS, **"suggesting a stable kink-ballooning response"**; the ideal MHD response need not align with B. Proposed tests: **MARS modeling** of the internal plasma response with a singular current at a rational surface, varying β, q95, elongation; include different radial dependences of spatial harmonics (m±1, m±2,...) added by shaping; check probe orientation relative to plasma surface; consider phase shifts from conducting vessel structures.

---

## Visualizations to reproduce

For the GUI demos, these are the recurring plot types, with axes/units/ranges **as actually shown**:

1. **MODESPEC time-series panel (pp.5, 19)** — multi-stack plot vs **Time (msec)**:
   - Top: raw `dB/dt (T/s)` traces of two probes (p.5 range roughly −400 to 800 T/s; p.19 also shows Ip up to ~1.5×10⁶).
   - `rms dB/dt (T/s)` panel.
   - **Mode Number** panel, y-axis −6 to +6, showing fitted mode-number track over time.
   - **Cross-Power (T²/s²/kHz)** color/log scale (e.g. 1.00e+00 to 1.00e+03 on p.5; 2.00e−01 to 2.00e+01 on p.19).
   - **f (kHz)** spectrogram-style panel, y 0-~15 kHz (p.5) / 0-~10-15 kHz (p.19).
   - p.5 settings annotation: delta-t 4.00 ms, delta-f 0.50 kHz, smoothing 3 pts, mode numbers −5 to 5. p.19: delta-t 10.00 ms, delta-f 0.20 kHz, smoothing 3 pts, mode numbers −5 to 5. On p.19 the mode track is labeled with rational-surface values 4/1, 3/1, 5/1, 6/1, 7/1, 8/1, 9/1 and 7/2, 9/2, 11/2, 13/2.

2. **Toroidal-array fit (pp.6, 23)** — three stacked panels vs **Phi (deg.), 0-270 (to 360)**:
   - **Coherence** (0.0-1.0).
   - **Phase (deg.)** 0-360, linear with φ, fit line Φ = nφ.
   - **Cross-power (T²/s²/kHz)** (e.g. 0-400), roughly flat.

3. **Poloidal-array fit (pp.7, 23, 34-36)** — three stacked panels vs **Theta (deg.), 0-270 (to 360)**:
   - **Coherence** (0.0-1.0), low at top/bottom.
   - **Phase (deg.)** 0-360, with overlaid fit curve (mθ, mθ*, or general θ* fit).
   - **Cross-power (T²/s²/kHz)** strongly varying with θ.

4. **Phase-vs-θ comparison plots (pp.21-22, 46-49)** — single panel, **Phase (deg.) 0-360 vs θ (or Theta deg.) 0-270**, data points with candidate model curves overlaid. Used to contrast cylindrical (mθ) "Clearly wrong!" fits against θ* fits. On p.22, two cases stacked.

5. **θ*−θ curves and flux-surface cross-sections (pp.14, 16-18, 31, 33, 45)** — paired figures:
   - Left/top: **θ*−θ (radians) vs θ (0 to 2π ≈ 0-6)**, sinusoidal, ~−1 to +1.5 rad; sometimes dθ*/dθ overlaid (range ~0-6); curves for several normalized flux surfaces ψ_N (e.g. 0.1, 0.2, 0.5, 0.9, 1.0).
   - Right/bottom: **Z (m) vs R (m)** flux-surface cross-section (R ~1.0-2.4 m, Z ~−1.5 to +1.5 m) plus a **q(ψ) panel** ("curve = eqdsk, squares = θ* calc."), q axis ~1-4 (p.14) up to higher for other shots, vs ψ_N 0-1.

6. **Mode-pitch vs field-pitch profile (pp.26-28, 37-39, 50)** — single panel, **q(R) / d(phi)/d(theta) vs R(m) (1.0-2.5 m)**:
   - q(R) profile from EFIT (symmetric in/out), with edge q labeled at inner and outer walls.
   - **Local field pitch a·B_t/(R·B_p)** ("equilibrium fields") — asymmetric in/out.
   - **Mode pitch** markers at the inner and outer wall to compare against the equilibrium curve at the relevant rational surface.

7. **Fitted-values-vs-time summary (p.24)** — two stacked panels vs **Time (ms), 0-2000** for shot 146035:
   - Top: **m/n** comparison — `q (EFIT)` (range ~0-10), `m/n (mode fit)`.
   - Bottom: **λ amplitude** (~0.0-0.8) — `λ (field integral)`, `λ (mode fit)`, `λ (Merezhkin)`, all "at r=a".

---

## Concrete example values (only those actually appearing)

**Shot 174446** (ITER-like single null):
- p.5: cylindrical-model demo, time window around 3300-3550 ms; best fit **m, n = 2, 1**.
- p.6: toroidal array, **3488-3492 ms, 2.00 kHz, n = 1** ("Excellent fit").
- p.7: poloidal array, same window/freq, **m = 2** (acceptable cylindrical fit).
- p.33: "ITER-like LSN plasma," **q95 = 3.3, β_N = 1.8**; θ*−θ predominantly m=1 & 2; **|θ*−θ| ≤ 0.5 rad ≈ 30° at q=2**. Analysis of **2/1 mode shortly before locking and disruption**; also a **pre-existing 3/2 mode**.
- pp.34-36: **3460 ms, 2.50 kHz**, n=1 mode; best fit **m = 2** with cylindrical θ (even with λ₁ & λ₂ free); locally at inboard wall phase looks like m=3 but inboard/outboard in phase ⟹ m even; **mθ* is a much poorer fit**.
- pp.37-39: EFIT efit02er; edge q = 3.3 (inner & outer); n=1 mode pitch at outer wall ≈ cylindrical 2/1; **n=2 mode pitch at outer wall ≈ 3/2**, very different from field-line pitch at q=2 or q=1.5; no location matches the n=2 mode pitch.

**Shot 146035** (low-β circular reference case):
- p.9: **ε = 0.39, κ = 1.15** (toroidicity m=1 modulation example).
- pp.14-18: EFIT slice 146035.01700; q=3 surface; Shafranov-shift pitch variation.
- p.17 Merezhkin inputs (verbatim): **a = 0.654 m, R = 1.670, β_P = 0.104, ℓ_i = 0.955, κ = 1.145 ⟹ λ_M = 0.62.** Note κ ≠ 1.0 could explain the slight EFIT-vs-analytic difference.
- p.19: Ip ramp, modes with decreasing m/n; rational surfaces 4/1...9/1, 7/2...13/2 (see plot list above); delta-t 10 ms, delta-f 0.20 kHz.
- p.21-22: **1800 ms, 3.00 kHz, m=3**; **1130 ms, 2.60 kHz, m=4**. Cylindrical mθ "Clearly wrong!"; mθ* "significantly better."
- p.23: **540.00-550.00 ms, 8.80 kHz, m = 11** ("Identification is (surprisingly) successful even at high m").
- pp.26-28: EFIT01 slice 146035.01800; edge q=3.0 both walls; 3/1 mode pitch smaller than cylindrical 3 at LFS, larger at HFS; agrees reasonably with local field pitch at q=3.

**Shot 182685** (high-triangularity QH, extra slides):
- p.41: MODESPEC call `shot=182685,t0=4100,dx=10,df=.4`. fittype 0 best fit **m/n = 2/1**; fittype 2 best fit **m/n = 4/1** (table residuals below).
- p.45: "High triangularity QH plasma," **q95 = 5.2, β_N = 1.25**; **|θ*−θ| ≤ 1 rad ≈ 60° at q=4**; analysis of low-frequency n=1 (4/1?) mode late in discharge.
- pp.46-49: **4100 ms, 1.30 kHz**; phase varies strongly with θ; cylindrical m=2 or m=4 poor; **θ* fit with sin θ + sin 2θ fits well**; θ* from field-line integral is a poor fit (poor near outboard midplane θ=0).
- p.50: EFIT02 slice 182685.04100; edge q=5.2 both walls; n=1 mode pitch at outer wall poor match to local field pitch at q=4 (but inner-wall mode pitch does match q=4); n=2 mode pitch at outer wall ≈ 3/2; no location matches.

**fittype residual table (p.41), shot 182685 @ 4100 ms** (verbatim, `*` = best fit):

Toroidal (both fittypes identical):
| n | fit stdev (rad.) |
|---|---|
| 1 | 0.03 * |
| 2 | 1.95 |
| 3 | 1.40 |

Poloidal, `fittype 0` (no modulation):
| m | stdev (rad.) |
|---|---|
| 1 | 1.72 |
| 2 | 0.71 * |
| 3 | 1.59 |
| 4 | 1.05 |
| 5 | 2.09 |
→ Best fit m/n = **2/1**

Poloidal, `fittype 2` (m=1 & m=2 modulation; columns: m, fit stdev, m±1 sideband, m±2 sideband):
| m | stdev (rad.) | m±1 | m±2 |
|---|---|---|---|
| 1 | 1.72 | 0.00 | 0.00 |
| 2 | 0.71 | 0.00 | 0.00 |
| 3 | 1.45 | 0.00 | 0.31 |
| 4 | 0.58 * | 0.15 | 0.20 |
| 5 | 1.18 | 0.56 | 0.00 |
→ Best fit m/n = **4/1**

(This is the key cautionary result: the same data yields m=2 under the circular fit and m=4 once toroidicity+elongation modulation terms are enabled.)

---

## Notable quotes (verbatim, with page numbers)

- p.2: "Goal: control-room level mode identification – based only on external magnetic data and equilibrium reconstruction."
- p.2: "Useful, but oversimplified. Can it be improved?"
- p.2: "However, the mode structure observed at the wall does not always fit the straight field line model — May be influenced by plasma away from the rational surface."
- p.2: "MODESPEC can use additional free parameters to fit a straight field line-like mode structure — Often gives a better fit to measured data — But can add ambiguity to the interpretation."
- p.4: "The 322º poloidal array includes 31 probes – Ideally should resolve poloidal modes up to m~15."
- p.4: "Origin at R=1.695 m, Z=0."
- p.6: "Toroidal mode number identification is simple due to toroidal symmetry."
- p.7: "Poloidal mode identification is more challenging due to geometrical effects (discharge shaping, wall distance, …)."
- p.7: "Mode analysis uses only the measured phase."
- p.8: "The plasma is not a simple cylinder!"
- p.8: "Can the simple model be improved? / Does a better model change the results? / Why does the cylindrical model work at all?"
- p.11: "If the measured δB of a tearing mode is due to perturbed currents on a rational surface, then curves of constant mode phase should be aligned with the magnetic field on the rational surface."
- p.12: "Equivalent to PEST coordinates [J.K. Park, 2008]."
- p.17: "è The 'Merezhkin correction'."
- p.21: "Clearly wrong!"
- p.22: "Θ* fit allows more rapid phase change on HFS."
- p.23: "Identification is (surprisingly) successful even at high m."
- p.30: "What about more interesting plasmas?"
- p.34: "Surprisingly (?) the cylindrical model fits this case well."
- p.35: "But inboard, outboard sides in phase ⟹ m is even."
- p.36: "The straight field line model does not match the data."
- p.39 / p.50: "No location between the magnetic axis and the outer wall has a magnetic field pitch that matches the mode pitch."
- p.40: "A simple cylindrical model is not a good representation of the poloidal mode phase – Although it can give reasonable results in many cases."
- p.40: "Fitting the data to the general functional form of the 'straight field line' model seems to be the most reasonable approach for interpretation of experimental data."
- p.41: "Including toroidicity and elongation terms changes the best-fit value of m."
- p.42: "Warning: Fitting with shaping terms can lead to confusing results – use caution in the interpretation."
- p.43: "The most likely explanation is the response of the rest of the plasma, particularly between the rational surface and the wall... suggesting a stable kink-ballooning response. The ideal MHD response does not need to align with the B field."

---

## Digest (unique content)

This 50-page Strait deck is specifically about the **poloidal (m) side of MODESPEC** and is largely a critical evaluation rather than a how-to: it shows the cylindrical δB ~ exp[i(mθ−nφ)] model, then introduces a PEST-like straight-field-line angle θ* (θ* = θ − λ₁sinθ − λ₂sin2θ + λ₃sin3θ + λ₄sin4θ, with λ₁/λ₂/λ₃/λ₄ = toroidicity/elongation/triangularity/squareness) derived three independent ways (EFIT field-line integral, the analytic Merezhkin correction λ_M = (a/R)(2+β_P+ℓ_i/2−1)/2, and free-parameter fitting). The central, non-obvious finding is that the physics-based straight-field-line model **fails** for shaped plasmas — the wall mode pitch matches the equilibrium field pitch at *no* radius (greatest discrepancy on the LFS, hinting at a stable kink-ballooning response) — even though an empirical θ* fit with free λ₁, λ₂ matches the phase data well. The most operationally important artifact is the `fittype` command (options 0/1/2) and its p.41 residual table for shot 182685, which concretely demonstrates that enabling toroidicity+elongation terms flips the best-fit answer from m/n = 2/1 to 4/1 — hence the explicit warning to use caution. Hardware specifics for a GUI: a 31-probe 322° poloidal array (θ origin at R=1.695 m, Z=0, resolves up to m~15) and a 14-probe outboard-midplane toroidal array, both measuring dBp/dt, with named channels MPI66M307D/340D and MPI66M307E/340E. Concrete cases span low-β circular 146035 (ε=0.39, κ=1.15; m up to 11 at 8.80 kHz), ITER-like 174446 (q95=3.3, β_N=1.8, 2/1 pre-disruption), and high-δ QH 182685 (q95=5.2, β_N=1.25).

**Note:** SLCONTOUR is not mentioned in this document.

---

**Output file:** `docs/research-summaries/03_PoloidalModeID_MODESPEC.md`
