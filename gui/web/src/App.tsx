// App shell: header · left rail (shot picker) · tabbed main · right rail (quality).
// The four tabs are independent files owned by different people — they read from
// the store and render `kind`-nodes via <NodeView>. Adding a view = one file.
import { useEffect } from "react";
import "./theme.css";
import { useStore, type TabId } from "./store";
import { usingLiveBackend } from "./lib/api";
import SensorsTab from "./components/tabs/SensorsTab";
import QuasiStationaryTab from "./components/tabs/QuasiStationaryTab";
import RotatingTab from "./components/tabs/RotatingTab";
import FitsTab from "./components/tabs/FitsTab";
import PullControl from "./components/PullControl";

const TABS: { id: TabId; label: string }[] = [
  { id: "sensors", label: "Sensors" },
  { id: "qs", label: "Quasi-stationary" },
  { id: "rotating", label: "Rotating modes" },
  { id: "fits", label: "Fits" },
];

export default function App() {
  const { machines, machine, tab, loadingMachines, init, setMachine, setTab } = useStore();

  useEffect(() => { void init(); }, [init]);

  return (
    <div className="app">
      <header className="app-header">
        <span className="title">Magnetics</span>
        <span className="sub">3D magnetic-sensor analysis</span>
        <span className="spacer" />
        <span className="badge">{usingLiveBackend() ? "● live backend" : "○ mock data"}</span>
      </header>

      <aside className="rail-left">
        <div className="rail-section">
          <h3>Shot / machine</h3>
          {loadingMachines && <div className="placeholder">loading…</div>}
          {machines.map((m) => (
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
        <PullControl />
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
        ) : tab === "sensors" ? (
          <SensorsTab machine={machine} />
        ) : tab === "qs" ? (
          <QuasiStationaryTab machine={machine} />
        ) : tab === "rotating" ? (
          <RotatingTab machine={machine} />
        ) : (
          <FitsTab machine={machine} />
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
