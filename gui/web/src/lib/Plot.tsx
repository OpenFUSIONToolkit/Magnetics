// Thin imperative wrapper over Plotly. Every plot in the app goes through this
// one component, so theming and lifecycle (resize, cleanup) live in exactly one
// place. Build your traces + layout, hand them here. See <NodeView> for the
// generic kind→trace mapping.
//
// Plotly's imperative API can throw transiently when react/purge race (concurrent
// plots, fast re-renders) — the `_redrawFromAutoMarginCount` crash. We guard every
// Plotly call so a transient throw can never blank the React tree.
import { type CSSProperties, useEffect, useRef, useState } from "react";
import Plotly from "plotly.js-dist-min";
import { plotChrome } from "./colormaps";
import { nodeDownloadUrl } from "./api";
import { useStore } from "../store";

export interface PlotProps {
  data: Partial<Plotly.PlotData>[];
  layout?: Partial<Plotly.Layout>;
  height?: number;
  onClick?: (e: Plotly.PlotMouseEvent) => void;
  onRelayout?: (e: Record<string, unknown>) => void;
  /** Per-plot Plotly config overrides (e.g. scrollZoom, displayModeBar). */
  config?: Partial<Plotly.Config>;
  /** Base filename for the PNG/SVG image exports (e.g. "shot_190000_amplitude");
   *  defaults to "plot". */
  exportName?: string;
  /** When set, the toolbar shows a "Data" button that downloads this node's arrays
   *  as HDF5 from /api/node/.../download. Omit for client-derived plots (image only). */
  download?: { machine: string; nodeId: string; params?: Record<string, string | number> };
}

function baseLayout(theme: "dark" | "light"): Partial<Plotly.Layout> {
  const c = plotChrome(theme);
  const axis = {
    gridcolor: c.gridcolor,
    zerolinecolor: c.zerolinecolor,
    linecolor: c.linecolor,
    ticks: "outside" as const,
    tickcolor: c.tickcolor,
  };
  return {
    paper_bgcolor: c.paper_bgcolor,
    plot_bgcolor: c.plot_bgcolor,
    font: c.font,
    margin: { l: 60, r: 20, t: 16, b: 48 },
    showlegend: false,
    xaxis: axis,
    yaxis: axis,
  };
}

export default function Plot({
  data, layout, height = 320, onClick, onRelayout, config, exportName, download,
}: PlotProps) {
  const ref = useRef<HTMLDivElement>(null);
  const [hover, setHover] = useState(false);
  const theme = useStore((s) => s.theme);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const base = baseLayout(theme);
    const merged: Partial<Plotly.Layout> = {
      ...base,
      ...layout,
      height,
      xaxis: { ...base.xaxis, ...(layout?.xaxis as object) },
      yaxis: { ...base.yaxis, ...(layout?.yaxis as object) },
    };
    try {
      Plotly.react(el, data as Plotly.Data[], merged, { displayModeBar: false, responsive: true, ...config });
      const clickHandler = (e: Plotly.PlotMouseEvent) => onClick?.(e);
      const relayoutHandler = (e: Record<string, unknown>) => onRelayout?.(e);
      // @ts-expect-error plotly event typing is loose on the dist build
      if (onClick) el.on("plotly_click", clickHandler);
      // @ts-expect-error plotly event typing is loose on the dist build
      if (onRelayout) el.on("plotly_relayout", relayoutHandler);
    } catch {
      /* transient Plotly layout race (e.g. StrictMode remount); next render re-syncs */
    }
    return () => {
      try {
        // @ts-expect-error plotly cleanup helper is untyped on the dist build
        el.removeAllListeners?.("plotly_click");
        // @ts-expect-error plotly cleanup helper is untyped on the dist build
        el.removeAllListeners?.("plotly_relayout");
      } catch {
        /* noop */
      }
    };
  }, [data, layout, height, onClick, onRelayout, theme, config]);

  useEffect(() => {
    const el = ref.current;
    return () => {
      try {
        if (el) Plotly.purge(el);
      } catch {
        /* noop */
      }
    };
  }, []);

  // Save the current figure as an image. Plotly.downloadImage handles the file
  // download itself; PNG is rasterized at 2× for crisp screenshots, SVG is vector
  // (opens/prints to PDF from any viewer).
  const saveImage = (format: "png" | "svg") => {
    const el = ref.current;
    if (!el) return;
    // PNG is raster: render at 2× for a crisp screenshot. SVG is vector, so native
    // size is exact (opens/prints to PDF from any viewer at any scale).
    const w = el.clientWidth || 800;
    const mul = format === "png" ? 2 : 1;
    void Plotly.downloadImage(el, {
      format,
      filename: exportName || "plot",
      width: w * mul,
      height: height * mul,
    }).catch(() => {
      /* transient (plot not fully drawn); user can retry */
    });
  };

  const dataUrl = download ? nodeDownloadUrl(download.machine, download.nodeId, download.params) : null;

  return (
    <div
      style={{ position: "relative", height, width: "100%" }}
      onMouseEnter={() => setHover(true)}
      onMouseLeave={() => setHover(false)}
    >
      <div ref={ref} style={{ height, width: "100%" }} />
      <div
        style={{
          position: "absolute", top: 2, right: 6, display: "flex", gap: 3, zIndex: 5,
          opacity: hover ? 1 : 0, transition: "opacity 0.15s",
          pointerEvents: hover ? "auto" : "none",
        }}
      >
        <button type="button" title="Save as PNG" style={TOOLBTN} onClick={() => saveImage("png")}>PNG</button>
        <button type="button" title="Save as SVG (vector)" style={TOOLBTN} onClick={() => saveImage("svg")}>SVG</button>
        {dataUrl && (
          <a title="Download this plot's data as HDF5" style={TOOLBTN} href={dataUrl} download>Data</a>
        )}
      </div>
    </div>
  );
}

// Small toolbar button/link, styled to match the app chrome (CSS vars) and stay
// unobtrusive until the plot is hovered.
const TOOLBTN: CSSProperties = {
  fontSize: 10,
  lineHeight: 1.4,
  padding: "1px 6px",
  borderRadius: 3,
  cursor: "pointer",
  background: "var(--panel)",
  color: "var(--text-dim)",
  border: "1px solid var(--border)",
  textDecoration: "none",
};
