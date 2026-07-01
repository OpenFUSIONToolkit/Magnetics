import { afterEach, expect, test, vi } from "vitest";
import { getJSON, nodeDownloadUrl, qs } from "./api";

afterEach(() => vi.restoreAllMocks());

function mockFetch(status: number, body: unknown, ok = status < 400) {
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => ({
      ok,
      status,
      json: async () => body,
    })),
  );
}

test("qs serializes params, returns '' when absent", () => {
  expect(qs({ time: 3140, fmin: 0 })).toBe("?time=3140&fmin=0");
  expect(qs(undefined)).toBe("");
  expect(qs({})).toBe("");
});

test("getJSON returns the parsed body on 200", async () => {
  mockFetch(200, { kind: "line" });
  await expect(getJSON("/x")).resolves.toEqual({ kind: "line" });
});

test("getJSON surfaces the FastAPI detail + status on error", async () => {
  mockFetch(404, { detail: "shot not fetched" });
  await expect(getJSON("/x")).rejects.toThrow(/fetch failed \(404\).*shot not fetched/);
});

test("getJSON keeps the 422 reason (the QS banners depend on this)", async () => {
  mockFetch(422, { detail: "no valid channels" });
  await expect(getJSON("/x")).rejects.toThrow(/fetch failed \(422\).*no valid channels/);
});

test("nodeDownloadUrl returns null without a live backend (mock fixtures can't export)", () => {
  // VITE_API_BASE is unset in the test env, so there is no serializer to hit.
  expect(nodeDownloadUrl("190000", "amplitude", { time: 3140 })).toBeNull();
});
