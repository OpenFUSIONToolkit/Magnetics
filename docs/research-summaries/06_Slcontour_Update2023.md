# SLCONTOUR — Introduction (2023 Update)

**Source PDF:** `resources/DIII-D IDL Command Line Tools/Strait_Magnetics_20230420_Slcontour(Update).pdf`
**Title (p.1):** "Introduction to SLCONTOUR"
**Author:** Ted Strait (slide footer reads "E. Strait / DIII-D Magnetics / Apr. 20, 2023")
**Date:** April 20, 2023; with "Updates 4/26/23"
**Length:** 32 pages
**PDF Producer/dates (metadata):** macOS Quartz PDFContext; CreationDate/ModDate D:20230426195556Z

> NOTE ON ACCURACY: Page text was extracted programmatically; slide layouts cause some word-order scrambling, which I have reconstructed conservatively. For the four central screenshot figures (pages 7, 21, 22) I rendered the actual images and read axis labels/units/ranges directly off them. Where a value or label could not be confirmed, I say so. Verbatim quotes are flagged with page numbers.

---

## Document overview

This is an introductory tutorial deck for SLCONTOUR, an IDL command-line tool at DIII-D for visualizing and analyzing "3D Magnetics" (non-axisymmetric) magnetic datasets. The deck states it focuses on **the basics of SLCONTOUR with 1-D arrays**, and that advanced features (2-D arrays in (φ, θ); 2-axis arrays) will be covered in additional presentation(s). The deck ends (p.32) with "To Be Continued …".

**What this "Update" page (p.1) literally lists as changed (verbatim, p.1):**
- "p. 8: Added footnotes regarding basis functions and sign of f"
- "p. 9: Corrected a typo in the first equation"
- "p. 17: Revised the table to distinguish ESLD and ESLDU"

These are the only stated changes in the 4/26/23 update. (The tool itself is not described as having new features in this revision; the update is to the slides.)

**Non-axisymmetric features SLCONTOUR is used for (p.2):** Tearing Modes (rotating and locked); Kink Modes (e.g. Resistive Wall Modes); Applied fields (C-coil and I-coil); Stable plasma response to external fields; Error fields.
- Footnote (p.2): "Direct measurement of error fields is difficult, but they can be measured indirectly through the response of islands or stable kink modes"

**Stated purposes of SLCONTOUR (p.5):**
- Mode analysis: "Reliable decomposition of toroidal modes with 1D array data"; "Analysis of poloidal modes with 2D array data, using a simple cylindrical model"; "Estimates of mode growth or decay rate"
- Checking data quality: visually (raw traces show dead probes, large drifts) and analytically (quality of fits to a simple model)
- Maintaining a database of available data channels and how they organize into 1D/2D arrays

---

## Magnetic sensors / hardware

**Overview (p.3, title):** "(Mostly) Co-located Mag Probes and Saddle Loops Provide 2-Axis Measurements of Non-Axisymmetric (3D) Fields"
- Sensor counts stated (p.3): "70 Bp probes (MPI)" and "64 Br loops (ISL)".
  - Bp sensors = magnetic probes (MPI); Br sensors = saddle loops (ISL).
- p.3 lists vertical arrays at toroidal angles **139º** and **199º**, and references inboard/HFS, top, LFS/OUTBOARD locations. A schematic plots "Distance along vessel wall (m)" (axis from about -2 to 5) vs "q (deg.)" 0–360 (here "q" is θ, poloidal angle). Pointname families shown: MPI/ISL1A, 1B, 79A, 67A, 66M, 67B, 79B. Note (p.3): "MPI67A layout includes changes in 2020".

**Differential pairs (p.4), title:** "Differential Pairs of Sensors Reject n=0 Field"
- "All '3D' sensors are connected in toroidally separated pairs": ΔB = [B(φ₁) – B(φ₂)] / 2 (reconstructed from text "DB = [B(f) – B(f)] / 2").
- "Some are also acquired individually for n=0 field and for redundant n≠0 data"
- Pair connection has an "Adjustable balance" and an integrator (∫ dt) on the differential signal.
- "Variable toroidal separation of the pairs minimizes spatial degeneracy when fitting multiple n values"
- Toroidal separation ranges (verbatim, p.4): "LFS midplane Bp array: 77º ≤ Df ≤ 180º" and "Other arrays: 15º ≤ Df ≤ 180º" (Df = Δφ).

