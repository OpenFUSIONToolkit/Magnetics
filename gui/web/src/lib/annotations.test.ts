import { expect, test } from "vitest";
import { annotationsToPlotly, parseAnnotations, type Annotation } from "./annotations";

const axisOf = { spec: "y", amplitude: "y2" };

test("vline and span are time-anchored and span the full figure height", () => {
  const list: Annotation[] = [
    { id: "a", kind: "vline", t: 1500, label: "LM onset", color: "#e0533d" },
    { id: "b", kind: "span", t0: 1600, t1: 1700 },
  ];
  const { shapes, annotations, traces } = annotationsToPlotly(list, axisOf, "#fff");
  expect(shapes[0]).toMatchObject({ type: "line", xref: "x", yref: "paper", x0: 1500, x1: 1500, y0: 0, y1: 1 });
  expect(shapes[0].line?.color).toBe("#e0533d");
  expect(shapes[1]).toMatchObject({ type: "rect", xref: "x", yref: "paper", x0: 1600, x1: 1700, layer: "below" });
  expect(annotations).toHaveLength(1); // only the labelled vline gets a text label
  expect(annotations[0]).toMatchObject({ x: 1500, text: "LM onset" });
  expect(traces).toHaveLength(0);
});

test("hline and point attach to their panel's y axis; hidden panels are skipped", () => {
  const list: Annotation[] = [
    { id: "a", kind: "hline", panel: "amplitude", y: 3.5, label: "threshold" },
    { id: "b", kind: "point", panel: "spec", t: 2000, y: 12.5 },
    { id: "c", kind: "point", panel: "phase", t: 2000, y: 0 }, // phase panel not shown
  ];
  const { shapes, annotations, traces } = annotationsToPlotly(list, axisOf, "#fff");
  expect(shapes).toHaveLength(1);
  expect(shapes[0]).toMatchObject({ xref: "paper", yref: "y2", y0: 3.5, y1: 3.5, x0: 0, x1: 1 });
  expect(annotations[0]).toMatchObject({ yref: "y2", text: "threshold" });
  expect(traces).toHaveLength(1);
  expect(traces[0]).toMatchObject({ xaxis: "x", yaxis: "y", x: [2000], y: [12.5], mode: "markers" });
});

test("parseAnnotations validates untrusted JSON", () => {
  const out = parseAnnotations([
    { id: "ok", kind: "vline", t: 1 },
    { kind: "span", t0: 5, t1: 2, color: "#123456" }, // reversed edges, no id
    { kind: "hline", panel: "nope", y: 1 },            // unknown panel
    { kind: "point", panel: "phase", t: 1 },           // missing y
    { kind: "vline", t: "1" },                         // wrong type
    { kind: "vline", t: 2, color: "red; x" },          // bad color dropped
    null, 7,
  ]);
  expect(out).toHaveLength(3);
  expect(out[0]).toEqual({ id: "ok", kind: "vline", t: 1 });
  expect(out[1]).toMatchObject({ kind: "span", t0: 2, t1: 5, color: "#123456" });
  expect(out[1].id).toBeTruthy();
  expect(out[2]).not.toHaveProperty("color");
  expect(parseAnnotations({ not: "an array" })).toEqual([]);
});
