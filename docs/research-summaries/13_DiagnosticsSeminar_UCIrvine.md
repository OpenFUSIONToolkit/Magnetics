# 13 — Strait, "Magnetic Diagnostics" (UC-Irvine Plasma Diagnostics seminar)

**Source file:** `resources/Magnetics Hardware and Analysis Overviews/Strait_Magnetic_Diagnostics_Seminar_UCIrvine.pdf`
**Pages:** 40 (PowerPoint export, created 2021-01-11)

> ACCURACY NOTE: Everything below is taken verbatim or paraphrased directly from the slide text and the one figure I rendered (page 6). Slide text from PowerPoint exports is run together and sometimes out of reading order; where layout was ambiguous I flag it. Numbers, shot IDs, sensor counts, and frequencies are reproduced exactly as printed. Where I am inferring figure appearance I say so explicitly.

---

## Document overview

A broad pedagogical seminar by **Ted (E.) Strait**, "Magnetic Diagnostics," presented to the **Plasma Diagnostics course at UC-Irvine, Jan. 12, 2021** (title page p.1). Footer on every page reads "E. Strait / Conference / Date." Focused on **DIII-D** (DIII-D National Fusion Facility, San Diego — logo on every slide).

Scope, stated on pp.2-3: "Magnetic diagnostics measure in DIII-D — Magnetic flux; Local magnetic fields; Currents that generate the fields. This talk will focus on **inductive measurements using sensors external to the plasma**." Notes (p.3) that "ITER will use mainly inductive magnetic diagnostics" and that "Reliable, compact non-inductive options are limited," listing three non-inductive backups:
- Hall probes — backup for local B field (ex-vessel)
- Faraday rotation in optical fiber — backup for Ip (ex-vessel)
- MEMS based on Lorentz force — "considered as backup for local B field, but not accepted"

**Outline (p.5), verbatim structure:**
- Types of inductive sensors: Magnetic probes, Flux loops, Saddle loops, Rogowski loops
- Applications of magnetic data: Magnet and plasma currents; Equilibrium reconstruction (2-D); Non-axisymmetric (3-D) fields; MHD instabilities
- Instrumentation: Active integrators; Combinations of multiple signals
- Characterization of measurements: Calibration; Position; Uncertainties; Validation
- Challenges and potential pitfalls: Magnetic shielding; Integrator drift; Sensor misalignment
- Non-inductive methods (brief summary)

**Four purposes (p.4 figure montage and p.13 list):** Rotating MHD modes; Stationary MHD modes & 3D fields; Axisymmetric equilibrium and plasma control ("= shape control points for real-time EFIT"). Page 13 reformulates as: single-channel measurements of key quantities (toroidal field, plasma current, coil currents); axisymmetric equilibrium reconstruction (magnetics alone or with other diagnostics); non-axisymmetric plasma features (stationary MHD modes, stable response to external 3D fields); MHD instabilities (tearing modes, ideal kink modes). Used in both "Real-time plasma control" and "Off-line analysis."

---

## Magnetic sensors / hardware

**Common physical basis (p.6):** "Inductive magnetic sensors are based on Faraday's Law: V = − dφ/dt" (V = measured voltage; φ = flux linked by a conducting loop). "Physical interpretation of the flux φ depends on the configuration of the loop."

**Page-6 figure (rendered, confirmed):** a 3-D line drawing of a torus showing five labeled sensors arranged around/on it:
- **Diamagnetic Loop** — a loop lying in a poloidal plane, wrapping around the minor cross-section of the torus (top).
- **Rogowski Coil** — a long helical (coiled-spring) winding running poloidally around the torus minor circumference (left).
- **Saddle Loop** — a small rectangular loop patch lying flat on the outer torus surface (bottom-center).
- **Flux Loop** — a wire going around the major circumference of the torus (right).
- **Magnetic Field Probe** — a small short solenoid/coil sitting just outside the torus wall (far right).
  *(Caption note: this drawing labels the vertical poloidal-plane loop "Diamagnetic Loop"; the body slides p.6/p.10 call the same geometry the "Toroidal Flux Loop." Treat them as the same sensor type.)*

### Sensor-by-sensor

**1. Magnetic probe — poloidal field, Bp (p.7).** "Small(ish) coil measures local B parallel to its axis: φ = N·A·B∥, where N = number of turns, A = cross-sectional area." A dimension "14 cm" is annotated on the probe figure. Measures the **local poloidal field Bp**.

