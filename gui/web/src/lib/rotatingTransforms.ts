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
