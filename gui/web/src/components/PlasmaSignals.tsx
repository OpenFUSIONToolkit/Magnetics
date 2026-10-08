// Plasma-signal strip — shown above every tab. Plots any channel in the shot file
// (Ip, Bt, κ, 3D-coil currents, individual probes, …) as stacked time traces on the
// global time axis (store.timeRange — zooming here zooms every tab's time plots and
// vice versa), with the global time cursor; clicking sets the cursor. (Pointnames
// not yet in the file are fetched with the Quasi-stationary tab's custom-signal
// panel, which merges them into the shot; they then appear here.) On the Compare tab (`plot={false}`) only the controls show: the selected signals are
// drawn as panels inside the Compare figure instead.
//
// Data: the `extra_signals` node — one request returns both the selected traces and
// `meta.available` (every channel in the file, grouped plasma / coil / sensor).
import { useCallback, useMemo } from "react";
import type Plotly from "plotly.js-dist-min";
import { useStore } from "../store";
import { useNode } from "../lib/useNode";
import Plot from "../lib/Plot";
import type { LineNode } from "../lib/contract";
import { LINE_PALETTE } from "../lib/plotTraces";
import { displayScale, signalAxisTitle } from "../lib/signalUnits";
import { resetTimeRangeOnDoubleClick, sharedXAxis, timeRangeFromRelayout } from "../lib/timeRange";

type Groups = { plasma: string[]; coil: string[]; sensor: string[] };
const PANEL_PX = 78; // plot height per trace
const GAP = 0.04; // vertical gap between stacked traces (paper fraction)

const chipStyle = (on: boolean): React.CSSProperties => ({
  fontSize: 11, padding: "1px 8px", borderRadius: 10, cursor: "pointer",
  background: on ? "var(--accent)" : "var(--panel)",
  color: on ? "#fff" : "var(--text-dim)", border: "1px solid var(--border)",
});

