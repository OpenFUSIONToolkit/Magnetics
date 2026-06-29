// Tiny helper: fetch a named node for a machine and render it via <NodeView>,
// with loading / error states. Tabs use this so each panel is one line.
import { useNode } from "./useNode";
import NodeView from "./NodeView";

export default function NodePanel({
  machine,
  nodeId,
  height,
}: {
  machine: string;
  nodeId: string;
  height?: number;
}) {
  const { node, loading, error } = useNode(machine, nodeId);
  if (loading) return <div className="placeholder">loading {nodeId}…</div>;
  if (error) return <div className="placeholder">⚠ {nodeId}: {error}</div>;
  if (!node) return null;
  return <NodeView node={node} height={height} />;
}
