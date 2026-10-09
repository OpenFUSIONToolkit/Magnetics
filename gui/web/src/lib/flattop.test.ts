import { describe, expect, it } from "vitest";
import { withFlattopCut } from "./flattop";

describe("withFlattopCut", () => {
  it("adds the flag when on and strips a stale one when off", () => {
    expect(withFlattopCut({ fmin: 0 }, true)).toEqual({ fmin: 0, cut_flattop: 1 });
    expect(withFlattopCut({ fmin: 0, cut_flattop: 1 }, false)).toEqual({ fmin: 0 });
    expect(withFlattopCut({ ns: "1,2" }, false)).toEqual({ ns: "1,2" });
  });
});
