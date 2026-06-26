# SLCONTOUR (II): 2-Dimensional Sensor Arrays

**Source:** `Strait_Magnetics_20230503_Slcontour(II).pdf`
**Author:** Ted Strait (E. Strait) — DIII-D Magnetics
**Date on slides:** May 3, 2023
**Length:** 27 pages (PDF), footer on every page: "E. Strait / DIII-D Magnetics / May 3, 2023"

> Accuracy note: This summary reports only what is verbatim or clearly present in the document. The slide figures embed IDL contour plots whose surrounding axis/colorbar labels are interleaved in the extracted text. Where a numeric value or label is stated, it is quoted as it appears. Several figure pages (15, 25) only rendered an overlay dashed line on image extraction; their bullet text was used instead and is flagged. The page-14 IDL figure rendered fully and is described from the actual image.

---

## Document overview

This is part II of a presentation series on SLCONTOUR, an IDL command-line tool for DIII-D magnetics. Part I (a separate document) covered 1-D arrays; this part focuses on **2-D sensor arrays** in toroidal angle phi and poloidal angle theta. Stated scope (page 2, verbatim):

- "This presentation will focus on the basics of SLCONTOUR with 2-D arrays (phi, theta)"
- "A future presentation will discuss 2-axis arrays (B_theta, B_r)"

Purpose (page 2): "SLCONTOUR Enables Visualization of '3D Magnetics' Datasets." Non-axisymmetric magnetic features listed:
- Tearing Modes (rotating and locked)
- Kink Modes (e.g. Resistive Wall Modes)
- Applied fields (C-coil and I-coil)
- Stable plasma response to external fields
- Error fields (with footnote: "Direct measurement of error fields is difficult, but they can be measured indirectly through the response of islands or stable kink modes")

The deck's overall arc: define 2-D arrays as combinations of 1-D arrays -> the harmonic basis used -> the least-squares fitting math -> SLCONTOUR commands to set up a 2-D fit -> a worked locked-mode example (shot 174436) with its printed and plotted outputs -> degree-of-freedom and condition-number constraints on 1-D vs 2-D fits -> partial-poloidal-coverage effects on which m values are well-resolved -> LFS and HFS array examples -> guidance/heuristics for the user to optimize the fit, ending with a summary table.

## Magnetic sensors / hardware

Page 3 ("Sensors for 3D Fields are Organized in 1-D Arrays: Constant phi or theta; 2-D Arrays in phi and theta are Defined as Combinations of 1-D arrays"):
- "70 Bp probes (MPI)" and "64 Br loops (ISL)" (Bp sensors and Br sensors)
- Vertical Arrays located at toroidal angles **139 deg and 199 deg**
- Toroidal arrays (named, with "***" markers): MPI/ISL1A, MPI/ISL1B, MPI/ISL79A, MPI/ISL67A, MPI/ISL66M, MPI/ISL67B, MPI/ISL79B
- Sensor map plotted as "Distance along vessel wall (m)" (axis range shown roughly -2 to 5) vs theta (deg, 0 to 360), with regions labeled INBOARD / High Field Side / TOP / Low Field Side / OUTBOARD
- Note: "MPI67A layout includes changes in 2020"

Naming convention abbreviations used throughout: **MPI** = magnetic (Bp) probes; **ISL** = internal saddle loops (Br); **ESL** = external saddle loops; a trailing **D** (e.g. MPID, ISLD) denotes differential paired sensors; the **66M / 67A / 67B / 79A / 79B / 1A / 1B / 139 / 199** suffixes denote toroidal/vertical array locations. Radial labels R0, R+/-1, R+/-2 denote poloidal rows of toroidal arrays.

The two array-name reference tables:

