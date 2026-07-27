// Bad-channel exclusions (#56) — the store half.
//
// The server owns the exclusion set; the store mirrors it for the Sensors view
// and bumps `excludedRev` so every open view re-fits. The parts worth pinning:
// the optimistic update greys the sensor immediately, and a FAILED save rolls
// back — a map showing an exclusion the analyses aren't honoring is a lie.
import { beforeEach, describe, expect, it, vi } from "vitest";

const fetchExclusions = vi.fn();
const saveExclusions = vi.fn();
vi.mock("./api", () => ({
  fetchExclusions: (...a: unknown[]) => fetchExclusions(...a),
  saveExclusions: (...a: unknown[]) => saveExclusions(...a),
  // the store imports these at module load; never called in these tests
  fetchMachines: vi.fn().mockResolvedValue([]),
  fetchDevices: vi.fn().mockResolvedValue([]),
  deleteMachine: vi.fn(),
  deleteAllMachines: vi.fn(),
}));

import { useStore } from "../store";

beforeEach(() => {
  fetchExclusions.mockReset();
  saveExclusions.mockReset();
  useStore.setState({ excluded: [], excludedRev: 0 });
});

describe("loadExclusions", () => {
  it("mirrors the server's list for the shot", async () => {
    fetchExclusions.mockResolvedValueOnce(["A", "B"]);
    await useStore.getState().loadExclusions("184927");
    expect(fetchExclusions).toHaveBeenCalledWith("184927");
    expect(useStore.getState().excluded).toEqual(["A", "B"]);
  });

  it("degrades to empty with no live backend", async () => {
    fetchExclusions.mockRejectedValueOnce(new Error("no backend"));
    await useStore.getState().loadExclusions("1");
    expect(useStore.getState().excluded).toEqual([]);
  });
});

describe("toggleExcluded", () => {
  it("adds a channel and persists it", async () => {
    saveExclusions.mockResolvedValueOnce(["A"]);
    await useStore.getState().toggleExcluded("1", "A");
    expect(saveExclusions).toHaveBeenCalledWith("1", ["A"]);
    expect(useStore.getState().excluded).toEqual(["A"]);
  });

  it("removes an already-excluded channel (click to restore)", async () => {
    useStore.setState({ excluded: ["A", "B"] });
    saveExclusions.mockResolvedValueOnce(["B"]);
    await useStore.getState().toggleExcluded("1", "A");
    expect(saveExclusions).toHaveBeenCalledWith("1", ["B"]);
    expect(useStore.getState().excluded).toEqual(["B"]);
  });

  it("adopts the server's canonical (sorted) list", async () => {
    useStore.setState({ excluded: ["Z"] });
    saveExclusions.mockResolvedValueOnce(["A", "Z"]); // server sorts
    await useStore.getState().toggleExcluded("1", "A");
    expect(useStore.getState().excluded).toEqual(["A", "Z"]);
  });

  it("rolls back when the save fails", async () => {
    useStore.setState({ excluded: ["A"] });
    saveExclusions.mockRejectedValueOnce(new Error("500"));
    await useStore.getState().toggleExcluded("1", "B");
    // never leave the map claiming an exclusion the analyses don't have
    expect(useStore.getState().excluded).toEqual(["A"]);
  });

  it("bumps excludedRev so every open view re-fits", async () => {
    saveExclusions.mockResolvedValueOnce(["A"]);
    const before = useStore.getState().excludedRev;
    await useStore.getState().toggleExcluded("1", "A");
    expect(useStore.getState().excludedRev).toBeGreaterThan(before);
  });
});

describe("clearExclusions", () => {
  it("restores everything in one call", async () => {
    useStore.setState({ excluded: ["A", "B"] });
    saveExclusions.mockResolvedValueOnce([]);
    await useStore.getState().clearExclusions("1");
    expect(saveExclusions).toHaveBeenCalledWith("1", []);
    expect(useStore.getState().excluded).toEqual([]);
  });

  it("rolls back a failed clear", async () => {
    useStore.setState({ excluded: ["A", "B"] });
    saveExclusions.mockRejectedValueOnce(new Error("500"));
    await useStore.getState().clearExclusions("1");
    expect(useStore.getState().excluded).toEqual(["A", "B"]);
  });
});
