# Spec: Spectral analysis module translation

*Translates OMFIT's `spectrogram_prep.py` + `spectrogram_useful_stuff.py` into a single
device-agnostic module for the new magnetics platform.*

**Source files (OMFIT, Python 2):**
- `modules/magnetics/SCRIPTS/SPECTROGRAM/spectrogram_prep.py`
- `modules/magnetics/LIB/spectrogram_useful_stuff.py`

**Target:** `analysis/src/magnetics/core/spectral.py`

---

## In scope

Five functions translated from OMFIT, covering the full MODESPEC-style rotating-mode
pipeline (plus one new de-noising extension — see "Extensions beyond the translation"):

### 1. `downsample(time, signal, t_range?, sample_rate=2e5) → (time, signal)`

Trim signal to a time range and resample to a target rate via `scipy.signal.resample`.

Source: `downsampling()` in `spectrogram_useful_stuff.py`.

### 2. `integrate_bdot(time, signal, highpass_window?) → signal`

Convert dB/dt → B. High-pass filters to suppress integrator drift (running-average
subtraction if `highpass_window` is given, mean subtraction otherwise), then integrates
via `scipy.integrate.cumulative_trapezoid`.

Source: `integrate()` in `spectrogram_useful_stuff.py`.

### 3. `cross_spectrum(sig1, sig2, sample_rate, delta_phi?) → CrossSpectrumResult`

Core 2-point spectral analysis for a single time window:
- Cross-power spectral density (`scipy.signal.csd`) → power + phase.
- Coherence (`scipy.signal.coherence`).
- If `delta_phi` is provided: toroidal mode number `n = round(phase / Δφ)` at each
  frequency, plus RMS amplitude summed per mode number.

Source: `calculate_fft()` in `spectrogram_useful_stuff.py`.

### 4. `compute_spectrogram(time, sig1, sig2, delta_phi, slice_duration=0.001, window="hann", max_columns=2000, coherence_smooth=5) → SpectrogramResult`

Cross-power spectrogram, coherence, and toroidal mode number vs (time, frequency). Uses a
single **batched short-time FFT per probe** (the private `_stft` helper) rather than a
per-window `cross_spectrum` loop — frames are windowed and rffted in one vectorized call,
and the column count is decimated to `max_columns` so cost scales with the display, not the
record length. The physics (cross-power, frequency-smoothed coherence, `n = round(phase/Δφ)`,
per-mode RMS) matches the 2-point definitions in `cross_spectrum`, including the signed-`n`
convention. Raises `ValueError` if `delta_phi == 0`.

Source: `calculate_spectrogram()` in `spectrogram_prep.py`, re-engined onto a batched STFT.

### 5. `extract_mode_at_frequency(signals, toroidal_angles, time, sample_rate?, frequency=0, t_range?, poloidal_angles?) → ModeAtFrequencyResult`

Multi-probe variant: cross-correlate each probe against the first at a single frequency
to extract phase, amplitude, and coherence vs. toroidal/poloidal angle. Enables the
phase-vs-φ and phase-vs-θ mode-number fits.

Source: `get_mode_2d()` in `spectrogram_useful_stuff.py`.

---

## Extensions beyond the translation

New capability not present in the OMFIT source, added to the same module:

### `denoise_spectrogram(result, coherence_min=0.5, power_floor_k=3.0, floor_percentile=50) → SpectrogramResult`

Suppress low-amplitude / incoherent cells in a computed spectrogram via two complementary
gates: a **coherence gate** (drop cells below `coherence_min` — incoherent cells carry no
real toroidal mode) and a **per-frequency power floor** (drop cells below
`power_floor_k × percentile(power, axis=time)`). Gated cells get power 0 and `rms_by_mode`
is recomputed from what survives.

Note: the per-frequency floor assumes modes are *transient* relative to the window — a
perfectly persistent mode raises its own per-frequency median, so lean on the coherence
gate for steady/locked modes. (Broadband-transient ELM filtering is a possible future
addition, acting per-time-slice rather than per-frequency.)

---

## Out of scope

These stay behind the data-source boundary or in the GUI — not in the spectral module:

