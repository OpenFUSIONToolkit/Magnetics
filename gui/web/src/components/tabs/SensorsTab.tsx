// Sensors view — OWNED BY CAPTAIN.
// Demo wiring: renders the live `geometry` node (φ–θ wall map; sensor angles
// parsed from the fetched channel set). Extend with the R–Z cross-section and
// visual array selection. Tools (src/lib): useNode / NodeView / Plot.
import NodePanel from "../../lib/NodePanel";

export default function SensorsTab({ machine }: { machine: string }) {
  return (
    <div className="card">
      <h2>Sensors — φ–θ wall map</h2>
      <p className="desc">shot {machine} · sensor positions from the fetched channels</p>
      <NodePanel machine={machine} nodeId="geometry" height={460} />
    </div>
  );
}
