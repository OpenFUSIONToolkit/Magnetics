// Global UI state (zustand). Deliberately small: the selected machine/shot, the
// active tab, and the shared time cursor that links the quasi-stationary and
// rotating views (VISION §6.4). Views read what they need and render nodes from
// the API; heavy data stays in the nodes, not here.
import { create } from "zustand";
import { fetchMachines, type MachineInfo } from "./lib/api";

export type TabId = "sensors" | "qs" | "rotating";
export type Theme = "dark" | "light";

// ── global appearance preferences ──────────────────────────────────────────
// Each preference follows one shape: a persisted value → an `apply*` function
// that mutates <html> → the whole app restyles from CSS/plot layer. `theme` and
// `fontScale` below are both instances; `readPref` factors the load/validate.
// To add a new global appearance preference: add its value + apply*() + set*()
// here (mirroring fontScale), then a row in components/SettingsMenu.tsx.
function readPref<T>(key: string, isValid: (v: string) => boolean, fallback: T, parse: (v: string) => T): T {
  if (typeof window === "undefined") return fallback;
  const saved = window.localStorage.getItem(key);
  return saved !== null && isValid(saved) ? parse(saved) : fallback;
}

// Theme is a single global switch: it drives the `data-theme` attribute on
// <html> (so theme.css restyles the chrome) and is read by the plot layer and
// Meg's useDarkMode() hook, so one toggle re-skins everything at once.
const THEME_KEY = "magnetics-theme";
function loadTheme(): Theme {
  return readPref(
    THEME_KEY,
    (v) => v === "light" || v === "dark",
    "dark" as Theme,
    (v) => v as Theme,
  );
}
export function applyTheme(t: Theme) {
  if (typeof document === "undefined") return;
  document.documentElement.setAttribute("data-theme", t);
  document.documentElement.style.colorScheme = t;
}

// Text size is the second global appearance preference: a `--font-scale`
// multiplier on <html> that theme.css folds into the base font-size (all
// em-based type then scales with it). The named presets are the only allowed
// values, evenly spaced from S (kept small) up to a boosted XL; anything else
// in storage falls back to M (the default).
export const FONT_SCALES = { S: 0.85, M: 1.1, L: 1.35, XL: 1.6 } as const;
export type FontSizeKey = keyof typeof FONT_SCALES;
const FONT_SCALE_KEY = "magnetics-font-scale";
const isFontScaleKey = (v: string): v is FontSizeKey => v in FONT_SCALES;
function loadFontScale(): number {
  return readPref(FONT_SCALE_KEY, isFontScaleKey, FONT_SCALES.M, (v) => FONT_SCALES[v as FontSizeKey]);
}
export function applyFontScale(n: number) {
  if (typeof document === "undefined") return;
  document.documentElement.style.setProperty("--font-scale", String(n));
}

// Apply synchronously at module load so the first paint matches (no flash).
applyTheme(loadTheme());
applyFontScale(loadFontScale());

interface State {
  machines: MachineInfo[];
  machine: string | null; // current machine/shot id
  tab: TabId;
  cursorMs: number; // shared time cursor across views
  loadingMachines: boolean;
  theme: Theme;
  fontScale: number;

  init: () => Promise<void>;
  setMachine: (id: string) => void;
  setTab: (t: TabId) => void;
  setCursorMs: (t: number) => void;
  toggleTheme: () => void;
  setFontScale: (n: number) => void;
}

export const useStore = create<State>((set) => ({
  machines: [],
  machine: null,
  tab: "sensors",
  cursorMs: 0,
  loadingMachines: true,
  theme: loadTheme(),
  fontScale: loadFontScale(),

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
  setFontScale: (n) => {
    // Persist by preset name (the localStorage schema), not the raw multiplier,
    // so unknown values fall back cleanly on the next load.
    const key = (Object.keys(FONT_SCALES) as FontSizeKey[]).find((k) => FONT_SCALES[k] === n);
    if (key && typeof window !== "undefined") window.localStorage.setItem(FONT_SCALE_KEY, key);
    applyFontScale(n);
    set({ fontScale: n });
  },
}));
