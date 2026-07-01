// Trigger a live mdsthin/remote pull from the GUI and stream its REAL progress.
// Only shown when a live backend is configured. Credentials are entered here and
// sent to the LOCAL backend (localhost) only — not stored.
//
// Flow: POST /api/fetch starts a background job → we open an EventSource on
// /api/fetch/{job_id}/stream → a real per-channel progress bar fills → on done we
// refresh the shot list and select the new shot. Set a window (tmin/tmax) +
// decimation to make a pull seconds instead of minutes.
import { useEffect, useRef, useState } from "react";
import { apiBase, startFetch, usingLiveBackend } from "../lib/api";
import { useStore } from "../store";

export default function PullControl() {
  const init = useStore((s) => s.init);
  const setMachine = useStore((s) => s.setMachine);
  // Device is owned by the store (single source of truth) — shared with the left
  // rail's Device picker. This form just reads/sets it.
  const devices = useStore((s) => s.devices);
  const device = useStore((s) => s.device);
  const setDevice = useStore((s) => s.setDevice);
  const [shot, setShot] = useState("184927");
  const [analysis, setAnalysis] = useState("rotating");
  // Default to the fast cluster path. `mdsthin` (laptop tunnel) streams raw float
  // over the SSH tunnel — minutes; `remote` fetches on the cluster and ships back a
  // compressed h5 — tens of seconds. Users without cluster access pick mdsthin.
  const [backend, setBackend] = useState("remote");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  // Two-factor is always a typed passcode (never push — KSTAR/KFE and GA Duo both
  // accept a one-time code; push is intentionally not offered).
  const [duoPasscode, setDuoPasscode] = useState("");
  // Prefill a sensible DIII-D flat-top window (ms): transfer time is linear in the
  // samples pulled, so cropping the default ~5 s shot to its active window roughly
  // halves the wire payload. Visible + editable (not a silent backend crop, which
  // would hide mode evolution outside the window) — clear both for the full shot.
  const [tmin, setTmin] = useState("1000");
  const [tmax, setTmax] = useState("5000");
  const [decimate, setDecimate] = useState("");
  // Optional sensor-set override: "" = pull the analysis groups (default); a named
  // set (from the device's sensor_sets) overrides analysis and pulls that array.
  const [sensorSet, setSensorSet] = useState("");
  // SSH login for devices that gateway over ssh (e.g. KSTAR). Sent to the local
  // backend only; not stored.
  const [sshUser, setSshUser] = useState("");
  const [sshPassword, setSshPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [frac, setFrac] = useState(0);
  const [msg, setMsg] = useState<string | null>(null);
  // Live EventSource for the in-flight pull, kept in a ref so the unmount cleanup can
  // close it. Without this, navigating away mid-pull leaks the stream and its handlers
  // fire setState on an unmounted component.
  const esRef = useRef<EventSource | null>(null);

  // close any open pull stream when the component unmounts
  useEffect(() => () => esRef.current?.close(), []);
  const dev = devices.find((d) => d.id === device);

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
        duo: duoPasscode || undefined,
        tmin: num(tmin),
        tmax: num(tmax),
        decimate: num(decimate),
        // device drives the gateway/server + which sensor_sets exist; a chosen
        // sensor-set overrides the analysis groups (backend semantics).
        device: device || undefined,
        sensor_set: sensorSet || undefined,
        ssh_user: sshUser || undefined,
        ssh_password: sshPassword || undefined,
      });
      esRef.current?.close();  // close a prior stream if one is somehow still open
      const es = new EventSource(`${apiBase()}/api/fetch/${job_id}/stream`);
      esRef.current = es;
      const close = () => { es.close(); if (esRef.current === es) esRef.current = null; };
      es.onmessage = (e: MessageEvent) => {
        const f = JSON.parse(e.data as string);
        setFrac(f.progress ?? 0);
        setMsg(f.msg ?? null);
        if (f.status === "done") {
          close();
          void init();
          if (f.result?.shot) setMachine(f.result.shot);
          setMsg(`✓ pulled shot ${f.result?.shot}`);
          setBusy(false);
        } else if (f.status === "error") {
          close();
          setMsg(`✗ ${f.error}`);
          setBusy(false);
        }
      };
      es.onerror = () => {
        close();
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
      {devices.length > 0 && (
        <select className="pull-input" value={device} aria-label="device"
          onChange={(e) => { setDevice(e.target.value); setSensorSet(""); }}>
          {devices.map((d) => (
            <option key={d.id} value={d.id}>{d.name}</option>
          ))}
        </select>
      )}
      <input className="pull-input" value={shot}
        onChange={(e) => setShot(e.target.value)} placeholder="shot number" />
      <select className="pull-input" value={analysis} disabled={!!sensorSet}
        onChange={(e) => setAnalysis(e.target.value)}>
        <option value="rotating">rotating</option>
        <option value="quasi-stationary">quasi-stationary</option>
        <option value="both">both</option>
      </select>
      {dev && dev.sensor_sets.length > 0 && (
        <>
          <select className="pull-input" value={sensorSet}
            onChange={(e) => setSensorSet(e.target.value)}>
            <option value="">— by analysis (above) —</option>
            <optgroup label={`${dev.name} sensor sets`}>
              {dev.sensor_sets.map((s) => (
                <option key={s} value={s}>{s}</option>
              ))}
            </optgroup>
          </select>
          {sensorSet && (
            <div className="note pull-hint">
              pulling the “{sensorSet}” sensor set (+ plasma params) — analysis
              selection is overridden
            </div>
          )}
        </>
      )}
      {/* Transport devices (KSTAR) reach MDS over their own VPN tunnel, so the
          cluster/mdsthin backend choice doesn't apply — hide it to avoid confusion. */}
      {dev?.needs_ssh_creds ? (
        <div className="note pull-hint">via the {dev.name} VPN tunnel</div>
      ) : (
        <select className="pull-input" value={backend}
          onChange={(e) => setBackend(e.target.value)}>
          <option value="remote">remote (cluster · fast)</option>
          <option value="mdsthin">mdsthin (laptop · slow, no cluster)</option>
          <option value="auto">auto</option>
        </select>
      )}

      {/* speed knobs — a window + decimation make a pull seconds instead of minutes */}
      <div className="pull-row">
        <input className="pull-input" value={tmin}
          onChange={(e) => setTmin(e.target.value)} placeholder="tmin ms" />
        <input className="pull-input" value={tmax}
          onChange={(e) => setTmax(e.target.value)} placeholder="tmax ms" />
        <input className="pull-input" value={decimate}
          onChange={(e) => setDecimate(e.target.value)} placeholder="decim." />
      </div>
      <div className="note pull-hint">
        window (ms) prefilled to flat-top — clear tmin/tmax for the whole shot
      </div>

      {needsCreds && (
        <>
          <div className="note pull-hint">
            {dev?.needs_ssh_creds
              ? "KFE VPN login — username, password, and a 2FA passcode (never push)"
              : "cluster address is built in — just your GA username; leave password blank if your SSH key is set up (else password + Duo)"}
          </div>
          <input className="pull-input" value={username}
            onChange={(e) => setUsername(e.target.value)}
            placeholder={dev?.needs_ssh_creds ? "KFE VPN username" : "GA username"}
            autoComplete="username" />
          <input className="pull-input" type="password" value={password}
            onChange={(e) => setPassword(e.target.value)}
            placeholder={dev?.needs_ssh_creds ? "KFE VPN password" : "GA password (blank if key auth)"}
            autoComplete="current-password" />
          <input className="pull-input" value={duoPasscode}
            onChange={(e) => setDuoPasscode(e.target.value)}
            placeholder={dev?.needs_ssh_creds ? "2FA passcode" : "Duo passcode"}
            inputMode="numeric" autoComplete="one-time-code" />
        </>
      )}

      {dev?.needs_ssh_creds && (
        <>
          <div className="note pull-hint">{dev.name} SSH login</div>
          {dev.connect_note && (
            <div className="note pull-hint">{dev.connect_note}</div>
          )}
          <input className="pull-input" value={sshUser}
            onChange={(e) => setSshUser(e.target.value)}
            placeholder={`${dev.name} SSH user`} autoComplete="username" />
          <input className="pull-input" type="password" value={sshPassword}
            onChange={(e) => setSshPassword(e.target.value)}
            placeholder={`${dev.name} SSH password`} autoComplete="current-password" />
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
