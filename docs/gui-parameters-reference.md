# Magnetics GUI Parameters Reference

Complete catalog of every user-tunable parameter in `prep.py`, `fit.py`, and `plots.py`,
organized as GUI panels would be. Derived from the code; intended to drive GUI design.

---

## 1. Shot / Data Loading

| Parameter | Type | Default | Notes |
|-----------|------|---------|-------|
| `shot` | int / path | — | Shot number or path to shot data directory |
| `data_root` | path / null | auto | Override the example-data root directory |

**GUI suggestion:** Shot number input at the top level, always visible. `data_root` is a settings/advanced field.

---

## 2. Channel Selection

Used in both **prep** and **fit**; fit can narrow down further.

| Parameter | Type | Default | Notes |
|-----------|------|---------|-------|
| `channel_filter` | regex / list / name | `".*"` | Friendly names like `"Bp_LFS_midplane"` are resolved from `channel_filters.txt`. Accepts a raw regex or a list of regexes. |
| `fit_exclude` | list of regexes | `()` | Fit-only: channels matching these are excluded even if `channel_filter` includes them. |

**GUI suggestion:** Dropdown of friendly filter names with a "custom regex" escape hatch.
The fit panel can optionally show a channel exclude list.

---

## 3. Time Window

| Parameter | Type | Default | Notes |
|-----------|------|---------|-------|
| `time_trim` | (float, float) seconds | `(2.9, 3.0)` | Analysis window `[t1, t2]`. A padding region is added before `t1` if a high-pass filter is active (automatically computed as `1 / f_low`). |

**GUI suggestion:** Dual-handle range slider over the shot's time axis, with numeric inputs for precision.

---

## 4. Signal Preprocessing

### 4a. Integration

| Parameter | Type | Default | Notes |
|-----------|------|---------|-------|
| `integrate` | bool | `False` | Numerically integrates signals in time: dB/dt (bdot) → B using cumulative trapezoid rule. |

**GUI suggestion:** Toggle switch labeled "Integrate dB/dt → B".

---

### 4b. DC Vacuum Compensation

| Parameter | Type | Default | Notes |
|-----------|------|---------|-------|
| `dc_comp` | bool | `False` | Subtract the DC vacuum field estimated from the COUPLING matrix. Only applied if `shotdata.coupling` contains `"dc_coupling"`. |
| `dc_comp_coils` | list of regexes | `()` | Coil channels (by regex) whose coupling to subtract. Required when `dc_comp` is `True`. |

**GUI suggestion:** Toggle switch; when enabled, reveal a text field for coil name patterns.

---

### 4c. Frequency Filter

Implements a **causal Gaussian** filter (one-sided kernel — no acausal smearing). The filter type is determined by which corner(s) of `cutoff_hz` are set.

| Parameter | Type | Default | Notes |
|-----------|------|---------|-------|
| `cutoff_hz` | (float, float) | `(0.0, 400.0)` | `(f_low, f_high)` bandpass corners in Hz. |

Filter mode logic:

| `f_low` | `f_high` | Mode |
|---------|----------|------|
| `== 0` | `< Nyquist` | **Low-pass** at `f_high` |
| `> 0` | `>= Nyquist` | **High-pass** at `f_low` |
| `> 0` | `< Nyquist` | **Band-pass** between `f_low` and `f_high` |
| `== 0` | `>= Nyquist` | No filtering |

**Automatic downsampling:** If `f_high < Nyquist`, the data is decimated before filtering (step = `floor(Nyquist / f_high)`, capped so ≥ 300 samples remain).

**GUI suggestion:** Two sliders (or numeric inputs) for low and high cutoffs with live readout of the resulting filter mode. Optionally show a frequency-domain preview.

---

### 4d. Detrending

Applied after filtering, before SVD conditioning.

