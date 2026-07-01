// Trigger a live mdsthin/remote pull from the GUI and stream its REAL progress.
// Only shown when a live backend is configured. Credentials are entered here and
// sent to the LOCAL backend (localhost) only — not stored.
//
// Flow: POST /api/fetch starts a background job → we open an EventSource on
// /api/fetch/{job_id}/stream → a real per-channel progress bar fills → on done we
// refresh the shot list and select the new shot. Set a window (tmin/tmax) +
// decimation to make a pull seconds instead of minutes.
import { useEffect, useRef, useState } from "react";
import { apiBase, fetchDevices, startFetch, usingLiveBackend, type DeviceInfo } from "../lib/api";
import { useStore } from "../store";

export default function PullControl() {
  const init = useStore((s) => s.init);
  const setMachine = useStore((s) => s.setMachine);
  const [shot, setShot] = useState("184927");
  const [analysis, setAnalysis] = useState("rotating");
  // Default to the fast cluster path. `mdsthin` (laptop tunnel) streams raw float
  // over the SSH tunnel — minutes; `remote` fetches on the cluster and ships back a
  // compressed h5 — tens of seconds. Users without cluster access pick mdsthin.
  const [backend, setBackend] = useState("remote");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  // Duo two-factor: a push (sends "1") or a typed passcode. A dropdown makes the
  // choice explicit; the passcode box only appears when "passcode" is selected.
  const [duoMode, setDuoMode] = useState<"push" | "passcode">("push");
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
  const [devices, setDevices] = useState<DeviceInfo[]>([]);
  const [deviceId, setDeviceId] = useState("");
  const [sensorSet, setSensorSet] = useState("");
  const [busy, setBusy] = useState(false);
  const [frac, setFrac] = useState(0);
  const [msg, setMsg] = useState<string | null>(null);
  // Live EventSource for the in-flight pull, kept in a ref so the unmount cleanup can
  // close it. Without this, navigating away mid-pull leaks the stream and its handlers
  // fire setState on an unmounted component.
  const esRef = useRef<EventSource | null>(null);

  // Snap backend / sensor-set / window / shot to sensible per-device defaults. A
  // tree device (NSTX) has no cluster and no analysis→signal map, so it must use
  // mdsthin + a sensor set, over a NARROW window (its raw signals are ~15 MHz and
  // seconds long — a wide window is gigabytes). Called from event handlers (device
  // change, initial load) — NOT a synchronous effect (react-hooks/set-state-in-effect).
  function snapDeviceDefaults(dev: DeviceInfo) {
    const tree = dev.access === "mdsplus_tree";
    setBackend(dev.remote_capable ? "remote" : "mdsthin");
    setSensorSet(tree ? (dev.sensor_sets[0] ?? "") : "");
    setTmin(tree ? "250" : "1000");
    setTmax(tree ? "350" : "5000");
    if (dev.default_shot != null) setShot(String(dev.default_shot));
  }

  // load supported devices; default the picker to the first one + its defaults (the
  // setState calls run in an async .then callback, not synchronously in the effect)
  useEffect(() => {
    void fetchDevices().then((ds) => {
      setDevices(ds);
      if (ds[0] && !deviceId) {
        setDeviceId(ds[0].id);
        snapDeviceDefaults(ds[0]);
      }
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // close any open pull stream when the component unmounts
  useEffect(() => () => esRef.current?.close(), []);
  const device = devices.find((d) => d.id === deviceId);
  // A tree device (NSTX/NSTX-U) pulls ONLY via mdsthin + a named sensor set; only a
  // device with a cluster block can use the fast `remote` backend (DIII-D).
  const isTree = device?.access === "mdsplus_tree";
  const remoteCapable = device?.remote_capable ?? false;

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
        duo: duoMode === "push" ? "1" : duoPasscode || undefined,
        tmin: num(tmin),
        tmax: num(tmax),
        decimate: num(decimate),
        // device drives the gateway/server + which sensor_sets exist; a chosen
        // sensor-set overrides the analysis groups (backend semantics).
        device: deviceId || undefined,
        sensor_set: sensorSet || undefined,
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
        <select className="pull-input" value={deviceId} aria-label="device"
          onChange={(e) => {
            const d = devices.find((x) => x.id === e.target.value);
            setDeviceId(e.target.value);
            if (d) snapDeviceDefaults(d);
          }}>
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
      {device && device.sensor_sets.length > 0 && (
        <>
          <select className="pull-input" value={sensorSet}
            onChange={(e) => setSensorSet(e.target.value)}>
            {/* a tree device (NSTX) has no analysis groups — a sensor set is required */}
            {!isTree && <option value="">— by analysis (above) —</option>}
            <optgroup label={`${device.name} sensor sets`}>
              {device.sensor_sets.map((s) => (
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
      <select className="pull-input" value={backend}
        onChange={(e) => setBackend(e.target.value)}>
        {remoteCapable && <option value="remote">remote (cluster · fast)</option>}
        <option value="mdsthin">
          mdsthin ({isTree ? "MDSplus tree · direct" : "laptop · slow, no cluster"})
        </option>
        {remoteCapable && <option value="auto">auto</option>}
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
      <div className="note pull-hint">
        {isTree
          ? "window (ms) — keep it NARROW: raw signals are ~15 MHz, so a wide window pulls gigabytes"
          : "window (ms) prefilled to flat-top — clear tmin/tmax for the whole shot"}
      </div>

      {needsCreds && (
        <>
          <div className="note pull-hint">
            the data host + gateway are built in — enter your{" "}
            {device ? device.name : "site"} username; leave password blank if key/Duo
            auth is set up (else password + Duo)
          </div>
          <input className="pull-input" value={username}
            onChange={(e) => setUsername(e.target.value)}
            placeholder="username" autoComplete="username" />
          <input className="pull-input" type="password" value={password}
            onChange={(e) => setPassword(e.target.value)}
            placeholder="password (blank if key/Duo auth)"
            autoComplete="current-password" />
          <div className="note pull-hint">Duo two-factor</div>
          <select className="pull-input" value={duoMode} aria-label="Duo authentication"
            onChange={(e) => setDuoMode(e.target.value as "push" | "passcode")}>
            <option value="push">Push notification</option>
            <option value="passcode">Enter passcode…</option>
          </select>
          {duoMode === "passcode" && (
            <input className="pull-input" value={duoPasscode}
              onChange={(e) => setDuoPasscode(e.target.value)}
              placeholder="Duo passcode" inputMode="numeric" autoComplete="one-time-code" />
          )}
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