**2. Magnetic probe / saddle loop — radial field, Br (p.8).** "Rectangular loop measures average B normal to plane: φ = N·A·B⊥, where N = number of turns, A = cross-sectional area." Annotated dimensions "33 cm" and "14 cm." Note: "Saddle loops may have dimensions of meters, depending on machine size." Measures **Br (radial field)**.

**3. Rogowski loop — current, e.g. plasma current Ip (p.9).** "Long, thin coil measures the line integral of B: φ = Σ A B ≈ n A ∮ B·dl, where n = turns per unit length, A = cross-sectional area." For a Rogowski enclosing current Ip: "φ = μ₀ n A I_P." Diameter annotated "d ~ 6.3 mm." Key design point: "Central return conductor avoids linking other flux through the loop opening (toroidal flux, for example)."

**4. Toroidal flux loop — total toroidal flux Φ (p.10).** "Vertical loop, aligned in a poloidal plane (constant toroidal angle) measures total toroidal flux Φ." "Mainly of interest for the small (in a tokamak) contribution by the plasma, the 'diamagnetic' flux: φ = Φ₀ + Φ_DIA." Dimension "14 cm" annotated. (This is the diamagnetic loop.)

**5. Poloidal flux loop — total poloidal flux ψ (p.11).** "Horizontal, axisymmetric loop measures the poloidal flux ψ: φ = 2π ψ, where ψ is poloidal flux per radian of toroidal angle." "ψ is a key quantity for MHD equilibrium! Note that ∇ψ = R·Bp."

**Installation examples (p.12, "DIII-D centerpost (1985)"):**
- *Ex-vessel:* Rogowski loops (plasma current); Rogowski loops on PF coil leads; Toroidal flux loop; Poloidal flux loops.
- *In-vessel:* Bp & Br loops.

### Counts / locations used by EFIT (p.16, verbatim list, "Magnetic data input to EFIT includes")
- ✔ **44 poloidal flux loops**
- ✔ **76 magnetic field probes**
- ✔ **18 PF coil current Rogowski loops**
- plus … **OH coil Rogowskis; TF coil Rogowskis; BT probes; Diamagnetic loop**

The p.16 cross-section also annotates two toroidal-angle ranges for groups of sensors: "Φ = 140–180" and "Φ = 310–330" (degrees). (See Visualizations.)

### "3D" diagnostic set counts (p.18)
- "**66 Bp probes**" and "**64 Br loops**" (legend: "Bp sensors / Br sensors").
- "n ≤ 3 resolution at 5 poloidal locations; n ≤ 4 at Low Field Side midplane."
- "m ≤ ~6 resolution is provided by 15 poloidal locations."
- Provides "2-axis measurements over most of the wall."

---

## SLCONTOUR

**Not covered.** The string "SLCONTOUR" does not appear anywhere in this document.

---

## MODESPEC

The tool name "MODESPEC" is **not used by name** in this document. However, the underlying technique MODESPEC implements — **2-point cross-correlation between toroidally separated probes to estimate toroidal mode number n, displayed as a spectrogram** — is described in detail on **pp.20-22**.

**Toroidal rotation rationale (p.20, "Toroidal Rotation Simplifies Measurements of MHD Modes"):**
- "dBp/dt = ω·Bp can be large, even when δBp is small — Easier to measure."
- "Rapid rotation allows time-domain Fourier analysis — Frequencies > 1 kHz are fast compared to mode evolution — Fourier analysis yields amplitude and phase vs. spatial location."
- "A single toroidal and poloidal array can resolve the external spatial structure — Mode rotates past each probe." Figure shows a "Poloidal Array Mag Probes" at "Φ ~ 322°" and a "Toroidal Array."

**2-point correlation for toroidal mode number n (p.21, "2-point Correlation Estimates Toroidal Mode Number"):**
- Uses two probes separated in toroidal angle: "**MPI66M307D**" and "**MPI66M340D**" (Shot 174446).
- Method: "Spectrogram plot for 2 probes separated in toroidal angle: Time evolution of the power spectrum, with [color code for toroidal mode number]." n is extracted from "ΔΦ = phase difference / Δφ = toroidal spacing," i.e. **n = ΔΦ / Δφ** (printed as "ΔΦ ← phase difference, Δφ ← toroidal spacing, n = ΔΦ/Δφ").
- Analysis parameters printed on slide: "delta-t 4.00 ms; delta-f 0.50 kHz; smoothing 3 pts; mode numbers −5 to 5."
- Result label: "**m, n = 2, 1**."

