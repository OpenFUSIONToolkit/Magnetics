# Phase 1 — Wire the coherence gate + move the power floor server-side

**Lane:** Rapid Rotators (rotating-mode / MODESPEC spectrograms)
**Status:** implemented (branch `rotating-live-wiring`)
**Prereqs:** none — everything below builds on code that already ships and is tested.

## Implementation notes (what actually landed)

- Service: `_prep_spec` now threads `coherence_min` / `power_floor_k` / `floor_percentile`
  through to `denoise_spectrogram`; `_spectrogram` emits gated cells as JSON `null` (not
  `log10→−30`) so they render transparent.
- GUI: added a "Coherence Gate (γ²)" slider; folded `denoise` + both gates into the shared
  `specParams`; removed the client-side power blanking on the live path (server does it now).
- **Core bug found + fixed along the way:** `compute_spectrogram`'s frequency-smoothed
  coherence was **not** bounded to [0,1] (observed range ≈ −1400 … +2.6e5): a single-
  realization estimate overshoots Cauchy–Schwarz and near-zero-power bins blow up 0/0. The
  `_coherence` node's docstring claimed "[0,1]" but never enforced it, so the existing
  coherence view was already serving garbage. Fixed at the source: guard the denominator and
  clip to [0,1]. This was a prerequisite for a meaningful γ² gate slider.
- `denoise_spectrogram` coherence gate is now NaN-safe (NaN γ² → 0), so a disabled gate
  (`coherence_min ≤ 0`) is a true no-op.
- Tests: +1 core no-op test, +2 node tests (gate introduces null cells / gate-off matches
  default). Full suite 215 passed / 1 skipped; ruff format clean; `ty` adds no new src
  diagnostics; frontend `tsc -b` clean.
- Not verified in-browser: another session held port 5173 and the served data dir has no
  fetched shot, so the live visual wasn't brought up; backend gating is covered by the node
  tests instead.

### Follow-up: n-map gating + context-aware controls

The coherence gate (2-point γ²) only touches the **power** spectrogram — the array n-map
(`_mode_number`) is a separate path gated by its own per-cell mode-coherence (`n_gate`, the
array-fit resultant quality ∈ [0,1]) and amplitude percentile (`n_amp_pct`). Rather than
conflate the two different "coherences" under one slider, the n-map got its **own knob**, and
the coherence-type sliders are now **context-aware** (they only show for the plot in view):
- Power view: **Coherence Gate (γ²)** (+ Power Gate).
- n-map: **Mode Coherence** (`n_gate`, default 0.65) (+ Power Gate as `n_amp_pct`).

`_mode_number` already read `n_gate`, so this was GUI-only (new `nGate` state → `mode_number`
param; sliders wrapped in `displayMode === 'power' | 'n'`). The Power Gate stays visible in
both modes since it's meaningful to each; frontend `tsc` + 24 vitest + 215 pytest all green.

### Follow-up: mode-coherence metric → harmonic energy fraction

`array_mode_spectrogram.quality` was the **resultant length** `|R_{n*}| / Σ_p|Z_p|` (noise
floor ~1/√P ≈ 0.38). Switched it to the **energy fraction** `|R_{n*}|² / Σ_n|R_n|²` ∈ [1/M, 1]
(M = 2·n_max+1 candidates) — a true spectral-concentration ratio: 1 = pure single-n, 1/M =
white across harmonics. More noise/signal contrast (synthetic: clean ≈ 0.99, pure-noise
median ≈ 0.26 vs the old ~0.4–0.5). Because real cells rarely put >50% of toroidal power in
one harmonic, the **default `n_gate` was recalibrated 0.65 → 0.3** (the old default blanked
the whole map under the new metric); useful slider range is now ~0.15–0.4. Verified across 3
real shots. Docstrings, the GUI label/tooltip, and the noise-floor test comment updated to
match. Also renamed **Power Gate → Power Floor** and grouped the denoise controls under a
captioned "Denoise" header with the `γ² averaging` (was "Coherence Smoothing") knob nested
under the coherence gate, so the panel reads as *two gates + one estimator*, not three
sliders.

