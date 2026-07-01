// App shell: header · left rail (shot picker) · tabbed main · right rail (quality).
// The four tabs are independent files owned by different people — they read from
// the store and render `kind`-nodes via <NodeView>. Adding a view = one file.
//
// `gui` is the GUI integration branch: teammates branch off it (gui-<view>) and
// PR back here; `gui` itself PRs into `develop`.
import { useEffect } from "react";
import "./theme.css";
import { useStore, type TabId } from "./store";
import { usingLiveBackend } from "./lib/api";
import ThemeToggle from "./components/ThemeToggle";
import PullControl from "./components/PullControl";
import ErrorBoundary from "./components/ErrorBoundary";
import SensorsTab from "./components/tabs/SensorsTab";
import QuasiStationaryTab from "./components/tabs/QuasiStationaryTab";
import RotatingTab from "./components/tabs/RotatingTab";

const TABS: { id: TabId; label: string }[] = [
  { id: "sensors", label: "Sensors" },
  { id: "qs", label: "Quasi-stationary" },
  { id: "rotating", label: "Rotating modes" },
];

export default function App() {
  // Per-field selectors: subscribing to the whole store re-rendered the entire
  // shell on every cursor scrub (setCursorMs); App doesn't read cursorMs.
  const machines = useStore((s) => s.machines);
  const machine = useStore((s) => s.machine);
  const tab = useStore((s) => s.tab);
  const loadingMachines = useStore((s) => s.loadingMachines);
  const init = useStore((s) => s.init);
  const setMachine = useStore((s) => s.setMachine);
  const setTab = useStore((s) => s.setTab);

  useEffect(() => { void init(); }, [init]);

  // Honest data-source badge: a live backend with zero fetched shots still serves
  // the mock machines, so key off the SELECTED machine's `mock` flag (from the
  // backend), falling back to usingLiveBackend only when the flag is absent.
  const selected = machines.find((m) => m.id === machine);
  const mock = selected?.mock ?? !usingLiveBackend();
  const badgeText = !mock
    ? "● live backend"
    : usingLiveBackend()
      ? "○ demo data (no shots fetched)"
      : "○ offline / demo";

  return (
    <div className="app">
      <header className="app-header">
        <span className="title">Magnetics</span>
        <span className="sub">3D magnetic-sensor analysis</span>
        <span className="spacer" />
        <span className="badge">{badgeText}</span>
        <ThemeToggle />
      </header>

      <aside className="rail-left">
        <PullControl />
        <div className="rail-section">
          <h3 id="shot-list-label">Shot / machine</h3>
          {loadingMachines && <div className="placeholder">loading…</div>}
          <div role="listbox" aria-labelledby="shot-list-label">
            {machines.map((m) => (
              <button
                key={m.id}
                type="button"
                role="option"
                aria-selected={m.id === machine}
                className={`machine-item${m.id === machine ? " active" : ""}`}
                onClick={() => setMachine(m.id)}
              >
                <div className="id">{m.label}</div>
                {m.note && <div className="note">{m.note}</div>}
              </button>
            ))}
          </div>
        </div>
      </aside>

      <main className="main">
        <div className="tabbar" role="tablist" aria-label="Analysis views">
          {TABS.map((t) => (
            <button
              key={t.id}
              type="button"
              role="tab"
              aria-selected={t.id === tab}
              className={`tab${t.id === tab ? " active" : ""}`}
              onClick={() => setTab(t.id)}
            >
              {t.label}
            </button>
          ))}
        </div>
        {!machine ? (
          <div className="placeholder">No machine selected.</div>
        ) : (
          <ErrorBoundary resetKeys={[machine, tab]} label={`The ${tab} view`}>
            {tab === "sensors" ? (
              <SensorsTab machine={machine} />
            ) : tab === "qs" ? (
              <QuasiStationaryTab machine={machine} />
            ) : (
              <RotatingTab machine={machine} />
            )}
          </ErrorBoundary>
        )}
      </main>

      <aside className="rail-right">
        <div className="rail-section">
          <h3>Quality</h3>
          <div className="placeholder">
            Condition number K, χ², and channel counts surface here once a fit is selected.
          </div>
        </div>
      </aside>
    </div>
  );
}
