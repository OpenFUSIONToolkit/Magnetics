// Fits registry — flat list of analyses for the shot with quality flags.
// Demo wiring: shows the live `fit_quality` metrics. Extend into a searchable
// registry. Tools (src/lib): useNode(machine, "fit_quality").
import NodePanel from "../../lib/NodePanel";

export default function FitsTab({ machine }: { machine: string }) {
  return (
    <div className="card">
      <h2>Saved fits</h2>
      <p className="desc">shot {machine} · quality of the current pull</p>
      <NodePanel machine={machine} nodeId="fit_quality" />
    </div>
  );
}
