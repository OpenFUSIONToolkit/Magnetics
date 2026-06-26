# Tokamak 3D Magnetics Analysis Tool — Vision & Requirements

*Synthesis of the research phase for the 2026 Magnetics Hackathon (Columbia, Jun 29 – Jul 1).
Distilled from the OMFIT magnetics module, the OMFIT magnetics tutorial, E. Strait's
DIII-D magnetics literature (RSI 2016, HTPD 2016/2018, the SLCONTOUR and MODESPEC decks,
the UC-Irvine diagnostics seminar), and the device-access work done for the demos.
Everything here is meant to be grounded in those sources — see `resources/` and the
per-document summaries in `docs/research-summaries/`.*

> **Status:** this is the *requirements/vision* document — the lasting artifact. Standalone
> concept-demo GUIs (a web workbench, a native console, a 3D mode visualizer) and a prototype
> backend were built separately to explore these ideas; this document captures what they informed.

---

## 1. Purpose & end goal

Build a **modern, fast, modular GUI plus a standalone Python analysis library** that lets a
user quickly and intuitively perform and visualize **standard 3D magnetic-sensor analysis of
tokamak MHD instabilities** — the spatial-temporal decomposition of both **quasi-stationary
(quasi-symmetric / locked) modes** and **rapidly-rotating modes**.

The hackathon target is a **minimum viable product in 3 days**: a working GUI skeleton with a
clean modular architecture, whose minimum analysis capability is

1. **reproduction of the OMFIT magnetics decomposition for quasi-stationary modes** measured by
   toroidal arrays of local sensors, and
2. **spectrogram analysis for rapidly-rotating modes**.

Beyond the MVP, the explicit ambitions are:

- **Cross-tokamak.** The tool should not be DIII-D-specific. It must work across machines
  (DIII-D, NSTX-U, AUG, KSTAR, EAST, HBT-EP, …) and even **non-real / synthetic tokamaks**.
- **Sensor-system design.** Because the analysis is just geometry + a basis, the *same* code
  should support **designing** sensor arrays for hypothetical machines (how many sensors,
  where, to resolve which modes at what noise level).
- **Modular & extensible.** A clean seam between data access, analysis, and GUI so capabilities
  can be added without rewrites, with an upgrade path toward a general, PDV-like data viewer.
- **Consolidation.** Replace today's fragmented toolset (OMFIT magnetics GUIs + the legacy IDL
  tools SLCONTOUR and MODESPEC) with one coherent interface.

---

## 2. Physics background (what we measure and why)

Tokamak plasmas develop **non-axisymmetric ("3D") magnetic field perturbations** from MHD
instabilities and from applied 3D fields. These perturbations are **small — typically 10⁻³ to
10⁻⁵ of the total magnetic field** — and slowly varying, which makes them challenging to
measure and motivates the specialized sensor sets and conditioning below.

A perturbation is characterized by its **toroidal mode number n** (variation the long way
around the torus) and **poloidal mode number m** (variation the short way around), with
structure approximated by **δB(φ,θ) ∝ exp[i(nφ − mθ)]**.

Modes of interest:

- **Tearing modes (TM)** — resistive instabilities forming magnetic islands at rational
  surfaces (q = m/n). The canonical measurement is the **growth → slowing → locking** of an
  initially rotating tearing mode (often **m/n = 2/1**).
- **Locked modes (LM)** — modes that have stopped rotating and phase-locked to the wall;
  quasi-stationary, so **time-domain Fourier analysis cannot be used** — they need *spatial*
  fitting at single time slices.
- **Rotating modes** — precess toroidally at finite frequency (kHz). Rotation makes them
  *easier* to measure (Ḃ = ωB is large) and enables time-domain Fourier / spectrogram analysis.
- **Sawteeth** — central relaxation oscillations; can be confused with 2/1 tearing modes in
  rotating-mode analysis (a known discrimination problem to solve).
- **ELMs / kink modes / stable 3D plasma response** to applied error-field-correction (EFC)
  and resonant-magnetic-perturbation (RMP) fields.

The same hardware also feeds **axisymmetric equilibrium reconstruction (EFIT)** and real-time
plasma control, but the focus of this tool is the **non-axisymmetric** analysis.

