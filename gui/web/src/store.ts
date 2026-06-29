// Global UI state (zustand). Deliberately small: the selected machine/shot, the
// active tab, and the shared time cursor that links the quasi-stationary and
// rotating views (VISION §6.4). Views read what they need and render nodes from
// the API; heavy data stays in the nodes, not here.
import { create } from "zustand";
import { fetchMachines, type MachineInfo } from "./lib/api";

export type TabId = "sensors" | "qs" | "rotating" | "fits";

interface State {
  machines: MachineInfo[];
  machine: string | null; // current machine/shot id
  tab: TabId;
  cursorMs: number; // shared time cursor across views
  loadingMachines: boolean;

  init: () => Promise<void>;
  setMachine: (id: string) => void;
  setTab: (t: TabId) => void;
  setCursorMs: (t: number) => void;
}

export const useStore = create<State>((set) => ({
  machines: [],
  machine: null,
  tab: "sensors",
  cursorMs: 0,
  loadingMachines: true,

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
}));
