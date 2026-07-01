# Optional 2-D Gaussian pre-smoothing for the rotating spectrogram

**Lane:** Rapid Rotators (rotating-mode / MODESPEC spectrograms)
**Status:** implemented (branch `rotating-live-wiring`)
**Depends on:** the Phase-1 denoise wiring (coherence gate + power floor + n-map gate),
`docs/plans/phase1-coherence-gate.md`.

## Addendum (cell-based sliders — supersedes the ms/kHz units below)

The pre-smooth widths were switched from **physical units (ms/kHz)** to **grid cells** (STFT
bins): the sliders now read `σ time`/`σ freq` in cells (defaults **3 / 1.5 cells**, ranges
0–8 / 0–5), sent as `smooth_t_cells` / `smooth_f_cells`. Reason: at the default `slice_duration`
(2 ms → 0.5 kHz freq bin) and a time-decimated grid, the old physical defaults (3 ms / 0.3 kHz)
mapped to **sub-bin σ** (~0.6–0.75 cells) that a Gaussian barely changes — so moving the
sliders had no visible effect. Cells are resolution-relative (one cell = one bin) and can't
collapse to a sub-bin no-op. Each slider shows the physical equivalent for the live grid
(e.g. `3.0 cells ≈ 6.0 ms`), computed client-side from the returned spectrogram axes via
`rotatingTransforms.medianStep`. `_smooth_sigma_bins` now reads the cell params directly (no
dt/df conversion). Everything below that says "ms"/"kHz" or `smooth_t_ms`/`smooth_f_khz` refers
to the original design and is superseded by this note.

## Implementation notes (what landed)

- Core (`spectral.py`): `smooth_spectrogram` (blurs `power` + `coherence`, recomputes
  `rms_by_mode`, leaves `mode_number`) and `smooth_mode_spectrogram` (blurs the n-map
  `quality` + `amplitude`). Both anisotropic `gaussian_filter(sigma=(σ_t, σ_f), mode="reflect")`,
  σ=0 ⇒ exact no-op via `dataclasses.replace`, and both return copies (cache-safe).
- Service (`nodes.py`): `_smooth_sigma_bins` maps `smooth_t_ms`/`smooth_f_khz` → grid bins;
  applied in `_prep_spec` (full band, *before* `denoise_spectrogram`) and in `_mode_number`
  (native grid, *before* the display-time decimation).
- GUI: an off-by-default "Pre-smooth (2-D Gaussian)" checkbox at the top of the Denoise group
  with `σ time (ms)` / `σ freq (kHz)` sliders (defaults 3 ms / 0.3 kHz when enabled); threaded
  into the shared `specParams` + the `mode_number` params.
- Contract + docs updated. Tests: 7 new (5 core smooth_spectrogram incl. the ridge-gap
  reinforcement, 1 core smooth_mode_spectrogram, 1 node smoke/no-op). Full suite 222 passed /
  1 skipped; frontend `tsc` + 24 vitest green; `ty` adds no new src diagnostics; ruff clean.
- Verified on real shots: grid preserved, cell variance drops under smoothing, `smooth=0` is
  byte-identical to the default, and the n-map responds. Not brought up in-browser (other
  session holds port 5173; served data dir has no shot) — covered by the node tests.

### Follow-up: log-space power smoothing (visibility fix), continued on `feature/spectrogram-elm-filter`

The committed version (commit `7ba1241`) shipped **cell-based σ** (`smooth_t_cells`/`smooth_f_cells`,
not the ms/kHz noted above) and smoothed **linear** power. That made the blur ~invisible: on the
log heatmap, linear-space smoothing halos the bright ridges and *raises* the visible log-variance
(measured 1.18 → 1.19) instead of lowering it. Switched `smooth_spectrogram` to smooth **log10
power** then map back (`10**gaussian_filter(log10 power)`); coherence stays linear. Now the
log-variance drops monotonically with σ (1.18 → 1.01 → 0.91 → 0.88 on a real shot) — a genuinely
visible blur that matches the display and the log-power gate. Trade-off vs linear: log/geometric
smoothing lifts ridge *dropouts* less strongly, but ridge preservation is carried mainly by the
(still linear) coherence-gate smoothing and by ridges being bright, so the cost is small. Tests
updated (`test_ridge_dropout_is_lifted_toward_ridge`, `test_smoothing_makes_log_display_smoother`);
full suite 240 passed / 2 skipped, frontend `tsc` + 26 vitest green.

## Motivation

At aggressive gate settings the gates start dropping **real coherent structures** (and, at
the other extreme, brief high-power chirps survive). Both symptoms are because the gates
threshold **per cell**, with no notion that a real mode occupies a *neighborhood* of the
(time, frequency) plane. A 2-D Gaussian blur of the field **before** gating fixes this: a
coherent ridge spans many contiguous cells, so smoothing reinforces it (fills gaps, holds it
above threshold), while isolated noise cells and thin transients get averaged down.

