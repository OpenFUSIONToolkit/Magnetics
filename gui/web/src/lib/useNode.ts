// Small hook: fetch a named analysis node for a machine and track load/error.
// Views use this instead of hand-rolling fetch + useState each time.
//
// State is keyed by (machine, node, params). Stale-while-revalidate is
// PARAM-scoped only: when params change we keep returning the last node while
// the new fetch is in flight, so a consumer plot never unmounts/blanks
// mid-refetch (which crashes Plotly when e.g. a time-slider changes the fetch
// params). A MACHINE change drops the stale node immediately — the previous
// shot's data must never render under the new shot's labels (or leak into its
// PNG/HDF5 export descriptors).
//
// `retryKey`: bump to re-run the fetch for an IDENTICAL key — without it, a
// transient failure was unrecoverable from the UI (the QS "Plot" button with
// unchanged params re-ran no effect).
import { useEffect, useState } from "react";
import { useStore } from "../store";
import { fetchNode } from "./api";
import type { Node } from "./contract";

interface Entry { key: string; machine: string | null; node: Node | null; error: string | null }

export function useNode(
  machine: string | null,
  nodeId: string,
  params?: Record<string, string | number>,
  retryKey: number = 0,
) {
  // Bad-channel exclusions (#56) live server-side and change what EVERY node
  // returns, but appear in no node's params — so fold the revision counter into
  // the fetch key here rather than threading it through ~30 call sites. One
  // toggle in the Sensors view then re-fits every open view.
  const excludedRev = useStore((s) => s.excludedRev);
  const key = `${machine}::${nodeId}::${params ? JSON.stringify(params) : ""}::x${excludedRev}`;
  const [entry, setEntry] = useState<Entry>({ key, machine, node: null, error: null });

  useEffect(() => {
    if (!machine) return;
    let alive = true;
    fetchNode(machine, nodeId, params)
      .then((n) => { if (alive) setEntry({ key, machine, node: n, error: null }); })
      .catch((e) => { if (alive) setEntry({ key, machine, node: null, error: String(e) }); });
    return () => { alive = false; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [machine, nodeId, key, retryKey]);

  const fresh = entry.key === key;
  const node = fresh || entry.machine === machine ? entry.node : null;
  return {
    node,                                              // stale only across param changes
    error: fresh ? entry.error : null,
    loading: node === null && !(fresh && entry.error),
    refetching: !fresh && node !== null,               // stale shown, new fetch in flight
  };
}
