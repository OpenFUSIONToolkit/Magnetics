// Fits registry — flat, searchable list of saved analyses for the shot, with
// quality flags. Lowest priority; whoever finishes their view first picks it up.
//
// Tools (src/lib): useNode(machine, "fit_quality") returns a metrics node.
export default function FitsTab({ machine }: { machine: string }) {
  return (
    <div className="card">
      <h2>Saved fits</h2>
      <p className="desc">shot {machine} · build me (searchable registry + quality flags)</p>
      <div className="placeholder">Empty by design.</div>
    </div>
  );
}
