// The generic renderer. Give it ANY `kind`-node and it draws the right plot —
// this is the whole point of the self-describing contract: views don't hand-roll
// Plotly for each analysis, and new Python analyses render with no frontend work.
//
// metrics → a small panel of labelled scalars (K, χ², counts) with quality color.
// everything else → a Plotly figure.
import type * as Plotly from "plotly.js";
import type { Node, Quality } from "./contract";
import Plot from "./Plot";
import { FIELD_DIVERGING, POWER_SEQUENTIAL, MODE_PALETTE, plotChrome } from "./colormaps";
import { useStore } from "../store";

const QCOLOR: Record<Quality, string> = { good: "#54e08a", warn: "#ffb454", bad: "#ff5c5c" };

export default function NodeView({ node, height }: { node: Node; height?: number }) {
  const dark = useStore((s) => s.theme === "dark");
  // Foreground ink that flips with the theme so white markers/labels/error bars
  // don't disappear on the light plot background.
  const ink = dark ? "rgba(255,255,255,0.85)" : "rgba(20,34,46,0.9)";
  const inkSubtle = dark ? "rgba(255,255,255,0.45)" : "rgba(20,34,46,0.5)";
  const inkEdge = dark ? "#000" : "#ffffff";
  const knockout = plotChrome(dark ? "dark" : "light").plot_bgcolor; // marker ring = bg
  switch (node.kind) {
    case "metrics":
      return (
        <div className="metrics">
          <div className="metrics-title">{node.title}</div>
          {node.fields.map((f, i) => (
            <div className="metric-row" key={i}>
              <span className="metric-label">{f.label}</span>
              <span className="metric-value" style={{ color: f.status ? QCOLOR[f.status] : undefined }}>
                {f.value}
              </span>
            </div>
          ))}
        </div>
      );

    case "contour": {
      const zr = node.zrange ?? symRange(node.z);
      const traces: Partial<Plotly.PlotData>[] = [
        {
          type: "contour", x: node.x, y: node.y, z: node.z,
          colorscale: FIELD_DIVERGING, zmin: zr[0], zmax: zr[1],
          contours: { coloring: "fill" },
          colorbar: { title: { text: node.axes.z ?? "" }, thickness: 12, outlinewidth: 0 },
        } as Partial<Plotly.PlotData>,
      ];
      if (node.overlay) {
        const pts = node.overlay.points;
        // Per-point hover text: a labelled point (sensor dot) shows its pointname above
        // the coordinates; an unlabelled one shows coordinates alone. Building the text
        // per point keeps mixed overlays correct (no empty line on the unlabelled ones).
        const hovertext = pts.map((p) => {
          const coords = `(${p.x.toFixed(0)}, ${p.y.toFixed(0)})`;
          return p.label ? `${p.label}<br>${coords}` : coords;
        });
        traces.push({
          type: "scatter", mode: "markers",
          x: pts.map((p) => p.x),
          y: pts.map((p) => p.y),
          text: hovertext,
          marker: { symbol: node.overlay.symbol ?? "square", size: 6, color: ink, line: { color: inkEdge, width: 0.5 } },
          hovertemplate: "%{text}<extra></extra>",
        } as Partial<Plotly.PlotData>);
      }
      return <Plot data={traces} height={height} layout={axisLayout(node.axes)} />;
    }

    case "heatmap": {
      const colorscale = node.discrete
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
      
      const isSpecDiscrete = node.discrete && zr && Math.abs(zr[0] - (-0.5)) < 0.1;

      return (
        <Plot
          height={height}
          layout={axisLayout(node.axes)}
          data={[{
            type: "heatmap", x: node.x, y: node.y, z: node.z,
            colorscale, zmin: zr?.[0], zmax: zr?.[1], zsmooth: node.discrete ? false : "best",
            colorbar: isSpecDiscrete
              ? {
                  title: { text: node.axes.z ?? "" },
                  thickness: 12,
                  outlinewidth: 0,
                  tickvals: [0, 1, 2, 3, 4, 5, 6],
                  ticktext: ["0", "1", "2", "3", "4", "5", "6"],
                  tickmode: "array" as const,
                }
              : { title: { text: node.axes.z ?? "" }, thickness: 12, outlinewidth: 0 },
          } as Partial<Plotly.PlotData>]}
        />
      );
    }

    case "scatter2d": {
      const hasErrorY = node.points.some(p => p.error_y !== undefined);
      const hasErrorX = node.points.some(p => p.error_x !== undefined);

      const traces: Partial<Plotly.PlotData>[] = [{
        type: "scatter", mode: "markers",
        x: node.points.map((p) => p.x), y: node.points.map((p) => p.y),
        text: node.points.map((p) => p.label ?? ""),
        marker: { size: 7, color: node.points.map((p) => groupColor(p.group)), line: { color: knockout, width: 0.5 } },
        hoverinfo: "x+y+text",
        ...(hasErrorY ? {
          error_y: {
            type: "data" as const,
            array: node.points.map((p) => p.error_y ?? 0),
            visible: true,
            color: inkSubtle,
            thickness: 1,
            width: 3,
          }
        } : {}),
        ...(hasErrorX ? {
          error_x: {
            type: "data" as const,
            array: node.points.map((p) => p.error_x ?? 0),
            visible: true,
            color: inkSubtle,
            thickness: 1,
            width: 3,
          }
        } : {}),
      } as Partial<Plotly.PlotData>];
      if (node.fit) {
        traces.push({
          type: "scatter", mode: "lines", x: node.fit.x, y: node.fit.y,
          line: { color: "#54e08a", width: 1.5, dash: "dot" }, hoverinfo: "skip",
          connectgaps: false,  // null entries = wrap breaks; don't bridge them
        } as Partial<Plotly.PlotData>);
      }
      return <Plot data={traces} height={height} layout={axisLayout(node.axes)} />;
    }

    case "equilibrium": {
      const levels = node.levels ?? [0.2, 0.4, 0.6, 0.8, 1.0];
      const flux = dark ? "rgba(120,170,255,0.55)" : "rgba(40,90,180,0.55)";
      const base = axisLayout(node.axes);
      const traces: Partial<Plotly.PlotData>[] = [
        {
          type: "contour", x: node.r, y: node.z, z: node.psi_n, autocontour: false,
          contours: { coloring: "lines", start: Math.min(...levels), end: 1.0, size: levels.length > 1 ? levels[1] - levels[0] : 0.2 },
          colorscale: [[0, flux], [1, flux]], showscale: false, hoverinfo: "skip",
        } as Partial<Plotly.PlotData>,
        {
          type: "scatter", mode: "lines", name: "LCFS", x: node.boundary.r, y: node.boundary.z,
          line: { color: "#2ee6cf", width: 2 }, hoverinfo: "skip",
        } as Partial<Plotly.PlotData>,
        {
          type: "scatter", mode: "markers", x: [node.axis.r], y: [node.axis.z],
          marker: { symbol: "cross", size: 8, color: "#2ee6cf" }, hoverinfo: "skip", showlegend: false,
        } as Partial<Plotly.PlotData>,
      ];
      return <Plot data={traces} height={height} layout={{ ...base, yaxis: { ...base.yaxis, scaleanchor: "x", scaleratio: 1 } } as Partial<Plotly.Layout>} />;
    }

    case "line": {
      const palette = ["#4aa3ff", "#ff5cad", "#ffb454", "#2ee6cf", "#9d7bff"];
      const traces: Partial<Plotly.PlotData>[] = [];
      node.series.forEach((s, i) => {
        const color = palette[i % palette.length];
        // shaded ±band (e.g. GP 2σ): upper edge then lower edge filled up to it.
        if (s.lower && s.upper) {
          traces.push({
            type: "scatter", mode: "lines", x: s.x, y: s.upper,
            line: { width: 0 }, showlegend: false, hoverinfo: "skip",
          } as Partial<Plotly.PlotData>);
          traces.push({
            type: "scatter", mode: "lines", x: s.x, y: s.lower, fill: "tonexty",
            fillcolor: withAlpha(color, 0.16), line: { width: 0 },
            name: `${s.name} ±2σ`, showlegend: false, hoverinfo: "skip",
          } as Partial<Plotly.PlotData>);
        }
        traces.push({
          type: "scatter", mode: "lines", name: s.name, x: s.x, y: s.y,
          line: { color, width: 1.6 },
        } as Partial<Plotly.PlotData>);
        // measured probe values the curve was fit to (Olofsson fig 10)
        if (s.markers) {
          traces.push({
            type: "scatter", mode: "markers", x: s.markers.x, y: s.markers.y,
            name: `${s.name} (probes)`, showlegend: false, hoverinfo: "x+y",
            marker: { color, size: 6, line: { color: inkEdge, width: 0.5 } },
          } as Partial<Plotly.PlotData>);
        }
      });
      return (
        <Plot
          height={height}
          layout={{ ...axisLayout(node.axes), showlegend: true, legend: { font: { size: 10 }, orientation: "h", y: 1.12 } }}
          data={traces}
        />
      );
    }
  }
}

