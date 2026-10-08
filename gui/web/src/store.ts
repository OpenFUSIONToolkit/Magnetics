// Global UI state (zustand). Deliberately small: the selected machine/shot, the
// active tab, the shared time cursor that links the quasi-stationary and
// rotating views (VISION §6.4), the analysis params each of those views last ran
// (so the Compare view plots the same analysis), and the per-shot annotations. Views read what they need and render nodes from
// the API; heavy data stays in the nodes, not here.
import { create } from "zustand";
import {
  deleteAllMachines,
  deleteMachine,
  fetchDevices,
  fetchMachines,
  type DeviceInfo,
  type MachineInfo,
} from "./lib/api";
import {
  newAnnotationId, parseAnnotations, type Annotation, type AnnotationInput, type AnnotationPatch,
} from "./lib/annotations";

export type TabId = "sensors" | "qs" | "rotating" | "compare";
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

// ── Plasma-signal strip (every tab) ─────────────────────────────────────────
// Global (not per shot) and persisted: the traces to plot, whether the strip is open,
// and whether every analysis stops at the Ip flattop end (lib/flattop.ts).
const TRACE_SIGNALS_KEY = "magnetics-trace-signals";
const TRACE_OPEN_KEY = "magnetics-trace-open";
const CUT_FLATTOP_KEY = "magnetics-cut-flattop";
export const DEFAULT_TRACE_SIGNALS = ["ip", "bt", "kappa"];
const isBool = (v: string) => v === "true" || v === "false";
const isNameList = (v: string) => {
  try { const a: unknown = JSON.parse(v); return Array.isArray(a) && a.every((x) => typeof x === "string"); } catch { return false; }
};
const savePref = (key: string, value: unknown) => window.localStorage.setItem(key, JSON.stringify(value));

// ── Per-shot plot annotations (Compare view) ────────────────────────────────
// Keyed by machine id, persisted as JSON. Every read is validated (parseAnnotations)
// and storage failures are swallowed — annotations are a convenience, never fatal.
const ANNOTATIONS_KEY = "magnetics-annotations";
function loadAnnotations(): Record<string, Annotation[]> {
  if (typeof window === "undefined") return {};
  try {
    const raw: unknown = JSON.parse(window.localStorage.getItem(ANNOTATIONS_KEY) ?? "{}");
    if (!raw || typeof raw !== "object" || Array.isArray(raw)) return {};
    const out: Record<string, Annotation[]> = {};
    for (const [k, v] of Object.entries(raw)) {
      const list = parseAnnotations(v);
      if (list.length) out[k] = list;
    }
    return out;
  } catch {
    return {};
  }
}
function saveAnnotations(all: Record<string, Annotation[]>) {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(ANNOTATIONS_KEY, JSON.stringify(all));
  } catch {
    /* quota / private mode — keep the in-memory copy */
  }
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
  // Shared time axis (ms) of every time-series plot — strip, QS, rotating, Compare;
  // null = autorange. Zooming any of them sets it; a shot change clears it.
  timeRange: [number, number] | null;
  loadingMachines: boolean;
  theme: Theme;
  fetchCreds: FetchCreds; // shared by PullControl + the QS custom-signal panel
  fontScale: number;
  // Params of the last spectrogram / mode-number fetch the Rotating tab made, and of
  // the last committed quasi-stationary fit — null until that tab has run (the
  // Compare view then falls back to the same defaults those tabs start from).
  rotParams: { spec: Record<string, number>; mode: Record<string, number> } | null;
  qsParams: Record<string, string> | null;
  annotations: Record<string, Annotation[]>; // keyed by machine id
  traceSignals: string[]; // plasma-signal strip selection (every tab)
  traceOpen: boolean;
  cutFlattop: boolean; // stop every analysis at the Ip flattop end (lib/flattop.ts)

  init: () => Promise<void>;
  removeMachine: (id: string) => Promise<void>;
  clearMachines: () => Promise<void>;
  setMachine: (id: string) => void;
  setDevice: (id: string) => void;
  setTab: (t: TabId) => void;
  setCursorMs: (t: number) => void;
  setTimeRange: (r: [number, number] | null) => void;
  toggleTheme: () => void;
  setFetchCreds: (patch: Partial<FetchCreds>) => void;
  setFontScale: (n: number) => void;
  setRotParams: (p: { spec: Record<string, number>; mode: Record<string, number> }) => void;
  setQsParams: (p: Record<string, string>) => void;
  addAnnotation: (machine: string, a: AnnotationInput) => void;
  updateAnnotation: (machine: string, id: string, patch: AnnotationPatch) => void;
  removeAnnotation: (machine: string, id: string) => void;
  setAnnotations: (machine: string, list: Annotation[]) => void;
  setTraceSignals: (names: string[]) => void;
  setTraceOpen: (open: boolean) => void;
  setCutFlattop: (on: boolean) => void;
}

export const useStore = create<State>((set) => ({
  machines: [],
  machine: null,
  devices: [],
  device: "",
  tab: "sensors",
  cursorMs: 0,
  timeRange: null,
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
  rotParams: null,
  qsParams: null,
  annotations: loadAnnotations(),
  traceSignals: readPref(TRACE_SIGNALS_KEY, isNameList, DEFAULT_TRACE_SIGNALS, (v) => JSON.parse(v) as string[]),
  traceOpen: readPref(TRACE_OPEN_KEY, isBool, true, (v) => v === "true"),
  cutFlattop: readPref(CUT_FLATTOP_KEY, isBool, false, (v) => v === "true"),

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
  setMachine: (id) => set((s) => (s.machine === id ? {} : { machine: id, timeRange: null })),
  setDevice: (id) => set({ device: id }),
  setTab: (t) => set({ tab: t }),
  setCursorMs: (t) => set({ cursorMs: t }),
  setTimeRange: (r) =>
    set((s) => (r === s.timeRange || (r && s.timeRange && r[0] === s.timeRange[0] && r[1] === s.timeRange[1])
      ? {} : { timeRange: r })),
  setRotParams: (p) => set({ rotParams: p }),
  setQsParams: (p) => set({ qsParams: p }),
  addAnnotation: (machine, a) =>
    set((s) => withAnnotations(s, machine, [...(s.annotations[machine] ?? []), { ...a, id: newAnnotationId() } as Annotation])),
  updateAnnotation: (machine, id, patch) =>
    set((s) =>
      withAnnotations(s, machine, (s.annotations[machine] ?? []).map((a) => (a.id === id ? ({ ...a, ...patch } as Annotation) : a))),
    ),
  removeAnnotation: (machine, id) =>
    set((s) => withAnnotations(s, machine, (s.annotations[machine] ?? []).filter((a) => a.id !== id))),
  setAnnotations: (machine, list) => set((s) => withAnnotations(s, machine, list)),
  setTraceSignals: (names) => { savePref(TRACE_SIGNALS_KEY, names); set({ traceSignals: names }); },
  setTraceOpen: (open) => { savePref(TRACE_OPEN_KEY, open); set({ traceOpen: open }); },
  setCutFlattop: (on) => { savePref(CUT_FLATTOP_KEY, on); set({ cutFlattop: on }); },
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
}));

// Replace one machine's annotation list (dropping the key when empty) and persist.
function withAnnotations(s: State, machine: string, list: Annotation[]): Pick<State, "annotations"> {
  const annotations = { ...s.annotations };
  if (list.length) annotations[machine] = list;
  else delete annotations[machine];
  saveAnnotations(annotations);
  return { annotations };
}

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