---

## 3. The diagnostics / hardware

All sensors are **inductive**, based on Faraday's law (V = −dφ/dt); the physical meaning of the
flux φ depends on the loop geometry. A key, recurring engineering point: **the raw signal is a
voltage ∝ dφ/dt, so it must be integrated** (active op-amp integrators; integrator drift is the
defining challenge), and **even numerical integration inherits the offset-drift problem.**

**Sensor types (device-agnostic):**

| Sensor | Measures | Notes |
|---|---|---|
| Magnetic probe (Bp / Br, "Mirnov") | local field component (φ = N·A·B) | small coil; poloidal (Bp) or radial (Br) |
| Saddle loop | average B normal to loop | rectangular; can be meters across |
| Toroidal / diamagnetic flux loop | toroidal flux Φ | plasma stored energy |
| Poloidal flux loop | poloidal flux ψ (φ = 2πψ) | key EFIT input; ∇ψ = R·Bp |
| Rogowski coil | enclosed current (e.g. Ip) | central return rejects external flux |

**DIII-D "3D" set (the reference implementation):**

- **66 Bp probes (32 HFS + 34 LFS) + 64 Br loops**, giving 2-axis coverage at ~64 wall
  locations; n ≤ 3 at 5 poloidal locations, n ≤ 4 at the LFS midplane; m ≤ ~6 from 15 poloidal
  locations.
- Wired as **toroidally-separated differential pairs**, ΔB = [B(φ₁) − B(φ₂)]/2, to **reject the
  n = 0 field** (which is ~10⁴× larger than the 3D signal). Variable separations (LFS midplane
  77°–180°, other arrays 15°–180°) minimize spatial degeneracy.
- Integrated and digitized at **20 or 50 kHz** (fast Mirnov channels run much higher).
- Key named arrays: LFS toroidal Bp (e.g. `MPI66M*` / pairs `MPID66M*`), 322° poloidal array
  (31 probes, origin R = 1.695 m, Z = 0), plus saddle (`ISLD`/`ESLD`) and coil (`C`, `IU/IL`)
  sets. SLCONTOUR recognizes **>95 named arrays** via keyword search.
- EFIT input for reference: 44 poloidal flux loops, 76 magnetic field probes, 18 PF-coil
  Rogowskis, plus OH/TF Rogowskis, BT probes, diamagnetic loop.

**NSTX-U (second device, verified during this work):**

- Magnetics live in the MDSplus **`fastmag` tree** (not PTDATA): an **hf poloidal Mirnov array**
  (`\top.mirnov.rawdata:fm_dt216_01:input_NN`) sampled at **~15 MHz**, and an **hn toroidal Ḃ
  array** (`\bdot_l1dmivvhnK_raw`) at ~1 MHz. Geometry + calibration (`raw·gain/na`) come from
  shot-indexed text configs (`/u/eric/nstx/mm/`), not MDSplus.

The lesson for the architecture: **sensor geometry, calibration, and access differ per device,
but the analysis downstream is identical** — so device specifics must be isolated behind a thin
"source" boundary.

---

## 4. The two core analyses

### 4.1 Quasi-stationary / spatial fitting (the "SLCONTOUR" capability)

For non-rotating or slowly-evolving modes (locked modes, stable 3D response), fit the spatial
field pattern at each time slice independently:

- **Basis:** cylindrical Fourier harmonics **δB(φ,θ) = Σ bₙₘ exp(i(nφ − mθ))**. (For a toroidal
  array only m = 0; for differential pairs n = 0 is automatically eliminated.) Other bases
  matter for special geometries (vertical/HFS, spherical at R = 0), and Gaussian RBFs are an
  alternative.
- **Fit:** "normal-equations" least squares, **B = (AᵀA)⁻¹AᵀS**, where A is the design matrix of
  basis functions evaluated at each sensor (finite-extent sensors get a sinc-like averaging
  factor). SVD is used to condition A.
- **Quality metric:** the **condition number K = max(wᵢ)/min(wᵢ)** of A — *the* central design
  and trust metric. SLCONTOUR warns at **K > 10** and errors at **K > 20**. Plus reduced χ² and
  the per-coefficient covariance (error bars).