function axisLayout(a: { x: string; y: string }): Partial<Plotly.Layout> {
  return { xaxis: { title: { text: a.x } }, yaxis: { title: { text: a.y } } } as Partial<Plotly.Layout>;
}

function symRange(z: number[][]): [number, number] {
  let m = 0;
  for (const row of z) for (const v of row) if (Number.isFinite(v)) m = Math.max(m, Math.abs(v));
  return [-m, m];
}

/** hex (#rrggbb) → rgba string with the given alpha, for shaded uncertainty bands. */
function withAlpha(hex: string, a: number): string {
  const h = hex.replace("#", "");
  const r = parseInt(h.slice(0, 2), 16);
  const g = parseInt(h.slice(2, 4), 16);
  const b = parseInt(h.slice(4, 6), 16);
  return `rgba(${r}, ${g}, ${b}, ${a})`;
}

const GROUP_COLORS = ["#2ee6cf", "#4aa3ff", "#ff5cad", "#ffb454", "#9d7bff", "#54e08a"];
function groupColor(group?: string): string {
  if (!group) return "#4aa3ff";
  let h = 0;
  for (let i = 0; i < group.length; i++) h = (h * 31 + group.charCodeAt(i)) | 0;
  return GROUP_COLORS[Math.abs(h) % GROUP_COLORS.length];
}