**2-D Paired-sensor arrays (page 5)** — columns: Location | 2D Array Name | 1D arrays included | Total Pairs, given for both BR (saddle loops) and BP (magnetic probes):
- R0, R+/-1 (External): ESLDR01 = ESLD, ESLD67A, ESLD67B; Total 30 (BP side)
- R0, R+/-1: ISLDR01 = ISLD, ISLD67A, ISLD67B (24); MPIDR01 = MPID, MPID67A, MPID67B (30)
- R0, R+/-1, R+/-2: ISLD_LFS (32); MPID_LFS = MPID, MPID67A, MPID67B, MPID79A, MPID79B (38)
- HFS Midplane: ISLD1AB = ISLD1A, ISLD1B (16); MPID1AB = MPID1A, MPID1B (16)
- HFS Mid & Vertical: ISLD_HFS = ISLD1A, ISLD1B, ISLD199 (24); MPID_HFS = MPID1A, MPID1B, MPID199 (24)
- HFS & LFS Midplane: ISLD_MID = ISLD, ISLD1A, ISLD1B (24); MPID_MID = MPID, MPID1A, MPID1B (26)
- R0, R+/-1, HFS Midplane: ISLD_TOR (40); MPID_TOR = MPID, MPID67A, MPID67B, MPID79A, MPID79B, MPID1A, MPID1B (46)
- R0, R+/-1, R+/-2, HFS Mid & Vertical: ISLD_ALL (56); MPID_ALL = MPID, MPID67A, MPID67B, MPID79A, MPID79B, MPID1A, MPID1B, MPID199 (62)

**2-D Single-sensor arrays (page 6):**
- R0, R+/-1 (External): ESLR01 = ESL66M, ESL67A, ESL67B (30, BP side)
- R0, R+/-1: ISLR01 = ISL66M, ISL67A, ISL67B (24); MPIR01 = MPI66M, MPI67A, MPI67B (30)
- HFS Mid & Vertical: ISL_HFS = ISL1A, ISL139 (16); MPI_HFS = MPI1A, MPI139 (16)
- HFS & LFS Midplane: ISL_MID = ISL66M, ISL1A (16); MPI_MID = MPI66M, MPI1A (18)
- R0, R+/-1, HFS Mid & Vertical: ISL_ALL = ISL66M, ISL67A, ISL67B, ISL1A, ISL139 (40); MPI_ALL = MPI66M, MPI67A, MPI67B, MPI1A, MPI139 (46)

## SLCONTOUR (Part II topics)

### What 2-D fitting does and how to set it up
2-D arrays are defined as combinations of the 1-D toroidal/vertical arrays above; the toroidal arrays remove the n=0 field and provide amplitude/phase at each poloidal location, and stacking several poloidal locations lets the tool resolve poloidal (m) harmonics.

**Commands for 2-D array fitting (page 9, "2-D Array Fitting in SLCONTOUR", quoted verbatim from the `-->` prompts):**
- `--> find 2d` — "List the available 2D arrays"
- `--> array=MPID_LFS` — "Select an array (e.g. Bp @ R0, R+/-1, R+/-2)"
- `--> nmin=1,nmax=3,nstep=1` — "Select n range & increment" ("default: nstep=1")
- `--> mmin=2,mmax=8,mstep=2` — "Select m range & increment"
- `--> mmin=1, mmax=4, mstep=1` — "for LFS or HFS arrays on a reduced range Δθ < 2π"
- `--> mmin2=2,mmax2=10,mstep2=4` — "Optional primary and secondary ranges of m" ("May be useful for combined LFS & HFS")
- "If secondary m range is added, only unique m values are used" — "The last example above gives m = [1, 2, 3, 4, 6, 10]"

(Also shown on page 10 as a single combined command line: `--> shot 174436,xmin 3000,xmax 4000,array MPID_LFS`.)

### Worked example (shot 174436) — fetch and fit log
Page 10 ("Example: Fitting Locked Mode with 2-D Array at LFS"). After the fetch command, SLCONTOUR prints "FETCHING RAW DATA" and lists the constituent 1-D arrays of MPID_LFS:
- MPID66M array (R0, 10 probes)
- MPID67A array (R+1, 8 probes)
- MPID67B array (R-1, 8 probes)
- MPID79A array (R+2, 4 probes)
- MPID79B array (R-1, 4 probes)  [as printed; presumably R-2]

Then: "LEFT-HAND helicity, sign(Bt, Ip) = -1 1" with annotation "Needed for 2-D array to determine the sign of m". Then "FITTING HELICAL MODES", echoing `nmin=1, nmax=1` -> `n values = 1`; and `mmin=1, mmax=5, mstep=2` -> `m values = 1 3 5`.