- `RZ2psi()` — NSTX-specific equilibrium mapping (future: `data/` source).
- `get_CER_NSTX()`, `get_TS_NSTX()` — NSTX-specific profile fetchers (future: `data/` source).
- `refresh_deltat()` — UI/settings concern (frontend or service layer).
- All OMFIT tree reads/writes (`root['SETTINGS']...`, `OMFITtree()`).
- Data fetching and caching (handled by the service/data layers).
- Full baseline subtraction catalog (14 `btype` algorithms from SLCONTOUR) — belongs in a
  shared signal-conditioning module for the quasi-stationary path. The two-mode
  `integrate_bdot` here is sufficient for the MODESPEC/spectrogram use case where raw
  signals are dB/dt from fast Mirnov probes.

---

## Return types

Typed dataclasses with a `kind` field for the self-describing results contract:

```python
@dataclass
class CrossSpectrumResult:
    kind: str               # "cross_spectrum"
    frequency: ndarray      # Hz
    power: ndarray          # (n_freqs,)
    coherence: ndarray      # (n_freqs,), 0–1
    phase: ndarray          # (n_freqs,), degrees
    mode_number: ndarray | None     # (n_freqs,), integer, present when delta_phi given
    rms_by_mode: ndarray | None     # (n_modes,), present when delta_phi given
    mode_indices: ndarray | None    # (n_modes,), the n values corresponding to rms_by_mode

@dataclass
class SpectrogramResult:
    kind: str               # "spectrogram"
    time: ndarray           # (n_times,), center of each window, seconds
    frequency: ndarray      # (n_freqs,), Hz
    power: ndarray          # (n_times, n_freqs)
    coherence: ndarray      # (n_times, n_freqs)
    mode_number: ndarray    # (n_times, n_freqs), integer
    rms_by_mode: ndarray    # (n_times, n_modes)
    mode_indices: ndarray   # (n_modes,)

@dataclass
class ModeAtFrequencyResult:
    kind: str               # "mode_at_frequency"
    frequency: float        # Hz, the frequency used
    phase: ndarray          # (n_probes,), degrees
    amplitude: ndarray      # (n_probes,)
    coherence: ndarray      # (n_probes,), 0–1
    toroidal_angle: ndarray # (n_probes,), degrees
    poloidal_angle: ndarray | None  # (n_probes,), degrees, if provided
```

---

## Key modernizations from the OMFIT code

| OMFIT (Python 2) | New (Python 3.14) |
|---|---|
| Bare `except:` | `except Exception:` or specific types |
| `== None` | `is None` |
| `/` integer division | `//` where integer division intended |
| `scipy.integrate.cumtrapz` | `scipy.integrate.cumulative_trapezoid` |
| `np.vstack` in a per-window loop | Single batched STFT, fully vectorized (no Python loop) |
| Implicit `np`/`size` from star imports | Explicit `import numpy as np` |
| `print(...)` status messages | No prints; let caller handle logging |
| Returns loose tuples/dicts | Typed dataclasses with `kind` field |
| Settings from OMFIT tree | Function arguments |
| Results stored in OMFIT tree | Return values |
| `str() + str()` concatenation | f-strings where needed |

---

## Dependencies

- **numpy** — in `pyproject.toml`
- **scipy** — in `pyproject.toml` (for `signal.csd`, `signal.coherence`,
  `signal.resample`, `signal.get_window`, `fft.rfft`/`rfftfreq`/`next_fast_len`,
  `integrate.cumulative_trapezoid`, `ndimage.uniform_filter1d`)

---

## Testing notes

- The module is pure functions over arrays — fully testable without any device access.
- Synthetic test signals: two sinusoids with known mode number, frequency, and phase
  difference → verify `cross_spectrum` recovers the correct n.
- Round-trip: `downsample` → `integrate_bdot` → `compute_spectrogram` on a synthetic
  rotating mode should produce a spectrogram peak at the known (t, f, n).
- Edge cases: single-frequency signal, zero coherence (uncorrelated noise), `delta_phi`
  that doesn't evenly divide 360°.
