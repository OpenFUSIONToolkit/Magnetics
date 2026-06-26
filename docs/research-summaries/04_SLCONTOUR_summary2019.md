# SLCONTOUR Analysis Tool for 3D Magnetics — Summary

**Source file:** `resources/DIII-D IDL Command Line Tools/Strait_3DSPmeeting_20190204 A Brief Summary of the SLCONTOUR Analysis Tool for 3D Magnetics.pdf`

> ACCURACY NOTE: Everything below is taken from the document's extracted text (26 pages, 26 slides). Where the underlying PowerPoint geometry made the text run together (especially numeric labels on plots), the original spacing was lost in extraction; I have reconstructed the intended meaning but flag any reconstruction explicitly. The only embedded raster images on the figure slides are the slide-template background and the DIII-D logo — the actual plots are vector graphics and could not be extracted as images, so all plot details below come from the text labels embedded in those slides. I do not state any value that is not literally present in the extracted text.

---

## Document overview

- **Title:** "A Brief Summary of the SLCONTOUR Analysis Tool for 3D Magnetics" (slide 1).
- **Author:** E.J. Strait.
- **Venue / date:** "DIII-D 3D and Stability Physics Meeting, Feb. 4, 2019." Every page footer reads "E. Strait / 3DSP / Feb. 4, 2019." PDF metadata: Creator = PowerPoint, Producer = Mac OS X Quartz PDFContext, CreationDate D:20190204170725Z.
- **Length:** 26 pages / 26 slides.
- **References listed on slide 1 (verbatim):**
  - "Spatial and temporal analysis of DIII-D 3D magnetic diagnostic data, E.J. Strait, et al., RSI 87, 11D423 (2016) … also see Friday Science Meeting slides, June 24, 2016."
  - "An upgrade of the magnetic diagnostic system of the DIII-D tokamak for nonaxisymmetric measurements, J.D. King, et al., RSI 85, 083503 (2014)."
  - Slide 26 cites: "R.M. Sweeney & E.J. Strait, Phys. Plasmas 26, 012509 (2019)."
  - Slide 7 cites the fitting method to: "W. H. Press, et al., Numerical Recipes in Fortran, 2nd ed., Cambridge Univ. Press, 1994, p. 665."
- **Scope:** This is a tutorial/overview deck describing what SLCONTOUR is, the math behind its fits, the sensor arrays it works with, fitting constraints, and the command-line interface for running it inside IDL.

---

## Magnetic sensors / hardware

(DIII-D "3D" magnetic diagnostics — slides 2-3, 8, 11-13, 19)

- **Slide 2 title:** "DIII-D '3D' Magnetic Diagnostics Provide 2-Axis Measurements Over Most of the Wall."
  - "n ≤ 3 resolution at 5 poloidal locations; n ≤ 4 at Low Field Side midplane"
  - "Single-n detection (amplitude & phase) at 15 poloidal locations"
  - "14 cm poloidal resolution at High Field Side"
  - Sensor counts named on the slide: **"66 Bp probes"** and **"64 Br loops."**
  - The slide-2 figure axes (text labels): vertical axis "Distance along vessel wall (m)" running roughly -2 to 5; region labels INBOARD, HFS, TOP, LFS, OUTBOARD; horizontal axis "φ (deg.)" with ticks 0 90 180 270 360, plus an "(m)" axis with 1 2 3.

- **Differential pair connection (slide 3, title "Differential Pairs of Sensors Reject n=0 Field"):**
  - "All '3D' sensors are connected in toroidally separated pairs: ΔB = [B(φ₁) – B(φ₂)] / 2" (subscripts 1 and 2 on the two toroidal angles).
  - "Some are also acquired individually for n=0 field" (with an "Adjustable balance" annotation and an integrator term `∫ ΔB(φ₁,φ₂) dt`).
  - "Variable toroidal separation minimizes spatial degeneracy for multiple n values."
  - **"LFS midplane Bp array: 77º ≤ Δφ ≤ 180º"**
  - **"Other arrays: 15º ≤ Δφ ≤ 180º"**
  - The slide includes a polar diagram "Differential pair connections for LFS midplane toroidal array" with toroidal angle marks 0 / 90 / 180 / 270.

