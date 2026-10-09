// Pure figure builder for the Compare view: the rotating-mode and quasi-stationary
// main plots stacked as vertical panels of ONE Plotly figure that share a single
// time x-axis. Because every panel is a y-axis on the same `xaxis`, a zoom/pan in any
// panel moves them all, and time-anchored annotations (lines, spans) draw straight
// through every panel. Kept free of React so the axis/domain math is unit-testable.
import type Plotly from "plotly.js-dist-min";
import type { PanelId } from "./annotations";
import type { PlotChrome } from "./colormaps";

export interface PanelSpec {
  id: PanelId;
  traces: Partial<Plotly.PlotData>[];
  yaxis: Partial<Plotly.LayoutAxis>;
  /** Relative height (default 1). */
  weight?: number;
  /** Show a legend (with this title) for this panel's named traces. Plotly has one
   *  legend, so at most one panel should set it. */
  legend?: string;
}

/** Plotly's id for the k-th (0-based) y-axis: "y", "y2", "y3", … */
export const axisId = (k: number): string => (k === 0 ? "y" : `y${k + 1}`);
/** The matching layout key: "yaxis", "yaxis2", … */
export const axisKey = (k: number): string => (k === 0 ? "yaxis" : `yaxis${k + 1}`);

/** Vertical [lo, hi] paper domains for panels listed top → bottom, sized by weight
 *  and separated by `gap` (paper fraction). */
export function panelDomains(weights: number[], gap = 0.035): [number, number][] {
  const n = weights.length;
  if (!n) return [];
  const usable = Math.max(0, 1 - gap * (n - 1));
  const total = weights.reduce((a, w) => a + Math.max(w, 0), 0) || n;
  const out: [number, number][] = [];
  let top = 1;
  for (const w of weights) {
    const h = (usable * (Math.max(w, 0) || 0)) / total;
    const lo = Math.max(0, top - h);
    out.push([round(lo), round(top)]);
    top = lo - gap;
  }
  return out;
}
const round = (v: number) => Math.round(v * 1e6) / 1e6;

/** First/last x of every non-empty series → [min start, max end] (union) and
 *  [max start, min end] (overlap; null when the ranges don't intersect). */
export function timeExtents(xs: (number[] | undefined)[]): {
  union: [number, number] | null;
  overlap: [number, number] | null;
} {
  const r = xs.filter((x): x is number[] => !!x && x.length > 0).map((x) => [x[0], x[x.length - 1]] as const);
  if (!r.length) return { union: null, overlap: null };
  const lo = r.map(([a, b]) => Math.min(a, b));
  const hi = r.map(([a, b]) => Math.max(a, b));
  const union: [number, number] = [Math.min(...lo), Math.max(...hi)];
  const o: [number, number] = [Math.max(...lo), Math.min(...hi)];
  return { union, overlap: o[0] < o[1] ? o : null };
}

export interface CompareFigure {
  data: Partial<Plotly.PlotData>[];
  layout: Partial<Plotly.Layout>;
  /** Visible panel → its y-axis id (for annotations and click → panel lookup). */
  axisOf: Partial<Record<PanelId, string>>;
}

export function buildCompareFigure(
  panels: PanelSpec[],
  opts: { chrome: PlotChrome; xTitle: string; xRange?: [number, number] | null; uirevision?: string },
): CompareFigure {
  const domains = panelDomains(panels.map((p) => p.weight ?? 1));
  const axisStyle = {
    gridcolor: opts.chrome.gridcolor,
    zerolinecolor: opts.chrome.zerolinecolor,
    linecolor: opts.chrome.linecolor,
    ticks: "outside" as const,
    tickcolor: opts.chrome.tickcolor,
    automargin: true,
  };
  const data: Partial<Plotly.PlotData>[] = [];
  const layout: Record<string, unknown> = {
    uirevision: opts.uirevision,
    hovermode: "x",
    showlegend: panels.some((p) => p.legend != null),
    margin: { l: 70, r: 110, t: 24, b: 48 },
  };
  const axisOf: Partial<Record<PanelId, string>> = {};

  panels.forEach((p, k) => {
    const yid = axisId(k);
    const [lo, hi] = domains[k];
    axisOf[p.id] = yid;
    layout[axisKey(k)] = { ...axisStyle, ...p.yaxis, domain: [lo, hi], anchor: "x" };
    for (const t of p.traces) {
      const tr: Record<string, unknown> = { ...t, xaxis: "x", yaxis: yid };
      // Heatmap colorbars sit beside their own panel instead of spanning the figure.
      if (t.type === "heatmap" && t.showscale !== false) {
        tr.colorbar = {
          ...(t.colorbar as object),
          y: (lo + hi) / 2, yanchor: "middle", len: hi - lo, lenmode: "fraction", x: 1.01,
        };
      }
      // Only the legend panel contributes legend entries.
      if (p.legend == null) tr.showlegend = false;
      data.push(tr as Partial<Plotly.PlotData>);
    }
    if (p.legend != null) {
      layout.legend = {
        x: 1.01, xanchor: "left", y: hi, yanchor: "top", font: { size: 10 }, traceorder: "normal",
        title: { text: p.legend, font: { size: 10 } },
      };
    }
  });

  // The x axis hangs off the bottom panel so its ticks/title sit under the stack;
  // spikes give a cross-panel time read-out at the mouse.
  layout.xaxis = {
    ...axisStyle,
    anchor: panels.length ? axisId(panels.length - 1) : "y",
    title: { text: opts.xTitle },
    showspikes: true, spikemode: "across", spikesnap: "cursor", spikethickness: 1, spikedash: "dot",
    ...(opts.xRange ? { range: opts.xRange, autorange: false } : { autorange: true }),
  };
  return { data, layout: layout as Partial<Plotly.Layout>, axisOf };
}

/** Which panel a Plotly click landed in, from the clicked trace's y-axis id. */
export function panelForAxis(axisOf: Partial<Record<PanelId, string>>, yaxis: string | undefined): PanelId | null {
  const id = yaxis ?? "y";
  for (const [panel, ax] of Object.entries(axisOf)) if (ax === id) return panel as PanelId;
  return null;
}

// ── User panel order (Compare "reorder") ─────────────────────────────
// `order` is the user's saved top→bottom sequence of panel ids. Panels it doesn't
// mention (never reordered, or new — e.g. a newly selected plasma signal) keep their
// default relative order and go after the ordered ones.

/** `ids` (default order) re-sorted by the user's `order`. */
export function orderPanels<T extends string>(ids: T[], order: string[]): T[] {
  const rank = (id: T, i: number) => {
    const k = order.indexOf(id);
    return k >= 0 ? k : order.length + i;
  };
  return ids.map((id, i) => [id, rank(id, i)] as const).sort((a, b) => a[1] - b[1]).map(([id]) => id);
}

/** New saved order after moving `id` to position `to` among the `shown` panels
 *  (already in display order). Hidden panels keep their saved slots at the end so
 *  they return where they were when re-enabled. */
export function movePanel(shown: string[], order: string[], id: string, to: number): string[] {
  const from = shown.indexOf(id);
  if (from < 0) return order;
  const next = shown.filter((p) => p !== id);
  next.splice(Math.max(0, Math.min(next.length, to)), 0, id);
  return [...next, ...order.filter((p) => !next.includes(p))];
}
