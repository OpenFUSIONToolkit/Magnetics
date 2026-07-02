import { expect, test } from "vitest";
import { gatePosToPct, medianStep, percentile } from "./rotatingTransforms";

test("percentile: endpoints and linear interpolation", () => {
  expect(percentile([10, 20, 30, 40], 0)).toBe(10);
  expect(percentile([10, 20, 30, 40], 100)).toBe(40);
  // p=50 over 4 elements → idx 1.5 → halfway between 20 and 30.
  expect(percentile([10, 20, 30, 40], 50)).toBe(25);
});

test("percentile: empty array → -Infinity", () => {
  expect(percentile([], 50)).toBe(-Infinity);
});

test("percentile sorts its input in place (documented contract)", () => {
  const arr = [3, 1, 2];
  percentile(arr, 50);
  expect(arr).toEqual([1, 2, 3]);
});

test("medianStep: median cell width of a monotone axis", () => {
  expect(medianStep([0, 2, 4, 6])).toBe(2); // uniform 2-unit grid
  // sorted diffs [1, 1, 4] → odd count → median 1
  expect(medianStep([0, 1, 2, 6])).toBe(1);
  // even count of diffs → mean of the two middle values: diffs [2,2,10,10] → 6
  expect(medianStep([0, 2, 4, 14, 24])).toBe(6);
});

test("medianStep: degenerate axis → NaN", () => {
  expect(medianStep(undefined)).toBeNaN();
  expect(medianStep([5])).toBeNaN();
});

test("gatePosToPct: monotonic, clamped, log-headroom mapping", () => {
  expect(gatePosToPct(0)).toBeCloseTo(0, 5); // headroom 100 → 0th percentile
  expect(gatePosToPct(1000)).toBeCloseTo(99.5, 1); // headroom 0.5 → 99.5th
  expect(gatePosToPct(-50)).toBeCloseTo(0, 5); // clamped below
  expect(gatePosToPct(5000)).toBeCloseTo(99.5, 1); // clamped above
  expect(gatePosToPct(500)).toBeGreaterThan(gatePosToPct(100)); // monotonic
});
