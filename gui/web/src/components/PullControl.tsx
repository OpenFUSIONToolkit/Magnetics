// Trigger a live mdsthin/remote pull from the GUI and stream its REAL progress.
// Only shown when a live backend is configured. Credentials are entered here and
// sent to the LOCAL backend (localhost) only — not stored.
//
// Flow: POST /api/fetch starts a background job → we open an EventSource on
// /api/fetch/{job_id}/stream → a real per-channel progress bar fills → on done we
// refresh the shot list and select the new shot. Set a window (tmin/tmax) +
// decimation to make a pull seconds instead of minutes.
import { useState } from "react";
import { apiBase, startFetch, usingLiveBackend } from "../lib/api";
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
  const [tmin, setTmin] = useState("");
  const [tmax, setTmax] = useState("");
  const [decimate, setDecimate] = useState("");
  const [busy, setBusy] = useState(false);
  const [frac, setFrac] = useState(0);
  const [msg, setMsg] = useState<string | null>(null);

  if (!usingLiveBackend()) return null;
  const needsCreds = backend === "remote" || backend === "mdsthin";
  const num = (s: string) => (s.trim() === "" ? undefined : Number(s));

  async function pull() {
    setBusy(true);
    setFrac(0);
    setMsg("starting…");
    try {
      const { job_id } = await startFetch({
        shot: Number(shot),
        analysis,
        backend,
        username: username || undefined,
        password: password || undefined,
        duo: duo || undefined,
        tmin: num(tmin),
        tmax: num(tmax),
        decimate: num(decimate),
      });
      const es = new EventSource(`${apiBase()}/api/fetch/${job_id}/stream`);
      es.onmessage = (e: MessageEvent) => {
        const f = JSON.parse(e.data as string);
        setFrac(f.progress ?? 0);
        setMsg(f.msg ?? null);
        if (f.status === "done") {
          es.close();
          void init();
          if (f.result?.shot) setMachine(f.result.shot);
          setMsg(`✓ pulled shot ${f.result?.shot}`);
          setBusy(false);
        } else if (f.status === "error") {
          es.close();
          setMsg(`✗ ${f.error}`);
          setBusy(false);
        }
      };
      es.onerror = () => {
        es.close();
        setMsg("✗ progress stream lost (the pull may still be running)");
        setBusy(false);
      };
    } catch (e) {
      setMsg(String(e));
      setBusy(false);
    }
  }

  return (
    <div className="rail-section">
      <h3>Pull a shot (live)</h3>
      <input className="pull-input" value={shot}
        onChange={(e) => setShot(e.target.value)} placeholder="shot number" />
      <select className="pull-input" value={analysis}
        onChange={(e) => setAnalysis(e.target.value)}>
        <option value="rotating">rotating</option>
        <option value="quasi-stationary">quasi-stationary</option>
        <option value="both">both</option>
      </select>
      <select className="pull-input" value={backend}
        onChange={(e) => setBackend(e.target.value)}>
        <option value="mdsthin">mdsthin (laptop → DIII-D)</option>
        <option value="remote">remote (run on cluster · WIP)</option>
        <option value="auto">auto</option>
      </select>

      {/* speed knobs — a window + decimation make a pull seconds instead of minutes */}
      <div className="pull-row">
        <input className="pull-input" value={tmin}
          onChange={(e) => setTmin(e.target.value)} placeholder="tmin ms" />
        <input className="pull-input" value={tmax}
          onChange={(e) => setTmax(e.target.value)} placeholder="tmax ms" />
        <input className="pull-input" value={decimate}
          onChange={(e) => setDecimate(e.target.value)} placeholder="decim." />
      </div>

      {needsCreds && (
        <>
          <input className="pull-input" value={username}
            onChange={(e) => setUsername(e.target.value)}
            placeholder="GA username" autoComplete="username" />
          <input className="pull-input" type="password" value={password}
            onChange={(e) => setPassword(e.target.value)}
            placeholder="GA password" autoComplete="current-password" />
          <input className="pull-input" value={duo}
            onChange={(e) => setDuo(e.target.value)}
            placeholder="Duo: 1 = push, or passcode" />
        </>
      )}
      <button className="pull-btn" disabled={busy} onClick={pull}>
        {busy ? `pulling… ${Math.round(frac * 100)}%` : "Pull"}
      </button>
      {busy && (
        <div className="pull-bar">
          <div className="pull-bar-fill" style={{ width: `${frac * 100}%` }} />
        </div>
      )}
      {msg && <div className="note">{msg}</div>}
    </div>
  );
}
