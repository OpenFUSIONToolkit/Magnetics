// Thin imperative wrapper over Plotly. Every plot in the app goes through this
// one component, so theming and lifecycle (resize, cleanup) live in exactly one
// place. Build your traces + layout, hand them here. See <NodeView> for the
// generic kind→trace mapping.
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
    if (!ref.current) return;
    const merged: Partial<Plotly.Layout> = {
      ...BASE_LAYOUT,
      ...layout,
      height,
      xaxis: { ...BASE_LAYOUT.xaxis, ...(layout?.xaxis as object) },
      yaxis: { ...BASE_LAYOUT.yaxis, ...(layout?.yaxis as object) },
    };
    Plotly.react(ref.current, data as Plotly.Data[], merged, {
      displayModeBar: false,
      responsive: true,
    });
    const el = ref.current;
    const handler = (e: Plotly.PlotMouseEvent) => onClick?.(e);
    // @ts-expect-error plotly event typing is loose on the dist build
    if (onClick) el.on("plotly_click", handler);
    return () => {
      // @ts-expect-error plotly cleanup helper is untyped on the dist build
      el.removeAllListeners?.("plotly_click");
    };
  }, [data, layout, height, onClick]);

  useEffect(() => {
    const el = ref.current;
    return () => { if (el) Plotly.purge(el); };
  }, []);

  return <div ref={ref} style={{ height, width: "100%" }} />;
}
