# Strait HTPD 2016 Poster — Analysis of DIII-D "3D" Magnetic Diagnostic Data

**Source file:** `resources/Magnetics Hardware and Analysis Overviews/Strait HTPD poster 2016 Analysis of DIII-D 3D Magnetic Diagnostic Data.pdf`

> ACCURACY NOTE: Every value, label, caption, and quote below is transcribed directly from the PDF text layer and/or read off the rendered figure images (pages 5, 7, 11, 21, 22, 24, 25). Where the auto-extracted text was garbled (this is a PowerPoint-to-PDF export with overlapping text runs), I reconstructed numbers from the figure images and flag any remaining uncertainty explicitly. Items genuinely absent are marked "not covered."

---

## Document overview

- **Title:** "Analysis of DIII-D '3D' Magnetic Diagnostic Data" (page 1).
- **Authors (page 1):** E.J. Strait¹·* , J.D. King¹, J.M. Hanson², N.C. Logan³.
  - ¹ General Atomics, San Diego, CA 92186
  - ² Columbia University, New York, NY 10027
  - ³ Princeton Plasma Physics Laboratory, Princeton, NJ 08543
  - "*Present Address: Office of Science, USDOE, Germantown, MD 20874"
- **Venue:** "Presented at the High Temperature Plasma Diagnostics Conference, Madison, Wisconsin, June 6-10, 2016." (page 1)
- **Format:** 35-page PDF. It is a **poster rendered as a slide deck** (PowerPoint export, CreationDate 2016-05-29). Footer on every content page reads "E. Strait / HTPD / June, 2016." Numbered section dividers appear: (1) INTRODUCTION (p3), (2) SIGNAL CONDITIONING (p8), (3) SYNCHRONOUS DETECTION (p14), (4) SPATIAL FITTING (p18), (5) SINGULAR VALUE DECOMPOSITION (p23), (6) COMPARISON TO MODELS (p27), (7) CONCLUSIONS (p32).
- **Abstract (page 2):** describes a recent upgrade [ref 1] enabling measurement of non-axisymmetric ("3D") features; "Two-axis measurements at approximately 64 locations provide the amplitude and spatial structure of plasma asymmetries." States 3D fields of interest are "typically 10⁻³ to 10⁻⁵ of the total axisymmetric magnetic field." Outlines the toolkit: differential measurements, spatial toroidal Fourier analysis, poloidal Fourier (caveated), SVD, synchronous detection, compensation for direct coil coupling. "such techniques can successfully isolate plasma signals with amplitudes well below one Gauss."
- **Key cited references in abstract:** [1] J. D. King, E. J. Strait, et al., Rev. Sci. Instrum. 85, 083503 (2014); [2] J. D. King, E. J. Strait, et al., Phys. Plasmas 22, 072501 (2015).
- **Physics objectives (page 4):** identification of unstable plasma modes (poloidal structure of non-rotating MHD modes); plasma response to external 3D fields (stable kink response to RMP coils, error fields); 3D equilibrium reconstruction. Additional arrays (not highlighted) provide toroidally/poloidally resolved dB/dt of rotating modes & transient events, and toroidal averaging to minimize n=1 effects in axisymmetric equilibrium reconstruction.

---

## Magnetic sensors / hardware

This is the central hardware content. The flagship figure is **page 5** ("DIII-D '3D' Magnetic Diagnostics Provide 2-axis Measurements Over Most of the Wall").

**Sensor counts and types (page 5, verbatim labels):**
- **"66 Bp probes"** (legend: short red bars = Bp probes).
- **"64 Br loops"** (legend: blue rectangular outlines = Br loops).
- Bullets (page 5):
  - "n ≤ 3 resolution at 5 poloidal locations; n ≤ 4 at Low Field Side midplane"
  - "Single-n detection (amplitude & phase) at 15 poloidal locations"
  - "– 14 cm poloidal resolution at High Field Side"

