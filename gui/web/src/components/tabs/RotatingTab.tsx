// Rotating-modes view — OWNED BY TEAMMATE B.
// Branch: gui-rotating — build here, PR into `gui`.
// Build the MODESPEC n-colored spectrogram (Ḃ vs time & frequency), a power↔n
// display toggle, a shared time cursor, and phase-vs-φ / phase-vs-θ mode-number
// fits (slope = n, m). VISION §4.2, §7. Summaries: 02_MODESPEC2012,
// 03_PoloidalModeID_MODESPEC, 13_DiagnosticsSeminar_UCIrvine.
//
// Tools (src/lib): useNode(machine, "spectrogram") / ("phase_fit"); render via
// <NodeView/> (heatmap supports `discrete` n-coloring), or custom Plotly via <Plot/>.
export default function RotatingTab({ machine }: { machine: string }) {
  return (
    <div className="card">
      <h2>Rotating modes — spectrogram Ḃp(t, f)</h2>
      <p className="desc">shot {machine} · build me (VISION §4.2)</p>
      <div className="placeholder">
        Empty by design. Hero plot = spectrogram heatmap (color = log power or toroidal
        n, −6…+6). Fetch with <code>useNode(machine, "spectrogram")</code>.
      </div>
    </div>
  );
}
