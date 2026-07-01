// Sensors view — the static device sensor layout.
//
//   • R-Z poloidal cross-section: the vessel wall, Bp point probes as dots, and
//     saddle loops drawn as their poloidal extent (a segment along the loop's tilt).
//   • 3D: every sensor in machine coordinates — Bp probes as points, saddle loops
//     and coils as their real toroidal × poloidal band, curved around the torus,
//     inside a faint vessel surface.
//
// All geometry comes from one `geometry` node via useNode(machine, "geometry").
// The node is a scatter2d (R-Z points) whose `meta` carries the full per-sensor
// records + the vessel outline; the backend owns every device specific (which
// family is Bp vs a saddle loop, the wall shape), so this view is device-agnostic.
import { useMemo, useState } from "react";
import type * as Plotly from "plotly.js";
import { useStore } from "../../store";
import { useNode } from "../../lib/useNode";
import { usingLiveBackend } from "../../lib/api";
import type { EquilibriumNode } from "../../lib/contract";
import { d2r, loopSegment2d } from "../../lib/sensorGeometry";
import Plot from "../../lib/Plot";

type Kind = "Bp" | "Br" | "coil";
interface Sensor {
  name: string; family: string; kind: Kind; shape: "point" | "loop";
  phi: number; r: number; z: number; length: number; delta_phi: number; tilt: number;
}
interface Wall { r: number[]; z: number[]; label: string }
interface SensorSet { name: string; kind: Kind; count: number; sensors: string[] }
interface VVPlate { r: number[]; z: number[] }
interface CoilSet {
  name: string; count: number; turns: number;
  rz: { r: number[]; z: number[] }; // one representative coil's R-Z footprint
  loops: number[][][]; // every coil's 3D [x,y,z] loop
}
interface GeoMeta {
  n_sensors: number; device: string; sensors: Sensor[]; wall: Wall;
  arrays: { family: string; kind: Kind; shape: string; count: number }[];
  sensor_sets: SensorSet[];
  vv?: VVPlate[]; coils?: CoilSet[];
}

const COLOR: Record<Kind, string> = { Bp: "#4aa3ff", Br: "#ff5cad", coil: "#ffb454" };
const KIND_LABEL: Record<Kind, string> = {
  Bp: "Bp probes", Br: "Br saddle loops", coil: "coils",
};
const KINDS: Kind[] = ["Bp", "Br", "coil"];
// Sensors time-cursor window (ms), until a real equilibrium node supplies bounds.
const EQ_TIME_RANGE: [number, number] = [100, 5000];
// No backend `equilibrium` node exists yet (tracked in #43). Until it does, don't
// request one — otherwise every time-cursor move fires a 404. Flip to true when the
// service serves `equilibrium` and the overlay + fetch light up automatically.
const EQUILIBRIUM_BACKEND = false;

// 2D cross-section: scroll to zoom, drag to pan, toolbar for zoom/reset.
const PAN_CONFIG: Partial<Plotly.Config> = {
  scrollZoom: true,
  displayModeBar: true,
  displaylogo: false,
  modeBarButtonsToRemove: ["lasso2d", "select2d"],
};

const LEGEND = { orientation: "h" as const, font: { size: 10 }, y: 1.12 };
// 2D: legend sits BELOW the R-Z plot so it never overlaps the (tall, narrow) scene.
const LEGEND_2D = {
  orientation: "h" as const, font: { size: 10 },
  x: 0.5, xanchor: "center" as const, y: -0.16, yanchor: "top" as const,
};

// Stable layouts (module constants) + a constant `uirevision`, so re-plotting on
// a slider move never resets the user's 3D camera or 2D zoom/pan.
const LAYOUT_2D = {
  showlegend: true, legend: LEGEND_2D, dragmode: "pan", uirevision: "sensors",
  margin: { t: 24, r: 16, b: 96, l: 56 },
  xaxis: { title: { text: "R (m)" } },
  yaxis: { title: { text: "Z (m)" }, scaleanchor: "x", scaleratio: 1 },
} as Partial<Plotly.Layout>;

const LAYOUT_3D = {
  showlegend: true, legend: LEGEND, uirevision: "sensors",
  scene: {
    aspectmode: "data",
    // Hover spikes: a single line from the point to each axis, not the
    // projected cross-sections on the cube walls.
    xaxis: { title: { text: "X (m)" }, showspikes: true, spikesides: false, spikethickness: 1.5 },
    yaxis: { title: { text: "Y (m)" }, showspikes: true, spikesides: false, spikethickness: 1.5 },
    zaxis: { title: { text: "Z (m)" }, showspikes: true, spikesides: false, spikethickness: 1.5 },
  },
} as Partial<Plotly.Layout>;

