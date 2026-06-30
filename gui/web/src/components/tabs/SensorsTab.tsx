// Sensors view — unrolled φ–θ wall map with visual array selection.
// Consumes the real `geometry` node (a scatter2d of sensor positions grouped by
// family) and lets the user toggle array families on/off. R–Z cross-section is a
// follow-up (the geometry node carries φ–θ only today).
import { useMemo, useState } from "react";
import { useNode } from "../../lib/useNode";
import Plot from "../../lib/Plot";

export default function SensorsTab({ machine }: { machine: string }) {
  const { node, loading, error } = useNode(machine, "geometry");
  const [hidden, setHidden] = useState<Record<string, boolean>>({});

  const isGeom = node?.kind === "scatter2d";

  // Sensor families present in this shot (the selectable array groups).
  const families = useMemo(() => {
    if (!isGeom) return [];
    const fams = node.points.map((p) => p.group ?? p.label ?? "other");
    return Array.from(new Set(fams)).sort();
  }, [node, isGeom]);

  // One Plotly trace per visible family — square markers, the SLCONTOUR convention.
  const traces = useMemo(() => {
    if (!isGeom) return [];
    return families
      .filter((f) => !hidden[f])
      .map((f) => {
        const pts = node.points.filter((p) => (p.group ?? p.label ?? "other") === f);
        return {
          type: "scatter" as const,
          mode: "markers" as const,
          name: f,
          x: pts.map((p) => p.x),
          y: pts.map((p) => p.y),
          text: pts.map((p) => p.label ?? ""),
          marker: { size: 7, symbol: "square" as const },
        };
      });
  }, [node, isGeom, families, hidden]);

  const toggle = (f: string) => setHidden((h) => ({ ...h, [f]: !h[f] }));

  return (
    <div className="card">
      <h2>Sensors — φ–θ wall map</h2>
      <p className="desc">shot {machine} · visual array selection (VISION §6.4 view 1)</p>

      {isGeom && (
        <div style={{ display: "flex", flexWrap: "wrap", gap: "10px", margin: "8px 0" }}>
          {families.map((f) => (
            <label key={f} style={{ fontSize: "12px", color: "var(--text)", cursor: "pointer" }}>
              <input
                type="checkbox"
                checked={!hidden[f]}
                onChange={() => toggle(f)}
                style={{ marginRight: "4px", accentColor: "var(--accent)" }}
              />
              {f}
            </label>
          ))}
        </div>
      )}

      {isGeom ? (
        <Plot
          data={traces}
          layout={{
            xaxis: { title: { text: node.axes.x }, range: [0, 360] },
            yaxis: { title: { text: node.axes.y } },
            margin: { l: 55, r: 15, t: 10, b: 45 },
          }}
          height={440}
        />
      ) : (
        <div className="placeholder">
          {loading ? "Loading geometry…" : error ? `No geometry node: ${error}` : "No geometry"}
        </div>
      )}
    </div>
  );
}
