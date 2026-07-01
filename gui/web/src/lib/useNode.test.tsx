import { renderHook, waitFor } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";
import type { Node } from "./contract";

// Mock the fetch layer useNode depends on.
const fetchNode = vi.fn();
vi.mock("./api", () => ({ fetchNode: (...a: unknown[]) => fetchNode(...a) }));

import { useNode } from "./useNode";

afterEach(() => {
  fetchNode.mockReset();
});

const lineNode = (name: string): Node =>
  ({ kind: "line", series: [{ name, x: [], y: [] }], axes: { x: "", y: "" } }) as Node;

test("resolves a node and clears loading", async () => {
  fetchNode.mockResolvedValueOnce(lineNode("A"));
  const { result } = renderHook(() => useNode("m1", "spectrogram"));
  expect(result.current.loading).toBe(true);
  await waitFor(() => expect(result.current.loading).toBe(false));
  expect(result.current.node).toEqual(lineNode("A"));
  expect(result.current.error).toBeNull();
});

test("keeps the stale node while a param change refetches", async () => {
  fetchNode.mockResolvedValueOnce(lineNode("A"));
  const { result, rerender } = renderHook(({ p }) => useNode("m1", "spectrogram", p), {
    initialProps: { p: { t: 1 } as Record<string, number> },
  });
  await waitFor(() => expect(result.current.node).toEqual(lineNode("A")));

  // Change params → new key. Fetch is pending; the hook must keep returning A.
  let resolveB: (n: Node) => void = () => {};
  fetchNode.mockReturnValueOnce(new Promise<Node>((r) => (resolveB = r)));
  rerender({ p: { t: 2 } });
  expect(result.current.node).toEqual(lineNode("A")); // stale kept, no blank

  resolveB(lineNode("B"));
  await waitFor(() => expect(result.current.node).toEqual(lineNode("B")));
});

test("surfaces an error for the current key", async () => {
  fetchNode.mockRejectedValueOnce(new Error("fetch failed (422): no array"));
  const { result } = renderHook(() => useNode("m1", "qs_fit"));
  await waitFor(() => expect(result.current.error).toMatch(/422/));
  expect(result.current.node).toBeNull();
});

test("does not fetch when machine is null", () => {
  renderHook(() => useNode(null, "spectrogram"));
  expect(fetchNode).not.toHaveBeenCalled();
});
