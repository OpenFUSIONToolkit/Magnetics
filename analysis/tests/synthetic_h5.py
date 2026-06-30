"""Synthetic HDF5 shot files in the on-disk layout ``data/toksearch_fetch.py`` writes.

Mirrors ``_write_h5``'s layout exactly so data-layer tests exercise real h5py reads
without a live PTDATA pull:

  * each channel is a group ``/{name}`` holding a float32 ``data`` dataset and a
    ``time`` hard-link into a shared ``/_timebases`` group;
  * identical time vectors are stored once and hard-linked (content-addressed),
    just like the fetcher — so a reader that assumes a private per-channel time
    array is exercised against the real shared-link structure;
  * datasets are chunked + lzf-compressed (the writer's default) so windowed
    reads decompress real chunks.

This module is the single source of truth for "a file in the fetcher's layout"
used by the lazy-read and streaming-writer regression tests.
"""
from __future__ import annotations

import hashlib

import h5py
import numpy as np

# (name, time_ms float64, data) triples, ready for write_shot.
Channel = tuple[str, np.ndarray, np.ndarray]


def write_shot(path, channels: list[Channel], *, shot: int = 164672,
               device: str = "DIII-D", analysis: str = "both",
               backend: str = "synthetic", compression: str | None = "lzf") -> str:
    """Write ``channels`` to an HDF5 file in the fetcher's layout; return ``path``.

    Each channel is ``(name, time_ms, data)``: ``time_ms`` is the sample-time axis
    in milliseconds (stored float64), ``data`` is the signal (stored float32).
    Time vectors equal byte-for-byte share one ``_timebases`` dataset via a hard
    link, reproducing the writer's content-addressed dedup.
    """
    comp = None if compression in (None, "none") else compression
    chunks = True if comp else None
    with h5py.File(path, "w") as h5:
        h5.attrs["shot"] = int(shot)
        h5.attrs["device"] = device
        h5.attrs["source"] = "synthetic"
        h5.attrs["analysis"] = analysis
        h5.attrs["backend"] = backend
        tb_grp = h5.create_group("_timebases")
        tb_cache: dict[tuple, str] = {}
        tb_n = 0
        names: list[str] = []
        for name, time_ms, data in channels:
            t = np.ascontiguousarray(np.asarray(time_ms, dtype=np.float64))
            d = np.asarray(data, dtype=np.float32)
            if d.shape != t.shape:
                raise ValueError(
                    f"{name}: data/time length mismatch ({d.shape} vs {t.shape})")
            key = (t.dtype.str, t.shape, hashlib.sha1(t).digest())
            tb_name = tb_cache.get(key)
            if tb_name is None:
                tb_name = f"tb{tb_n}"
                tb_n += 1
                tb_grp.create_dataset(tb_name, data=t, compression=comp, chunks=chunks)
                tb_grp[tb_name].attrs["time_units"] = "ms"
                tb_cache[key] = tb_name
            g = h5.create_group(name)
            g.create_dataset("data", data=d, compression=comp, chunks=chunks)
            g["time"] = tb_grp[tb_name]  # hard link → shared time base
            g.attrs["time_units"] = "ms"
            names.append(name)
        h5.attrs["channels_fetched"] = np.array(names, dtype="S")
        h5.attrs["channels_missing"] = np.array([], dtype="S")
    return str(path)


def uniform_time_ms(*, n_samples: int, fs_khz: float = 200.0,
                    t0_ms: float = 0.0) -> np.ndarray:
    """Uniform sample-time axis (ms). ``fs_khz`` kHz = samples per ms."""
    return t0_ms + np.arange(n_samples, dtype=np.float64) / fs_khz


def rotating_array(phis_deg, *, names=None, n: int = 2, f_khz: float = 5.0,
                   fs_khz: float = 200.0, dur_ms: float = 50.0, t0_ms: float = 0.0,
                   amp: float = 1.0, noise: float = 0.02, family: str = "MPID",
                   seed: int = 0) -> tuple[list[Channel], np.ndarray, np.ndarray]:
    """A toroidal array sharing ONE uniform clock.

    Channel j carries a rotating mode ``amp·cos(2π f t − n φ_j) + noise`` so the
    contour / phase-fit paths see coherent signal. Pass ``names`` to use real
    pointnames (e.g. ``magnetics_signals.GROUPS['MPID']``) when a test needs device
    parsing; otherwise ``{family}66M{phi:03d}`` names are generated.

    Returns ``(channels, time_ms, phis_deg)``.
    """
    phis = np.asarray(phis_deg, dtype=np.float64)
    if names is not None and len(names) != len(phis):
        raise ValueError(f"names/phis length mismatch ({len(names)} vs {len(phis)})")
    rng = np.random.default_rng(seed)
    n_samples = int(round(dur_ms * fs_khz))
    t_ms = uniform_time_ms(n_samples=n_samples, fs_khz=fs_khz, t0_ms=t0_ms)
    t_s = t_ms * 1e-3
    f_hz = f_khz * 1e3
    channels: list[Channel] = []
    for j, phi in enumerate(phis):
        sig = amp * np.cos(2 * np.pi * f_hz * t_s - np.deg2rad(n * phi))
        sig = sig + noise * rng.standard_normal(n_samples)
        name = names[j] if names is not None else f"{family}66M{int(round(phi)) % 360:03d}"
        channels.append((name, t_ms, sig.astype(np.float32)))
    return channels, t_ms, phis


def nonuniform_channel(name: str, *, n_samples: int = 2000, fs_khz: float = 200.0,
                       t0_ms: float = 0.0, jitter_frac: float = 0.3, f_khz: float = 5.0,
                       seed: int = 1) -> Channel:
    """One channel on a genuinely NON-uniform time axis (a distinct timebase that
    must not be content-merged with the uniform arrays). The sample times keep a
    monotone order but with per-step jitter, so descriptor-style (start, dt, n)
    reconstruction would be lossy — exactly the case dedup/compaction must respect.
    """
    rng = np.random.default_rng(seed)
    dt = 1.0 / fs_khz
    steps = dt * (1.0 + jitter_frac * rng.standard_normal(n_samples))
    steps = np.abs(steps) + 1e-6  # keep strictly increasing
    t_ms = t0_ms + np.cumsum(steps) - steps[0]
    sig = np.sin(2 * np.pi * (f_khz * 1e3) * (t_ms * 1e-3)).astype(np.float32)
    return name, t_ms, sig
