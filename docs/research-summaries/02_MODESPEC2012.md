# MODESPEC — Summary of Strait (2012-04-23) presentation

> Source PDF: `resources/DIII-D IDL Command Line Tools/Strait_20120423 Modespec.pdf`
> This summary reports ONLY what is literally present in the document. Where the document does not address a required topic, that is stated explicitly. The page-7 screenshot was extracted as an image and described from direct inspection. Verbatim text and on-image readings are flagged as such; anything not directly readable is noted.

---

## Document overview

- **Title:** "Modespec: a replacement for newspec & mode1" (page 1, verbatim).
- **Author / presenter:** Ted Strait. (Listed as both the slide author and the PDF metadata `Author: Ted Strait`.)
- **Venue:** "Stability and Disruption Avoidance Meeting" (page 1, verbatim).
- **Date:** April 23, 2012 (page 1). PDF metadata `CreationDate: 2012-04-23`.
- **Format:** PowerPoint slide deck exported to PDF (metadata `Creator: PowerPoint`, `Producer: Mac OS X 10.7.3 Quartz PDFContext`).
- **Length:** 9 pages (slides).
- **Purpose:** Introduce MODESPEC, a new IDL-based MHD-mode-identification code that **combines the functionality of two legacy Fortran/DISSPLA codes, `newspec` and `mode1`** (page 2). The deck describes what MODESPEC does, its command set, an example run, a screenshot of typical output, and how to start it. It is explicitly an early-release announcement: "Modespec is stable but still needs development" (page 9).

This is the PRIMARY MODESPEC reference in the document set. Note: the deck is a brief overview/announcement (9 slides), not a manual; it does not exhaustively document every command's syntax or numeric ranges. Details below are limited to what is shown.

---

## Magnetic sensors / hardware

The document does NOT contain a dedicated sensor/hardware section. The only sensor information appears in the worked example (page 6) and the screenshot (page 7):

