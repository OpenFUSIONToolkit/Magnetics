import { render, screen } from "@testing-library/react";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import ErrorBoundary from "./ErrorBoundary";

function Boom(): React.ReactElement {
  throw new Error("kaboom");
}

// React logs caught render errors to console.error; silence the expected noise.
beforeEach(() => vi.spyOn(console, "error").mockImplementation(() => {}));
afterEach(() => vi.restoreAllMocks());

test("renders a fallback (not a blank tree) when a child throws", () => {
  render(
    <ErrorBoundary label="The test view">
      <Boom />
    </ErrorBoundary>,
  );
  expect(screen.getByText(/failed to render/i)).toBeInTheDocument();
  expect(screen.getByText(/kaboom/)).toBeInTheDocument();
});

test("renders children unchanged when nothing throws", () => {
  render(
    <ErrorBoundary>
      <div>healthy panel</div>
    </ErrorBoundary>,
  );
  expect(screen.getByText("healthy panel")).toBeInTheDocument();
});
