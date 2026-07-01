import { expect, test } from "vitest";
import { modeColor, MODE_PALETTE } from "./colormaps";

test("modeColor indexes the palette by |round(n)|, clamped", () => {
  expect(modeColor(0)).toBe(MODE_PALETTE[0]);
  expect(modeColor(2)).toBe(MODE_PALETTE[2]);
  expect(modeColor(-3)).toBe(MODE_PALETTE[3]); // absolute value
  expect(modeColor(2.4)).toBe(MODE_PALETTE[2]); // rounds down
  expect(modeColor(2.6)).toBe(MODE_PALETTE[3]); // rounds up
  expect(modeColor(99)).toBe(MODE_PALETTE[MODE_PALETTE.length - 1]); // clamped
});