- **Array geometry referenced elsewhere:**
  - 2-D Bp set = **66 Bp probes**: "32 HFS (inboard) locations – 34 LFS (outboard) locations" (slide 8).
  - LFS toroidal arrays named **"R0, R±1, R±2"** (5 poloidal locations), spanning "Δθ ~ 160°" in poloidal angle (slide 11).
  - HFS vertical array spans "Δθ ~ 90°," "10 poloidal locations," "no toroidal resolution except at the midplane," average sensor spacing "Δθ ~ 10°," vertical resolution "δZ = 14 cm" (slides 12-13).

- **Array naming keywords (slide 19 — searchable keyword categories for the `find` command, verbatim):**
  - "Bp / Br / Bt / Bpdot"
  - "Pairs / Singles"
  - "Tor / Pol / Vert / 2D"
  - "LFS / HFS / R0, R+1, …"
  - "PCS, Comp, External, …"
  - SLCONTOUR "recognizes >95 arrays."
  - Example array names returned by `find bp r0` (verbatim, 5 matches): **MPID** (Bp Pairs Tor LFS R0), **MPI66M** (Bp Singles Tor LFS R0), **MPI66M_S** (Bp Singles Tor LFS R0, Slow A/D), **PCMPID** (Bp Pairs Tor LFS R0, PCS), **NRSMPID** (Bp Pairs Tor LFS R0, PCS-Comp).
  - Other array names appearing in command examples: **ISLD** (slide 17, `array=ISLD`), **MPID** (used as the example 10-probe / 66-pair array on slides 9 & 14), **mpi66m** (slide 19, `array mpi66m`).

---

## SLCONTOUR (primary focus)

### Purpose (slide 4, title "Slcontour Enables Visualization of '3D Magnetics' Data")
The three stated purposes (verbatim bullet headings + sub-bullets):
1. **"Checking the data quality"**
   - "Visually: raw data traces show dead probes, large drifts, etc."
   - "Analytically: quality of fits to a simple model"
2. **"Quick mode analysis"**
   - "Reliable decomposition of toroidal modes with 1D array data"
   - "Rough analysis of poloidal modes with 2D array data"
3. **"Maintaining a database of the available data channels"**
   - "… and how they are organized into 1D and 2D arrays"

Slide 5 ("Spatial Fitting of Single-Time Snapshots Allows Arbitrary Time Evolution"): "3D magnetic diagnostics are aimed primarily at measuring non-rotating MHD modes, stable 3D plasma response, etc. – Time-domain Fourier analysis cannot be used." The slide-5 example caption: "1-D toroidal array shows growth of n=2 and n=1 locked modes."

Slide 25 summary restates the three uses as: "Visual checking of data / Toroidal mode analysis / Rough poloidal mode analysis."

### Getting started / launching (slides 15-16, verbatim)
```
$ module load slcontour      (• Set the environment — or include this line in .cshrc)
$ idl                        (• Launch idl)
IDL> slcontour               (• Run slcontour)
-->                          (• Enter commands at the prompt)
--> exit                     (• Exit back to idl)
```
- "Command syntax: `--> command=<value>`"
- "Unique abbreviations of commands are ok."
- "Use `,` or `;` to separate multiple commands on a single line"
- "Example: `--> tmin=2000, tmax=3000`"

### Frequently used commands (slide 17, verbatim left = command, right = meaning)
```
--> shot=123456            • Shot
--> tmin=3000, tmax=4000   • Time interval (ms)
--> array=ISLD             • Array
--> nmin=1, nmax=3         • Mode number range to fit
--> smooth=5               • Smooth raw data (ms)
--> slice=3250             • Time slice for plot (ms)
--> hc=13-450-xerox        • Print a hard copy
```

### Informational commands (slide 18, verbatim)
```
--> commands   • Print a list of all commands
--> help       • Print a summary of commands with hints
--> document   • Open a read-only window to view documentation
--> view       • Show current parameter settings (or just hit Return)
```

### Finding an array (slide 19, verbatim)
```
--> find             (no keywords → see the entire list incl. keywords)
--> find bp r0       (search by keywords)
   5 Matches found
   MPID      Bp Pairs Tor LFS R0
   MPI66M    Bp Singles Tor LFS R0
   MPI66M_S  Bp Singles Tor LFS R0 (Slow A/D)
   PCMPID    Bp Pairs Tor LFS R0 (PCS)
   NRSMPID   Bp Pairs Tor LFS R0 (PCS-Comp)
--> array mpi66m
```