- **Resolution rules:** an N-sensor toroidal array resolves |n| ≤ (N−1)/2; partial poloidal
  coverage Δθ resolves m in integer multiples of 2π/Δθ; over-fitting an array produces
  meaningless results (the classic example: 8 equally-spaced sensors cannot resolve n = 4 —
  they constrain only the cosine).
- **Signal conditioning ("prep"):** trim to a time window, band-pass filter, **detrend / baseline
  subtraction** (SLCONTOUR offers ~14 `btype` algorithms for transient / long-pulse / periodic
  data), and optional SVD conditioning to drop incoherent noise (keep ~98% of energy).
- **Advanced:** separation of **internal (plasma) vs external (coil/eddy-current) sources** using
  the two-axis (Bp, Br) data and the Laplace phase relation **b_θ = ±i b_r** (SLCONTOUR2 /
  "Gauss algorithm"); synchronous detection of an applied field at a known/reference frequency.

**Outputs:** φ–θ contour of the reconstructed δB (with sensor positions overlaid), amplitude &
phase of each (n,m) mode vs time, condition number / χ², and a φ-vs-time contour for toroidal
arrays.

### 4.2 Rapidly-rotating / spectral analysis (the "MODESPEC" capability)

For rotating modes, exploit toroidal rotation and use time-domain Fourier methods:

- **Spectrogram** of Ḃ vs time and frequency, **color-coded by toroidal mode number n** (the
  signature MODESPEC view; n from −6…+6).
- **Toroidal n** from the **2-point cross-correlation** between toroidally-separated probes:
  **n = ΔΦ/Δφ** (phase difference / angular separation), generalized to a weighted phase-vs-φ
  fit across the whole array. **Poloidal m** from the phase-vs-θ slope.
- **Coherence** (0–1) and cross-power gate which (t, f) cells carry a real, resolvable mode.
- **Poloidal-m is hard** because of toroidicity and plasma shaping: the poloidal wavelength
  varies around a flux surface. Approaches: a straight-field-line / PEST angle
  **θ\* = θ − λ₁sinθ − λ₂sin2θ + …** (λ = toroidicity / elongation / triangularity / squareness),
  derivable from EFIT field-line integrals or the analytic Merezhkin correction, or fit
  empirically (`fittype`). **Caution:** enabling shaping terms can change the best-fit m (e.g.
  flip 2/1 → 4/1) — so m identification needs care and clear uncertainty reporting.
- **Synchronous detection:** when a 3D field is applied at a known rotation frequency, a running
  Fourier filter at that frequency isolates the plasma response from noise/other MHD.

**Outputs:** the n-colored spectrogram, single-time spectra (power / coherence / n vs f),
phase-vs-φ and phase-vs-θ mode-number fits, and time traces of mode amplitude/phase.

---

## 5. The current workflow and its pain points

The OMFIT magnetics module already implements the physics as **fetch → prep → fit → plot** (plus
a separate spectrogram pipeline and the IDL SLCONTOUR/MODESPEC tools). What a modern tool should
*fix* (these are the concrete UX requirements):

- **Sensor selection is regex-driven** (e.g. `MPID.*`) and requires knowing channel-name
  conventions → replace with **visual array selection** (named arrays, checkboxes, live counts,
  on the machine cross-section).
- **Prep is a manual, multi-step ritual** (trim, band-pass, detrend to fight Ip-ramp pickup and
  integrator drift) with no quick-start presets → provide sensible **defaults + a visual,
  interactive prep** (pick the window on the raw trace).
- **Ill-conditioning is discovered only after fitting** → surface **K / resolvability up front**,
  warn before the user fits modes the array can't constrain.
- **Quality assessment is fragmented** across separate "plot chi / plot SVD / plot modes" buttons
  → a **single, always-visible quality panel** (K, χ², residuals, error bars).
- **Results live in an opaque tree** with unvalidated free-text fit names → a **flat, searchable
  fit registry**.
- **Tools are fragmented** (separate magnetics GUI, coil GUI, SLCONTOUR, spectrogram driver,
  per-device code paths) → **one consolidated interface** with the QS and rotating analyses as
  first-class, linked views.
- **No built-in physics guidance** (when to fit n=1 vs n=2, which analysis to use) → contextual
  hints and good defaults.

