// Shared visual vocabulary: fonts, the diverging field colorscale, and the
// discrete toroidal-mode-number palette. Kept in one place so every plot in the
// app reads consistently (a clean, scientific look).

// Per-theme Plotly chrome (paper/plot background, axes, font). One source of
// truth so the shared <Plot> wrapper and every hand-built layout agree. The
// light values match a clean engineering-paper look; the dark values match the
// console aesthetic of the rest of the app.
export interface PlotChrome {
  paper_bgcolor: string;
  plot_bgcolor: string;
  gridcolor: string;
  zerolinecolor: string;
  linecolor: string;
  tickcolor: string;
  font: { family: string; size: number; color: string };
}

const MONO = "IBM Plex Mono, ui-monospace, monospace";

export const PLOT_CHROME: Record<"dark" | "light", PlotChrome> = {
  dark: {
    paper_bgcolor: "rgba(0,0,0,0)",
    plot_bgcolor: "#0a0f16",
    gridcolor: "#16202d",
    zerolinecolor: "#24323f",
    linecolor: "#24323f",
    tickcolor: "#24323f",
    font: { family: MONO, size: 11, color: "#c8d4e0" },
  },
  light: {
    paper_bgcolor: "rgba(0,0,0,0)",
    plot_bgcolor: "#f8fafc",
    gridcolor: "#e2e8f0",
    zerolinecolor: "#94a3b8",
    linecolor: "#94a3b8",
    tickcolor: "#94a3b8",
    font: { family: MONO, size: 11, color: "#1a2332" },
  },
};

export function plotChrome(theme: "dark" | "light"): PlotChrome {
  return PLOT_CHROME[theme];
}

// Diverging blue → white → red for signed field (δB). Plotly colorscale form.
export const FIELD_DIVERGING: [number, string][] = [
  [0.0, "#2166ac"],
  [0.25, "#67a9cf"],
  [0.5, "#f7f7f7"],
  [0.75, "#ef8a62"],
  [1.0, "#b2182b"],
];

// Sequential for log power (dark → bright), good on a dark background.
export const POWER_SEQUENTIAL: [number, string][] = [
  [0.0, "#0b1020"],
  [0.4, "#23406e"],
  [0.7, "#2e9fae"],
  [0.9, "#a7d94c"],
  [1.0, "#fff7b0"],
];

// Discrete palette for toroidal mode-number magnitude |n| = 0 … 6 (7 bins).
// Folding the sign to |n| halves the categories, so the hues stay well-separated
// (rotation direction lives in the signed phase fit, not this map). Index with |n|.
export const MODE_PALETTE = [
  "#6b7785", // 0 — slate grey (no coherent mode)
  "#4c9be8", // 1 — blue
  "#3fb56b", // 2 — green
  "#e8c84a", // 3 — gold
  "#f08a3c", // 4 — orange
  "#e0533d", // 5 — red
  "#a86bd1", // 6 — purple
];

export function modeColor(n: number): string {
  const i = Math.max(0, Math.min(MODE_PALETTE.length - 1, Math.round(Math.abs(n))));
  return MODE_PALETTE[i];
}
