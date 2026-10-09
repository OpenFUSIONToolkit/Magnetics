// The global time axis shared by every time-series plot (plasma-signal strip, QS
// traces, rotating spectrogram/tracks, Compare). Plots read `timeRange` from the
// store and report user zoom/pan back through `timeRangeFromRelayout`.

/** The x-range change in a Plotly relayout event: a [t0, t1] range, `null` for an
 *  autorange reset (double-click), or `undefined` when the event doesn't touch x
 *  (a y-only zoom, a resize, …) and the shared range should stay as it is. */
export function timeRangeFromRelayout(e: Record<string, unknown>): [number, number] | null | undefined {
  if (e["xaxis.autorange"] === true) return null;
  if (e["xaxis.range[0]"] != null && e["xaxis.range[1]"] != null)
    return [Number(e["xaxis.range[0]"]), Number(e["xaxis.range[1]"])];
  if (Array.isArray(e["xaxis.range"])) {
    const [a, b] = e["xaxis.range"] as number[];
    return [Number(a), Number(b)];
  }
  return undefined;
}

/** Plotly x-axis props for the shared range: fixed when set, else autorange. */
export const sharedXAxis = (range: [number, number] | null) =>
  range ? { range, autorange: false } : { autorange: true };


/** A double-click handler that clears the shared range. Deferred one tick so it lands
 *  AFTER Plotly's own double-click relayout, which otherwise re-reports the range the
 *  plot was first drawn with (a stale zoom when the plot mounted while zoomed). */
export const resetTimeRangeOnDoubleClick = (setTimeRange: (r: null) => void) => () => {
  setTimeout(() => setTimeRange(null), 0);
};
