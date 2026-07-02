import { render, screen, fireEvent, cleanup } from "@testing-library/react";
import { afterEach, beforeEach, expect, test } from "vitest";
import SettingsMenu from "./SettingsMenu";
import { useStore, FONT_SCALES } from "../store";

beforeEach(() => {
  window.localStorage.clear();
  useStore.getState().setFontScale(FONT_SCALES.M);
});
afterEach(() => {
  cleanup(); // no global auto-cleanup (vitest globals off) → unmount between tests
  window.localStorage.clear();
});

test("the popover is closed until the gear is clicked", () => {
  render(<SettingsMenu />);
  expect(screen.queryByText("Appearance")).not.toBeInTheDocument();

  fireEvent.click(screen.getByRole("button", { name: /settings/i }));
  expect(screen.getByText("Appearance")).toBeInTheDocument();
});

test("Escape closes the open popover", () => {
  render(<SettingsMenu />);
  fireEvent.click(screen.getByRole("button", { name: /settings/i }));
  expect(screen.getByText("Appearance")).toBeInTheDocument();

  fireEvent.keyDown(document, { key: "Escape" });
  expect(screen.queryByText("Appearance")).not.toBeInTheDocument();
});

test("clicking a size preset updates the store and marks the preset active", () => {
  render(<SettingsMenu />);
  fireEvent.click(screen.getByRole("button", { name: /settings/i }));

  fireEvent.click(screen.getByRole("button", { name: "XL" }));

  expect(useStore.getState().fontScale).toBe(FONT_SCALES.XL);
  const xl = screen.getByRole("button", { name: "XL" });
  expect(xl).toHaveAttribute("aria-pressed", "true");
});
