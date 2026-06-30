#!/usr/bin/env python3
"""Write a SYNTHETIC DIII-D shot HDF5 into data/datafile/ — no GA account needed.

Builds the real MPID (integrated Bp) 66M toroidal array plus the MPI_BDOT 307/340
MODESPEC pair at their real toroidal angles, injects a clean rotating n-mode, and
writes the file through the REAL streaming writer (``stream_channels_to_h5``).
The backend then serves it through the real ``nodes.py`` / ``spectral.py``
pipeline exactly like a fetched shot — only the network pull and real plasma
physics are absent.

    cd analysis && uv run python ../data/make_synthetic_shot.py     # -> shot_999999.h5

Use a clearly-fake shot number (default 999999) so it never shadows a real shot.
"""
from __future__ import annotations

import argparse
import re

import numpy as np

import magnetics_signals as ms
from toksearch_fetch import DATA_DIR, Channel, stream_channels_to_h5

_BDOT_SPECTROGRAM_PAIR = ("MPI66M307D", "MPI66M340D")


def _phi(name: str) -> float:
    """Toroidal angle (deg) from the trailing digit run, same as data/diiid.py."""
    m = re.search(r"(\d+)\D*$", name)
    return float(int(m.group(1)) % 360) if m else 0.0


def _build_channels(*, n: int, f_khz: float, fs_khz: float, dur_ms: float,
                    seed: int) -> list[Channel]:
    """A coherent rotating mode imprinted on the Bp ring + BDOT spectrogram pair.

    Channel j sees ``cos(2π f t − n·φ_j)``: same frequency, a toroidal phase ramp
    set by the mode number n — so the cross-spectrogram recovers n and the contour
    shows a clean δBp(φ, t) band, just like a real rotating mode (minus the mess).
    """
    rng = np.random.default_rng(seed)
    n_samp = int(round(dur_ms * fs_khz))          # fs_khz kHz = samples per ms
    t_ms = np.arange(n_samp, dtype=np.float64) / fs_khz
    t_s = t_ms * 1e-3
    w = 2.0 * np.pi * f_khz * 1e3
    envelope = 1.0 + 0.3 * np.sin(2.0 * np.pi * 2.0 * t_s)   # slow amplitude wobble

    chans: list[Channel] = []
    # Raw dB/dt probes (MODESPEC spectrogram pair): use the 307/340 pair mirrored
    # by the spectral tests. The current service chooses the min/max toroidal
    # separation in the available BDOT set; a full 20..340 ring has Δφ=320°, which
    # aliases n=2 to 0 in the two-point estimator. The 33° pair keeps the no-account
    # demo honest: the GUI's mode-number node recovers the injected default n=2.
    for name in _BDOT_SPECTROGRAM_PAIR:
        ph = np.deg2rad(n * _phi(name))
        sig = w * 5e-4 * envelope * np.cos(w * t_s - ph + np.pi / 2)
        sig += 0.04 * w * 5e-4 * rng.standard_normal(n_samp)
        chans.append(Channel(name, t_ms.copy(), sig.astype(np.float32), ok=True))
    # Integrated Bp probes (SLCONTOUR contour): the 66M toroidal ring (10 probes).
    for name in ms.GROUPS["MPID"][:10]:
        ph = np.deg2rad(n * _phi(name))
        sig = 5e-4 * envelope * np.cos(w * t_s - ph)
        sig += 0.02 * 5e-4 * rng.standard_normal(n_samp)
        chans.append(Channel(name, t_ms.copy(), sig.astype(np.float32), ok=True))
    return chans


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Write a synthetic DIII-D shot HDF5.")
    ap.add_argument("--shot", type=int, default=999999)
    ap.add_argument("--n", type=int, default=2, help="toroidal mode number")
    ap.add_argument("--f-khz", type=float, default=8.0, help="mode frequency (kHz)")
    ap.add_argument("--fs-khz", type=float, default=250.0, help="sample rate (kHz)")
    ap.add_argument("--dur-ms", type=float, default=200.0, help="record length (ms)")
    ap.add_argument("--seed", type=int, default=0)
    args = ap.parse_args(argv)

    chans = _build_channels(n=args.n, f_khz=args.f_khz, fs_khz=args.fs_khz,
                            dur_ms=args.dur_ms, seed=args.seed)
    order = {c.name: i for i, c in enumerate(chans)}

    def produce(sink):
        for i in range(0, len(chans), 8):      # batches of 8, like the fetch path
            sink.put(chans[i:i + 8])

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    out = DATA_DIR / f"shot_{args.shot}.h5"
    got, missing = stream_channels_to_h5(
        str(out), args.shot, "both", "synthetic", compression="lzf",
        tmin=None, tmax=None, stride=1, order=order, produce=produce, queue_max=4)
    print(f"wrote {len(got)} channels ({len(chans[0].data)} samples each, "
          f"n={args.n}, f={args.f_khz} kHz) -> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
