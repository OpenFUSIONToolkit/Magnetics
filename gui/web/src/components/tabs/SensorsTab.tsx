// Sensors view — OWNED BY CAPTAIN.
// Build the unrolled φ–θ wall map + R–Z cross-section with visual array selection.
//
// Tools available (src/lib): useNode(machine, "geometry") returns a kind-node;
// render it with <NodeView/>, or build a custom Plotly figure via <Plot/>.
export default function SensorsTab({ machine }: { machine: string }) {
  return (
    <div className="card">
      <h2>Sensors — φ–θ wall map + R–Z cross-section</h2>
      <p className="desc">shot {machine} · build me (VISION §6.4 view 1)</p>
      <div className="placeholder">
        Empty by design. Fetch geometry with <code>useNode(machine, "geometry")</code> and
        render via <code>&lt;NodeView/&gt;</code>, then add visual array selection.
      </div>
    </div>
  );
}
