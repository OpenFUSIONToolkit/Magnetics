// Pure reductions over a δBp(φ, t) contour grid `z[φ][t]`, extracted from
// QuasiStationaryTab so the index math is unit-testable (and can't throw and blank
// the app on an empty/ragged grid).

/** φ of the maximum (signed) δBp at each time column → one value per time. `y` is
 *  the φ axis. Signed (not |·|) argmax is intentional: it's the stable phase tracker
 *  for a signed δBp contour. */
export function phiPeak(z: number[][], y: number[]): number[] {
  const nCol = z[0]?.length ?? 0;
  if (!nCol || !y.length) return [];
  const out: number[] = [];
  for (let j = 0; j < nCol; j++) {
    let bestI = 0;
    let bestV = -Infinity;
    for (let i = 0; i < z.length; i++) {
      const v = z[i]?.[j];
      if (v != null && v > bestV) {
        bestV = v;
        bestI = i;
      }
    }
    out.push(y[bestI]);
  }
  return out;
}

/** RMS over φ at each time column → one value per time. */
export function phiRms(z: number[][]): number[] {
  const nRow = z.length;
  const nCol = z[0]?.length ?? 0;
  if (!nRow || !nCol) return [];
  const out: number[] = [];
  for (let j = 0; j < nCol; j++) {
    let sum = 0;
    for (let i = 0; i < nRow; i++) sum += (z[i]?.[j] ?? 0) ** 2;
    out.push(Math.sqrt(sum / nRow));
  }
  return out;
}

/** The quasi-stationary fit's starting settings, as the /api/node query params they
 *  become (time window omitted → the shot's own tmin/tmax). Shared by the QS tab's
 *  initial control values and the Compare view's "QS tab not run yet" fallback. */
export const QS_DEFAULTS = {
  ns: "1,2,3",
  ms: "0",
  channel_filter: "Bp LFS midplane",
  detrend_type: "baseline",
  sigma: "2e-5",
  energy: "0.98",
  fit_basis: "sinusoidal-integral",
  fit_cond: "1000", // OMFIT SLCONTOUR inversion cutoff (1/rcond), not the K>10 trust threshold
  cutoff_lo: "5.0",
  cutoff_hi: "250.0",
} as const satisfies Record<string, string>;