### Printed fit output (pages 11 and 21)
Page 11 printed block (verbatim values):
```
SHOT = 174436   TIME = 3500.00
Array = MPID_LFS ( Bp Pairs 2D LFS R0,R1,R2 )
n = 1
                Ampl.    Phase
All m           32.01   322.73     <- "Amplitude & Phase for each n, vector sum of all m"
m = 1           10.79   327.24     <- "Amplitude & Phase for each n,m"
m = 3           16.86   324.44
m = 5            4.60   305.68
-----------------------------------
Condition number of array = 1.61   <- "Two key figures of merit to watch! Smaller is better."
Standard deviation of fit = 3.16
-----------------------------------
Omitted sensors:
MPID67B022
LMPID037
MPID67B052
41 contour levels: min, max, interval = -54.23  54.23  2.711
Contour plot downsampled x 5 : Time resolution (ms) = 0.10
```
Page 12 is a single slide: "Pause for comments on the condition number?"

Page 21 ("Fits are Equally Good With m=1,3,5 or m=2,4,6") shows two side-by-side printed blocks for the same SHOT 174436 / TIME 3500.00 / MPID_LFS / n=1:
- m=1,3,5 fit: All m = 32.01 / 322.73; m=1 = 10.79/327.24; m=3 = 16.86/324.44; m=5 = 4.60/305.68; Condition number = 1.61; Standard deviation = 3.16
- m=2,4,6 fit: All m = 31.43 / 321.32; m=2 = 16.51/327.96; m=4 = 11.75/323.38; m=6 = 4.03/285.99; Condition number = 1.59; Standard deviation = 3.63
- Annotation: "Condition number and std. deviation are almost identical"

### Plotted output (3 figure pages)
- **Page 13, "Plotted Output (page 1): Raw Data"** — callouts: "Map of many pair difference connections", "Raw data: 31 time traces after subtraction of baseline offsets", "Pointname of the pair and toroidal angles of its probes", "3 bad probes are omitted".
- **Page 14, "Plotted Output (page 2): Results of Fit"** — described from the actual rendered image below.
- **Page 15, "Plotted Output (page 3): Mode Structure vs. phi and theta"** — bullets (text only; contour image did not render): "Amplitude peaks at the midplane"; "Helical structure is clear"; "Pitch of δB at the LFS wall is consistent with m~3"; labeled MPID_LFS - Bp Pairs.

## MODESPEC

**Not covered.** MODESPEC is not mentioned anywhere in this document. (This deck is exclusively about SLCONTOUR 2-D array analysis.)

## Analysis methods / math

**Harmonic basis (page 7, "2-D Array Data Is Represented by Toroidal & Poloidal Harmonics"):** The 2-D toroidal fit uses "a simple basis set: cylindrical Fourier harmonics in phi and θ." The field model is, as written:
- delta-B(phi, theta) = Re[ sum over n,m of B_{n,m} e^{i(n phi - m theta)} ], with B(t) complex coefficients
- Equivalently delta-B(phi, theta) = b_0 + sum [ b_{n,m} cos(n phi - m theta) + a_{n,m} sin(n phi - m theta) ], with b(t), a(t) real coefficients
- Notes: "DIII-D 'machine angle' (clockwise)"; "coding uses sine, cosine"; Im(B) = a, and a_0 = 0.
- Caveats (verbatim): "Toroidal symmetry => e^{in phi} is usually a reasonable model for the toroidal dependence of a plasma mode"; "Poloidal asymmetry => the poloidal variation of a plasma mode is NOT well described by a single term e^{im theta}"; "The n,m basis functions are a device for fitting periodic data. They do not necessarily correspond to plasma modes."

