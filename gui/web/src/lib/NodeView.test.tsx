import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";
import type { MetricsNode, Node } from "./contract";
import NodeView from "./NodeView";

// No global auto-cleanup is configured, so unmount between tests to keep the DOM
// isolated (otherwise one render's download link leaks into the next assertion).
afterEach(cleanup);

// Give NodeView a concrete download URL regardless of the (unset) backend env.
vi.mock("./api", () => ({
  nodeDownloadUrl: (m: string, id: string) => `http://x/api/node/${m}/${id}/download`,
}));

test("renders a placeholder (not undefined) for an unknown node kind", () => {
  // A kind outside the union would otherwise fall through the switch → the
  // component returns undefined → React throws → the whole app blanks.
  const bogus = { kind: "not-a-real-kind" } as unknown as Node;
  render(<NodeView node={bogus} />);
  expect(screen.getByText(/unsupported node kind/i)).toBeInTheDocument();
  expect(screen.getByText(/not-a-real-kind/)).toBeInTheDocument();
});

const metrics: MetricsNode = {
  kind: "metrics",
  title: "fit quality",
  fields: [{ label: "K", value: 12.3 }],
};

test("metrics panel shows a data-download link when a download descriptor is given", () => {
  render(<NodeView node={metrics} download={{ machine: "190000", nodeId: "fit_quality" }} />);
  const link = screen.getByRole("link", { name: /data/i });
  expect(link).toHaveAttribute("href", "http://x/api/node/190000/fit_quality/download");
  expect(link).toHaveAttribute("download");
});

test("metrics panel has no download link without a descriptor", () => {
  render(<NodeView node={metrics} />);
  expect(screen.queryByRole("link", { name: /data/i })).toBeNull();
});