## Goal

Give the user a *physical* noise filter on the rotating spectrogram by exposing the
coherence gate that already exists in the core (`denoise_spectrogram`), and by moving the
existing client-side power percentile gate into the server so the spectrogram, n-map, and
n-spectrum all threshold on **one consistent, per-frequency floor** — and so we transport
less data.

This is deliberately the low-risk first step: it wires and unifies filters we already own
rather than adding new math. It also satisfies the project rule that every GUI control must
change real backend output (it replaces a cosmetic client gate with a real one).

## Why this is the right starting point

- `denoise_spectrogram(coherence_min, power_floor_k, floor_percentile)` is already
  implemented and unit-tested in `src/magnetics/core/spectral.py` (~line 413).
- It is already half-wired in the service: `_prep_spec` in `src/magnetics/service/nodes.py`
  (~line 247) applies it **iff** the request carries a `denoise` flag + `coherence_min`.
- But `RotatingTab` never sends `denoise` / `coherence_min`. Today the tab only fetches a
  real `coherence` node (for the coherence trace) and applies a **client-side** power
  percentile gate (`powerGate` / `gateFrac`) over the returned cells.

So the coherence filter is built and reachable from the API — it just has no knob, and the
power gate lives on the wrong side of the wire.

## Current state (facts to build on)

Backend — `src/magnetics/core/spectral.py`:
- `denoise_spectrogram(result, *, coherence_min=0.5, power_floor_k=3.0, floor_percentile=50.0)`
  zeroes cells below the coherence gate and/or below `k ×` the per-frequency power floor,
  then recomputes `rms_by_mode` from what survives.

Service — `src/magnetics/service/nodes.py`:
- `_prep_spec(shot, params)` reads `slice_duration`, `coherence_smooth`/`smoothing`,
  `max_columns`, then:
  ```python
  if _flag(params, "denoise"):
      res = spectral.denoise_spectrogram(res, coherence_min=_f(params, "coherence_min", 0.5))
  ```
  — note `power_floor_k` / `floor_percentile` are **not** threaded through yet.
- `_spectrogram`, `_mode_number_2pt`, `_mode_number`, and the n-spectrum node all read from
  `_prep_spec`, so gating there propagates to every derived view for free.

GUI — `gui/web/src/components/tabs/RotatingTab.tsx`:
- State: `fmin`, `fmax`, `smoothing`, `specSliceMs`, and `gatePos → powerGate (%) → gateFrac`.
- `specParams = { slice_duration, max_columns: 1000, fmin, fmax, smoothing }` — **no denoise**.
- `powerGate` is applied two ways today: client-side filtering of the power spectrogram
  cells, and server-side as `n_amp_pct` on the `mode_number` node only.
- There is already a real `coherence` node fetched with `specParams`.

## Changes

### 1. Core — small robustness touch (optional, low risk)
`denoise_spectrogram` already does what we need. Only change if we want an explicit
"coherence gate only" vs "power floor only" toggle: allow `power_floor_k=None` (already
supported) and confirm `coherence_min=0.0` is a clean no-op pass-through. Add/confirm a unit
test for the `coherence_min=0` and `power_floor_k=None` corners.

### 2. Service — thread the full denoise params through `_prep_spec`
In `src/magnetics/service/nodes.py`, extend the `denoise` branch to honor all three levers
so the GUI can drive them:
```python
if _flag(params, "denoise"):
    res = spectral.denoise_spectrogram(
        res,
        coherence_min=_f(params, "coherence_min", 0.5),
        power_floor_k=_f(params, "power_floor_k", None),   # None = skip power floor
        floor_percentile=_f(params, "floor_percentile", 50.0),
    )
```
This keeps the gate centralized in `_prep_spec`, so the spectrogram, both n-maps, and the
n-spectrum stay cell-for-cell consistent (they already share this function). No contract
`kind` changes — these are query params, matching the existing seam convention.

