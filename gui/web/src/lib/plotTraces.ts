// Shared Plotly trace builders for the main analysis plots, so the Quasi-stationary,
// Rotating and Compare views draw the same node identically (one place to restyle).
import type Plotly from "plotly.js-dist-min";
import type { ContourNode, HeatmapNode, LineNode } from "./contract";
import { MODE_PALETTE, POWER_SEQUENTIAL } from "./colormaps";

// ── Colorblind-safe palette (Wong 2011) — for sensor/channel traces ──
export const LINE_PALETTE = ["#0072B2", "#E69F00", "#56B4E9", "#D55E00", "#CC79A7", "#009E73", "#F0E442"];

// ── Quasi-stationary mode-number palette — green/purple/red for n=1,2,3,… ──
// Clearly distinct hues so each mode reads immediately, not blue/orange.
export const QS_MODE_PALETTE = ["#2ca02c", "#9467bd", "#d62728", "#8c564b", "#e377c2", "#bcbd22", "#17becf"];

export function hexToRgba(hex: string, alpha: number): string {
  const r = parseInt(hex.slice(1, 3), 16);
  const g = parseInt(hex.slice(3, 5), 16);
  const b = parseInt(hex.slice(5, 7), 16);
  return `rgba(${r},${g},${b},${alpha})`;
}

// Build Plotly traces from a LineNode, optionally with per-series visibility overrides.
export function lineTraces(
  node: LineNode,
  opts?: { visible?: boolean[]; opacity?: number[]; palette?: string[] },
): Partial<Plotly.PlotData>[] {
  const pal = opts?.palette ?? LINE_PALETTE;
  const traces: Partial<Plotly.PlotData>[] = [];

  node.series.forEach((s, i) => {
    const color = pal[i % pal.length];
    const vis = opts?.visible?.[i] !== false;
    const opacity = opts?.opacity?.[i] ?? 1;

    // ±1σ band from the contract's typed lower/upper fields (also what the
    // HDF5 export writes, so the band on screen matches the downloaded data).
    if (s.lower && s.upper && vis) {
      traces.push({
        type: "scatter", mode: "lines", x: s.x,
        y: s.upper,
        line: { width: 0, color }, showlegend: false, hoverinfo: "skip",
        opacity,
      } as Partial<Plotly.PlotData>);
      traces.push({
        type: "scatter", mode: "lines", x: s.x,
        y: s.lower,
        fill: "tonexty", fillcolor: hexToRgba(color, 0.45 * opacity),
        line: { width: 0, color }, showlegend: false, hoverinfo: "skip",
        opacity,
      } as Partial<Plotly.PlotData>);
    }

    traces.push({
      type: "scatter", mode: "lines", name: s.name, x: s.x, y: s.y,
      line: { color, width: 1.5 },
      visible: vis ? true : "legendonly",
      opacity,
    } as Partial<Plotly.PlotData>);
  });

  return traces;
}

// ── φ–t contour colormaps (QS) ───────────────────────────────────────
export type PhiColormap = "rdbu" | "cividis" | "viridis";
export function phiColormapProps(c: PhiColormap) {
  if (c === "cividis") return { colorscale: "Cividis", reversescale: false };
  if (c === "viridis") return { colorscale: "Viridis", reversescale: false };
  return { colorscale: "RdBu", reversescale: true };  // RdBu_r ≈ notebook matplotlib
}

/** δBp(φ, t) heatmap + (optional) per-time peak-φ markers. */
export function phiTimeTraces(
  node: ContourNode,
  peak: number[] | null,
  cmap: PhiColormap = "rdbu",
): Partial<Plotly.PlotData>[] {
  const [zmin, zmax] = node.zrange ?? [-42, 42];
  const traces: Partial<Plotly.PlotData>[] = [{
    type: "heatmap" as const,
    x: node.x, y: node.y, z: node.z,
    ...phiColormapProps(cmap),
    zmin, zmax,
    zsmooth: false,
    showscale: true,
    colorbar: { title: { text: "Fit" }, thickness: 12, outlinewidth: 0 },
  } as Partial<Plotly.PlotData>];
  if (peak) {
    traces.push({
      type: "scatter" as const, mode: "markers" as const,
      x: node.x, y: peak,
      marker: { symbol: "circle-open" as const, size: 4, color: "white", line: { width: 1, color: "white" } },
      hoverinfo: "skip" as const, showlegend: false,
    } as Partial<Plotly.PlotData>);
  }
  return traces;
}

/** The MODESPEC spectrogram heatmap — discrete |n| palette for the mode-number map,
 *  sequential for log power. */
export function spectrogramTrace(node: HeatmapNode): Partial<Plotly.PlotData> {
  const colorscale: [number, string][] = node.discrete
    ? (() => {
        const n = MODE_PALETTE.length;
        const s: [number, string][] = [];
        for (let i = 0; i < n; i++) {
          s.push([i / n, MODE_PALETTE[i]], [(i + 1) / n, MODE_PALETTE[i]]);
        }
        return s;
      })()
    : POWER_SEQUENTIAL;
  const zr = node.zrange;
  return {
    type: "heatmap" as const,
    x: node.x,
    y: node.y,
    z: node.z,
    colorscale,
    zmin: zr?.[0],
    zmax: zr?.[1],
    zsmooth: (node.discrete ? false : "best") as false | "best" | "fast" | undefined,
    colorbar: {
      title: { text: node.axes.z ?? "" },
      thickness: 12,
      outlinewidth: 0,
      ...(node.discrete
        ? {
            // one tick per integer mode-number magnitude |n| = 0 … 6
            tickvals: Array.from({ length: 7 }, (_, i) => i),
            ticktext: Array.from({ length: 7 }, (_, i) => `${i}`),
            tickmode: "array" as const,
          }
        : {}),
    },
  } as Partial<Plotly.PlotData>;
}