### Fitting options (slide 20, verbatim)
```
--> nmin=1,nmax=3,nstep=1            • Select n range & increment (default: nstep=1)
--> mmin=2,mmax=8,mstep=2            • Select m range & increment (for LFS arrays, e.g.)
--> mmin=1, mmax=4, mstep=1          • (m range example)
--> mmin2=2,mmax2=10,mstep2=4        • Combine primary and secondary ranges of m
                                       (may be useful for combined LFS & HFS)
```
- "If secondary m range is added, only unique m values are used. The last example above gives **m = [1, 2, 3, 4, 6, 10]**."

### Baseline-subtraction options (slides 21-24)
Commands (slide 21, verbatim):
```
--> btype=1                      • Select baseline algorithm (no argument: list the options)
--> btype                        • (lists the options)
--> base=50                      • Baseline time interval (ms)
--> tbmin=2200,tbmax=2800        • Baseline start, end times (ms) (optional)
```
btype option table (slide 21, verbatim):
```
0  = No baseline subtraction          9  = single-freq. sine fit, period=base
1  = baseline: early data             10 = single-freq. square fit, period=base
2  = baseline: late data              11 = arb. base interval, early data (~ #1)
3  = baseline: interpolated           12 = arb. base interval, late data (~ #2)
4  = baseline: running average        13 = arb. base interval, interpol. (~ #3)
5  = baseline: running av., lag=base
6  = baseline: running av., lag=2xbase
7  = baseline: RC filter, tau=base
8  = baseline: RC filter, lag=base
```
- Transient-event use (slide 22): btype=1 averages over a "base"-duration interval at the **start** of the plotted window; btype=2 at the **end**; btype=3 interpolates between the two averages. "btype = 11, 12, 13 are the same as 1, 2, 3 except the baseline times are decoupled from the time window limits — Start time of the earlier base interval is set by `tbmin` (default = tmin); End time of the later base interval is set by `tbmax` (default = tmax)."
- Long-pulse use (slide 23): btype=4 running average centered at sample time; btype=5 lag Δt=base; btype=6 lag Δt=2×base; btype=7 single-pole filter up to sample time, τ=base; btype=8 lag Δt=base. "Note: options 5-8 are causal, 4 is not."
- Periodic data, period=T (slide 24): "Set base = T for all of these options." btype=4 subtracts non-periodic contributions; btype=9 fits one period of a sine wave around each sample; btype=10 fits one period of a square wave around each sample.

### Built-in fit-quality limits (slide 9, verbatim)
- "Limits built into slcontour:"
  - "K > 10: warning"
  - "K > 20: error message"
- (K = SVD condition number; see Analysis methods below.)

### Outputs
- Raw-data traces (for visual data-quality checks; "show dead probes, large drifts, etc." — slide 4).
- A 2-D φ–θ contour plot of the fitted field (slides 8, 13 — see Visualizations).
- Reported fit metrics: SVD condition number **K** and standard deviation **σ** (slide 14: "Optimize condition number K (depends on choice of n,m) and standard deviation σ").
- Hard-copy print via `hc=` (slide 17).
- (No explicit phase-vs-position plot, coherence bar, or numbered raw-trace example slide appears in this deck — see "not covered" notes below.)

---

## MODESPEC

**Not covered.** MODESPEC is not mentioned anywhere in this document. (This deck is exclusively about SLCONTOUR.)

---

## Analysis methods / math

(slides 6-7, 9-12, 14, 25)

- **Basis set (slide 6, title "Fit to Spatial Function Enables Data Visualization"):**
  - "δB(φ,θ) = Σ b_nm exp(inφ − imθ)" — "cylindrical Fourier harmonics in φ and θ."
  - "These basis functions are a device for fitting periodic data. They do not necessarily correspond to plasma modes."
  - "Toroidal symmetry ⇒ e^{inφ} is usually a reasonable model for the toroidal dependence of a plasma mode."
  - "Poloidal asymmetry ⇒ poloidal variation of a plasma mode is NOT well described by a single term e^{imφ}." (Note: the slide text reads e^{imφ}; in context this is the poloidal e^{-imθ} term.)

