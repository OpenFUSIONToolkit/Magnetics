# SLCONTOUR (III): 2-Axis Sensor Arrays — Summary

**Source PDF:** `resources/DIII-D IDL Command Line Tools/Strait_Magnetics_20230621_Slcontour(III)_Update.pdf`
**Author/footer (verbatim, every page):** "E. Strait / DIII-D Magnetics / June 21, 2023"
**Title slide author line:** "Ted Strait" (title slide); footer attributes to "E. Strait"
**Date:** June 21, 2023 (with an "Update 6/22/23")
**Length:** 42 pages
**Producer metadata:** macOS Quartz PDFContext; CreationDate D:20230623

> NOTE ON ACCURACY: This deck is mostly slide titles + bullet text plus several embedded plot images. Image-only plot pages (32, 33, 34, 36, 37) were read by extracting the page images and reading the axis labels/legends directly off them. Where the underlying PDF text-extraction garbled physics subscripts (e.g. "B_r", "B_theta", "B_phi" run together), I have reconstructed conservatively and flagged uncertainty. Quotes marked verbatim are copied from extracted text or read off the figure.

---

## Document overview

This is the third in a series of DIII-D magnetics presentations by E. Strait on the SLCONTOUR / SLCONTOUR2 IDL tools. Per the title slide (p.1):

- "(Apr. 20, 2023) SLCONTOUR (I): 1-D Sensor Arrays"
- "(May 3, 2023) SLCONTOUR (II): 2-D Sensor Arrays"
- This deck: "SLCONTOUR (III): 2-Axis Sensor Arrays"
- "Update 6/22/23: Added lists of 2-axis arrays available in SLCONTOUR2 (new slides 38-41)"

The technical content (slides 2-28) is "Adapted from" an APS-DPP 2018 invited/contributed talk: "Distinguishing Internal and External Sources of Measured '3D' Magnetic Fields in the DIII-D Tokamak" by E.J. Strait (General Atomics) and R.M. Sweeney (ITER Organization), presented at the 60th Annual Meeting of the APS Division of Plasma Physics, Portland, Oregon, Nov. 5-9, 2018 (p.2). The remainder (slides 29-42) is the SLCONTOUR2 how-to and array reference.

The deck has an explicit outline (repeated on pp. 11, 15, 24):
- Introduction
- Analysis Method
- Example 1: Tearing Mode Locking
- Example 2: Applied n=1 Field (no plasma)
- Conclusions

Core physics goal (p.3): separate the plasma's contribution to externally-measured "3D" magnetic fields from contributions of "external coils, eddy currents, etc." (i.e. internal-source vs external-source decomposition).

---

## Magnetic sensors / hardware

From "DIII-D Diagnostics Provide Spatially Resolved 2-Axis Measurements Between Plasma and Wall" (p.12):

- "n <= 3 resolution at 5 poloidal locations; n <= 4 at Low Field Side midplane"
- "Single-n detection (amplitude & phase) at 15 poloidal locations"
- "This presentation uses only the five LFS arrays"
- The accompanying schematic (poloidal cross-section, "Distance along vessel wall (m)" vs theta in deg, theta axis 0-90-180-270-360) labels probe groups: INBOARD, HFS, TOP, LFS, OUTBOARD. Text fragments give sensor counts as "66 Bq probes" and "64 Br loops" (i.e. Bq/poloidal probes and Br/radial loops — exact numbers garbled by extraction; the fragment reads "66 Bq probes" / "64 Br loops").
- Reference (p.12): "J.D. King, et al., RSI 85, 083503 (2014)."

Requirements for the measurement (p.10, "Requirements for Tokamak Measurements"):
- "2-axis measurements (dB_normal and dB_tang)" — "For tokamak helical perturbations, use dB_r and dB_q" (i.e. radial and poloidal).
- "Sensors between internal and external field sources" — isolation of the plasma field "limits the time resolution to ... of first-wall components in front of the sensors", with the condition written as "omega << tau^-1 = L/R".
- Spatial resolution: "Toroidal resolution -> phase & amplitude of toroidal modes"; "Toroidal & poloidal resolution -> spatial structure of fields"; "Rejection of toroidally symmetric field".

The SLCONTOUR2 array tables (pp. 38-41) name the actual sensor channels (see "Concrete example values").

---

## SLCONTOUR / SLCONTOUR2 (Part III update topics)

