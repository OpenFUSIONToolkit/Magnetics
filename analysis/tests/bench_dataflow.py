"""Memory + time benchmark harness for the data-layer paths.

Records, per measured block:
  * wall-clock seconds,
  * ``tracemalloc`` peak — the Python-heap high-water mark *for that block*; this
    is the reliable per-operation allocation number,
  * process ``ru_maxrss`` — the whole-process RSS high-water mark (monotone, not a
    per-op delta); reported as context, since C-level buffers (h5py, numpy) live
    outside the tracemalloc domain.

Run directly for a baseline on synthetic data::

    cd analysis && uv run python tests/bench_dataflow.py

The before/after comparison lines for the new lazy-read and chunked-STFT paths are
added by their owning changes; this module owns the measurement contract only.
"""
from __future__ import annotations

import resource
import sys
import tempfile
import time
import tracemalloc
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

import numpy as np

# ru_maxrss units differ by platform: bytes on macOS/BSD, kibibytes on Linux.
_RSS_TO_BYTES = 1 if sys.platform == "darwin" else 1024


@dataclass(frozen=True, slots=True)
class Measurement:
    """One measured block. Sizes in bytes; ``seconds`` wall-clock."""
    label: str
    seconds: float
    py_peak_bytes: int       # tracemalloc peak for this block (per-op, reliable)
    rss_peak_bytes: int      # process ru_maxrss after the block (high-water mark)


def _mib(n: int) -> float:
    return n / (1024 * 1024)


def format_measurement(m: Measurement) -> str:
    return (f"{m.label:<34s} {m.seconds * 1e3:8.1f} ms  "
            f"py_peak {_mib(m.py_peak_bytes):8.2f} MiB  "
            f"rss_hwm {_mib(m.rss_peak_bytes):8.1f} MiB")


@contextmanager
def measure(label: str, sink=None):
    """Measure the wrapped block. Do not nest: ``tracemalloc`` keeps one trace.

    Yields a one-element list that receives the :class:`Measurement` on exit, so a
    caller can assert on it; also passes the measurement to ``sink`` (default: print).
    """
    holder: list[Measurement] = []
    tracemalloc.start()
    t0 = time.perf_counter()
    try:
        yield holder
    finally:
        seconds = time.perf_counter() - t0
        _, py_peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        rss_peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * _RSS_TO_BYTES
        m = Measurement(label, seconds, int(py_peak), int(rss_peak))
        holder.append(m)
        (sink or (lambda x: print(format_measurement(x))))(m)


def _baseline(tmpdir: Path) -> None:
    """Baseline numbers on a synthetic shot: full-array read + one spectrogram."""
    import h5py

    from magnetics.core import spectral

    import synthetic_h5

    # A dense toroidal array at a realistic rate, plus one bigger Ḃ-like channel.
    phis = np.linspace(0, 330, 12)
    channels, t_ms, _ = synthetic_h5.rotating_array(
        phis, n=2, f_khz=8.0, fs_khz=500.0, dur_ms=100.0)
    path = tmpdir / "synthetic_bench.h5"
    synthetic_h5.write_shot(path, channels)
    n_samp = channels[0][1].size
    print(f"# synthetic shot: {len(channels)} ch x {n_samp} samples "
          f"({_mib(len(channels) * n_samp * 4):.1f} MiB float32)")

    with measure("full read: all channels [:]"):
        with h5py.File(path, "r") as h5:
            mats = [np.asarray(h5[name]["data"][:]) for name, _, _ in channels]
        _ = np.array(mats)

    t_s = t_ms * 1e-3
    s1, s2 = channels[0][2], channels[1][2]
    with measure("compute_spectrogram (1 pair)"):
        spectral.compute_spectrogram(t_s, s1, s2, delta_phi=float(phis[1] - phis[0]))


def main() -> int:
    with tempfile.TemporaryDirectory() as d:
        _baseline(Path(d))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
