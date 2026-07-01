// Quasi-stationary view — OWNED BY TEAMMATE A.
// Branch: gui-quasistationary — build here, PR into `gui`.
// VISION §4.1, §7.
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type Plotly from "plotly.js-dist-min";
import { useStore } from "../../store";
import { apiBase, startFetch } from "../../lib/api";
import { useNode } from "../../lib/useNode";
import NodeView from "../../lib/NodeView";
import Plot from "../../lib/Plot";
import type { ContourNode, LineNode, MetricsNode } from "../../lib/contract";
import { phiPeak as phiPeakFn, phiRms as phiRmsFn } from "../../lib/qsTransforms";

// ── Colorblind-safe palette (Wong 2011) — for sensor/channel traces ──
const LINE_PALETTE = ["#0072B2", "#E69F00", "#56B4E9", "#D55E00", "#CC79A7", "#009E73", "#F0E442"];

// Excluded sensors are drawn on the maps but de-emphasised (thin grey dashes) so
// the user can still see where the deselected/broken probes sit.
const EXCLUDED_LINE = { color: "#888", width: 1, dash: "dot" as const };

// A valid PTDATA pointname (DIII-D custom-signal entry): letters/digits/underscore,
// e.g. `Ip`, `betan`, `bt`, `MPI66M020D`. Anything else is rejected before fetch.
const POINTNAME_RE = /^[A-Za-z0-9_]+$/;

// Shown when a fetch is attempted (or would stall) without the left-rail credentials.
const CREDS_HINT =
  "Enter your username in the left “Pull a shot” panel (plus password/Duo if your "
  + "account needs them) to fetch new signals.";

// ── Mode-number palette — green/purple/red for n=1,2,3,… ─────────────
// Clearly distinct hues so each mode reads immediately, not blue/orange.
const MODE_PALETTE = ["#2ca02c", "#9467bd", "#d62728", "#8c564b", "#e377c2", "#bcbd22", "#17becf"];

// ── Light-mode Plotly overrides ───────────────────────────────────────
const LT_AXIS = {
  gridcolor: "#e2e8f0", zerolinecolor: "#94a3b8",
  linecolor: "#94a3b8", tickcolor: "#94a3b8",
};
const LT_BASE: Partial<Plotly.Layout> = {
  plot_bgcolor: "#f8fafc",
  font: { family: "IBM Plex Mono, ui-monospace, monospace", size: 11, color: "#1a2332" },
};

// ── Hooks & helpers ───────────────────────────────────────────────────
function useDarkMode(): boolean {
  return useStore((s) => s.theme === "dark");
}

function themedLayout(
  dark: boolean,
  overrides: Partial<Plotly.Layout>,
): Partial<Plotly.Layout> {
  if (dark) return overrides;
  return {
    ...LT_BASE,
    ...overrides,
    xaxis: { ...LT_AXIS, ...(overrides.xaxis as object) },
    yaxis: { ...LT_AXIS, ...(overrides.yaxis as object) },
  };
}

function hexToRgba(hex: string, alpha: number): string {
  const r = parseInt(hex.slice(1, 3), 16);
  const g = parseInt(hex.slice(3, 5), 16);
  const b = parseInt(hex.slice(5, 7), 16);
  return `rgba(${r},${g},${b},${alpha})`;
}

// Build Plotly traces from a LineNode, optionally with per-series visibility overrides.
function lineTraces(
  node: LineNode,
  opts?: { visible?: boolean[]; opacity?: number[]; palette?: string[] },
): Partial<Plotly.PlotData>[] {
  const sigma = node.meta?.sigma as number[][] | undefined;
  const pal = opts?.palette ?? LINE_PALETTE;
  const traces: Partial<Plotly.PlotData>[] = [];

  node.series.forEach((s, i) => {
    const color = pal[i % pal.length];
    const sig = sigma?.[i];
    const vis = opts?.visible?.[i] !== false;
    const opacity = opts?.opacity?.[i] ?? 1;

    if (sig && vis) {
      traces.push({
        type: "scatter", mode: "lines", x: s.x,
        y: s.y.map((v, j) => v + sig[j]),
        line: { width: 0, color }, showlegend: false, hoverinfo: "skip",
        opacity,
      } as Partial<Plotly.PlotData>);
      traces.push({
        type: "scatter", mode: "lines", x: s.x,
        y: s.y.map((v, j) => v - sig[j]),
        fill: "tonexty", fillcolor: hexToRgba(color, 0.45 * opacity),
        line: { width: 0, color }, showlegend: false, hoverinfo: "skip",
        opacity,
      } as Partial<Plotly.PlotData>);
    }

    traces.push({
      type: "scatter", mode: "lines", name: s.name, x: s.x, y: s.y,
      line: { color, width: 1.5 },
      visible: vis ? true : "legendonly",
      opacity,
    } as Partial<Plotly.PlotData>);
  });

  return traces;
}

// ── Sensor arrays most useful for QS analysis ────────────────────────
const CHANNEL_FILTERS = [
  "Bp LFS midplane",
  "Bp LFS midplane bdot",
  "Bp LFS R+1",
  "Bp LFS R-1",
  "Bp LFS R+2",
  "Bp LFS R-2",
  "All LFS Bp Arrays",
  "Bp HFS +midplane",
  "Bp HFS -midplane",
];

// ── Collapsible section header ────────────────────────────────────────
function CollapseHeader({
  open, onToggle, children,
}: { open: boolean; onToggle: () => void; children: React.ReactNode }) {
  return (
    <div
      onClick={onToggle}
      style={{
        display: "flex", alignItems: "center", gap: 6, cursor: "pointer",
        userSelect: "none", marginBottom: open ? 6 : 0,
      }}
      className="metrics-title"
    >
      <span style={{ fontSize: 9 }}>{open ? "▼" : "▶"}</span>
      {children}
    </div>
  );
}