### What SLCONTOUR2 is

- "SLCONTOUR2 is a special version for 2-axis data" and "Should be equivalent to SLCONTOUR when used for 1-axis data" (p.29).
- Closing-slide status (p.42, "SLCONTOUR2 is still under development / Please try it!"):
  - "It is reasonably stable -- no major changes in the last year or so"
  - "It seems to agree with SLCONTOUR on single-axis array data" but "there are small differences in user options, details of the plots, ..."
  - "My goal is to consolidate all features into SLCONTOUR2, rather than maintain separate versions for 1-axis and 2-axis data"
  - Invites bug reports / feature requests.

### Commands / workflow literally shown (p.29, "How to run SLCONTOUR with 2-axis arrays")

```
IDL> slcontour2_test          Run the latest version
-->find 2axis 2D pairs         Search for an array name
8 Matches found
MPISLD_R01   2axis Pairs 2D LFS R0,R1
MPISLD_LFS   2axis Pairs 2D LFS R0,R1,R2
MPISLD1AB    2axis Pairs 2D HFS Mid-A,B
MPISLD_HFS   2axis Pairs 2D HFS Mid+Vert
MPISLD_TOR   2axis Pairs 2D LFS/HFS Mid+R0R1R
MPISLD_ALL   2axis Pairs 2D LFS/HFS All
PCMPSLDR01   2axis Pairs 2D LFS R0,R1 (PCS)
NRMPSLDR01   2axis Pairs 2D LFS R0,R1 (PCS-Comp)
-->array MPISLD_LFS            Specify the desired array name
--> Enter shot, xmin, xmax, etc. . . .
```

(Annotations in the right margin are verbatim as shown: "Run the latest version", "Search for an array name", "Specify the desired array name".)

### Input parameters (p.30, "Typical set of input parameters", via `-->view`)

