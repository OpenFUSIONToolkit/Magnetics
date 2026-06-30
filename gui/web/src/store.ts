// Global UI state (zustand). Deliberately small: the selected machine/shot, the
// active tab, and the shared time cursor that links the quasi-stationary and
// rotating views (VISION §6.4). Views read what they need and render nodes from
// the API; heavy data stays in the nodes, not here.
import { create } from "zustand";
import { fetchMachines, type MachineInfo } from "./lib/api";

export type TabId = "sensors" | "qs" | "rotating";
export type Theme = "dark" | "light";

// Theme is a single global switch: it drives the `data-theme` attribute on
// <html> (so theme.css restyles the chrome) and is read by the plot layer and
// Meg's useDarkMode() hook, so one toggle re-skins everything at once.
const THEME_KEY = "magnetics-theme";
function loadTheme(): Theme {
  if (typeof window === "undefined") return "dark";
  const saved = window.localStorage.getItem(THEME_KEY);
  return saved === "light" || saved === "dark" ? saved : "dark";
}
export function applyTheme(t: Theme) {
  if (typeof document === "undefined") return;
  document.documentElement.setAttribute("data-theme", t);
  document.documentElement.style.colorScheme = t;
}
// Apply synchronously at module load so the first paint matches (no flash).
applyTheme(loadTheme());

interface State {
  machines: MachineInfo[];
  machine: string | null; // current machine/shot id
  tab: TabId;
  cursorMs: number; // shared time cursor across views
  loadingMachines: boolean;
  theme: Theme;

  init: () => Promise<void>;
  setMachine: (id: string) => void;
  setTab: (t: TabId) => void;
  setCursorMs: (t: number) => void;
  toggleTheme: () => void;
}

export const useStore = create<State>((set) => ({
  machines: [],
  machine: null,
  tab: "sensors",
  cursorMs: 0,
  loadingMachines: true,
  theme: loadTheme(),

  async init() {
    const machines = await fetchMachines();
    set((s) => ({
      machines,
      loadingMachines: false,
      machine: s.machine ?? machines[0]?.id ?? null,
    }));
  },
  setMachine: (id) => set({ machine: id }),
  setTab: (t) => set({ tab: t }),
  setCursorMs: (t) => set({ cursorMs: t }),
  toggleTheme: () =>
    set((s) => {
      const theme: Theme = s.theme === "dark" ? "light" : "dark";
      if (typeof window !== "undefined") window.localStorage.setItem(THEME_KEY, theme);
      applyTheme(theme);
      return { theme };
    }),
}));