**Poloidal mode number m (p.22, "Poloidal mode number identification is less clean due to strong asymmetry in the poloidal direction"):** Two-panel comparison of "322 POLOIDAL ARRAY" (left) and "LFS TOROIDAL ARRAY" (right). For the poloidal array "ΔΦ = 2·Δθ"; for the toroidal array "ΔΦ = Δφ." Result: "n = 1, m = 2." Shot 174446, window 3488–3492 ms, 2.00 kHz.

---

## Analysis methods / math

### Limits of external magnetics (p.14, "What can external magnetic data tell us about the internal details of the plasma?")
- The magnetic field in a bounded volume = (integral over currents within the volume) + (surface integral on the boundary).
- The field external to the plasma is completely specified by (integral over external currents) + (surface integral depending on ψ and B at the plasma boundary).
- External currents are measurable; ψ and B at the boundary can be extrapolated from nearby flux loops and magnetic probes.
- "HOWEVER, the surface distribution of ψ and B at the plasma boundary does not uniquely determine the internal distribution — Can find a surface current that would yield a given distribution of ψ and B." Conclusion: "The information about internal plasma structure that is available in external magnetic data alone is fundamentally limited → Need additional assumptions (and maybe additional data)."

### Grad-Shafranov equilibrium reconstruction / EFIT (p.15)
- Key assumptions: **Force-balance equilibrium ∇p = j × B** and **Axisymmetry (toroidally symmetric)**.
- Differential equation for poloidal flux ψ: "**Δ\*ψ = −μ₀ R² p′(ψ) − F(ψ) F′(ψ)**," with the elliptic operator "Δ\*ψ = ∂²ψ/∂R² − (1/R)·∂ψ/∂R + ∂²ψ/∂z²" and "F(ψ) = R·B_T", "′ denotes ∂/∂ψ."
- "Equilibrium reconstructions solve for ψ(R,z) by fitting to external magnetic data, with parameterized forms of p′(ψ) and F·F′(ψ)."
- "Magnetics-only reconstructions are sufficient for many purposes — Plasma shape and position, plasma energy, internal inductance."
- "Additional diagnostics improve the accuracy of reconstructions — Internal profiles of n, Te, Ti, magnetic field pitch, etc."

### Equilibrium as framework (p.16)
- "Flux surface reconstruction converts Te(R,z) to Te(ψ), for example." (EFIT input list given in Sensors section above.)

### 3-D / non-axisymmetric fields (p.17)
- "Grad-Shafranov equilibrium is fundamentally 2-dimensional — Toroidal angle is assumed to be an ignorable coordinate." For 2-D, ψ comes from axisymmetric flux loops and the toroidal location of Bp probes is unimportant.
- "3-D tokamak plasmas result from non-axisymmetric boundary conditions, or 'locked' (non-rotating) MHD instabilities — 3D amplitudes are small, typically **δBp ≤ few % of axisymmetric Bp**."
- "Underlying axisymmetry allows Fourier analysis in toroidal angle." "Resolution of toroidal mode numbers n = 0, 1, … N requires measurements at a minimum of **2N+1 toroidal locations** → Significant increase in the number of sensors."

### Helical-harmonic fit for locked modes (p.19)
- "Fit of 66 Bp probes yields m=2 / n=1 structure — Data fit to helical harmonics: **δB ~ Σ_{n,m} B_{n,m} exp(i n φ − i m θ)**." Example shot 164672, t=3140 ms. (See Visualizations.)

### Instrumentation math — integration

**Integration is the core requirement (p.23):** "Magnetic flux φ is proportional to the measured quantity, but sensor output voltage is V_S = −dφ/dt; requires integration so that V_OUT = ∫V_S dt ∝ φ."
- **Passive RC integration:** "V_OUT/V_IN = 1/(1+iωRC) ~ 1/(iωRC) if ωRC ≫ 1 (at small ω)." "Passive integration is only feasible at high frequency, short pulse." "Larger RC extends integration to lower frequency, longer pulse — but reduces the output signal."