**Page-5 layout figure (read from the rendered image):**
- **X-axis:** φ (deg.), 0 to 360.
- **Y-axis:** "Distance along vessel wall (m)", range −2 to 5 (gridlines at −2,−1,0,1,2,3,4,5).
- Right-edge region labels stacked top-to-bottom: **INBOARD**, **HFS**, **TOP**, **LFS**, **OUTBOARD**. Dashed horizontal lines separate the regions (visible dashes near ~5, ~2.5, ~1.7, ~−1.6 m).
- **HFS / INBOARD band (upper, ~3 to ~4.5 m):** rows of blue Br loops each containing red Bp probes; toroidally spaced. Two φ locations (around ~150° and ~190°) have tall vertical stacks of several co-located loop+probe units (the inner-wall poloidal arrays), while the rest of the inboard band is a sparser toroidal ring of loop+probe pairs.
- **LFS midplane (~1.5–1.7 m):** a toroidal row of stand-alone red Bp probes (with small blue marks).
- **OUTBOARD band (~ −1.5 to +1 m):** three horizontal rows of large blue Br loops spanning φ, with red Bp probes distributed across/within them — this is the outboard saddle-loop / poloidal-field-probe coverage.
- Net visual impression: dense 2-axis (Br + Bp) coverage over essentially the full poloidal extent of the wall, with toroidal arrays at several poloidal locations.

**Inner-wall toroidal arrays (page 6, "Inner Wall Toroidal Arrays: Co-located Br & Bp sensors"):**
- "Two toroidal arrays, 8 Br-Bp combinations per array."
- Figure shows a Br sensor and a Bp sensor co-located (labels "Br" and "Bp").

**Differential pairs / connection scheme (page 10, "Differential Pairs of Sensors Reject n=0 Field"):**
- "All '3D' sensors are connected in toroidally separated pairs: ΔB = B(φ₁) – B(φ₂)."
- "Some are also acquired individually for n=0 field." ("Adjustable balance" annotation on the circuit; ΔB(φ₁,φ₂) feeds an integrator ∫dt.)
- "Variable toroidal separation minimizes spatial degeneracy for multiple n values."
- **"LFS midplane Bp array: 77º ≤ Δφ ≤ 180º"**
- **"Other arrays: 15º ≤ Δφ ≤ 180º"**
- Figure: "Differential pair connections for LFS midplane toroidal array," shown on a polar (φ) diagram with 0/90/180/270 marks.

**Integration / digitization rates:** NOT explicitly stated as numeric sample rates anywhere in this poster. The hardware shows integrators (∫dt) on the differential pairs (page 10). Digitization rate per se is **not covered** (the abstract and page 9 note that kHz time-domain Fourier works for fast modes but the quasi-static perturbations require spatial methods). Any specific kHz digitizer numbers should be sourced from ref [1] King RSI 85, 083503 (2014), not from this poster.

**Vertical (poloidal) resolution specifics, HFS inboard array (page 22):**
- "Vertical resolution δZ = 14 cm, δθ ~11º → maximum m ~ 16"
- "Vertical range ΔZ = 152 cm, δθ ~93º → minimum m ~ 4"

---

## SLCONTOUR

**Not covered.** The tool/name "SLCONTOUR" does not appear anywhere in this document. (The φ–θ contour plots on pages 7, 21, 22 are the conceptual analog — color contour maps of δBp over toroidal/poloidal angle — but the poster never names SLCONTOUR.)

## MODESPEC

**Not covered.** "MODESPEC" does not appear in this document. (The toroidal-array fit to multiple n harmonics on page 20, and the SVD on pages 25–26, are the conceptual analogs of mode-spectrum analysis, but the tool is not named.)

---

## Analysis methods / math

**Challenges → solutions table (page 9, "Measurement of 3D Tokamak Fields is Challenging"):**
- Small signal vs. large axisymmetric field (δB/B₀ ~ 10⁻⁴) → differential measurements from toroidally spaced sensor pairs; signal averaging.
- Low S/N (~0.1 or less) → synchronous detection; multiple-sensor arrays.
- Direct pickup from non-axisymmetric coils → subtract static contributions; compensate time-varying signals in frequency or time domain.
- Wide range of possible toroidal/poloidal mode numbers but limited number of sensors → spatial fit to a limited set of basis functions; use a priori knowledge in selecting basis functions.

**Compensation for direct coil coupling (pages 12–13):**
- For DC or fixed-frequency AC coil currents: single no-plasma measurement of coefficients A_sc for sensor s & coil c:
  - B_{s,plasma} = B_{s,meas} − B_{s,vacuum}, with B_{s,vacuum} = Σ_c A_sc I_c.
