// User-placed plot annotations for the Compare view: vertical time markers, shaded
// time spans, horizontal reference levels and labelled points. Pure data + pure
// mapping to Plotly shapes/annotations/traces, so the geometry is unit-testable and
// the store only holds plain JSON (persisted to localStorage, exportable as a file).
import type Plotly from "plotly.js-dist-min";

/** Panels of the Compare figure — the target of a panel-anchored annotation. The fixed
 *  analysis panels, plus one `sig:<channel>` panel per plasma signal (Ip, Bt, κ, …). */
export type FixedPanelId = "spec" | "mode_over_time" | "mode_amplitude" | "phi_t" | "amplitude" | "phase";
export type PanelId = FixedPanelId | `sig:${string}`;

export const PANEL_IDS: FixedPanelId[] = ["spec", "mode_over_time", "mode_amplitude", "phi_t", "amplitude", "phase"];

interface Base {
  id: string;
  label?: string;
  color?: string; // literal hex — Plotly doesn't resolve CSS custom properties
}
export type Annotation =
  | (Base & { kind: "vline"; t: number })
  | (Base & { kind: "span"; t0: number; t1: number })
  | (Base & { kind: "hline"; panel: PanelId; y: number })
  | (Base & { kind: "point"; panel: PanelId; t: number; y: number });

export type AnnotationKind = Annotation["kind"];
/** An annotation before the store assigns its id (distributes over the union). */
export type AnnotationInput = Annotation extends infer A ? (A extends Annotation ? Omit<A, "id"> : never) : never;
/** An in-place edit: any position / text field; `kind` and `id` never change. */
export type AnnotationPatch = Partial<{
  t: number; t0: number; t1: number; y: number; panel: PanelId; label: string; color: string;
}>;

// Readable on both the dark and the light plot background.
export const ANNOTATION_COLORS = ["#e8a33c", "#e0533d", "#4c9be8", "#3fb56b", "#a86bd1", "#8a8f98"];

export const DEFAULT_COLOR: Record<AnnotationKind, string> = {
  vline: ANNOTATION_COLORS[0],
  span: ANNOTATION_COLORS[2],
  hline: ANNOTATION_COLORS[3],
  point: ANNOTATION_COLORS[1],
};

export function newAnnotationId(): string {
  return typeof crypto !== "undefined" && "randomUUID" in crypto
    ? crypto.randomUUID()
    : `a${Date.now().toString(36)}${Math.random().toString(36).slice(2, 8)}`;
}

const isNum = (v: unknown): v is number => typeof v === "number" && Number.isFinite(v);
const isPanel = (v: unknown): v is PanelId =>
  PANEL_IDS.includes(v as FixedPanelId) || (typeof v === "string" && /^sig:[A-Za-z0-9_]+$/.test(v));

/** Validate untrusted JSON (localStorage / an imported file) into annotations.
 *  Invalid entries are dropped, not thrown on; missing ids are regenerated. */
export function parseAnnotations(raw: unknown): Annotation[] {
  if (!Array.isArray(raw)) return [];
  const out: Annotation[] = [];
  for (const r of raw) {
    if (!r || typeof r !== "object") continue;
    const o = r as Record<string, unknown>;
    const base: Base = {
      id: typeof o.id === "string" && o.id ? o.id : newAnnotationId(),
      ...(typeof o.label === "string" && o.label ? { label: o.label } : {}),
      ...(typeof o.color === "string" && /^#[0-9a-fA-F]{6}$/.test(o.color) ? { color: o.color } : {}),
    };
    if (o.kind === "vline" && isNum(o.t)) out.push({ ...base, kind: "vline", t: o.t });
    else if (o.kind === "span" && isNum(o.t0) && isNum(o.t1))
      out.push({ ...base, kind: "span", t0: Math.min(o.t0, o.t1), t1: Math.max(o.t0, o.t1) });
    else if (o.kind === "hline" && isPanel(o.panel) && isNum(o.y))
      out.push({ ...base, kind: "hline", panel: o.panel, y: o.y });
    else if (o.kind === "point" && isPanel(o.panel) && isNum(o.t) && isNum(o.y))
      out.push({ ...base, kind: "point", panel: o.panel, t: o.t, y: o.y });
  }
  return out;
}

export interface AnnotationLayers {
  shapes: Partial<Plotly.Shape>[];
  annotations: Partial<Plotly.Annotations>[];
  traces: Partial<Plotly.PlotData>[];
}

/**
 * Map annotations onto a (possibly multi-panel) Plotly figure.
 * `axisOf` maps each visible panel to its y-axis id ("y", "y2", …); annotations on a
 * hidden panel are skipped. Time-anchored kinds (vline, span) span the whole figure
 * height so a marker reads across every stacked panel at once.
 */
export function annotationsToPlotly(
  list: Annotation[],
  axisOf: Partial<Record<PanelId, string>>,
  textColor: string,
): AnnotationLayers {
  const shapes: Partial<Plotly.Shape>[] = [];
  const annotations: Partial<Plotly.Annotations>[] = [];
  const traces: Partial<Plotly.PlotData>[] = [];
  const font = { color: textColor, size: 10 };

  for (const a of list) {
    const color = a.color ?? DEFAULT_COLOR[a.kind];
    if (a.kind === "vline") {
      shapes.push({
        type: "line", xref: "x", yref: "paper", x0: a.t, x1: a.t, y0: 0, y1: 1,
        line: { color, width: 1.5 },
      });
      if (a.label)
        annotations.push({
          x: a.t, xref: "x", y: 1, yref: "paper", yanchor: "bottom", text: a.label,
          showarrow: false, font: { ...font, color },
        });
    } else if (a.kind === "span") {
      shapes.push({
        type: "rect", xref: "x", yref: "paper", x0: a.t0, x1: a.t1, y0: 0, y1: 1,
        fillcolor: color, opacity: 0.18, layer: "below", line: { width: 0 },
      });
      if (a.label)
        annotations.push({
          x: (a.t0 + a.t1) / 2, xref: "x", y: 1, yref: "paper", yanchor: "bottom", text: a.label,
          showarrow: false, font: { ...font, color },
        });
    } else {
      const yref = axisOf[a.panel];
      if (!yref) continue;
      if (a.kind === "hline") {
        shapes.push({
          type: "line", xref: "paper", yref: yref as Plotly.YAxisName, x0: 0, x1: 1, y0: a.y, y1: a.y,
          line: { color, width: 1.5, dash: "dot" },
        });
        if (a.label)
          annotations.push({
            x: 1, xref: "paper", xanchor: "right", y: a.y, yref: yref as Plotly.YAxisName,
            yanchor: "bottom", text: a.label, showarrow: false, font: { ...font, color },
          });
      } else {
        traces.push({
          type: "scatter", mode: a.label ? "text+markers" : "markers",
          x: [a.t], y: [a.y], xaxis: "x", yaxis: yref,
          text: a.label ? [a.label] : undefined, textposition: "top center",
          textfont: { ...font, color },
          marker: { color, size: 9, symbol: "diamond", line: { color: textColor, width: 1 } },
          name: a.label || "point", showlegend: false,
          hovertemplate: `${a.label ? a.label + "<br>" : ""}t=%{x:.2f} ms, y=%{y:.4g}<extra></extra>`,
        } as Partial<Plotly.PlotData>);
      }
    }
  }
  return { shapes, annotations, traces };
}