**Active (op-amp) integration (p.24):** "V_out ≈ (1/RC)∫(V_in − V_in)dt"; transfer function "V_OUT/(V_IN−V_IN) = 1/(1/G + iωRC) ≈ 1/(iωRC) if GωRC ≫ 1." "G is an op-amp with large gain." "Integration error is reduced by 1/G relative to passive RC circuit — Maximum usable pulse length is increased by G." Enables "Quasi-DC (long pulse) integration with adequate amplitude."

**Integrator drift (p.25):** "Chief source of integration error is output drift due to DC offset at the input": "V_OUT = (1/RC)∫(V_IN + V_OFFSET)dt = (1/RC)∫V_IN dt + (V_OFFSET/RC)·t." "Note that numerical integration would have the same problem!" Solution = **Track & Hold circuit** that "corrects input offset — applies an offset correction voltage; minimizes output voltage between tokamak pulses; holds the offset correction during a pulse." "ITER plans analog integrators with input chopped and converted to AC — Allows better removal of DC offset effects — Developed for W7-X, said to be good for 1-hour pulses."

**Instrumentation branches (p.26):** signal chain "Mag. Probe, Flux loop, Rogowski, …" → Variable-Gain Amplifier → Anti-alias filter → A/D. Branches include an Integrator (∫ G/RC dt) producing "B, Ψ, I (Magnetic)" with gains "G" and "1/10 G," a fast-sampling buffered branch "G=1, ext Atten., u, Fast B, Ψ, I," and a "Square wave generator" for calibration; an "External Amplifier: Programmable Gain Amplifier / Balanced Attenuator." Key spec: "Wide range of sensor output voltages ⇒ **Integrator G/RC range: 1 – 2000 s⁻¹**."

**Combining signals (p.27, "Magnetic Signals Are Sometimes Combined … Pre- or Post-integration"):**
- "Differential pairs of toroidally separated sensors reject n=0 field — Increases sensitivity of non-axisymmetric field measurements" — "∫ΔB(φ₁,φ₂)dt" with "Adjustable balance."
- "Poloidal flux loops are differenced with a reference loop — Minimizes the effect of the OH solenoid, which adds ~constant flux everywhere" (loops PSF1A (Ref.), PSF2A, PSF3A shown).
- "Analog plasma current signal is formed post-integration as **IP = (Rog. Loop Flux) − c·∫V_LOOP dt**." "Ex-vessel Rogowski includes plasma and vessel wall currents; [correction term] approximates vessel current, if vessel response is mainly resistive."

---

## Characterization: calibration / position / uncertainty / validation

**Daily signal-path calibration (p.29):** "0.5 Hz square wave input to all integrators — Divided down to match integrator RC/G. Integrated output → triangle wave." Yields: measured RC/G; noise & linearity of integration; integrator drift; DC offset.

**Bench calibration of probes/Rogowskis (p.30):** "Magnetic probes are calibrated in a solenoid coil — Reference is a loop of well-known dimensions — Typical frequency = 1 kHz." "Rogowski is linked by multiple turns of wire — Reference is a factory-calibrated current transformer." "Estimated uncertainty: ~0.3%."

**Position measurement (p.31):** "Measurement method ca. 1985"; "ca. 2013: Digital measurement arm"; "ca. 2019: Laser scanner (not shown)." "Quoted uncertainties: 2 mm … 1 mm."

**Uncertainty budget (p.32, "Estimated Uncertainties of 1-2%"):**
- PF coil Flux Loops: 2.3 % (dominated by position) — "<δS>/<S> = 2.27%"
- Vessel Flux Loops: 1.2 % (position) — "1.21%"
- Magnetic Probes: 1.0 % (position, tilt angle) — "0.98%" (labeled "322 Magnetic Probes")
- PF coil Rogowskis: 0.9 % (integrator drift) — "0.94%"
- Bar-chart error categories listed: Bt, tilt, port, leads, noise, C-coil, int cal, bit res, int. drift, loop cal, position, LT int cal, nonlinear, LT loop cal.

**Validation vs. PF coils (p.33):** "18 PF coils are pulsed individually with ~1.5 second flattop. Measurements are predicted from EFIT Green's function tables."
- "PSF3A (HFS flux loop) agrees to 0.4%" — "PSF3A (Ψ, V-s/rad) slope = 0.996."
- "MPI7NA322 (LFS Bp probe) agrees to 1.2%" — "MPI7NA322 (Bp, T) slope = 0.988."

---

## Challenges / pitfalls

