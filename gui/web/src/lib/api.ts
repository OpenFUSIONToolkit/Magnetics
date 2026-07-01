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

/** URL for the per-node HDF5 data export (GET /api/node/.../download), or null
 *  without a live backend (the static mock fixtures have no serializer). The same
 *  `params` the plot was fetched with are forwarded so the file matches the view. */
export function nodeDownloadUrl(
  machine: string,
  nodeId: string,
  params?: Record<string, string | number>,
): string | null {
  if (!API_BASE) return null;
  return `${API_BASE}/api/node/${machine}/${nodeId}/download${qs(params)}`;
}

/** Per-shot channel diagnostic: which fetched pointnames the analysis uses vs. idle. */
export interface ChannelUsage {
  shot: string;
  n_total: number;
  n_used: number;
  used: { name: string; roles: string[] }[];
  unused: string[];
}

/** Which pointnames each analysis consumes for a shot; null without a live backend
 *  (the static mock has no channel introspection). */
export async function fetchChannelUsage(shot: string): Promise<ChannelUsage | null> {
  if (!API_BASE) return null;
  return getJSON<ChannelUsage>(`${API_BASE}/api/channels/${shot}`);
}

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
  device?: string; // data/device/<device>.json (default: diiid)
  sensor_set?: string; // a set under the device's sensor_sets; overrides analysis
}

/** A device config (data/device/<id>.json) the backend can fetch from. */
export interface DeviceInfo {
  id: string; // --device value, e.g. "diiid"
  name: string; // display name, e.g. "DIII-D"
  sensor_sets: string[]; // selectable as sensor_set (composites included)
  access?: string; // "mdsplus_tree" (NSTX: mdsthin + sensor_set only) | "ptdata"
  remote_capable?: boolean; // device has a network.cluster block (remote backend)
  default_shot?: number | null; // per-device example shot (prefilled on select)
}

/** List available device configs + their sensor-set names (GET /api/devices).
 * Empty when no live backend or no device files. */
export async function fetchDevices(): Promise<DeviceInfo[]> {
  if (!API_BASE) return [];
  try {
    return await getJSON<DeviceInfo[]>(`${API_BASE}/api/devices`);
  } catch {
    return [];
  }
}

/** The live backend's base URL (for building an EventSource), or undefined. */
export function apiBase(): string | undefined {
  return API_BASE;
}

/** Start a live pull in the background; returns a job_id. Stream its progress at
 * `${apiBase()}/api/fetch/{job_id}/stream`. Requires a live backend. */
export async function startFetch(body: FetchBody): Promise<{ job_id: string }> {
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
export function qs(params?: Record<string, string | number>): string {
  if (!params) return "";
  const p = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) p.set(k, String(v));
  const s = p.toString();
  return s ? `?${s}` : "";
}
export async function getJSON<T>(url: string): Promise<T> {
  const res = await fetch(url);
  if (!res.ok) {
    // Surface the service's reason (FastAPI `{detail}`) when present, so callers
    // can distinguish e.g. "shot not fetched" (404) from "no QS array" (422).
    let detail = "";
    try { detail = ((await res.json()) as { detail?: string }).detail ?? ""; } catch { /* non-JSON body */ }
    throw new Error(`fetch failed (${res.status}): ${detail || url}`);
  }
  return res.json() as Promise<T>;
}