| Parameter | Type | Default | Options |
|-----------|------|---------|---------|
| `detrend_type` | string | `"none"` | `"none"` / `"baseline"` / `"linear"` / `"endpoints"` |
| `detrend_band` | (float, float) or array of pairs | `(0.0, 10.0)` | Sub-interval(s) of the time window used to estimate the trend. Meaning depends on `detrend_type`. |

Detrend type details:

| Mode | What it removes | `detrend_band` role |
|------|----------------|---------------------|
| `none` | Nothing | Ignored |
| `baseline` | Mean value of each channel | Mean is computed over `detrend_band` |
| `linear` | Best-fit line (polyfit degree 1) | Line fitted over `detrend_band` and subtracted from the full window |
| `endpoints` | Line connecting first and last samples | `detrend_band` selects which endpoint samples to use |

**GUI suggestion:** Radio button / segmented control for the four modes. When not `none`, show a secondary range selector for `detrend_band` overlaid on the time-window slider.

---

### 4e. SVD Conditioning

After detrending, the `channel × time` data matrix is decomposed via SVD. Singular values below a cumulative energy threshold are zeroed out, removing incoherent noise. Cosine/sine pairs (n≠0 modes) are kept together.

| Parameter | Type | Default | Notes |
|-----------|------|---------|-------|
| `energy` | float `[0, 1]` | `1.0` | Fraction of cumulative SVD energy to retain. `1.0` = keep all. `< 1.0` removes incoherent noise components. The result is stored as `signal_effective_rank`. |

**GUI suggestion:** Slider from 0.90 to 1.00 (fine-grained), with a readout of the resulting effective rank. Pairs with the `plot_svds` panel.

---

## 5. Fit Options

Least-squares spatial modal fit (SLCONTOUR-style).

| Parameter | Type | Default | Notes |
|-----------|------|---------|-------|
| `ns` | tuple of ints | `(1, 2, 3)` | Toroidal mode numbers included in the basis. |
| `ms` | tuple of ints | `(0,)` | Poloidal mode numbers. Sign is automatically flipped to match the device helicity convention. |
| `fit_basis` | string | `"sinusoidal-integral"` | `"sinusoidal-point"` (evaluate sinusoid at sensor center) or `"sinusoidal-integral"` (average sinusoid over sensor extent — preferred for finite-size sensors). |
| `fit_geometry` | string | `"cylindrical"` | `"cylindrical"` uses `(phi, theta)` coordinates; `"vertical"` uses `(phi, z)`. |
| `fit_cond` | float | `10.0` | Design-matrix condition-number cutoff `= 1/rcond` for `lstsq`. Singular values beyond this ratio are truncated. Also determines the threshold displayed in `plot_svds`. |

**Condition number warnings** (from SLCONTOUR):
- `K > 10`: fit may be poorly resolved — show warning
- `K > 20`: fit is untrustworthy — show error / red indicator

**GUI suggestion:**
- Multi-select chip picker or tag input for `ns` and `ms`.
- Radio buttons for `fit_basis` and `fit_geometry`.
- Numeric input for `fit_cond` with inline K warning display.

---

## 6. Plots

### 6a. `plot_sensors` — Sensor Map

Shows sensor footprints overlaid on the machine geometry.

| Parameter | Type | Default | Options |
|-----------|------|---------|---------|
| `channel_filter` | regex | `".*"` | Which channels to draw |
| `geometry` | string | `"rz"` | `"rz"` (R-Z cross-section with wall outline), `"flat"` (phi vs z), `"cylindrical"` (phi vs theta) |

**Output:** Single panel. Wall outline added automatically for `"rz"`.

---

### 6b. `plot_signal` — Raw vs Prepared Time Traces

Overlays the conditioned (PREPARED) signal on the original RAW signal (raw is shifted to match PREPARED at `t0` so filtering effects are visible).

| Parameter | Type | Default | Notes |
|-----------|------|---------|-------|
| `channel_filter` | regex | `".*"` | Channels to show |
| `legend_maxnum` | int | `12` | Max number of channels shown in the legend; remaining are greyed out |

