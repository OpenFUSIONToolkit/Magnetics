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
import { plotChrome } from "./colormaps";
import { useStore } from "../store";

export interface PlotProps {
  data: Partial<Plotly.PlotData>[];
  layout?: Partial<Plotly.Layout>;
  height?: number;
  onClick?: (e: Plotly.PlotMouseEvent) => void;
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

export default function Plot({ data, layout, height = 320, onClick }: PlotProps) {
  const ref = useRef<HTMLDivElement>(null);
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
  }, [data, layout, height, onClick, theme]);

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