**Topics (p.34):** Electromagnetic shielding of sensors; Misalignment of sensors. (Marked "* Not discussed here": Noise pickup from magnet coil power supplies; Effects of field asymmetries on local measurements — intrinsic field errors, eddy currents, applied magnetic perturbations.)

**Shielding by armor tiles (p.35, "High Frequency Signals Are Shielded if Sensor Is Enclosed by a Conducting Path"):** "A break is required in any possible conducting path." "'Mushroom' tiles (outer wall): Tiles must not contact each other above a magnetic probe" (a Gap is shown). "'Arch' tiles (top, bottom, inner wall): One foot must be insulated from the wall; Fastening hardware must be insulated from the tile." Labeled "Highly schematic illustrations!"

**Bandwidth testing (pp.36-37):** "Bandwidth is Tested with a Large Coil in the Vessel" at "Z ~ +1 m, Z ~ 0, Z ~ −1 m." Frequency scan (p.37) compares two HFS Bp probes:
- "MPI1A322: f_3db = 42.9 kHz (good) — 40–50 kHz is typical."
- "MPI1A049: f_3db = 4.9 kHz (bad) — Typical for shielding by graphite tiles — Need to add or adjust insulation."

**Sensor misalignment / Bt pickup (pp.38-39):** For a Bp probe misaligned by small angle γ ≪ 1: "B_MEAS = Bp cosγ + Bt sinγ ≈ (1 − γ²/2)Bp + γ·Bt." "Small error: 2nd order in γ"; "Larger error: 1st order in γ and larger multiplier [Bt]." Two compensation approaches: **Analog** — "combine a Bt probe signal (using adjustable attenuation) with the Bp probe signal at the integrator input"; **Digital** — "subtract a fraction of the measured Bt from each probe signal in post-processing."

**Bt compensation results (p.39, "RMS Bt pickup is"):**
- "1.79 % — No comp."
- "0.28 % — Analog comp."
- "0.12 % — Digital comp. (excluding 5 probes in need of updates)."
Plots: "Bt pickup: Mag Probes (Tesla/Tesla)" vs "Probe Number" (0–80), y-range ±0.06, comparing "No Compensation" vs "Analog Compensation," with a second panel "Bt pickup after compensation."

**Summary (p.40):** Magnetic data essential to tokamak operation and to interpreting other diagnostics; inductive magnetics are simple/robust for flux, field, current; the unique requirement is **integration of the raw signal** ("Accurate integration over long pulses is a challenge"); accuracy/reliability come from sensor+instrument characterization and experimental validation.

---

## Visualizations to reproduce

1. **Sensor-types torus diagram (p.6, rendered).** Black line drawing of a torus with five labeled inductive sensors (Diamagnetic Loop / poloidal-plane loop, Rogowski Coil / helical poloidal winding, Saddle Loop / rectangular surface patch, Flux Loop / major-circumference loop, Magnetic Field Probe / small solenoid). Good template for a "sensor zoo" panel.

2. **Multi-purpose montage (p.4).** (a) Rotating MHD modes: f(kHz) 0–30 vs Time 2000–3500 msec, shot 174455 t=2500 / shot 174446, with EFIT scalar readout box: betaN 1.884, ln/li 0.933, q95 3.307, BT(0) −1.998 T, Ipfit 1.520 MA, "In 1.389". (b) Stationary MHD / 3D fields: Phi(deg.) 0–360 vs Time 3460–3580 ms, shot 174446. (c) Axisymmetric equilibrium / shape control (EFIT cross-section).

3. **EFIT input cross-section (p.16).** Z(m) −3…+2 vs R(m) −3…+3 (note negative R shown — full poloidal cross-section both sides), with "Mag Probes" and "Flux Loops" markers, annotated toroidal ranges Φ = 140–180 and Φ = 310–330.

4. **3-D diagnostic wall map (p.18).** "Distance along vessel wall (m)" (−2 to 5/6) vs φ (deg.) 0–360; markers distinguish "Bp sensors" and "Br sensors"; regions labeled INBOARD/High Field Side, TOP, OUTBOARD/Low Field Side. 66 Bp probes, 64 Br loops.

5. **Locked tearing mode 2-D map (p.19).** Poloidal Angle θ (deg.) −90…270 vs Toroidal Angle φ (deg.) 0–360; color = δBp (G), colorbar −40…+40 G; shot 164672 t=3140 ms; wall regions BOT/INBOARD/TOP/OUTBOARD labeled. Companion fit panel of helical harmonics m=2/n=1.