// ── Component ─────────────────────────────────────────────────────────
export default function QuasiStationaryTab({ machine }: { machine: string }) {
  const dark = useDarkMode();
  const { cursorMs, setCursorMs } = useStore();

  // ── Analysis settings ─────────────────────────────────────────────
  const [ns, setNs]               = useState("1,2,3");
  const [ms, setMs]               = useState("0");
  const [channelFilter, setChannelFilter] = useState("Bp LFS midplane");
  const [detrendType, setDetrendType]     = useState("baseline");
  const [detrendLo, setDetrendLo] = useState("");
  const [detrendHi, setDetrendHi] = useState("");
  const [tminMs, setTminMs]       = useState("");  // "" = auto (read from HDF5)
  const [tmaxMs, setTmaxMs]       = useState("");
  const [colormapChoice, setColormapChoice] = useState<"rdbu" | "cividis" | "viridis">("rdbu");

  // ── Section collapse state ────────────────────────────────────────
  const [fitQualityOpen, setFitQualityOpen] = useState(false);
  const [channelsMapOpen, setChannelsMapOpen] = useState(false);  // fit-channel excludes + φ-θ map
  const [customOpen, setCustomOpen]         = useState(false);    // custom-signal panel

  // ── Sensor-signals view: overlay (default) or one axes per sensor ──
  const [signalStacked, setSignalStacked] = useState(false);

  // ── Channels the user has deselected from the fit (checkbox panel). These are
  // dropped from the quasi-stationary fit (fit_exclude) but stay drawn — greyed — on the
  // sensor maps and signal plots. Reset when the array (channelFilter) changes.
  const [excludedChannels, setExcludedChannels] = useState<Set<string>>(new Set());
  const toggleExcluded = useCallback((ch: string) => {
    setExcludedChannels(prev => {
      const next = new Set(prev);
      if (next.has(ch)) next.delete(ch); else next.add(ch);
      return next;
    });
  }, []);

  // ── Deferred fetch: only compute when user clicks Plot ────────────
  const [committedParams, setCommittedParams] = useState<Record<string, string> | null>(null);

  const qsParams = useMemo(() => {
    const p: Record<string, string> = {
      ns, ms,
      channel_filter: channelFilter,
      detrend_type: detrendType,
    };
    if (detrendLo && detrendHi) {
      p.detrend_lo = detrendLo;
      p.detrend_hi = detrendHi;
    }
    if (tminMs) p.tmin_ms = tminMs;
    if (tmaxMs) p.tmax_ms = tmaxMs;
    // Sorted so the param string is stable (identical exclusion set → same fetch key).
    const excl = Array.from(excludedChannels).sort().join(",");
    if (excl) p.fit_exclude = excl;
    return p;
  }, [ns, ms, channelFilter, detrendType, detrendLo, detrendHi, tminMs, tmaxMs, excludedChannels]);

  useEffect(() => {
    if (cursorMs === 0) setCursorMs(3140);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Linked time-axis zoom (declared here so the trim-window effect below can reset it).
  const [timeRange, setTimeRange] = useState<[number, number] | null>(null);

  // When the trim window changes, clear any user zoom so the axis re-fits to the new data.
  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- reset zoom to refit the axis on a new trim window
    setTimeRange(null);
  }, [tminMs, tmaxMs]);

  // A different array has different channels, so stale exclusions don't apply.
  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- clear exclusions on array change
    setExcludedChannels(new Set());
  }, [channelFilter]);

  // Auto-commit on mount so plots load immediately without requiring a click.
  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- initial commit to trigger fetch on mount
    setCommittedParams(qsParams);
    // eslint-disable-next-line react-hooks/exhaustive-deps -- intentionally run once on mount only
  }, []);

  // When Plot is clicked (committedParams changes), reset zoom to fit new data.
  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- reset zoom when new computation is triggered
    setTimeRange(null);
  }, [committedParams]);

  // null fetchMachine suppresses all useNode fetches until initial commit fires.
  const fetchMachine = committedParams !== null ? machine : null;
  // Highlight the Plot button when settings have drifted from the last commit.
  const paramsDirty = committedParams !== null && committedParams !== qsParams;

  // Per-plot export helpers: a stable filename + the download descriptor (node id +
  // the params that produced it) so each figure exports its own image + HDF5 data.
  const dl = useCallback(
    (nodeId: string) => ({ machine, nodeId, params: committedParams ?? {} }),
    [machine, committedParams],
  );
  const xn = useCallback((nodeId: string) => `shot_${machine}_${nodeId}`, [machine]);

  // ── Node fetches — gated by fetchMachine (null until Plot is clicked) ──
  const { node: qualityRaw } = useNode(fetchMachine, "fit_quality", committedParams ?? {});
  const qualityNode = qualityRaw?.kind === "metrics" ? (qualityRaw as MetricsNode) : null;

  // Time-series nodes
  const { node: phiTimeNode }                   = useNode(fetchMachine, "phi_t",      committedParams ?? {});
  const { node: ampNode, error: ampError }       = useNode(fetchMachine, "amplitude",   committedParams ?? {});
  const { node: phaseTimeNode }                 = useNode(fetchMachine, "phase_t",     committedParams ?? {});

  // Sensor map (φ-θ only; the R-Z cross-section lives in the Sensors tab), signal
  // conditioning, fit quality time series.
  const { node: sensorCylRaw }   = useNode(fetchMachine, "sensor_map_cylindrical", committedParams ?? {});
  const { node: signalRaw }      = useNode(fetchMachine, "signal_conditioning",    committedParams ?? {});
  const { node: chiSqRaw }       = useNode(fetchMachine, "chi_sq_t",               committedParams ?? {});
  const { node: fitResRaw }      = useNode(fetchMachine, "fit_residuals",          committedParams ?? {});

  // No-data guard: 404 means the shot's HDF5 file hasn't been pulled yet.
  const noData = committedParams !== null && ampError?.includes("fetch failed (404)") === true;
  // Fit-unavailable guard: a non-404 error means the quasi-stationary fit couldn't run
  // (most often the shot was pulled for rotating-mode analysis and lacks the Bp
  // LFS midplane array). Show the reason instead of a perpetual "loading…".
  const fitUnavailable = committedParams !== null && !noData && ampError != null;
  const fitError = ampError?.replace(/^Error:\s*fetch failed \(\d+\):\s*/, "") ?? "";

  const sensorCylNode = sensorCylRaw?.kind === "line" ? (sensorCylRaw as LineNode) : null;
  const signalNode    = signalRaw?.kind    === "line" ? (signalRaw    as LineNode) : null;
  const chiSqNode     = chiSqRaw?.kind     === "line" ? (chiSqRaw     as LineNode) : null;
  const fitResNode    = fitResRaw?.kind    === "line" ? (fitResRaw    as LineNode) : null;

  // ── Custom user signals (Ip, Dα, …): fetch → merge into the h5 → plot ─────
  const fetchCreds = useStore((s) => s.fetchCreds);
  const [customText, setCustomText]     = useState("");            // entry box (persisted)
  const [committedSignals, setCommittedSignals] = useState("");    // comma list, drives the node
  const [customBusy, setCustomBusy]     = useState(false);
  const [customFrac, setCustomFrac]     = useState(0);
  const [customMsg, setCustomMsg]       = useState<string | null>(null);
  const customEsRef = useRef<EventSource | null>(null);
  useEffect(() => () => customEsRef.current?.close(), []);  // close stream on unmount

  const { node: extraRaw } = useNode(
    committedSignals ? machine : null, "extra_signals", { signals: committedSignals },
  );
  const extraNode = extraRaw?.kind === "line" ? (extraRaw as LineNode) : null;
  const extraMissing = (extraNode?.meta?.missing as string[] | undefined) ?? [];

  // Tokenise the entry box (comma- or space-separated) and validate each name as a
  // PTDATA pointname before we spend a network round-trip. Invalid tokens block the
  // fetch and are surfaced to the user; "not found" (a valid but absent pointname)
  // is a separate, server-side signal reported via extraMissing.
  const customTokens = useMemo(
    () => customText.split(/[\s,]+/).map(s => s.trim()).filter(Boolean),
    [customText],
  );
  const invalidTokens = useMemo(
    () => customTokens.filter(t => !POINTNAME_RE.test(t)),
    [customTokens],
  );
  const customValid = customTokens.length > 0 && invalidTokens.length === 0;

  // Fetching new data needs the same backend + credentials as the left-rail pull.
  // remote/mdsthin both require a GA username (password/Duo too unless key auth) —
  // without it the cluster job hangs at 0%, so we block up-front with a clear hint.
  const needsCreds = fetchCreds.backend === "remote" || fetchCreds.backend === "mdsthin";
  const credsMissing = needsCreds && !fetchCreds.username.trim();

  const plotCustomSignals = useCallback(() => {
    const names = customText.split(/[\s,]+/).map(s => s.trim()).filter(Boolean);
    if (!names.length || names.some(n => !POINTNAME_RE.test(n))) return;
    if (!apiBase()) { setCustomMsg("✗ no live backend configured — set VITE_API_BASE to fetch data"); return; }
    if (credsMissing) { setCustomMsg(`✗ ${CREDS_HINT}`); return; }
    setCustomBusy(true); setCustomFrac(0); setCustomMsg("fetching…");
    void (async () => {
      try {
        const { job_id } = await startFetch({
          shot: Number(machine),
          signals: names,
          backend: fetchCreds.backend,
          username: fetchCreds.username || undefined,
          password: fetchCreds.password || undefined,
          duo: fetchCreds.duoMode === "push" ? "1" : fetchCreds.duoPasscode || undefined,
          device: fetchCreds.deviceId || undefined,
        });
        customEsRef.current?.close();
        const es = new EventSource(`${apiBase()}/api/fetch/${job_id}/stream`);
        customEsRef.current = es;
        // Watchdog: if the job never moves off 0% it is almost always a stuck
        // login (missing/incorrect password or an unanswered Duo push). Surface a
        // credentials hint instead of an eternal 0% spinner. Held in a const box so
        // `close` can clear it without a use-before-assign dance.
        const timer: { id?: ReturnType<typeof setTimeout> } = {};
        const close = () => {
          clearTimeout(timer.id);
          es.close();
          if (customEsRef.current === es) customEsRef.current = null;
        };
        let moved = false;
        timer.id = setTimeout(() => {
          close();
          setCustomMsg(`✗ no progress after 30s — likely a login issue. ${CREDS_HINT}`);
          setCustomBusy(false);
        }, 30000);
        es.onmessage = (e: MessageEvent) => {
          const f = JSON.parse(e.data as string);
          setCustomFrac(f.progress ?? 0);
          setCustomMsg(f.msg ?? null);
          if (!moved && (f.progress ?? 0) > 0) { moved = true; clearTimeout(timer.id); }
          if (f.status === "done") {
            close();
            setCommittedSignals(names.join(","));  // triggers the extra_signals node fetch
            setCustomMsg(`✓ fetched ${names.length} signal(s)`);
            setCustomBusy(false);
          } else if (f.status === "error") {
            close();
            setCustomMsg(`✗ ${f.error}`);
            setCustomBusy(false);
          }
        };
        es.onerror = () => {
          close();
          setCustomMsg("✗ progress stream lost (the pull may still be running)");
          setCustomBusy(false);
        };
      } catch (e) {
        setCustomMsg(String(e));
        setCustomBusy(false);
      }
    })();
  }, [customText, machine, fetchCreds, credsMissing]);

  const phiTimePlot = phiTimeNode?.kind === "contour" ? (phiTimeNode as ContourNode) : null;

  const phiPeak = useMemo(
    () => (phiTimePlot ? phiPeakFn(phiTimePlot.z, phiTimePlot.y) : null),
    [phiTimePlot],
  );

  const phiRms = useMemo(
    () => (phiTimePlot ? phiRmsFn(phiTimePlot.z) : null),
    [phiTimePlot],
  );

  const seekTo = useCallback((e: Plotly.PlotMouseEvent) => {
    const x = e.points?.[0]?.x;
    if (x != null) setCursorMs(Math.round(Number(x)));
  }, [setCursorMs]);

  // ── Linked time-axis zoom (state declared above) ──────────────────
  const handleTimeRelayout = useCallback((e: Record<string, unknown>) => {
    if (e["xaxis.autorange"] === true) {
      setTimeRange(null);
    } else if (e["xaxis.range[0]"] != null) {
      setTimeRange([Number(e["xaxis.range[0]"]), Number(e["xaxis.range[1]"])]);
    }
  }, []);

  // ── Shared time axis ──────────────────────────────────────────────
  const tMin = useMemo(() =>
    ampNode?.kind === "line" ? Math.round((ampNode as LineNode).series[0]?.x[0] ?? 800) : 800,
  [ampNode]);
  const tMax = useMemo(() =>
    ampNode?.kind === "line" ? Math.round((ampNode as LineNode).series[0]?.x.at(-1) ?? 6100) : 6100,
  [ampNode]);
  const timeXAxis = useMemo(
    () => ({ range: timeRange ?? [tMin, tMax] }),
    [timeRange, tMin, tMax],
  );

  // ── Sensor map plot (φ-θ unrolled) ────────────────────────────────
  // Remap phi values from 0–360 to –180–180 for the unrolled plot.
  const sensorCylData = useMemo((): Partial<Plotly.PlotData>[] => {
    if (!sensorCylNode) return [];
    return sensorCylNode.series.map((s, i) => ({
      type: "scatter" as const, mode: "lines" as const,
      name: s.name,
      x: (s.x as number[]).map(v => v > 180 ? v - 360 : v),
      y: s.y,
      line: excludedChannels.has(s.name)
        ? EXCLUDED_LINE
        : { color: LINE_PALETTE[i % LINE_PALETTE.length], width: 2 },
    } as Partial<Plotly.PlotData>));
  }, [sensorCylNode, excludedChannels]);

  const sensorCylLayout = useMemo(() =>
    themedLayout(dark, {
      xaxis: { title: { text: sensorCylNode?.axes.x ?? "φ (deg)" }, range: [-180, 180], dtick: 90 },
      yaxis: { title: { text: sensorCylNode?.axes.y ?? "θ (deg)" }, range: [-180, 180], dtick: 90 },
      showlegend: false,
      margin: { t: 4, b: 40, l: 48, r: 8 },
    } as Partial<Plotly.Layout>),
  [dark, sensorCylNode]);

  // ── Shared y-range: signal conditioning + residuals ───────────────
  const signalYRange = useMemo(() => {
    if (!signalNode) return null;
    let lo = Infinity, hi = -Infinity;
    for (const s of signalNode.series)
      for (const v of s.y as number[]) { if (v < lo) lo = v; if (v > hi) hi = v; }
    return [lo, hi] as [number, number];
  }, [signalNode]);

  const sharedSigResRange = useMemo(() => {
    if (!signalYRange && !fitResNode) return null;
    let lo = signalYRange?.[0] ?? Infinity;
    let hi = signalYRange?.[1] ?? -Infinity;
    for (const s of fitResNode?.series ?? [])
      for (const v of s.y as number[]) { if (v < lo) lo = v; if (v > hi) hi = v; }
    return [lo, hi] as [number, number];
  }, [signalYRange, fitResNode]);

  // ── Signal conditioning plots ─────────────────────────────────────
  // Channel raw/prepared pairs: the master channel list for this array (fit_exclude
  // does not drop channels from prep, so every array channel appears here).
  const signalPairs = signalNode?.meta?.pairs as
    { channel: string; prepared_idx: number; raw_idx: number }[] | undefined;

  // Build the two traces (prepared + raw) for one sensor pair. Reused by the overlay
  // plot and the stacked one-axes-per-sensor view. Excluded sensors are greyed.
  const pairTraces = useCallback((
    pair: { channel: string; prepared_idx: number; raw_idx: number }, pIdx: number,
  ): Partial<Plotly.PlotData>[] => {
    if (!signalNode) return [];
    const excluded = excludedChannels.has(pair.channel);
    const color = excluded ? "#888" : LINE_PALETTE[pIdx % LINE_PALETTE.length];
    const prep = signalNode.series[pair.prepared_idx];
    const raw  = signalNode.series[pair.raw_idx];
    const traces: Partial<Plotly.PlotData>[] = [];
    if (prep) {
      traces.push({
        type: "scatter" as const, mode: "lines" as const,
        name: prep.name, x: prep.x, y: prep.y,
        line: { color, width: 1.5, ...(excluded ? { dash: "dot" as const } : {}) },
      } as Partial<Plotly.PlotData>);
    }
    if (raw) {
      traces.push({
        type: "scatter" as const, mode: "lines" as const,
        name: raw.name, x: raw.x, y: raw.y,
        line: { color, width: 1, dash: "dot" as const },
        opacity: 0.55, showlegend: false,
      } as Partial<Plotly.PlotData>);
    }
    return traces;
  }, [signalNode, excludedChannels]);

  const signalData = useMemo((): Partial<Plotly.PlotData>[] => {
    if (!signalNode) return [];
    if (!signalPairs) return lineTraces(signalNode);
    return signalPairs.flatMap((pair, pIdx) => pairTraces(pair, pIdx));
  }, [signalNode, signalPairs, pairTraces]);

  const signalLayout = useMemo(() =>
    signalNode ? themedLayout(dark, {
      xaxis: { ...timeXAxis, title: { text: signalNode.axes.x } },
      yaxis: {
        title: { text: signalNode.axes.y },
        ...(sharedSigResRange ? { range: sharedSigResRange } : {}),
      },
      showlegend: false,
      margin: { t: 4, b: 34, l: 60, r: 20 },
    } as Partial<Plotly.Layout>) : {},
  [dark, signalNode, timeXAxis, sharedSigResRange]);

  // ── Dynamic chi² y-range ──────────────────────────────────────────
  const chiSqYRange = useMemo(() => {
    if (!chiSqNode) return null;
    const vals = (chiSqNode.series[0].y as number[]).filter((v: number) => v > 0);
    if (!vals.length) return null;
    const lo = Math.min(...vals), hi = Math.max(...vals);
    return [Math.floor(Math.log10(lo * 0.5)), Math.ceil(Math.log10(hi * 2))];
  }, [chiSqNode]);

  // ── Chi-squared plot ──────────────────────────────────────────────
  const chiSqData = useMemo((): Partial<Plotly.PlotData>[] => {
    if (!chiSqNode) return [];
    return [{
      type: "scatter" as const, mode: "lines" as const,
      name: "χ²", x: chiSqNode.series[0].x, y: chiSqNode.series[0].y,
      line: { color: LINE_PALETTE[0], width: 1.5 },
    } as Partial<Plotly.PlotData>];
  }, [chiSqNode]);

  const chiSqLayout = useMemo(() =>
    chiSqNode ? themedLayout(dark, {
      xaxis: { ...timeXAxis, title: { text: chiSqNode.axes.x } },
      yaxis: {
        title: { text: "χ²" }, type: "log" as const,
        ...(chiSqYRange ? { range: chiSqYRange } : {}),
      },
      shapes: [
        { type: "line" as const, x0: 0, x1: 1, xref: "paper" as const,
          y0: 0, y1: 0, yref: "y" as const,
          line: { color: dark ? "#aaa" : "#555", width: 1, dash: "dash" as const } },
      ],
      showlegend: false,
      margin: { t: 4, b: 40, l: 60, r: 20 },
    } as Partial<Plotly.Layout>) : {},
  [dark, chiSqNode, timeXAxis, chiSqYRange]);

  // ── Fit residuals plot ────────────────────────────────────────────
  const worstChannels = useMemo(() => {
    if (!fitResNode) return new Set<string>();
    const ptps = fitResNode.series.map(s => {
      const lo = Math.min(...s.y), hi = Math.max(...s.y);
      return { name: s.name, ptp: hi - lo };
    });
    ptps.sort((a, b) => b.ptp - a.ptp);
    return new Set(ptps.slice(0, 6).map(p => p.name));
  }, [fitResNode]);

  const fitResData = useMemo((): Partial<Plotly.PlotData>[] => {
    if (!fitResNode) return [];
    return fitResNode.series.map((s, i) => {
      const isWorst = worstChannels.has(s.name);
      return {
        type: "scatter" as const, mode: "lines" as const,
        name: s.name, x: s.x, y: s.y,
        line: {
          color: LINE_PALETTE[i % LINE_PALETTE.length],
          width: isWorst ? 2 : 1,
        },
        opacity: isWorst ? 1 : 0.4,
      } as Partial<Plotly.PlotData>;
    });
  }, [fitResNode, worstChannels]);

  const fitResLayout = useMemo(() =>
    fitResNode ? themedLayout(dark, {
      xaxis: { ...timeXAxis, title: { text: fitResNode.axes.x }, showticklabels: false },
      yaxis: {
        title: { text: "residual (T)" },
        ...(sharedSigResRange ? { range: sharedSigResRange } : {}),
      },
      showlegend: false,
      margin: { t: 4, b: 4, l: 60, r: 20 },
    } as Partial<Plotly.Layout>) : {},
  [dark, fitResNode, sharedSigResRange, timeXAxis]);

  // ── Section 8: phi_t waterfall ────────────────────────────────────
  const cmapProps = useMemo(() => {
    if (colormapChoice === "cividis") return { colorscale: "Cividis", reversescale: false };
    if (colormapChoice === "viridis") return { colorscale: "Viridis", reversescale: false };
    return { colorscale: "RdBu", reversescale: true };  // RdBu_r ≈ notebook matplotlib
  }, [colormapChoice]);

  const phiTimeData = useMemo((): Partial<Plotly.PlotData>[] => {
    if (!phiTimePlot) return [];
    const [zmin, zmax] = phiTimePlot.zrange ?? [-42, 42];
    const traces: Partial<Plotly.PlotData>[] = [{
      type: "heatmap" as const,
      x: phiTimePlot.x, y: phiTimePlot.y, z: phiTimePlot.z,
      ...cmapProps,
      zmin, zmax,
      zsmooth: false,
      showscale: true,
      colorbar: { title: { text: "Fit" }, thickness: 12, outlinewidth: 0 },
    } as Partial<Plotly.PlotData>];
    if (phiPeak) {
      traces.push({
        type: "scatter" as const, mode: "markers" as const,
        x: phiTimePlot.x, y: phiPeak,
        marker: { symbol: "circle-open" as const, size: 4, color: "white", line: { width: 1, color: "white" } },
        hoverinfo: "skip" as const, showlegend: false,
      } as Partial<Plotly.PlotData>);
    }
    return traces;
  }, [phiTimePlot, phiPeak, cmapProps]);

  const phiTimeLayout = useMemo(() =>
    phiTimePlot ? themedLayout(dark, {
      xaxis: { ...timeXAxis, title: { text: phiTimePlot.axes.x } },
      yaxis: { title: { text: phiTimePlot.axes.y }, range: [0, 360], dtick: 90, tickvals: [0, 90, 180, 270, 360] },
      margin: { t: 4, b: 40, l: 60, r: 80 },
    } as Partial<Plotly.Layout>) : {},
  [dark, phiTimePlot, timeXAxis]);

  // ── Section 7: amplitude & phase ─────────────────────────────────
  const ampData = useMemo(() =>
    ampNode?.kind === "line" ? lineTraces(ampNode as LineNode, { palette: MODE_PALETTE }) : [],
  [ampNode]);

  const ampLayout = useMemo(() =>
    ampNode?.kind === "line" ? themedLayout(dark, {
      xaxis: { ...timeXAxis, title: { text: (ampNode as LineNode).axes.x } },
      yaxis: { title: { text: (ampNode as LineNode).axes.y }, rangemode: "tozero" as const },
      showlegend: true,
      legend: {
        orientation: "h" as const, y: 1.18, font: { size: 10 },
        title: { text: String((ampNode as LineNode).meta?.legend_title ?? "n"), font: { size: 10 } },
      },
      margin: { t: 16, b: 48, l: 60, r: 80 },
    } as Partial<Plotly.Layout>) : {},
  [dark, ampNode, timeXAxis]);

  const phaseTimeData = useMemo(() => {
    if (phaseTimeNode?.kind !== "line") return [];
    const phaseVisible = (phaseTimeNode as LineNode).meta?.phase_visible as boolean[] | undefined;
    return lineTraces(phaseTimeNode as LineNode, { visible: phaseVisible, palette: MODE_PALETTE });
  }, [phaseTimeNode]);

  const phaseTimeLayout = useMemo(() =>
    phaseTimeNode?.kind === "line" ? themedLayout(dark, {
      xaxis: { ...timeXAxis, title: { text: (phaseTimeNode as LineNode).axes.x } },
      yaxis: {
        title: { text: (phaseTimeNode as LineNode).axes.y },
        range: [-180, 180],
        tickvals: [-180, -90, 0, 90, 180],
      },
      showlegend: true,
      legend: { orientation: "h" as const, y: 1.18, font: { size: 10 } },
      margin: { t: 16, b: 48, l: 60, r: 80 },
    } as Partial<Plotly.Layout>) : {},
  [dark, phaseTimeNode, timeXAxis]);

  return (
    <div className="card" style={{ display: "flex", flexDirection: "column", gap: 10 }}>
      <div>
        <h2>Quasi-stationary — spatial fit δB<sub>p</sub>(φ, θ)</h2>
        <p className="desc" style={{ margin: 0 }}>shot {machine}</p>
      </div>

      {/* ── Settings bar ──────────────────────────────────────────────── */}
      <div style={{ display: "flex", flexWrap: "wrap", gap: 8, alignItems: "center", fontSize: 11, color: "var(--text-dim)", borderBottom: "1px solid var(--border)", paddingBottom: 8 }}>
        <label style={{ display: "flex", alignItems: "center", gap: 4 }}>
          Array
          <select value={channelFilter} onChange={e => setChannelFilter(e.target.value)}
            style={{ fontSize: 11, background: "var(--panel)", color: "var(--text)", border: "1px solid var(--border)", borderRadius: 3, padding: "1px 4px" }}>
            {CHANNEL_FILTERS.map(f => <option key={f} value={f}>{f}</option>)}
          </select>
        </label>
        <label style={{ display: "flex", alignItems: "center", gap: 4 }}>
          n modes
          <input value={ns} onChange={e => setNs(e.target.value)}
            style={{ width: 60, fontSize: 11, background: "var(--panel)", color: "var(--text)", border: "1px solid var(--border)", borderRadius: 3, padding: "1px 4px" }} />
        </label>
        <label style={{ display: "flex", alignItems: "center", gap: 4 }}>
          m modes
          <input value={ms} onChange={e => setMs(e.target.value)}
            style={{ width: 40, fontSize: 11, background: "var(--panel)", color: "var(--text)", border: "1px solid var(--border)", borderRadius: 3, padding: "1px 4px" }} />
        </label>
        <label style={{ display: "flex", alignItems: "center", gap: 4 }}>
          Detrend
          <select value={detrendType} onChange={e => setDetrendType(e.target.value)}
            style={{ fontSize: 11, background: "var(--panel)", color: "var(--text)", border: "1px solid var(--border)", borderRadius: 3, padding: "1px 4px" }}>
            <option value="baseline">baseline</option>
            <option value="none">none</option>
            <option value="linear">linear</option>
            <option value="endpoints">endpoints</option>
          </select>
        </label>
        {detrendType !== "none" && (
          <label style={{ display: "flex", alignItems: "center", gap: 4 }}>
            band (ms)
            <input placeholder="auto" value={detrendLo} onChange={e => setDetrendLo(e.target.value)}
              style={{ width: 52, fontSize: 11, background: "var(--panel)", color: "var(--text)", border: "1px solid var(--border)", borderRadius: 3, padding: "1px 4px" }} />
            –
            <input placeholder="auto" value={detrendHi} onChange={e => setDetrendHi(e.target.value)}
              style={{ width: 52, fontSize: 11, background: "var(--panel)", color: "var(--text)", border: "1px solid var(--border)", borderRadius: 3, padding: "1px 4px" }} />
          </label>
        )}
        <label style={{ display: "flex", alignItems: "center", gap: 4 }}>
          t trim (ms)
          <input placeholder="auto" value={tminMs} onChange={e => setTminMs(e.target.value)}
            style={{ width: 52, fontSize: 11, background: "var(--panel)", color: "var(--text)", border: "1px solid var(--border)", borderRadius: 3, padding: "1px 4px" }} />
          –
          <input placeholder="auto" value={tmaxMs} onChange={e => setTmaxMs(e.target.value)}
            style={{ width: 52, fontSize: 11, background: "var(--panel)", color: "var(--text)", border: "1px solid var(--border)", borderRadius: 3, padding: "1px 4px" }} />
        </label>
        <div style={{ marginLeft: "auto", display: "flex", alignItems: "center", gap: 6 }}>
          {paramsDirty && (
            <span style={{ fontSize: 10, color: "var(--text-dim)" }}>settings changed</span>
          )}
          <button
            onClick={() => setCommittedParams(qsParams)}
            style={{
              fontSize: 11, padding: "2px 10px", borderRadius: 3, cursor: "pointer",
              background: paramsDirty ? "var(--accent)" : "var(--panel)",
              color: paramsDirty ? "#fff" : "var(--text-dim)",
              border: "1px solid var(--border)",
              fontWeight: paramsDirty ? 600 : 400,
            }}
          >
            Plot
          </button>
        </div>
      </div>

      {/* ── Plot content — show immediately; message only if data unavailable ── */}
      {noData ? (
        <div style={{ padding: 16, border: "1px solid var(--border)", borderRadius: 4,
                      color: "var(--text-dim)", fontSize: 12, lineHeight: 1.6 }}>
          <strong>No data for shot {machine}.</strong><br />
          The HDF5 file for this shot has not been fetched yet.<br />
          Use the <strong>pull panel</strong> in the left sidebar to fetch the data, then click Plot.
        </div>
      ) : fitUnavailable ? (
        <div style={{ padding: 16, border: "1px solid var(--border)", borderRadius: 4,
                      color: "var(--text-dim)", fontSize: 12, lineHeight: 1.6 }}>
          <strong>No quasi-stationary fit for shot {machine}.</strong><br />
          The quasi-stationary fit needs the Bp LFS midplane array; this shot was most likely
          fetched for rotating-mode analysis only. Re-fetch it with the quasi-stationary
          channels, or choose a QS-capable shot.<br />
          <span style={{ opacity: 0.7 }}>reason: {fitError}</span>
        </div>
      ) : (<>

      {/* ── Fit channels + sensor map (φ-θ) — collapsed by default, above the main plots ── */}
      <div>
        <CollapseHeader open={channelsMapOpen} onToggle={() => setChannelsMapOpen(o => !o)}>
          fit channels &amp; sensor map{excludedChannels.size > 0 ? ` · ${excludedChannels.size} excluded` : ""}
        </CollapseHeader>
        {channelsMapOpen && (
          <div style={{ display: "flex", gap: 12, alignItems: "flex-start" }}>
            {/* left — checkbox grid: deselect sensors from the fit */}
            <div style={{ flex: "0 0 300px" }}>
              <div style={{ fontSize: 10, opacity: 0.7, marginBottom: 4 }}>
                unchecked sensors are dropped from the fit (they stay drawn, greyed, on the map) — click Plot to apply
              </div>
              {signalPairs ? (
                <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "2px 10px", fontSize: 10, color: "var(--text-dim)" }}>
                  {signalPairs.map((pair, i) => {
                    const included = !excludedChannels.has(pair.channel);
                    return (
                      <label key={pair.channel} style={{ display: "flex", alignItems: "center", gap: 4, cursor: "pointer" }}>
                        <input type="checkbox" checked={included}
                          onChange={() => toggleExcluded(pair.channel)}
                          style={{ accentColor: LINE_PALETTE[i % LINE_PALETTE.length] }} />
                        <span style={{ color: included ? LINE_PALETTE[i % LINE_PALETTE.length] : "#888",
                          textDecoration: included ? "none" : "line-through" }}>
                          {pair.channel}
                        </span>
                      </label>
                    );
                  })}
                </div>
              ) : <div className="placeholder">loading channels…</div>}
            </div>
            {/* right — φ-θ unrolled sensor map (R-Z lives in the Sensors tab) */}
            <div style={{ flex: 1, minWidth: 0 }}>
              <div style={{ fontSize: 10, color: "var(--text-dim)", marginBottom: 2 }}>unrolled φ-θ · {channelFilter}</div>
              {sensorCylNode
                ? <Plot height={300} data={sensorCylData} layout={sensorCylLayout} exportName={xn("sensor_map_cylindrical")} download={dl("sensor_map_cylindrical")} />
                : <div className="placeholder" style={{ height: 300 }}>loading…</div>
              }
            </div>
          </div>
        )}
      </div>

      {/* ── Section D+E: Time-series results — PRIMARY, at top ────────── */}
      <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
        {/* Section 8: Contour φ–t heatmap */}
        {phiTimePlot && (
          <div>
            <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap", marginBottom: 4 }}>
              <div className="metrics-title">δB<sub>p</sub>(φ, t) · Contour — θ = 0°</div>
              {(["rdbu", "cividis", "viridis"] as const).map(cm => (
                <button key={cm} onClick={() => setColormapChoice(cm)}
                  style={{
                    fontSize: 10, padding: "1px 6px", borderRadius: 3, cursor: "pointer",
                    background: colormapChoice === cm ? "var(--accent)" : "var(--panel)",
                    color: colormapChoice === cm ? "#fff" : "var(--text-dim)",
                    border: "1px solid var(--border)",
                  }}>
                  {cm === "rdbu" ? "default" : cm}
                </button>
              ))}
            </div>
            {phiRms && (
              <Plot height={70} data={[{
                type: "scatter" as const, mode: "lines" as const,
                x: phiTimePlot.x, y: phiRms,
                line: { color: LINE_PALETTE[0], width: 1.5 },
                showlegend: false,
              } as Partial<Plotly.PlotData>]} layout={themedLayout(dark, {
                xaxis: { ...timeXAxis, showticklabels: false },
                yaxis: { title: { text: "RMS (G)" }, rangemode: "tozero" as const },
                margin: { t: 4, b: 4, l: 60, r: 80 },
              } as Partial<Plotly.Layout>)} onClick={seekTo} onRelayout={handleTimeRelayout} exportName={xn("phi_rms")} download={dl("phi_t")} />
            )}
            <Plot height={400} data={phiTimeData} layout={phiTimeLayout} onClick={seekTo} onRelayout={handleTimeRelayout} exportName={xn("phi_t")} download={dl("phi_t")} />
          </div>
        )}

        {/* Section 7: Mode amplitude & phase */}
        {ampNode?.kind === "line" && (
          <Plot height={200} data={ampData} layout={ampLayout} onClick={seekTo} onRelayout={handleTimeRelayout} exportName={xn("amplitude")} download={dl("amplitude")} />
        )}
        {phaseTimeNode?.kind === "line" && (
          <Plot height={200} data={phaseTimeData} layout={phaseTimeLayout} onClick={seekTo} onRelayout={handleTimeRelayout} exportName={xn("phase_t")} download={dl("phase_t")} />
        )}
      </div>

      {/* ── Custom user signals (Ip, Dα, …) — collapsible, above the sensor signals ── */}
      <div>
        <CollapseHeader open={customOpen} onToggle={() => setCustomOpen(o => !o)}>
          custom signals
        </CollapseHeader>
        {customOpen && (
          <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
            <div className="note" style={{ fontSize: 10, opacity: 0.75 }}>
              Enter one or more <strong>signal names</strong> — PTDATA pointnames or
              EFIT scalars — comma- or space-separated (e.g. <code>Ip, betan, bt</code>).
              Names are letters, digits and underscores only; each is fetched via the
              same backend/credentials as the left-rail pull and merged into this shot.
            </div>
            <div style={{ display: "flex", gap: 6, alignItems: "center", flexWrap: "wrap" }}>
              <input value={customText} onChange={e => setCustomText(e.target.value)}
                placeholder="Ip, betan, bt"
                title="Comma- or space-separated signal names — PTDATA pointnames or EFIT scalars (letters, digits, underscore). Example: Ip, betan, bt"
                aria-label="custom PTDATA pointnames"
                aria-invalid={invalidTokens.length > 0}
                onKeyDown={e => { if (e.key === "Enter") plotCustomSignals(); }}
                style={{ flex: 1, minWidth: 200, fontSize: 11, background: "var(--panel)", color: "var(--text)",
                  border: `1px solid ${invalidTokens.length > 0 ? "var(--danger, #d64550)" : "var(--border)"}`,
                  borderRadius: 3, padding: "2px 6px" }} />
              <button onClick={plotCustomSignals} disabled={customBusy || !customValid}
                title={
                  customTokens.length === 0 ? "Enter at least one pointname"
                    : invalidTokens.length > 0 ? `Invalid: ${invalidTokens.join(", ")}`
                    : credsMissing ? CREDS_HINT
                    : "Fetch these signals and plot them"
                }
                style={{ fontSize: 11, padding: "2px 10px", borderRadius: 3,
                  cursor: (customBusy || !customValid) ? "not-allowed" : "pointer",
                  opacity: (customBusy || !customValid) ? 0.5 : 1,
                  background: "var(--accent)", color: "#fff", border: "1px solid var(--border)" }}>
                {customBusy ? `fetching… ${Math.round(customFrac * 100)}%` : "Fetch & plot"}
              </button>
            </div>
            {invalidTokens.length > 0 && (
              <div className="note" style={{ fontSize: 10, color: "var(--danger, #d64550)" }}>
                not a valid pointname: {invalidTokens.join(", ")} — use letters, digits and underscores only
              </div>
            )}
            {credsMissing && invalidTokens.length === 0 && (
              <div className="note" style={{ fontSize: 10, color: "var(--warn, #d0972e)" }}>
                ⚠ {CREDS_HINT}
              </div>
            )}
            {customBusy && (
              <div className="pull-bar"><div className="pull-bar-fill" style={{ width: `${customFrac * 100}%` }} /></div>
            )}
            {customMsg && <div className="note" style={{ fontSize: 10 }}>{customMsg}</div>}
            {extraMissing.length > 0 && (
              <div className="note" style={{ fontSize: 10 }}>not found: {extraMissing.join(", ")}</div>
            )}
            {extraNode?.series.map((s, i) => (
              <Plot key={s.name} height={130}
                data={[{
                  type: "scatter" as const, mode: "lines" as const,
                  name: s.name, x: s.x, y: s.y,
                  line: { color: LINE_PALETTE[i % LINE_PALETTE.length], width: 1.5 },
                  showlegend: false,
                } as Partial<Plotly.PlotData>]}
                layout={themedLayout(dark, {
                  xaxis: { ...timeXAxis, title: { text: "time (ms)" } },
                  yaxis: { title: { text: s.name, font: { size: 9 } } },
                  showlegend: false,
                  margin: { t: 4, b: 34, l: 64, r: 20 },
                } as Partial<Plotly.Layout>)}
                onClick={seekTo} onRelayout={handleTimeRelayout}
                exportName={xn(`custom_${s.name}`)} />
            ))}
          </div>
        )}
      </div>

      {/* ── Sensor signals (raw + prepared) — PRIMARY; overlay by default, stackable ── */}
      <div>
        <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap", marginBottom: 4 }}>
          <div className="metrics-title">sensor signals · raw + prepared</div>
          <button onClick={() => setSignalStacked(s => !s)}
            style={{ fontSize: 10, padding: "1px 6px", borderRadius: 3, cursor: "pointer",
              background: signalStacked ? "var(--accent)" : "var(--panel)",
              color: signalStacked ? "#fff" : "var(--text-dim)", border: "1px solid var(--border)" }}>
            {signalStacked ? "overlay" : "stack per sensor"}
          </button>
          {/* One style legend for the whole section: solid = prepared, dotted = raw. */}
          <span style={{ display: "inline-flex", alignItems: "center", gap: 10, fontSize: 10, color: "var(--text-dim)" }}>
            <span style={{ display: "inline-flex", alignItems: "center", gap: 4 }}>
              <svg width={20} height={8} aria-hidden="true">
                <line x1={0} y1={4} x2={20} y2={4} stroke="currentColor" strokeWidth={1.5} />
              </svg>
              prepared
            </span>
            <span style={{ display: "inline-flex", alignItems: "center", gap: 4 }}>
              <svg width={20} height={8} aria-hidden="true">
                <line x1={0} y1={4} x2={20} y2={4} stroke="currentColor" strokeWidth={1} strokeDasharray="2 2" />
              </svg>
              raw
            </span>
          </span>
        </div>
        {!signalNode ? (
          <div className="placeholder" style={{ height: 240 }}>loading signals…</div>
        ) : signalStacked && signalPairs ? (
          <div>
            {signalPairs.map((pair, i) => {
              const isLast = i === signalPairs.length - 1;
              return (
                <Plot key={pair.channel} height={isLast ? 96 : 74}
                  data={pairTraces(pair, i)}
                  layout={themedLayout(dark, {
                    xaxis: { ...timeXAxis, showticklabels: isLast,
                      ...(isLast ? { title: { text: signalNode.axes.x } } : {}) },
                    yaxis: { title: { text: pair.channel, font: { size: 8 } }, showticklabels: false },
                    showlegend: false,
                    margin: { t: 2, b: isLast ? 34 : 2, l: 92, r: 20 },
                  } as Partial<Plotly.Layout>)}
                  onClick={seekTo} onRelayout={handleTimeRelayout}
                  exportName={xn(`signal_${pair.channel}`)} />
              );
            })}
          </div>
        ) : (
          <Plot height={240} data={signalData} layout={signalLayout} onClick={seekTo} onRelayout={handleTimeRelayout}
            exportName={xn("signal_conditioning")} download={dl("signal_conditioning")} />
        )}
      </div>

      {/* ── Section C: Fit Quality — collapsible (residuals + χ² + metrics) ── */}
      <div>
        <CollapseHeader open={fitQualityOpen} onToggle={() => setFitQualityOpen(o => !o)}>
          fit quality
        </CollapseHeader>
        {fitQualityOpen && (
          <div style={{ display: "flex", gap: 10 }}>
            <div style={{ flex: 1, minWidth: 0 }}>
              {/* Residuals — top */}
              {fitResNode
                ? <Plot height={150} data={fitResData} layout={fitResLayout} onClick={seekTo} onRelayout={handleTimeRelayout} exportName={xn("fit_residuals")} download={dl("fit_residuals")} />
                : <div className="placeholder" style={{ height: 150 }}>loading residuals…</div>
              }
              {/* Chi² — bottom */}
              {chiSqNode
                ? <Plot height={130} data={chiSqData} layout={chiSqLayout} onClick={seekTo} onRelayout={handleTimeRelayout} exportName={xn("chi_sq_t")} download={dl("chi_sq_t")} />
                : <div className="placeholder" style={{ height: 130 }}>loading χ²…</div>
              }
            </div>
            <div style={{ width: 190, flexShrink: 0 }}>
              {qualityNode && <NodeView node={qualityNode} download={dl("fit_quality")} />}
            </div>
          </div>
        )}
      </div>
      </>)}
    </div>
  );
}
