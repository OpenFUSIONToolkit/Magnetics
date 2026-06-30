// Synthetic, time-evolving plasma equilibrium — a stand-in for EFIT so the
// Sensors view's flux-surface overlay + time slider can be built and tested
// before the real equilibrium fetch (Data Streamers) lands.
//
// It emits the SAME `EquilibriumNode` shape the backend will serve, so swapping
// in real EFIT is just changing the data source (useNode) — no view changes.
//
// Model: nested D-shaped flux surfaces (a simple Solov'ev-like analytic form),
// with the minor radius ramping up then down over the shot and a mild Shafranov
// shift, so scrubbing the slider visibly evolves the plasma. NOT physical EFIT.
import type { EquilibriumNode } from "./contract";

/** Default mock shot time window (ms). Real EFIT supplies its own bounds. */
export const EQ_TIME_RANGE: [number, number] = [100, 5000];

function linspace(a: number, b: number, n: number): number[] {
  return Array.from({ length: n }, (_, i) => a + ((b - a) * i) / (n - 1));
}

export function mockEquilibrium(
  timeMs: number,
  range: [number, number] = EQ_TIME_RANGE,
): EquilibriumNode {
  const [t0, t1] = range;
  const u = Math.min(1, Math.max(0, (timeMs - t0) / (t1 - t0)));
  const env = Math.sin(Math.PI * u); // 0 → 1 → 0 over the shot (current ramp)

  const R0 = 1.67, a0 = 0.62, kappa = 1.7, delta = 0.33;
  const a = a0 * (0.45 + 0.55 * env); // minor radius grows then shrinks
  const Raxis = R0 + 0.14 * (a / a0); // Shafranov shift outward
  const Zaxis = 0.0;

  // ψ_N on an R-Z grid. Triangularity enters the field so the ψ_N = 1 contour
  // exactly matches the boundary curve below (drt = dr + δ·dz² ⇒ ψ_N = drt² + dz²).
  const nR = 72, nZ = 96;
  const r = linspace(0.9, 2.5, nR);
  const z = linspace(-1.45, 1.45, nZ);
  const psi_n: number[][] = [];
  for (let j = 0; j < nZ; j++) {
    const dz = (z[j] - Zaxis) / (kappa * a);
    const row: number[] = [];
    for (let i = 0; i < nR; i++) {
      const dr = (r[i] - Raxis) / a;
      const drt = dr + delta * dz * dz;
      row.push(drt * drt + dz * dz);
    }
    psi_n.push(row);
  }

  // Boundary = the ψ_N = 1 surface: dr = cos t − δ·sin²t, dz = sin t.
  const nb = 120, br: number[] = [], bz: number[] = [];
  for (let k = 0; k <= nb; k++) {
    const t = (k / nb) * 2 * Math.PI;
    const s = Math.sin(t);
    br.push(Raxis + a * (Math.cos(t) - delta * s * s));
    bz.push(Zaxis + kappa * a * s);
  }

  return {
    kind: "equilibrium",
    r, z, psi_n,
    boundary: { r: br, z: bz },
    axis: { r: Raxis, z: Zaxis },
    levels: [0.2, 0.4, 0.6, 0.8, 1.0],
    time_ms: timeMs,
    axes: { x: "R (m)", y: "Z (m)" },
    meta: { synthetic: true },
  };
}
