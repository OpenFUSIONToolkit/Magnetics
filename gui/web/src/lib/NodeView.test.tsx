import { render, screen } from "@testing-library/react";
import { expect, test } from "vitest";
import type { Node } from "./contract";
import NodeView from "./NodeView";

test("renders a placeholder (not undefined) for an unknown node kind", () => {
  // A kind outside the union would otherwise fall through the switch → the
  // component returns undefined → React throws → the whole app blanks.
  const bogus = { kind: "not-a-real-kind" } as unknown as Node;
  render(<NodeView node={bogus} />);
  expect(screen.getByText(/unsupported node kind/i)).toBeInTheDocument();
  expect(screen.getByText(/not-a-real-kind/)).toBeInTheDocument();
});