- **`MPI66M307E`** and **`MPI66M340E`** — these are the two pointnames fetched in the example run (page 6, verbatim from the IDL log: "148283 MPI66M307E ier = 0 2031616 samples returned" / "148283 MPI66M340E ier = 0"). They are also listed in the SPECTROGRAM window header in the screenshot ("MPI66M307E / MPI66M340E").
- The naming `MPI66M...` indicates these are DIII-D **Mirnov / poloidal magnetic probes** (the "MPI66" series; the trailing numbers, 307 and 340, are the toroidal angle φ in degrees of each probe — consistent with the deck's notion of a "probe pair"). The document itself does NOT spell out what `MPI66M` stands for; this naming interpretation is inferred and not stated in the text.
- The code measures **dB/dt (T/s)** by default (the deck refers to "Spectrogram of dB/dt"), with an option to numerically **integrate** to get B (see the `integrate`/`bdot` command, page 4).
- The screenshot's MODE STRUCTURE window (page 7) shows a **"TOROIDAL ARRAY"** and a **"POLOIDAL ARRAY"** of probes (plots vs. Phi and vs. Theta), implying MODESPEC can use full toroidal and poloidal probe arrays for mode-number fitting, not just a single pair. The specific array members are not enumerated in the document.

The document does NOT describe sensor calibration, sensor geometry tables, sampling hardware, or saddle/radial sensors.

---

## SLCONTOUR

Not covered in this document. SLCONTOUR is not mentioned anywhere in the deck. (This deck concerns MODESPEC and its two predecessor codes `newspec` and `mode1` only.)

---

## MODESPEC (focus)

### What it does (page 2, verbatim bullet structure)

"Modespec is a new analysis code for quick MHD mode identification." It "combines the functionality of newspec and mode1." Four capabilities are listed:

1. **Spectrogram of dB/dt vs. time and frequency** — "Color coded for toroidal mode number." Marked "~ newspec" (i.e., this replicates `newspec`).
2. **Spectrum plot for a single time-interval** — "Power, coherence, toroidal mode number vs. f."
3. **Single-mode fit → n, m vs. frequency** — "Fit of phase only, for a single time interval." Marked "~ mode1" (replicates `mode1`).
4. **Multiple-mode fit → n, m spectrum** — labeled "(new)"; "Fit of instantaneous δB." This is the genuinely new capability beyond the two legacy codes.

### Implementation / status (page 3, verbatim)

- "Written in idl" — whereas "newspec and mode1 use fortran and disspla."
- "Driven by typed commands" — "commands and syntax similar to newspec & mode1"; "hope to develop a GUI."
- "Available to run out of my directory – Details later."

### Command interface (page 4, verbatim from the `help` output)

The `help` command prints:

```
-->help
****************************************************************
Enter commands, separated by "," or ";" Abbreviations OK.
Form is <command> or <command = value> or <command value>
********************** COMMANDS ********************************
help view exit quit            -- Actions
backup hardcopy hc mode        -- Actions
-------------------------------------------------- SHOT & POINTNAME
shot [ ]                       -- Shot number select/advance
point1 point2 dtheta           -- Probe pair selection
integrate bdot                 -- Numerical integration on/off
-------------------------------------------------- SPECTROGRAM PLOT
tmin tmax dt                   -- Spectrogram plot time limits
fmin fmax df                   -- Frequency limits & smoothing
zmin zmax nlog                 -- Spectrogram contour values
-------------------------------------------------- SUBINTERVAL PLOT
t0 { }                         -- Single FFT time select/advance
tslice < > zoom                -- Time slice select/advance
-------------------------------------------------- MODE ANALYSIS
nmin nmax mmin mmax            -- Mode number analysis limits
f0 ( )                         -- Mode frequency select/advance
--------------------------------------------------------------------
```

Key facts about the command syntax (all from page 4):
- Commands are **typed at a `-->` prompt**, separated by "," or ";", and **abbreviations are OK**.
- Three command forms: `<command>`, `<command = value>`, or `<command value>`.
- Commands are grouped into: **Actions** (`help`, `view`, `exit`, `quit`, `backup`, `hardcopy`/`hc`, `mode`); **Shot & Pointname** (`shot`, `point1`, `point2`, `dtheta`, `integrate`, `bdot`); **Spectrogram Plot** (`tmin`, `tmax`, `dt`, `fmin`, `fmax`, `df`, `zmin`, `zmax`, `nlog`); **Subinterval Plot** (`t0`, `tslice`, `zoom`); **Mode Analysis** (`nmin`, `nmax`, `mmin`, `mmax`, `f0`).
- The bracket/symbol annotations next to commands (`shot [ ]`, `t0 { }`, `tslice < >`, `f0 ( )`) appear to be the **increment/decrement (select/advance) keys** for stepping those values up/down; the deck labels them "select/advance" but does not further define each symbol.

### Example command usage actually shown (page 6)

During the example session the user types these commands at the `-->` prompt (verbatim):
- `-->tmin 2000,tmax 3000,fmax 50` — sets the spectrogram time window to 2000–3000 ms and the frequency max to 50 (kHz); this is the `<command value>` form with multiple commands comma-separated on one line.
- `-->mode` — invokes the mode-analysis (single-mode / multiple-mode fit) display.

### Spectrogram details

From page 2 and the page-7 screenshot:
- The spectrogram plots **dB/dt power vs. time (x-axis) and frequency (y-axis)**, and is **color-coded by toroidal mode number** (this is the `newspec`-equivalent display).
- In the screenshot's SPECTROGRAM window (page 7): x-axis "Time (msec)" 2000–3000; the bottom panel y-axis "f (kHz)" 0–50. A color legend on the right reads **"Mode Number"** with discrete colors for integer n values labeled (reading top to bottom) 6, 5, 4, 3, 2, 1, 0, -1, -2, -3, -4, -5, -6 — i.e., the toroidal mode number n is color-mapped over roughly −6…+6.
- The screenshot header lists "delta-t 4.00 ms", "delta-f 1.00 kHz", "smoothing 5 pts", "mode numbers +/- 5" (these are the FFT window, frequency resolution, smoothing, and mode-number search range parameters in effect).
- A separate **"Cross-Power (T^2/sr^2/kHz)"** legend appears, with contour-level entries (e.g. `1.65E+00`, `1.65E-02` style — exact intermediate values not fully legible).

### How it identifies toroidal n and poloidal m

- **Toroidal n:** computed from the **phase difference between toroidally separated probes** (the `point1`/`point2` pair separated in φ; in the example, probes at toroidal angles 307 and 340). In the single-spectrum plot, "toroidal mode number vs. f" is one of the outputs (page 2). The spectrogram is color-coded by n.
- **Poloidal m:** the **single-mode fit** (page 2, "~ mode1") fits **phase only, for a single time interval** to determine n and m vs. frequency. The MODE STRUCTURE window in the screenshot (page 7) shows separate **TOROIDAL ARRAY** (Phase vs. Phi) and **POLOIDAL ARRAY** (Phase vs. Theta) plots — the slope of phase vs. toroidal angle φ gives n, and phase vs. poloidal angle θ gives m. The `dtheta` command (page 4) and the `mmin`/`mmax` limits support the poloidal m analysis.
- The text-console portion of the screenshot (lower-left, page 7) shows a fit table: columns "n fit / stdev (rad.)" and "m fit / stdev (rad.)", listing candidate n=1,2 and m=1..5 with standard deviations, and "Best fit: m/n = 2 / 1" — demonstrating the multi-mode fit selecting m=2, n=1.

### Phase & coherence analysis

- **Coherence** is plotted in the SUB-INTERVAL window (page 7): a "Coherence" panel with y-axis 0–1.0 vs. f (kHz). Coherence between the probe pair is used to gauge reliability of the phase/mode-number determination.
- **Phase analysis** is central to the mode fitting (n from toroidal phase slope, m from poloidal phase slope), shown in the MODE STRUCTURE Phase-vs-angle plots.

---

## Analysis methods / math

The deck states the method at a high level but gives no equations:
- **FFTs** are computed on the raw probe signals ("CALCULATING FFTs", page 6).
- **Cross-spectra** between the two probes are computed ("CALCULATING CROSS-SPECTRA", page 6); cross-power and coherence come from these.
- **dB/dt** is the native signal; optional **numerical integration** (`integrate`/`bdot` commands) converts dB/dt → B.
- **Mode-number determination** is by **phase fitting**: single-mode fit "of phase only" (n, m vs. frequency, ~mode1), and a new **multiple-mode fit** of the **instantaneous δB** to extract an n, m spectrum.
- FFT/processing parameters shown (page 7): delta-t = 4.00 ms (FFT window), delta-f = 1.00 kHz (frequency resolution), smoothing = 5 pts, mode-number search ±5.

No explicit formulas, fit algorithms, error definitions, or windowing/normalization conventions are given in the document.

---

## Visualizations to reproduce

The page-7 screenshot ("Screen shot of typical output") shows **four IDL plot windows** open simultaneously for shot 148283 (a "Connect to Cybele" X11 desktop). Described from direct image inspection:

### 1. SPECTROGRAM window (`SPECTROGRAM 148283`), top-left — the "newspec-type spectrogram"
Three stacked panels sharing an x-axis of **Time (msec), ~2000–3000**:
- **Top panel:** raw time trace, y-axis **"dB/dt (T/s)"** roughly −40 to +60 (tick labels 60/40/20/0/−20/−40 visible). White trace on black; shows a burst of activity growing ~2350–2800 ms.
- **Middle panel:** **"rms dB/dt (T/s)"**, y-axis ~0–15. Multiple colored line traces (color = mode number); a red curve rises to a broad hump ~2400–2750 ms.
- **Bottom panel:** the spectrogram proper — y-axis **"f (kHz)" 0–50**, x-axis Time (msec) 2000–3000, on a black background with colored points (color = toroidal mode number). Coherent low-frequency mode branches sweep upward in the 2400–2800 ms region.
- **Right-side annotations:** "Shot 148283", "MPI66M307E", "MPI66M340E"; parameter block "delta-t 4.00 ms / delta-f 1.00 kHz / smoothing 5 pts / mode numbers +/- 5"; a discrete **"Mode Number"** color legend spanning roughly +6 to −6; and a **"Cross-Power (T^2/sr^2/kHz)"** contour-level legend.

### 2. SUB-INTERVAL window (`SUB-INTERVAL 148283.02500`), top-right — the "single-time / newspec-type spectrum"
Header "Shot 148283". Four stacked panels:
- **Top:** time trace **"dB/dt (T/s)"** ~−20 to +20, x-axis **"time (ms)" ~2499–2501** — shows a clean oscillation (~10 cycles across ~2 ms ⇒ ~5 kHz).
- **2nd:** **"Coherence"** 0–1.0 vs. f.
- **3rd:** **"n mode"** vs. f, y-axis labeled with integer n (range about −3…+3).
- **Bottom:** **"Cross-power (T^2/sr^2/kHz)"** on a **log y-axis** (~0.001 to 100.000) vs. **"f (kHz)" 0–50**; a sharp peak near a few kHz.

### 3. ARRAY DATA window (`ARRAY DATA 148283.02500`), bottom-center
Header "Shot 148283". Contains:
- A top time trace **"dB/dt (T/s)"** ~−20..+30, x-axis **"Time (msec)" 2498–2502**.
- Two 2-D color (contour/image) panels with a **dB/dt (T/s)** color bar (~−30 to +30): one with y-axis **"phi (deg.)" ~0–300** (toroidal array data vs. time) and one with y-axis **"theta (deg.)" ~−100..+300** (poloidal array data vs. time) — diagonal stripes showing the rotating mode pattern.
- To their right, small profile/fit panels with labels "n" and amplitude ("Ampl.") columns (e.g., n 2, Ampl. 0.647) and an m list (m 1–5 with amplitudes).

### 4. MODE STRUCTURE window (`MODE STRUCTURE 148283.02500`), bottom-right — the "mode1-type phase analysis"
Header "Shot 148283   2498.00 — 2502.00 ms   3.00 kHz". Two columns: **TOROIDAL ARRAY** and **POLOIDAL ARRAY**. Each column has three stacked panels:
- **Coherence** (top, y 0–1.0).
- **Phase (deg.)** (middle, y ~0–300) — for the toroidal array, points fall on a clean straight line vs. **Phi (deg.) 0–300** (slope ⇒ n); for the poloidal array, points vs. **Theta (deg.) 0–300** (slope ⇒ m).
- **Cross-power (T^2/sr^2/kHz)** (bottom) vs. angle.

### 5. Text console (lower-left of the desktop, page 7)
Shows the fit output tables: "n fit / stdev (rad.)", "m fit / stdev (rad.)", with lines such as `m 2  0.66 *`, `n 1 0.03 *`, "Best fit: m/n = 2" and "Best fit: m/n = 2 / 1", and the `-->nmax 2` command, plus the live `-->` prompt.

The slide's call-out labels (page 7 text, verbatim) tie these together: "Single-time / Newspec-type spectrum", "spectrogram", "m=2 / n=1", "Raw data vs. time & position", "Mode1-type phase analysis".

---

## Concrete example values (only those actually appearing)

- **Shot number:** **148283** (used throughout the example and screenshot).
- **Probe pointnames:** **MPI66M307E** and **MPI66M340E** (toroidal angles 307° and 340° implied by the names).
- **Samples returned per probe:** **2,031,616** ("2031616 samples returned", page 6, for each probe).
- **Example launch command:** `IDL> modespec,148283,1000,4000,/small` (page 6) — shot 148283, tmin 1000, tmax 4000, /small.
- **Typed commands in session:** `tmin 2000,tmax 3000,fmax 50` and `mode` (page 6).
- **Spectrogram contour values printed:** **16.4926, 1.64926, 0.164926, 0.0164926** (page 6, appears twice).
- **Sub-interval / mode-analysis time tag:** **148283.02500** ⇒ t0 ≈ 2500 ms (window 2498.00–2502.00 ms per MODE STRUCTURE header, page 7).
- **FFT/analysis parameters (screenshot, page 7):** delta-t = 4.00 ms, delta-f = 1.00 kHz, smoothing = 5 pts, mode numbers ±5; MODE STRUCTURE analysis frequency = 3.00 kHz.
- **Mode identified:** **m = 2, n = 1** ("Best fit: m/n = 2 / 1", screenshot console; slide label "m=2 / n=1", page 7).
- **Fit values readable in screenshot console:** n=1 stdev 0.03 (rad., flagged best `*`), n=2 stdev 1.86; m fit list m=1 (1.80), m=2 (0.66, best `*`), m=3 (1.91), m=4 (0.96), m=5 (1.86) (rad.); an array-fit amplitude n=2 Ampl. 0.647.
- **IDL color table loaded:** "STD GAMMA-II" (page 6, "% LOADCT: Loading table STD GAMMA-II").

(All frequency-axis ranges quoted, e.g. f 0–50 kHz, are read from the on-screen axes; the fmax=50 command sets that.)

---

## Notable quotes (verbatim, with page numbers)

- "Modespec: a replacement for newspec & mode1" (page 1).
- "Modespec is a new analysis code for quick MHD mode identification" (page 2).
- "Modespec combines the functionality of newspec and mode1" (page 2).
- "Spectrogram of dB/dt vs. time and frequency – Color coded for toroidal mode number" (page 2).
- "Multiple-mode fit  n, m spectrum (new) – Fit of instantaneous δB" (page 2).
- "Written in idl – newspec and mode1 use fortran and disspla" (page 3).
- "Driven by typed commands – commands and syntax similar to newspec & mode1 – hope to develop a GUI" (page 3).
- "Enter commands, separated by \",\" or \";\" Abbreviations OK. Form is <command> or <command = value> or <command value>" (page 4).
- "IDL> modespec,148283,1000,4000,/small" (page 6).
- "% LOADCT: Loading table STD GAMMA-II" (page 6).
- "148283 MPI66M307E ier = 0  2031616 samples returned" (page 6).
- "CALCULATING FFTs / CALCULATING CROSS-SPECTRA / 2-D SPECTROGRAM / Contour Values: 16.4926 1.64926 0.164926 0.0164926" (page 6).
- "Include "/u/strait/idl" in your idl path." (page 8).
- "modespec, (shot), (tmin), (tmax), (t0), (/small)" with definitions "(shot) is the shot number / (tmin) is start time for spectrogram plot / (tmax) is end time for spectrogram plot / (t0) selects time for the single-spectrum plot / /small selects plot window suitable for a laptop screen" (page 8).
- "Modespec is stable but still needs development / Please let me know of bugs / Please suggest improvements" (page 9).

---

## How to start MODESPEC (page 8, verbatim content)

- Include **"/u/strait/idl"** in your IDL path. Then at the IDL prompt:
  - Type **`modespec`**, then enter commands — OR —
  - Provide parameters positionally: **`modespec, (shot), (tmin), (tmax), (t0), (/small)`**, where:
    - `(shot)` = shot number
    - `(tmin)` = start time for spectrogram plot
    - `(tmax)` = end time for spectrogram plot
    - `(t0)` = selects time for the single-spectrum plot
    - `/small` = plot window suitable for a laptop screen