**Array inventory tables** — see "Concrete example values" below for the full p.17/p.18 tables.

---

## SLCONTOUR

### What is NEW / updated in this 2023 update
Per p.1, the only documented changes are slide edits (footnotes on p.8 about basis functions and the sign of φ; a typo fix in the first equation on p.9; and revising the p.17 table to distinguish ESLD vs ESLDU). I found **no claim of new tool features** introduced by this revision. The "ESLD vs ESLDU" distinction is reflected on p.17, where ESLD (3 pairs, "External-Comp") and ESLDU (6 pairs, "External") are listed separately; on p.16 the `find` example lists "ESLD … (External-Comp)" and "ESLDU … (External)".

### Launching / environment (p.11, p.12)
```
$ module load slcontour        (or include this line in .cshrc)   — set the environment
$ idl                          — launch IDL
IDL> slcontour                 — run slcontour
-->                            — command prompt
--> exit                       — exit back to IDL
```

### Command syntax (p.12, verbatim where noted)
- "Command syntax: --> command=<value>"
- "Unique abbreviations of commands are ok."
- "Use , or ; to separate multiple commands on a single line"
- Example (p.12): `--> tmin=2000, tmax=3000`
- (p.19 examples also show space-separated form, e.g. `shot 174436,xmin 3000,xmax 4000` and `array mpi66m`.)

### Frequently used commands (p.13) — literally shown
- `--> shot=123456` — Shot
- `--> tmin=3000, tmax=4000` — Time interval (ms); "Same" as `xmin=3000, xmax=4000`
- `--> array=ISLD` — Array
- `--> nmin=1, nmax=3` — Mode number range for fitting
- `--> smooth=5` — Smoothing of raw data (ms)
- `--> slice=3250` — Time slice for plot (ms)
- `--> hc=13-450-xerox` — Print a hard copy

### Information / help commands (p.14)
- `--> commands` — "Print a list of all commands (alphabetical order)"
- `--> help` — "Print a summary of commands (by topics)"
- `--> document` — "Open a read-only window to view documentation"
- `--> view` — "Show current parameter settings (or just hit Return)"

### Finding an array (p.15, p.16)
- "Slcontour recognizes >100 arrays" (p.15).
- `--> find` with keywords searches arrays; `find` with no keywords lists all arrays + keywords.
- Keyword categories (p.15): Array Name (e.g. MPID, ISLD, MPID67A); Component of Field (Bp / Br / Bt / Bpdot); Connections of Sensors (Singles / Pairs); Type of Array (Tor / Pol / Vert / 2D); Which Side (LFS / HFS); Poloidal location (R0, R+1, Mid, All, … for toroidal arrays); Toroidal location (67, 157, 322, … for poloidal arrays); Comments (PCS, Comp, External, …).
- Example (p.16, verbatim output):
  ```
  --> find bp r0 tor
  5 Matches found
  MPID     Bp Pairs Tor LFS R0
  MPI66M   Bp Singles Tor LFS R0
  MPI66M_S Bp Singles Tor LFS R0 (Slow A/D)
  PCMPID   Bp Pairs Tor LFS R0 (PCS)
  NRSMPID  Bp Pairs Tor LFS R0 (PCS-Comp)
  --> array mpi66m
  ```

### Example run output (p.19, p.20) — verbatim run trace
On `shot 174436, xmin 3000, xmax 4000`, the tool prints a sequence:
`FETCHING RAW DATA` → lists channels with "gadat error code and data size (samples)", e.g. `MPID66M020  0  563200` (the 10 channels MPID66M020/067/097/127/157/200/247/277/307/340, all "0" error and 563200 samples) → `LEFT-HAND helicity, sign(Bt, Ip) = -1` → `APPLYING COMPENSATION` → `WINDOWING DATA` → `PREPROCESSING DATA` → `PLOT RAW DATA` → `FITTING HELICAL MODES` with `n values = 1 2 3` and `m values = 0` (annotation: "1-D toroidal array cannot resolve m values").

