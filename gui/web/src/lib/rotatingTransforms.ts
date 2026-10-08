// Pure helpers for the Rotating-modes power gate — extracted so the percentile /
// slider math is unit-testable and doesn't trip the react-refresh rule (component
// files must export only components).

// p-th percentile of a numeric array (linear interpolation). Sorts its input IN
// PLACE — callers pass freshly-built throwaway arrays, so we skip the copy to keep
// slider scrubbing allocation-free.
export function percentile(values: number[], p: number): number {
  if (values.length === 0) return -Infinity;
  const s = values.sort((a, b) => a - b);
  if (p <= 0) return s[0];
  if (p >= 100) return s[s.length - 1];
  const idx = (p / 100) * (s.length - 1);
  const lo = Math.floor(idx);
  const hi = Math.ceil(idx);
  return s[lo] + (s[hi] - s[lo]) * (idx - lo);
}

// Power-gate slider mapping. The slider position is linear in [0, GATE_POS_MAX] but
// the percentile it selects follows a log curve in the "headroom" (100 − percentile):
// the top of the travel resolves finely (e.g. 97 → 99.5%) where the noise floor
// matters, instead of a coarse 1%-per-step linear scale.
export const GATE_POS_MAX = 1000;
const GATE_H_LO = 100; // headroom at pos 0   → 0th percentile (show everything)
const GATE_H_HI = 0.5; // headroom at pos max → 99.5th percentile (tightest crop)

export function gatePosToPct(pos: number): number {
  const t = Math.min(1, Math.max(0, pos / GATE_POS_MAX));
  const h = Math.exp(Math.log(GATE_H_LO) * (1 - t) + Math.log(GATE_H_HI) * t);
  return Math.round((100 - h) * 10) / 10; // 0.1%-resolution percentile
}

// Median spacing between successive samples of a monotone axis — the physical width of
// one grid cell (e.g. one STFT time or frequency bin). Used to render the σ-in-cells
// pre-smooth readout in the axis's own units. Returns NaN for a degenerate axis (<2
// points), which the caller renders as an em dash.
export function medianStep(axis: number[] | undefined): number {
  if (!axis || axis.length < 2) return NaN;
  const diffs: number[] = [];
  for (let i = 1; i < axis.length; i++) diffs.push(Math.abs(axis[i] - axis[i - 1]));
  diffs.sort((a, b) => a - b);
  const mid = Math.floor(diffs.length / 2);
  return diffs.length % 2 ? diffs[mid] : (diffs[mid - 1] + diffs[mid]) / 2;
}

// ── Spectral fetch params ────────────────────────────────────────────────────
// The Rotating tab's knobs → the /api/node query params of its `spectrogram` (and
// `coherence`) and `mode_number` fetches. One builder so the Compare view's
// "not yet run" fallback requests exactly what the Rotating tab starts with.
export const GATE_POS_DEFAULT = 227; // slider position that yields ≈70% (a sensible noise floor)

export interface RotSettings {
  specSliceMs: number;  // STFT slice duration (ms)
  fmin: number;         // band crop (kHz)
  fmax: number;
  smoothing: number;    // coherence-estimation window
  coherenceMin: number; // 2-point γ² gate (0 = off)
  powerGate: number;    // per-frequency power-floor percentile (0 = off)
  nGate: number;        // n-map mode-coherence gate
  smoothOn: boolean;    // 2-D Gaussian pre-smoothing
  smoothTcells: number;
  smoothFcells: number;
}

export const ROT_DEFAULTS: RotSettings = {
  specSliceMs: 2, fmin: 0, fmax: 50, smoothing: 5, coherenceMin: 0,
  powerGate: gatePosToPct(GATE_POS_DEFAULT), nGate: 0.3,
  smoothOn: false, smoothTcells: 3, smoothFcells: 1.5,
};

export function rotFetchParams(s: RotSettings): { spec: Record<string, number>; mode: Record<string, number> } {
  // Server-side denoise: the coherence gate and the per-frequency power floor both run in
  // the core (denoise_spectrogram) so the spectrogram, 2-point n-map, and n-spectrum all
  // threshold on ONE consistent (t, f) grid. 0 on both = no-op.
  const denoiseOn = s.coherenceMin > 0 || s.powerGate > 0;
  // 2-D Gaussian pre-smoothing, shared by every spectral node so all views smooth on one
  // basis. Effective only when the toggle is on and a σ is non-zero (else a server no-op).
  const smoothActive = s.smoothOn && (s.smoothTcells > 0 || s.smoothFcells > 0);
  const smoothParams = {
    smooth: smoothActive ? 1 : 0,
    smooth_t_cells: smoothActive ? s.smoothTcells : 0,
    smooth_f_cells: smoothActive ? s.smoothFcells : 0,
  };
  return {
    spec: {
      slice_duration: s.specSliceMs / 1000, max_columns: 1000, fmin: s.fmin, fmax: s.fmax,
      smoothing: s.smoothing,
      denoise: denoiseOn ? 1 : 0,
      coherence_min: s.coherenceMin,
      power_floor_k: s.powerGate > 0 ? 1.0 : 0,
      floor_percentile: s.powerGate,
      ...smoothParams,
    },
    mode: {
      slice_duration: s.specSliceMs / 1000, fmin: s.fmin, fmax: s.fmax,
      n_amp_pct: s.powerGate, n_gate: s.nGate,
      ...smoothParams,
    },
  };
}