---

## 6. What we want — requirements

### 6.1 Analysis core (a standalone Python library)

- **Device-agnostic.** Pure functions over abstract objects: sensors (position, orientation,
  finite extent, wiring), a surface/geometry, and a mode basis. No machine specifics in the math.
- **Reproduce the reference analyses:** the SLCONTOUR-style spatial fit (with K, χ², covariance,
  internal/external separation) and the MODESPEC-style spectral analysis (n-colored spectrogram,
  phase-fit n & m with θ\* options, coherence).
- **Forward model is first-class:** `S = A·b` so you can synthesize signals for hypothetical
  machines/arrays — the basis of **sensor-system design** and of testing.
- **Resolvability / design metrics as outputs**, not just warnings: condition number, the
  Nyquist limit |n| ≤ (N−1)/2, per-mode error bars (AᵀΣ⁻¹A)⁻¹, spatial-aliasing limits.
- **Pluggable bases** (Fourier now; Gaussian RBF; a future "plasma-mode" basis = surface currents
  on rational surfaces + a GPEC kink mode).
- **Importable in notebooks**, fully testable, independent of any GUI or web framework.

### 6.2 Data sources (the device boundary)

- A single `DataSource` interface; one implementation per device/mode:
  **DIII-D** (PTDATA via `atlas.gat.com`), **NSTX-U** (`fastmag` tree via `skylark.pppl.gov`),
  a **file** source (cached/reduced), and a **synthetic** source (non-real tokamak, forward-modeled).
- Sources own geometry tables, calibration, units, and access; everything downstream is identical.
- **Reduce near the data:** raw rates are huge (DIII-D 200 kHz–1 MHz, NSTX-U ~15 MHz) — decimate /
  compute spectrograms / fit on the cluster and ship only reduced arrays to the GUI.

### 6.3 Architecture (serving & deployment)

- **One Python backend** (analysis core) wrapped by a **thin web service** (FastAPI/Flask). The
  web framework is disposable; the analysis library is the asset. Physics never lives in route
  handlers.
- **Self-describing results contract:** every analysis returns `{kind: "heatmap" | "contour" |
  "scatter2d" | "metrics" | …, …}` so the frontend renders generically and new analyses need no
  frontend changes. This is the **upgrade path toward a general tree-of-nodes (PDV-like) viewer.**
- **Runs where the data is.** The service runs on the analysis cluster (omega for DIII-D, flux for
  NSTX-U) with in-process MDSplus; the GUI is served from there with one forwarded port, or runs
  locally against the tunneled API. Same backend serves the web GUI, a native console, and notebooks.
- **Caching** of reduced (and ideally intermediate/raw) per-shot data so re-fits and scrubbing are
  interactive.

### 6.4 GUI / frontend

- **Thin and generic:** renders results, never computes.
- **Modern web stack** (React + a JS plotting library) is the primary GUI; a native option
  (e.g. PySide6 + pyqtgraph) is viable for power users on the analysis server.
- **Core views** (linked by a shared time cursor):
  1. **Sensors** — machine R–Z cross-section + unrolled φ–θ wall map; visual array selection.
  2. **Quasi-stationary** — φ–θ δB contour (sensors overlaid), time scrubber, n/m amplitude &
     phase vs time, prominent K/χ² quality.
  3. **Rotating modes** — n-colored spectrogram with linked cursor, phase-vs-φ / phase-vs-θ fits,
     coherence, the θ\* / fittype controls.
  4. **Fit registry / export** — all analyses for a shot in one place with quality flags.
- **Multi-device** from the same UI (DIII-D, NSTX-U, synthetic) — the UI is data-driven.
- A **3D view** (torus colored by the fitted δB(φ,θ), rotating/locked animation) is a strong
  optional/educational mode.

---

## 7. Visualizations to support (grounded catalog)

