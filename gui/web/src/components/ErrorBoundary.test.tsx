import { fireEvent, render, screen } from "@testing-library/react";
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

test("Retry clears the error and recovers in place when the child stops throwing", () => {
  let shouldThrow = true;
  function Flaky(): React.ReactElement {
    if (shouldThrow) throw new Error("transient payload");
    return <div>recovered panel</div>;
  }
  render(
    <ErrorBoundary label="The test view">
      <Flaky />
    </ErrorBoundary>,
  );
  expect(screen.getByText(/failed to render/i)).toBeInTheDocument();

  // The underlying condition is fixed; Retry should re-render children in place.
  shouldThrow = false;
  fireEvent.click(screen.getByRole("button", { name: /retry/i }));
  expect(screen.getByText("recovered panel")).toBeInTheDocument();
  expect(screen.queryByText(/failed to render/i)).not.toBeInTheDocument();
});
