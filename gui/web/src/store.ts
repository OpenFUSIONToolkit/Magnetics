// Global UI state (zustand). Deliberately small: the selected machine/shot, the
// active tab, and the shared time cursor that links the quasi-stationary and
// rotating views (VISION §6.4). Views read what they need and render nodes from
// the API; heavy data stays in the nodes, not here.
import { create } from "zustand";
import {
  deleteAllMachines,
  deleteMachine,
  fetchDevices,
  fetchExclusions,
  fetchMachines,
  saveExclusions,
  type DeviceInfo,
  type MachineInfo,
} from "./lib/api";

export type TabId = "sensors" | "qs" | "rotating";
export type Theme = "dark" | "light";

// Backend + DIII-D credentials for a live pull. Lifted out of PullControl so the
// QS tab's custom-signal panel can reuse the same creds — the user enters them
// once. Sent to the LOCAL backend (localhost) only, never persisted.
export interface FetchCreds {
  backend: string;
  username: string;
  password: string;
  duoMode: "push" | "passcode";
  duoPasscode: string;
}

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
  devices: DeviceInfo[]; // available device configs (GET /api/devices)
  device: string; // selected device id (single source of truth)
  tab: TabId;
  cursorMs: number; // shared time cursor across views
  loadingMachines: boolean;
  theme: Theme;
  fetchCreds: FetchCreds; // shared by PullControl + the QS custom-signal panel
  fontScale: number;
  // Channels the operator marked bad for the current shot (#56). Server-side
  // state mirrored here for the Sensors view; the analyses read it from the
  // store on the backend, so `excludedRev` (bumped on every change) is what
  // makes every open view re-fit — useNode() folds it into its fetch key.
  excluded: string[];
  excludedRev: number;

  init: () => Promise<void>;
  removeMachine: (id: string) => Promise<void>;
  clearMachines: () => Promise<void>;
  setMachine: (id: string) => void;
  setDevice: (id: string) => void;
  setTab: (t: TabId) => void;
  setCursorMs: (t: number) => void;
  toggleTheme: () => void;
  setFetchCreds: (patch: Partial<FetchCreds>) => void;
  setFontScale: (n: number) => void;
  loadExclusions: (shot: string) => Promise<void>;
  toggleExcluded: (shot: string, channel: string) => Promise<void>;
  clearExclusions: (shot: string) => Promise<void>;
}

export const useStore = create<State>((set) => ({
  machines: [],
  machine: null,
  devices: [],
  device: "",
  tab: "sensors",
  cursorMs: 0,
  loadingMachines: true,
  theme: loadTheme(),
  // Default to the fast cluster path (remote); PullControl's device snap adjusts it.
  fetchCreds: {
    backend: "remote",
    username: "",
    password: "",
    duoMode: "push",
    duoPasscode: "",
  },
  fontScale: loadFontScale(),
  excluded: [],
  excludedRev: 0,

  async init() {
    // fetchDevices() guards its own errors and returns [] (no live backend / no
    // device files), so this Promise.all never rejects on the devices side.
    const [machines, devices] = await Promise.all([fetchMachines(), fetchDevices()]);
    // Default the device to the one matching the first machine's device name,
    // falling back to the first configured device.
    const firstDeviceName = machines[0]?.device;
    const defaultDevice =
      devices.find((d) => d.name === firstDeviceName)?.id ?? devices[0]?.id ?? "";
    set((s) => ({
      machines,
      devices,
      loadingMachines: false,
      machine: s.machine ?? machines[0]?.id ?? null,
      device: s.device || defaultDevice,
    }));
  },
  // Delete one shot's data, then re-list. If the removed shot was selected, fall
  // back to the first remaining machine (or none).
  async removeMachine(id) {
    await deleteMachine(id);
    const machines = await fetchMachines();
    set((s) => ({
      machines,
      machine: s.machine === id ? (machines[0]?.id ?? null) : s.machine,
    }));
  },
  // Delete every fetched shot, then re-list and reselect (the backend falls back
  // to demo machines when no real data remains).
  async clearMachines() {
    await deleteAllMachines();
    const machines = await fetchMachines();
    set({ machines, machine: machines[0]?.id ?? null });
  },
  setMachine: (id) => set({ machine: id }),
  setDevice: (id) => set({ device: id }),
  setTab: (t) => set({ tab: t }),
  setCursorMs: (t) => set({ cursorMs: t }),
  setFetchCreds: (patch) => set((s) => ({ fetchCreds: { ...s.fetchCreds, ...patch } })),
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

  // ── bad-channel exclusions (#56) ─────────────────────────────────────────
  // The server is the source of truth (persisted per shot); these keep a mirror
  // for the Sensors view and bump `excludedRev` so every open view re-fits.
  async loadExclusions(shot) {
    try {
      set({ excluded: await fetchExclusions(shot), excludedRev: 0 });
    } catch {
      set({ excluded: [], excludedRev: 0 }); // no live backend / no store yet
    }
  },
  async toggleExcluded(shot, channel) {
    const cur = useStore.getState().excluded;
    const next = cur.includes(channel) ? cur.filter((c) => c !== channel) : [...cur, channel];
    // Optimistic: the sensor greys immediately, then the save confirms the
    // canonical (sorted) list. Roll back if the write fails so the map never
    // shows an exclusion the analyses aren't actually honoring.
    set((s) => ({ excluded: next, excludedRev: s.excludedRev + 1 }));
    try {
      const stored = await saveExclusions(shot, next);
      set((s) => ({ excluded: stored, excludedRev: s.excludedRev + 1 }));
    } catch {
      set((s) => ({ excluded: cur, excludedRev: s.excludedRev + 1 }));
    }
  },
  async clearExclusions(shot) {
    const cur = useStore.getState().excluded;
    set((s) => ({ excluded: [], excludedRev: s.excludedRev + 1 }));
    try {
      await saveExclusions(shot, []);
    } catch {
      set((s) => ({ excluded: cur, excludedRev: s.excludedRev + 1 }));
    }
  },
}));

// Keep the theme in sync across browser tabs: toggleTheme writes localStorage, so a
// `storage` event fires in every OTHER tab — mirror it into the store + the DOM.
if (typeof window !== "undefined") {
  window.addEventListener("storage", (e) => {
    if (e.key !== THEME_KEY) return;
    const next = e.newValue;
    if (next === "light" || next === "dark") {
      applyTheme(next);
      useStore.setState({ theme: next });
    }
  });
}
