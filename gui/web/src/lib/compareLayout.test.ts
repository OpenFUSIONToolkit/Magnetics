import { describe, expect, it, test } from "vitest";
import {
  axisId, buildCompareFigure, movePanel, orderPanels, panelDomains, panelForAxis, timeExtents, type PanelSpec,
} from "./compareLayout";
import { PLOT_CHROME } from "./colormaps";

const chrome = PLOT_CHROME.dark;
const line = (x: number[]) => ({ type: "scatter" as const, x, y: x.map(() => 0), name: "1" });
const heat = (x: number[]) => ({ type: "heatmap" as const, x, y: [0, 1], z: [x, x], colorbar: { thickness: 12 } });

test("panelDomains stacks top → bottom, sized by weight, with gaps, within [0, 1]", () => {
  for (const n of [1, 2, 3, 4, 5]) {
    const d = panelDomains(Array(n).fill(1), 0.05);
    expect(d).toHaveLength(n);
    expect(d[0][1]).toBe(1);
    expect(d[n - 1][0]).toBeCloseTo(0, 6);
    for (let i = 1; i < n; i++) expect(d[i - 1][0] - d[i][1]).toBeCloseTo(0.05, 6); // gap
  }
  const [a, b] = panelDomains([2, 1], 0);
  expect(a[1] - a[0]).toBeCloseTo(2 * (b[1] - b[0]), 5);
  expect(panelDomains([])).toEqual([]);
});

test("timeExtents: union and overlap of the series' time ranges", () => {
  expect(timeExtents([[0, 5, 10], [4, 20], undefined, []])).toEqual({ union: [0, 20], overlap: [4, 10] });
  expect(timeExtents([[0, 1], [2, 3]]).overlap).toBeNull(); // disjoint
  expect(timeExtents([])).toEqual({ union: null, overlap: null });
});

test("buildCompareFigure puts every panel on one shared x axis with its own y axis", () => {
  const panels: PanelSpec[] = [
    { id: "spec", traces: [heat([0, 10])], yaxis: { title: { text: "f" } }, weight: 2 },
    { id: "amplitude", traces: [line([5, 15])], yaxis: {}, legend: "n" },
    { id: "phase", traces: [line([5, 15])], yaxis: { range: [-180, 180] } },
  ];
  const fig = buildCompareFigure(panels, { chrome, xTitle: "time (ms)", xRange: [2, 8] });
  expect(fig.axisOf).toEqual({ spec: "y", amplitude: "y2", phase: "y3" });
  expect(fig.data.map((t) => [t.xaxis, t.yaxis])).toEqual([["x", "y"], ["x", "y2"], ["x", "y3"]]);
  const L = fig.layout as Record<string, { domain?: number[]; anchor?: string; range?: number[] }>;
  expect(L.yaxis.anchor).toBe("x");
  expect(L.yaxis3.range).toEqual([-180, 180]);
  // x axis hangs off the bottom panel, carries the shared range
  expect(L.xaxis.anchor).toBe("y3");
  expect(L.xaxis.range).toEqual([2, 8]);
  // heatmap colorbar is confined to its own panel's domain
  const cb = (fig.data[0] as { colorbar: { y: number; len: number; thickness: number } }).colorbar;
  const [lo, hi] = L.yaxis.domain!;
  expect(cb.y).toBeCloseTo((lo + hi) / 2, 6);
  expect(cb.len).toBeCloseTo(hi - lo, 6);
  expect(cb.thickness).toBe(12);
  // only the legend panel contributes legend entries
  expect(fig.layout.showlegend).toBe(true);
  expect(fig.data[2].showlegend).toBe(false);
  expect(fig.data[1].showlegend).toBeUndefined();
});

test("no xRange → autorange; panelForAxis maps a clicked trace's y axis back to its panel", () => {
  const fig = buildCompareFigure(
    [{ id: "phi_t", traces: [line([0, 1])], yaxis: {} }, { id: "phase", traces: [line([0, 1])], yaxis: {} }],
    { chrome, xTitle: "t" },
  );
  expect((fig.layout.xaxis as { autorange?: boolean }).autorange).toBe(true);
  expect(panelForAxis(fig.axisOf, axisId(1))).toBe("phase");
  expect(panelForAxis(fig.axisOf, undefined)).toBe("phi_t");
  expect(panelForAxis(fig.axisOf, "y9")).toBeNull();
});

describe("panel reordering", () => {
  it("sorts by the saved order, unknown panels after in default order", () => {
    expect(orderPanels(["a", "b", "c", "d"], ["c", "a"])).toEqual(["c", "a", "b", "d"]);
    expect(orderPanels(["a", "b"], [])).toEqual(["a", "b"]);
  });
  it("moves a panel and keeps hidden panels' saved slots", () => {
    const order = movePanel(["a", "b", "c"], ["x", "a"], "c", 0);
    expect(order).toEqual(["c", "a", "b", "x"]);
    expect(orderPanels(["a", "b", "c", "x"], order)).toEqual(["c", "a", "b", "x"]);
    expect(movePanel(["a", "b", "c"], [], "a", 99)).toEqual(["b", "c", "a"]);
    expect(movePanel(["a"], ["a"], "zz", 0)).toEqual(["a"]);
  });
});
