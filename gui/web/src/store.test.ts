import { afterEach, beforeEach, expect, test } from "vitest";
import { useStore, applyFontScale, FONT_SCALES } from "./store";

const FONT_SCALE_KEY = "magnetics-font-scale";

beforeEach(() => {
  window.localStorage.clear();
  // reset to the default (Medium) preset between tests
  useStore.getState().setFontScale(FONT_SCALES.M);
});
afterEach(() => window.localStorage.clear());

test("applyFontScale writes the --font-scale custom property on <html>", () => {
  applyFontScale(FONT_SCALES.XL);
  expect(document.documentElement.style.getPropertyValue("--font-scale")).toBe(String(FONT_SCALES.XL));
});

test("setFontScale persists the preset name and applies the multiplier", () => {
  useStore.getState().setFontScale(FONT_SCALES.L);

  expect(useStore.getState().fontScale).toBe(FONT_SCALES.L);
  // persisted by preset key, not the raw number, so unknown values fall back cleanly
  expect(window.localStorage.getItem(FONT_SCALE_KEY)).toBe("L");
  expect(document.documentElement.style.getPropertyValue("--font-scale")).toBe(String(FONT_SCALES.L));
});

test("the store's default font scale is the Medium preset", () => {
  // no font-scale saved in a fresh environment → Medium
  expect(useStore.getState().fontScale).toBe(FONT_SCALES.M);
});

test("the presets are evenly spaced from S up to a boosted XL", () => {
  const { S, M, L, XL } = FONT_SCALES;
  expect(S).toBe(0.85); // small kept as-is
  expect(XL).toBeGreaterThan(1.3); // XL boosted beyond the old top
  // equal steps S→M→L→XL
  expect(M - S).toBeCloseTo(L - M);
  expect(L - M).toBeCloseTo(XL - L);
});
