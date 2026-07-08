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
