# GUI ⇄ Analysis Contract — DRAFT v0.1

**Status:** proposal for review. Owned by Interfacers (Pharr). Reviewers:
**Suh** (Data Streamers / geometry), **Lunia** (Slow Rollers / QS fit),
**Burgess** (Rapid Rotators / spectrogram). Nothing here is final until each
producing team signs off on the shape they fill — this is a starting point, not a
decree.

---

## Principles (agreed on the Interfacers side)

1. **They send numbers + meaning; we own appearance + interaction.** The analysis
   teams hand the GUI **plot-ready data** (arrays + units). The GUI (JavaScript /
   Plotly) owns everything visual and interactive: colormaps, value ranges, axis
   styling, the shared time cursor, hover, click-to-refit, array selection.
2. **Plot-ready shapes, defined by us.** Pre-rasterized grids and point lists in
   the shapes below (this is the "Option 1" decision — they rasterize the field
   onto a grid; the GUI does not re-evaluate the fit).
3. **Coarse first, then refine.** A result is streamed as successive **frames** of
   the *same shape* with progressively finer numbers (coarse grid → fine grid, or
   few modes → many). The GUI swaps each frame in place (`Plotly.react`), so the
   user sees something instantly and watches it sharpen.
4. **Every frame carries `progress` (0→1) and `final`** so we can drive a progress
   bar and stop refreshing when done.
5. **Not in this contract:** colormaps, color ranges, axis label styling, plot
   types, or any Plotly objects. If you find yourself choosing a color, it belongs
   on our side — tell us the number and what it means instead.

---

## Transport

Two ways to read every result. The streaming one is the real path; the one-shot
is for tests, notebooks, and the static mock.

| | Endpoint | Returns |
|---|---|---|
| discovery | `GET /api/machines` | `MachineInfo[]` (below) |
| one-shot | `GET /api/{machine}/{result}?<params>` | a single **final** frame (blocking) |
| streaming | `GET /api/{machine}/{result}/stream?<params>` | `text/event-stream` of frames, coarse→fine, last one `final:true` |

`{machine}` = a shot number or a synthetic id. `{result}` ∈ `geometry`,
`qs_fit`, `spectrogram`. List-valued params are comma-separated (`ns=1,2`).

### Frame envelope (shared by every result)

```jsonc
{
  "type": "qs_fit",        // which result shape `data` holds
  "progress": 0.4,          // 0..1, monotonic
  "final": false,           // true on the last frame
  "meta": { "shot": 164672, "t_ms": 3140 },   // data-level context (NOT styling)
  "data": { /* one of the shapes below */ }
}
```

`geometry` is instant, so it returns a single `final:true` frame and need not
stream. `qs_fit` and `spectrogram` stream.

---

## `MachineInfo` (discovery)

```jsonc
{ "id": "164672", "label": "DIII-D 164672", "device": "DIII-D",
  "note": "m/n=2/1 locked mode", "mock": false }
```

---

## Result 1 — `geometry`  ·  owner: **Suh (Data Streamers)**

Sensor positions + the array families that exist for this shot. Feeds the Sensors
view (unrolled φ–θ map and the R–Z cross-section).

**Params:** none beyond `{machine}`.

**`data`:**
```jsonc
{
  "sensors": [
    { "name": "MPI66M307", "phi": 307.0, "theta": 0.0,
      "r": 2.41, "z": 0.00, "kind": "Bp", "family": "MPI66M" }
  ],
  "arrays": [
    { "family": "MPI66M", "label": "LFS toroidal Mirnov", "kind": "Bp", "count": 14 }
  ]
}
```
**Units:** `phi`,`theta` degrees; `r`,`z` meters. `kind` ∈ `Bp|Br|coil|…`.
`family` is the selectable array group.

**Open questions for Suh:** per-shot or static per device? does this include
calibration/validity flags (dead probes)? are `r,z` always available (needed for
the R–Z view)?

---

## Result 2 — `qs_fit`  ·  owner: **Lunia (Slow Rollers)**

A quasi-stationary spatial fit at one time. One fit produces all the QS-view
panels (contour, mode amp/phase, quality), so it's one streamed result.

**Params:** `t_ms` (time slice), `ns` (e.g. `1,2`), `ms` (e.g. `0,1,2`),
`channels` (families or names), `baseline` (algorithm + window).

