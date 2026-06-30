import { useState, useMemo, useEffect, useCallback } from "react";
import type * as Plotly from "plotly.js";
import { useStore } from "../../store";
import { useNode } from "../../lib/useNode";
import { MODE_PALETTE, POWER_SEQUENTIAL, FIELD_DIVERGING, modeColor } from "../../lib/colormaps";
import Plot from "../../lib/Plot";
import NodeView from "../../lib/NodeView";
import DraggableDivider from "../../lib/DraggableDivider";
import { usingLiveBackend, fetchChannelUsage, type ChannelUsage } from "../../lib/api";
import type { Node } from "../../lib/contract";

// p-th percentile of a numeric array (linear interpolation). Used by the power gate
// to pick a noise-floor threshold from the visible cells. NOTE: sorts `values` in
// place — callers pass freshly-built throwaway arrays, so we skip the copy to keep
// slider scrubbing allocation-free.
function percentile(values: number[], p: number): number {
  if (values.length === 0) return -Infinity;
  const s = values.sort((a, b) => a - b);
  if (p <= 0) return s[0];
  if (p >= 100) return s[s.length - 1];
  const idx = (p / 100) * (s.length - 1);
  const lo = Math.floor(idx);
  const hi = Math.ceil(idx);
  return s[lo] + (s[hi] - s[lo]) * (idx - lo);
}

// Power-gate slider mapping. The slider position is linear in [0, 1000] but the
// percentile it selects follows a log curve in the "headroom" (100 − percentile):
// the top of the travel resolves finely (e.g. 97 → 99.5%) where the noise floor
// matters, instead of a coarse 1%-per-step linear scale.
const GATE_POS_MAX = 1000;
const GATE_H_LO = 100; // headroom at pos 0   → 0th percentile (show everything)
const GATE_H_HI = 0.5; // headroom at pos max → 99.5th percentile (tightest crop)
function gatePosToPct(pos: number): number {
  const t = Math.min(1, Math.max(0, pos / GATE_POS_MAX));
  const h = Math.exp(Math.log(GATE_H_LO) * (1 - t) + Math.log(GATE_H_HI) * t);
  return Math.round((100 - h) * 10) / 10; // 0.1%-resolution percentile
}
// Slider position that yields ≈70% by default (a sensible noise floor to start).
const GATE_POS_DEFAULT = 227;

// Offline synthetic-demo constants. These were formerly user-facing knobs (PEST λ and
// sensor-shielding cutoff) that only ever affected the no-backend demo — they have no
// effect on real data — so they're fixed at their old defaults. (Bt-compensation mode is
// likewise fixed to its old "digital" default, inlined where the demo noise is computed.)
const DEMO_PEST_L1 = 0.35; // PEST θ* toroidicity coefficient
const DEMO_PEST_L2 = 0.05; // PEST θ* elongation coefficient
const DEMO_SHIELD_CUTOFF_KHZ = 50; // 3 dB sensor-shielding cutoff

// Deterministic mock generator helper (keeps React render pure)
function generateDeterministicTimeTrace(timeSlice: number, freqPeaks: number[]) {
  const times: number[] = [];
  const values: number[] = [];
  const duration = 2.0; // ms
  const numPoints = 80;
  for (let i = 0; i < numPoints; i++) {
    const t = timeSlice - duration / 2 + (i * duration) / numPoints;
    times.push(t);
    // Sum of sines matching peak frequencies + deterministic pseudo-random noise
    let val = Math.sin(i * 9.87) * 0.15; // deterministic noise
    freqPeaks.forEach((f, fIdx) => {
      // f in kHz, t in ms
      const amplitude = fIdx === 0 ? 1.5 : 0.6;
      val += amplitude * Math.sin(2 * Math.PI * f * t);
    });
    values.push(val);
  }
  return { times, values };
}

// Honest placeholder shown in LIVE mode wherever a panel has no real backend node
// (loading, or a view not yet wired). Guarantees the GUI never shows fabricated/demo
// data against a live backend.
function PanelPlaceholder({ text, height = 200 }: { text: string; height?: number }) {
  return (
    <div style={{
      height, display: "flex", alignItems: "center", justifyContent: "center",
      color: "var(--text-dim)", fontSize: "11px", textAlign: "center", padding: "12px",
      border: "1px dashed var(--border)", borderRadius: "4px",
    }}>
      {text}
    </div>
  );
}