Then (p.20) `PLOT FITTED RESULTS`, with this printed block (verbatim, single time slice):
```
SHOT = 174436   TIME = 3500.00
Array = MPID ( Bp Pairs Tor LFS R0 )
            n = 1            n = 2            n = 3
         Ampl.  Phase     Ampl.  Phase     Ampl.  Phase
All m    31.67  321.97     6.46  332.63     1.97  358.60
m = 0    31.67  321.97     6.46  332.63     1.97  358.60
-----------------------------------
Condition number of array = 1.83
Standard deviation of fit = 1.44
-----------------------------------
41 contour levels: min, max, interval = -69.70  69.70  3.485
Contour plot downsampled x 5 : Time resolution (ms) = 0.10
```
- Annotations: "Two key figures of merit to watch! Smaller is better." (refers to condition number and standard deviation). "Done to improve plotting speed. (Time resolution should still be better than the screen resolution.)"

### Zoom feature (p.23, p.24)
- `--> xxmin 3400, xxmax 3450` — zoom into a narrow time window (here 3400–3450 ms). "This feature preserves the original data arrays on [xmin, xmax]" and "Subtraction of baseline values is unchanged".
- `--> zoom off` / `--> zoom on` — "Toggle between Full time interval [xmin, xmax] ⬍ Zoom interval [xxmin, xxmax]".

### Baseline subtraction (p.25, p.29, p.30, p.31)
Rationale (p.25): small δB amplitudes mean signals acquire offsets from "integrator drift or pickup of the n=0 field"; with sensor pairs the n=0 balancing may be imperfect, with single sensors the n=0 contribution is large. Subtract a baseline close to the time of interest (e.g. just before an MHD-mode onset). "Poor selection of the timing or the algorithm for baseline subtraction can lead to nonsensical results."

Baseline commands (p.29):
- `--> btype=1` — select baseline algorithm ("baseline type"); annotated "Default value – best for most cases".
- `--> btype` (no argument) — list the options.
- `--> base=50` — baseline time interval (ms).
- `--> tbmin=2200, tbmax=2800` — baseline start, end times (ms); "Optional, only applies to btype = 11 to 13".

`btype` values (verbatim list, p.29):
```
0  = No baseline subtraction
1  = baseline: early data, ∆t=base
2  = baseline: late data
3  = baseline: interpolated
4  = baseline: running average
5  = baseline: running ave., lag=base
6  = baseline: running ave., lag=2xbase
7  = baseline: RC filter, tau=base
8  = baseline: RC filter, lag=base
9  = single-freq. sine fit, period=base
10 = single-freq. square fit, period=base
11 = average on interval [tbmin, tbmax]
12 = linear fit on interval [tbmin, tbmax]
13 = interpolate tbmin+[0,base] to tbmax-[base,0]
```
Transient-event guidance (p.30): btype=1 averages over an interval of duration "base" at the START of the plotted window; btype=2 averages an interval of duration "base" at the END; btype=3 interpolates between the two averages.

---

## MODESPEC

MODESPEC is mentioned only by contrast on **p.6** ("SLCONTOUR is Aimed at Low-Frequency Perturbations"), as the complementary tool for rapidly rotating modes. The deck does not otherwise document MODESPEC commands or usage.

SLCONTOUR vs MODESPEC contrast (p.6, paired bullets):
| | SLCONTOUR | MODESPEC |
|---|---|---|
| Mode type | Stationary or slowly rotating modes; 0 ≤ ωτ ≤ 1 | Rapidly rotating modes; ωτ ≫ 1 |
| Analysis domain | Space-domain Fourier analysis | Time-domain Fourier analysis |
| Time interval | No minimum time interval for analysis | Requires analysis interval T ≥ (a minimum, written as a fraction; the denominator/numerator symbols did not extract cleanly) |
| Mode separation | Modes separated by spatial structure | Modes separated by frequency |
| Probe count | Requires many probes | Requires relatively few probes |
| n=0 handling | n=0 removed by differential pairs | n=0 negligible in data; dB/dt too small to use at low frequency |

