// Quasi-stationary view — OWNED BY TEAMMATE A.
// Branch: gui-quasistationary — build here, PR into `gui`.
// VISION §4.1, §7. Summaries: 04_SLCONTOUR_summary2019, 08_Slcontour_II_2023.
import { useCallback, useEffect, useMemo, useState } from "react";
import type Plotly from "plotly.js-dist-min";
import { useStore } from "../../store";
import { useNode } from "../../lib/useNode";
import { usingLiveBackend } from "../../lib/api";
import NodeView from "../../lib/NodeView";
import Plot from "../../lib/Plot";
import type { ContourNode, LineNode, MetricsNode, Scatter2DNode } from "../../lib/contract";
import { qualityForK } from "../../lib/contract";

// ── Colorblind-safe palette (Wong 2011) ──────────────────────────────
// Blue + orange are distinguishable across deuteranopia, protanopia, tritanopia.
const LINE_PALETTE = ["#0072B2", "#E69F00", "#56B4E9", "#D55E00", "#CC79A7"];

// Diverging colorscale for signed field: blue → neutral → orange.
// Avoids red-green confusion; center adapts to background lightness.
const CB_DIV_DARK:  [number, string][] = [
  [0.0, "#2166ac"], [0.25, "#74acd5"], [0.5, "#f7f7f7"], [0.75, "#f4a460"], [1.0, "#b35900"],
];
const CB_DIV_LIGHT: [number, string][] = [
  [0.0, "#2166ac"], [0.25, "#74acd5"], [0.5, "#9e9e9e"], [0.75, "#f4a460"], [1.0, "#b35900"],
];

// ── Light-mode Plotly overrides ───────────────────────────────────────
const LT_AXIS = {
  gridcolor: "#e2e8f0", zerolinecolor: "#94a3b8",
  linecolor: "#94a3b8", tickcolor: "#94a3b8",
};
const LT_BASE: Partial<Plotly.Layout> = {
  plot_bgcolor: "#f8fafc",
  font: { family: "IBM Plex Mono, ui-monospace, monospace", size: 11, color: "#1a2332" },
};

// ── Hooks & helpers ───────────────────────────────────────────────────
function useDarkMode(): boolean {
  const [dark, setDark] = useState(
    () => typeof window !== "undefined"
      ? window.matchMedia("(prefers-color-scheme: dark)").matches
      : true,
  );
  useEffect(() => {
    const mq = window.matchMedia("(prefers-color-scheme: dark)");
    const onChange = (e: MediaQueryListEvent) => setDark(e.matches);
    mq.addEventListener("change", onChange);
    return () => mq.removeEventListener("change", onChange);
  }, []);
  return dark;
}

function themedLayout(
  dark: boolean,
  overrides: Partial<Plotly.Layout>,
): Partial<Plotly.Layout> {
  if (dark) return overrides;
  return {
    ...LT_BASE,
    ...overrides,
    xaxis: { ...LT_AXIS, ...(overrides.xaxis as object) },
    yaxis: { ...LT_AXIS, ...(overrides.yaxis as object) },
  };
}

function hexToRgba(hex: string, alpha: number): string {
  const r = parseInt(hex.slice(1, 3), 16);
  const g = parseInt(hex.slice(3, 5), 16);
  const b = parseInt(hex.slice(5, 7), 16);
  return `rgba(${r},${g},${b},${alpha})`;
}

function lineTraces(node: LineNode): Partial<Plotly.PlotData>[] {
  const sigma = node.meta?.sigma as number[][] | undefined;
  const traces: Partial<Plotly.PlotData>[] = [];

  node.series.forEach((s, i) => {
    const color = LINE_PALETTE[i % LINE_PALETTE.length];
    const sig = sigma?.[i];

    if (sig) {
      // Upper bound then lower with fill tonexty → shaded band
      traces.push({
        type: "scatter", mode: "lines", x: s.x,
        y: s.y.map((v, j) => v + sig[j]),
        line: { width: 0, color }, showlegend: false, hoverinfo: "skip",
      } as Partial<Plotly.PlotData>);
      traces.push({
        type: "scatter", mode: "lines", x: s.x,
        y: s.y.map((v, j) => v - sig[j]),
        fill: "tonexty", fillcolor: hexToRgba(color, 0.18),
        line: { width: 0, color }, showlegend: false, hoverinfo: "skip",
      } as Partial<Plotly.PlotData>);
    }

    traces.push({
      type: "scatter", mode: "lines", name: s.name, x: s.x, y: s.y,
      line: { color, width: 1.5 },
    } as Partial<Plotly.PlotData>);
  });

  return traces;
}