- **"Normal Equations" method (slide 7):**
  - "Evaluate the basis functions at each sensor j."
  - "'Sensor' is a differential pair at [φ_{j,1}, θ_j] and [φ_{j,2}, θ_j]."
  - "k indexes the combinations of n,m harmonics."
  - "⟨…⟩ indicates averaging over area."
  - Basis-matrix element (verbatim form): "A_jk = (1/2){ exp(inφ_{k,j,1} − imθ_{k,j}) − exp(inφ_{k,j,2} − imθ_{k,j}) }" → "'Basis matrix' A_jk of orthogonal basis functions k, evaluated at sensors j."
  - Forward model: "Predicts vector of sensor measurements S_j given a vector of basis coefficients B_k: **S_j = Σ_k A_jk B_k**."
  - Least-squares solution: "Pseudo-inverse of A yields a linear least-squares fit of coefficients B, for a set of measurements S: **B = (Aᵀ A)⁻¹ Aᵀ S**."
  - "Can reconstruct the fitted function at any spatial location, using coefficients B_k."
  - Cited to Numerical Recipes in Fortran, 2nd ed., p. 665.

- **Condition number (slide 9):**
  - "Quality of fit depends on condition number **K ≡ max(w_i) / min(w_i)** — where w_i are the singular values of the basis matrix."
  - "Uncertainty of the fit is roughly proportional to K, so small values are desirable."
  - Built-in thresholds: K > 10 → warning; K > 20 → error message.

- **1-D array resolution rule (slide 9):** "A toroidal array of N sensors should resolve up to **(N-1)/2** modes." Example MPID array: "10 probes ⇒ can resolve n ≤ 4"; "K < 2 for fits with n ≤ 3"; "K < 5 for fits with n ≤ 4."

- **2-D array resolution rules (slide 10):**
  - "A poloidal array of M sensors should resolve up to **(M-1)/2** poloidal harmonics."
  - "A 2-D array consisting of M toroidal arrays should resolve up to **M** poloidal harmonics — Toroidal distribution provides the real/imaginary resolution."
  - When the array does not span full 2π poloidally: "Spatial Fourier analysis within the measurement domain is based on a longest poloidal wavelength of Δθ < 2π — Poloidal array can resolve **m = [1, 2, 3, …] × 2π/Δθ**."
  - Reiterates: "These basis functions are a device for fitting periodic data. They do not necessarily correspond to plasma modes. They need not match the structure outside the measurement domain."

- **LFS-specific (slide 11):** Δθ ~ 160°, 5 poloidal locations; longest wavelength "λ_{θ,max} ~ π ⇒ m_min ~ 2," resolvable m are integer multiples of 2; "m=[2, 4, 6, 8, 10] is well conditioned"; "m=[1,2,3,…] decomposition is poorly conditioned for more than 3 harmonics"; poloidal spacing "may limit m_max < 5-6 to avoid spatial aliasing."

- **HFS-specific (slide 12):** Δθ ~ 90°, 10 poloidal locations (no toroidal resolution except at midplane); "λ_{θ,max} ~ π/2 ⇒ m_min ~ 4"; "m=[4, 8, 12, …] is well conditioned up to 5 harmonics"; "m=[1,2,3,…] decomposition is very poorly conditioned for more than 2 harmonics"; average spacing Δθ ~ 10° "may limit m_max < 18 to avoid spatial aliasing."

- **2-D fit optimization guidance (slide 14):**
  - "Bad example: n ≤ 3 and m ≤ 3 ... ⇒ 55 degrees of freedom — Fitting to 66 MPID pairs is likely to produce meaningless results." (Note: extracted text shows the "55 d.o.f." figure adjacent to a partly garbled "n ≤ 9"; the 55 d.o.f. value is explicit.)
  - "Example: n=1 tearing mode, try n ≤ 2, m ≤ 2 ... ⇒ 17 d.o.f." (adjacent garbled "n ≤ 4").
  - "Narrow the range of n,m until σ starts to increase … and/or … Widen the range of n,m until K starts to increase."
  - m-step guidance: "m step = 1 or 2 → m_max = 4-6 if fitting LFS only"; "m step = 4 → m_max = 16-18 if fitting HFS only"; "m step = 1 → m_max = 4-6(?) if fitting the full poloidal range."

- **Summary takeaway (slide 25):** "Selection of basis functions must be guided by quality of fit and SVD condition number."

---

## Visualizations to reproduce

