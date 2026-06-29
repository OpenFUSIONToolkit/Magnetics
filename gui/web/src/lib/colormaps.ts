// Shared visual vocabulary: fonts, the diverging field colorscale, and the
// discrete toroidal-mode-number palette. Kept in one place so every plot in the
// app reads consistently (a clean, scientific look).

export const FONT = { family: "IBM Plex Mono, ui-monospace, monospace", size: 11, color: "#c8d4e0" };

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

// Discrete palette for toroidal mode number n = −6 … +6 (13 bins).
// Index with (n + 6).
export const MODE_PALETTE = [
  "#5e4fa2", "#3288bd", "#66c2a5", "#abdda4", "#e6f598", "#ffffbf",
  "#fee08b", "#fdae61", "#f46d43", "#d53e4f", "#9e0142", "#7a0028", "#4d0019",
];

export function modeColor(n: number): string {
  const i = Math.max(0, Math.min(MODE_PALETTE.length - 1, Math.round(n) + 6));
  return MODE_PALETTE[i];
}
