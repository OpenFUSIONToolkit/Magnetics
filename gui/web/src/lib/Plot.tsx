// Thin imperative wrapper over Plotly. Every plot in the app goes through this
// one component, so theming and lifecycle (resize, cleanup) live in exactly one
// place. Build your traces + layout, hand them here. See <NodeView> for the
// generic kind→trace mapping.
//
// Plotly's imperative API can throw transiently when react/purge race (concurrent
// plots, fast re-renders) — the `_redrawFromAutoMarginCount` crash. We guard every
// Plotly call so a transient throw can never blank the React tree.
import { useEffect, useRef } from "react";
import Plotly from "plotly.js-dist-min";
import { FONT } from "./colormaps";

export interface PlotProps {
  data: Partial<Plotly.PlotData>[];
  layout?: Partial<Plotly.Layout>;
  height?: number;
  onClick?: (e: Plotly.PlotMouseEvent) => void;
}

const BASE_LAYOUT: Partial<Plotly.Layout> = {
  paper_bgcolor: "rgba(0,0,0,0)",
  plot_bgcolor: "#0a0f16",
  font: FONT,
  margin: { l: 60, r: 20, t: 16, b: 48 },
  showlegend: false,
  xaxis: { gridcolor: "#16202d", zerolinecolor: "#24323f", linecolor: "#24323f", ticks: "outside", tickcolor: "#24323f" },
  yaxis: { gridcolor: "#16202d", zerolinecolor: "#24323f", linecolor: "#24323f", ticks: "outside", tickcolor: "#24323f" },
};

export default function Plot({ data, layout, height = 320, onClick }: PlotProps) {
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const merged: Partial<Plotly.Layout> = {
      ...BASE_LAYOUT,
      ...layout,
      height,
      xaxis: { ...BASE_LAYOUT.xaxis, ...(layout?.xaxis as object) },
      yaxis: { ...BASE_LAYOUT.yaxis, ...(layout?.yaxis as object) },
    };
    try {
      Plotly.react(el, data as Plotly.Data[], merged, { displayModeBar: false, responsive: true });
      const handler = (e: Plotly.PlotMouseEvent) => onClick?.(e);
      // @ts-expect-error plotly event typing is loose on the dist build
      if (onClick) el.on("plotly_click", handler);
    } catch {
      /* transient Plotly layout race (e.g. StrictMode remount); next render re-syncs */
    }
    return () => {
      try {
        // @ts-expect-error plotly cleanup helper is untyped on the dist build
        el.removeAllListeners?.("plotly_click");
      } catch {
        /* noop */
      }
    };
  }, [data, layout, height, onClick]);

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

  return <div ref={ref} style={{ height, width: "100%" }} />;
}
