// Small hook: fetch a named analysis node for a machine and track load/error.
// Views use this instead of hand-rolling fetch + useState each time.
//
// State is keyed by (machine, node, params). Stale-while-revalidate: when the key
// changes we keep returning the last node while the new fetch is in flight, so a
// consumer plot never unmounts/blanks mid-refetch (which crashes Plotly when e.g.
// a time-slider changes the fetch params).
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
    node: entry.node,                                  // keep stale node during refetch
    error: fresh ? entry.error : null,
    loading: entry.node === null && !(fresh && entry.error),
  };
}
