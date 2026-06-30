"""Device-agnostic geometry / resolvability math.

The central SLCONTOUR design metric is the condition number K of the basis design
matrix evaluated at the sensor positions (warn > 10, error > 20). It depends only
on sensor angles + the requested mode set, so it is a real, honest number we can
report before the full spatial fit exists.
"""
from __future__ import annotations

import numpy as np


def fourier_design_matrix(phi_deg, n_max: int) -> np.ndarray:
    """Toroidal Fourier design matrix A for sensors at angles `phi_deg`.

    Columns: [1, cos(nφ), sin(nφ) for n=1..n_max]. Rows: one per sensor.
    """
    phi = np.deg2rad(np.asarray(phi_deg, dtype=float))
    cols = [np.ones_like(phi)]
    for n in range(1, n_max + 1):
        cols.append(np.cos(n * phi))
        cols.append(np.sin(n * phi))
    return np.column_stack(cols)


def condition_number(phi_deg, n_max: int = 3) -> float:
    """Condition number K = max(singular)/min(singular) of the design matrix.

    Returns inf if the array cannot constrain the requested modes (degenerate).
    """
    phi = np.asarray(phi_deg, dtype=float)
    n_cols = 1 + 2 * n_max
    if phi.size < n_cols:
        return float("inf")
    a = fourier_design_matrix(phi, n_max)
    sv = np.linalg.svd(a, compute_uv=False)
    if sv.size == 0 or sv[-1] <= 0:
        return float("inf")
    return float(sv[0] / sv[-1])
