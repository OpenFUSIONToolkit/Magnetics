// Display scaling for raw plasma / coil / sensor time traces. The backend serves
// native units (A, T, T/s, or "" for dimensionless EFIT scalars like κ); this picks
// a readable display unit from the trace's magnitude (Ip 1e6 A → 1 MA, a 3D-coil
// 2e3 A → 2 kA, a 4e-3 T probe → 40 G).

export interface DisplayScale { factor: number; unit: string }

export function displayScale(unit: string | undefined, values: ArrayLike<number>): DisplayScale {
  let peak = 0;
  for (let i = 0; i < values.length; i++) {
    const v = Math.abs(values[i]);
    if (Number.isFinite(v) && v > peak) peak = v;
  }
  if (unit === "A") {
    if (peak >= 1e5) return { factor: 1e-6, unit: "MA" };
    if (peak >= 1e2) return { factor: 1e-3, unit: "kA" };
    return { factor: 1, unit: "A" };
  }
  if (unit === "T" && peak > 0 && peak < 0.1) return { factor: 1e4, unit: "G" };
  return { factor: 1, unit: unit ?? "" };
}

/** Axis title for a scaled trace, e.g. "ip (MA)" or just "kappa". */
export const signalAxisTitle = (name: string, s: DisplayScale) => (s.unit ? `${name} (${s.unit})` : name);
