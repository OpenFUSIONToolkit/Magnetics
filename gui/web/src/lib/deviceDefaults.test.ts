// Per-device pull defaults (issue #64) — the decision the rail/pull device
// pickers snap to. Shapes mirror the real /api/devices payloads.
import { describe, expect, it } from "vitest";

import type { DeviceInfo } from "./api";
import { deviceDefaults } from "./deviceDefaults";

const diiid: DeviceInfo = {
  id: "diiid",
  name: "DIII-D",
  sensor_sets: ["Bp LFS midplane", "Bp All"],
  access: "ptdata",
  remote_capable: true,
  default_shot: 184927,
  needs_ssh_creds: false,
};

const nstx: DeviceInfo = {
  id: "nstx",
  name: "NSTX/NSTX-U",
  sensor_sets: ["fastmag toroidal", "fastmag poloidal"],
  access: "mdsplus_tree",
  remote_capable: false,
  default_shot: 204718,
  needs_ssh_creds: false,
};

const kstar: DeviceInfo = {
  id: "kstar",
  name: "KSTAR",
  sensor_sets: ["mirnov_toroidal"],
  access: "mdsplus_tree",
  remote_capable: false,
  default_shot: 42477,
  needs_ssh_creds: true, // own VPN+SSH transport
};

describe("deviceDefaults", () => {
  it("DIII-D: fast cluster backend, wide flat-top window, no set override", () => {
    expect(deviceDefaults(diiid)).toEqual({
      backend: "remote",
      sensorSet: "",
      tmin: "1000",
      tmax: "5000",
      shot: "184927",
    });
  });

  it("NSTX (tree device): mdsthin + narrow window + first sensor set required", () => {
    expect(deviceDefaults(nstx)).toEqual({
      backend: "mdsthin",
      sensorSet: "fastmag toroidal",
      tmin: "250",
      tmax: "350",
      shot: "204718",
    });
  });

  it("KSTAR (own transport): tree window but NO preselected set (its arrays block is the default)", () => {
    const d = deviceDefaults(kstar);
    expect(d.backend).toBe("mdsthin"); // never "remote" — no cluster block
    expect(d.sensorSet).toBe("");
    expect(d.tmin).toBe("250");
  });

  it("keeps the user's shot when the device has no default", () => {
    expect(deviceDefaults({ ...nstx, default_shot: null }).shot).toBeNull();
    expect(deviceDefaults({ ...nstx, default_shot: undefined }).shot).toBeNull();
  });

  it("tree device with no sensor sets degrades to an empty set", () => {
    expect(deviceDefaults({ ...nstx, sensor_sets: [] }).sensorSet).toBe("");
  });
});