| View | Axes / encoding (typical) |
|---|---|
| φ–θ contour (locked mode) | x = φ 0–360°, y = θ (−90–270°), color = δBp diverging ±~40 G, **white squares = sensor positions** |
| φ-vs-time contour (toroidal array) | x = time (ms), y = φ 0–360°, color = δB |
| Amplitude & phase vs time | per (n,m) trace with error bands; phase 0–360° |
| Spectrogram (rotating) | x = time (ms), y = frequency (kHz), color = **toroidal n (−6…+6)** or log power |
| Phase-vs-φ / phase-vs-θ | scatter + linear fit; slope = n (φ) or m (θ); coherence panel |
| Single-time spectrum | power / coherence / n vs frequency (kHz) |
| SVD / conditioning | cumulative energy vs singular-value index; condition number vs fit range |
| Sensor maps | R–Z cross-section; unrolled φ–θ wall map; (optional) 3D torus surface colored by δB |

Conventions: angles in degrees, time in ms, frequency in kHz, field in Gauss; diverging
blue-white-red for signed field; a discrete palette for mode number; traffic-light coloring for
quality (K / coherence).

---

## 8. Reference shots & example values (for tests / demos)

- **DIII-D 164672** @ 3140 ms — the canonical **m/n = 2/1 locked tearing mode**; 66-Bp φ–θ
  contour (±40 G); a well-conditioned 2-D fit (K ≈ 7).
- **DIII-D 162432** — toroidal-array growth of n = 2 then n = 1 locked modes (~1700–2200 ms).
- **DIII-D 165878** — plasma response to an applied **n = 1 field rotating at 20 Hz** (synchronous
  detection example).
- **DIII-D 154551** — LFS Bp SVD: a rotating n = 1 that slows and locks; first 2 singular values
  ≈ 98% energy.
- **DIII-D 158116** @ 4850 ms — HFS high-m (m ~ 10) response to an applied n = 2 field.
- **DIII-D 174436 / 174446** — SLCONTOUR2 / MODESPEC worked examples (rotating then locked).
- **DIII-D 148283** — the MODESPEC reference (probes MPI66M307E/340E, m/n = 2/1 near 3 kHz).
- **NSTX-U 204718** — verified `fastmag` access (hf Mirnov ~15 MHz, hn toroidal ~1 MHz).
- Typical scales: 3D amplitudes 10⁻³–10⁻⁵ of total field; locked-mode δBp tens of G; rotating
  modes ~kHz; noise floor ~10⁻⁵ T; condition-number thresholds 10 / 20.

---

## 9. Future / upgrade directions (beyond the MVP)

From the hackathon agenda (Logan's "future analysis upgrades") and the literature:

- **Discriminate sawteeth from 2/1 tearing modes** in rotating-mode analysis.
- **Modified poloidal angles (θ\*)** for Fourier decomposition, properly handling toroidicity and
  shaping (and honest uncertainty when shaping terms change the answer).
- **Fit a basis of *plasma* modes** rather than geometric harmonics: surface currents on rational
  surfaces + an ideal kink mode from GPEC — closing the gap between "fitting functions" and real
  MHD structure.
- **Internal vs external source separation** as a standard product (two-axis Bp/Br).
- **Real-time / control-room** operation (causal conditioning, fast fits).
- **Sensor-system design** workflows for future machines (optimize placement against a target
  mode set and noise budget) — enabled directly by the forward model + resolvability metrics.
- **Cross-machine breadth** (AUG, KSTAR, EAST, HBT-EP) via new data sources.

---

## 10. Glossary

- **n, m** — toroidal / poloidal mode numbers.
- **q** — safety factor; rational surfaces at q = m/n host tearing modes.
- **Tearing / locked / kink mode, sawtooth, ELM** — see §2.
- **Ḃ (bdot)** — dB/dt, the raw Mirnov/probe signal before integration.
- **Differential pair** — two toroidally-separated sensors subtracted to reject n = 0.
- **K (condition number)** — max/min singular value of the design matrix; fit trust metric
  (warn > 10, error > 20).
- **Synchronous detection** — Fourier filtering at a known applied-field frequency.
- **θ\*** — straight-field-line (PEST-like) poloidal angle correcting for toroidicity/shaping.
- **EFC / RMP** — error-field correction / resonant magnetic perturbation (applied 3D fields).
- **SLCONTOUR / MODESPEC** — DIII-D's legacy IDL tools for quasi-stationary spatial fits and
  rotating-mode spectral analysis, respectively — the capabilities this tool consolidates.
```