**Output:** Single panel. Channels with the largest peak-to-peak variation are highlighted in the legend.

---

### 6c. `plot_fit` — Fit Quality Overview

3-panel diagnostic: fit trustworthiness at a glance.

| Panel | Content |
|-------|---------|
| Top | Reduced chi² vs time (log scale, reference line at 1) |
| Middle | Measured signals vs time (all channels) |
| Bottom | Residuals vs time; channels with the largest residual are labeled |

| Parameter | Type | Default | Notes |
|-----------|------|---------|-------|
| `legend_maxnum` | int | `6` | Number of worst-residual channels labeled in the residual panel |

---

### 6d. `plot_fit_modes` — Mode Amplitude & Phase vs Time

The central mode-dynamics view. Shows how each (m/n) mode evolves: a rotating mode has a steadily winding phase; locking shows phase flattening while amplitude grows.

| Parameter | Type | Default | Notes |
|-----------|------|---------|-------|
| `legend_maxnum` | int | `12` | Modes to show in the legend (ordered by peak amplitude) |

| Panel | Content |
|-------|---------|
| Top | Amplitude ± 1σ error band for each mode vs time |
| Bottom | Phase (−180° to +180°) ± 1σ for modes with appreciable amplitude (> 10% of the dominant mode) |

---

### 6e. `plot_slice` — SLCONTOUR Phi-vs-Time Contour

The classic locked-mode picture. Reconstructs the fitted field on a spatial × time grid and shows it as a pcolormesh. Rotating modes appear as diagonal stripes; locking = stripe goes horizontal.

| Parameter | Type | Default | Notes |
|-----------|------|---------|-------|
| `fix_coord` | string | `"theta"` | Spatial coordinate held fixed: `"theta"` (cylindrical) or `"phi"` (poloidal slice or vertical slice) |
| `fix_value` | float | `0.0` | Value at which to fix the coordinate (degrees for theta/phi; meters for z) |
| `ngrid` | int | `120` | Resolution of the swept spatial axis |
| `trace_peak` | bool | `True` | When `True`, adds an RMS amplitude trace panel above the contour and overlays peak-location dots |
| `cmap` | string | `"RdBu_r"` | Colormap for the pcolormesh (passed as `**plot_kwargs`) |

**Layout when `trace_peak=True`:** 4-row grid — top row = RMS amplitude, bottom 3 rows = contour.

---

### 6f. `plot_svds` — SVD Conditioning Diagnostics

Pure diagnostic, no tunable parameters.

| Panel | Content |
|-------|---------|
| Top | Cumulative energy fraction of data-matrix singular values. Energy threshold line from `energy` param. Removed components marked with ×. |
| Bottom | Design-matrix (basis) condition number per singular value. Condition-number cutoff line from `fit_cond`. Truncated components marked with ×. |

---

## 7. Summary Table: Parameter ↔ Pipeline Stage

| Parameter | prep | fit | plot |
|-----------|:----:|:---:|:----:|
| `channel_filter` | ✓ | ✓ | ✓ |
| `time_trim` | ✓ | | |
| `integrate` | ✓ | | |
| `dc_comp` / `dc_comp_coils` | ✓ | | |
| `cutoff_hz` | ✓ | | |
| `detrend_type` / `detrend_band` | ✓ | | |
| `energy` | ✓ | | `plot_svds` |
| `ns` / `ms` | | ✓ | |
| `fit_exclude` | | ✓ | |
| `fit_basis` | | ✓ | |
| `fit_geometry` | | ✓ | `plot_slice` |
| `fit_cond` | | ✓ | `plot_svds` |
| `geometry` (sensor view) | | | `plot_sensors` |
| `fix_coord` / `fix_value` | | | `plot_slice` |
| `ngrid` | | | `plot_slice` |
| `trace_peak` | | | `plot_slice` |
| `legend_maxnum` | | | `plot_signal`, `plot_fit`, `plot_fit_modes` |