6. **2-point correlation spectrogram (p.21).** Top trace: dB/dt (T/s) −400…+800 for two probes MPI66M307D & MPI66M340D, shot 174446. Main panel: spectrogram f (kHz) 0–15 vs Time 3300–3550 msec; color = toroidal mode number (color code, mode numbers −5 to 5, scale shown 6/4/2/0/−2/−4/−6); secondary colorbar "Cross-Power (T^2/s^2/kHz)" log scale 1.00e+00…1.00e+03; an "rms dB/dt (T/s)" scale 0–40 also shown. Params: delta-t 4.00 ms, delta-f 0.50 kHz, smoothing 3 pts. Result m,n = 2,1.

7. **Coherence/phase mode-number plots (p.22).** Two columns ("322 POLOIDAL ARRAY", "LFS TOROIDAL ARRAY"). Rows: Coherence 0.0–1.0; Phase (deg.) 0–360 vs Theta or Phi (deg.) 0–270; Cross-power (T^2/s^2/kHz) 0–400. Shot 174446, 3488–3492 ms, 2.00 kHz; n=1, m=2.

8. **Daily calibration trace (p.29).** Square-wave input → triangle-wave integrated output (no numeric axes printed).

9. **Uncertainty bar charts (p.32).** Four stacked sub-panels (F-coil Flux Loops, Vessel Flux Loops, 322 Magnetic Probes, F-coil Rogowskis), y = <δS> contribution in %, 0–2 range; x = error-source categories (Bt, tilt, port, leads, noise, C-coil, int cal, bit res, int. drift, loop cal, position, LT int cal, nonlinear, LT loop cal).

10. **Validation scatter/bar (p.33).** Two pairs of panels: left = measured vs coil index (coils labeled 6 7 9 8 5 4 3 2 1 | 1 2 3 4 5 8 9 7 6, A and B sides), right = measured-vs-calculated scatter near unity slope. PSF3A: axes ±0.10 (Ψ, V-s/rad), slope 0.996. MPI7NA322: axes ~ −0.08…0.02 (Bp, T), slope 0.988.

11. **Frequency-scan Bode plots (p.37).** mG/Amp (log, ~1–100) vs f(kHz) (log, 0.1–100) for MPI1A322 (f_3db 42.9 kHz) and MPI1A049 (f_3db 4.9 kHz).

12. **Bt pickup vs probe number (p.39).** Tesla/Tesla, ±0.06, vs Probe Number 0–80; two panels (before/after compensation), No Compensation vs Analog Compensation series.

---

## Concrete example values (only as printed)

- **Shots:** 174455 (t=2500); 174446 (used pp.4, 21, 22); 164672 (t=3140 ms).
- **EFIT scalars (p.4, shot 174446 readout):** betaN 1.884; li 0.933; q95 3.307; BT(0) −1.998 T; Ipfit 1.520 MA; "In 1.389."
- **Sensor counts (EFIT input, p.16):** 44 poloidal flux loops; 76 magnetic field probes; 18 PF coil current Rogowskis; plus OH/TF Rogowskis, BT probes, diamagnetic loop.
- **3-D set (p.18):** 66 Bp probes; 64 Br loops; n≤3 at 5 poloidal locations, n≤4 at LFS midplane; m≤~6 at 15 poloidal locations.
- **Locked-mode fit (p.19):** fit of 66 Bp probes → m=2/n=1; δBp colorbar ±40 G.
- **Probe/coil dimensions:** Bp probe coil ~14 cm (pp.7,10); Br/saddle loop 33 cm × 14 cm (p.8); Rogowski d~6.3 mm (p.9).
- **Integrator G/RC range:** 1 – 2000 s⁻¹ (p.26).
- **Calibration:** square wave 0.5 Hz (p.29); bench cal typical 1 kHz, ~0.3% uncertainty (p.30).
- **Position uncertainty:** 2 mm (1985) → 1 mm (2013 arm) → laser scanner (2019) (p.31).
- **Uncertainty budget (p.32):** PF-coil flux loops 2.27%; vessel flux loops 1.21%; magnetic probes 0.98%; PF-coil Rogowskis 0.94% (overall 1–2%).
- **Validation slopes (p.33):** 18 PF coils, ~1.5 s flattop; PSF3A slope 0.996 (agrees to 0.4%); MPI7NA322 slope 0.988 (agrees to 1.2%).
- **Bandwidth (p.37):** MPI1A322 f_3db = 42.9 kHz (typical 40–50 kHz); MPI1A049 f_3db = 4.9 kHz (graphite-tile shielded).
- **Bt pickup (p.39):** 1.79% none / 0.28% analog / 0.12% digital (excl. 5 probes).
- **Mode-analysis params (p.21):** delta-t 4.00 ms; delta-f 0.50 kHz; 3-pt smoothing; mode numbers −5 to 5; window/freq on p.22 = 3488–3492 ms, 2.00 kHz.
- **3-D amplitudes:** δBp ≤ few % of axisymmetric Bp (p.17); ITER long-pulse integrator "good for 1-hour pulses" (W7-X, p.25).