## Design decisions (from Q&A)

- **Acts on:** *both the displayed power and the gate fields.* Because the display shows
  `log10(power)` and the power floor gates on `power`, smoothing `power` once (before gate +
  display) covers both; likewise smoothing `coherence` before the coherence gate + coherence
  view. "What you see is what's gated."
- **Kernel:** *anisotropic* — independent `σ_time` and `σ_freq`. Mode ridges are narrow in
  frequency but extended in time; chirps are the opposite. Independent widths let you smooth
  along one axis without smearing the other.
- **Primary goal:** *preserve coherent ridges.* Drives the default when enabled toward
  **σ_time > σ_freq** (average *along* a ridge to fill gaps, with only light cross-frequency
  blur so nearby modes don't merge).
- **Optional / off by default:** `σ = 0` in both axes is an exact no-op, so the current view
  is unchanged until the user enables it.

## Where it fits in the pipeline

```
_spec_result (cached STFT)           ← UNCHANGED, must not be mutated (shared cache)
      │  SpectrogramResult{power, coherence, mode_number, rms_by_mode}
      ▼
_prep_spec:
   smooth_spectrogram(res, σ_t_bins, σ_f_bins)   ← NEW: returns a COPY, blurs power+coherence
      ▼
   denoise_spectrogram(res, coherence_min, power_floor_k, …)   ← existing gate, now sees smoothed fields
      ▼
   freq mask → nodes (_spectrogram / _coherence / _n_spectrum)

n-map path (separate grid):
_array_mode_spec (cached) → ArrayModeSpectrogram{mode_number, amplitude, quality}
      ▼
_mode_number:
   smooth_mode_spectrogram(ms, σ_t_bins, σ_f_bins)  ← NEW: blurs quality+amplitude, leaves mode_number
      ▼
   gate: show = (quality ≥ n_gate) & (amplitude ≥ floor)
```

Smoothing runs on the **full band** (before the display freq-crop) so the displayed region is
blurred with its true neighbors — no artificial edge at fmin/fmax.

## Core changes (`src/magnetics/core/spectral.py`) — pure, device-agnostic

Use `scipy.ndimage.gaussian_filter` (separable, fast; already import `uniform_filter1d` from
`scipy.ndimage`). σ is in **bins** at the core boundary (device-agnostic); the service maps
physical ms/kHz → bins per grid.

```python
def smooth_spectrogram(result, *, sigma_time_bins, sigma_freq_bins) -> SpectrogramResult:
    """2-D Gaussian blur over (time, frequency) of the continuous fields, so contiguous
    coherent structure survives gating. Blurs `power` (linear) and `coherence`; leaves the
    discrete `mode_number` untouched; recomputes `rms_by_mode` from the smoothed power.
    σ=0 in an axis is a no-op along that axis. Returns a COPY (never mutates the input —
    it comes from a shared lru_cache)."""
```

- Fields arrays are `(n_times, n_freqs)`; call `gaussian_filter(field, sigma=(σ_t, σ_f),
  mode="reflect")`. `reflect` avoids edge darkening.
- **Linear power** is smoothed (averaging energy fills a ridge's dim gaps by pulling toward
  the bright neighbors — better ridge continuity than a geometric/log mean). Note as a future
  option: smooth `log10(power)` instead for a more uniform blur across dynamic range.
- Coherence stays in [0,1] automatically (a convex average of in-range values); no re-clip.
- Recompute `rms_by_mode` from smoothed power (same loop as `denoise_spectrogram`), so the
  n-spectrum node reflects the smoothing even when gating is off.

```python
def smooth_mode_spectrogram(result, *, sigma_time_bins, sigma_freq_bins) -> ArrayModeSpectrogram:
    """Same 2-D blur for the array n-map: smooths `quality` and `amplitude` (the two gated
    continuous fields), leaves the discrete `mode_number` as-is. Returns a copy."""
```

The discrete `mode_number` is never blurred — the reported n stays the per-cell argmax; only
the *gating* fields (quality/amplitude) and the displayed power are smoothed.

## Service changes (`src/magnetics/service/nodes.py`)

- `_prep_spec`: after pulling the cached `res` and **before** `denoise_spectrogram`, if
  smoothing is requested, `res = spectral.smooth_spectrogram(res, σ_t_bins, σ_f_bins)`.
  Convert params from physical units using the result's own grid:
  `dt = median(diff(res.time))`, `df = diff(res.frequency)`;
  `σ_t_bins = (smooth_t_ms·1e-3)/dt`, `σ_f_bins = (smooth_f_khz·1e3)/df`.
- `_mode_number`: after reading `q`/`amp` (or on the native `ms` before display decimation),
  apply `smooth_mode_spectrogram` with bins from the n-map's own grid spacing. Prefer
  smoothing on the **native** ms grid before the `ti = linspace(...)` decimation so the
  physical σ_t is resolution-independent, then decimate.
- New query params, defaulting to no-op:
  `smooth` (1/0 master flag), `smooth_t_ms` (σ_time, ms), `smooth_f_khz` (σ_freq, kHz).
  Applied consistently to the spectrogram, coherence, n-spectrum, and n-map nodes so every
  view stays on one smoothed basis.
- **Cache safety:** both core functions return new objects; never mutate the lru-cached
  `_spec_result` / `_array_mode_spec` outputs. Smoothing is a cheap per-request post-op
  (separable Gaussian on ~1000×N), so it stays *outside* the STFT cache key (like denoise).

## Contract (`docs/CONTRACT.md` + `contract.ts`/`contracts.py`)

Document the three new spectrogram-family params (`smooth`, `smooth_t_ms`, `smooth_f_khz`)
alongside the Phase-1 denoise params; note they are a pre-gate preprocessing stage.

## GUI changes (`gui/web/src/components/tabs/RotatingTab.tsx`)

- New state: `smoothOn` (bool), `smoothTms` (σ_time, ms), `smoothFkhz` (σ_freq, kHz);
  default **off** (`0/0`).
- Place a **"Pre-smooth (2-D Gaussian)"** block at the **top of the Denoise group** (it runs
  before the gates), shown in both power and n modes since it feeds both. Two sliders:
  - `σ time (ms)` — the dominant knob for preserving ridges.
  - `σ freq (kHz)` — keep small to avoid merging nearby modes.
  A tooltip: *"Blurs the spectrogram before gating so contiguous coherent structure survives;
  time-heavy settings fill gaps along a mode ridge. Off = 0."*
- Thread `smooth`/`smooth_t_ms`/`smooth_f_khz` into the shared `specParams` (and the
  `mode_number` params) so all views smooth on one basis. Fold `smoothOn` into the existing
  `denoiseOn`-style flag pattern.
- Interaction note: the existing **γ² averaging** (`coherence_smooth`) 1-D freq-smooths the
  coherence *estimate*; this new 2-D blur smooths the *output* fields. They compose — keep
  both, but the tooltip should distinguish "estimate window" from "pre-gate blur."

## Units & defaults

- Sliders in **physical units** (ms, kHz), converted to bins per grid in the service, so the
  smoothing means the same thing regardless of the resolution knob.
- Default **off**. Suggested "on" starting point (tuned to preserve ridges):
  `σ_time ≈ 2–3 ms`, `σ_freq ≈ 0.2–0.3 kHz` (σ_time > σ_freq). Final defaults picked by eye on
  real shots during implementation.

## Testing

- **Core (`tests/test_spectral.py`):**
  - `sigma=0` (both axes) is an exact no-op (power/coherence unchanged).
  - shapes/kind preserved; coherence stays in [0,1]; `mode_number` unchanged.
  - a single injected hot cell spreads (peak drops, neighbors rise) — blur works.
  - **ridge reinforcement:** on a ridge with a punched-out gap cell, the gap's smoothed
    value rises toward the ridge (vs an isolated cell), so it survives a gate that the raw
    gap wouldn't — the core behavior we're buying.
  - `smooth_mode_spectrogram`: `sigma=0` no-op; quality in [0,1]; `mode_number` untouched.
- **Service (`tests/test_nodes.py`):** spectrogram/n-map with `smooth=1` vs off → same (t,f)
  grid, smoother field (e.g. reduced cell-to-cell variance), and `smooth=0` reproduces the
  default exactly.
- **Frontend:** unit-test the ms/kHz→param plumbing; sliders render; default off ⇒ params
  omitted/zero so the view is unchanged.

## Acceptance criteria

- An optional, off-by-default 2-D Gaussian with independent `σ_time`/`σ_freq` blurs the power
  + coherence (and n-map quality/amplitude) **before** gating, and the blur shows in both the
  displayed spectrogram and which cells survive the gates.
- At aggressive gate settings, contiguous coherent ridges are retained where they previously
  dropped out; the effect is tunable via σ_time.
- σ=0 reproduces today's view exactly; the STFT cache is never mutated.
- Contract files in sync; `ruff format` clean; `ty` adds no new src diagnostics; Python +
  frontend suites green.

## Out of scope (later)

- Log-power smoothing option; median / edge-preserving (bilateral) filters; structure-tensor
  or Radon-based chirp-aware smoothing; SVD/biorthogonal spatiotemporal denoise (separate
  Phase-2 plan).

## Estimate

~0.5–1 day: two small pure core functions + tests, per-request wiring in two node paths, and
a two-slider GUI block. No change to the STFT engine or the cache.
