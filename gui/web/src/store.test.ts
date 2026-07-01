import { afterEach, expect, test } from "vitest";
import { useStore } from "./store";

// The store module registers a window `storage` listener at import time so a theme
// change in one browser tab (localStorage write) mirrors into every other tab.
const THEME_KEY = "magnetics-theme";

afterEach(() => useStore.setState({ theme: "dark" }));

test("a theme storage event syncs the store + the <html> data-theme", () => {
  useStore.setState({ theme: "dark" });

  window.dispatchEvent(new StorageEvent("storage", { key: THEME_KEY, newValue: "light" }));
  expect(useStore.getState().theme).toBe("light");
  expect(document.documentElement.getAttribute("data-theme")).toBe("light");

  window.dispatchEvent(new StorageEvent("storage", { key: THEME_KEY, newValue: "dark" }));
  expect(useStore.getState().theme).toBe("dark");
  expect(document.documentElement.getAttribute("data-theme")).toBe("dark");
});

test("unrelated storage keys and junk values are ignored", () => {
  useStore.setState({ theme: "dark" });

  window.dispatchEvent(new StorageEvent("storage", { key: "some-other-key", newValue: "light" }));
  expect(useStore.getState().theme).toBe("dark");

  window.dispatchEvent(new StorageEvent("storage", { key: THEME_KEY, newValue: "purple" }));
  expect(useStore.getState().theme).toBe("dark");
});