**Least-squares fit (page 8, "Least-Squares Fit Uses 'Normal Equations' Method"):** cites W. H. Press et al., *Numerical Recipes in Fortran*, 2nd ed., Cambridge Univ. Press, 1994, p. 665.
- Each basis function k evaluated at each sensor j. "Sensor j" is either a single probe at (phi_j, theta_j), giving A = e^{i(n phi_j - m theta_j)}, OR a differential pair at poloidal angle theta_j and two toroidal angles phi_{j,1}, phi_{j,2}, giving A = e^{i(n phi_{j,1} - m theta_j)} - e^{i(n phi_{j,2} - m theta_j)} (pair difference -> "indicates spatial averaging").
- "Although the sensors and basis functions are 2-D in phi and θ, the indexing treats them as 1-D lists. Then the fitting calculation is the same as for 1-D arrays":
  - S_j = A_{jk} B_k ("Basis matrix" A of orthogonal basis functions k evaluated at sensors j)
  - "Pseudo-inverse of A gives a 'detection matrix' D": D = A^{-1} = (A^T A)^{-1} A^T
  - "D yields a linear least-squares fit of coefficients B": B_k = D_{kj} S_j, for any set of measurements S

**Degree-of-freedom constraints:**
- 1-D (page 16): fit to modes n=1..N needs a toroidal array with at least **2N+1 sensors** (1 DOF for n=0, 2 per nonzero n). For differential pairs, n=0 is removed so only 2N free parameters — but "A set of 2N sensors can make only 2N-1 independent differential pairs," so "a minimum of 2N+1 individual sensors are required to make 2N independent pairs."
- 2-D (page 17): toroidal array needs >=2N+1 for n=1..N; poloidal array needs >=2M+1 for m=1..M; but a 2-D array needs only **M toroidal arrays** to resolve M poloidal harmonics (the toroidal arrays remove n=0 and give amplitude/phase at each theta). More generally, a fit to [n=1..N] x [m=1..M] requires a 2-D array with at least **(2N+1)M sensors**: "2NM" (cos/sin harmonics for NxM combinations) "+ M" (a constant term at each poloidal position for poloidal asymmetry of the n=0 field) = "2NM + M degrees of freedom."

**Partial poloidal coverage (page 18):** If a poloidal/2-D array does not span full 2pi, the well-resolved harmonics are not necessarily m=1,2,3,...
- Maximum poloidal wavelength = Δθ -> smallest poloidal mode number m_min = 2π/Δθ.
- A poloidal array spanning Δθ can resolve m = 1,2,3,... x (2π/Δθ).
- Example: a 2-D array covering only the low-field side spans only Δθ = π, so it can only give an independent fit of m = [2, 4, 6, ...].
- "Other sets of m can be used. The corresponding sets of fitting functions may be linearly independent but will not be orthogonal on a domain of width Δθ -> The condition number for a non-orthogonal set of fitting functions is likely to be poorer."
- Repeated caveat: "These basis functions are a device for fitting periodic data. They do not necessarily correspond to plasma modes. They need not match the structure outside the measurement domain."

**Two figures of merit (emphasized repeatedly):** Condition number K (of the array; depends on choice of n,m) and Standard deviation σ of the fit (depends on n,m and the data). "Smaller is better."

**User optimization heuristics (pages 26-27, "2-D Fitting Requires Optimization by the User"):**
- "Sparse data requires an intelligent choice of n,m." Bad example: n<=3 and m<=3n<=9 => 55 degrees of freedom; "Fitting to 66 MPID pairs is likely to produce meaningless results."
- General approach: choose an initial physically justified n,m range (Example: n=1 tearing mode, try n<=2, m<=2n<=4 => 17 degrees of freedom). "Narrow the range of n,m until σ starts to increase ... and/or ... Widen the range of n,m until K starts to increase."
- Page 27: minimum m from poloidal range, m_min ~ 2π/Δθ; "Typically use mstep = mmin, so that m = [1,2,3,...] x mmin"; number of independent poloidal positions sets the max number of m's.

## Visualizations to reproduce

