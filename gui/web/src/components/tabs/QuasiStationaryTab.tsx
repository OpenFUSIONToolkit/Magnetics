// Quasi-stationary view — OWNED BY TEAMMATE A.
// Branch: gui-quasistationary — build here, PR into `gui`.
// Build the SLCONTOUR φ–θ δBp contour (sensor markers overlaid), a time-slice
// scrubber, n/m amplitude & phase vs time, and the K/χ² quality panel.
// VISION §4.1, §7. Summaries: 04_SLCONTOUR_summary2019, 08_Slcontour_II_2023, 12_RSI2016.
//
// Tools (src/lib): useNode(machine, "contour") / ("fit_quality"); render via
// <NodeView/>, or build custom Plotly via <Plot/>. Shared time cursor: store.cursorMs.
export default function QuasiStationaryTab({ machine }: { machine: string }) {
  return (
    <div className="card">
      <h2>Quasi-stationary — spatial fit δBp(φ, θ)</h2>
      <p className="desc">shot {machine} · build me (VISION §4.1)</p>
      <div className="placeholder">
        Empty by design. Hero plot = filled φ–θ contour, ±~40 G diverging, white squares
        = sensors. Fetch with <code>useNode(machine, "contour")</code>.
      </div>
    </div>
  );
}
