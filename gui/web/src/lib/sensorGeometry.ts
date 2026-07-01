// Pure geometry helpers for the Sensors view — extracted so the coordinate math
// (which decides where a sensor is drawn) is unit-testable without Plotly.

export const d2r = (deg: number): number => (deg * Math.PI) / 180;

export interface LoopLike {
  r: number;
  z: number;
  tilt: number; // poloidal orientation angle, degrees from +R toward +Z
  length: number; // poloidal extent, m
}

/**
 * The R-Z endpoints of a saddle loop's poloidal extent: a segment of length
 * `length` centred at (r, z), oriented by the loop's own `tilt` (its real angle
 * in the poloidal plane), NOT the vessel tangent. The segment is symmetric, so
 * tilt's sign/wrap doesn't matter.
 */
export function loopSegment2d(s: LoopLike): { x: [number, number]; y: [number, number] } {
  const a = d2r(s.tilt);
  const dr = Math.cos(a);
  const dz = Math.sin(a);
  const h = s.length / 2;
  return { x: [s.r - h * dr, s.r + h * dr], y: [s.z - h * dz, s.z + h * dz] };
}