---

## Notable quotes (verbatim, with page #s)

- p.6: "Inductive magnetic sensors are based on Faraday's Law: V = − dφ/dt … Physical interpretation of the flux φ depends on the configuration of the loop."
- p.9: "Central return conductor avoids linking other flux through the loop opening (toroidal flux, for example)."
- p.11: "ψ is a key quantity for MHD equilibrium! … Note that ∇ψ = R Bp."
- p.14: "the surface distribution of ψ and B at the plasma boundary does not uniquely determine the internal distribution … The information about internal plasma structure that is available in external magnetic data alone is fundamentally limited."
- p.15: "Equilibrium reconstructions solve for ψ(R,z) by fitting to external magnetic data, with parameterized forms of p′(ψ) and F F′(ψ)."
- p.17: "Resolution of toroidal mode numbers n = 0, 1, ... N requires measurements at a minimum of 2N+1 toroidal locations."
- p.19: "Data fit to helical harmonics: δB ~ Σ_{n,m} B exp(in φ − im θ)."
- p.20: "dBp/dt = ωBp can be large, even when δBp is small … A single toroidal and poloidal array can resolve the external spatial structure — Mode rotates past each probe."
- p.23: "requires integration so that V_OUT = ∫ V_S dt ∝ φ."
- p.25: "Chief source of integration error is output drift due to DC offset at the input … Note that numerical integration would have the same problem!"
- p.25: "ITER plans analog integrators with input chopped and converted to AC … Developed for W7-X, said to be good for 1-hour pulses."
- p.40: "A unique feature of magnetic diagnostic is the requirement for integration of the raw signal to enable its interpretation — Accurate integration over long pulses is a challenge."

---

## Digest (4-6 sentences)

This is Ted Strait's pedagogical UC-Irvine seminar and the best single source in the collection for inductive magnetic sensor fundamentals: it derives each sensor type from Faraday's law (Bp/Br magnetic probes with φ=NAB; Rogowski for current with φ=μ₀nAI; toroidal/diamagnetic flux loop; poloidal flux loop with φ=2πψ, ∇ψ=R·Bp; saddle loops), with a clean labeled torus diagram (p.6) and DIII-D installation examples. It gives concrete EFIT sensor inventory (44 poloidal flux loops, 76 field probes, 18 PF-coil Rogowskis, plus OH/TF Rogowskis, BT probes, diamagnetic loop) and the Grad-Shafranov reconstruction math (Δ\*ψ = −μ₀R²p′ − FF′), while making the key conceptual point that external magnetics alone cannot uniquely determine internal structure. The 3-D/MHD section covers the helical-harmonic fit (δB ~ Σ Bₙₘ exp(inφ−imθ)), the 2N+1 toroidal-location rule, and the **2-point cross-correlation spectrogram technique that underlies MODESPEC** (n = ΔΦ/Δφ; result m,n=2,1 on shot 174446) — though the names SLCONTOUR and MODESPEC never appear literally. A large, unusually detailed instrumentation block explains why integration (passive RC vs active op-amp, Track-and-Hold for drift) is the defining challenge of magnetic diagnostics, and a full characterization block gives real calibration/uncertainty/validation/bandwidth numbers (~0.3% bench cal, 1–2% budgets, f_3db ~43 kHz good vs 4.9 kHz tile-shielded, Bt-pickup compensation 1.79%→0.12%). For the GUI-replacement project this document is the authoritative reference for sensor physics, EFIT inputs, and the mode-spectrum/spectrogram analysis chain.

**Output file:** `docs/research-summaries/13_DiagnosticsSeminar_UCIrvine.md`