// ── Standalone CSS color scale bar ───────────────────────────────────
function ColorScale({ zrange, dark }: { zrange: [number, number]; dark: boolean }) {
  const stops = (dark ? CB_DIV_DARK : CB_DIV_LIGHT)
    .map(([pos, color]) => `${color} ${pos * 100}%`).join(", ");
  const [lo, hi] = zrange;
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 6, padding: "2px 8px 4px", fontSize: 10, color: "var(--text-dim)" }}>
      <span style={{ minWidth: 32, textAlign: "right" }}>{lo} G</span>
      <div style={{ flex: 1, height: 10, background: `linear-gradient(to right, ${stops})`, borderRadius: 2 }} />
      <span style={{ minWidth: 32 }}>+{hi} G</span>
      <span style={{ marginLeft: 4 }}>δB<sub>p</sub></span>
    </div>
  );
}

// ── Live API types (frame envelope from /api/{machine}/qs_fit/stream) ─
interface QsFitFrame {
  progress: number;
  final: boolean;
  data: {
    contour: { phi: number[]; theta: number[]; z: number[][]; units: string };
    sensors: { phi: number; theta: number }[];
    modes: { n: number; m: number; amp: number; phase_deg: number }[];
    quality: { K: number; chi2: number; n_channels: number; m_max: number };
  };
}

// ── useQsFit ──────────────────────────────────────────────────────────
// Mock mode:  reads individual mock JSON files via useNode (existing contract).
// Live mode:  opens an SSE stream to /api/{machine}/qs_fit/stream and builds
//             ContourNode + MetricsNode from each progressive coarse→fine frame.
function useQsFit(machine: string, fetchCursor: number) {
  const isLive = usingLiveBackend();

  // Pass empty string in live mode so useNode skips fetching (it guards on !machine).
  const mockMachine = isLive ? "" : machine;
  const { node: rawContour, loading: mockLoading, error: mockError } =
    useNode(mockMachine, "contour", { t: fetchCursor });
  const { node: rawQuality } = useNode(mockMachine, "fit_quality");
  const { node: rawPhaseFit } = useNode(mockMachine, "phase_fit");

  const [liveContour,  setLiveContour]  = useState<ContourNode | null>(null);
  const [liveQuality,  setLiveQuality]  = useState<MetricsNode | null>(null);
  const [liveProgress, setLiveProgress] = useState(0);
  const [liveLoading,  setLiveLoading]  = useState(isLive);
  const [liveError,    setLiveError]    = useState<string | null>(null);

  useEffect(() => {
    if (!isLive || !machine) return;
    /* eslint-disable react-hooks/set-state-in-effect -- reset before live stream; Meg's hookup, revisit later */
    setLiveLoading(true);
    setLiveError(null);
    setLiveContour(null);
    setLiveProgress(0);
    /* eslint-enable react-hooks/set-state-in-effect */

    const base = import.meta.env.VITE_API_BASE as string;
    const es = new EventSource(`${base}/api/${machine}/qs_fit/stream`);

    es.onmessage = (e: MessageEvent) => {
      const frame = JSON.parse(e.data as string) as QsFitFrame;
      const d = frame.data;

      const absMax = Math.max(...d.contour.z.flat().map(Math.abs), 1);

      setLiveContour({
        kind: "contour",
        x: d.contour.phi,
        y: d.contour.theta,
        z: d.contour.z,
        axes: { x: "φ (deg)", y: "θ (deg)", z: `δB<sub>p</sub> (${d.contour.units})` },
        zrange: [-absMax, absMax],
        overlay: {
          points: d.sensors.map(s => ({ x: s.phi, y: s.theta })),
          symbol: "square",
        },
        meta: { m: d.modes[0]?.m, n: d.modes[0]?.n },
      });

      const q = d.quality;
      setLiveQuality({
        kind: "metrics",
        title: "fit quality",
        fields: [
          { label: "K (cond.)",  value: q.K.toFixed(1),    status: qualityForK(q.K) },
          { label: "χ²",         value: q.chi2.toFixed(2) },
          { label: "channels",   value: q.n_channels },
          { label: "m max",      value: q.m_max },
        ],
      });

      setLiveProgress(frame.progress);
      if (frame.final) { setLiveLoading(false); es.close(); }
    };

    es.onerror = () => {
      setLiveError("connection to backend failed");
      setLiveLoading(false);
      es.close();
    };

    return () => es.close();
  }, [machine, isLive]);

  if (isLive) {
    return {
      contourNode: liveContour,
      qualityNode:  liveQuality,
      phaseFitNode: null as Scatter2DNode | null,
      loading:      liveLoading,
      error:        liveError,
      progress:     liveProgress,
    };
  }

  return {
    contourNode:  rawContour?.kind  === "contour"   ? rawContour  : null,
    qualityNode:  rawQuality?.kind  === "metrics"   ? rawQuality  : null,
    phaseFitNode: rawPhaseFit?.kind === "scatter2d" ? rawPhaseFit : null,
    loading:      mockLoading,
    error:        mockError ?? null,
    progress:     1,
  };
}