- General time-varying currents require fuller compensation (must include induced currents in wall and other structures). Three methods:
  - **Method 1 — Frequency-domain transfer function:** measure transfer function over a range of frequencies; analytic fit B_{s,vacuum}(ω) = Σ_c [ (iω−z₁,sc)(iω−z₂,sc)... / (iω−p₁,sc)(iω−p₂,sc)... ] I_c(ω) (rational pole/zero fit). (page 12)
  - **Method 2 — Convert to a time-domain filter:** inverse Z-transform (inverse bilinear transform) → recursive time-domain filter, "Suitable for real-time use with arbitrary waveforms" (recursive a_j/b_j form). (page 13)
  - **Method 3 — Time-domain response function R(τ):** B_s(t) = Σ_c [ R_sc(0) I_c(t) + ∫₀ᵗ R'_sc(τ) I_c(t−τ) dτ ]; R_sc is the measured step-function response to coil c. (page 13)

**Spatial fitting — "normal equations" method (page 19, "Fit to a Spatial Function Enables Data Visualization"):**
- Matrix A of orthogonal basis functions evaluated at sensors j: **S_j = Σ_k A_jk B_k** (predicts sensor measurements S_j given basis coefficients B_k).
- Pseudo-inverse least-squares fit: **B = (AᵀA)⁻¹ Aᵀ S**.
- Can reconstruct the fitted function at any spatial location from coefficients B_k.
- Simple basis choice: cylindrical Fourier harmonics in φ and θ:
  **δB(φ,θ) = Σ b_nm exp(inφ − imθ)**
- Basis matrix for differential pairs at [φ_{j,1},θ_j] and [φ_{j,2},θ_j]:
  **A_jk = ⟨exp(inφ_{k,j,1} − imθ_{k,j})⟩ − ⟨exp(inφ_{k,j,2} − imθ_{k,j})⟩**, where ⟨…⟩ indicates averaging over sensor areas and k indexes the (n,m) harmonic combinations.
- Caveat (bold on page 19 and repeated page 33): "**Basis functions do NOT necessarily correspond to plasma modes.**"
- Method reference [5]: W. H. Press et al., *Numerical Recipes in Fortran*, 2nd ed., 1994, p. 665.

**SVD / biorthogonal decomposition (page 25, "Singular Value Decomposition Identifies Principal Time and Space Vectors of the Data"):**
- Decompose measurement matrix M (sensors s × time samples t): **M = U W Vᵀ**.
- "Columns of U (left-singular vectors) → spatial structure"; "Columns of V (right-singular vectors) → time evolution."
- "Space-time decomposition is also termed **Biorthogonal Decomposition**" (refs 6,7,8: Kim PPCF 41 1399 (1999); Nardone PPCF 34 1447 (1992); Dudok de Wit PPCF 37 117 (1995)).
- Largest singular values w capture dominant behavior.

**Condition number / basis selection (page 24, "Choice of Basis Functions is Guided by Quality of Fit and SVD Condition Number"):**
- "A meaningful fit requires the basis matrix A to be well-conditioned" — "Avoid degeneracy of basis functions as observed at the sensors."
- **Condition number: K(A) = max(w_i) / min(w_i)**, eigenvalues/singular values w_i from SVD of A.
- "Choose basis functions to optimize quality of fit and condition number."
- "Ex: Fit to 2/1 locked mode is optimized with **1 ≤ m ≤ 4-5**."
- "Including more poloidal harmonics — Increases condition number — Does not reduce standard deviation."
- NOTE: The task brief mentions "κ(A) < 10" as a target. This poster does NOT state a numeric threshold of 10 in the text. On the page-24 figure the optimum (highlighted green ellipse, at m(max)≈4–5) sits at a condition number of roughly 3 on the y-axis (axis runs 0–15); condition number rises to ~9 at m(max)=8. So the empirically chosen optimum is well under 10, but "κ(A)<10" as an explicit rule is not written in this document — treat that as inferred, not quoted.

---

## Visualizations to reproduce

### 1. Sensor layout map (page 5) — see Hardware section above for full detail
- φ (deg) 0–360 horizontal; "Distance along vessel wall (m)" −2 to 5 vertical; region labels INBOARD/HFS/TOP/LFS/OUTBOARD on right; red Bp probe bars + blue Br loop rectangles; legend "66 Bp probes / 64 Br loops."

### 2. Locked tearing mode φ–θ contour (page 7, "Locked Tearing Mode Has Static '3D' Structure")
- Fit to 66 Bp probes → m=2 / n=1 structure; "32 HFS (inboard) locations – 34 LFS (outboard) locations."
- **Axes:** X = Phi (deg.) 0–360; Y = Theta (deg.) from −90 to 270, with a white gap/break separating the inboard panel (upper, ~120°–270°) from the outboard panel (lower, −90°–~120°).
- **Right-edge θ labels (top→bottom):** BOT (270), INBOARD, TOP (90), OUTBOARD, BOT (−90).
- **Colorbar:** "δBp (G)", diverging, **−40 to +40 G** (dark blue negative → red/orange mid → yellow/white positive).
- White square markers = sensor locations overlaid on the smooth fitted contour. Diagonal helical banding visible (n=1 toroidal, m=2 poloidal); inboard banding steeper.

### 3. Signal-conditioning stages (page 11, "Signal Conditioning Reduces Noise and Offset")
- Header: "Measuring plasma response to external n=2 field." Bullets give desired signal ~.001 of axisymmetric Bp; oscillating applied field enables synchronous detection; offset subtraction + averaging not adequate; high-pass separates AC; single-frequency Fourier filter yields clean signal (filter ref [3] Hanson NF 52 13003 (2012)).
- **Stacked time-series panels (read from image), all share Time(ms) axis; lower panels zoom 2000–~3450 ms:**
  - Top: **"Total Bp"**, y = Bp (T), 0 to 0.3 T, full shot 0–~6500 ms (ramps up to a ~0.28 T flat-top then down). Annotation: **ΔBp = [ B(φ₁) − B(φ₂) ] / 2**, with a red ellipse highlighting the tiny ΔBp trace near zero.
  - **"Coil current (A)"**, y ≈ −800 to +800 A, sinusoidal modulation (turns on ~2400 ms).
  - **"ΔBp (G): Raw data"**, y ≈ −20 to +30 G, very noisy.
  - **"Smooth, subtract offset"**, y ≈ −10 to +10 G.
  - **"Smooth, hi-pass filt."**, y ≈ −6 to +6 G.
  - **"20 Hz Fourier filter"**, y ≈ −6 to +6 G, clean sinusoid.
- (Demonstrates the pipeline: raw → smooth+offset-subtract → high-pass → single-frequency Fourier filter.)

### 4. Toroidal array fit, n=2 → n=1 evolution (page 20)
- "10-probe array → good fit to 3 toroidal modes (6 degrees of freedom)." Shows initial n=2 locked mode followed by growth of n=1 locked mode. (Underlying time-trace figure present; specific numeric axes not legible in the text layer.)

### 5. n=2 locked-mode poloidal-structure fit (page 21, "Fit to 66 Bp Pairs Shows n=2 Locked Mode Has m ~ 3")
- Shot/time annotation on plot: **"162432, t=1835 ms"** (time slice before onset of the n=1 mode).
- **Main panel:** X = Phi (deg.) 0–360; Y = Theta (deg.) −90 to 270 with right labels BOT/INBOARD/TOP/OUTBOARD/BOT. Colorbar "δBp (G)" diverging **−4 to +4 G** (blue→red→yellow). White square sensor markers overlaid on fitted contour; helical banding.
- **Inset (upper right):** Fit vs. Measured scatter, both axes "δBp (G)" −4 to +4, with a 1:1 diagonal line; points cluster on the line (good fit). Labels "Fit" (y) / "Measured" (x).
- **Fitting box:** "Fitting / 1 ≤ n ≤ 2 / 1 ≤ m ≤ 5."

### 6. Inboard (HFS) array fit, high-m response (page 22, "Inboard Array Fit Shows High-m Plasma Response to Applied n=2 Perturbation")
- "Inboard side (HFS) response to n=2 applied field → m ~ 10." Shot annotation: **"158116, t=4850 ms"** (time slice with minimum HFS response).
- **Panel:** X = Phi (deg.) 0–360; Y = Theta (deg.) **90 to 270** (note: only inboard wall range; tick labels 90,135,180,225,270). Right label "INBOARD WALL," BOT at top (270), TOP at bottom (90). Colorbar "δBp (G)" **−4 to +4 G**. White square sensor markers; tightly spaced helical bands (high m).
- **Fitting box:** "Fitting / n = 2 / m = 6,10,14."
- Resolution notes (δZ=14 cm, δθ~11°→max m~16; ΔZ=152 cm, δθ~93°→min m~4) as in Hardware section.

### 7. SVD energy spectrum + time vectors (page 25)
- **Left panel:** Y axis label "Energy, 1 − Σ_{j=1}^{i} s_j² / Σ_{j=1}^{N} s_j² (A.U.)", **log scale 10⁻⁸ to 10⁰**. X = "Singular values," 0 to ~35 (ticks 0,5,10,15,20,25,30,35). Blue filled circles descend monotonically; a horizontal **dashed blue reference line at ~10⁻² (i.e., 0.02)** marks the 98% cumulative-energy level. Sharp drop after the first 1–2 values, then a gentle decline, then a steep fall after ~30.
- **Right panel:** Y = "Time Vector, v_i (A.U.)", **−0.08 to +0.08**. X = "Time (ms)", **2.90 to 3.00 ×10³** (i.e., 2900–3000 ms). Two traces: **v₀ (blue)** and **v₁ (green)**, legend top-right. Both oscillate rapidly at left (rotating phase) then flatten/separate to steady offsets at right (locking) — illustrating "Rotating n=1 mode that slows and locks." Bullet: "98% of the energy is in the first two singular vectors … correspond to sin(φ) and cos(φ)."

### 8. SVD vs. βN and coil phase (page 26, "Singular Value Decomposition Identifies Dependences on Other Variables")
- Plasma response to applied n=1 field vs. βN and upper-lower coil phase Δφ. "Decompose measurement matrix M of sensors and experimental cases." "Two SVD vectors have different Δφ dependences"; "SVD reconstruction with only 2 vectors fits the spatial dependence well." Left subplot: Amplitude vs. Inner Wall Height (m) (~−0.5 to 0.5); right subplot: Normalized Amplitude vs. "Phasing Δφ (Deg)" 0–360. (Specific table of βN/Δφ values partly garbled in text layer — see Example values.)

### 9–11. Model-comparison plots (pages 29–31) — see Example values; these compare measurement to MARS-F, IPEC, M3D-C1, VMEC.

---

## Concrete example values (only as they appear)

Shots/times explicitly printed in this poster:
- **162432, t = 1835 ms** — n=2 locked mode poloidal fit, m~3 (page 21).
- **158116, t = 4850 ms** — inboard HFS array fit, high-m response to applied n=2 (page 22).
- **164672, t = 3140 ms** — condition-number vs. m(max) example, 2/1 locked mode (page 24).
- Page 26 case list (text layer, somewhat garbled): shot numbers **153480, 153485, 153489, 153491** and **161261, 161262, 161263** appear, associated with a table of (βN, Δφ) entries — visible pairs include roughly βN ~2.5 / Δφ −240°, 2.5 / −300°, 1.8 / −240°, 1.7 / −300°, and an annotation "T = 8 Nm" and "NBI." Treat the precise βN/Δφ pairings as LOW CONFIDENCE (table cells overlap in extraction; not verified against the rendered figure).

Other quantitative facts stated:
- δB/B₀ of interest: **10⁻³ to 10⁻⁵** (abstract); δB/B₀ ~ **10⁻⁴** (page 9).
- S/N "~0.1 or less" (page 9); raw data S/N "~1" (page 17).
- "Two-axis measurements at approximately **64 locations**" (abstract).
- **66 Bp probes; 64 Br loops** (page 5).
- Differential separations: LFS midplane Bp array **77°–180°**; other arrays **15°–180°** (page 10).
- Inboard array: δZ=14 cm (δθ~11°, max m~16); ΔZ=152 cm (δθ~93°, min m~4) (page 22).
- Synchronous detection: applied n=2 field, **5 Hz** square-wave filter (page 17); page-11 figure also shows a **20 Hz Fourier filter** stage and **100 ms** polarity reversals on page 16.
- "98% of the energy is in the first two singular vectors" (page 25).
- 2/1 fit optimized with **1 ≤ m ≤ 4-5** (page 24).

**Note on task brief's candidate shots:** Of the brief's listed shots (164672, 165878, 162432, 154551), only **164672** (p24) and **162432** (p21) actually appear. **165878 and 154551 do NOT appear** in this document.

**Synchronous-detection coil modulation (pages 15–16):**
- DIII-D non-axisymmetric coils modulate the applied field by: toroidal rotation (n ≤ 2); polarity reversals (n ≤ 3); transient turn-on (page 15).
- Page 16, "'Phase flips' of Applied n=2 Field": "6 coils in 3 symmetric (n=even) pairs apply n=2 field"; "Polarity reversal / 100 ms"; "Toroidal phase change every 3 periods." Figure shows current distribution in the 6-coil array and currents of the 3 coil pairs.

**Model-comparison results:**
- Page 29 ("Measured Kink Mode Structure Agrees with Ideal MHD"): unstable kink in a limiter discharge at q(a)~2; measurement = growing instability at **q_a = 2.08**; **MARS-F** prediction = ideal MHD instability, equilibrium extrapolated to **q_a = 1.995**. Two φ-contour panels, "Measurements, q(a)=2.08" vs "MARS prediction, q(a)=1.995," X = Toroidal Angle (deg) 0–360.
- Page 30 ("Measurements Benchmark 3D Equilibrium Models"): measured response to applied n=1 perturbation agrees with **IPEC** (Ideal, perturbative — green), **MARS-F** (Ideal, eigenvalue — blue), **M3D-C1** (Resistive, 2-fluid — purple), **VMEC** (Ideal, fully 3D — red). Plots: Amplitude (G/kA) 0–4 and Phase (deg) −100 to +100, vs Outer Wall Distance (m) −1.5 to 1.5 (left) and Inner Wall Distance (m) −0.5 to 0.5 (right).
- Page 31 ("Data Confirm Predictions of n=2 Multi-Mode Response"): LFS vs HFS response to applied n=2 vs upper-lower coil phase Δφ_UL; agrees with **IPEC** two-mode prediction; "High-field side mode is correlated with ELM suppression." Plots: |δBp| (G) 0–8 (top) and 0–2.5 (bottom) vs Δφ_UL 0–360°, labeled DATA vs IPEC, with "ELM Suppression" region marked. Ref [10] Paz-Soldan PRL 114, 105001 (2015).

---

## Notable quotes (verbatim, with page #)

- (p2) "Two-axis measurements at approximately 64 locations provide the amplitude and spatial structure of plasma asymmetries, enabling detailed comparison to 3D MHD models."
- (p2) "The measurements are challenging because of the small amplitude of 3D fields of interest – typically 10⁻³ to 10⁻⁵ of the total axisymmetric magnetic field."
- (p2) "Fourier analysis in the poloidal direction is not well justified due to the lack of symmetry, but can still yield a rough picture of the structure of helical perturbations, while techniques such as singular value decomposition can provide a more unbiased representation of the poloidal structure."
- (p2) "such techniques can successfully isolate plasma signals with amplitudes well below one Gauss."
- (p5) "n ≤ 3 resolution at 5 poloidal locations; n ≤ 4 at Low Field Side midplane"
- (p5) "Single-n detection (amplitude & phase) at 15 poloidal locations – 14 cm poloidal resolution at High Field Side"
- (p6) "Two toroidal arrays, 8 Br-Bp combinations per array"
- (p10) "All '3D' sensors are connected in toroidally separated pairs: ΔB = B(φ₁) – B(φ₂)"
- (p10) "Variable toroidal separation minimizes spatial degeneracy for multiple n values"
- (p10) "LFS midplane Bp array: 77º ≤ Δφ ≤ 180º – Other arrays: 15º ≤ Δφ ≤ 180º"
- (p16) "6 coils in 3 symmetric (n=even) pairs apply n=2 field"
- (p19) "Fitting uses the 'normal equations' method"
- (p19) "Simple choice of basis set: cylindrical Fourier harmonics in φ and θ  …  δB(φ,θ) = Σ b_nm exp(inφ − imθ)"
- (p19) "Basis functions do NOT necessarily correspond to plasma modes"
- (p24) "A meaningful fit requires the basis matrix A to be well-conditioned. – Avoid degeneracy of basis functions as observed at the sensors"
- (p24) "Ex: Fit to 2/1 locked mode is optimized with 1 ≤ m ≤ 4-5"
- (p24) "Including more poloidal harmonics – Increases condition number – Does not reduce standard deviation"
- (p25) "Space-time decomposition is also termed Biorthogonal Decomposition"
- (p25) "98% of the energy is in the first two singular vectors … correspond to sin(φ) and cos(φ)"
- (p31) "High-field side mode is correlated with ELM suppression"
- (p33) "Cylindrical poloidal harmonics are simple and general but not necessarily well aligned with mode structure"
- (p33) "'3D' magnetic measurements confirm non-axisymmetric MHD models and have revealed new physics"

---

## Future work (page 34)
- Improved basis functions (better account of sensor locations; better matched to typical mode features; case-specific predictions).
- Combined Br + Bp analysis to "double the inputs" / "double toroidal resolution" — but must account for Br/Bp phase shifts from induced currents.
- Uncertainty analysis: propagate measurement uncertainties; account for imperfectly conditioned sensor distributions.

## References (page 35, verbatim list)
1 King RSI 85, 083503 (2014); 2 Strait RSI 77, 023502 (2006); 3 Hanson NF 52, 13003 (2012); 4 Logan PhD Thesis, Princeton (Jan 2015); 5 Press et al., Numerical Recipes in Fortran 2nd ed. (1994) p.665; 6 Kim PPCF 41, 1399 (1999); 7 Nardone PPCF 34, 1447 (1992); 8 Dudok de Wit PPCF 37, 117 (1995); 9 King NF 56, 14003 (2016); 10 Paz-Soldan PRL 114, 105001 (2015); 11 King PoP 22, 072501 (2015); 12 Wingen GA Report GA-A28270 (2016); 13 Hanson PoP 21, 072107 (2014); 14 Turnbull, accepted J. Plasma Phys. (2016); 15 Hanson, Bull. APS DPP abstract JP8.82 (2009).

---

## Digest (4–6 sentences)

This is E.J. Strait's 2016 HTPD poster (rendered as a 35-page slide deck) on analysis techniques for DIII-D's upgraded "3D" magnetic diagnostic set, comprising **66 Bp probes and 64 Br loops** giving two-axis coverage at ~64 wall locations, with n≤3 resolution at 5 poloidal locations (n≤4 at the LFS midplane) and single-n detection at 15 poloidal locations (14 cm HFS resolution). The core hardware trick is **toroidally separated differential pairs** (ΔB = B(φ₁)−B(φ₂)) with variable separations (77°–180° for the LFS midplane Bp array, 15°–180° for other arrays) to reject the n=0 field that is ~10⁴× larger than the 3D signals of interest. The analysis chain is laid out method-by-method: signal conditioning (offset subtraction, smoothing, high-pass, single-frequency Fourier filter — shown on a stacked time-series figure with a 20 Hz filter stage), three coil-coupling compensation schemes (frequency-domain pole/zero transfer function, recursive time-domain filter via inverse bilinear transform, and time-domain step response R(τ)), synchronous detection of applied n=2 fields (6 coils, 3 pairs, 100 ms polarity flips, 5 Hz filter), least-squares "normal-equations" spatial fitting to cylindrical Fourier harmonics δB(φ,θ)=Σb_nm exp(inφ−imθ) with pseudo-inverse B=(AᵀA)⁻¹AᵀS, and SVD/biorthogonal decomposition M=UWVᵀ where condition number K(A)=max(w_i)/min(w_i) guides basis selection (2/1 fit optimal at 1≤m≤4–5). Distinctive concrete content includes the φ–θ δBp contour maps (±40 G for the locked tearing mode on p7; ±4 G for shots 162432/158116 on pp21–22), the SVD energy spectrum showing 98% of energy in the first two singular vectors (sin φ / cos φ) with the v₀/v₁ time vectors over 2900–3000 ms (p25), and model benchmarks against MARS-F, IPEC, M3D-C1 and VMEC including a q_a=2.08 kink and an n=2 HFS multi-mode response correlated with ELM suppression. IMPORTANT caveats for the GUI project: this poster never names SLCONTOUR or MODESPEC, never states a numeric digitization/integration rate, and does not literally write "κ(A)<10" (the chosen optimum is empirically ~3, well under 10, per the p24 figure); of the brief's candidate shots, only **164672** and **162432** actually appear (165878 and 154551 do not).

**Output file:** `docs/research-summaries/11_HTPDposter2016.md`
