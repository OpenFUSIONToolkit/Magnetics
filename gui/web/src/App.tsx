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
  const { machines, machine, devices, device, tab, loadingMachines, init, setMachine, setDevice, setTab } =
    useStore();

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

  return (
    <div className="app">
      <header className="app-header">
        <span className="title">Magnetics</span>
        <span className="sub">3D magnetic-sensor analysis</span>
        <span className="spacer" />
        <span className="badge">{usingLiveBackend() ? "● live backend" : "○ offline / demo"}</span>
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
          <h3>Shot / machine</h3>
          {loadingMachines && <div className="placeholder">loading…</div>}
          {visibleMachines.map((m) => (
            <div
              key={m.id}
              className={`machine-item${m.id === machine ? " active" : ""}`}
              onClick={() => setMachine(m.id)}
            >
              <div className="id">{m.label}</div>
              {m.note && <div className="note">{m.note}</div>}
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