**Page 14 — "Results of Fit" composite (rendered image; describe exactly):** Title across top-left "Shot 174436  MPID_LFS (Bp Pairs)". Four panels:
1. Top-left time trace: y-axis "Phase (deg)" 0–~350 (ticks 0,100,200,300), x-axis = Time (ms). Trace is a black/saturated band early then a sawtooth (mode rotation) phase signal.
2. Middle-left time trace: y-axis "delta-B (G)" 0–60 (ticks 0,10,20,30,40,50,60), x-axis Time (ms). Amplitude grows to a peak near t~3450 ms then settles ~25–35 G.
3. Top-right scatter: y-axis "Fit", x-axis "Measured", both -40 to 40 G, with open squares scattered along the y=x diagonal line; annotated "m = 1 3 5" and "n = 1"; title "Sensor data".
4. Bottom-left contour (the main plot): x-axis "Time (ms)" ~3100–~3950 (ticks 3200,3400,3600,3800); y-axis "Phi (deg.)" 0–360 (ticks 0,90,180,270,360). Diagonal stripes (rotating mode). Color scale is a rainbow/jet-like map (black/dark blue -> blue -> red/orange -> yellow/white) with vertical colorbar labeled in Gauss from about -40 to +40 (ticks ~ -40,-20,0,20,40).
5. Bottom-right line plot: title "t=3500.0, Theta=0.0"; x-axis "delta-B (G)" -40 to 40; y-axis Phi (deg.) 0–360. A dashed sinusoidal fitted curve (one full toroidal period, n=1) overlaid with measured data points (diamonds and plus markers).

Slide callouts (page 14 text): "Toroidal phase (n=1)"; "Amplitude (n=1)"; "Comparison of fitted values vs. raw data (∆B of pairs)"; "Contour plot of fitted δB vs. time and toroidal angle"; "Comparison of fitted curve and measured local δB, evaluated at LFS midplane, θ = 0".

**Page 1 / Page 4 — title-slide and locked-mode contour (theta vs phi):** A 2-D contour of bBp (Bp, in Gauss) on axes Phi (deg.) 0–360 (x) vs Theta (deg.) (y), with y tick labels at -90 (BOT), 0 (OUTBOARD), 90 (TOP), 180 (INBOARD), 270 (BOT) — i.e. theta runs across BOT/OUTBOARD/TOP/INBOARD. A vertical colorbar in G with ticks at approximately -40, -20, 0, 20, 40. Page 4 labels it shot **164672, t=3140 ms**.

**Page 15 — MPID_LFS mode structure (theta vs phi contour):** Axes Phi (deg.) 0–360 vs Theta (deg.) with labels TOP (90), OUTBOARD WALL (0/45), BOT (-90). Color scale in Gauss with ticks ~ -30,-20,-10,0,10,20,30 (the "45" and "-45" appear as theta tick labels). Annotated "m = 3". (Contour image did not render on extraction; described from slide text + analogous pages.)

**Page 20 — condition-number-vs-harmonics plot (LFS):** y-axis "K for LFS Bp arrays (fitting n=1)" 0–20 (ticks 0,5,10,15,20); x-axis "Number of poloidal harmonics to fit" 0–6 (ticks 0,2,4,6). Two curves: "m=[2,4,...]" (stays low/well-conditioned out to 5 harmonics) and "m=[1,2,...]" (rises = poorly conditioned beyond ~3 harmonics).

**Page 24 — condition-number-vs-harmonics plot (HFS):** y-axis "K for HFS Bp arrays (fitting n=1)" 0–20; x-axis "Number of poloidal harmonics to fit" 0–6. Curves: "m=[4,8,...]" (well-conditioned up to 5 harmonics) and "m=[1,2,...]" (very poorly conditioned beyond 2 harmonics).

**Page 22 — two side-by-side theta-vs-phi contours** ("Fitting m=1,3,5" vs "Fitting m=2,4,6"), both MPID_LFS - Bp Pairs. Axes Phi (deg.) 0–360 vs Theta (deg.) (TOP 90 / OUTBOARD WALL 0,45 / BOT -90); color in Gauss (one panel ~ -30..30, other ~ -20..20). Left annotated "m = 3", right annotated "m ~ 3.3".

**Page 25 — HFS array fit contour (theta vs phi):** shot **158116, t=4850 ms**. Axes Phi (deg.) 0–360 vs Theta (deg.) with ticks 90 (TOP), 135, 180, 225, 270 (BOT) and label INBOARD WALL. Color scale "bBp (G)" with ticks -4,-2,0,2,4. Annotated "Fitting n = 2, m = 6,10,14" and "m ~ 6.5". (Contour image did not render on extraction; described from slide text.)

**Page 19 / 23 — sensor-layout schematics:** "Distance along vessel wall (m)" (y, ~ -2 to 5) vs theta (deg., 0–360), regions INBOARD / High Field Side / TOP / Low Field Side / OUTBOARD; used to illustrate LFS toroidal arrays (R0, R+/-1, R+/-2) and the HFS vertical array footprint.

