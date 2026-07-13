// Per-device pull-form defaults — the decision PullControl snaps to whenever the
// selected device changes (from its own select OR the left rail's picker).
//
// Extracted as a pure function so it is unit-testable (issue #64): a tree device
// (NSTX/KSTAR) has no cluster and no analysis→signal map, so it pulls via
// mdsthin over a NARROW window (its raw signals are ~15 MHz and seconds long — a
// wide window is gigabytes). An NSTX-style tree device requires a named sensor
// set; a device with its own SSH transport (KSTAR) defaults to its declared
// arrays when none is chosen, so no set is preselected there.
import type { DeviceInfo } from "./api";

export interface DeviceDefaults {
  backend: "remote" | "mdsthin";
  sensorSet: string;
  tmin: string;
  tmax: string;
  shot: string | null; // null = keep whatever shot the user typed
}

export function deviceDefaults(d: DeviceInfo): DeviceDefaults {
  const tree = d.access === "mdsplus_tree";
  return {
    backend: d.remote_capable ? "remote" : "mdsthin",
    sensorSet: tree && !d.needs_ssh_creds ? (d.sensor_sets[0] ?? "") : "",
    tmin: tree ? "250" : "1000",
    tmax: tree ? "350" : "5000",
    shot: d.default_shot != null ? String(d.default_shot) : null,
  };
}