// ── Component ─────────────────────────────────────────────────────────
export default function QuasiStationaryTab({ machine }: { machine: string }) {
  const dark = useDarkMode();
  const { cursorMs, setCursorMs } = useStore();

  // localCursor: updates on every slider tick for smooth visuals.
  // cursorMs (store): only updated on pointer-up / chart click, so useNode
  // doesn't re-fetch (and Plotly doesn't purge/re-init) on every tick.
  const [localCursor, setLocalCursor] = useState(() => cursorMs === 0 ? 3140 : cursorMs);

  useEffect(() => {
    if (cursorMs === 0) setCursorMs(3140);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Keep localCursor in sync when store changes (e.g. other tab seeks)
  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- mirror external cursor; revisit later
    if (cursorMs !== 0) setLocalCursor(cursorMs);
  }, [cursorMs]);

  // fetchCursor: stable during drag (only updates on pointer-up / chart click).
  const fetchCursor = cursorMs === 0 ? 3140 : cursorMs;

  const { contourNode, qualityNode, phaseFitNode, loading: contourLoading, error: contourError, progress } =
    useQsFit(machine, fetchCursor);

  // Time-series nodes — useNode; live API doesn't provide these yet.
  const { node: phiTimeNode }   = useNode(machine, "phi_t");
  const { node: ampNode }       = useNode(machine, "amplitude");
  const { node: phaseTimeNode } = useNode(machine, "phase_t");

  const modeTag = contourNode?.meta?.m != null
    ? `m/n = ${contourNode.meta.m}/${contourNode.meta.n} locked mode`
    : null;

  // seekTo: stable ref so Plot.tsx's onClick dep never changes during drag.
  const seekTo = useCallback((e: Plotly.PlotMouseEvent) => {
    const x = e.points?.[0]?.x;
    if (x != null) {
      const t = Math.round(Number(x));
      setLocalCursor(t);
      setCursorMs(t);
    }
  }, [setCursorMs]);

  // ── Memoized Plot props ─────────────────────────────────────────────
  // Every data/layout object is memoized so its reference only changes when
  // the underlying node data or color scheme changes — NOT on every slider tick.
  // Without this, Plot.tsx sees new object refs every render and calls
  // Plotly.react on every tick → '_redrawFromAutoMarginCount' crash.

  const cursorLine = useMemo(() => ({
    type: "line" as const, x0: fetchCursor, x1: fetchCursor, y0: 0, y1: 1,
    yref: "paper" as const,
    line: {
      color: dark ? "rgba(255,255,255,0.45)" : "rgba(0,0,0,0.45)",
      width: 1.5, dash: "dot" as const,
    },
  }), [fetchCursor, dark]);

  const phiTimeData = useMemo(() =>
    phiTimeNode?.kind === "contour" ? [{
      type: "contour" as const,
      x: phiTimeNode.x, y: phiTimeNode.y, z: phiTimeNode.z,
      colorscale: dark ? CB_DIV_DARK : CB_DIV_LIGHT,
      zmin: (phiTimeNode.zrange ?? [-42, 42])[0],
      zmax: (phiTimeNode.zrange ?? [-42, 42])[1],
      contours: { coloring: "fill" as const },
      showscale: false,
    } as Partial<Plotly.PlotData>] : [],
  [dark, phiTimeNode]);

  // Slider / shared axis bounds — derived from loaded data
  const tMin = useMemo(() =>
    ampNode?.kind === "line" ? Math.round(ampNode.series[0]?.x[0] ?? 800) : 800,
  [ampNode]);
  const tMax = useMemo(() =>
    ampNode?.kind === "line" ? Math.round(ampNode.series[0]?.x.at(-1) ?? 6100) : 6100,
  [ampNode]);

  // Shared xaxis range keeps all three time plots visually aligned
  const timeXAxis = useMemo(() => ({ range: [tMin, tMax] }), [tMin, tMax]);

  const phiTimeLayout = useMemo(() =>
    phiTimeNode?.kind === "contour" ? themedLayout(dark, {
      xaxis: { ...timeXAxis, title: { text: phiTimeNode.axes.x } },
      yaxis: { title: { text: phiTimeNode.axes.y } },
      shapes: [cursorLine],
    } as Partial<Plotly.Layout>) : {},
  [dark, phiTimeNode, cursorLine, timeXAxis]);

  const ampData = useMemo(() =>
    ampNode?.kind === "line" ? lineTraces(ampNode) : [],
  [ampNode]);

  const ampLayout = useMemo(() =>
    ampNode?.kind === "line" ? themedLayout(dark, {
      xaxis: { ...timeXAxis, title: { text: ampNode.axes.x } },
      yaxis: { title: { text: ampNode.axes.y } },
      showlegend: true,
      legend: { orientation: "h" as const, y: 1.18, font: { size: 10 } },
      shapes: [cursorLine],
    } as Partial<Plotly.Layout>) : {},
  [dark, ampNode, cursorLine, timeXAxis]);

  const phaseTimeData = useMemo(() =>
    phaseTimeNode?.kind === "line" ? lineTraces(phaseTimeNode) : [],
  [phaseTimeNode]);

  const phaseTimeLayout = useMemo(() =>
    phaseTimeNode?.kind === "line" ? themedLayout(dark, {
      xaxis: { ...timeXAxis, title: { text: phaseTimeNode.axes.x } },
      yaxis: { title: { text: phaseTimeNode.axes.y } },
      showlegend: true,
      legend: { orientation: "h" as const, y: 1.18, font: { size: 10 } },
      shapes: [cursorLine],
    } as Partial<Plotly.Layout>) : {},
  [dark, phaseTimeNode, cursorLine, timeXAxis]);

  return (
    <div className="card" style={{ display: "flex", flexDirection: "column", gap: 10 }}>
      <div>
        <h2>Quasi-stationary — spatial fit δB<sub>p</sub>(φ, θ)</h2>
        <p className="desc" style={{ margin: 0 }}>shot {machine}{modeTag ? ` · ${modeTag}` : ""}</p>
      </div>

      {/* Streaming progress bar — visible while live frames arrive */}
      {progress < 1 && (
        <div style={{ height: 2, background: "var(--border)", borderRadius: 1, overflow: "hidden" }}>
          <div style={{
            height: "100%", background: "var(--accent)",
            width: `${Math.round(progress * 100)}%`,
            transition: "width 0.3s ease",
          }} />
        </div>
      )}

      {/* Two-column body: left = vs-φ  ·  right = vs-time */}
      <div style={{ display: "grid", gridTemplateColumns: "3fr 2fr", gap: 10 }}>

        {/* LEFT — φ-space plots stacked */}
        <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
          {qualityNode?.kind === "metrics" && <NodeView node={qualityNode} />}

          {contourLoading && <div className="placeholder">loading contour…</div>}
          {contourError && <div className="placeholder" style={{ color: "var(--bad)" }}>{contourError}</div>}
          {contourNode && <NodeView node={contourNode} height={280} />}

          {phaseFitNode?.kind === "scatter2d" && (
            <div>
              <div className="metrics-title">phase vs φ · n = {String(phaseFitNode.meta?.n_fit ?? "?")}</div>
              <NodeView node={phaseFitNode} height={175} />
            </div>
          )}
        </div>

        {/* RIGHT — time-series plots stacked, all sharing the same x range */}
        <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
          {phiTimeNode?.kind === "contour" && (
            <div>
              <div className="metrics-title">δB<sub>p</sub> vs time — toroidal array</div>
              <Plot height={200} data={phiTimeData} layout={phiTimeLayout} onClick={seekTo} />
              <ColorScale zrange={(phiTimeNode.zrange ?? [-42, 42]) as [number, number]} dark={dark} />
            </div>
          )}

          {ampNode?.kind === "line" && (
            <Plot height={145} data={ampData} layout={ampLayout} onClick={seekTo} />
          )}

          {phaseTimeNode?.kind === "line" && (
            <Plot height={145} data={phaseTimeData} layout={phaseTimeLayout} onClick={seekTo} />
          )}
        </div>
      </div>

      {/* Time scrubber — sticky so it's always reachable */}
      <div style={{
        position: "sticky", bottom: 0,
        display: "flex", alignItems: "center", gap: 12,
        padding: "8px 0 2px",
        borderTop: "1px solid var(--border)",
        background: "var(--panel)",
      }}>
        <span className="mono" style={{ fontSize: 12, minWidth: 90, color: "var(--text-dim)" }}>
          t = {localCursor} ms
        </span>
        <input
          type="range" min={tMin} max={tMax} step={10} value={localCursor}
          onChange={(e) => setLocalCursor(Number(e.target.value))}
          onPointerUp={() => setCursorMs(localCursor)}
          style={{ flex: 1 }}
        />
      </div>
    </div>
  );
}