(τ defined p.6: "a characteristic time scale for changes in the discharge or in the mode (e.g. mode growth time)".)

---

## Analysis methods / math

**1-D toroidal harmonic representation (p.8).** δB(φ) is fit to a cylindrical Fourier basis in φ. Two equivalent forms are shown:
- Complex: δB(φ) = Re[ Σₙ Bₙ e^{inφ} ], where Bₙ(t) are complex coefficients (sum from n=0).
- Sine/cosine: δB(φ) = b₀ + Σₙ [ bₙ cos(nφ) + aₙ sin(nφ) ], with bₙ(t), aₙ(t) real; with the n=0 term having Im(B₀) = a₀ = 0.
- Footnotes (the ones added in this update): "SLCONTOUR uses 'machine angle' φ (clockwise when viewed from above)"; "SLCONTOUR coding uses sine, cosine basis functions, not complex exponentials".
- "A fit to modes n=1, 2, … N requires at least 2N+1 sensors — Fit has 2N+1 degrees of freedom: one for n=0 and two for each non-zero n."
- "Coefficients are found by least-squares fit of data to the basis functions — FFT cannot be used because the probes are not equally spaced."

**Normal-equations / pseudo-inverse method (p.9, p.10).** Cites W. H. Press et al., *Numerical Recipes in Fortran*, 2nd ed., Cambridge Univ. Press, 1994, p. 665.
- Basis matrix A_{jk}: each basis function k evaluated at each sensor j. For a single probe at angle φ_j: A_{jk} = e^{inφ_j} (averaged over the probe's area, ⟨…⟩). For a differential pair at φ_{j,1}, φ_{j,2}: A_{jk} = ½(e^{inφ_{j,1}} − e^{inφ_{j,2}}). "Sensor j" is either a single probe or a differential pair; k indexes the n numbers to fit (usually n = 1, 2, …).
- Forward problem: S_j = A_{jk} B_k (measurements predicted from coefficients).
- Inverse problem: A is generally non-square (no true inverse), so use the Moore-Penrose pseudo-inverse to form a "detection matrix" D = A⁺ = (Aᵀ A)⁻¹ Aᵀ, giving the least-squares fit B_k = D_{kj} S_j; coefficients then reconstruct the fitted function at any spatial location.
- Caveat (p.9): "These basis functions are a device for fitting periodic data. They do not necessarily correspond to plasma modes."

---

## Visualizations to reproduce
(Axes/units/ranges below were read off the rendered figure images, not inferred.)

### A. Fitted-results page for shot 174436 (p.22, "Plotted Output (page 2)") — VERIFIED FROM IMAGE
Five-panel composite, title "Shot 174436  MPID (Bp Pairs)". Time-slice annotation "t=3500.0, Theta=0.0".
1. **Top-left: Phase vs Time.** Y = "Phase (deg)" 0 → ~350 (ticks at 0,100,200,300). X shared with panel below. Three traces (black, blue, dark-red/maroon) = n=1,2,3 phases; very noisy/wrapping before ~3450 ms, then organized.
2. **Mid-left: Amplitude vs Time.** Y = "delta-B (G)" 0 → 80 (ticks 0,20,40,60,80). Black (n=1) grows from ~3400 ms to a peak (~45–55 G near 3440), then ~30 G; blue (n=2) and maroon (n=3) much smaller. A vertical line marks the selected time slice (~3500 ms).
3. **Bottom-left: Contour map of fitted δB.** X = "Time (ms)" ~3000–~4000 (ticks 3200, 3400, 3600, 3800); Y = "Phi (deg.)" 0–360 (ticks 0,90,180,270,360). Filled rainbow color scale, colorbar range about **−60 to +60** (G) (ticks −60,−40,−20,0,20,40,60), dark blue = negative, red/orange mid, yellow = positive. Shows diagonal stripes (rotating phase fronts) after ~3450 ms.
4. **Top-right: "Sensor data" — Fit vs Measured scatter.** X = "Measured" (−40 to 40), Y = "Fit" (−40 to 40); open-square data points lie on the 1:1 line; legend "m = 0, n = 1 2 3".
5. **Bottom-right: δB vs Phi at the time slice.** X = "delta-B (G)" −40 to 40; Y = 0–360 (deg). Solid black curve = total fit with diamond data points (reconstructed from pair differences); blue dashed and maroon dash-dot = individual harmonic components.

### B. Raw-data page for shot 174436 (p.21, "Plotted Output (page 1)") — VERIFIED FROM IMAGE
Title "Shot 174436  MPID: Bp, Pairs, Tor, LFS, R0,  delta-B (G)".
- **Left: stacked time traces**, 10 panels (one per pair): MPID66M020 (20–97), 66M067 (68–246), 66M097 (97–278), 66M127 (128–307), 66M157 (158–340), 66M200 (200–20), 66M247 (246–128), 66M277 (278–158), 66M307 (307–200), 66M340 (340–68). Each Y axis = δB in G with ticks −60, 0, 60. X = "Time(msec)" ~3000–~4000 (ticks 3200, 3400, 3600, 3800). A vertical line near 3500 ms marks the slice. The "NN–MM" labels are the two probe toroidal angles forming each pair.
- **Right: a circle schematic** ("difference pair connections"): a circle with "0" at top, "90" at right, "180" at bottom, "Phi" arrow; chords connect paired probe locations (open squares).
- **Right text block (parameter settings, verbatim):** `array = MPID`, `smooth = 0.00`, `base = 100.0`, `btype = 1`, `baseline: early data`, `comp = N`.

### C. Locked-mode growth example, shot 162432 (p.7) — VERIFIED FROM IMAGE
Same five-panel layout. Shot number "162432" printed top-right; time slice "(t=2010 ms)".
1. **Phase (deg)** vs Time: Y ticks 0,100,200,300; black = n=1, blue dashed = n=2 (labeled "n=2" upper, "n=1" lower).
2. **Amplitude (G)** vs Time: Y 0 → 20 (ticks 0,10,20). Traces labeled n=1 (black solid), n=2 (blue dashed), n=3 (maroon dash-dot). n=2 grows first (~1850 ms), n=1 grows after ~2000 ms to ~15 G.
3. **Contour map δB**: X = "Time (ms)" 1700–2200 (ticks 1700,1800,1900,2000,2100,2200); Y = "Phi (deg.)" 0–360. Colorbar range **−20 to +20** (ticks −20,−10,0,10,20). Vertical line at the 2010 ms slice.
4. **Fit vs Measured** scatter: both axes ~ −45 to −15; open squares on 1:1 line.
5. **δBp vs Phi** at slice: X = "δBp (G)" −15 to 15; Y 0–360. Solid black (total) with diamonds; blue dashed (n=1 or component), maroon dash-dot, black dotted curves for components.

### D. Plasma-current ramp diagnostic (p.28) — from text + image
Single trace: "IP (MA)" for shot 174436, Y from 0 to 1.5 (ticks 0, 0.5, 1.0, 1.5), X 0–4000 (ms). Timestamp on plot "Tue Apr 18 15:37:26 2023". Used to show MPID ramps track the Ip ramp → "Probably n=0 Pickup".

### E. Early-time "strange" data (p.26, p.27) — described in text
Same raw-trace / fit layout as A/B but for `xmin 0, xmax 3000`; deck notes "Large apparent δB amplitudes ~30-40 Gauss!" and slowly developing n=2/n=3 with no clear mode onset; p.27 shows some probe time traces with a slow ramp. (I did not separately render these; layout matches A/B.)

---

## Concrete example values (only as they appear)

- **Shots:** 123456 (syntax placeholder, p.13); **174436** (main worked example, pp.19–31); **162432** (locked-mode example, p.7).
- **Times (ms):** tmin/tmax 2000/3000, 3000/4000 (examples); slice 3250 (p.13); fitted slice TIME = 3500.00 (p.20/22); zoom xxmin/xxmax 3400/3450 (p.23); btype interval tbmin/tbmax 2200/2800 (p.29); baseline `[xmin, xmin+base] = [3000, 3100] ms` with base=100 (p.31); early-time window xmin 0/xmax 3000 (p.26); t=2010 ms (p.7).
- **Mode numbers fit:** n = 1, 2, 3 (m = 0 only for 1-D toroidal array).
- **Fit results, shot 174436, t=3500 ms, array MPID (p.20):** n=1 Ampl 31.67 / Phase 321.97; n=2 Ampl 6.46 / Phase 332.63; n=3 Ampl 1.97 / Phase 358.60. Condition number = 1.83; Standard deviation of fit = 1.44. Contour: 41 levels, min/max/interval = −69.70 / 69.70 / 3.485; downsampled ×5, time resolution 0.10 ms.
- **Helicity readout (p.19):** "LEFT-HAND helicity, sign(Bt, Ip) = -1".
- **Channel list (p.19):** MPID66M020, 067, 097, 127, 157, 200, 247, 277, 307, 340 — all error code 0, 563200 samples.
- **Toroidal separation limits:** LFS midplane Bp 77º–180º; other arrays 15º–180º (p.4).
- **Sensor totals (p.3):** 70 Bp probes (MPI); 64 Br loops (ISL). Vertical arrays at 139º and 199º.

**Array inventory — 1-D Paired-sensor arrays (p.17), counts = "Pairs":**
| Location | Type | BR (saddle) | BR pairs | Bp/BT (probes) | Bp/BT pairs |
|---|---|---|---|---|---|
| R0 | Toroidal | ESLD (External-Comp; compensated in ISLD1A/B) | 3 | BTID | 4 |
| R0 | Toroidal | ESLDU (External) | 6 | — | — |
| R+1 | Toroidal | ESLD67A | 12 | — | — |
| R−1 | Toroidal | ESLD67B | 12 | — | — |
| R0 | Toroidal | ISLD | 8 | MPID | 10 |
| R+1 | Toroidal | ISLD67A | 8 | MPID67A | 12 |
| R−1 | Toroidal | ISLD67B | 8 | MPID67B | 8 |
| R+2 | Toroidal | ISLD79A | 4 | MPID79A | 4 |
| R−2 | Toroidal | ISLD79B | 4 | MPID79B | 4 |
| HFS (above mid) | Toroidal | ISLD1A | 8 | MPID1A | 8 |
| HFS (below mid) | Toroidal | ISLD1B | 8 | MPID1B | 8 |
| HFS (139º–199º) | Vertical | ISLDVERT | 8* | MPIDVERT | 8* |
- Footnote (p.17): "*10, with two in ISLD1A/B" (vertical-array footnote); "**Compensated in ISLD1A/B". **TOTAL PAIRS: 86 (saddle/BR) and 66 (probes/Bp).**

**Array inventory — 1-D Single-sensor arrays (p.18), counts shown under "Pairs" column header in the slide:**
| Location | Type | BR (saddle) | count | Bp/BT (probes) | count |
|---|---|---|---|---|---|
| R0 | Toroidal | ESL66M | 6 | BTI66M | 4 |
| R+1 | Toroidal | ESL67A | 12 | — | — |
| R−1 | Toroidal | ESL67B | 12 | — | — |
| R0 | Toroidal | ISL66M | 8 | MPI66M | 10 |
| R+1 | Toroidal | ISL67A | 8 | MPI67A | 12 |
| R−1 | Toroidal | ISL67B | 8 | MPI67B | 8 |
| R+2 | Toroidal | — | 2 | — | 2 |
| R−2 | Toroidal | — | 2 | — | 2 |
| HFS (above mid) | Toroidal | ISL1A | 8 | MPI1A | 8 |
| HFS (below mid) | Toroidal | — | 2 | — | 2 |
| HFS (139º) | Vertical | ISLVERT | 8* | MPIVERT | 8* |
- Footnote (p.18): "*10, with two in ISL1A/B" / "in MPI1A/B". **TOTAL digitized channels: 76 (saddle/BR) and 56 (probes/Bp).**

(Note: the p.18 column is headed "Pairs" in the extracted slide text, but the page is titled "Single-sensor Arrays" and the bottom row reads "TOTAL digitized channels", so these are channel counts, not pairs. The header label appears to be a slide-template carryover.)

---

## Notable quotes (verbatim, with page #s)

- (p.1) "Updates 4/26/23 / p. 8: Added footnotes regarding basis functions and sign of f / p. 9: Corrected a typo in the first equation / p. 17: Revised the table to distinguish ESLD and ESLDU"
- (p.2) "This presentation will focus on the basics of SLCONTOUR with 1-D arrays"
- (p.2) "Direct measurement of error fields is difficult, but they can be measured indirectly through the response of islands or stable kink modes"
- (p.4) "All '3D' sensors are connected in toroidally separated pairs"
- (p.4) "Variable toroidal separation of the pairs minimizes spatial degeneracy when fitting multiple n values"
- (p.6) "SLCONTOUR is Aimed at Low-Frequency Perturbations"
- (p.8) "A fit to modes n=1, 2, … N requires at least 2N+1 sensors"
- (p.8) "FFT cannot be used because the probes are not equally spaced"
- (p.8) "SLCONTOUR uses 'machine angle' f (clockwise when viewed from above)"
- (p.8) "SLCONTOUR coding uses sine, cosine basis functions, not complex exponentials"
- (p.9) "These basis functions are a device for fitting periodic data. They do not necessarily correspond to plasma modes."
- (p.12) "Unique abbreviations of commands are ok."
- (p.15) "Slcontour recognizes >100 arrays"
- (p.20) "Two key figures of merit to watch! Smaller is better." (condition number, std. dev. of fit)
- (p.19) "1-D toroidal array cannot resolve m values"
- (p.25) "Poor selection of the timing or the algorithm for baseline subtraction can lead to nonsensical results"
- (p.29) "btype=1 … Default value – best for most cases"
- (p.32) "To Be Continued …"

---

## Digest (unique content)

This 32-slide Ted Strait tutorial (Apr. 20, 2023, updated 4/26/23) is the canonical introduction to **SLCONTOUR**, DIII-D's IDL command-line tool for visualizing/analyzing low-frequency non-axisymmetric ("3D") magnetics, and the 4/26 "update" is purely editorial (three slide fixes on pp.8/9/17), not a tool feature change. Its most reproducible content is the concrete command vocabulary (`shot`, `tmin/tmax` ≡ `xmin/xmax`, `array`, `nmin/nmax`, `smooth`, `slice`, `btype/base/tbmin/tbmax`, `find`, `commands`, `help`, `document`, `view`, `zoom`, `xxmin/xxmax`, `hc`) and the full 14-value `btype` baseline-subtraction menu (p.29) with transient-event guidance (p.30). The math is a 1-D toroidal sine/cosine harmonic fit (needs ≥2N+1 sensors) solved by Moore-Penrose pseudo-inverse "detection matrix" D = (AᵀA)⁻¹Aᵀ per Numerical Recipes, reporting condition number and fit standard deviation as quality metrics. The signature visualization to replicate is the five-panel fitted-results display (phase-vs-time, amplitude-vs-time, a δB rainbow contour over time × toroidal angle φ 0–360º, a Fit-vs-Measured 1:1 scatter, and a δB-vs-φ snapshot), shown for shots **174436** (MPID Bp pairs, colorbar ±60 G, t=3500 ms, n=1 amp 31.67 G) and **162432** (colorbar ±20 G, t=2010 ms), plus the 10-panel raw-pair-trace page and the supporting Ip-ramp / n=0-pickup diagnostic. The deck's two array-inventory tables (pp.17/18) — 86 BR + 66 Bp paired sensors, 76 BR + 56 Bp single channels, with names like ISLD/MPID/ESLD(U)/ISLDVERT — are a ready-made channel database for a replacement GUI. MODESPEC appears only as a contrast on p.6 (rapidly rotating modes, time-domain Fourier) and is otherwise not documented here.

**Output file written to:** `docs/research-summaries/06_Slcontour_Update2023.md`