> Important: the actual plots are vector graphics; the values below are read directly from the text labels embedded in the slides. Where label digits ran together in extraction (e.g., color-bar tick values), I report exactly what is present and flag reconstructed groupings.

1. **2-D φ–θ contour plot — locked mode (slide 8, title "2-D Spatial Fit Shows Structure of Locked Mode").**
   - Caption text on slide: "Fit to 66 Bp probes yields m=2 / n=1 structure — 32 HFS (inboard) locations, 34 LFS (outboard) locations."
   - Shot/time label on the plot: **"164672, t=3140 ms."**
   - Quantity / color bar label: **"δBp (G)."** Color-bar tick values present in text: **40, 20, 0, -20, -40** (i.e. range roughly ±40 G).
   - Vertical axis: **"Theta (deg.)"** with tick labels including 270, 180, 90, 0, -90; poloidal-region annotations BOT, INBOARD, TOP, OUTBOARD, BOT mark the θ positions.
   - Horizontal axis: **"Phi (deg.)"** with ticks **0 90 180 270 360**. The slide appears to show two side-by-side panels (the "0 90 180 270 360 / 0 90 180 270 360" pattern in the text suggests two φ panels, e.g. data vs. fit).

2. **2-D φ–θ contour plot — HFS high-m response (slide 13, title "HFS Array Fit Shows High-m Plasma Response to Applied n=2 Perturbation").**
   - Bullet context: "Inboard side (HFS) response to n=2 applied field ⇒ m ~ 10 locally — Fitting HFS arrays only, in a time slice with minimum LFS response. Vertical resolution δZ = 14 cm, δθ ~11º → maximum m ~ 16. Vertical range ΔZ = 152 cm, δθ ~93º → minimum m ~ 4."
   - Shot/time label on the plot: **"158116, t=4850 ms."**
   - Plot annotations: "Fitting n = 2, m = 6,10,14" and "INBOARD WALL."
   - Color bar label: **"δBp (G)"**, tick values present: **4, 2, 0, -2, -4** (range roughly ±4 G).
   - Vertical axis: **"Theta (deg.)"** with ticks 270, 225, 180, 135, 90 (region labels BOT … TOP).
   - Horizontal axis: **"Phi (deg.)"** with ticks 0 90 180 270 360.

3. **Raw-data traces.** Described in words only (slide 4: "raw data traces show dead probes, large drifts, etc.") and the slide-5 example caption ("1-D toroidal array shows growth of n=2 and n=1 locked modes"). No labeled raw-trace figure with explicit axis values is given in the extracted text.

4. **Condition-number vs. fit-range plots (slides 9, 11, 12).** Each is a small inset:
   - Slide 9: "K for MPID array," y-axis 0–20 (ticks 5,10,15,20), x-axis "Maximum n to fit" 0 1 2 3 4 5.
   - Slide 11: "K for LFS Bp arrays (fitting n=1)," y 0–20, x "Number of poloidal harmonics to fit" 0–6; two curves "m=[1, 2, …]" and "m=[2, 4, …]."
   - Slide 12: "K for HFS Bp arrays (fitting n=1)," y 0–20, x "Number of poloidal harmonics to fit" 0–6; two curves "m=[1, 2, …]" and "m=[4, 8, …]."

> **Not covered / not present:** an explicit phase-vs-toroidal-angle (or phase-vs-position) line plot, an amplitude-vs-position plot, and a "coherence bar" are NOT shown in this deck. Only the φ–θ contour plots, the condition-number insets, and described raw traces appear.

---

## Concrete example values (only those actually appearing)