export default function PlasmaSignals({ machine, plot = true }: { machine: string; plot?: boolean }) {
  const theme = useStore((s) => s.theme);
  const cursorMs = useStore((s) => s.cursorMs);
  const setCursorMs = useStore((s) => s.setCursorMs);
  const timeRange = useStore((s) => s.timeRange);
  const cutFlattop = useStore((s) => s.cutFlattop);
  const setCutFlattop = useStore((s) => s.setCutFlattop);
  const setTimeRange = useStore((s) => s.setTimeRange);
  const selected = useStore((s) => s.traceSignals);
  const setSelected = useStore((s) => s.setTraceSignals);
  const open = useStore((s) => s.traceOpen);
  const setOpen = useStore((s) => s.setTraceOpen);

  // Always fetch (even collapsed) so the header can show what's available; the node
  // is light — ≤2000 points per selected trace.
  const { node, error } = useNode(machine, "extra_signals", { signals: selected.join(",") });
  const line = node?.kind === "line" ? (node as LineNode) : null;
  const groups = useMemo(
    () => (line?.meta?.available as Groups | undefined) ?? { plasma: [], coil: [], sensor: [] },
    [line],
  );
  const units = useMemo(() => (line?.meta?.units as Record<string, string> | undefined) ?? {}, [line]);
  const missing = (line?.meta?.missing as string[] | undefined) ?? [];
  const flattop = (line?.meta?.flattop_ms as [number, number] | null | undefined) ?? null;
  const inFile = useMemo(
    () => new Set([...groups.plasma, ...groups.coil, ...groups.sensor]),
    [groups.plasma, groups.coil, groups.sensor],
  );

  const toggle = (name: string) =>
    setSelected(selected.includes(name) ? selected.filter((n) => n !== name) : [...selected, name]);


  // ── One stacked figure, shared x axis, one y axis per trace ──────────
  const figure = useMemo(() => {
    const series = line?.series ?? [];
    const n = series.length;
    const data: Partial<Plotly.PlotData>[] = [];
    const layout: Record<string, unknown> = {
      showlegend: false,
      margin: { t: 6, b: 30, l: 70, r: 16 },
      xaxis: { title: { text: "time (ms)" }, anchor: n ? `y${n > 1 ? n : ""}` : "y", ...sharedXAxis(timeRange) },
      hovermode: "x unified",
    };
    series.forEach((s, i) => {
      const sc = displayScale(units[s.name], s.y);
      const ax = i === 0 ? "y" : `y${i + 1}`;
      const top = 1 - i / n;
      const bot = 1 - (i + 1) / n;
      data.push({
        type: "scatter", mode: "lines", name: s.name, x: s.x,
        y: sc.factor === 1 ? s.y : s.y.map((v) => v * sc.factor),
        xaxis: "x", yaxis: ax,
        line: { color: LINE_PALETTE[i % LINE_PALETTE.length], width: 1.4 },
        hovertemplate: `%{y:.4g} ${sc.unit}<extra>${s.name}</extra>`,
      } as Partial<Plotly.PlotData>);
      layout[i === 0 ? "yaxis" : `yaxis${i + 1}`] = {
        domain: [bot + (i === n - 1 ? 0 : GAP / 2), top - (i === 0 ? 0 : GAP / 2)],
        title: { text: signalAxisTitle(s.name, sc), font: { size: 10 } },
        anchor: "x", zeroline: false,
      };
    });
    const accent = theme === "dark" ? "#2ee6cf" : "#0a8d80"; // literal --accent
    // Draw the shared cursor only inside the traces' time span — the cursor starts
    // at 0 ms, which would otherwise stretch the axis back to t=0.
    const xs = series.flatMap((s) => (s.x.length ? [s.x[0], s.x[s.x.length - 1]] : []));
    const inSpan = xs.length > 0 && cursorMs >= Math.min(...xs) && cursorMs <= Math.max(...xs);
    const shapes: Record<string, unknown>[] = inSpan
      ? [{ type: "line", xref: "x", yref: "paper", x0: cursorMs, x1: cursorMs, y0: 0, y1: 1,
           line: { color: accent, width: 1.5, dash: "dash" } }]
      : [];
    // Analysis cut-off at the Ip flattop end: shade what the analyses now leave out.
    if (cutFlattop && flattop && xs.length) {
      const tEnd = Math.max(...xs);
      shapes.push(
        { type: "rect", xref: "x", yref: "paper", x0: flattop[1], x1: Math.max(tEnd, flattop[1]), y0: 0, y1: 1,
          fillcolor: "rgba(128,128,128,0.18)", line: { width: 0 }, layer: "below" },
        { type: "line", xref: "x", yref: "paper", x0: flattop[1], x1: flattop[1], y0: 0, y1: 1,
          line: { color: "#e0533d", width: 1.2 } },
      );
    }
    layout.shapes = shapes;
    layout.uirevision = `${machine}:${series.map((s) => s.name).join(",")}`;
    return { data, layout: layout as Partial<Plotly.Layout>, n };
  }, [line, units, cursorMs, theme, machine, timeRange, cutFlattop, flattop]);

  const onRelayout = useCallback((e: Record<string, unknown>) => {
    const r = timeRangeFromRelayout(e);
    if (r !== undefined) setTimeRange(r);
  }, [setTimeRange]);
  const onDoubleClick = useMemo(() => resetTimeRangeOnDoubleClick(setTimeRange), [setTimeRange]);

  const onClick = useCallback((e: Plotly.PlotMouseEvent) => {
    const x = e.points?.[0]?.x;
    if (typeof x === "number") setCursorMs(Math.round(x * 100) / 100);
  }, [setCursorMs]);

  const extraChannels = [...groups.coil, ...groups.sensor].filter((n) => !selected.includes(n));

  return (
    <section className="card plasma-signals" aria-label="Plasma signals" style={{ marginBottom: 12, padding: "6px 10px" }}>
      <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
        <button type="button" onClick={() => setOpen(!open)} aria-expanded={open}
          style={{ background: "none", border: "none", padding: 0, cursor: "pointer", fontFamily: "inherit",
            fontSize: "calc(11px * var(--font-scale))", fontWeight: 600, textTransform: "uppercase",
            letterSpacing: 0.5, color: "var(--accent)" }}>
          {open ? "▾" : "▸"} Plasma signals
        </button>
        {/* plasma signals in this shot (Ip, Bt, κ, …) as toggle chips */}
        {groups.plasma.map((name) => (
          <button key={name} type="button" style={chipStyle(selected.includes(name))}
            aria-pressed={selected.includes(name)} onClick={() => toggle(name)}>{name}</button>
        ))}
        {/* any other selected channel (coil, probe) — click to remove */}
        {selected.filter((n) => !groups.plasma.includes(n) && inFile.has(n)).map((name) => (
          <button key={name} type="button" style={chipStyle(true)} title="Remove from the strip"
            aria-pressed onClick={() => toggle(name)}>{name} ×</button>
        ))}
        <select value="" aria-label="add a signal" onChange={(e) => e.target.value && toggle(e.target.value)}
          style={{ fontSize: 11, background: "var(--panel)", color: "var(--text)", border: "1px solid var(--border)",
            borderRadius: 3, padding: "1px 4px" }}>
          <option value="">+ add coil / probe channel…</option>
          {extraChannels.map((n) => <option key={n} value={n}>{n}</option>)}
        </select>
        <label className="cmp-check" style={{ fontSize: 11, color: flattop ? "var(--text)" : "var(--text-dim)" }}
          title={flattop
            ? `Ip flattop ${Math.round(flattop[0])}–${Math.round(flattop[1])} ms (smoothed |Ip| ≥ 95 % of peak). When on, every analysis — QS fit, rotating maps and tracks — stops at the flattop end.`
            : "No Ip trace in this shot — can't find the flattop"}>
          <input type="checkbox" checked={cutFlattop} disabled={!flattop}
            onChange={(e) => setCutFlattop(e.target.checked)} />
          stop analysis at Ip flattop end{flattop ? ` (${Math.round(flattop[1])} ms)` : ""}
        </label>
        {timeRange && (
          <button type="button" onClick={() => setTimeRange(null)}
            title="Reset the shared time axis (every tab) to the full range"
            style={{ fontSize: 11, padding: "1px 8px", borderRadius: 3, cursor: "pointer", marginLeft: "auto",
              background: "var(--panel)", color: "var(--text-dim)", border: "1px solid var(--border)" }}>
            t {Math.round(timeRange[0])}–{Math.round(timeRange[1])} ms · ↺ full range
          </button>
        )}
      </div>
      {missing.length > 0 && (
        <div className="note" style={{ fontSize: 10, color: "var(--text-dim)" }}>
          not in this shot: {missing.join(", ")} — fetch it with the Quasi-stationary tab's custom signals
        </div>
      )}
      {error && <div className="note" style={{ fontSize: 10 }}>signals unavailable for this shot</div>}
      {open && plot && figure.n > 0 && (
        <Plot data={figure.data} layout={figure.layout} height={figure.n * PANEL_PX + 40}
          onClick={onClick} onRelayout={onRelayout} onDoubleClick={onDoubleClick}
          exportName={`shot_${machine}_plasma_signals`} />
      )}
      {open && !plot && figure.n > 0 && (
        <div className="note" style={{ fontSize: 10, color: "var(--text-dim)" }}>
          plotted as panels in the Compare figure below (toggle “Plasma signals” there)
        </div>
      )}
    </section>
  );
}
