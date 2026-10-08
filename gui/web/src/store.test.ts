import { afterEach, beforeEach, expect, test } from "vitest";
import { useStore, applyFontScale, FONT_SCALES } from "./store";

// The store module registers a window `storage` listener at import time so a theme
// change in one browser tab (localStorage write) mirrors into every other tab.
const THEME_KEY = "magnetics-theme";
const FONT_SCALE_KEY = "magnetics-font-scale";

beforeEach(() => {
  window.localStorage.clear();
  // reset to the default (Medium) preset between tests
  useStore.getState().setFontScale(FONT_SCALES.M);
});
afterEach(() => {
  window.localStorage.clear();
  useStore.setState({ theme: "dark" });
});

test("a theme storage event syncs the store + the <html> data-theme", () => {
  useStore.setState({ theme: "dark" });

  window.dispatchEvent(new StorageEvent("storage", { key: THEME_KEY, newValue: "light" }));
  expect(useStore.getState().theme).toBe("light");
  expect(document.documentElement.getAttribute("data-theme")).toBe("light");

  window.dispatchEvent(new StorageEvent("storage", { key: THEME_KEY, newValue: "dark" }));
  expect(useStore.getState().theme).toBe("dark");
  expect(document.documentElement.getAttribute("data-theme")).toBe("dark");
});

test("unrelated storage keys and junk values are ignored", () => {
  useStore.setState({ theme: "dark" });

  window.dispatchEvent(new StorageEvent("storage", { key: "some-other-key", newValue: "light" }));
  expect(useStore.getState().theme).toBe("dark");

  window.dispatchEvent(new StorageEvent("storage", { key: THEME_KEY, newValue: "purple" }));
  expect(useStore.getState().theme).toBe("dark");
});

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

test("annotations: add / update / remove per shot, persisted to localStorage", () => {
  const s = useStore.getState();
  s.setAnnotations("190000", []);
  s.addAnnotation("190000", { kind: "vline", t: 1500, label: "onset" });
  s.addAnnotation("190000", { kind: "hline", panel: "amplitude", y: 2 });
  let list = useStore.getState().annotations["190000"];
  expect(list).toHaveLength(2);
  expect(list[0].id).toBeTruthy();
  expect(JSON.parse(window.localStorage.getItem("magnetics-annotations")!)["190000"]).toHaveLength(2);

  useStore.getState().updateAnnotation("190000", list[0].id, { t: 1600 });
  list = useStore.getState().annotations["190000"];
  expect(list[0]).toMatchObject({ kind: "vline", t: 1600, label: "onset" });

  useStore.getState().removeAnnotation("190000", list[0].id);
  useStore.getState().removeAnnotation("190000", list[1].id);
  expect(useStore.getState().annotations["190000"]).toBeUndefined(); // empty list → key dropped
});
