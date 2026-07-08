import { expect, test } from "vitest";
import { phiPeak, phiRms } from "./qsTransforms";

test("phiPeak picks the φ of the max |δBp| per time column", () => {
  // z[φ][t]: at t=0 the peak is row 0, at t=1 it's row 1.
  const z = [
    [1, 0],
    [0, 1],
  ];
  expect(phiPeak(z, [10, 20])).toEqual([10, 20]);
});

test("phiPeak uses the SIGNED argmax, not |δBp| (negative-dominant column)", () => {
  // z[φ][t]: column t=0 is all-negative — signed argmax picks the least-negative
  // (-1 at φ=20), whereas an |·| argmax would wrongly pick -5 at φ=10.
  const z = [
    [-5, 0],
    [-1, 0],
  ];
  expect(phiPeak(z, [10, 20])).toEqual([20, 10]);
});

test("phiRms computes RMS over φ per time column", () => {
  const z = [
    [3, 0],
    [4, 0],
  ];
  expect(phiRms(z)).toEqual([Math.sqrt((9 + 16) / 2), 0]);
});

test("empty / ragged input does not throw and returns []", () => {
  expect(phiPeak([], [])).toEqual([]);
  expect(phiRms([])).toEqual([]);
  expect(phiPeak([[1]], [])).toEqual([]); // no φ axis
});
