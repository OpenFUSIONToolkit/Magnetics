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
  const { machines, machine, tab, loadingMachines, init, setMachine, setTab } = useStore();
  const removeMachine = useStore((s) => s.removeMachine);
  const clearMachines = useStore((s) => s.clearMachines);

  useEffect(() => { void init(); }, [init]);

  // Deletable = real fetched shots (mock demo machines have nothing on disk). Only
  // offer delete controls against a live backend.
  const deletable = usingLiveBackend() ? machines.filter((m) => !m.mock) : [];

  async function onDelete(id: string, label: string) {
    if (!window.confirm(`Delete ${label} and all its underlying data? This cannot be undone.`)) return;
    try {
      await removeMachine(id);
    } catch (e) {
      window.alert(`Delete failed: ${String(e)}`);
    }
  }

  async function onClearAll() {
    if (!window.confirm(`Delete ALL ${deletable.length} fetched shot(s) and their data? This cannot be undone.`))
      return;
    try {
      await clearMachines();
    } catch (e) {
      window.alert(`Clear all failed: ${String(e)}`);
    }
  }

  return (
    <div className="app">
      <header className="app-header">
        <span className="title">Magnetics</span>
        <span className="sub">3D magnetic-sensor analysis</span>
        <span className="spacer" />
        <span className="badge">{usingLiveBackend() ? "● live backend" : "○ offline / demo"}</span>
        <ThemeToggle />
      </header>

      <aside className="rail-left">
        <PullControl />
        <div className="rail-section">
          <div className="rail-head">
            <h3>Shot / machine</h3>
            {deletable.length > 0 && (
              <button className="rail-clear" title="Delete all fetched shots and their data"
                onClick={() => void onClearAll()}>
                Clear all
              </button>
            )}
          </div>
          {loadingMachines && <div className="placeholder">loading…</div>}
          {machines.map((m) => (
            <div
              key={m.id}
              className={`machine-item${m.id === machine ? " active" : ""}`}
              onClick={() => setMachine(m.id)}
            >
              <div className="machine-main">
                <div className="id">{m.label}</div>
                {m.note && <div className="note">{m.note}</div>}
              </div>
              {!m.mock && usingLiveBackend() && (
                <button className="machine-del" title={`Delete ${m.label} and its data`}
                  aria-label={`Delete ${m.label}`}
                  onClick={(e) => { e.stopPropagation(); void onDelete(m.id, m.label); }}>
                  ×
                </button>
              )}
            </div>
          ))}
        </div>
      </aside>

      <main className="main">
        <div className="tabbar">
          {TABS.map((t) => (
            <div key={t.id} className={`tab${t.id === tab ? " active" : ""}`} onClick={() => setTab(t.id)}>
              {t.label}
            </div>
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
