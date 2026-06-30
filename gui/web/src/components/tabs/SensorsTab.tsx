// Sensors view — the static device sensor layout.
//
//   • R-Z poloidal cross-section: the vessel wall, Bp point probes as dots, and
//     saddle loops drawn as their true poloidal extent (a segment along the wall).
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
import Plot from "../../lib/Plot";

type Kind = "Bp" | "Br" | "coil";
interface Sensor {
  name: string; family: string; kind: Kind; shape: "point" | "loop";
  phi: number; r: number; z: number; length: number; delta_phi: number; tilt: number;
}
interface Wall { r: number[]; z: number[]; label: string }
interface GeoMeta {
  n_sensors: number; device: string; sensors: Sensor[]; wall: Wall;
  arrays: { family: string; kind: Kind; shape: string; count: number }[];
}

const COLOR: Record<Kind, string> = { Bp: "#4aa3ff", Br: "#ff5cad", coil: "#ffb454" };
const KIND_LABEL: Record<Kind, string> = {
  Bp: "Bp probes", Br: "Br saddle loops", coil: "coils",
};
const KINDS: Kind[] = ["Bp", "Br", "coil"];
const d2r = (deg: number) => (deg * Math.PI) / 180;

export default function SensorsTab({ machine }: { machine: string }) {
  const dark = useStore((s) => s.theme === "dark");
  const { node, error, loading } = useNode(machine, "geometry");
  const meta = (node?.meta as unknown as GeoMeta) ?? null;
  const wallInk = dark ? "rgba(255,255,255,0.30)" : "rgba(20,34,46,0.35)";

  const [visible, setVisible] = useState<Record<Kind, boolean>>({ Bp: true, Br: true, coil: false });
  const toggle = (k: Kind) => setVisible((v) => ({ ...v, [k]: !v[k] }));

  // Which kinds actually exist in this device's table.
  const present = useMemo(() => {
    const set = new Set<Kind>();
    meta?.sensors.forEach((s) => set.add(s.kind));
    return KINDS.filter((k) => set.has(k));
  }, [meta]);

  // Vessel center (for the local poloidal-tangent direction of each loop).
  const Rc = useMemo(() => {
    if (!meta) return 1.7;
    const r = meta.wall.r;
    return (Math.max(...r) + Math.min(...r)) / 2;
  }, [meta]);

  const shownKinds = useMemo(() => present.filter((k) => visible[k]), [present, visible]);

  const traces2d = useMemo<Partial<Plotly.PlotData>[]>(() => {
    if (!meta) return [];
    const t: Partial<Plotly.PlotData>[] = [{
      type: "scatter", mode: "lines", name: meta.wall.label,
      x: meta.wall.r, y: meta.wall.z, hoverinfo: "skip",
      line: { color: wallInk, width: 1.5 },
    } as Partial<Plotly.PlotData>];

    for (const kind of shownKinds) {
      const group = meta.sensors.filter((s) => s.kind === kind);
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
        // Each loop projects onto R-Z as a segment of its poloidal length, laid
        // along the local wall tangent through the sensor center.
        const x: (number | null)[] = [], y: (number | null)[] = [], txt: (string | null)[] = [];
        for (const s of loops) {
          const u = Math.atan2(s.z, s.r - Rc);
          const tr = -Math.sin(u), tz = Math.cos(u), h = s.length / 2;
          x.push(s.r - h * tr, s.r + h * tr, null);
          y.push(s.z - h * tz, s.z + h * tz, null);
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
  }, [meta, Rc, wallInk, shownKinds]);

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
      type: "surface", showscale: false, opacity: 0.1, hoverinfo: "skip",
      colorscale: [[0, wallInk], [1, wallInk]],
      // Suppress the surface's hover cross-section trace lines (the wall
      // "cross sections"); we only want the spike lines to the hovered point.
      contours: {
        x: { highlight: false }, y: { highlight: false }, z: { highlight: false },
      },
      x: ru.map((R) => phis.map((p) => R * Math.cos(p))),
      y: ru.map((R) => phis.map((p) => R * Math.sin(p))),
      z: ru.map((_, i) => phis.map(() => zu[i])),
    } as unknown as Partial<Plotly.PlotData>);

    for (const kind of shownKinds) {
      const group = meta.sensors.filter((s) => s.kind === kind);
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
  }, [meta, Rc, wallInk, shownKinds]);

  const legend = { orientation: "h" as const, font: { size: 10 }, y: 1.12 };

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
          <div style={{ display: "flex", gap: 16, flexWrap: "wrap", margin: "0 0 12px" }}>
            {present.map((k) => (
              <label key={k} style={{ display: "flex", alignItems: "center", gap: 6, cursor: "pointer", fontSize: 13 }}>
                <input type="checkbox" checked={visible[k]} onChange={() => toggle(k)} />
                <span style={{ width: 10, height: 10, borderRadius: 2, background: COLOR[k], display: "inline-block" }} />
                {KIND_LABEL[k]}
              </label>
            ))}
          </div>

          <div style={{ display: "flex", flexWrap: "wrap", gap: 16 }}>
            <div style={{ flex: "1 1 360px", minWidth: 320 }}>
              <Plot
                height={460}
                data={traces2d}
                layout={{
                  showlegend: true, legend,
                  xaxis: { title: { text: "R (m)" } },
                  yaxis: { title: { text: "Z (m)" }, scaleanchor: "x", scaleratio: 1 },
                } as Partial<Plotly.Layout>}
              />
            </div>
            <div style={{ flex: "1 1 360px", minWidth: 320 }}>
              <Plot
                height={460}
                data={traces3d}
                layout={{
                  showlegend: true, legend,
                  scene: {
                    aspectmode: "data",
                    // Hover spikes: a single line from the point to each axis,
                    // not the projected cross-sections on the cube walls.
                    xaxis: { title: { text: "X (m)" }, showspikes: true, spikesides: false, spikethickness: 1.5 },
                    yaxis: { title: { text: "Y (m)" }, showspikes: true, spikesides: false, spikethickness: 1.5 },
                    zaxis: { title: { text: "Z (m)" }, showspikes: true, spikesides: false, spikethickness: 1.5 },
                  },
                } as Partial<Plotly.Layout>}
              />
            </div>
          </div>
        </>
      )}
    </div>
  );
}
