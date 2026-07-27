// The device boundary, frontend side. The GUI never knows whether a Node came
// from a mock fixture or a live Python/FastAPI service — it asks for a named node
// on a machine and gets a `kind`-tagged result back.
//
//   VITE_API_BASE=http://127.0.0.1:8000 → explicit live FastAPI service (run-dev.sh live)
//   unset, production build (`vite build`) → same-origin: "" → relative /api/… URLs
//       (the service serves the GUI on one port; this is the packaged/`magnetics` app)
//   unset, dev server (`vite`)            → static MOCK JSON in public/mock/ (run-dev.sh static)
//
// IMPORTANT: the files in public/mock/ are TEST FIXTURES ONLY — fake data so we
// can build and test the GUI before the Python module + data connectors exist.
// In production the Python module is the sole source of data; nothing is read
// from disk. The mock path is purely a stand-in until those connectors are wired.
import type { Node } from "./contract";

// An explicit VITE_API_BASE wins (trailing slashes trimmed so we never build
// `//api/…`). Otherwise a production build defaults to same-origin ("" → relative
// URLs), while the dev server stays in mock mode (undefined). Note "" is a valid
// LIVE base, so every live-vs-mock check below tests `LIVE`, never truthiness.
const explicit = import.meta.env.VITE_API_BASE as string | undefined;
const API_BASE: string | undefined =
  explicit !== undefined ? explicit.replace(/\/+$/, "") : import.meta.env.PROD ? "" : undefined;
const LIVE = API_BASE !== undefined;

export interface MachineInfo {
  id: string; // shot number or synthetic id, as a string
  label: string;
  device: string; // "DIII-D" | "NSTX-U" | "synthetic"
  note?: string;
  synthetic?: boolean;
  /** Backend-supplied: true when this entry is mock/demo data (no real shot file,
   *  nothing on disk, not deletable). A live backend with zero fetched shots still
   *  serves mock machines, so the GUI keys its "live vs demo" badge off this, not
   *  merely off having a backend URL. */
  mock?: boolean;
}

/** List available machines/shots. */
export async function fetchMachines(): Promise<MachineInfo[]> {
  const url = LIVE ? `${API_BASE}/api/machines` : `${base()}mock/machines.json`;
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
  const url = LIVE
    ? `${API_BASE}/api/node/${machine}/${nodeId}${qs(params)}`
    : `${base()}mock/${machine}/${nodeId}.json`;
  return getJSON<Node>(url);
}

export const usingLiveBackend = (): boolean => LIVE;

/** URL for the per-node HDF5 data export (GET /api/node/.../download), or null
 *  without a live backend (the static mock fixtures have no serializer). The same
 *  `params` the plot was fetched with are forwarded so the file matches the view. */
export function nodeDownloadUrl(
  machine: string,
  nodeId: string,
  params?: Record<string, string | number>,
): string | null {
  if (!LIVE) return null;
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
  if (!LIVE) return null;
  return getJSON<ChannelUsage>(`${API_BASE}/api/channels/${shot}`);
}

/** Channels the operator has marked bad for a shot (#56). Dropped from BOTH
 *  analyses; still drawn (greyed) on the sensor map so you can see what went. */
export async function fetchExclusions(shot: string): Promise<string[]> {
  if (!LIVE) return [];
  const r = await getJSON<{ excluded: string[] }>(`${API_BASE}/api/exclusions/${shot}`);
  return r.excluded ?? [];
}

/** Replace a shot's exclusion set. Returns the stored (sorted) list. */
export async function saveExclusions(shot: string, excluded: string[]): Promise<string[]> {
  if (!LIVE) throw new Error("no live backend (run the packaged app or set VITE_API_BASE)");
  const res = await fetch(`${API_BASE}/api/exclusions/${shot}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ excluded }),
  });
  if (!res.ok) throw new Error(`save failed (${res.status}): ${await res.text()}`);
  return ((await res.json()) as { excluded: string[] }).excluded ?? [];
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
  signals?: string[]; // custom PTDATA pointnames; merged into an existing shot file
  ssh_user?: string; // SSH login for devices that gateway over ssh (e.g. KSTAR)
  ssh_password?: string; // sent to the local backend only; not stored
}

/** A device config (data/device/<id>.json) the backend can fetch from. */
export interface DeviceInfo {
  id: string; // --device value, e.g. "diiid"
  name: string; // display name, e.g. "DIII-D"
  sensor_sets: string[]; // selectable as sensor_set (composites included)
  access?: string; // "mdsplus_tree" (NSTX/KSTAR: mdsthin + sensor_set only) | "ptdata"
  remote_capable?: boolean; // device has a network.cluster block (remote backend)
  default_shot?: number | null; // per-device example shot (prefilled on select)
  needs_ssh_creds?: boolean; // true → prompt for SSH user/password (e.g. KSTAR)
  connect_note?: string | null; // short note/warning shown by the pull form
}

/** List available device configs + their sensor-set names (GET /api/devices).
 * Empty when no live backend or no device files. */
export async function fetchDevices(): Promise<DeviceInfo[]> {
  if (!LIVE) return [];
  try {
    return await getJSON<DeviceInfo[]>(`${API_BASE}/api/devices`);
  } catch {
    return [];
  }
}

/** The live backend's base URL for building request/EventSource URLs: "" means
 *  same-origin (relative URLs), a full URL means an explicit backend, and
 *  undefined means no live backend (mock mode). Prefer `usingLiveBackend()` for
 *  a live-vs-mock check — "" is a valid live base and would fail a truthiness test. */
export function apiBase(): string | undefined {
  return API_BASE;
}

/** Start a live pull in the background; returns a job_id. Stream its progress at
 * `${apiBase()}/api/fetch/{job_id}/stream`. Requires a live backend. */
export async function startFetch(body: FetchBody): Promise<{ job_id: string }> {
  if (!LIVE) throw new Error("no live backend (run the packaged app or set VITE_API_BASE)");
  const res = await fetch(`${API_BASE}/api/fetch`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(`pull failed (${res.status}): ${await res.text()}`);
  return res.json();
}

/** Delete one shot's underlying data files from the backend. Requires a live
 * backend (there is nothing to delete against the static mock). */
export async function deleteMachine(shot: string): Promise<void> {
  if (!LIVE) throw new Error("no live backend (run the packaged app or set VITE_API_BASE)");
  const res = await fetch(`${API_BASE}/api/machines/${shot}`, { method: "DELETE" });
  if (!res.ok) throw new Error(`delete failed (${res.status}): ${await res.text()}`);
}

/** Delete ALL fetched shot data (the "clear all"). Requires a live backend. */
export async function deleteAllMachines(): Promise<void> {
  if (!LIVE) throw new Error("no live backend (run the packaged app or set VITE_API_BASE)");
  const res = await fetch(`${API_BASE}/api/machines`, { method: "DELETE" });
  if (!res.ok) throw new Error(`clear failed (${res.status}): ${await res.text()}`);
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