## Concrete example values (only as appearing)

- **Shot 174436**, primary worked example. xmin 3000, xmax 4000; TIME = 3500.00 ms. Array MPID_LFS ("Bp Pairs 2D LFS R0,R1,R2").
  - n=1; m=1,3,5 fit: All m = 32.01 G / 322.73 deg; m=1 = 10.79/327.24; m=3 = 16.86/324.44; m=5 = 4.60/305.68. Condition number = 1.61; Std deviation = 3.16.
  - n=1; m=2,4,6 fit: All m = 31.43/321.32; m=2 = 16.51/327.96; m=4 = 11.75/323.38; m=6 = 4.03/285.99. Condition number = 1.59; Std deviation = 3.63.
  - 41 contour levels: min, max, interval = -54.23, 54.23, 2.711. Contour plot downsampled x 5; Time resolution = 0.10 ms.
  - Omitted (bad) sensors: MPID67B022, LMPID037, MPID67B052 ("3 bad probes are omitted"; "31 time traces" of raw data).
  - LEFT-HAND helicity, sign(Bt, Ip) = -1, 1.
  - MPID_LFS constituents: MPID66M (R0, 10 probes), MPID67A (R+1, 8), MPID67B (R-1, 8), MPID79A (R+2, 4), MPID79B (4); MPID_LFS = 38 pairs total.
- **Shot 164672, t=3140 ms** (page 4): locked tearing mode, "Fit to 66 Bp probes yields m=2 / n=1 structure"; "32 HFS (inboard) locations" and "34 LFS (outboard) locations."
- **Shot 158116, t=4850 ms** (page 25): HFS array fit, "Inboard side (HFS) response to n=2 applied field => m ~ 10 locally"; fitting n=2 with m = 6, 10, 14; "m ~ 6.5"; "Fitting HFS arrays only, in a time slice with minimum LFS response." Vertical resolution dZ = 14 cm, dθ ~ 11 deg => max m ~ 360/(2 dθ) ~ 16; Vertical range DZ = 152 cm, Dθ ~ 93 deg => min m ~ 360/Dθ ~ 4.
- **LFS arrays (pages 19-20):** R0, R+/-1, R+/-2 span ~160 deg in poloidal angle; 5 poloidal locations => should resolve 5 poloidal harmonics; λ_θ,max ~ π => m_min ~ 2; resolvable m are integer multiples of m=2; "Decomposition of LFS data in 5 harmonics m=[2,4,6,8,10] is well conditioned"; "m=[1,2,3,...] decomposition is poorly conditioned for more than 3 harmonics"; "Poloidal spacing of LFS arrays may limit m_max < 5-6 to avoid spatial aliasing."
- **HFS arrays (pages 23-24):** vertical array spans ~90 deg in poloidal angle; 10 poloidal locations => should resolve ~5 poloidal harmonics; "no toroidal resolution except at the midplane"; λ_θ,max ~ π/2 => m_min ~ 4; "Decomposition of HFS data in harmonics m=[4,8,12,...] is well conditioned up to 5 harmonics"; "m=[1,2,3,...] decomposition is very poorly conditioned for more than 2 harmonics"; "Av. spacing ~ 10 deg between sensors may limit m_max < 18 to avoid spatial aliasing."
- **n,m secondary-range example (page 9):** mmin2=2, mmax2=10, mstep2=4 combined with mmin=1,mmax=4,mstep=1 gives m = [1, 2, 3, 4, 6, 10].
- **DOF examples (page 26):** n<=3, m<=3n<=9 => 55 DOF (called a bad example for 66 MPID pairs); n<=2, m<=2n<=4 => 17 DOF (recommended start for an n=1 tearing mode).

**Summary table (page 27, "rough guide for fitting with a single n value"):**