### 3. Contract — document the new query params
Update `docs/CONTRACT.md` (and any param list in `core/contracts.py` ⇄
`gui/web/src/lib/contract.ts` if params are enumerated there) to record `denoise`,
`coherence_min`, `power_floor_k`, `floor_percentile` on the spectrogram-family nodes. Keep
the two contract files in sync per CLAUDE.md.

### 4. GUI — add the coherence gate control and swap the power gate to server-side
In `RotatingTab.tsx`:
- Add state `const [coherenceMin, setCoherenceMin] = useState<number>(0)` (0 = off, so the
  default view is unchanged).
- Add a "Coherence gate (γ²)" slider (0–1, ~0.02 step) next to the existing Power Gate.
- Fold denoise into the shared `specParams` so every derived node gets it in one place:
  ```ts
  const denoiseOn = coherenceMin > 0 || powerGate > 0;
  const specParams = {
    slice_duration: specSliceMs / 1000, max_columns: 1000, fmin, fmax, smoothing,
    denoise: denoiseOn,
    coherence_min: coherenceMin,
    // map the existing Power Gate percentile to the core's per-frequency floor lever:
    power_floor_k: powerGate > 0 ? gateFrac_to_k(powerGate) : null,
    floor_percentile: 50,
  };
  ```
- Remove the client-side power-cell filtering for the **live** path (keep it only for the
  synthetic fallback, which has no backend). The n-map keeps using `n_amp_pct` as today, or
  we align it to the same floor — decide during implementation; either way no fabricated
  gating remains on the live path.
- Update the Power Gate tooltip to say it now applies a real per-frequency power floor
  server-side (not a client cosmetic crop).

**Mapping note:** the core power gate is `power_floor_k` (drop cells below `k ×` the
per-frequency median), whereas the GUI slider is a percentile. Two clean options — pick one
in implementation:
  - (a) keep the slider as a percentile and thread `floor_percentile` + a fixed `k=1.0`
    (drop cells below the chosen percentile of each frequency's power over time); or
  - (b) keep `floor_percentile=50` (median) and map the slider to `k` via a small helper.
Option (a) is the more faithful "percentile floor" and needs no new mapping helper — likely
preferred.

## Testing

- **Core:** extend `tests/` coverage for `denoise_spectrogram` — assert coherence gating
  zeroes sub-threshold cells, the power floor drops sub-floor cells, `rms_by_mode` is
  recomputed from survivors, and `coherence_min=0` / `power_floor_k=None` are exact no-ops.
- **Service:** FastAPI TestClient against the synthetic shot — request `spectrogram` with
  and without `denoise`, assert the gated response has strictly fewer/zeroed cells and the
  same (t, f) grid; assert the n-map/n-spectrum reflect the same gate.
- **Frontend:** unit-test the percentile→param mapping helper; confirm `denoise` is omitted
  (or false) when both gates are at 0 so the default view is byte-for-byte unchanged.
- **Manual:** load a shot with a clear rotating mode, raise the coherence gate, confirm the
  broadband floor drops out while the coherent mode ridge survives across spectrogram + n-map.

## Acceptance criteria

- A "Coherence gate (γ²)" slider drives real `denoise_spectrogram` coherence gating on the
  live spectrogram, n-map, and n-spectrum, consistently on one (t, f) grid.
- The Power Gate applies a real per-frequency power floor **server-side**; the live path no
  longer filters cells in the browser.
- Gates at 0 reproduce today's default view exactly.
- `docs/CONTRACT.md` + `contract.ts`/`contracts.py` document the new params and stay in sync.
- Python formatted (`uv run ruff format .`), `ty` typecheck green, Python + frontend suites pass.

## Out of scope (later phases)

- SVD / biorthogonal spatiotemporal denoise on the toroidal array (**Phase 2** — the
  headline feature).
- Bandpass / line-notch pre-filter ahead of the STFT (**Phase 3**).
- Wavelet / HHT / VMD decomposition (**Phase 4**, stretch).

## Estimate

~½ day: mostly plumbing + tests on already-shipping, already-tested core code.