**`data`:**
```jsonc
{
  "contour": { "phi": [/*deg*/], "theta": [/*deg*/], "z": [[/*…*/]], "units": "G" },
  "sensors": [ { "phi": 307.0, "theta": 0.0 } ],          // overlay positions
  "modes": [
    { "n": 2, "m": 1, "amp": 16.9, "phase_deg": 324.4,    // at this slice
      "t_ms": [/*…*/], "amp_t": [/*…*/], "phase_t": [/*…*/] }  // optional vs-time
  ],
  "quality": { "K": 6.7, "chi2": 1.3, "n_channels": 58, "m_max": 5 }
}
```
**Refinement:** coarse → fine `contour` grid (and/or growing mode set) across
frames; `progress` reflects fit completeness.

**Open questions for Lunia:** is the amp/phase-**vs-time** (`*_t`) in the MVP, or
just the single slice? what does `progress` track — grid density or mode count?
what are the baseline param names (mirror SLCONTOUR `btype`/`base`)?

---

## Result 3 — `spectrogram`  ·  owner: **Burgess (Rapid Rotators)**

The rotating-mode view: spectrogram + toroidal-n coloring + a mode-number phase
fit.

**Params:** `array` (probe set), `fmin`,`fmax` (kHz), `tmin`,`tmax` (ms),
`window` (FFT length), `t0` (slice for the phase fit), `slice_duration` (s, FFT
window → freq resolution), `smoothing`/`coherence_smooth` (coherence-estimation
window, bins).

**Denoise params** (spectrogram / 2-point n-map / n-spectrum — all share `_prep_spec`,
so one gate thresholds every derived view on the same (t,f) grid; applied server-side
via `core.spectral.denoise_spectrogram`):
`denoise` (1/0 master flag), `coherence_min` (drop cells with γ² below this, 0 = off),
`power_floor_k` (drop cells below k × the per-frequency floor; 0/absent = skip),
`floor_percentile` (percentile over time defining that floor; 50 = median). The GUI's
Power Gate slider maps to a percentile floor (`power_floor_k=1`, `floor_percentile=p`).
Gated cells are returned as `null` in `power` so the heatmap renders them transparent.

**Pre-smoothing params** (optional 2-D Gaussian applied *before* the gates, via
`core.spectral.smooth_spectrogram` / `smooth_mode_spectrogram`, so contiguous coherent
structure survives aggressive gating; feeds both the gate decision and the display):
`smooth` (1/0 master flag), `smooth_t_cells` (σ along time, in grid cells), `smooth_f_cells`
(σ along frequency, in grid cells). Off by default; `smooth=0` (or σ=0) is an exact no-op.
σ is expressed directly in STFT grid cells (one cell = one (t, f) bin), so the blur spans the
same number of neighbours at any resolution and can't collapse to a sub-bin no-op; the GUI
shows the physical (ms/kHz) equivalent for the live grid.

**`data`:**
```jsonc
{
  "spectrogram": { "t_ms": [/*…*/], "f_kHz": [/*…*/], "power": [[/*…*/]] },
  "n_map":       { "t_ms": [/*…*/], "f_kHz": [/*…*/], "n": [[/*int −6..6*/]] },  // optional, same grid
  "phase_fit":   { "phi_deg": [/*…*/], "phase_deg": [/*…*/],
                   "fit": { "phi_deg": [0, 360], "phase_deg": [0, 360] },
                   "n": 1, "t_ms": 2500, "f_kHz": 5.0 },
  "coherence":   { "f_kHz": [/*…*/], "coh": [/*0..1*/] }   // optional
}
```
**Refinement:** coarse → fine `spectrogram` grid across frames; `n_map` fills in.

**Open questions for Burgess:** is `power` linear or log10 (we'll scale either —
just tell us which)? is `n_map` on the same grid as `spectrogram`? how is the
`phase_fit` slice `(t0,f)` chosen — fixed param, or follows the cursor? coherence
in the MVP?

---

## Notes

- **Source of truth = this file.** The GUI's TypeScript types and any Python
  models mirror it; if they disagree, this wins until we amend it here.
- **Decoupling:** the GUI already runs against a static mock of these shapes, so
  we build in parallel; each team swaps the mock for the real producer behind the
  same endpoint with no GUI change.
- **What's still open across the board:** the exact `progress` semantics per
  analysis, and whether `qs_fit`/`spectrogram` bundle their sub-panels (as drafted)
  or split into separate results. Decide with each owner.
