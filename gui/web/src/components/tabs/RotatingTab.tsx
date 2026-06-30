import { useState, useMemo, useEffect, useCallback } from "react";
import type * as Plotly from "plotly.js";
import { useStore } from "../../store";
import { useNode } from "../../lib/useNode";
import { usingLiveBackend } from "../../lib/api";
import { MODE_PALETTE, POWER_SEQUENTIAL } from "../../lib/colormaps";
import Plot from "../../lib/Plot";
import NodeView from "../../lib/NodeView";
import DraggableDivider from "../../lib/DraggableDivider";

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

export default function RotatingTab({ machine }: { machine: string }) {
  const { cursorMs, setCursorMs } = useStore();
  
  // View states
  const [displayMode, setDisplayMode] = useState<"n" | "power">("n");
  const [sidebarExpanded, setSidebarExpanded] = useState<boolean>(true);

  // Control Parameter states
  const [fmin, setFmin] = useState<number>(0);
  const [fmax, setFmax] = useState<number>(50);
  const [fittype, setFittype] = useState<number>(2); // 0 = circular, 1 = toroidicity, 2 = PEST theta*
  const [btype, setBtype] = useState<number>(4); // visual only — no backend (QS/SLCONTOUR path)
  const [smoothing, setSmoothing] = useState<number>(5);
  const [coherenceThreshold, setCoherenceThreshold] = useState<number>(0.5);
  // Toroidal mode-number range (real knob — bounded to the Δφ aliasing ceiling by the backend)
  const [nMin, setNMin] = useState<number>(-6);
  const [nMax, setNMax] = useState<number>(6);

  // Advanced Parameter states
  const [advancedExpanded, setAdvancedExpanded] = useState<boolean>(false);
  const [fftWindow, setFftWindow] = useState<number>(512);
  const [fftOverlap, setFftOverlap] = useState<number>(75);
  const [probePhi1, setProbePhi1] = useState<number>(307);
  const [probePhi2, setProbePhi2] = useState<number>(340);
  const [pestLambda1, setPestLambda1] = useState<number>(0.35);
  const [pestLambda2, setPestLambda2] = useState<number>(0.05);
  const [btCompMode, setBtCompMode] = useState<"none" | "analog" | "digital">("digital");
  const [shieldingCutoff, setShieldingCutoff] = useState<number>(50); // 3dB shielding cutoff in kHz

  // Resizable layout dimensions
  const [sidebarWidth, setSidebarWidth] = useState(260);
  const [specHeight, setSpecHeight] = useState(280);
  const [panel1Height, setPanel1Height] = useState(290);
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
  const live = usingLiveBackend();

  // Knob → node params. Sent to the live backend (re-runs the core on change);
  // ignored by the static mock. Memoized so useNode only refetches on real changes.
  const specParams = useMemo(
    () => ({
      fmin, fmax,
      coherence_min: coherenceThreshold,
      smoothing,
      fft_overlap: fftOverlap,
      n_min: nMin, n_max: nMax,
    }),
    [fmin, fmax, coherenceThreshold, smoothing, fftOverlap, nMin, nMax],
  );

  // Fetch main spectrogram node (from static files if available)
  const {
    node: specNode,
    loading: specLoading,
    error: specError,
  } = useNode(machine, "spectrogram", specParams);

  // Fetch toroidal phase fit node (from static files if available)
  const {
    node: phaseNode,
  } = useNode(machine, "phase_fit", { time: cursorMs });

  // Rich MODESPEC nodes — gated on a live backend (no static mock fixtures for these).
  // Passing `null` as the machine when not live makes useNode a no-op (returns null),
  // so the panels fall back to the clearly-labeled synthetic generators below.
  const liveMachine = live ? machine : null;
  const { node: modeNode } = useNode(liveMachine, "mode_number", specParams);
  const { node: cohNode } = useNode(liveMachine, "coherence", specParams);
  const { node: rawNode } = useNode(liveMachine, "raw_signal", { time: cursorMs, window_ms: 2 });
  const { node: contourNode } = useNode(liveMachine, "contour", {});

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

  // Detect data source. Live backend = real Python/FastAPI nodes; otherwise the
  // static mock JSON (if present) or the synthetic generator (last resort).
  const hasStaticFiles = !!specNode && !specError;
  const dataSourceText = live
    ? "Live Backend"
    : hasStaticFiles
      ? "Mock Files (Static)"
      : "Synthetic Generator (Dynamic)";
  const dataSourceColor = live || hasStaticFiles ? "var(--good)" : "var(--accent)";

  // --- 2. DYNAMIC SYNTHETIC DATA GENERATOR ---
  // When static files aren't found, we synthesize mode activity
  const syntheticSpecNode = useMemo(() => {
    if (hasStaticFiles) return null;
    
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
      axes: { x: "Time (ms)", y: "f (kHz)", z: "log power" },
      discrete: false,
    };
  }, [hasStaticFiles, fftWindow]);

  // Merge loaded specNode with controls/display settings
  const processedSpecNode = useMemo(() => {
    // Live backend: the real nodes are already cropped/gated/mode-ranged server-side
    // (we pass fmin/fmax/coherence/n_min/n_max), so render them directly. "Mode n"
    // uses the real mode_number node; "Log Power" uses the real spectrogram.
    if (live) {
      const node = displayMode === "n" ? modeNode : specNode;
      return node && node.kind === "heatmap" ? node : null;
    }

    const baseNode = hasStaticFiles ? specNode : syntheticSpecNode;
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
      const cutoffAttenDb = -5 * Math.log10(1 + Math.pow(f / shieldingCutoff, 2));
      return baseNode.z[fIdx].map((val) => val + cutoffAttenDb);
    });

    const filteredY = fIndices.map((idx) => baseNode.y[idx]);

    const allZ = filteredZ.flat().filter((v): v is number => v !== null && !isNaN(v));
    const zMin = allZ.length ? Math.min(...allZ) : -3;
    const zMax = allZ.length ? Math.max(...allZ) : 0;
    const powerThreshold = zMin + coherenceThreshold * (zMax - zMin);

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
        zrange: [-6.5, 6.5] as [number, number],
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
  }, [live, modeNode, hasStaticFiles, specNode, syntheticSpecNode, displayMode, fmin, fmax, coherenceThreshold, shieldingCutoff]);

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
  const nearestCol = (xs: number[]) => {
    let tIdx = 0, minDiff = Infinity;
    xs.forEach((t, idx) => {
      const diff = Math.abs(t - cursorMs);
      if (diff < minDiff) { minDiff = diff; tIdx = idx; }
    });
    return tIdx;
  };

  const subIntervalData = useMemo(() => {
    // Live: slice the REAL spectrogram / coherence / mode-number heatmaps at the
    // cursor column (all three share the core's STFT grid, so columns align).
    if (live && specNode?.kind === "heatmap") {
      const freqs = specNode.y;
      const tIdx = nearestCol(specNode.x);
      const power = freqs.map((_, fIdx) => Math.pow(10, specNode.z[fIdx][tIdx]));
      const coh = cohNode?.kind === "heatmap"
        ? freqs.map((_, fIdx) => cohNode.z[fIdx]?.[tIdx] ?? 0)
        : power.map(() => 0);
      const nMode = modeNode?.kind === "heatmap"
        ? freqs.map((_, fIdx) => modeNode.z[fIdx]?.[tIdx] ?? 0)
        : freqs.map(() => 0);
      return { freqs, power, coh, nMode };
    }

    const baseNode = hasStaticFiles ? specNode : syntheticSpecNode;
    if (!baseNode || baseNode.kind !== "heatmap") {
      return { freqs: [], power: [], coh: [], nMode: [] };
    }
    const tIdx = nearestCol(baseNode.x);
    const freqs = baseNode.y;
    const power = freqs.map((_, fIdx) => Math.pow(10, baseNode.z[fIdx][tIdx])); // log → linear

    // Synthetic fallback (no backend): simulate coherence + mode number.
    const coh = power.map((p) => {
      const rawCoh = p > 0.05 ? 0.9 - (0.1 / p) : 0.15 + p * 2.0;
      return Math.max(0.0, Math.min(1.0, rawCoh));
    });
    const nMode = coh.map((c, fIdx) => {
      if (c < coherenceThreshold) return 0;
      const f = freqs[fIdx];
      if (currentModeFreqs.some(mf => Math.abs(f - mf) < 1.0)) {
        if (Math.abs(f - currentModeFreqs[0]) < 1.0) return 2; // n=2
        if (Math.abs(f - currentModeFreqs[1]) < 1.0) return 1; // n=1
        if (currentModeFreqs[2] && Math.abs(f - currentModeFreqs[2]) < 1.0) return 3; // n=3
      }
      return 0;
    });

    return { freqs, power, coh, nMode };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [live, specNode, cohNode, modeNode, hasStaticFiles, syntheticSpecNode, cursorMs, coherenceThreshold, currentModeFreqs]);

  // Toroidal & Poloidal wave stripes data (Array Tab)
  const arrayStripesData = useMemo(() => {
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
      const thetaStar = thetaRad - pestLambda1 * Math.sin(thetaRad) - pestLambda2 * Math.sin(2 * thetaRad);
      return times.map((t, tIdx) => {
        if (targetFreq === 0) return Math.sin(tIdx * 0.4 + theta * 0.1) * 2;
        // m=3, m=2, and m=4 rotating waves superposition
        return 12 * Math.sin(3 * thetaStar - omega1 * t) +
               6 * Math.sin(2 * thetaStar - omega2 * t) +
               4 * Math.sin(4 * thetaStar - omega3 * t);
      });
    });

    return { times, phiAngles, thetaAngles, toroidalZ, poloidalZ };
  }, [cursorMs, currentModeFreqs, pestLambda1, pestLambda2]);

  // Mode structure poloidal node (computed dynamically from fittype option)
  const processedPoloidalNode = useMemo(() => {
    const m = fittype === 2 ? 3 : fittype === 1 ? 2 : 1;
    const angles = Array.from({ length: 31 }, (_, i) => (i * 360) / 30); // 31 probes
    
    const points = angles.map((theta, i) => {
      const rad = (theta * Math.PI) / 180;
      
      // Calculate straight-field-line theta* depending on fittype
      let thetaStar = rad;
      if (fittype === 1) thetaStar = rad - pestLambda1 * Math.sin(rad); // weak toroidicity
      if (fittype === 2) thetaStar = rad - pestLambda1 * Math.sin(rad) - pestLambda2 * Math.sin(2 * rad); // elongation
      
      const basePhase = (m * thetaStar) % (2 * Math.PI);
      const noise = Math.sin(i * 4.31) * 0.15; // deterministic pure noise
      
      // Bt misalignment compensation noise (Slide 39)
      const btNoise = btCompMode === "none"
        ? Math.sin(theta * 2.3 + 1.2) * 22
        : btCompMode === "analog"
          ? Math.sin(theta * 2.3 + 1.2) * 5
          : Math.sin(theta * 2.3 + 1.2) * 1.5;

      return {
        x: theta,
        y: (((basePhase + noise) * 180) / Math.PI + btNoise + 360) % 360,
        group: "Bp",
        error_y: 5.0 + Math.abs(btNoise) * 0.8 + (1.0 - coherenceThreshold) * 10,
        error_x: 1.2, // 1.2 deg poloidal alignment error (Slide 32)
      };
    });

    const fitAngles = Array.from({ length: 37 }, (_, i) => i * 10);
    const fitPhases = fitAngles.map((a) => {
      const rad = (a * Math.PI) / 180;
      let thetaStar = rad;
      if (fittype === 1) thetaStar = rad - pestLambda1 * Math.sin(rad);
      if (fittype === 2) thetaStar = rad - pestLambda1 * Math.sin(rad) - pestLambda2 * Math.sin(2 * rad);
      return ((m * thetaStar * 180) / Math.PI) % 360;
    });

    return {
      kind: "scatter2d" as const,
      points,
      fit: { x: fitAngles, y: fitPhases },
      axes: { x: "θ (deg)", y: "phase (deg)" },
      meta: { m_fit: m },
    };
  }, [fittype, pestLambda1, pestLambda2, btCompMode, coherenceThreshold]);

  // Toroidal node processing
  const processedToroidalNode = useMemo(() => {
    if (hasStaticFiles && phaseNode && phaseNode.kind === "scatter2d") {
      return phaseNode;
    }
    // Synthesize toroidal fit (n = 2)
    const n = 2;
    // Add active probePhi1 and probePhi2 toroidal probe positions dynamically
    const angles = [0, 30, 55, 77, 105, 130, 155, 180, 205, 230, 255, 280, 310, 340, probePhi1, probePhi2];
    const points = angles.map((phi, i) => {
      const rad = (phi * Math.PI) / 180;
      const basePhase = (n * rad) % (2 * Math.PI);
      const noise = Math.sin(i * 7.42) * 0.08;
      
      // Bt misalignment compensation noise
      const btNoise = btCompMode === "none"
        ? Math.sin(phi * 3.1 + 0.5) * 18
        : btCompMode === "analog"
          ? Math.sin(phi * 3.1 + 0.5) * 4
          : Math.sin(phi * 3.1 + 0.5) * 1.0;

      return {
        x: phi,
        y: (((basePhase + noise) * 180) / Math.PI + btNoise + 360) % 360,
        group: phi === probePhi1 || phi === probePhi2 ? "Selected Probe" : "Bp",
        error_y: 4.0 + Math.abs(btNoise) * 0.8 + (1.0 - coherenceThreshold) * 8,
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
  }, [hasStaticFiles, phaseNode, probePhi1, probePhi2, btCompMode, coherenceThreshold]);

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
            ? { tickvals: [-6, -4, -2, 0, 2, 4, 6], ticktext: ["-6", "-4", "-2", "0", "2", "4", "6"], tickmode: "array" as const }
            : {}),
        },
      },
    ];

    const layout = {
      xaxis: { title: { text: processedSpecNode.axes.x } },
      yaxis: { title: { text: processedSpecNode.axes.y } },
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

    return <Plot data={data} layout={layout} height={260} onClick={handlePlotClick} />;
  };

  const renderSubInterval = () => {
    const { freqs, power, coh, nMode } = subIntervalData;
    const activeFreqs = currentModeFreqs[0] > 0 ? currentModeFreqs : [8.0];
    // Live: real probe dB/dt around the cursor; else the synthetic sum-of-sines.
    const liveRaw = live && rawNode?.kind === "line" && rawNode.series.length > 0;
    const rawTrace = liveRaw
      ? { times: rawNode.series[0].x, values: rawNode.series[0].y }
      : generateDeterministicTimeTrace(cursorMs, activeFreqs);

    const rawPlotData = [
      {
        type: "scatter" as const,
        mode: "lines" as const,
        x: rawTrace.times,
        y: rawTrace.values,
        line: { color: "#fff", width: 1.2 },
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
          color: nMode.map((n) => (n === 2 ? "#f46d43" : n === 1 ? "#fdae61" : "rgba(0,0,0,0)")),
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
      yaxis: { title: { text: "Coh." }, range: [0, 1.05], domain: [0.7, 1.0] },
      yaxis2: { title: { text: "n" }, range: [-0.5, 3.5], domain: [0.35, 0.65] },
      yaxis3: { title: { text: "Power" }, type: "log" as const, domain: [0.0, 0.3] },
      margin: { l: 50, r: 15, t: 10, b: 35 },
    };

    return (
      <div style={{ display: "flex", flexDirection: "row", height: "240px", gap: "0px" }}>
        <div style={{ width: subintervalLeftWidth, overflow: "auto", flexShrink: 0 }}>
          <h4 style={{ fontSize: "11px", textTransform: "uppercase", color: "var(--text-dim)", margin: "0 0 8px" }}>
            Raw Signal dB/dt (4ms Window)
          </h4>
          <Plot data={rawPlotData} height={200} layout={{ margin: { l: 40, r: 10, t: 10, b: 30 }, xaxis: { title: { text: "Time (ms)" } } }} />
        </div>
        <DraggableDivider direction="horizontal" onDelta={handleSubintervalSplit} />
        <div style={{ flex: 1, overflow: "auto", paddingLeft: "8px" }}>
          <h4 style={{ fontSize: "11px", textTransform: "uppercase", color: "var(--text-dim)", margin: "0 0 8px" }}>
            Frequency Spectrum
          </h4>
          <Plot data={specSubplotsData} layout={specSubplotsLayout} height={200} />
        </div>
      </div>
    );
  };

  const renderArrayContour = () => {
    const { times, phiAngles, thetaAngles, toroidalZ, poloidalZ } = arrayStripesData;

    const toroidalTrace = [
      {
        type: "heatmap" as const,
        x: times,
        y: phiAngles,
        z: toroidalZ,
        colorscale: POWER_SEQUENTIAL,
        showscale: false,
      },
    ];

    const poloidalTrace = [
      {
        type: "heatmap" as const,
        x: times,
        y: thetaAngles,
        z: poloidalZ,
        colorscale: POWER_SEQUENTIAL,
        showscale: false,
      },
    ];

    const baseLayout = {
      xaxis: { title: { text: "Time (ms)" } },
      margin: { l: 50, r: 15, t: 10, b: 35 },
    };

    // Live: real toroidal δBp(φ,t) from the `contour` node (its own φ-vs-time axes).
    const liveContour = live && contourNode?.kind === "contour";

    return (
      <div style={{ display: "flex", flexDirection: "row", height: "240px", gap: "0px" }}>
        <div style={{ width: arrayLeftWidth, overflow: "auto", flexShrink: 0 }}>
          <h4 style={{ fontSize: "11px", textTransform: "uppercase", color: "var(--text-dim)", margin: "0 0 8px" }}>
            Toroidal Array δBp(φ, t){liveContour ? "" : "  ·  synthetic"}
          </h4>
          {liveContour
            ? <NodeView node={contourNode} height={200} />
            : <Plot data={toroidalTrace} layout={{ ...baseLayout, yaxis: { title: { text: "φ (deg)" } } }} height={200} />}
        </div>
        <DraggableDivider direction="horizontal" onDelta={handleArraySplit} />
        <div style={{ flex: 1, overflow: "auto", paddingLeft: "8px" }}>
          <h4 style={{ fontSize: "11px", textTransform: "uppercase", color: "var(--text-dim)", margin: "0 0 8px" }}>
            Poloidal Array dBp(θ, t)  ·  synthetic — pending backend
          </h4>
          <Plot data={poloidalTrace} layout={{ ...baseLayout, yaxis: { title: { text: "θ (deg)" } } }} height={200} />
        </div>
      </div>
    );
  };

  const renderModeStructure = () => {
    const toroidalMeta = processedToroidalNode.meta as Record<string, number> | undefined;
    const poloidalMeta = processedPoloidalNode.meta as Record<string, number> | undefined;
    return (
      <div style={{ display: "flex", flexDirection: "row", height: "240px", gap: "0px" }}>
        <div style={{ width: modeLeftWidth, overflow: "auto", flexShrink: 0 }}>
          <h4 style={{ fontSize: "11px", textTransform: "uppercase", color: "var(--text-dim)", margin: "0 0 8px" }}>
            Toroidal Phase Fit (n = {String(toroidalMeta?.n_fit ?? "")})
          </h4>
          <NodeView node={processedToroidalNode} height={200} />
        </div>
        <DraggableDivider direction="horizontal" onDelta={handleModeSplit} />
        <div style={{ flex: 1, overflow: "auto", paddingLeft: "8px" }}>
          <h4 style={{ fontSize: "11px", textTransform: "uppercase", color: "var(--text-dim)", margin: "0 0 8px" }}>
            Poloidal Phase Fit (m = {String(poloidalMeta?.m_fit ?? "")}, fittype = {fittype})  ·  synthetic — pending backend
          </h4>
          <NodeView node={processedPoloidalNode} height={200} />
        </div>
      </div>
    );
  };

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
              Modespec Controls
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
              <label htmlFor="fittype-select" style={{ fontSize: "11px", color: "var(--text-dim)" }}>Poloidal Fit (fittype)</label>
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

            {/* btype */}
            <div style={{ display: "flex", flexDirection: "column", gap: "4px" }}>
              <label htmlFor="btype-select" style={{ fontSize: "11px", color: "var(--text-dim)" }}>Baseline Method (btype) · visual only</label>
              <select
                id="btype-select"
                value={btype}
                onChange={(e) => setBtype(parseInt(e.target.value))}
                style={{
                  background: "var(--panel-2)",
                  color: "var(--text)",
                  border: "1px solid var(--border-2)",
                  padding: "5px",
                  borderRadius: "4px",
                  outline: "none",
                }}
              >
                <option value={0}>0 = None</option>
                <option value={1}>1 = Early baseline</option>
                <option value={2}>2 = Late baseline</option>
                <option value={3}>3 = Interpolated</option>
                <option value={4}>4 = Running average</option>
              </select>
            </div>

            {/* smoothing */}
            <div style={{ display: "flex", flexDirection: "column", gap: "4px" }}>
              <label htmlFor="smoothing-range" style={{ fontSize: "11px", color: "var(--text-dim)" }}>
                Smoothing: <strong style={{ color: "var(--text)" }}>{smoothing} pts</strong>
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

            {/* coherence threshold */}
            <div style={{ display: "flex", flexDirection: "column", gap: "4px" }}>
              <label htmlFor="coh-range" style={{ fontSize: "11px", color: "var(--text-dim)" }}>
                Coherence Gate: <strong style={{ color: "var(--text)" }}>{coherenceThreshold.toFixed(2)}</strong>
              </label>
              <input
                id="coh-range"
                type="range"
                min="0.0"
                max="1.0"
                step="0.05"
                value={coherenceThreshold}
                onChange={(e) => setCoherenceThreshold(parseFloat(e.target.value))}
                style={{ accentColor: "var(--accent)" }}
              />
            </div>

            {/* toroidal mode-number range (real; backend clamps to the Δφ ceiling) */}
            <div style={{ display: "flex", flexDirection: "column", gap: "4px" }}>
              <label style={{ fontSize: "11px", color: "var(--text-dim)" }}>
                Mode range n: <strong style={{ color: "var(--text)" }}>{nMin} … {nMax}</strong>
              </label>
              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "6px" }}>
                <input
                  aria-label="n_min"
                  type="range"
                  min="-6"
                  max="0"
                  step="1"
                  value={nMin}
                  onChange={(e) => setNMin(Math.min(parseInt(e.target.value), nMax))}
                  style={{ accentColor: "var(--accent)" }}
                />
                <input
                  aria-label="n_max"
                  type="range"
                  min="0"
                  max="6"
                  step="1"
                  value={nMax}
                  onChange={(e) => setNMax(Math.max(parseInt(e.target.value), nMin))}
                  style={{ accentColor: "var(--accent)" }}
                />
              </div>
              <span style={{ fontSize: "8px", color: "var(--text-dim)", lineHeight: 1.1 }}>
                A 2-probe pair resolves only |n| ≤ ⌊180/Δφ⌋; the backend clamps to that.
              </span>
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
                <span>Advanced Params</span>
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

                  {/* PEST Shaping Coefficient lambda1 slider */}
                  <div style={{ display: "flex", flexDirection: "column", gap: "2px" }}>
                    <label htmlFor="lambda1-range" style={{ fontSize: "10px", color: "var(--text-dim)" }}>
                      PEST λ₁ (Toroidicity) · visual: <strong style={{ color: "var(--good)" }}>{pestLambda1.toFixed(2)}</strong>
                    </label>
                    <input
                      id="lambda1-range"
                      type="range"
                      min="0.0"
                      max="1.0"
                      step="0.05"
                      value={pestLambda1}
                      onChange={(e) => setPestLambda1(parseFloat(e.target.value))}
                      style={{ accentColor: "var(--good)" }}
                    />
                  </div>

                  {/* PEST Shaping Coefficient lambda2 slider */}
                  <div style={{ display: "flex", flexDirection: "column", gap: "2px" }}>
                    <label htmlFor="lambda2-range" style={{ fontSize: "10px", color: "var(--text-dim)" }}>
                      PEST λ₂ (Elongation) · visual: <strong style={{ color: "var(--good)" }}>{pestLambda2.toFixed(2)}</strong>
                    </label>
                    <input
                      id="lambda2-range"
                      type="range"
                      min="-0.5"
                      max="0.5"
                      step="0.05"
                      value={pestLambda2}
                      onChange={(e) => setPestLambda2(parseFloat(e.target.value))}
                      style={{ accentColor: "var(--good)" }}
                    />
                  </div>

                  {/* Bt Compensation selection */}
                  <div style={{ display: "flex", flexDirection: "column", gap: "2px" }}>
                    <label htmlFor="bt-comp-select" style={{ fontSize: "10px", color: "var(--text-dim)" }}>Bt Alignment Comp. · visual only</label>
                    <select
                      id="bt-comp-select"
                      value={btCompMode}
                      onChange={(e) => setBtCompMode(e.target.value as "none" | "analog" | "digital")}
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
                      <option value="none">None (±18° Bt-leakage noise)</option>
                      <option value="analog">Analog Comp. (±4° noise)</option>
                      <option value="digital">Digital Comp. (±1° noise)</option>
                    </select>
                  </div>

                  {/* Sensor Shielding Cutoff slider */}
                  <div style={{ display: "flex", flexDirection: "column", gap: "2px" }}>
                    <label htmlFor="shielding-cutoff-range" style={{ fontSize: "10px", color: "var(--text-dim)" }}>
                      Sensor Bandwidth · visual: <strong style={{ color: "var(--accent)" }}>{shieldingCutoff} kHz</strong>
                    </label>
                    <input
                      id="shielding-cutoff-range"
                      type="range"
                      min="5"
                      max="50"
                      step="5"
                      value={shieldingCutoff}
                      onChange={(e) => setShieldingCutoff(parseInt(e.target.value))}
                      style={{ accentColor: "var(--accent)" }}
                    />
                    <span style={{ fontSize: "8px", color: "var(--text-dim)", lineHeight: 1.1 }}>
                      Low bandwidth simulates graphite tile attenuation.
                    </span>
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
              <h3 style={{ margin: 0, fontWeight: 600, fontSize: "13px" }}>Spectrogram Ḃp(t, f)</h3>
              <span style={{ fontSize: "11px", color: "var(--text-dim)" }}>
                Active cursor: <strong style={{ color: "var(--good)" }}>{cursorMs ? `${cursorMs.toFixed(1)} ms` : "none"}</strong>
              </span>
            </div>
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
          <div style={{ flex: 1, minHeight: 0 }}>{renderSpectrogram()}</div>
        </div>

        <DraggableDivider direction="vertical" onDelta={handleSpecDelta} />

        {/* Panel 1: Sub-Interval Spectrum */}
        <div className="card" style={{ flexShrink: 0, display: "flex", flexDirection: "column", gap: "12px", margin: 0, height: panel1Height, minHeight: 0 }}>
          <h4 style={{ margin: 0, fontSize: "11px", fontWeight: 600, textTransform: "uppercase", color: "var(--accent)" }}>
            Sub-Interval Spectrum (tslice)
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

        {/* Panel 3: Mode Structure Fits */}
        <div className="card" style={{ flexShrink: 0, display: "flex", flexDirection: "column", gap: "12px", margin: 0, height: panel3Height, minHeight: 0 }}>
          <h4 style={{ margin: 0, fontSize: "11px", fontWeight: 600, textTransform: "uppercase", color: "var(--accent)" }}>
            Mode Structure Fits (Error Bars Active)
          </h4>
          <div style={{ flex: 1, minHeight: 0 }}>
            {renderModeStructure()}
          </div>
        </div>
      </div>
    </div>
  );
}
