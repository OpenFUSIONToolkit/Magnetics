# Plan: Wire RotatingTab to real nodes + expose the missing knobs

**Branch:** `rotating-live-nodes` (off `develop` @ 4161463). **Owner:** Rapid Rotators.

## Context

The seam now serves real data — `analysis/src/magnetics/service/nodes.py` builds eight
live nodes (`geometry`, `spectrogram`, `mode_number`, `coherence`, `n_spectrum`, `contour`,
`fit_quality`, `phase_fit`) from real shot HDF5 via `core/spectral` + `contract`. But
`gui/web/src/components/tabs/RotatingTab.tsx` still **fabricates** most of what it shows:
it fetches only `spectrogram` + `phase_fit` and synthesizes n, coherence, the n-spectrum,
the raw trace, and the wave-stripes. This plan replaces the fakery with the real nodes,
wires the knobs that have a backend, labels/hides the ones that don't, adds the two params
the core is missing (FFT overlap, mode range), and builds the empty SensorsTab.

The work splits into **core/contract**, **service**, **GUI**, and **mock fixtures**.

---

## 1. Core + contract — add the two missing params

### 1a. FFT overlap → STFT hop  (`core/spectral.py`)
Today `stft_layout()` hardcodes a 50%-overlap hop (`natural_hop = n_fft // 2`) and
`compute_spectrogram` only varies hop via `max_columns` decimation. The GUI has an FFT-overlap
slider (0–90%) with no backend.
- Add `overlap: float = 0.5` to `stft_layout(n_samples, sample_rate, slice_duration, overlap=0.5)`;
  compute `hop = max(1, round(n_fft * (1 - overlap)))` and the column count from it.
- Thread `overlap` through `compute_spectrogram(..., overlap=0.5)` — the decimation cap
  (`max_columns`) still applies on top (take `max(overlap_hop, decimation_hop)`).
- Plumb through `contract.stream_spectrogram`/`spectrogram_oneshot` and `_natural_columns`
  (which calls `stft_layout`) so coarse→fine geometry stays consistent.
- Tests: `tests/test_spectral.py` — `stft_layout` hop honors overlap; higher overlap ⇒ more
  columns; output still finite and mode-number still recovered.

### 1b. Variable mode resolution  (`core/spectral.py`, `contract.py`)
The 2-point estimator aliases: `mode_indices` spans only `±floor(180/|Δφ|)` (for the 33° pair,
≈ ±5; for small Δφ, ±1). `fit_toroidal_mode` already takes `n_range`. Plan:
- Surface `n_min`/`n_max` as request params (contract already passes `n_range` to
  `build_phase_fit`); expose it on the `mode_number`/`n_spectrum` service nodes too.
- Document the aliasing ceiling honestly: the 2-point pair **cannot** resolve beyond
  `±floor(180/|Δφ|)`; serving more modes requires the full toroidal array (a future
  array-fit node). Clamp the requested range to the achievable one and report it in `meta`.

> Note: this is the one item where "serve more modes" is physically bounded. The slider should
> expose the *achievable* range, not promise −6..6 from two probes.

---

## 2. Service — forward the new params  (`service/nodes.py`)

- `_spec_result` / `_prep_spec`: accept `overlap` (alias `fft_overlap`, %→fraction) and pass to
  `compute_spectrogram`; add to the lru_cache key.
