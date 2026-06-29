// Trigger a live toksearch/mdsthin/remote pull from the GUI (POST /api/fetch),
// then refresh the shot list and select the new shot. Only shown when a live
// backend is configured. Credentials are entered here and sent to the LOCAL
// backend (localhost) only — not stored.
//
// A pull is synchronous and can take minutes (a full-rate rotating pull is ~3 min
// over the tunnel). We show a live elapsed timer + a "keep this open" warning so
// it never looks hung — DON'T stop the server mid-pull. To make pulls fast, set a
// time window (tmin/tmax, ms) and a decimation factor (quasi-stationary only).
import { useEffect, useRef, useState } from "react";
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
  const [tmin, setTmin] = useState("");
  const [tmax, setTmax] = useState("");
  const [decimate, setDecimate] = useState("");
  const [busy, setBusy] = useState(false);
  const [elapsed, setElapsed] = useState(0);
  const [msg, setMsg] = useState<string | null>(null);
  const startRef = useRef(0);

  // tick an elapsed-seconds counter while a pull is in flight
  useEffect(() => {
    if (!busy) return;
    startRef.current = Date.now();
    // eslint-disable-next-line react-hooks/set-state-in-effect -- reset the timer when a pull starts
    setElapsed(0);
    const id = setInterval(
      () => setElapsed(Math.round((Date.now() - startRef.current) / 1000)),
      1000,
    );
    return () => clearInterval(id);
  }, [busy]);

  if (!usingLiveBackend()) return null;
  const needsCreds = backend === "remote" || backend === "mdsthin";
  const num = (s: string) => (s.trim() === "" ? undefined : Number(s));

  async function pull() {
    setBusy(true);
    setMsg(null);
    try {
      const r = await triggerFetch({
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
      await init();
      setMachine(r.shot);
      const secs = Math.round((Date.now() - startRef.current) / 1000);
      setMsg(`✓ pulled shot ${r.shot} in ${secs}s`);
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

      {/* speed knobs — a window + decimation make a pull seconds instead of minutes */}
      <div className="pull-row">
        <input
          className="pull-input"
          value={tmin}
          onChange={(e) => setTmin(e.target.value)}
          placeholder="tmin ms"
        />
        <input
          className="pull-input"
          value={tmax}
          onChange={(e) => setTmax(e.target.value)}
          placeholder="tmax ms"
        />
        <input
          className="pull-input"
          value={decimate}
          onChange={(e) => setDecimate(e.target.value)}
          placeholder="decim."
        />
      </div>

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
        {busy ? `pulling… ${elapsed}s` : "Pull"}
      </button>
      {busy && (
        <div className="note pull-warn">
          a full-rate pull can take a few minutes — keep this open and don't stop
          the server. Use tmin/tmax + decimate to make it fast.
        </div>
      )}
      {msg && <div className="note">{msg}</div>}
    </div>
  );
}
