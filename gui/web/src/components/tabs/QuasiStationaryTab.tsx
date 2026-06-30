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
// Follows the app-wide theme toggle (store), not the OS setting, so the
// in-app light/dark switch re-skins this tab's plots along with everything else.
function useDarkMode(): boolean {
  return useStore((s) => s.theme === "dark");
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
        fill: "tonexty", fillcolor: hexToRgba(color, 0.45),
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

// ── -180→180 angle remapping ─────────────────────────────────────────
// Shifts a sorted 0-360 angle array to -180-180 and reorders the
// corresponding z dimension so the grid stays consistent.
function remapAxis180(
  vals: number[], z: number[][], axis: "x" | "y",
): { vals: number[]; z: number[][] } {
  const split = vals.findIndex(v => v > 180);
  if (split === -1) return { vals, z };
  const newVals = [...vals.slice(split).map(v => v - 360), ...vals.slice(0, split)];
  const newZ = axis === "x"
    ? z.map(row => [...row.slice(split), ...row.slice(0, split)])
    : [...z.slice(split), ...z.slice(0, split)];
  return { vals: newVals, z: newZ };
}
function remapOverlay(ov: ContourNode["overlay"]): ContourNode["overlay"] {
  if (!ov) return ov;
  return { ...ov, points: ov.points.map(p => ({ ...p, x: p.x > 180 ? p.x - 360 : p.x, y: p.y > 180 ? p.y - 360 : p.y })) };
}

// ── useQsFit ──────────────────────────────────────────────────────────
// Mock mode: reads individual mock JSON files via useNode (existing contract).
// Live mode: calls real REST nodes — qs_fit (spatial map) and fit_quality
//            (metrics panel). Each path zeros-out the machine string on the
//            inactive side so useNode skips the fetch (it guards on !machine).
function useQsFit(
  machine: string,
  fetchCursor: number,
  qsParams: Record<string, string>,
) {
  const isLive = usingLiveBackend();

  const mockMachine = isLive ? "" : machine;
  const liveMachine = isLive ? machine : "";

  const liveQsParams = useMemo(
    () => ({ ...qsParams, time: String(fetchCursor) }),
    [qsParams, fetchCursor],
  );

  const { node: rawContour, loading: mockLoading, error: mockError } =
    useNode(mockMachine, "contour", { t: fetchCursor });
  const { node: rawQuality } = useNode(mockMachine, "fit_quality");

  const { node: liveContourNode, loading: liveLoading, error: liveError } =
    useNode(liveMachine, "qs_fit", liveQsParams);
  const { node: liveQualityNode } = useNode(liveMachine, "fit_quality", qsParams);

  if (isLive) {
    return {
      contourNode: liveContourNode?.kind === "contour" ? liveContourNode : null,
      qualityNode: liveQualityNode?.kind === "metrics" ? liveQualityNode : null,
      loading:     liveLoading,
      error:       liveError,
      progress:    liveLoading ? 0.5 : 1,
    };
  }

  return {
    contourNode: rawContour?.kind === "contour" ? rawContour : null,
    qualityNode: rawQuality?.kind === "metrics" ? rawQuality : null,
    loading:     mockLoading,
    error:       mockError ?? null,
    progress:    1,
  };
}

// ── Sensor arrays most useful for QS analysis ────────────────────────
const CHANNEL_FILTERS = [
  "Bp LFS midplane",
  "Bp LFS midplane bdot",
  "Bp LFS R+1",
  "Bp LFS R-1",
  "Bp LFS R+2",
  "Bp LFS R-2",
  "All LFS Bp Arrays",
  "Bp HFS +midplane",
  "Bp HFS -midplane",
];

// ── Component ─────────────────────────────────────────────────────────
export default function QuasiStationaryTab({ machine }: { machine: string }) {
  const dark = useDarkMode();
  const { cursorMs, setCursorMs } = useStore();

  // ── Analysis settings ─────────────────────────────────────────────
  const [ns, setNs]               = useState("1,2,3");
  const [ms, setMs]               = useState("0");
  const [channelFilter, setChannelFilter] = useState("Bp LFS midplane");
  const [detrendType, setDetrendType]     = useState("baseline");
  const [detrendLo, setDetrendLo] = useState("");  // "" = auto (first 10ms)
  const [detrendHi, setDetrendHi] = useState("");  // "" = auto

  // Stable params dict — triggers re-fetch when any setting changes.
  // time-cursor is merged in per-node so phi_t/amp/phase_t share the same base.
  const qsParams = useMemo(() => {
    const p: Record<string, string> = {
      ns,
      ms,
      channel_filter: channelFilter,
      detrend_type: detrendType,
    };
    if (detrendLo && detrendHi) {
      p.detrend_lo = detrendLo;
      p.detrend_hi = detrendHi;
    }
    return p;
  }, [ns, ms, channelFilter, detrendType, detrendLo, detrendHi]);

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

  const { contourNode, qualityNode, loading: contourLoading, error: contourError, progress } =
    useQsFit(machine, fetchCursor, qsParams);

  // phase_fit is a plain REST node — works in both mock and live mode.
  const { node: rawPhaseFit } = useNode(machine, "phase_fit");
  const phaseFitNode = rawPhaseFit?.kind === "scatter2d" ? rawPhaseFit : null;

  // Time-series nodes — pass qsParams so channel filter / modes / detrend are respected.
  const { node: phiTimeNode }   = useNode(machine, "phi_t",      qsParams);
  const { node: ampNode }       = useNode(machine, "amplitude",   qsParams);
  const { node: phaseTimeNode } = useNode(machine, "phase_t",     qsParams);

  // ── Remap phi/theta from 0-360 → -180-180 ──────────────────────────
  const heroContour = useMemo((): ContourNode | null => {
    if (!contourNode) return null;
    const rx = remapAxis180(contourNode.x, contourNode.z, "x");
    const ry = remapAxis180(contourNode.y, rx.z, "y");
    return { ...contourNode, x: rx.vals, y: ry.vals, z: ry.z, overlay: remapOverlay(contourNode.overlay) };
  }, [contourNode]);

  // phi_t: keep φ in 0-360 to match plots.plot_slice (reference uses [0,360] ticks at 90s)
  const phiTimePlot = phiTimeNode?.kind === "contour" ? phiTimeNode : null;

  // Peak toroidal angle at each time — mirrors plots.plot_slice's white open-circle trace
  const phiPeak = useMemo(() => {
    if (!phiTimePlot) return null;
    return phiTimePlot.x.map((_, j) => {
      let bestI = 0, bestV = -Infinity;
      for (let i = 0; i < phiTimePlot.z.length; i++) {
        if (phiTimePlot.z[i][j] > bestV) { bestV = phiTimePlot.z[i][j]; bestI = i; }
      }
      return phiTimePlot.y[bestI];
    });
  }, [phiTimePlot]);

  // RMS amplitude over φ at each time — mirrors plots.plot_slice's top RMS panel
  const phiRms = useMemo(() => {
    if (!phiTimePlot) return null;
    const nPhi = phiTimePlot.z.length;
    return phiTimePlot.x.map((_, j) =>
      Math.sqrt(phiTimePlot.z.reduce((s, row) => s + row[j] ** 2, 0) / nPhi)
    );
  }, [phiTimePlot]);

  const phaseFitRemapped = useMemo((): Scatter2DNode | null => {
    if (phaseFitNode?.kind !== "scatter2d") return null;
    const pts = phaseFitNode.points.map(p => ({
      ...p,
      x: p.x > 180 ? p.x - 360 : p.x,
      y: p.y > 180 ? p.y - 360 : p.y,
    }));
    let fit = phaseFitNode.fit;
    if (fit && fit.x.length >= 2) {
      const x0 = fit.x[0], x1 = fit.x[fit.x.length - 1];
      const slope = (fit.y[fit.y.length - 1] - fit.y[0]) / (x1 - x0);
      const intercept = fit.y[0] - slope * x0;
      fit = { x: [-180, 180], y: [slope * -180 + intercept, slope * 180 + intercept] };
    }
    return { ...phaseFitNode, points: pts, fit };
  }, [phaseFitNode]);

  // ── φ-space Plot props (own Plot calls so we can set dtick: 90) ──────
  const heroData = useMemo((): Partial<Plotly.PlotData>[] => {
    if (!heroContour) return [];
    const [zmin, zmax] = heroContour.zrange ?? [-42, 42];
    const traces: Partial<Plotly.PlotData>[] = [{
      type: "contour" as const, x: heroContour.x, y: heroContour.y, z: heroContour.z,
      colorscale: dark ? CB_DIV_DARK : CB_DIV_LIGHT, zmin, zmax,
      contours: { coloring: "fill" as const },
      colorbar: { title: { text: heroContour.axes.z ?? "" }, thickness: 12, outlinewidth: 0 },
    } as Partial<Plotly.PlotData>];
    if (heroContour.overlay) {
      traces.push({
        type: "scatter" as const, mode: "markers" as const,
        x: heroContour.overlay.points.map(p => p.x),
        y: heroContour.overlay.points.map(p => p.y),
        marker: { symbol: (heroContour.overlay.symbol ?? "square") as string, size: 6, color: "rgba(255,255,255,0.85)", line: { color: "#000", width: 0.5 } },
        hoverinfo: "x+y" as const,
      } as Partial<Plotly.PlotData>);
    }
    return traces;
  }, [dark, heroContour]);

  const heroLayout = useMemo(() =>
    heroContour ? themedLayout(dark, {
      xaxis: { title: { text: heroContour.axes.x }, dtick: 90, range:[-180,180] },
      yaxis: { title: { text: heroContour.axes.y }, dtick: 90, range:[-180,180] },
    } as Partial<Plotly.Layout>) : {},
  [dark, heroContour]);

  const phaseFitData = useMemo((): Partial<Plotly.PlotData>[] => {
    if (!phaseFitRemapped) return [];
    const traces: Partial<Plotly.PlotData>[] = [{
      type: "scatter" as const, mode: "markers" as const,
      x: phaseFitRemapped.points.map(p => p.x),
      y: phaseFitRemapped.points.map(p => p.y),
      text: phaseFitRemapped.points.map(p => p.label ?? ""),
      marker: { size: 7, color: "#4aa3ff", line: { color: "#0a0f16", width: 0.5 } },
      hoverinfo: "x+y+text" as const,
    } as Partial<Plotly.PlotData>];
    if (phaseFitRemapped.fit) {
      traces.push({
        type: "scatter" as const, mode: "lines" as const,
        x: phaseFitRemapped.fit.x, y: phaseFitRemapped.fit.y,
        line: { color: "#54e08a", width: 1.5, dash: "dot" as const },
        hoverinfo: "skip" as const,
      } as Partial<Plotly.PlotData>);
    }
    return traces;
  }, [phaseFitRemapped]);

  const phaseFitLayout = useMemo(() =>
    phaseFitRemapped ? themedLayout(dark, {
      xaxis: { title: { text: phaseFitRemapped.axes.x }, dtick: 90, range:[-180,180] },
      yaxis: { title: { text: phaseFitRemapped.axes.y }, dtick: 90, range:[-180,180] },
    } as Partial<Plotly.Layout>) : {},
  [dark, phaseFitRemapped]);

  const modeTag = contourNode?.meta?.n != null
    ? contourNode.meta.m === 0
      ? `n = ${contourNode.meta.n} locked mode`
      : `m/n = ${contourNode.meta.m}/${contourNode.meta.n} locked mode`
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

  const phiTimeData = useMemo((): Partial<Plotly.PlotData>[] => {
    if (!phiTimePlot) return [];
    const [zmin, zmax] = phiTimePlot.zrange ?? [-42, 42];
    const traces: Partial<Plotly.PlotData>[] = [{
      type: "contour" as const,
      x: phiTimePlot.x, y: phiTimePlot.y, z: phiTimePlot.z,
      colorscale: dark ? CB_DIV_DARK : CB_DIV_LIGHT,
      zmin, zmax,
      contours: { coloring: "fill" as const },
      showscale: false,
    } as Partial<Plotly.PlotData>];
    if (phiPeak) {
      traces.push({
        type: "scatter" as const, mode: "markers" as const,
        x: phiTimePlot.x, y: phiPeak,
        marker: { symbol: "circle-open" as const, size: 4, color: "white", line: { width: 1, color: "white" } },
        hoverinfo: "skip" as const, showlegend: false,
      } as Partial<Plotly.PlotData>);
    }
    return traces;
  }, [dark, phiTimePlot, phiPeak]);

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
    phiTimePlot ? themedLayout(dark, {
      xaxis: { ...timeXAxis, title: { text: phiTimePlot.axes.x } },
      yaxis: { title: { text: phiTimePlot.axes.y }, range: [0, 360], dtick: 90, tickvals: [0, 90, 180, 270, 360] },
      shapes: [cursorLine],
    } as Partial<Plotly.Layout>) : {},
  [dark, phiTimePlot, cursorLine, timeXAxis]);

  const ampData = useMemo(() =>
    ampNode?.kind === "line" ? lineTraces(ampNode) : [],
  [ampNode]);

  const ampLayout = useMemo(() =>
    ampNode?.kind === "line" ? themedLayout(dark, {
      xaxis: { ...timeXAxis, title: { text: ampNode.axes.x } },
      yaxis: { title: { text: ampNode.axes.y }, rangemode: "tozero" as const },
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
      yaxis: {
        title: { text: phaseTimeNode.axes.y },
        range: [-180, 180],
        tickvals: [-180, -90, 0, 90, 180],
      },
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

      {/* ── Analysis settings ─────────────────────────────────────────── */}
      <div style={{ display: "flex", flexWrap: "wrap", gap: 8, alignItems: "center", fontSize: 11, color: "var(--text-dim)", borderBottom: "1px solid var(--border)", paddingBottom: 8 }}>
        <label style={{ display: "flex", alignItems: "center", gap: 4 }}>
          Array
          <select value={channelFilter} onChange={e => setChannelFilter(e.target.value)}
            style={{ fontSize: 11, background: "var(--panel)", color: "var(--text)", border: "1px solid var(--border)", borderRadius: 3, padding: "1px 4px" }}>
            {CHANNEL_FILTERS.map(f => <option key={f} value={f}>{f}</option>)}
          </select>
        </label>
        <label style={{ display: "flex", alignItems: "center", gap: 4 }}>
          n modes
          <input value={ns} onChange={e => setNs(e.target.value)}
            style={{ width: 60, fontSize: 11, background: "var(--panel)", color: "var(--text)", border: "1px solid var(--border)", borderRadius: 3, padding: "1px 4px" }} />
        </label>
        <label style={{ display: "flex", alignItems: "center", gap: 4 }}>
          m modes
          <input value={ms} onChange={e => setMs(e.target.value)}
            style={{ width: 40, fontSize: 11, background: "var(--panel)", color: "var(--text)", border: "1px solid var(--border)", borderRadius: 3, padding: "1px 4px" }} />
        </label>
        <label style={{ display: "flex", alignItems: "center", gap: 4 }}>
          Detrend
          <select value={detrendType} onChange={e => setDetrendType(e.target.value)}
            style={{ fontSize: 11, background: "var(--panel)", color: "var(--text)", border: "1px solid var(--border)", borderRadius: 3, padding: "1px 4px" }}>
            <option value="baseline">baseline</option>
            <option value="none">none</option>
            <option value="linear">linear</option>
            <option value="endpoints">endpoints</option>
          </select>
        </label>
        {detrendType !== "none" && (
          <label style={{ display: "flex", alignItems: "center", gap: 4 }}>
            band (ms)
            <input placeholder="auto" value={detrendLo} onChange={e => setDetrendLo(e.target.value)}
              style={{ width: 52, fontSize: 11, background: "var(--panel)", color: "var(--text)", border: "1px solid var(--border)", borderRadius: 3, padding: "1px 4px" }} />
            –
            <input placeholder="auto" value={detrendHi} onChange={e => setDetrendHi(e.target.value)}
              style={{ width: 52, fontSize: 11, background: "var(--panel)", color: "var(--text)", border: "1px solid var(--border)", borderRadius: 3, padding: "1px 4px" }} />
          </label>
        )}
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
          {heroContour && <Plot height={280} data={heroData} layout={heroLayout} />}

          {phaseFitRemapped && (
            <div>
              <div className="metrics-title">phase vs φ · n = {String(phaseFitRemapped.meta?.n_fit ?? "?")}</div>
              <Plot height={175} data={phaseFitData} layout={phaseFitLayout} />
            </div>
          )}
        </div>

        {/* RIGHT — time-series plots stacked, all sharing the same x range */}
        <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
          {phiTimePlot && (
            <div>
              <div className="metrics-title">δB<sub>p</sub> vs time — toroidal array</div>
              {/* RMS amplitude panel — mirrors plots.plot_slice's top RMS subplot */}
              {phiRms && (
                <Plot height={70} data={[{
                  type: "scatter" as const, mode: "lines" as const,
                  x: phiTimePlot.x, y: phiRms,
                  line: { color: LINE_PALETTE[0], width: 1.5 },
                  showlegend: false,
                } as Partial<Plotly.PlotData>]} layout={themedLayout(dark, {
                  xaxis: { ...timeXAxis, showticklabels: false },
                  yaxis: { title: { text: "RMS (G)" }, rangemode: "tozero" as const },
                  margin: { t: 4, b: 4, l: 48, r: 8 },
                  shapes: [cursorLine],
                } as Partial<Plotly.Layout>)} onClick={seekTo} />
              )}
              <Plot height={200} data={phiTimeData} layout={phiTimeLayout} onClick={seekTo} />
              <ColorScale zrange={(phiTimePlot.zrange ?? [-42, 42]) as [number, number]} dark={dark} />
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