export default function SensorsTab({ machine }: { machine: string }) {
  const dark = useStore((s) => s.theme === "dark");
  const cursorMs = useStore((s) => s.cursorMs);
  const { node, error, loading } = useNode(machine, "geometry");
  // The Sensors scene needs the rich geometry meta (sensors + wall + sensor_sets);
  // the backend geometry node currently supplies only n_sensors, so treat an
  // incomplete meta as absent. The `if (!meta)` guards below then render an empty
  // scene instead of crashing the whole app on meta.sensors / meta.wall.
  const rawMeta = node?.meta as unknown as GeoMeta | undefined;
  const meta = rawMeta?.sensors && rawMeta?.wall ? rawMeta : null;
  const wallInk = dark ? "rgba(255,255,255,0.30)" : "rgba(20,34,46,0.35)";
  const fluxInk = dark ? "rgba(120,170,255,0.55)" : "rgba(40,90,180,0.55)";
  const vvInk = dark ? "rgba(255,255,255,0.16)" : "rgba(20,34,46,0.18)";
  // 3D vessel shell — brighter/whiter than the 2D outline so it reads in the
  // dark scene; lighter mode bumped up slightly too.
  const wallSurface = dark ? "rgb(225,232,245)" : "rgb(70,90,110)";
  const wallSurfaceOpacity = dark ? 0.22 : 0.16;

  const [showEq, setShowEq] = useState(true);
  const [showVV, setShowVV] = useState(true);
  const [showCoils, setShowCoils] = useState(true);

  // Sensor-set selection (driven by the device's curated `sensor_sets`). A sensor
  // is shown if it belongs to ANY checked set. Default: the broadest Bp + Br set.
  const sets = useMemo<SensorSet[]>(() => meta?.sensor_sets ?? [], [meta]);
  // User's explicit checkbox overrides; null until the first toggle, before which
  // the default selection (broadest Bp + Br set) is derived from `sets` at render.
  const [userSets, setUserSets] = useState<Record<string, boolean> | null>(null);
  const selectedSets = useMemo<Record<string, boolean>>(() => {
    if (userSets) return userSets;
    const init: Record<string, boolean> = {};
    const widest: Partial<Record<Kind, SensorSet>> = {};
    for (const set of sets) {
      init[set.name] = false;
      if (set.kind !== "coil" && (!widest[set.kind] || set.count > widest[set.kind]!.count))
        widest[set.kind] = set;
    }
    Object.values(widest).forEach((s) => { if (s) init[s.name] = true; });
    return init;
  }, [sets, userSets]);
  const toggleSet = (name: string) =>
    setUserSets((prev) => {
      const base = prev ?? selectedSets;
      return { ...base, [name]: !base[name] };
    });

  // Equilibrium overlay. Only the real backend node is drawn; when absent (today
  // it always is — no equilibrium node yet) nothing is added to the plot or the
  // legend. Real EFIT/boundary plotting is tracked as a follow-up.
  const live = usingLiveBackend();
  const [tmin, tmax] = EQ_TIME_RANGE;
  const tNow = Math.min(tmax, Math.max(tmin, cursorMs || tmin));
  const eqLive = useNode(EQUILIBRIUM_BACKEND && live ? machine : null, "equilibrium", { time: tNow });
  const equilibrium = useMemo<EquilibriumNode | null>(() => {
    if (!showEq) return null;
    return eqLive.node as unknown as EquilibriumNode | null;
  }, [showEq, eqLive.node]);

  // Sensors visible under the current set selection (union of checked sets).
  const visibleSensors = useMemo(() => {
    if (!meta) return [];
    const names = new Set<string>();
    for (const set of sets) if (selectedSets[set.name]) set.sensors.forEach((n) => names.add(n));
    return meta.sensors.filter((s) => names.has(s.name));
  }, [meta, sets, selectedSets]);

  // Vessel center (for the local poloidal-tangent direction of each loop).
  const Rc = useMemo(() => {
    if (!meta) return 1.7;
    const r = meta.wall.r;
    return (Math.max(...r) + Math.min(...r)) / 2;
  }, [meta]);

  const traces2d = useMemo<Partial<Plotly.PlotData>[]>(() => {
    if (!meta) return [];
    const t: Partial<Plotly.PlotData>[] = [];

    // Equilibrium first, so flux surfaces sit under the wall + sensors.
    if (equilibrium) {
      const lv = equilibrium.levels ?? [0.2, 0.4, 0.6, 0.8, 1.0];
      t.push({
        type: "contour", x: equilibrium.r, y: equilibrium.z, z: equilibrium.psi_n,
        autocontour: false,
        contours: { coloring: "lines", start: Math.min(...lv), end: 1.0, size: lv.length > 1 ? lv[1] - lv[0] : 0.2 },
        colorscale: [[0, fluxInk], [1, fluxInk]], showscale: false, hoverinfo: "skip",
        name: "flux surfaces", showlegend: false,
      } as unknown as Partial<Plotly.PlotData>);
      t.push({
        type: "scatter", mode: "lines", name: "LCFS (synthetic)",
        x: equilibrium.boundary.r, y: equilibrium.boundary.z,
        line: { color: "#2ee6cf", width: 2 }, hoverinfo: "skip",
      } as Partial<Plotly.PlotData>);
      t.push({
        type: "scatter", mode: "markers", x: [equilibrium.axis.r], y: [equilibrium.axis.z],
        marker: { symbol: "cross", size: 8, color: "#2ee6cf" }, hoverinfo: "skip", showlegend: false,
      } as Partial<Plotly.PlotData>);
    }

    t.push({
      type: "scatter", mode: "lines", name: meta.wall.label,
      x: meta.wall.r, y: meta.wall.z, hoverinfo: "skip",
      line: { color: wallInk, width: 1.5 },
    } as Partial<Plotly.PlotData>);

    // Vacuum-vessel plates — one combined, null-separated outline under everything.
    const vv = meta.vv ?? [];
    if (showVV && vv.length) {
      const vx: (number | null)[] = [], vy: (number | null)[] = [];
      for (const plate of vv) {
        plate.r.forEach((r, i) => { vx.push(r); vy.push(plate.z[i]); });
        vx.push(null); vy.push(null);
      }
      t.push({
        type: "scatter", mode: "lines", name: "vacuum vessel", x: vx, y: vy,
        hoverinfo: "skip", showlegend: false, line: { color: vvInk, width: 1 },
      } as Partial<Plotly.PlotData>);
    }

    // Perturbation coils — one representative coil's R-Z footprint per set.
    const coils2d = meta.coils ?? [];
    if (showCoils) {
      for (const c of coils2d) {
        t.push({
          type: "scatter", mode: "lines", legendgroup: "coils",
          name: `${c.name}-coils (×${c.count}, ${c.turns > 0 ? "+" : ""}${c.turns}T)`,
          x: c.rz.r, y: c.rz.z, hoverinfo: "name", line: { color: COLOR.coil, width: 2 },
        } as Partial<Plotly.PlotData>);
      }
    }

    for (const kind of KINDS) {
      const group = visibleSensors.filter((s) => s.kind === kind);
      if (!group.length) continue;
      const points = group.filter((s) => s.shape === "point");
      const loops = group.filter((s) => s.shape === "loop");
      let legendShown = false;

      if (points.length) {
        t.push({
          type: "scatter", mode: "markers", name: KIND_LABEL[kind],
          legendgroup: kind, x: points.map((s) => s.r), y: points.map((s) => s.z),
          text: points.map((s) => s.name), hoverinfo: "text",
          marker: { size: 6, color: COLOR[kind], line: { color: wallInk, width: 0.5 } },
        } as Partial<Plotly.PlotData>);
        legendShown = true;
      }
      if (loops.length) {
        // Each loop projects onto R-Z as a segment of its poloidal length, oriented
        // by the sensor's own tilt (its real angle in the R-Z plane, measured from
        // +R toward +Z) — NOT the vessel tangent, which points off-midplane loops
        // the wrong way. The segment is symmetric, so tilt's sign/wrap is moot.
        const x: (number | null)[] = [], y: (number | null)[] = [], txt: (string | null)[] = [];
        for (const s of loops) {
          const seg = loopSegment2d(s);
          x.push(seg.x[0], seg.x[1], null);
          y.push(seg.y[0], seg.y[1], null);
          txt.push(s.name, s.name, null);
        }
        t.push({
          type: "scatter", mode: "lines", name: KIND_LABEL[kind],
          legendgroup: kind, showlegend: !legendShown,
          x, y, text: txt, hoverinfo: "text",
          line: { color: COLOR[kind], width: 2.5 },
        } as Partial<Plotly.PlotData>);
      }
    }
    return t;
  }, [meta, wallInk, visibleSensors, equilibrium, fluxInk, showVV, showCoils, vvInk]);

  const traces3d = useMemo<Partial<Plotly.PlotData>[]>(() => {
    if (!meta) return [];
    const t: Partial<Plotly.PlotData>[] = [];

    // Faint vessel: sweep the wall outline around the torus.
    const phiN = 60;
    const phis = Array.from({ length: phiN + 1 }, (_, j) => (j / phiN) * 2 * Math.PI);
    const ru: number[] = [], zu: number[] = [];
    const step = Math.max(1, Math.floor(meta.wall.r.length / 64));
    for (let i = 0; i < meta.wall.r.length; i += step) { ru.push(meta.wall.r[i]); zu.push(meta.wall.z[i]); }
    t.push({
      type: "surface", showscale: false, opacity: wallSurfaceOpacity, hoverinfo: "skip",
      colorscale: [[0, wallSurface], [1, wallSurface]],
      // Flat, even shading so the shell reads uniformly bright (no dark facets).
      lighting: { ambient: 1.0, diffuse: 0.0, specular: 0.0, fresnel: 0.0 },
      // Suppress the surface's hover cross-section trace lines (the wall
      // "cross sections"); we only want the spike lines to the hovered point.
      contours: {
        x: { highlight: false }, y: { highlight: false }, z: { highlight: false },
      },
      x: ru.map((R) => phis.map((p) => R * Math.cos(p))),
      y: ru.map((R) => phis.map((p) => R * Math.sin(p))),
      z: ru.map((_, i) => phis.map(() => zu[i])),
    } as unknown as Partial<Plotly.PlotData>);

    // Perturbation coils — every coil's real 3D loop.
    if (showCoils) {
      for (const c of meta.coils ?? []) {
        const cx: (number | null)[] = [], cy: (number | null)[] = [], cz: (number | null)[] = [];
        for (const loop of c.loops) {
          for (const p of loop) { cx.push(p[0]); cy.push(p[1]); cz.push(p[2]); }
          cx.push(null); cy.push(null); cz.push(null);
        }
        t.push({
          type: "scatter3d", mode: "lines", name: `${c.name}-coils`, legendgroup: "coils",
          x: cx, y: cy, z: cz, hoverinfo: "name", line: { color: COLOR.coil, width: 2 },
        } as unknown as Partial<Plotly.PlotData>);
      }
    }

    for (const kind of KINDS) {
      const group = visibleSensors.filter((s) => s.kind === kind);
      if (!group.length) continue;
      const points = group.filter((s) => s.shape === "point");
      const loops = group.filter((s) => s.shape === "loop");
      let legendShown = false;

      if (points.length) {
        t.push({
          type: "scatter3d", mode: "markers", name: KIND_LABEL[kind], legendgroup: kind,
          x: points.map((s) => s.r * Math.cos(d2r(s.phi))),
          y: points.map((s) => s.r * Math.sin(d2r(s.phi))),
          z: points.map((s) => s.z),
          text: points.map((s) => s.name), hoverinfo: "text",
          marker: { size: 2.5, color: COLOR[kind] },
        } as unknown as Partial<Plotly.PlotData>);
        legendShown = true;
      }
      if (loops.length) {
        // True loop: ±length/2 poloidally, ±delta_phi/2 toroidally, with the
        // toroidal edges densified into arcs so wide loops/coils curve around
        // the machine instead of cutting across as straight chords.
        const x: (number | null)[] = [], y: (number | null)[] = [], z: (number | null)[] = [];
        const txt: (string | null)[] = [];
        for (const s of loops) {
          const u = Math.atan2(s.z, s.r - Rc);
          const tr = -Math.sin(u), tz = Math.cos(u), h = s.length / 2;
          const Rp = s.r + h * tr, Zp = s.z + h * tz, Rm = s.r - h * tr, Zm = s.z - h * tz;
          const seg = Math.max(2, Math.ceil(s.delta_phi / 6));
          const arc = Array.from({ length: seg + 1 },
            (_, k) => d2r(s.phi - s.delta_phi / 2 + (k / seg) * s.delta_phi));
          for (const p of arc) { x.push(Rp * Math.cos(p)); y.push(Rp * Math.sin(p)); z.push(Zp); txt.push(s.name); }
          for (let k = arc.length - 1; k >= 0; k--) {
            const p = arc[k]; x.push(Rm * Math.cos(p)); y.push(Rm * Math.sin(p)); z.push(Zm); txt.push(s.name);
          }
          const p0 = arc[0]; x.push(Rp * Math.cos(p0), null); y.push(Rp * Math.sin(p0), null);
          z.push(Zp, null); txt.push(s.name, null);
        }
        t.push({
          type: "scatter3d", mode: "lines", name: KIND_LABEL[kind],
          legendgroup: kind, showlegend: !legendShown,
          x, y, z, text: txt, hoverinfo: "text",
          line: { color: COLOR[kind], width: 3 },
        } as unknown as Partial<Plotly.PlotData>);
      }
    }
    return t;
  }, [meta, Rc, visibleSensors, wallSurface, wallSurfaceOpacity, showCoils]);

  return (
    <div className="card">
      <h2>Sensors — R-Z cross-section + 3D layout</h2>
      <p className="desc">
        shot {machine}
        {meta && <> · {meta.device} · {meta.n_sensors} sensors</>}
      </p>

      {loading && <div className="placeholder">loading geometry…</div>}
      {error && <div className="placeholder">geometry unavailable: {error}</div>}

      {meta && (
        <>
          {/* Sensor-set selection, grouped by kind. Check any sets to show them. */}
          <div style={{ display: "flex", gap: 24, flexWrap: "wrap", margin: "0 0 12px", fontSize: 13 }}>
            {KINDS.map((kind) => {
              const ks = sets.filter((s) => s.kind === kind);
              if (!ks.length) return null;
              return (
                <div key={kind} style={{ minWidth: 150 }}>
                  <div style={{ display: "flex", alignItems: "center", gap: 6, fontWeight: 600, marginBottom: 4 }}>
                    <span style={{ width: 10, height: 10, borderRadius: 2, background: COLOR[kind], display: "inline-block" }} />
                    {KIND_LABEL[kind]}
                  </div>
                  <div style={{ display: "flex", flexDirection: "column", gap: 2 }}>
                    {ks.map((s) => (
                      <label key={s.name} style={{ display: "flex", alignItems: "center", gap: 6, cursor: "pointer" }}>
                        <input type="checkbox" checked={!!selectedSets[s.name]} onChange={() => toggleSet(s.name)} />
                        {s.name} <span style={{ opacity: 0.5 }}>({s.count})</span>
                      </label>
                    ))}
                  </div>
                </div>
              );
            })}
            <div style={{ minWidth: 150 }}>
              <div style={{ fontWeight: 600, marginBottom: 4 }}>overlays</div>
              <label style={{ display: "flex", alignItems: "center", gap: 6, cursor: "pointer" }}>
                <input type="checkbox" checked={showEq} onChange={() => setShowEq((v) => !v)} />
                <span style={{ width: 10, height: 10, borderRadius: 2, background: "#2ee6cf", display: "inline-block" }} />
                equilibrium
              </label>
              <label style={{ display: "flex", alignItems: "center", gap: 6, cursor: "pointer" }}>
                <input type="checkbox" checked={showVV} onChange={() => setShowVV((v) => !v)} />
                <span style={{ width: 10, height: 10, borderRadius: 2, background: vvInk, display: "inline-block" }} />
                vacuum vessel
              </label>
              <label style={{ display: "flex", alignItems: "center", gap: 6, cursor: "pointer" }}>
                <input type="checkbox" checked={showCoils} onChange={() => setShowCoils((v) => !v)} />
                <span style={{ width: 10, height: 10, borderRadius: 2, background: COLOR.coil, display: "inline-block" }} />
                coils
              </label>
            </div>
          </div>

          {/* No time cursor here: sensor geometry is shot-static, and the only
              time-dependent overlay (equilibrium) is a future backend node (#43). */}
          <div style={{ display: "flex", flexWrap: "wrap", gap: 16 }}>
            <div style={{ flex: "1 1 360px", minWidth: 320 }}>
              <Plot height={460} data={traces2d} config={PAN_CONFIG} layout={LAYOUT_2D} exportName={`shot_${machine}_sensors_2d`} />
            </div>
            <div style={{ flex: "1 1 360px", minWidth: 320 }}>
              <Plot height={460} data={traces3d} layout={LAYOUT_3D} exportName={`shot_${machine}_sensors_3d`} />
            </div>
          </div>
        </>
      )}
    </div>
  );
}
