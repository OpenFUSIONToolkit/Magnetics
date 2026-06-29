// Rotating-modes view — OWNED BY TEAMMATE B.
// Demo wiring: renders the live `spectrogram` (real Hann-windowed STFT of a Ḃ
// channel) + the best-effort `phase_fit` (phase-vs-φ, slope → n). Extend with the
// n-coloring toggle and the shared time cursor.
import NodePanel from "../../lib/NodePanel";

export default function RotatingTab({ machine }: { machine: string }) {
  return (
    <div className="card">
      <h2>Rotating modes — spectrogram Ḃp(t, f)</h2>
      <p className="desc">shot {machine} · STFT of a bdot probe · phase-vs-φ fit</p>
      <NodePanel machine={machine} nodeId="spectrogram" height={420} />
      <NodePanel machine={machine} nodeId="phase_fit" height={320} />
    </div>
  );
}
