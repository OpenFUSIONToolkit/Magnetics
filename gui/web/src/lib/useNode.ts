// Small hook: fetch a named analysis node for a machine and track load/error.
// Views use this instead of hand-rolling fetch + useState each time.
//
// State is keyed by (machine, node, params): when those change, the stored key
// no longer matches and we report `loading` until the new fetch resolves — so
// stale data never flashes, without calling setState synchronously in the effect.
import { useEffect, useState } from "react";
import { fetchNode } from "./api";
import type { Node } from "./contract";

interface Entry { key: string; node: Node | null; error: string | null }

export function useNode(
  machine: string | null,
  nodeId: string,
  params?: Record<string, string | number>,
) {
  const key = `${machine}::${nodeId}::${params ? JSON.stringify(params) : ""}`;
  const [entry, setEntry] = useState<Entry>({ key, node: null, error: null });

  useEffect(() => {
    if (!machine) return;
    let alive = true;
    fetchNode(machine, nodeId, params)
      .then((n) => { if (alive) setEntry({ key, node: n, error: null }); })
      .catch((e) => { if (alive) setEntry({ key, node: null, error: String(e) }); });
    return () => { alive = false; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [machine, nodeId, key]);

  const fresh = entry.key === key;
  return {
    node: fresh ? entry.node : null,
    error: fresh ? entry.error : null,
    loading: !fresh || (!entry.node && !entry.error),
  };
}
