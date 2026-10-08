import { describe, expect, it } from "vitest";
import { sharedXAxis, timeRangeFromRelayout } from "./timeRange";

describe("timeRangeFromRelayout", () => {
  it("reads a zoom/pan range in either Plotly form", () => {
    expect(timeRangeFromRelayout({ "xaxis.range[0]": 1200, "xaxis.range[1]": 2400 })).toEqual([1200, 2400]);
    expect(timeRangeFromRelayout({ "xaxis.range": [10, 20] })).toEqual([10, 20]);
  });
  it("maps a double-click reset to null and ignores events that don't touch x", () => {
    expect(timeRangeFromRelayout({ "xaxis.autorange": true, "yaxis.autorange": true })).toBeNull();
    expect(timeRangeFromRelayout({ "yaxis.range[0]": 0, "yaxis.range[1]": 1 })).toBeUndefined();
    expect(timeRangeFromRelayout({ autosize: true })).toBeUndefined();
  });
});

describe("sharedXAxis", () => {
  it("fixes the range when set and autoranges otherwise", () => {
    expect(sharedXAxis([1, 2])).toEqual({ range: [1, 2], autorange: false });
    expect(sharedXAxis(null)).toEqual({ autorange: true });
  });
});
