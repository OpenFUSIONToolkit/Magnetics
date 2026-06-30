// ─────────────────────────────────────────────────────────────────────────────
// The self-describing result contract — the seam between the GUI and Python.
//
// Every analysis the backend produces returns a `Node`: a JSON object carrying a
// `kind` discriminator. The GUI renders any Node generically via <NodeView>, so
// adding a new analysis on the Python side needs ZERO frontend changes — the
// physics teams just emit one of these shapes.
//
// This mirrors the Python builders (magfit/contracts.py): contour · heatmap ·
// scatter2d · metrics, plus `line` for time-series traces. Keep the two in sync.
// ─────────────────────────────────────────────────────────────────────────────

export interface Axes {
  x: string; // axis label incl. units, e.g. "φ (deg)"
  y: string;
  z?: string; // colorbar label for 2-D fields, e.g. "δBp (G)"
}

/** A point overlay (e.g. sensor positions drawn on a contour). */
export interface Overlay {
  points: { x: number; y: number; label?: string }[];
  symbol?: "square" | "circle" | "cross";
}

/** Filled contour of a 2-D field — the SLCONTOUR φ–θ map. z is row-major [y][x]. */
export interface ContourNode {
  kind: "contour";
  x: number[];
  y: number[];
  z: number[][];
  axes: Axes;
  /** symmetric diverging range; omit to auto-scale. */
  zrange?: [number, number];
  overlay?: Overlay; // sensor markers
  meta?: Record<string, unknown>;
}

/** Image/heatmap — the MODESPEC spectrogram. `discrete` ⇒ z is a mode number. */
export interface HeatmapNode {
  kind: "heatmap";
  x: number[];
  y: number[];
  z: number[][];
  axes: Axes;
  discrete?: boolean; // true → mode-number palette; false → continuous (log power)
  zrange?: [number, number];
  meta?: Record<string, unknown>;
}

/** Scattered points — sensor geometry, phase-vs-angle fits. */
export interface Scatter2DNode {
  kind: "scatter2d";
  points: { x: number; y: number; label?: string; group?: string; error_x?: number; error_y?: number }[];
  axes: Axes;
  /** optional fitted line through the points (slope = n or m). */
  fit?: { x: number[]; y: number[] };
  meta?: Record<string, unknown>;
}

/** One or more 1-D traces — amplitude & phase vs time, GP mode shapes, etc.
 *  A series may carry a `lower`/`upper` envelope (same length as `y`), drawn as a
 *  shaded ±band — e.g. the 2σ uncertainty of a Gaussian-process mode shape. */
export interface LineNode {
  kind: "line";
  series: { name: string; x: number[]; y: number[]; lower?: number[]; upper?: number[] }[];
  axes: Axes;
  meta?: Record<string, unknown>;
}

/** A scalar quality panel — condition number K, χ², channel counts. */
export interface MetricsNode {
  kind: "metrics";
  title: string;
  fields: { label: string; value: string | number; status?: Quality }[];
  meta?: Record<string, unknown>;
}

export type Quality = "good" | "warn" | "bad";

export type Node =
  | ContourNode
  | HeatmapNode
  | Scatter2DNode
  | LineNode
  | MetricsNode;

/** SLCONTOUR condition-number thresholds (warn > 10, error > 20). */
export function qualityForK(K: number): Quality {
  if (!Number.isFinite(K) || K > 20) return "bad";
  if (K > 10) return "warn";
  return "good";
}
