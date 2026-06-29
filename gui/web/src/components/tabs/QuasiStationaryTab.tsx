// Quasi-stationary view — OWNED BY TEAMMATE A.
// Demo wiring: renders the live `contour` (raw δBp(φ,t) over the toroidal array;
// full SLCONTOUR φ–θ fit pending) + the `fit_quality` metrics (real condition
// number K). Extend with the time-slice scrubber and n/m amp/phase vs time.
import NodePanel from "../../lib/NodePanel";

export default function QuasiStationaryTab({ machine }: { machine: string }) {
  return (
    <div className="card">
      <h2>Quasi-stationary — δBp over the toroidal array</h2>
      <p className="desc">shot {machine} · raw field map (SLCONTOUR φ–θ fit pending)</p>
      <NodePanel machine={machine} nodeId="contour" height={420} />
      <NodePanel machine={machine} nodeId="fit_quality" />
    </div>
  );
}