- `_mode_number` / `_n_spectrum`: accept `n_min`/`n_max`, clamp to the Δφ ceiling, pass through.
- Add a **`raw_signal`** node (new): return a `line` node of one probe's dB/dt over a small
  window around `t0` (the GUI's "Raw Signal dB/dt" panel currently fabricates this). Pull the
  reference probe from `_pick_pair`; reuse `_stack`. This is the only genuinely missing node.

---

## 3. GUI — RotatingTab  (`gui/web/src/components/tabs/RotatingTab.tsx`)

### 3a. Replace fabricated n / power (lines 183–275, esp. 208–248)
- Keep fetching `spectrogram` for the power view. For the "Mode n" toggle, fetch the real
  `mode_number` node via `useNode(machine, "mode_number", { fmin, fmax, n_min, n_max, denoise, coherence_min })`
  instead of mapping log-power → fake n. Render whichever node matches `displayMode`.
- Drop `syntheticSpecNode` and the log-power→n heuristic entirely when `usingLiveBackend()`;
  keep a thin synthetic only behind the no-backend mock path (or remove if mocks exist — see §5).

### 3b. Replace fabricated sub-interval coherence / nMode (lines 291–331)
- Fetch `coherence` (heatmap) and `n_spectrum` (heatmap) nodes; slice the column nearest
  `cursorMs` for the sub-interval panel instead of `simulate coherence based on power peaks`.
- The cross-power trace already slices the real spectrogram — keep that.

### 3c. Replace synthetic fallbacks (lines 11–29, 333–370)
- **Raw dB/dt trace** (`generateDeterministicTimeTrace`) → consume the new `raw_signal` node.
- **Wave-stripes** (`arrayStripesData`) → consume the real `contour` node (raw δBp(φ,t));
  drop the m=3/m=2 synthetic poloidal stripes (no backend for poloidal yet — label as pending).

### 3d. Label / hide decorative knobs (sidebar, lines 828–850, 1000–1075)
No backend exists for these — mark each "(visual only)" or hide behind an "experimental" flag:
- `btype` (baseline) — **out of scope per spec** (belongs to the QS/SLCONTOUR path).
- PEST `λ₁`/`λ₂`, `btCompMode`, `shieldingCutoff` — purely cosmetic transforms today.

### 3e. Wire the real knobs
- `fmin`/`fmax`, `coherence_min` (gate), `smoothing` (→ `coherence_smooth`): already real params
  on the nodes — pass them through `useNode` params.
- `fftOverlap` slider → new `overlap` param (§1a). `fftWindow` → `slice_duration` mapping.
- Add a **mode-range slider** (`n_min`/`n_max`, §1b) bounded to the achievable Δφ range.

### 3f. Polish
- Data-source badge (lines 118–121): replace `hasStaticFiles ? "Mock Files (Static)" : …`
  with `usingLiveBackend() ? "Live Backend" : "Mock Files (Static)"`.

---

## 4. GUI — SensorsTab  (`gui/web/src/components/tabs/SensorsTab.tsx`)

Currently a placeholder. Build the φ–θ wall map from the real `geometry` node:
- `useNode(machine, "geometry")` → it's a `scatter2d` node; render via `<NodeView/>` for the
  unrolled φ–θ map (x=φ, y=θ, grouped/colored by sensor family).
- Add visual array selection (family checkboxes from the node's groups) feeding a selection
  store the other tabs can read. R–Z cross-section is stretch (geometry node lacks r,z today —
  confirm with the geometry owner before promising it). `SensorsTab.test.tsx` already exists;
  extend it.

---

## 5. Mock fixtures  (`gui/web/public/mock/<shot>/`)

The no-backend dev path reads static JSON. Today only `spectrogram`/`phase_fit`/`contour`/
`fit_quality`/`geometry` exist. For the new consumption to work without a live backend, add
mock `mode_number.json`, `coherence.json`, `n_spectrum.json`, `raw_signal.json` per shot
(generate from `spectrogram_oneshot`/the node builders against a fixture shot). If we decide
the rich views are live-backend-only, gate them on `usingLiveBackend()` and skip the mocks.

---

## Verification

- **Core/contract:** `cd analysis && uv run pytest -q` (extend `tests/test_spectral.py`,
  `tests/test_contract.py` for overlap + mode-range); `uvx ruff check .`.
- **Web:** `cd gui/web && npm run lint && npm run build && npx vitest run` (RotatingTab +
  SensorsTab).
- **End-to-end:** launch the mock service `uv run --extra service magnetics-service`, point the
  GUI at it (`VITE_API_BASE=http://127.0.0.1:8000 npm run dev`), and confirm RotatingTab shows
  the live badge, real n/coherence/n-spectrum, real raw trace + contour, and that the
  overlap/mode-range sliders re-run the backend.

---

## Decisions (resolved)

1. **Rich views gate on `usingLiveBackend()`** — no new mock fixtures (§5 skipped). Without a
   live backend, the new real-node views are hidden behind a "connect backend" note.
2. **Poloidal wave-stripes / poloidal phase fit: keep, clearly labeled "synthetic — pending
   backend."** Layout/intent stays visible.
3. **Mode range:** expose the *achievable* (Δφ-limited) range, communicated in the UI.
4. **SensorsTab:** φ–θ map + family-based array selection this pass; R–Z deferred (geometry node
   has no r,z yet).
5. **Execution:** implement core + contract + service + GUI + SensorsTab in one pass, verify
   end-to-end before committing.