export default function RotatingTab({ machine }: { machine: string }) {
  const { cursorMs, setCursorMs } = useStore();
  // Foreground ink that flips with the theme so the raw dB/dt trace stays visible on
  // the light plot background (it was hard-coded white → invisible in light mode).
  const dark = useStore((s) => s.theme === "dark");
  const ink = dark ? "rgba(255,255,255,0.85)" : "rgba(20,34,46,0.9)";
  
  // View states
  const [displayMode, setDisplayMode] = useState<"n" | "power">("n");
  const [sidebarExpanded, setSidebarExpanded] = useState<boolean>(true);
  const [channelInfo, setChannelInfo] = useState<ChannelUsage | null>(null);

  // Control Parameter states
  const [fmin, setFmin] = useState<number>(0);
  const [fmax, setFmax] = useState<number>(50);
  const [fittype, setFittype] = useState<number>(2); // 0 = circular, 1 = toroidicity, 2 = PEST theta*
  const [smoothing, setSmoothing] = useState<number>(5);
  // Power gate: a percentile floor on cell power; hides low-power noise in BOTH the
  // power spectrogram (client-side) and the n-map (server n_amp_pct). The slider stores
  // a linear position; gatePosToPct maps it to a percentile that scrubs finely near 100%.
  // gateFrac is its 0–1 form for the synthetic fallback.
  const [gatePos, setGatePos] = useState<number>(GATE_POS_DEFAULT);
  const powerGate = gatePosToPct(gatePos);
  const gateFrac = powerGate / 100;
  // STFT window for the LIVE backend spectrogram (ms). Frequency resolution is
  // 1/window, so 2 ms → 500 Hz bins (sharper than the 1 ms / 1 kHz default).
  const [specSliceMs, setSpecSliceMs] = useState<number>(2);

  // Advanced Parameter states
  const [advancedExpanded, setAdvancedExpanded] = useState<boolean>(false);
  const [fftWindow, setFftWindow] = useState<number>(512);
  const [fftOverlap, setFftOverlap] = useState<number>(75);
  const [probePhi1, setProbePhi1] = useState<number>(307);
  const [probePhi2, setProbePhi2] = useState<number>(340);
  // θ origin (deg) for the 2D modal pattern: pans the periodic poloidal axis so this
  // angle sits at the plot's origin. Default 90° (top of the machine).
  const [patternCut, setPatternCut] = useState<number>(90);

  // Resizable layout dimensions
  const [sidebarWidth, setSidebarWidth] = useState(260);
  const [specHeight, setSpecHeight] = useState(360);
  const [panel1Height, setPanel1Height] = useState(330);
  const [panel2Height, setPanel2Height] = useState(290);
  const [panel3Height, setPanel3Height] = useState(290);
  const [subintervalLeftWidth, setSubintervalLeftWidth] = useState(340);
  const [arrayLeftWidth, setArrayLeftWidth] = useState(380);
  const [modeLeftWidth, setModeLeftWidth] = useState(380);

  // Drag handlers for resizable dividers — each adjusts adjacent pane sizes
  const handleSidebarDelta = useCallback((d: number) => {
    setSidebarWidth(w => Math.max(40, Math.min(500, w + d)));
  }, []);
  const handleSpecDelta = useCallback((d: number) => {
    setSpecHeight(h => Math.max(200, h + d));
    setPanel1Height(h => Math.max(150, h - d));
  }, []);
  const handlePanel12Delta = useCallback((d: number) => {
    setPanel1Height(h => Math.max(150, h + d));
    setPanel2Height(h => Math.max(150, h - d));
  }, []);
  const handlePanel23Delta = useCallback((d: number) => {
    setPanel2Height(h => Math.max(150, h + d));
    setPanel3Height(h => Math.max(150, h - d));
  }, []);
  const handleSubintervalSplit = useCallback((d: number) => {
    setSubintervalLeftWidth(w => Math.max(100, Math.min(800, w + d)));
  }, []);
  const handleArraySplit = useCallback((d: number) => {
    setArrayLeftWidth(w => Math.max(100, Math.min(800, w + d)));
  }, []);
  const handleModeSplit = useCallback((d: number) => {
    setModeLeftWidth(w => Math.max(100, Math.min(800, w + d)));
  }, []);

  // --- 1. DATA INGESTION & FALLBACKS ---
  // STFT-shaping params shared by every spectral node so they hit one backend
  // compute (the cached `_spec_result`) and land on an identical (t, f) grid —
  // which lets the real coherence map gate the power/mode maps cell-for-cell.
  // fmin/fmax crop the band server-side (a cheap re-mask of the cached STFT, not a
  // recompute) so we transport only the displayed 0–fmax kHz, not the full Nyquist
  // band ×3 nodes. These don't depend on the time cursor, so scrubbing never refetches.
  // `smoothing` is the coherence-estimation window (backend `coherence_smooth`): it
  // re-runs the core and changes the real coherence map → the sub-interval coherence trace.
  const specParams = { slice_duration: specSliceMs / 1000, max_columns: 1000, fmin, fmax, smoothing };

  // Fetch main spectrogram node (real log-power Ḃp(t,f) from the live backend)
  const {
    node: specNode,
    loading: specLoading,
    error: specError,
  } = useNode(machine, "spectrogram", specParams);

  // Real toroidal mode-number map n(t,f) — a full-array fit per cell (resolves n=1,2,3,4…
  // that the 2-point estimate aliases away). Backs the "Mode n" toggle, gated server-side.
  // Honors the same resolution knob + band as the power view so the two stay consistent.
  const { node: modeNumberNode } = useNode(machine, "mode_number", {
    slice_duration: specSliceMs / 1000, fmin, fmax, n_amp_pct: powerGate,
  });

  // Real 2-point coherence γ²(t,f) ∈ [0,1] — feeds the coherence gate honestly,
  // instead of the previous power-derived stand-in.
  const { node: coherenceNode } = useNode(machine, "coherence", specParams);

  // Fetch toroidal phase fit node (from static files if available)
  const {
    node: phaseNode,
  } = useNode(machine, "phase_fit", { time: cursorMs });

  // Fetch the GP-smoothed toroidal mode shape with 2σ uncertainty band (eigspec §2.2.2)
  const {
    node: modeShapeNode,
  } = useNode(machine, "mode_shape", { time: cursorMs });

  // Fetch the GP-smoothed poloidal mode shape (real DIII-D θ; needs the MPID array)
  const {
    node: poloidalShapeNode,
  } = useNode(machine, "poloidal_shape", { time: cursorMs });

  // Fetch the 2D (θ,φ) modal pattern on real DIII-D geometry (eigspec eq 23).
  // 422s when the shot lacks the poloidal array — the panel simply hides then.
  const {
    node: modePatternNode,
  } = useNode(machine, "mode_pattern", { time: cursorMs });

  // Fetch the full-array shape-coherence-over-time track (eigspec fig 9).
  // Cursor-independent (reference is the strongest-mode slice), so no time param.
  const {
    node: modeTrackNode,
  } = useNode(machine, "mode_track");

  // Fetch the best-fit toroidal mode number n(t) over the shot (appears/persists/locks).
  // Cursor-independent (global dominant frequency), so no time param.
  const {
    node: modeOverTimeNode,
  } = useNode(machine, "mode_over_time");

  // Array wave-stripes: raw δBp(φ,t) / δBp(θ,t) over a few mode periods at the cursor.
  const { node: toroidalStripesNode } = useNode(machine, "toroidal_stripes", { time: cursorMs });
  const { node: poloidalStripesNode } = useNode(machine, "poloidal_stripes", { time: cursorMs });

  // Poloidal phase fit (phase vs θ, φ-detrended, best-fit m) — the poloidal analogue
  // of phase_fit. 422s when the shot lacks the poloidal array; the panel hides then.
  const { node: poloidalPhaseFitNode } = useNode(machine, "poloidal_phase_fit", { time: cursorMs });

  // One Mirnov probe's raw dB/dt time series in a 4 ms window around the cursor.
  const { node: rawTraceNode } = useNode(machine, "raw_trace", { time: cursorMs });

  // Auto-initialize the time cursor to the start of the data range
  useEffect(() => {
    if (specNode && specNode.kind === "heatmap" && specNode.x.length > 0) {
      const startTime = specNode.x[0];
      const endTime = specNode.x[specNode.x.length - 1];
      // If cursor is uninitialized or outside the spectrogram window, initialize to the beginning
      if (cursorMs < startTime || cursorMs > endTime) {
        setCursorMs(startTime);
      }
    }
  }, [specNode, cursorMs, setCursorMs]);

  // Which fetched pointnames the analysis actually uses — drives the collapsible
  // "Data Channels" diagnostic so idle probes can be trimmed from pulls. State is set
  // only from the async callbacks (never synchronously in the effect body, which would
  // trigger cascading renders): fetchChannelUsage resolves to null without a live
  // backend, so that case clears the panel through the same .then path.
  useEffect(() => {
    if (!machine) return;
    let alive = true;
    fetchChannelUsage(machine)
      .then((c) => { if (alive) setChannelInfo(c); })
      .catch(() => { if (alive) setChannelInfo(null); });
    return () => { alive = false; };
  }, [machine]);

  // Detect data source. `hasStaticFiles` only means a spec node loaded — it doesn't
  // say whether that node came from the live FastAPI backend (real shot data) or the
  // static mock JSON. The label keys off usingLiveBackend() so real data reads as the
  // device it came from (e.g. "DIII-D").
  const hasStaticFiles = !!specNode && !specError;
  const live = usingLiveBackend();
  // In LIVE mode no synthetic/mock data is ever produced (every generator below
  // short-circuits on `live`), so the source is always the live backend — labeled
  // with the device it came from (e.g. "DIII-D"); while a node loads we show a
  // loading state, never "Synthetic Generator".
  const deviceName = useStore((s) => s.machines).find((m) => m.id === machine)?.device;
  const dataSourceText = live
    ? `${deviceName ?? "Live backend"}${machine ? ` · shot ${machine}` : ""}`
    : hasStaticFiles ? "Mock fixtures (static demo)" : "Synthetic generator (demo)";
  const dataSourceColor = live
    ? "var(--good)"
    : hasStaticFiles ? "var(--accent)" : "var(--warn)";

  // --- 2. DYNAMIC SYNTHETIC DATA GENERATOR ---
  // When static files aren't found, we synthesize mode activity
  const syntheticSpecNode = useMemo(() => {
    if (live || hasStaticFiles) return null;  // never fabricate against a live backend

    // Fourier Uncertainty Principle Coupling:
    // Large window size -> higher frequency resolution (smaller df), lower time resolution (larger dt)
    const dt = (fftWindow / 512) * 10;   // dt = 5ms (for 256), 10ms (for 512), 20ms (for 1024), 40ms (for 2048)
    const df = (512 / fftWindow) * 0.2;  // df = 0.4kHz (for 256), 0.2kHz (for 512), 0.1kHz (for 1024), 0.05kHz (for 2048)

    const timesList = Array.from({ length: Math.round(3000 / dt) }, (_, i) => 1000 + i * dt);
    const freqsList = Array.from({ length: Math.round(50 / df) }, (_, i) => i * df);
    const zMatrix: number[][] = freqsList.map(() => new Array(timesList.length).fill(-3.0));

    timesList.forEach((t, tIdx) => {
      // Background noise
      freqsList.forEach((_, fIdx) => {
        // Deterministic pseudo-random background noise using sin
        zMatrix[fIdx][tIdx] = -2.5 - Math.sin(tIdx * 0.31 + fIdx * 0.17) * 0.5;
      });

      if (t >= 1500 && t <= 3200) {
        // Slowing tearing mode frequency (kHz)
        let modeFreq = 4.0;
        if (t < 2800) {
          const frac = (2800 - t) / 1300;
          modeFreq = 4.0 + 26.0 * frac * frac;
        }

        // Add n=2 peak
        const fIdxN2 = Math.round(modeFreq / df);
        if (fIdxN2 >= 0 && fIdxN2 < freqsList.length) {
          zMatrix[fIdxN2][tIdx] = -0.2 + Math.sin(tIdx * 0.43) * 0.1;
        }

        // Add n=1 peak at half frequency
        const fIdxN1 = Math.round((modeFreq / 2) / df);
        if (fIdxN1 >= 0 && fIdxN1 < freqsList.length) {
          zMatrix[fIdxN1][tIdx] = -0.9 + Math.sin(tIdx * 0.27) * 0.15;
        }

        // Add n=3 peak at 1.5x frequency (multiple modes)
        const fIdxN3 = Math.round((modeFreq * 1.5) / df);
        if (fIdxN3 >= 0 && fIdxN3 < freqsList.length) {
          zMatrix[fIdxN3][tIdx] = -0.7 + Math.sin(tIdx * 0.51) * 0.12;
        }
      }
    });

    return {
      kind: "heatmap" as const,
      x: timesList,
      y: freqsList,
      z: zMatrix,
      axes: { x: "Time (ms)", y: "f (kHz)", z: "log<sub>10</sub> power" },
      discrete: false,
    };
  }, [live, hasStaticFiles, fftWindow]);

  // Merge loaded specNode with controls/display settings
  const processedSpecNode = useMemo(() => {
    // ── LIVE BACKEND: render the real spectral nodes directly (no fabrication).
    if (hasStaticFiles) {
      // "n" → the array mode-number map: already band-cropped and quality-gated on the
      // server (its own STFT grid), so render it as-is — no client-side coherence gate.
      if (displayMode === "n") {
        if (!modeNumberNode || modeNumberNode.kind !== "heatmap") return null;
        // [-0.5,6.5] aligns the 7-colour |n| palette's bins to integers 0…6 (and modeColor()).
        return { ...modeNumberNode, discrete: true, zrange: [-0.5, 6.5] as [number, number] };
      }
      // "power" → real log-power spectrogram, gated by the power floor: cells below the
      // chosen percentile of the visible band's power are blanked (noise cropping).
      if (!specNode || specNode.kind !== "heatmap") return null;
      const keep = specNode.y
        .map((f, i) => ({ f, i }))
        .filter((o) => o.f >= fmin && o.f <= fmax)
        .map((o) => o.i);
      const y = keep.map((i) => specNode.y[i]);
      const rows = keep.map((fi) => specNode.z[fi]);
      const flat: number[] = [];
      for (const row of rows) for (const v of row) if (Number.isFinite(v)) flat.push(v);
      const floor = percentile(flat, powerGate);
      const z = rows.map((row) =>
        row.map((v) => (Number.isFinite(v) && v >= floor ? v : null)),
      );
      return { ...specNode, y, z: z as unknown as number[][], discrete: false, zrange: undefined };
    }

    // ── NO BACKEND: synthetic generator + fabricated n/coherence (demo only).
    const baseNode = syntheticSpecNode;
    if (!baseNode || baseNode.kind !== "heatmap") return null;

    // Filter by frequency limits
    const fIndices = baseNode.y
      .map((f, idx) => ({ f, idx }))
      .filter((item) => item.f >= fmin && item.f <= fmax)
      .map((item) => item.idx);

    // Filter and apply low-pass tile-shielding attenuation
    const filteredZ = fIndices.map((fIdx) => {
      const f = baseNode.y[fIdx];
      // first-order low-pass power attenuation: -5 * log10(1 + (f / fc)^2)
      const cutoffAttenDb = -5 * Math.log10(1 + Math.pow(f / DEMO_SHIELD_CUTOFF_KHZ, 2));
      return baseNode.z[fIdx].map((val) => val + cutoffAttenDb);
    });

    const filteredY = fIndices.map((idx) => baseNode.y[idx]);

    const allZ = filteredZ.flat().filter((v): v is number => v !== null && !isNaN(v));
    const zMin = allZ.length ? Math.min(...allZ) : -3;
    const zMax = allZ.length ? Math.max(...allZ) : 0;
    const powerThreshold = zMin + gateFrac * (zMax - zMin);

    if (displayMode === "n") {
      // Map log power values to discrete mode numbers (-6..6)
      const mappedZ = filteredZ.map((row, rowIdx) => {
        const f = filteredY[rowIdx];
        return row.map((val, colIdx) => {
          // Gating: filter out background noise cells
          if (val < powerThreshold) return null;

          const t = baseNode.x[colIdx];

          // 1. Synthetic Generator Case
          if (!hasStaticFiles) {
            if (t >= 1500 && t <= 3200) {
              let modeFreq = 4.0;
              if (t < 2800) {
                const frac = (2800 - t) / 1300;
                modeFreq = 4.0 + 26.0 * frac * frac;
              }
              const f1 = modeFreq;       // n = 2
              const f2 = modeFreq / 2;   // n = 1
              const f3 = modeFreq * 1.5; // n = 3

              if (Math.abs(f - f1) < 1.2) return 2;
              if (Math.abs(f - f2) < 1.0) return 1;
              if (Math.abs(f - f3) < 1.5) return 3;
            }
          }
          // 2. Static Mock File Case (e.g. 164672)
          else {
            // For shot 164672, the modes are at 2-3 kHz (n=1), 4-6 kHz (n=2), and 8-10 kHz (n=3)
            if (f >= 1.0 && f <= 3.2) return 1;
            if (f > 3.2 && f <= 6.5) return 2;
            if (f > 6.5 && f <= 11.0) return 3;
          }

          // Default fallback
          if (val > -1.2) return 2;
          if (val > -1.9) return 1;
          
          return null; // keep rest clean
        });
      });
      return {
        ...baseNode,
        x: baseNode.x,
        y: filteredY,
        z: mappedZ as unknown as number[][],
        discrete: true,
        zrange: [-0.5, 6.5] as [number, number],
      };
    } else {
      const mappedZ = filteredZ.map((row) =>
        row.map((val) => {
          // Gating: filter out background noise cells
          if (val < powerThreshold) return null;
          return val;
        })
      );
      return {
        ...baseNode,
        x: baseNode.x,
        y: filteredY,
        z: mappedZ as unknown as number[][],
        discrete: false,
        zrange: [-3, 0] as [number, number],
      };
    }
  }, [hasStaticFiles, specNode, modeNumberNode, syntheticSpecNode, displayMode, fmin, fmax, powerGate, gateFrac]);

  // Determine active mode frequencies at the current time slice
  const currentModeFreqs = useMemo(() => {
    const targetTime = cursorMs || 2000;
    if (targetTime >= 1500 && targetTime <= 3200) {
      let modeFreq = 4.0;
      if (targetTime < 2800) {
        const frac = (2800 - targetTime) / 1300;
        modeFreq = 4.0 + 26.0 * frac * frac;
      }
      return [modeFreq, modeFreq / 2, modeFreq * 1.5];
    }
    return [0.0, 0.0, 0.0];
  }, [cursorMs]);

  // Sliced Sub-interval spectrum arrays
  const subIntervalData = useMemo(() => {
    const baseNode = hasStaticFiles ? specNode : syntheticSpecNode;
    if (!baseNode || baseNode.kind !== "heatmap") {
      return { freqs: [], power: [], coh: [], nMode: [] };
    }

    // Find time column index closest to cursorMs
    let tIdx = 0;
    let minDiff = Infinity;
    baseNode.x.forEach((t, idx) => {
      const diff = Math.abs(t - cursorMs);
      if (diff < minDiff) {
        minDiff = diff;
        tIdx = idx;
      }
    });

    const freqs = baseNode.y;
    const power = freqs.map((_, fIdx) => Math.pow(10, baseNode.z[fIdx][tIdx])); // Convert log power to linear power

    // LIVE: real coherence + real mode number at the cursor column (same grid).
    const liveCoh = hasStaticFiles && coherenceNode?.kind === "heatmap" ? coherenceNode : null;
    const liveN = hasStaticFiles && modeNumberNode?.kind === "heatmap" ? modeNumberNode : null;

    const coh = liveCoh
      ? freqs.map((_, fIdx) => (liveCoh.z[fIdx] ? liveCoh.z[fIdx][tIdx] : 0))
      // Live but coherence node not yet loaded → zeros, never a synthesized stand-in.
      : live
      ? freqs.map(() => 0)
      // Fallback (mock demo only): synthesize coherence from power peaks.
      : power.map((p) => {
          const rawCoh = p > 0.05 ? 0.9 - (0.1 / p) : 0.15 + p * 2.0;
          return Math.max(0.0, Math.min(1.0, rawCoh));
        });

    const nMode = liveN
      ? (() => {
          // The array mode-number node has its own (t,f) grid → resolve by nearest cell.
          const nearest = (a: number[], v: number) => {
            let bi = 0, bd = Infinity;
            for (let i = 0; i < a.length; i++) { const d = Math.abs(a[i] - v); if (d < bd) { bd = d; bi = i; } }
            return bi;
          };
          const tiN = nearest(liveN.x, cursorMs);
          return freqs.map((f) => {
            const v = liveN.z[nearest(liveN.y, f)]?.[tiN];   // null where gated out
            return v == null ? 0 : v;
          });
        })()
      // Live but mode-number node not yet loaded → zeros, never a synthesized n.
      : live
      ? freqs.map(() => 0)
      // Fallback (mock demo only): synthesize mode number from the active-mode bands.
      : coh.map((c, fIdx) => {
          if (c < gateFrac) return 0;
          const f = freqs[fIdx];
          if (currentModeFreqs.some(mf => Math.abs(f - mf) < 1.0)) {
            if (Math.abs(f - currentModeFreqs[0]) < 1.0) return 2; // n=2
            if (Math.abs(f - currentModeFreqs[1]) < 1.0) return 1; // n=1
            if (currentModeFreqs[2] && Math.abs(f - currentModeFreqs[2]) < 1.0) return 3; // n=3
          }
          return 0;
        });

    // Power gate the n-markers: drop those whose cross-power is below the visible-band
    // percentile floor, so the same slider cleans this panel as the spectrogram.
    const pfloor = percentile(power.filter((p) => Number.isFinite(p)), powerGate);
    const nModeGated = nMode.map((v, i) => (power[i] >= pfloor ? v : 0));

    return { freqs, power, coh, nMode: nModeGated };
  }, [live, hasStaticFiles, specNode, modeNumberNode, coherenceNode, syntheticSpecNode, cursorMs, powerGate, gateFrac, currentModeFreqs]);

  // Toroidal & Poloidal wave stripes data (Array Tab)
  const arrayStripesData = useMemo(() => {
    // No backend node feeds the array wave-stripes yet → no demo data in live mode.
    if (live) return { times: [], phiAngles: [], thetaAngles: [], toroidalZ: [], poloidalZ: [] };
    const centerT = cursorMs || 2500;
    const times = Array.from({ length: 81 }, (_, i) => centerT - 20 + i * 0.5); // cursorMs +/- 20ms, step = 0.5 ms (double resolution!)
    const phiAngles = Array.from({ length: 72 }, (_, i) => i * 5); // 0 to 355 deg, step = 5 deg (double resolution!)
    const thetaAngles = Array.from({ length: 72 }, (_, i) => -100 + i * 5.5); // -100 to 290.5 deg, step = 5.5 deg (double resolution!)

    const targetFreq = currentModeFreqs[0];
    const omega1 = 2 * Math.PI * currentModeFreqs[0] * 1e-3; // cycles per ms
    const omega2 = 2 * Math.PI * currentModeFreqs[1] * 1e-3;
    const omega3 = 2 * Math.PI * currentModeFreqs[2] * 1e-3;

    const toroidalZ = phiAngles.map((phi) => {
      const phiRad = (phi * Math.PI) / 180;
      return times.map((t, tIdx) => {
        if (targetFreq === 0) return Math.sin(tIdx * 0.5 + phi * 0.1) * 2;
        // n=2, n=1, and n=3 wave propagation superposition
        return 15 * Math.sin(2 * phiRad - omega1 * t) +
               8 * Math.sin(1 * phiRad - omega2 * t) +
               5 * Math.sin(3 * phiRad - omega3 * t);
      });
    });

    const poloidalZ = thetaAngles.map((theta) => {
      const thetaRad = (theta * Math.PI) / 180;
      // PEST correction warping based on dynamic advanced inputs
      const thetaStar = thetaRad - DEMO_PEST_L1 * Math.sin(thetaRad) - DEMO_PEST_L2 * Math.sin(2 * thetaRad);
      return times.map((t, tIdx) => {
        if (targetFreq === 0) return Math.sin(tIdx * 0.4 + theta * 0.1) * 2;
        // m=3, m=2, and m=4 rotating waves superposition
        return 12 * Math.sin(3 * thetaStar - omega1 * t) +
               6 * Math.sin(2 * thetaStar - omega2 * t) +
               4 * Math.sin(4 * thetaStar - omega3 * t);
      });
    });

    return { times, phiAngles, thetaAngles, toroidalZ, poloidalZ };
  }, [live, cursorMs, currentModeFreqs]);

  // Mode structure poloidal node (synthetic demo; no backend poloidal-fit node wired yet)
  const processedPoloidalNode = useMemo(() => {
    if (live) return poloidalPhaseFitNode && poloidalPhaseFitNode.kind === "scatter2d"
      ? poloidalPhaseFitNode : null;
    const m = fittype === 2 ? 3 : fittype === 1 ? 2 : 1;
    const angles = Array.from({ length: 31 }, (_, i) => (i * 360) / 30); // 31 probes
    
    const points = angles.map((theta, i) => {
      const rad = (theta * Math.PI) / 180;
      
      // Calculate straight-field-line theta* depending on fittype
      let thetaStar = rad;
      if (fittype === 1) thetaStar = rad - DEMO_PEST_L1 * Math.sin(rad); // weak toroidicity
      if (fittype === 2) thetaStar = rad - DEMO_PEST_L1 * Math.sin(rad) - DEMO_PEST_L2 * Math.sin(2 * rad); // elongation

      const basePhase = (m * thetaStar) % (2 * Math.PI);
      const noise = Math.sin(i * 4.31) * 0.15; // deterministic pure noise

      // Bt misalignment compensation noise (Slide 39), digital compensation
      const btNoise = Math.sin(theta * 2.3 + 1.2) * 1.5;

      return {
        x: theta,
        y: (((basePhase + noise) * 180) / Math.PI + btNoise + 360) % 360,
        group: "Bp",
        error_y: 5.0 + Math.abs(btNoise) * 0.8 + (1.0 - gateFrac) * 10,
        error_x: 1.2, // 1.2 deg poloidal alignment error (Slide 32)
      };
    });

    const fitAngles = Array.from({ length: 37 }, (_, i) => i * 10);
    const fitPhases = fitAngles.map((a) => {
      const rad = (a * Math.PI) / 180;
      let thetaStar = rad;
      if (fittype === 1) thetaStar = rad - DEMO_PEST_L1 * Math.sin(rad);
      if (fittype === 2) thetaStar = rad - DEMO_PEST_L1 * Math.sin(rad) - DEMO_PEST_L2 * Math.sin(2 * rad);
      return ((m * thetaStar * 180) / Math.PI) % 360;
    });

    return {
      kind: "scatter2d" as const,
      points,
      fit: { x: fitAngles, y: fitPhases },
      axes: { x: "θ (deg)", y: "phase (deg)" },
      meta: { m_fit: m },
    };
  }, [live, poloidalPhaseFitNode, fittype, gateFrac]);

  // 2D modal pattern with the θ (poloidal) axis re-centred on `patternCut`. θ is
  // periodic, so we roll the rows so the cut angle sits at the origin and the axis runs
  // continuously cut … cut+360, with a closing row appended so the contour fills a
  // seamless full 360° as the slider moves; the probe-dot overlay is shifted to match.
  // Pure view transform on the real node — no refetch, so the slider is instant.
  const processedPatternNode = useMemo(() => {
    if (!modePatternNode || modePatternNode.kind !== "contour") return modePatternNode;
    const { y, z, overlay } = modePatternNode;
    const i = Math.max(0, y.findIndex((v) => v >= patternCut));
    const newY = [...y.slice(i), ...y.slice(0, i).map((v) => v + 360)];
    const newZ = [...z.slice(i), ...z.slice(0, i)];
    newY.push(newY[0] + 360);   // close the loop so the fill wraps with no seam
    newZ.push(newZ[0]);
    const newOverlay = overlay
      ? { ...overlay, points: overlay.points.map((p) => ({ ...p, y: p.y >= patternCut ? p.y : p.y + 360 })) }
      : overlay;
    return { ...modePatternNode, y: newY, z: newZ, overlay: newOverlay };
  }, [modePatternNode, patternCut]);

  // Toroidal node processing — real phase_fit node when present, else (mock only) synth.
  const processedToroidalNode = useMemo(() => {
    if (hasStaticFiles && phaseNode && phaseNode.kind === "scatter2d") {
      return phaseNode;
    }
    if (live) return null;  // live but phase_fit not loaded → placeholder, no synth
    // Synthesize toroidal fit (n = 2)
    const n = 2;
    // Add active probePhi1 and probePhi2 toroidal probe positions dynamically
    const angles = [0, 30, 55, 77, 105, 130, 155, 180, 205, 230, 255, 280, 310, 340, probePhi1, probePhi2];
    const points = angles.map((phi, i) => {
      const rad = (phi * Math.PI) / 180;
      const basePhase = (n * rad) % (2 * Math.PI);
      const noise = Math.sin(i * 7.42) * 0.08;
      
      // Bt misalignment compensation noise, digital compensation
      const btNoise = Math.sin(phi * 3.1 + 0.5) * 1.0;

      return {
        x: phi,
        y: (((basePhase + noise) * 180) / Math.PI + btNoise + 360) % 360,
        group: phi === probePhi1 || phi === probePhi2 ? "Selected Probe" : "Bp",
        error_y: 4.0 + Math.abs(btNoise) * 0.8 + (1.0 - gateFrac) * 8,
        error_x: 1.5, // 1.5 deg toroidal alignment error (Slide 32)
      };
    });

    const fitAngles = Array.from({ length: 37 }, (_, i) => i * 10);
    const fitPhases = fitAngles.map((a) => ((n * a) % 360));

    return {
      kind: "scatter2d" as const,
      points,
      fit: { x: fitAngles, y: fitPhases },
      axes: { x: "φ (deg)", y: "phase (deg)" },
      meta: { n_fit: n },
    };
  }, [live, hasStaticFiles, phaseNode, probePhi1, probePhi2, gateFrac]);

  // --- 3. RENDER SUB-COMPONENTS ---
  const renderSpectrogram = () => {
    if (specLoading && !syntheticSpecNode) {
      return <div className="placeholder">Loading spectrogram...</div>;
    }
    if (!processedSpecNode) return null;

    const colorscale: [number, string][] = processedSpecNode.discrete
      ? (() => {
          const n = MODE_PALETTE.length;
          const s: [number, string][] = [];
          for (let i = 0; i < n; i++) {
            s.push([i / n, MODE_PALETTE[i]], [(i + 1) / n, MODE_PALETTE[i]]);
          }
          return s;
        })()
      : POWER_SEQUENTIAL;
    const zr = processedSpecNode.zrange;

    const data = [
      {
        type: "heatmap" as const,
        x: processedSpecNode.x,
        y: processedSpecNode.y,
        z: processedSpecNode.z,
        colorscale,
        zmin: zr?.[0],
        zmax: zr?.[1],
        zsmooth: (processedSpecNode.discrete ? false : "best") as false | "best" | "fast" | undefined,
        colorbar: {
          title: { text: processedSpecNode.axes.z ?? "" },
          thickness: 12,
          outlinewidth: 0,
          ...(processedSpecNode.discrete
            ? {
                // one tick per integer mode-number magnitude |n| = 0 … 6
                tickvals: Array.from({ length: 7 }, (_, i) => i),
                ticktext: Array.from({ length: 7 }, (_, i) => `${i}`),
                tickmode: "array" as const,
              }
            : {}),
        },
      },
    ];

    const layout = {
      // Preserve the user's zoom/crop across every re-render (slider, toggle, scrub) —
      // Plotly only resets the view when uirevision changes, which we tie to the band, so
      // editing f_min/f_max intentionally re-frames while everything else keeps the crop.
      uirevision: `${machine}:${fmin}:${fmax}`,
      xaxis: { title: { text: processedSpecNode.axes.x } },
      // Pin the band to the knobs so the n-map (mostly null above the modes) doesn't
      // autorange-trim to ~30 kHz — both views show the full requested 0–fmax band.
      yaxis: { title: { text: processedSpecNode.axes.y }, range: [fmin, fmax] as [number, number] },
      shapes: [
        {
          type: "line" as const,
          xref: "x" as const,
          yref: "paper" as const,
          x0: cursorMs,
          y0: 0,
          x1: cursorMs,
          y1: 1,
          line: {
            color: "var(--accent)", // bright turquoise
            width: 2,
            dash: "dash" as const,
          },
        },
      ],
    };

    const handlePlotClick = (e: Plotly.PlotMouseEvent) => {
      if (e.points && e.points.length > 0) {
        const clickedTime = e.points[0].x;
        if (typeof clickedTime === "number") {
          setCursorMs(clickedTime);
        }
      }
    };

    // Fill the card: subtract its 12px padding (×2), ~38px header and the 8px gap, so the
    // plot — and its x-axis title — fit instead of overflowing and getting clipped.
    const plotH = Math.max(220, specHeight - 78);
    return <Plot data={data} layout={layout} height={plotH} onClick={handlePlotClick} />;
  };

  const renderSubInterval = () => {
    const { freqs, power, coh, nMode } = subIntervalData;
    // Live: one probe's real dB/dt from the raw_trace node. Mock: synthesize a trace.
    const activeFreqs = currentModeFreqs[0] > 0 ? currentModeFreqs : [8.0];
    const rawTrace = live
      ? (rawTraceNode?.kind === "line" && rawTraceNode.series[0]
          ? { times: rawTraceNode.series[0].x, values: rawTraceNode.series[0].y }
          : null)
      : generateDeterministicTimeTrace(cursorMs, activeFreqs);

    const rawPlotData = [
      {
        type: "scatter" as const,
        mode: "lines" as const,
        x: rawTrace?.times ?? [],
        y: rawTrace?.values ?? [],
        line: { color: ink, width: 1.2 },
      },
    ];

    const specSubplotsData = [
      {
        type: "scatter" as const,
        mode: "lines" as const,
        x: freqs,
        y: coh,
        line: { color: "var(--good)", width: 1.5 },
        name: "Coherence",
        xaxis: "x",
        yaxis: "y",
      },
      {
        type: "scatter" as const,
        mode: "markers" as const,
        x: freqs,
        y: nMode,
        marker: {
          size: 5,
          color: nMode.map((n) => (n === 0 ? "rgba(0,0,0,0)" : modeColor(n))),
          line: { width: 0.5, color: "#111" },
        },
        name: "Toroidal n",
        xaxis: "x",
        yaxis: "y2",
      },
      {
        type: "scatter" as const,
        mode: "lines" as const,
        x: freqs,
        y: power,
        line: { color: "var(--accent)", width: 1.5 },
        name: "Cross-Power",
        xaxis: "x",
        yaxis: "y3",
      },
    ];

    const specSubplotsLayout = {
      grid: { rows: 3, columns: 1, pattern: "coupled" as const },
      xaxis: { title: { text: "Frequency (kHz)" }, anchor: "y3" as const },
      yaxis: { title: { text: "Coh." }, range: [0, 1.05], domain: [0.74, 1.0] },
      // Match the spectrogram's |n| palette (0–6) so high-n modes aren't clipped here;
      // give this panel the largest domain share so all 7 integer ticks have room.
      yaxis2: { title: { text: "n" }, range: [-0.5, 6.5], dtick: 1, domain: [0.30, 0.66] },
      yaxis3: { title: { text: "Power" }, type: "log" as const, domain: [0.0, 0.22] },
      margin: { l: 50, r: 15, t: 10, b: 35 },
    };

    return (
      <div style={{ display: "flex", flexDirection: "row", height: "270px", gap: "0px" }}>
        <div style={{ width: subintervalLeftWidth, overflow: "auto", flexShrink: 0 }}>
          <h4 style={{ fontSize: "11px", textTransform: "uppercase", color: "var(--text-dim)", margin: "0 0 8px" }}>
            Raw Signal <span style={{ textTransform: "none" }}>dB/dt (4&nbsp;ms window)</span>
          </h4>
          {rawTrace
            ? <Plot data={rawPlotData} height={250} layout={{ margin: { l: 40, r: 10, t: 10, b: 30 }, xaxis: { title: { text: "Time (ms)" } } }} />
            : <PanelPlaceholder text="raw dB/dt trace — not yet wired to the backend" height={250} />}
        </div>
        <DraggableDivider direction="horizontal" onDelta={handleSubintervalSplit} />
        <div style={{ flex: 1, overflow: "auto", paddingLeft: "8px" }}>
          <h4 style={{ fontSize: "11px", textTransform: "uppercase", color: "var(--text-dim)", margin: "0 0 8px" }}>
            Frequency Spectrum
          </h4>
          <Plot data={specSubplotsData} layout={specSubplotsLayout} height={250} />
        </div>
      </div>
    );
  };

  const renderArrayContour = () => {
    // Per-panel data: live → the stripe heatmap nodes; mock → the synthetic stripes.
    const torData = live
      ? (toroidalStripesNode?.kind === "heatmap"
          ? { x: toroidalStripesNode.x, y: toroidalStripesNode.y, z: toroidalStripesNode.z } : null)
      : (arrayStripesData.times.length
          ? { x: arrayStripesData.times, y: arrayStripesData.phiAngles, z: arrayStripesData.toroidalZ } : null);
    const polData = live
      ? (poloidalStripesNode?.kind === "heatmap"
          ? { x: poloidalStripesNode.x, y: poloidalStripesNode.y, z: poloidalStripesNode.z } : null)
      : (arrayStripesData.times.length
          ? { x: arrayStripesData.times, y: arrayStripesData.thetaAngles, z: arrayStripesData.poloidalZ } : null);

    const baseLayout = {
      xaxis: { title: { text: "Time (ms)" } },
      margin: { l: 50, r: 15, t: 10, b: 35 },
    };
    const stripePlot = (d: { x: number[]; y: number[]; z: number[][] }, axisTitle: string) => (
      <Plot
        data={[{ type: "heatmap" as const, x: d.x, y: d.y, z: d.z, colorscale: POWER_SEQUENTIAL, showscale: false }]}
        layout={{ ...baseLayout, yaxis: { title: { text: axisTitle } } }}
        height={200}
      />
    );

    return (
      <div style={{ display: "flex", flexDirection: "row", height: "240px", gap: "0px" }}>
        <div style={{ width: arrayLeftWidth, overflow: "auto", flexShrink: 0 }}>
          <h4 style={{ fontSize: "11px", textTransform: "uppercase", color: "var(--text-dim)", margin: "0 0 8px" }}>
            Toroidal Array Waves <span style={{ textTransform: "none" }}>δB<sub>p</sub>(φ, t)</span>
          </h4>
          {torData
            ? stripePlot(torData, "φ (deg)")
            : <PanelPlaceholder text={`toroidal array waves · waiting for stripes at t=${cursorMs.toFixed(0)} ms`} />}
        </div>
        <DraggableDivider direction="horizontal" onDelta={handleArraySplit} />
        <div style={{ flex: 1, overflow: "auto", paddingLeft: "8px" }}>
          <h4 style={{ fontSize: "11px", textTransform: "uppercase", color: "var(--text-dim)", margin: "0 0 8px" }}>
            Poloidal Array Waves <span style={{ textTransform: "none" }}>δB<sub>p</sub>(θ, t)</span>
          </h4>
          {polData
            ? stripePlot(polData, "θ (deg)")
            : <PanelPlaceholder text="poloidal array not available for this shot" />}
        </div>
      </div>
    );
  };

  const renderModeStructure = () => {
    const toroidalMeta = processedToroidalNode?.meta as Record<string, number> | undefined;
    const poloidalMeta = processedPoloidalNode?.meta as Record<string, number> | undefined;
    return (
      <div style={{ display: "flex", flexDirection: "row", height: "240px", gap: "0px" }}>
        <div style={{ width: modeLeftWidth, overflow: "auto", flexShrink: 0 }}>
          <h4 style={{ fontSize: "11px", textTransform: "uppercase", color: "var(--text-dim)", margin: "0 0 8px" }}>
            Toroidal Phase Fit <span style={{ textTransform: "none" }}>(n = {String(toroidalMeta?.n_estimate ?? toroidalMeta?.n_fit ?? "")})</span>
          </h4>
          {processedToroidalNode
            ? <NodeView node={processedToroidalNode} height={200} />
            : <PanelPlaceholder text={`toroidal phase fit · waiting for phase_fit at t=${cursorMs.toFixed(0)} ms`} />}
        </div>
        <DraggableDivider direction="horizontal" onDelta={handleModeSplit} />
        <div style={{ flex: 1, overflow: "auto", paddingLeft: "8px" }}>
          <h4 style={{ fontSize: "11px", textTransform: "uppercase", color: "var(--text-dim)", margin: "0 0 8px" }}>
            Poloidal Phase Fit{poloidalMeta ? ` (m = ${String(poloidalMeta.m_fit ?? "")}, fittype = ${fittype})` : ""}
          </h4>
          {processedPoloidalNode
            ? <NodeView node={processedPoloidalNode} height={200} />
            : <PanelPlaceholder text="poloidal phase fit · no poloidal array in this shot" />}
        </div>
      </div>
    );
  };

  // The 2D modal pattern, rendered with a dedicated Plot (not the generic NodeView) so
  // we can: fill the tile edge-to-edge with an explicit y-range, wrap the panned θ tick
  // labels back to 0° past 360°, and stand the colorbar label up vertically to reclaim
  // horizontal room. Mirrors NodeView's contour styling otherwise.
  const renderModePattern = () => {
    const node = processedPatternNode;
    if (!node || node.kind !== "contour") return null;
    const inkEdge = dark ? "#000" : "#ffffff";
    const wrap = (v: number) => Math.round(((v % 360) + 360) % 360);
    let zr = node.zrange;
    if (!zr) {
      let m = 0;
      for (const row of node.z) for (const v of row) if (Number.isFinite(v)) m = Math.max(m, Math.abs(v));
      zr = [-m, m];
    }
    const y0 = node.y[0];
    const y1 = node.y[node.y.length - 1];
    const tickvals: number[] = [];
    for (let v = y0; v <= y1 + 1e-6; v += 45) tickvals.push(v);
    const ticktext = tickvals.map((v) => `${wrap(v)}`);

    const traces: Partial<Plotly.PlotData>[] = [{
      type: "contour", x: node.x, y: node.y, z: node.z,
      colorscale: FIELD_DIVERGING, zmin: zr[0], zmax: zr[1],
      contours: { coloring: "fill" },
      // side:"right" stands the title up vertically alongside the bar (frees width).
      colorbar: { title: { text: node.axes.z ?? "", side: "right" }, thickness: 12, outlinewidth: 0 },
    } as Partial<Plotly.PlotData>];
    if (node.overlay) {
      const pts = node.overlay.points;
      const hovertext = pts.map((p) => {
        const c = `(${p.x.toFixed(0)}, ${wrap(p.y)})`;
        return p.label ? `${p.label}<br>${c}` : c;
      });
      traces.push({
        type: "scatter", mode: "markers",
        x: pts.map((p) => p.x), y: pts.map((p) => p.y), text: hovertext,
        marker: { symbol: node.overlay.symbol ?? "circle", size: 6, color: ink, line: { color: inkEdge, width: 0.5 } },
        hovertemplate: "%{text}<extra></extra>",
      } as Partial<Plotly.PlotData>);
    }
    const layout: Partial<Plotly.Layout> = {
      xaxis: { title: { text: node.axes.x } },
      // explicit range = data extent → no autorange padding, fills the tile while sliding
      yaxis: { title: { text: node.axes.y }, range: [y0, y1], tickvals, ticktext },
    };
    return <Plot data={traces} layout={layout} height={260} />;
  };

  // Each analysis below renders in its OWN card panel (see the JSX), and only when
  // the backend serves it — no fabricated fallbacks. A small helper wraps a node in
  // a titled, bordered card consistent with the spectrogram / spectrum panels.
  const analysisCard = (
    title: string,
    node: Node | null,
    kind: Node["kind"],
    height: number,
    subtitle?: string,
  ) => {
    if (!node || node.kind !== kind) return null;
    return (
      // marginTop 7px matches the height of the DraggableDividers between the top
      // panels, so every card is spaced consistently down the column.
      <div className="card" style={{ flexShrink: 0, display: "flex", flexDirection: "column", gap: "8px", margin: "7px 0 0 0", minHeight: 0 }}>
        <h4 style={{ margin: 0, fontSize: "11px", fontWeight: 600, textTransform: "uppercase", color: "var(--accent)" }}>
          {title}
          {subtitle ? <span style={{ color: "var(--text-dim)", fontWeight: 400, textTransform: "none" }}> · {subtitle}</span> : null}
        </h4>
        <div style={{ flex: 1, minHeight: 0 }}>
          <NodeView node={node} height={height} />
        </div>
      </div>
    );
  };

  const shapeMeta = (n: Node | null) => (n?.meta as Record<string, number | string> | undefined);

  return (
    <div style={{ display: "flex", gap: sidebarExpanded ? "0px" : "16px", height: "100%", position: "relative" }}>
      
      {/* 1. Collapsible Control Panel */}
      <div
        className="card"
        style={{
          width: sidebarExpanded ? `${sidebarWidth}px` : "40px",
          transition: "width 0.2s ease-in-out",
          flexShrink: 0,
          overflow: "hidden",
          display: "flex",
          flexDirection: "column",
          gap: "12px",
          padding: sidebarExpanded ? "12px" : "12px 6px",
          border: "1px solid var(--border)",
          background: "var(--panel)",
        }}
      >
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", width: "100%" }}>
          {sidebarExpanded && (
            <span style={{ fontWeight: 600, fontSize: "11px", textTransform: "uppercase", letterSpacing: "0.5px" }}>
              Controls
            </span>
          )}
          <button
            onClick={() => setSidebarExpanded(!sidebarExpanded)}
            style={{
              background: "transparent",
              color: "var(--text)",
              border: "none",
              cursor: "pointer",
              fontSize: "12px",
              padding: 0,
              width: "20px",
            }}
          >
            {sidebarExpanded ? "◀" : "▶"}
          </button>
        </div>

        {sidebarExpanded && (
          <div style={{ display: "flex", flexDirection: "column", gap: "12px", height: "100%", overflowY: "auto" }}>
            {/* Data Source Badge */}
            <div style={{ borderBottom: "1px solid var(--border)", paddingBottom: "10px" }}>
              <div style={{ fontSize: "10px", color: "var(--text-dim)", textTransform: "uppercase", marginBottom: "4px" }}>
                Data Source
              </div>
              <div style={{ fontSize: "11px", fontWeight: 600, color: dataSourceColor }}>
                {dataSourceText}
              </div>
            </div>

            {/* Data Channels diagnostic — which fetched pointnames feed the analysis,
                and which are idle (droppable from the pull to speed it up). */}
            {channelInfo && (
              <details style={{ borderBottom: "1px solid var(--border)", paddingBottom: "10px" }}>
                <summary style={{ fontSize: "10px", color: "var(--text-dim)", textTransform: "uppercase", cursor: "pointer" }}>
                  Data Channels ({channelInfo.n_used}/{channelInfo.n_total} used)
                </summary>
                <div style={{ marginTop: "8px", display: "flex", flexDirection: "column", gap: "8px", maxHeight: "220px", overflowY: "auto" }}>
                  <div>
                    <div style={{ fontSize: "9px", color: "var(--good)", textTransform: "uppercase", marginBottom: "3px" }}>
                      Used ({channelInfo.used.length})
                    </div>
                    {channelInfo.used.map((c) => (
                      <div key={c.name} style={{ fontSize: "10px", fontFamily: "monospace", lineHeight: 1.45, display: "flex", justifyContent: "space-between", gap: "6px" }}>
                        <span style={{ color: "var(--text)" }}>{c.name}</span>
                        <span style={{ color: "var(--text-dim)", textAlign: "right" }}>{c.roles.join(", ")}</span>
                      </div>
                    ))}
                  </div>
                  {channelInfo.unused.length > 0 && (
                    <div>
                      <div style={{ fontSize: "9px", color: "var(--text-dim)", textTransform: "uppercase", marginBottom: "3px" }}>
                        Idle — droppable ({channelInfo.unused.length})
                      </div>
                      <div style={{ fontSize: "10px", fontFamily: "monospace", lineHeight: 1.45, color: "var(--text-dim)", wordBreak: "break-all" }}>
                        {channelInfo.unused.join(", ")}
                      </div>
                    </div>
                  )}
                </div>
              </details>
            )}

            {/* Time Cursor Scrubber Slider */}
            {processedSpecNode && (
              <div style={{ display: "flex", flexDirection: "column", gap: "4px", borderBottom: "1px solid var(--border)", paddingBottom: "10px" }}>
                <label htmlFor="time-range" style={{ fontSize: "11px", color: "var(--text-dim)" }}>
                  Time Scrubber (t0): <strong style={{ color: "var(--good)" }}>{cursorMs.toFixed(0)} ms</strong>
                </label>
                <input
                  id="time-range"
                  type="range"
                  min={processedSpecNode.x[0]}
                  max={processedSpecNode.x[processedSpecNode.x.length - 1]}
                  step={10}
                  value={cursorMs}
                  onChange={(e) => setCursorMs(parseFloat(e.target.value))}
                  style={{ accentColor: "var(--good)" }}
                />
              </div>
            )}

            {/* Frequency limits */}
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "6px" }}>
              <div>
                <label htmlFor="fmin-input" style={{ fontSize: "11px", color: "var(--text-dim)", display: "block", marginBottom: "2px" }}>
                  f_min (kHz)
                </label>
                <input
                  id="fmin-input"
                  type="number"
                  value={fmin}
                  onChange={(e) => setFmin(parseInt(e.target.value) || 0)}
                  style={{
                    width: "100%",
                    background: "var(--panel-2)",
                    color: "var(--text)",
                    border: "1px solid var(--border-2)",
                    padding: "5px",
                    borderRadius: "4px",
                    fontSize: "11px",
                    boxSizing: "border-box",
                  }}
                />
              </div>
              <div>
                <label htmlFor="fmax-input" style={{ fontSize: "11px", color: "var(--text-dim)", display: "block", marginBottom: "2px" }}>
                  f_max (kHz)
                </label>
                <input
                  id="fmax-input"
                  type="number"
                  value={fmax}
                  onChange={(e) => setFmax(parseInt(e.target.value) || 0)}
                  style={{
                    width: "100%",
                    background: "var(--panel-2)",
                    color: "var(--text)",
                    border: "1px solid var(--border-2)",
                    padding: "5px",
                    borderRadius: "4px",
                    fontSize: "11px",
                    boxSizing: "border-box",
                  }}
                />
              </div>
            </div>

            {/* fittype */}
            <div style={{ display: "flex", flexDirection: "column", gap: "4px" }}>
              <label htmlFor="fittype-select" style={{ fontSize: "11px", color: "var(--text-dim)" }}>Poloidal Fit (fittype) <em style={{ opacity: 0.7 }}>(not wired)</em></label>
              <select
                id="fittype-select"
                value={fittype}
                onChange={(e) => setFittype(parseInt(e.target.value))}
                style={{
                  background: "var(--panel-2)",
                  color: "var(--text)",
                  border: "1px solid var(--border-2)",
                  padding: "5px",
                  borderRadius: "4px",
                  outline: "none",
                }}
              >
                <option value={0}>0 = Circular (Straight θ)</option>
                <option value={1}>1 = Toroidicity (m=1 modulation)</option>
                <option value={2}>2 = Elongation (m=1,m=2 PEST θ*)</option>
              </select>
            </div>

            {/* smoothing — coherence-estimation window (backend coherence_smooth) */}
            <div
              style={{ display: "flex", flexDirection: "column", gap: "4px" }}
              title="Frequency-bin width for the coherence estimate — smooths the coherence map and the sub-interval coherence trace."
            >
              <label htmlFor="smoothing-range" style={{ fontSize: "11px", color: "var(--text-dim)" }}>
                Coherence Smoothing: <strong style={{ color: "var(--text)" }}>{smoothing} pts</strong>
              </label>
              <input
                id="smoothing-range"
                type="range"
                min="1"
                max="15"
                value={smoothing}
                onChange={(e) => setSmoothing(parseInt(e.target.value))}
                style={{ accentColor: "var(--accent)" }}
              />
            </div>

            {/* power gate — percentile noise floor, applied to every data-driven view */}
            <div
              style={{ display: "flex", flexDirection: "column", gap: "4px" }}
              title="Hides cells below this power percentile (noise floor) across the spectrogram, n-map, and spectrum."
            >
              <label htmlFor="power-gate-range" style={{ fontSize: "11px", color: "var(--text-dim)" }}>
                Power Gate: <strong style={{ color: "var(--text)" }}>{powerGate.toFixed(1)}%</strong>
              </label>
              <input
                id="power-gate-range"
                type="range"
                min="0"
                max={GATE_POS_MAX}
                step="1"
                value={gatePos}
                onChange={(e) => setGatePos(parseInt(e.target.value))}
                style={{ accentColor: "var(--accent)" }}
              />
            </div>

            {/* Advanced Parameters Divider & Header */}
            <div style={{ borderTop: "1px solid var(--border)", paddingTop: "10px", marginTop: "4px" }}>
              <button
                onClick={() => setAdvancedExpanded(!advancedExpanded)}
                style={{
                  display: "flex",
                  justifyContent: "space-between",
                  alignItems: "center",
                  width: "100%",
                  background: "transparent",
                  color: "var(--text)",
                  border: "none",
                  cursor: "pointer",
                  fontSize: "11px",
                  fontWeight: 600,
                  textTransform: "uppercase",
                  padding: "4px 0",
                }}
              >
                <span>Advanced Params <em style={{ opacity: 0.7, textTransform: "none" }}>(not wired)</em></span>
                <span>{advancedExpanded ? "▼" : "▶"}</span>
              </button>

              {advancedExpanded && (
                <div style={{ display: "flex", flexDirection: "column", gap: "10px", marginTop: "8px", borderTop: "1px dashed var(--border-2)", paddingTop: "8px" }}>
                  {/* FFT Window size select */}
                  <div style={{ display: "flex", flexDirection: "column", gap: "2px" }}>
                    <label htmlFor="fft-window-select" style={{ fontSize: "10px", color: "var(--text-dim)" }}>FFT Window Size</label>
                    <select
                      id="fft-window-select"
                      value={fftWindow}
                      onChange={(e) => setFftWindow(parseInt(e.target.value))}
                      style={{
                        background: "var(--panel-2)",
                        color: "var(--text)",
                        border: "1px solid var(--border-2)",
                        padding: "4px",
                        borderRadius: "4px",
                        fontSize: "11px",
                        outline: "none",
                      }}
                    >
                      <option value={256}>256 pts (dt=5ms, df=0.4kHz)</option>
                      <option value={512}>512 pts (dt=10ms, df=0.2kHz)</option>
                      <option value={1024}>1024 pts (dt=20ms, df=0.1kHz)</option>
                      <option value={2048}>2048 pts (dt=40ms, df=0.05kHz)</option>
                    </select>
                  </div>

                  {/* FFT Overlap slider */}
                  <div style={{ display: "flex", flexDirection: "column", gap: "2px" }}>
                    <label htmlFor="fft-overlap-range" style={{ fontSize: "10px", color: "var(--text-dim)" }}>
                      FFT Overlap: <strong style={{ color: "var(--text)" }}>{fftOverlap}%</strong>
                    </label>
                    <input
                      id="fft-overlap-range"
                      type="range"
                      min="0"
                      max="90"
                      step="5"
                      value={fftOverlap}
                      onChange={(e) => setFftOverlap(parseInt(e.target.value))}
                      style={{ accentColor: "var(--accent)" }}
                    />
                  </div>

                  {/* Probe Angles input fields (side-by-side) */}
                  <div style={{ display: "flex", flexDirection: "column", gap: "2px" }}>
                    <span style={{ fontSize: "10px", color: "var(--text-dim)" }}>Toroidal Probes (φ)</span>
                    <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "6px" }}>
                      <div>
                        <label htmlFor="phi1-input" style={{ fontSize: "9px", color: "var(--text-dim)", display: "block" }}>Probe 1</label>
                        <input
                          id="phi1-input"
                          type="number"
                          min="0"
                          max="360"
                          value={probePhi1}
                          onChange={(e) => setProbePhi1(Math.max(0, Math.min(360, parseInt(e.target.value) || 0)))}
                          style={{
                            width: "100%",
                            background: "var(--panel-2)",
                            color: "var(--text)",
                            border: "1px solid var(--border-2)",
                            padding: "4px",
                            borderRadius: "4px",
                            fontSize: "11px",
                            boxSizing: "border-box",
                          }}
                        />
                      </div>
                      <div>
                        <label htmlFor="phi2-input" style={{ fontSize: "9px", color: "var(--text-dim)", display: "block" }}>Probe 2</label>
                        <input
                          id="phi2-input"
                          type="number"
                          min="0"
                          max="360"
                          value={probePhi2}
                          onChange={(e) => setProbePhi2(Math.max(0, Math.min(360, parseInt(e.target.value) || 0)))}
                          style={{
                            width: "100%",
                            background: "var(--panel-2)",
                            color: "var(--text)",
                            border: "1px solid var(--border-2)",
                            padding: "4px",
                            borderRadius: "4px",
                            fontSize: "11px",
                            boxSizing: "border-box",
                          }}
                        />
                      </div>
                    </div>
                  </div>

                </div>
              )}
            </div>
          </div>
        )}
      </div>

      {sidebarExpanded && (
        <DraggableDivider direction="horizontal" onDelta={handleSidebarDelta} />
      )}

      {/* 2. Main Dashboard (Top Spectrogram / Stacked Analysis Panels) */}
      <div style={{ flex: 1, display: "flex", flexDirection: "column", gap: "0px", minWidth: 0, overflowY: "auto", paddingRight: "6px", height: "100%" }}>
        
        {/* Top: Spectrogram Heatmap */}
        <div className="card" style={{ flexShrink: 0, display: "flex", flexDirection: "column", gap: "8px", margin: 0, height: specHeight, minHeight: 0 }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
            <div>
              <h3 style={{ margin: 0, fontWeight: 600, fontSize: "13px" }}>Spectrogram Ḃ<sub>p</sub>(t, f)</h3>
              <span style={{ fontSize: "11px", color: "var(--text-dim)" }}>
                Active cursor: <strong style={{ color: "var(--good)" }}>{cursorMs ? `${cursorMs.toFixed(1)} ms` : "none"}</strong>
              </span>
            </div>
            <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
            {hasStaticFiles && (
              <select
                aria-label="Spectral resolution"
                title="STFT window — frequency resolution = 1/window"
                value={specSliceMs}
                onChange={(e) => setSpecSliceMs(parseFloat(e.target.value))}
                style={{ background: "var(--panel-2)", color: "var(--text)", border: "1px solid var(--border-2)", padding: "3px 6px", borderRadius: "4px", fontSize: "11px", outline: "none" }}
              >
                <option value={1}>1 kHz · coarse</option>
                <option value={2}>500 Hz · medium</option>
                <option value={4}>250 Hz · fine</option>
                <option value={8}>125 Hz · ultra</option>
              </select>
            )}
            <div className="toggle-group" style={{ display: "flex", background: "var(--border)", padding: "2px", borderRadius: "4px" }}>
              <button
                onClick={() => setDisplayMode("n")}
                style={{
                  background: displayMode === "n" ? "var(--border-2)" : "transparent",
                  color: displayMode === "n" ? "#fff" : "var(--text-dim)",
                  border: "none",
                  padding: "4px 10px",
                  borderRadius: "3px",
                  cursor: "pointer",
                  fontSize: "11px",
                  fontWeight: 500,
                }}
              >
                Mode n
              </button>
              <button
                onClick={() => setDisplayMode("power")}
                style={{
                  background: displayMode === "power" ? "var(--border-2)" : "transparent",
                  color: displayMode === "power" ? "#fff" : "var(--text-dim)",
                  border: "none",
                  padding: "4px 10px",
                  borderRadius: "3px",
                  cursor: "pointer",
                  fontSize: "11px",
                  fontWeight: 500,
                }}
              >
                Log Power
              </button>
            </div>
            </div>
          </div>
          <div style={{ flex: 1, minHeight: 0 }}>{renderSpectrogram()}</div>
        </div>

        <DraggableDivider direction="vertical" onDelta={handleSpecDelta} />

        {/* Panel 1: Sub-Interval Spectrum */}
        <div className="card" style={{ flexShrink: 0, display: "flex", flexDirection: "column", gap: "12px", margin: 0, height: panel1Height, minHeight: 0 }}>
          <h4 style={{ margin: 0, fontSize: "11px", fontWeight: 600, textTransform: "uppercase", color: "var(--accent)" }}>
            Sub-Interval Spectrum <span style={{ textTransform: "none" }}>(t-slice)</span>
          </h4>
          <div style={{ flex: 1, minHeight: 0 }}>
            {renderSubInterval()}
          </div>
        </div>

        <DraggableDivider direction="vertical" onDelta={handlePanel12Delta} />

        {/* Panel 2: Array Data Wave-Stripes */}
        <div className="card" style={{ flexShrink: 0, display: "flex", flexDirection: "column", gap: "12px", margin: 0, height: panel2Height, minHeight: 0 }}>
          <h4 style={{ margin: 0, fontSize: "11px", fontWeight: 600, textTransform: "uppercase", color: "var(--accent)" }}>
            Array Data Wave-Stripes
          </h4>
          <div style={{ flex: 1, minHeight: 0 }}>
            {renderArrayContour()}
          </div>
        </div>

        <DraggableDivider direction="vertical" onDelta={handlePanel23Delta} />

        {/* Panel 3: Mode Structure Fits (toroidal/poloidal phase fits) */}
        <div className="card" style={{ flexShrink: 0, display: "flex", flexDirection: "column", gap: "12px", margin: 0, height: panel3Height, minHeight: 0 }}>
          <h4 style={{ margin: 0, fontSize: "11px", fontWeight: 600, textTransform: "uppercase", color: "var(--accent)" }}>
            Mode Structure Fits
          </h4>
          <div style={{ flex: 1, minHeight: 0 }}>
            {renderModeStructure()}
          </div>
        </div>

        {/* Each eigspec analysis in its own card — rendered only when the backend
            serves it (poloidal shape & 2D pattern need a shot with the MPID array). */}
        {analysisCard("Toroidal Mode Shape", modeShapeNode, "line", 220,
          shapeMeta(modeShapeNode)?.f_kHz != null
            ? `GP fit ±2σ · markers = probes @ ${shapeMeta(modeShapeNode)!.f_kHz} kHz` : "GP fit ±2σ")}
        {analysisCard("Poloidal Mode Shape", poloidalShapeNode, "line", 220,
          shapeMeta(poloidalShapeNode)?.f_kHz != null
            ? `GP fit ±2σ · markers = probes @ ${shapeMeta(poloidalShapeNode)!.f_kHz} kHz` : "GP fit ±2σ")}
        {processedPatternNode && processedPatternNode.kind === "contour" && (
          <div className="card" style={{ flexShrink: 0, display: "flex", flexDirection: "column", gap: "8px", margin: "7px 0 0 0", minHeight: 0 }}>
            <h4 style={{ margin: 0, fontSize: "11px", fontWeight: 600, textTransform: "uppercase", color: "var(--accent)" }}>
              2D Modal Pattern (θ, φ)
              <span style={{ color: "var(--text-dim)", fontWeight: 400, textTransform: "none" }}>
                {" · "}
                {shapeMeta(modePatternNode)?.f_kHz != null
                  ? `Re{poloidal ⊗ toroidal}, eq 23 @ ${shapeMeta(modePatternNode)!.f_kHz} kHz` : "eigspec eq 23"}
              </span>
            </h4>
            <div style={{ display: "flex", flexDirection: "row", gap: "6px", flex: 1, minHeight: 0 }}>
              {/* θ-origin slider on the LEFT, vertical so it tracks the y (θ) axis it pans */}
              <div
                style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: "4px", padding: "2px 0" }}
                title="Pans the periodic θ (poloidal) axis so this angle sits at the plot origin."
              >
                <span style={{ fontSize: "9px", color: "var(--text-dim)", whiteSpace: "nowrap" }}>θ orig</span>
                <input
                  type="range" min={0} max={360} step={2} value={patternCut}
                  onChange={(e) => setPatternCut(Number(e.target.value))}
                  style={{ writingMode: "vertical-lr", direction: "rtl", width: "18px", height: "210px" }}
                />
                <span style={{ fontSize: "9px", color: "var(--text)" }}>{patternCut}°</span>
              </div>
              <div style={{ flex: 1, minHeight: 0 }}>
                {renderModePattern()}
              </div>
            </div>
          </div>
        )}
        {analysisCard("Mode Persistence", modeTrackNode, "line", 200,
          shapeMeta(modeTrackNode)?.dominant_n != null
            ? `shape similarity to the dominant mode vs time (1 = persists) · n≈${shapeMeta(modeTrackNode)!.dominant_n}`
            : "shape similarity to the dominant mode vs time")}
        {analysisCard("Toroidal Mode vs Time", modeOverTimeNode, "line", 200,
          shapeMeta(modeOverTimeNode)?.dominant_n != null
            ? `n of the strongest mode (freq follows the ridge${
                Array.isArray(shapeMeta(modeOverTimeNode)?.f_range_kHz)
                  ? `, ${(shapeMeta(modeOverTimeNode)!.f_range_kHz as unknown as number[]).join("–")} kHz`
                  : ""}) · dominant n≈${shapeMeta(modeOverTimeNode)!.dominant_n}`
            : "best-fit toroidal n over time")}
      </div>
    </div>
  );
}