Verbatim parameter dump (with the slide's own right-margin annotations noted):

```
-->view
SHOT     = 174436
ARRAY    = MPISLD_LFS  ... MPISLD_LFS 2axis Pairs 2D LFS R0,R1,R2
DCTYPE   = 1           ... Decomposition: B_r B_p        [annotation: "Decomposition type"]
XMIN     = 3200.000    XMAX = 4000.000   I3BCORRECT= ON
XXMIN    = 3350.000    XXMAX = 3600.000  ZOOM = ON
SLICE    = 3550.000    SMOOTH = 0.000    POSTSMOOTH= 0.000
BASE     = 100.000     BTYPE = 1   ... baseline: early data
THETASLI = 0.000       PHISLICE= 180.000
STYPE    = 0           ... Toroidal slice
COMP     = N
YLOG     = 0
ZMIN     = -50.000     ZMAX = 50.000     NCLEVEL= 41
NMIN     = 1           NMAX = 1          NSTEP = 1
MLIST    = 1 3 5       [annotation: "Can enter arbitrary list of m values to fit"]
NPLOTMIN = 0           NPLOTMAX = 99     DTYPE = 1   ... fitted data
OMIT     = ISLD67A112 MPID66M247 LMPID037 MPID67B052 LMPID157 MPID79B277
```

Key params: `DCTYPE` selects decomposition type; `XMIN/XMAX` and `XXMIN/XXMAX` are time windows (the zoom window with `ZOOM=ON`); `SLICE` is the time slice (3550 ms); `BTYPE`/`BASE` set baseline ("baseline: early data"); `MLIST` is the user-entered list of poloidal m values to fit; `NMIN/NMAX` set toroidal n; `ZMIN/ZMAX/NCLEVEL` set the contour color-scale range (-50 to +50, 41 levels); `OMIT` is a list of excluded sensor channels.

### `dctype` command — decomposition switch (pp.31, 35)

- `-->dctype 1` -> "Plot results as B_r and B_p" -> "2-axis decomposition: B_r B_p"
- `-->dctype` (no arg) prints the menu (p.35):
  ```
  Select type of 2-axis decomposition:   [current: B_r B_p]
  1 = B_r B_p
  2 = B_in B_ex
  ```
- `-->dctype 2` -> "Plot results as B_in and B_ex" -> "2-axis decomposition: B_in B_ex"

So the tool supports two 2-axis decomposition outputs: (1) the raw measured radial/poloidal pair (B_r, B_p) and (2) the internally-/externally-sourced pair (B_in, B_ex).

### Printed text output (pp.31, 35)

Output for `dctype 1` (p.31), verbatim:
```
2-axis decomposition: B_r B_p
SHOT = 174436   TIME = 3550.00
Array = MPISLD_LFS( 2axis Pairs 2D LFS R0,R1,R2 )
s = +1 (B_r )  -1 (B_p )        [s = index for spatial component]
n = 1   1                        [Toroidal mode number]
          Ampl.  Phase    Ampl.  Phase
All m    13.22   24.71    27.52  287.72
m = 1     5.20   46.71     9.69  292.34
m = 3     8.18   36.59    15.25  285.97
m = 5     3.65  300.85     2.63  280.89
-----------------------------------
Condition number of array = 2.49
Standard deviation of fit  = 1.53
```

Output for `dctype 2` (p.35), verbatim:
```
2-axis decomposition: B_in B_ex
s = +1 (B_in)  -1 (B_ex)
n = 1   1
          Ampl.  Phase    Ampl.  Phase
All m    20.34   19.99     7.24  191.34
m = 1     7.30   30.80     2.70  178.92
m = 3    11.54   23.14     4.06  175.17
m = 5     2.59  329.38     1.85  258.92
-----------------------------------
Condition number of array = 2.49
Standard deviation of fit  = 1.53
```

(Note the same condition number 2.49 and std dev 1.53 in both — B_in/B_ex is a recombination of the same fit.)

### Plot pages produced by the tool

Three plot "pages" per decomposition (titles verbatim):
- "Plots, p. 1: Raw data" (p.32) — same regardless of dctype.
- dctype 1: "Plots, p. 2: Time evolution (B_r, B_p)" (p.33); "Plots, p. 3: Mode structure (B_r, B_p)" (p.34).
- dctype 2: "Plots, p. 2: Time evolution (B_in, B_ex)" (p.36); "Plots, p. 3: Mode structure (B_in, B_ex)" (p.37).

See "Visualizations to reproduce" for exact axes/units/ranges read off the figures.

---

## MODESPEC

Not covered. MODESPEC is not mentioned anywhere in this document.

---

## Analysis methods / math

### Phase-shift principle (pp.5-8)

- For a planar current sheet at x=0 periodic in z (p.5): "Bx is continuous at x=0, but Bz reverses sign across x=0"; "Bz is phase-shifted in the z-direction by +90deg, at the right of the source; -90deg, at the left of the source." Conclusion: "Phase shifts distinguish which side of the source the measurements are seeing."
- Cylindrical analog (p.6): current sheet at r=r0 periodic in theta; "Br is continuous at r=r0, but Bq reverses sign across r=r0"; "Bq is phase-shifted in the q-direction by +90deg, outside of the source; -90deg, inside of the source."

### Scalar-potential / Laplace formulation (p.7, "Method Based on General Principles of E & M")

- "Magnetic field between the plasma and conductors is represented by a scalar potential that obeys Laplace's equation: del^2 Phi = 0"
- "Phi on a closed surface ... uniquely determines Phi and B inside (if no currents inside) -- Also defines a virtual surface current that produces the same B inside"
- A closed "observation" surface divides space: internal field from external sources = a virtual surface current just OUTSIDE the surface; external field from internal sources = a virtual surface current just INSIDE the surface; together they reproduce the total field.
- References (p.7): "A. Boozer, Nuclear Fusion 55, 025001 (2015)." and "J.D. Jackson, Classical Electrodynamics (1962)."

### Historical note (p.9)

- "This Principle Has Been Known for over 180 Years!" — Carl Friedrich Gauss, *Allgemeine Theorie des Erdmagnetismus* (1839); English translation cited "K.-H. Glassmeier & B. T. Tsurutani, Hist. Geo Space Sci. 5, 11 (2014)." Gauss mapped Earth's surface field, inferred the source is inside the Earth, and "Gauss' algorithm is well known to present planetary scientists" — leads to "separation of planetary and external sources of field."

### Cylindrical-harmonic expansion (pp.13-14)

- Scalar potential satisfies del^2 Phi = 0 (p.13). In the "straight tokamak" limit, the solution for a cylindrical current distribution at r=a is expanded in cylindrical harmonics of the form Phi(r,theta,phi) = sum_{m,n} +/- A_{m,n} (r/a)^{+/-m} e^{i m theta} e^{i n phi}. Note (verbatim): "Basis functions are NOT necessarily plasma modes." Upper/lower signs apply to measurements at r<a and r>a.
- Field components (B = grad Phi): B_r and B_theta expansions both carry (r/a)^{+/-m-1}; "B_theta - B_r phase shifts distinguish inner and outer solutions" (p.13).

### Internal/external decomposition (p.14, "Combining the Measured B_r and B_theta Fields Gives the Internal and External Contributions")

- Data fitted to cylindrical harmonics: B_r^meas(theta,phi) = sum_{m,n} b_r(m,n) e^{i m theta} e^{i n phi} (and similar for B_theta).
- Laplace constraint relating components (verbatim): "b_theta(m,n) = +/- i b_r(m,n)" with "'-' applies to sources at r<a" and "'+' applies to sources at r>a".
- Internal (r<a) and external (r>a) contributions for each (m,n):
  - b_r^int = (b_r + i b_theta)/2
  - b_r^ext = (b_r - i b_theta)/2
  - and b_r = b_r^int + b_r^ext; b_theta = b_theta^int + b_theta^ext = -i b_r^int + i b_r^ext
  - "Use these eqs for m>0. Flip the signs of i for m<0."
- "Then sum the m,n terms to reconstruct B^int(theta,phi) and B^ext(theta,phi)."

### Wall-torque relation (p.20)

- Wall torque per area written as proportional to: "dF/dA ~ B_r^plasma B_r^wall sin(Delta phi)" (the slide labels the y-axis "dF/dA (N/m)" — see figure note).

### Conclusions / method status (p.28)

- "Spatial phase shifts between normal and tangential magnetic field components distinguish the location of the source."
- Measurement requires: 2-axis data (normal & tangential), sensors between the field sources, and spatial resolution of toroidal/poloidal asymmetries.
- "Decomposition of tearing mode fields into plasma and wall contributions appears successful."
- "Resolution of fields from non-axisymmetric coils seems plausible -- more challenging due to wide poloidal spectrum."
- Reference (p.28): "R.M. Sweeney and E.J. Strait, Phys. Plasmas 26, 012509 (2019). 'Decomposing magnetic field measurements into internally and externally sourced components in toroidal plasma devices'".

---

## Visualizations to reproduce (axes/units/ranges/colors AS SHOWN)

All contour plots use the same IDL rainbow color scale: black/dark blue (most negative) -> blue -> purple/red -> orange -> yellow/white (most positive), labeled "Gauss" or "delta-B (G)", with the colorbar ticks at -40, -20, 0, 20, 40.

### 1. Example-1 physics figures (Shot 163060) — bullet-described diagnostic contour plots (pp.16-23)

These are 2-panel contour plots, B_r (top) and B_theta/B_q (bottom) unless noted. Two figure modes appear:

- **Time-evolution mode** (pp.17, 21): each panel is a contour of phi (label "q", deg) on y-axis 0/90/180/270/360 vs Time (ms) on x-axis 2700-2800; a side line trace shows amplitude in G (axis 0,20,40 / and 360,270,180,90). Vertical markers at "2720 ms" and "2760 ms". Titles: "B_q & B_r - Time Evolution" (p.17); "B_wall & B_plasma - Time Evolution" (p.21, with note "Harmonics fitted: n=1, m=[1, 3, 5]").
- **Spatial-structure mode** (pp.18, 19, 22, 23, 26, 27): contour of e/theta (deg, y-axis ~ -40..+40 region with side -50..50 G) vs q (deg, x-axis 0-90-180-270-360) at a fixed time. Color scale "(G)" ticks -50, 0, 50 and panel y-tick -40..40. Times labeled "t = 2720 ms" (before locking) and "t = 2760 ms" (after locking).

Specific captioned plots (Shot 163060 unless noted):
- p.16 "Interpretation of Single-Component dB Data Can Be Confusing" — m/n = 2/1 tearing mode that grows and locks.
- p.17 B_q & B_r time evolution: B_r increases rapidly ("plasma field penetrates the wall"); B_q decreases slightly.
- p.18 before locking (t=2720): B_r "is shielded out of the wall -- By mode rotation"; B_q "has strong helical structure -- Mode plus out-of-phase eddy currents".
- p.19 after locking (t=2760): B_r "of mode has penetrated the wall"; B_q and B_r "have similar helical structure -- With ~90deg phase shift".
- p.20 "2-Axis Measurement Separates B_r^plasma and B_r^wall" — line plot, y-axis "bB (Gauss)" 0-30 (curves B_plasma, B_wall, B_r) plus lower panel "dF/dA (N/m)" 0-0.10 (0.05 tick) vs Time 2700-2800 ms; note "At locking (2740-2750 ms)" and "Wall torque has a sudden peak".
- pp.21-23 wall/plasma decomposition time-evolution and spatial-structure.

### 2. C-coil example figures (Shot 176317) (pp.25-27)

- p.25: illustration of C-coil ("toroidal array of 6 coils") geometry; slide note "Figure is for illustration only. Some details may not be accurate."
- p.26 "B_q & B_r - Spatial Structure of C-coil Field": B_r "up/down symmetric structure"; B_q "up/down anti-symmetric structure". Same contour layout/scale as above.
- p.27 "B_coil & B_plasma - Spatial Structure of C-coil Field": B_coil up/down symmetric ("Similar to B_r, as expected"); residual B_plasma "~5 G -> External field is eliminated to within ~10%".

### 3. SLCONTOUR2 tool output plots (Shot 174436, MPISLD_LFS) — read off figures

**p.32 "Plots, p. 1: Raw data"** (figure read directly):
- Title on figure: "Shot 174436  MPISLD_LFS: 2axis, Pairs, 2D, LFS, R0,R1,R2,  delta-B (G)".
- A grid of small per-sensor time traces (5 columns x ~12 rows). Each subplot y-axis -60..0..60 (delta-B, G); x-axis "Time(msec)" ~3400, 3600, 3800. Each is labeled with its sensor name and two phase numbers (e.g. "ISLD66M017  17-41", "MPID66M200  200-20").
- Top-right inset: a circular (poloidal cross-section) sensor-layout schematic with angular labels 0 / Phi / 90 / 180 and connecting chords between sensor squares.
- Right-side text block: "array = MPISLD_LFS", "smooth = 0.00", "base = 100.0", "btype = 1", "baseline: early data", "comp = N", and "Omitted sensors:" listing ISLD67A112, MPID66M247, LMPID037, MPID67B052, LMPID157, MPID79B277.

**p.33 "Plots, p. 2: Time evolution (B_r, B_p)"** (figure read directly):
- Header: "Shot 174436  MPISLD_LFS 2axis Pairs   solid/square= B_r   dash/diamond= B_p".
- Top panel "Phase (deg)" y-axis 0/90/180/270/360 vs Time; second panel "delta-B (G)" y-axis ~8/10/20/30/40/50 (log-ish), labeled "n = 1"; the two lower panels are contour maps of "Phi (deg.)" (y 0-360) vs "Time (ms)" 3350-3600, top contour = "B_p", bottom = "B_r".
- Right colorbar "delta-B (G)" -40..-20..0..20..40 (rainbow); a phase-angle wedge labeled 0/90/180/270/360.
- Right-side small panels: "Fit vs Measured" scatter (axes -30..30, labeled "m = 1 3 5, n = 1") and a "delta-B (G)" vs phase profile at "t=3550.0, Theta=0.0" with squares (B_r, solid) and diamonds (B_p, dashed), x-axis -30..30 G.

**p.34 "Plots, p. 3: Mode structure (B_r, B_p)"** (figure read directly):
- Title: "174436  2axis Pairs t = 3550.0".
- Two contour panels: top "B_p", bottom "B_r". Both: y-axis "Theta (deg.)" from -90 to +90 (ticks -90,-45,0,45,90; right side labeled TOP / OUTBOARD / BOT), x-axis "Phi (deg.)" 0-90-180-270-360.
- White diamond and square markers overlaid = sensor sample locations.
- Colorbar "Gauss" -40..-20..0..20..40 (rainbow). B_p shows strong blue (negative) lobe near theta~0; B_r is more uniform/orange (weaker amplitude).

**p.36 "Plots, p. 2: Time evolution (B_in, B_ex)"** (figure read directly):
- Header: "Shot 174436  MPISLD_LFS 2axis Pairs   solid/square= B_in   dash/diamond= B_ex".
- Top "Phase (deg)" 0-360 vs Time; "delta-B (G)" 0-50 (n=1) showing B_in (solid) growing/oscillating and B_ex (dash) smaller; two contour maps "Phi (deg.)" 0-360 vs Time (ms) 3350-3600 — top "B_ex", bottom "B_in".
- B_in contour shows strong helical (rotating) banding; B_ex is much weaker.
- Right: "Fit vs Measured" scatter (m = 1 3 5, n = 1; -30..30) and a profile at "t=3550.0, Theta=0.0", delta-B (G) -30..30 vs phi 0-360.

**p.37 "Plots, p. 3: Mode structure (B_in, B_ex)"** (figure read directly):
- Title: "174436  2axis Pairs t = 3550.0".
- Two contour panels: top "B_ex", bottom "B_in". Axes: "Theta (deg.)" -90..90 (TOP/OUTBOARD/BOT on right), "Phi (deg.)" 0-360.
- White diamond/square markers = sensor locations. Colorbar "Gauss" -40..-20..0..20..40.
- B_in shows strong helical structure (deep purple/blue and yellow-green lobes); B_ex is weak and mostly orange/red -> visually demonstrates the field is dominated by the internal source.

---

## Concrete example values (only as appearing)

- **Example 1 shot:** 163060 (m/n = 2/1 tearing mode that grows and locks). Time markers 2720 ms (before locking) and 2760 ms (after locking); locking at "2740-2750 ms" (p.20). Time axis range 2700-2800 ms. Harmonics fitted: "n=1, m=[1, 3, 5]" (p.21).
- **Example 2 (C-coil, no plasma) shot:** 176317. C-coil = "toroidal array of 6 coils" applying an n=1 horizontal field at the midplane. Fits used arrays Bq, Br with "m = [-3, -1, +1, +3]" (p.25). Residual external-source leakage: "B_plasma ~5 G -> External field is eliminated to within ~10%" (p.27).
- **SLCONTOUR2 demo shot:** 174436, array MPISLD_LFS (2axis Pairs 2D LFS R0,R1,R2). Time slice 3550.00 ms, zoom window 3350-3600 ms (full 3200-4000 ms). MLIST = 1 3 5; n = 1. ZMIN/ZMAX = -50/+50 G, NCLEVEL = 41. BASE = 100. PHISLICE = 180, THETASLI = 0.
- **Fit diagnostics (174436, t=3550):** Condition number of array = 2.49; Standard deviation of fit = 1.53 (both dctype 1 and 2).
- **dctype 1 (B_r, B_p) amplitudes/phases (n=1):** All m: 13.22 / 24.71 (B_r), 27.52 / 287.72 (B_p). m=1: 5.20/46.71, 9.69/292.34. m=3: 8.18/36.59, 15.25/285.97. m=5: 3.65/300.85, 2.63/280.89.
- **dctype 2 (B_in, B_ex) amplitudes/phases (n=1):** All m: 20.34 / 19.99 (B_in), 7.24 / 191.34 (B_ex). m=1: 7.30/30.80, 2.70/178.92. m=3: 11.54/23.14, 4.06/175.17. m=5: 2.59/329.38, 1.85/258.92.
- **Omitted sensors (174436):** ISLD67A112, MPID66M247, LMPID037, MPID67B052, LMPID157, MPID79B277.
- **Sensor-channel naming (arrays, pp.38-41):** Br/ISLD channels (e.g. ISLD, ISLD67A, ISLD67B, ISLD79A, ISLD79B, ISLD1A, ISLD1B, ISLD199) and Bp/MPID channels (MPID, MPID67A, MPID67B, MPID79A, MPID79B, MPID1A, MPID1B, MPID199); single-sensor variants ISL/MPI. Toroidal positions R0, R+1 (R67A), R-1 (R67B), R+/-2 (R79A/B), HFS Above/Below mid (1A/1B), HFS vertical (199).

### Array reference tables (pp.38-41, totals as shown)

2-Axis 1-D paired-sensor arrays (p.38): MPISLD (R0, total 18), MPISLD67A (R+1, 20), MPISLD67B (R-1, 16), MPISLD1A (HFS above mid, 16), MPISLD1B (HFS below mid, 16).

2-Axis 1-D single-sensor arrays (p.39): MPISL (R0, 18), MPISL67A (R+1, 20), MPISL67B (R-1, 16), MPISL1A (HFS above mid, 16).

2-Axis 2-D paired-sensor arrays (p.40): MPISLD_R01 (R0,R+/-1; 54 pairs), MPISLD_LFS (R0,R+/-1,R+/-2; 70), MPISLD1AB (HFS midplane; 32), MPISLD_HFS (HFS mid & vertical; 48), MPISLD_TOR (R0,R+/-1 + HFS midplane; 86), MPISLD_ALL (R0,R+/-1,R+/-2 + HFS mid & vertical; 118).

2-Axis 2-D single-sensor arrays (p.41): MPISL_R01 (R0,R+/-1; 54), MPISL_HFS (HFS mid & vertical; 32).

---

## Notable quotes (verbatim, with page #s)

- (p.3) "'3D' magnetic fields outside the plasma typically contain contributions from both the plasma and external sources. How to distinguish the plasma's contribution from that of external coils, eddy currents, etc.?"
- (p.4) "General property of B-fields -- no specific model of wall or coils" / "First application in tokamak experiments??"
- (p.5) "Phase shifts distinguish which side of the source the measurements are seeing."
- (p.7) "Magnetic field between the plasma and conductors is represented by a scalar potential that obeys Laplace's equation: del^2 Phi = 0"
- (p.9) "This Principle Has Been Known for over 180 Years!"
- (p.12) "This presentation uses only the five LFS arrays"
- (p.13) "Basis functions are NOT necessarily plasma modes."
- (p.16) "dB_r is blind to the mode onset and early growth" / "B-dot (Mirnov) signal vanishes after the mode locks" / "Integrated dB_q sees full mode growth, but also wall currents"
- (p.18) "B_r is shielded out of the wall -- By mode rotation"
- (p.22) "B_wall is equal and opposite ... to B_plasma -- Image current shields the rotating mode"
- (p.23) "B_wall has vanished -- After mode rotation stops"; "B_plas is locked at fixed phase -- But amplitude has grown"
- (p.25) "No plasma -> B^int = 0: should detect only an external field"; "Figure is for illustration only. Some details may not be accurate."
- (p.27) "External field is eliminated to within ~10%"
- (p.28) "Decomposition of tearing mode fields into plasma and wall contributions appears successful" / "Resolution of fields from non-axisymmetric coils seems plausible -- more challenging due to wide poloidal spectrum"
- (p.29) "SLCONTOUR2 is a special version for 2-axis data -- Should be equivalent to SLCONTOUR when used for 1-axis data"
- (p.42) "SLCONTOUR2 is still under development. Please try it!" / "It is reasonably stable -- no major changes in the last year or so" / "My goal is to consolidate all features into SLCONTOUR2, rather than maintain separate versions for 1-axis and 2-axis data"

---

## Digest (unique content)

This Part-III deck extends the SLCONTOUR series to **2-axis (paired normal + tangential) magnetic sensor arrays** and is built around Strait & Sweeney's "Gauss algorithm" for separating internally-sourced (plasma) from externally-sourced (coils/eddy-current) 3D fields, exploiting the +/-90deg phase shift between B_r and B_theta across a periodic current source and a Laplace-equation cylindrical-harmonic fit (b_theta = +/- i b_r). The physics is demonstrated on two real cases: a 2/1 tearing-mode lock in **shot 163060** (showing plasma field penetrating the wall as the wall image current dies, with a sudden wall-torque peak at locking, 2740-2750 ms) and a **shot 176317** C-coil vacuum n=1 field (external field recovered to within ~10%, residual "plasma" ~5 G). The operationally unique part is the **SLCONTOUR2 how-to**: the `slcontour2_test` entry point, `find`/`array` selection, the full `view` parameter list (illustrated on shot 174436, MPISLD_LFS, t=3550 ms, MLIST=1 3 5, n=1), and the `dctype` switch between (B_r, B_p) and (B_in, B_ex) decompositions, each producing printed amplitude/phase tables (condition number 2.49, std dev 1.53) and three plot pages (raw data, time evolution, mode structure) with contour maps over Phi 0-360deg / Theta -90..+90deg / Time, colorbar in Gauss (-50..+50, 41 levels). Slides 38-41 are a reference catalog of the available 2-axis array names (MPISLD*/MPISL*) with their LFS/HFS toroidal positions and pair/sensor totals. The closing slide states SLCONTOUR2 is still under development but stable and agrees with SLCONTOUR on single-axis data, with the goal of consolidating both into one tool. (Note: MODESPEC is not mentioned in this document.)

**Output file:** `docs/research-summaries/09_Slcontour_III_Update2023.md`