- **Shots:** `164672` at `t=3140 ms` (slide 8); `158116` at `t=4850 ms` (slide 13). Generic placeholder `shot=123456` (slide 17).
- **Times:** command examples `tmin=2000, tmax=3000` (slide 16); `tmin=3000, tmax=4000`, `slice=3250` (slide 17); `tbmin=2200, tbmax=2800` (slide 21); `smooth=5`, `base=50` (ms).
- **Field ranges (G):** δBp color bar ≈ ±40 G (slide 8); δBp color bar ≈ ±4 G (slide 13).
- **n ranges:** `nmin=1, nmax=3` (slides 17, 20); MPID resolves n ≤ 4; n ≤ 3 → K < 2, n ≤ 4 → K < 5 (slide 9). Locked-mode example n=1 (and n=2/n=1 growth, slide 5). Applied-field example n=2 (slide 13).
- **m ranges:** LFS m=[2,4,6,8,10] well conditioned; HFS m=[4,8,12,…]; combined-range example yielding m=[1,2,3,4,6,10] (slide 20); HFS fit shown for m=6,10,14 (slide 13); locked mode m=2 (slide 8).
- **Array names:** ISLD, MPID, MPI66M, MPI66M_S, PCMPID, NRSMPID, mpi66m.
- **Geometry numbers:** 66 Bp probes (32 HFS + 34 LFS), 64 Br loops; 5 / 10 / 15 poloidal locations; LFS Δθ~160°, HFS Δθ~90°; 14 cm poloidal/vertical resolution; δZ=14 cm, ΔZ=152 cm; Δφ ranges 77°–180° (LFS midplane) and 15°–180° (other arrays).
- **Condition-number thresholds:** warning at K>10, error at K>20.
- **Degrees of freedom:** 55 d.o.f. (bad example), 17 d.o.f. (n=1 tearing example) — slide 14.
- **Hard copy device string:** `hc=13-450-xerox` (slide 17).

---

## Notable quotes (verbatim, with page numbers)

- (p.4) "Slcontour Enables Visualization of '3D Magnetics' Data."
- (p.4) "Visually: raw data traces show dead probes, large drifts, etc."
- (p.5) "3D magnetic diagnostics are aimed primarily at measuring non-rotating MHD modes, stable 3D plasma response, etc. – Time-domain Fourier analysis cannot be used."
- (p.6) "These basis functions are a device for fitting periodic data. They do not necessarily correspond to plasma modes."
- (p.7) "Pseudo-inverse of A yields a linear least-squares fit of coefficients B, for a set of measurements S: B = (AᵀA)⁻¹AᵀS."
- (p.9) "Quality of fit depends on condition number K ≡ max(w_i)/min(w_i) – where w_i are the singular values of the basis matrix."
- (p.9) "Uncertainty of the fit is roughly proportional to K, so small values are desirable."
- (p.9) "Limits built into slcontour: K > 10: warning; K > 20: error message."
- (p.14) "Fitting to 66 MPID pairs is likely to produce meaningless results."
- (p.14) "Narrow the range of n,m until σ starts to increase … and/or …. Widen the range of n,m until K starts to increase."
- (p.16) "Command syntax: --> command=<value>. Unique abbreviations of commands are ok. Use , or ; to separate multiple commands on a single line."
- (p.19) "Slcontour recognizes >95 arrays."
- (p.25) "Selection of basis functions must be guided by quality of fit and SVD condition number."
- (p.26) "Separation of internally and externally sourced fields (in progress) – Combined analysis of Br and Bp sensors."

---

## Digest (unique content)

This 2019 Strait deck is a primary, self-contained tutorial for SLCONTOUR, an IDL command-line tool for spatially fitting DIII-D's "3D" magnetic diagnostics (66 Bp probes + 64 Br loops, all wired as toroidally separated differential pairs that reject the n=0 field). Its three uses are visual/analytic data-quality checking, reliable 1-D toroidal mode decomposition, and rough 2-D poloidal analysis, all built on a cylindrical-Fourier basis fit by the normal-equations least-squares formula B = (AᵀA)⁻¹AᵀS, with fit reliability judged by the SVD condition number K (built-in warning at K>10, error at K>20) and standard deviation σ. The deck is the most explicit source for the actual IDL syntax: launch via `module load slcontour` → `idl` → `slcontour`, then `command=<value>` lines (shot, tmin/tmax, array, nmin/nmax/nstep, mmin/mmax/mstep plus secondary mmin2/mmax2/mstep2, smooth, slice, base/btype/tbmin/tbmax, hc, and the helper commands commands/help/document/view/find/exit). It documents 14 baseline-subtraction algorithms (btype 0-13) for transient, long-pulse, and periodic data, and gives concrete worked examples (shots 164672 @3140 ms and 158116 @4850 ms) shown as φ–θ contour plots of δBp in Gauss. Note that MODESPEC is not mentioned at all, and the only plots are φ–θ contours and small condition-number-vs-fit-range insets — there is no phase-vs-position plot or coherence bar in this document.

---

**Output file:** `docs/research-summaries/04_SLCONTOUR_summary2019.md`
