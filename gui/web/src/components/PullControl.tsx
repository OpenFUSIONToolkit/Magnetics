// Trigger a live toksearch/mdsthin pull from the GUI (POST /api/fetch), then
// refresh the shot list and select the new shot. Only shown when a live backend
// is configured. Actually pulling needs GA creds/cluster; offline it surfaces the
// backend's error message (the cached shots keep working).
import { useState } from "react";
import { triggerFetch, usingLiveBackend } from "../lib/api";
import { useStore } from "../store";

export default function PullControl() {
  const init = useStore((s) => s.init);
  const setMachine = useStore((s) => s.setMachine);
  const [shot, setShot] = useState("184927");
  const [analysis, setAnalysis] = useState("rotating");
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);

  if (!usingLiveBackend()) return null;

  async function pull() {
    setBusy(true);
    setMsg("pulling… (may prompt for creds in the backend terminal)");
    try {
      const r = await triggerFetch({ shot: Number(shot), analysis });
      await init();
      setMachine(r.shot);
      setMsg(`pulled shot ${r.shot}`);
    } catch (e) {
      setMsg(String(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="rail-section">
      <h3>Pull a shot (live)</h3>
      <input
        className="pull-input"
        value={shot}
        onChange={(e) => setShot(e.target.value)}
        placeholder="shot number"
      />
      <select
        className="pull-input"
        value={analysis}
        onChange={(e) => setAnalysis(e.target.value)}
      >
        <option value="rotating">rotating</option>
        <option value="quasi-stationary">quasi-stationary</option>
        <option value="both">both</option>
      </select>
      <button className="pull-btn" disabled={busy} onClick={pull}>
        {busy ? "pulling…" : "Pull"}
      </button>
      {msg && <div className="note">{msg}</div>}
    </div>
  );
}
