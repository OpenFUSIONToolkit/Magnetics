import { describe, expect, it } from "vitest";
import { displayScale, signalAxisTitle } from "./signalUnits";

describe("displayScale", () => {
  it("shows plasma current in MA and coil currents in kA", () => {
    expect(displayScale("A", [0, 9.8e5, -1e3])).toEqual({ factor: 1e-6, unit: "MA" });
    expect(displayScale("A", [-1100, 2264])).toEqual({ factor: 1e-3, unit: "kA" });
    expect(displayScale("A", [3, 8])).toEqual({ factor: 1, unit: "A" });
  });

  it("shows small fields in gauss but keeps Bt in tesla", () => {
    expect(displayScale("T", [-0.0413, 0.0407])).toEqual({ factor: 1e4, unit: "G" });
    expect(displayScale("T", [-2.0, -1.9])).toEqual({ factor: 1, unit: "T" });
  });

  it("leaves dimensionless and unknown units alone, ignoring NaN", () => {
    expect(displayScale("", [1.7, NaN])).toEqual({ factor: 1, unit: "" });
    expect(displayScale(undefined, [5])).toEqual({ factor: 1, unit: "" });
    expect(displayScale("T/s", [12])).toEqual({ factor: 1, unit: "T/s" });
  });
});

describe("signalAxisTitle", () => {
  it("appends the unit only when there is one", () => {
    expect(signalAxisTitle("ip", { factor: 1e-6, unit: "MA" })).toBe("ip (MA)");
    expect(signalAxisTitle("kappa", { factor: 1, unit: "" })).toBe("kappa");
  });
});
