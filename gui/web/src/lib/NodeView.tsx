// The generic renderer. Give it ANY `kind`-node and it draws the right plot —
// this is the whole point of the self-describing contract: views don't hand-roll
// Plotly for each analysis, and new Python analyses render with no frontend work.
//
// metrics → a small panel of labelled scalars (K, χ², counts) with quality color.
// everything else → a Plotly figure.
import type * as Plotly from "plotly.js";
import type { Node, Quality } from "./contract";
import Plot from "./Plot";
import { FIELD_DIVERGING, POWER_SEQUENTIAL, MODE_PALETTE } from "./colormaps";

const QCOLOR: Record<Quality, string> = { good: "#54e08a", warn: "#ffb454", bad: "#ff5c5c" };

export default function NodeView({ node, height }: { node: Node; height?: number }) {
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
        traces.push({
          type: "scatter", mode: "markers",
          x: node.overlay.points.map((p) => p.x),
          y: node.overlay.points.map((p) => p.y),
          marker: { symbol: node.overlay.symbol ?? "square", size: 6, color: "rgba(255,255,255,0.85)", line: { color: "#000", width: 0.5 } },
          hoverinfo: "x+y",
        } as Partial<Plotly.PlotData>);
      }
      return <Plot data={traces} height={height} layout={axisLayout(node.axes)} />;
    }

    case "heatmap": {
      const colorscale = node.discrete
        ? MODE_PALETTE.map((c, i) => [i / (MODE_PALETTE.length - 1), c] as [number, string])
        : POWER_SEQUENTIAL;
      const zr = node.zrange;
      return (
        <Plot
          height={height}
          layout={axisLayout(node.axes)}
          data={[{
            type: "heatmap", x: node.x, y: node.y, z: node.z,
            colorscale, zmin: zr?.[0], zmax: zr?.[1], zsmooth: node.discrete ? false : "best",
            colorbar: { title: { text: node.axes.z ?? "" }, thickness: 12, outlinewidth: 0 },
          } as Partial<Plotly.PlotData>]}
        />
      );
    }

    case "scatter2d": {
      const traces: Partial<Plotly.PlotData>[] = [{
        type: "scatter", mode: "markers",
        x: node.points.map((p) => p.x), y: node.points.map((p) => p.y),
        text: node.points.map((p) => p.label ?? ""),
        marker: { size: 7, color: node.points.map((p) => groupColor(p.group)), line: { color: "#0a0f16", width: 0.5 } },
        hoverinfo: "x+y+text",
      } as Partial<Plotly.PlotData>];
      if (node.fit) {
        traces.push({
          type: "scatter", mode: "lines", x: node.fit.x, y: node.fit.y,
          line: { color: "#54e08a", width: 1.5, dash: "dot" }, hoverinfo: "skip",
        } as Partial<Plotly.PlotData>);
      }
      return <Plot data={traces} height={height} layout={axisLayout(node.axes)} />;
    }

    case "line": {
      const palette = ["#4aa3ff", "#ff5cad", "#ffb454", "#2ee6cf", "#9d7bff"];
      return (
        <Plot
          height={height}
          layout={{ ...axisLayout(node.axes), showlegend: true, legend: { font: { size: 10 }, orientation: "h", y: 1.12 } }}
          data={node.series.map((s, i) => ({
            type: "scatter", mode: "lines", name: s.name, x: s.x, y: s.y,
            line: { color: palette[i % palette.length], width: 1.4 },
          } as Partial<Plotly.PlotData>))}
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

const GROUP_COLORS = ["#2ee6cf", "#4aa3ff", "#ff5cad", "#ffb454", "#9d7bff", "#54e08a"];
function groupColor(group?: string): string {
  if (!group) return "#4aa3ff";
  let h = 0;
  for (let i = 0; i < group.length; i++) h = (h * 31 + group.charCodeAt(i)) | 0;
  return GROUP_COLORS[Math.abs(h) % GROUP_COLORS.length];
}