| | All Arrays | LFS: R0,R+/-1,R+/-2 | LFS: R0,R+/-1 | HFS |
|---|---|---|---|---|
| Δθ = Poloidal range | 360 deg = 2π | 165 deg ~ 2π/2 | 110 deg ~ 2π/3 | 90 deg ~ 2π/4 |
| m_min, m_step ~ 2π/Δθ | 1 | 2 | 2 or 3 | 4 |
| M = number of m's* | 10 | 5 | 3 | 5 |
| Widest sets of m to fit | 1,2,...8 | 2,4,6,8,10 | 2,4,6 and 3,6,9 | 2,6,10,14,18 and 4,8,12,16,20 |

*"One for a toroidal array, and 0.5 for a vertical array pair." Accompanying notes: "Additional n values may reduce the number of m values that can be fitted"; "Keep the condition number low!"

## Notable quotes (verbatim, with page #)

- p.2: "SLCONTOUR Enables Visualization of '3D Magnetics' Datasets"
- p.2: "This presentation will focus on the basics of SLCONTOUR with 2-D arrays" ... "A future presentation will discuss 2-axis arrays"
- p.7: "The n,m basis functions are a device for fitting periodic data. They do not necessarily correspond to plasma modes."
- p.7: "Poloidal asymmetry => the poloidal variation of a plasma mode is NOT well described by a single term e^{im theta}"
- p.8: "Although the sensors and basis functions are 2-D in phi and θ, the indexing treats them as 1-D lists. Then the fitting calculation is the same as for 1-D arrays"
- p.10: "LEFT-HAND helicity, sign(Bt, Ip) = -1 1" ... "Needed for 2-D array to determine the sign of m"
- p.11: "Condition number of array = 1.61" / "Standard deviation of fit = 3.16" / "Two key figures of merit to watch! Smaller is better."
- p.12 (whole slide): "Pause for comments on the condition number?"
- p.16: "A set of 2N sensors can make only 2N-1 independent differential pairs." ... "a minimum of 2N+1 individual sensors are required to make 2N independent pairs"
- p.17: "a fit to modes [n=1, 2, … N] × [m=1, 2, … M] requires a 2-D array with at least (2N+1)M sensors"
- p.18: "a 2-D array covering only the low-field side spans only Δθ = π, and therefore can only give an independent fit of m = [2, 4, 6, … ]"
- p.21: "Fits are Equally Good With m=1,3,5 or m=2,4,6" ... "Condition number and std. deviation are almost identical"
- p.22: "Pitch of δB at the LFS wall is still near m=3, although the 2nd fit does not explicitly include m=3"
- p.25: "HFS Array Fit Shows High-m Plasma Response to Applied n=2 Perturbation"
- p.26: "Fitting to 66 MPID pairs is likely to produce meaningless results"
- p.27: "Keep the condition number low!"

---

### Digest (unique content)

This is Strait's second SLCONTOUR tutorial, dedicated entirely to 2-D (phi, theta) magnetic sensor arrays and how to fit them — MODESPEC is not discussed at all. Its uniquely valuable content is (1) the two reference tables of SLCONTOUR 2-D array names (paired ISLD/MPID/ESLD and single ISL/MPI/ESL variants, with their constituent 1-D arrays and pair counts) and the exact command sequence (`find 2d`, `array=`, `nmin/nmax/nstep`, `mmin/mmax/mstep`, plus secondary `mmin2/mmax2/mstep2`), and (2) a clear treatment of the linear-algebra fit (cylindrical Fourier e^{i(n phi - m theta)} basis, normal-equations pseudo-inverse "detection matrix" D = (A^T A)^{-1} A^T, citing Numerical Recipes p.665) together with the degree-of-freedom counting ((2N+1)M sensors; 2NM+M DOF). The deck's central practical message is that with sparse, partial-poloidal-coverage arrays the well-resolved poloidal harmonics are integer multiples of m_min ~ 2π/Δθ (LFS => m=2,4,6,8,10; HFS => m=4,8,12,...), and the user must tune n,m ranges to minimize both the array condition number K and the fit standard deviation σ. Three real shots anchor the examples: 174436 (rotating/locked LFS mode, full printed+plotted output), 164672 t=3140 ms (m=2/n=1 locked mode over 66 Bp probes), and 158116 t=4850 ms (high-m HFS plasma response to an n=2 applied field). A repeated caveat is that these n,m basis functions are merely a fitting device and "do not necessarily correspond to plasma modes."

**Output file:** `docs/research-summaries/08_Slcontour_II_2023.md`
