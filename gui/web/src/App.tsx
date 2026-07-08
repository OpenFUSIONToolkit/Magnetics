// App shell: header · left rail (shot picker) · tabbed main.
// The four tabs are independent files owned by different people — they read from
// the store and render `kind`-nodes via <NodeView>. Adding a view = one file.
//
// `gui` is the GUI integration branch: teammates branch off it (gui-<view>) and
// PR back here; `gui` itself PRs into `develop`.
import { useEffect } from "react";
import "./theme.css";
import { useStore, type TabId } from "./store";
import { usingLiveBackend } from "./lib/api";
import SettingsMenu from "./components/SettingsMenu";
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
  const devices = useStore((s) => s.devices);
  const device = useStore((s) => s.device);
  const tab = useStore((s) => s.tab);
  const loadingMachines = useStore((s) => s.loadingMachines);
  const init = useStore((s) => s.init);
  const setMachine = useStore((s) => s.setMachine);
  const setDevice = useStore((s) => s.setDevice);
  const setTab = useStore((s) => s.setTab);
  const removeMachine = useStore((s) => s.removeMachine);
  const clearMachines = useStore((s) => s.clearMachines);

  useEffect(() => { void init(); }, [init]);

  // Filter the shot list to the selected device (by display name). If no device
  // is resolved yet, show everything.
  const selName = devices.find((d) => d.id === device)?.name;
  const visibleMachines = selName ? machines.filter((m) => m.device === selName) : machines;

  // When the device changes and the current shot isn't in its list, jump to the
  // first shot for that device (keeps the main view consistent with the picker).
  useEffect(() => {
    if (visibleMachines.length && !visibleMachines.some((m) => m.id === machine)) {
      setMachine(visibleMachines[0].id);
    }
  }, [device, machines, devices]); // eslint-disable-line react-hooks/exhaustive-deps

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

  // Deletable = real fetched shots (mock demo machines have nothing on disk), scoped
  // to the visible device. Only offer delete controls against a live backend.
  const deletable = usingLiveBackend() ? visibleMachines.filter((m) => !m.mock) : [];

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
        <span className="badge">{badgeText}</span>
        <SettingsMenu />
      </header>

      <aside className="rail-left">
        <PullControl />
        {devices.length > 0 && (
          <div className="rail-section">
            <h3>Device</h3>
            <select
              className="pull-input"
              value={device}
              aria-label="device"
              onChange={(e) => setDevice(e.target.value)}
            >
              {devices.map((d) => (
                <option key={d.id} value={d.id}>{d.name}</option>
              ))}
            </select>
          </div>
        )}
        <div className="rail-section">
          <div className="rail-head">
            <h3 id="shot-list-label">Shot / machine</h3>
            {deletable.length > 0 && (
              <button className="rail-clear" title="Delete all fetched shots and their data"
                onClick={() => void onClearAll()}>
                Clear all
              </button>
            )}
          </div>
          {loadingMachines && <div className="placeholder">loading…</div>}
          <div role="listbox" aria-labelledby="shot-list-label">
            {visibleMachines.map((m) => (
              // role=option row (not a <button>, so the delete <button> can nest); keyboard-
              // reachable via tabIndex + Enter/Space so the a11y listbox pattern still holds.
              <div
                key={m.id}
                role="option"
                aria-selected={m.id === machine}
                tabIndex={0}
                className={`machine-item${m.id === machine ? " active" : ""}`}
                onClick={() => setMachine(m.id)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" || e.key === " ") {
                    e.preventDefault();
                    setMachine(m.id);
                  }
                }}
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
    </div>
  );
}
