import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";
import App from "./App";
import { useStore } from "./store";

afterEach(() => {
  vi.unstubAllGlobals();
  useStore.setState({
    machines: [],
    machine: null,
    tab: "sensors",
    cursorMs: 0,
    loadingMachines: true,
    theme: "dark",
  });
});

test("the shell does not advertise an unwired quality rail", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => ({
      ok: true,
      json: async () => [],
    })),
  );

  render(<App />);

  await waitFor(() => expect(screen.queryByText("loading…")).not.toBeInTheDocument());
  expect(document.querySelector(".rail-right")).toBeNull();
  expect(screen.queryByRole("heading", { name: /^quality$/i })).not.toBeInTheDocument();
  expect(screen.queryByText(/Condition number K/i)).not.toBeInTheDocument();
});
