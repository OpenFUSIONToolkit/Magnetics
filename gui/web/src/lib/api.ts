// The device boundary, frontend side. The GUI never knows whether a Node came
// from a mock fixture or a live Python/FastAPI service — it asks for a named node
// on a machine and gets a `kind`-tagged result back.
//
//   VITE_API_BASE unset  → static MOCK JSON in public/mock/  (default; no backend)
//   VITE_API_BASE=http://127.0.0.1:8000 → live FastAPI service (the real source)
//
// IMPORTANT: the files in public/mock/ are TEST FIXTURES ONLY — fake data so we
// can build and test the GUI before the Python module + data connectors exist.
// In production the Python module is the sole source of data; nothing is read
// from disk. The mock path is purely a stand-in until those connectors are wired.
import type { Node } from "./contract";

const API_BASE = import.meta.env.VITE_API_BASE as string | undefined;

export interface MachineInfo {
  id: string; // shot number or synthetic id, as a string
  label: string;
  device: string; // "DIII-D" | "NSTX-U" | "synthetic"
  note?: string;
  synthetic?: boolean;
}

/** List available machines/shots. */
export async function fetchMachines(): Promise<MachineInfo[]> {
  const url = API_BASE ? `${API_BASE}/api/machines` : `${base()}mock/machines.json`;
  return getJSON<MachineInfo[]>(url);
}

/**
 * Fetch one analysis node by name for a machine.
 * `params` (e.g. a time slice) are sent as query params to the live API and
 * ignored by the static mock (which serves a single representative slice).
 */
export async function fetchNode(
  machine: string,
  nodeId: string,
  params?: Record<string, string | number>,
): Promise<Node> {
  const url = API_BASE
    ? `${API_BASE}/api/node/${machine}/${nodeId}${qs(params)}`
    : `${base()}mock/${machine}/${nodeId}.json`;
  return getJSON<Node>(url);
}

export const usingLiveBackend = (): boolean => !!API_BASE;

/** Parameters for a live shot pull (POST /api/fetch). */
export interface FetchBody {
  shot: number;
  analysis?: string;
  backend?: string;
  username?: string;
  password?: string; // sent to the local backend only; not stored
  duo?: string; // Duo passcode, or "1" for push
  tmin?: number;
  tmax?: number;
  decimate?: number;
}

/** Trigger a live toksearch/mdsthin pull on the backend, then get the refreshed
 * machine list. Requires a live backend (VITE_API_BASE set). */
export async function triggerFetch(
  body: FetchBody,
): Promise<{ ok: boolean; shot: string; machines: MachineInfo[] }> {
  if (!API_BASE) throw new Error("set VITE_API_BASE to pull live data");
  const res = await fetch(`${API_BASE}/api/fetch`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(`pull failed (${res.status}): ${await res.text()}`);
  return res.json();
}

// ── helpers ──
function base(): string {
  return import.meta.env.BASE_URL; // respects vite `base` for sub-path deploys
}
function qs(params?: Record<string, string | number>): string {
  if (!params) return "";
  const p = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) p.set(k, String(v));
  const s = p.toString();
  return s ? `?${s}` : "";
}
async function getJSON<T>(url: string): Promise<T> {
  const res = await fetch(url);
  if (!res.ok) throw new Error(`fetch failed (${res.status}): ${url}`);
  return res.json() as Promise<T>;
}
