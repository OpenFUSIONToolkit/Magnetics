// Trigger a live toksearch/mdsthin/remote pull from the GUI (POST /api/fetch),
// then refresh the shot list and select the new shot. Only shown when a live
// backend is configured. Credentials are entered here and sent to the LOCAL
// backend (localhost) only — not stored. For the `remote` backend they answer the
// cluster SSH login (password + Duo) via an askpass helper, so no terminal prompt.
import { useState } from "react";
import { triggerFetch, usingLiveBackend } from "../lib/api";
import { useStore } from "../store";

export default function PullControl() {
  const init = useStore((s) => s.init);
  const setMachine = useStore((s) => s.setMachine);
  const [shot, setShot] = useState("184927");
  const [analysis, setAnalysis] = useState("rotating");
  const [backend, setBackend] = useState("mdsthin");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [duo, setDuo] = useState("1");
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);

  if (!usingLiveBackend()) return null;
  const needsCreds = backend === "remote" || backend === "mdsthin";

  async function pull() {
    setBusy(true);
    setMsg("pulling…");
    try {
      const r = await triggerFetch({
        shot: Number(shot),
        analysis,
        backend,
        username: username || undefined,
        password: password || undefined,
        duo: duo || undefined,
      });
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
      <select
        className="pull-input"
        value={backend}
        onChange={(e) => setBackend(e.target.value)}
      >
        <option value="mdsthin">mdsthin (laptop → DIII-D)</option>
        <option value="remote">remote (run on cluster)</option>
        <option value="auto">auto</option>
      </select>
      {needsCreds && (
        <>
          <input
            className="pull-input"
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            placeholder="GA username"
            autoComplete="username"
          />
          <input
            className="pull-input"
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            placeholder="GA password"
            autoComplete="current-password"
          />
          <input
            className="pull-input"
            value={duo}
            onChange={(e) => setDuo(e.target.value)}
            placeholder="Duo: 1 = push, or passcode"
          />
        </>
      )}
      <button className="pull-btn" disabled={busy} onClick={pull}>
        {busy ? "pulling…" : "Pull"}
      </button>
      {msg && <div className="note">{msg}</div>}
    </div>
  );
}
