# GUI Documentation — Changes and Planning

This document records the current state of the GUI development, setup results, and design planning for the **Rotational (MODESPEC) View** during the 2026 Magnetics Hackathon.

---

## 1. Development Environment Setup

We have set up and verified the local development environment for the React web GUI:
* **Repository & Branch**: Active on the `gui-rotating` branch (the teammate B branch for building the MODESPEC view).
* **Node.js**: Using version `v26.1.0`.
* **CI Gates Verification**:
  * `npm run lint` runs ESLint and passes cleanly with no warnings or errors.
  * `npm run build` compiles Vite + TypeScript successfully to `/dist`.
* **Dev Server**: `npm run dev` runs in the background and successfully serves the React site at `localhost:5173` (`HTTP/1.1 200 OK`).
* **FastAPI Backend Service**: Built and verified a python FastAPI web service at [main.py](file:///home/heliot/Projects/Magnetics/analysis/src/magnetics/service/main.py) which serves the machines list and node queries (`/api/machines`, `/api/node/{machine}/{nodeId}`). Serves locally at `http://127.0.0.1:8000` via uvicorn.
* **Frontend-Backend Connection**: Configured [gui/web/.env.development](file:///home/heliot/Projects/Magnetics/gui/web/.env.development) to declare `VITE_API_BASE=http://127.0.0.1:8000`. Vite automatically routes all `fetchNode` requests to the live python backend, ensuring the plot is fully hooked up to FastAPI.

---

## 2. GUI Strategy Comparison

A comprehensive review of three candidate GUI strategies was completed and saved to [gui_strategies_comparison.md](file:///home/heliot/Projects/Magnetics/gui_strategies_comparison.md):
* **Strategy A (Web-Based React + Plotly.js WebGL)**: The chosen strategy for the MVP. It uses WebGL-accelerated traces to bypass the DOM, ensuring high performance while remaining portable and easy to style.
* **Strategy B (Native PySide6 + pyqtgraph)**: A server-side Python Qt alternative with zero data serialization overhead but higher local installation complexity.
* **Strategy C (Hybrid React + WebGL Canvas + Three.js 3D Torus)**: A future enhancement combining raw Canvas pixels with a 3D animated torus for high visual impact.

---

## 3. Rotational (MODESPEC) View Specifications

### 3.1 Hero Plot Specification
* **Plot Type**: Toroidally-coherent $dB/dt$ power spectrogram of magnetic probe pairs.
* **X-Axis**: Time in milliseconds (ms) matching a typical shot-range window (e.g., 1000–4000 ms), synchronized with the global time cursor.
* **Y-Axis**: Frequency in kilohertz (kHz) spanning 0 to 50 kHz (user-configurable up to the digitizer's Nyquist limit).
* **Color Encoding**: Discrete color palette mapping the toroidal mode number $n$ from $-6$ to $+6$ (representing positive/negative rotation).
* **Gating/Masking**: Coherence ($0.0\text{--}1.0$) or log cross-power ($T^2/\text{s}^2/\text{kHz}$) threshold to dynamically mask/black out incoherent noise cells.

### 3.2 Visualizations Supported
The Rotational view contains the following linked panels:
1. **Toroidal Spectrogram**: The n-colored $dB/dt$ power heatmap.
2. **Single-Time Spectrum**: Line plots of Cross-Power, Coherence, and Toroidal Mode Number vs. Frequency (kHz) for a single time slice.
3. **Mode Structure**: Line/scatter plots of Coherence and Phase (deg) vs. angle ($\phi$ and $\theta$). Toroidal phase slope yields $n$, and poloidal phase slope yields $m$ (using straight-field-line $\theta^*$ coordinates).

---

## 4. Throwaway Plotly Sketch
We verified the feasibility of the WebGL heatmap and discrete colorscales in a standalone mock file at [/tmp/sketch.html](file:///tmp/sketch.html):
* Loads Plotly.js from a public CDN.
* Simulates an $n=2$ tearing mode (with an $n=1$ sideband) slowing down quadratically and locking between 1500–3500 ms.
* Maps a custom discrete colorscale for $n$ from $-6$ to $+6$ on a WebGL heatmap, with low-coherence/empty regions masked out.

---

## 5. Rotational View Implementation on `gui-rotating`

The implementation of the MODESPEC view has been integrated into the project skeleton at:
[gui/web/src/components/tabs/RotatingTab.tsx](file:///home/heliot/Projects/Magnetics/gui/web/src/components/tabs/RotatingTab.tsx)

### 5.1 Key Technical Highlights
* **Shared Time Cursor**: Linked to the global Zustand store (`cursorMs`, `setCursorMs` from `useStore`). Clicking on the spectrogram heatmap updates the global time cursor, which instantly updates the associated toroidal and poloidal phase fits.
* **CDNs Ignored (Safe Dependencies)**: Utilizes the built-in React `<Plot />` wrapper over `plotly.js-dist-min` built by the captain, rather than custom scripts, ensuring perfect project integration.
* **Purity Rules Respected**: Avoids impure runtime calls (e.g., `Math.random`) within component renders, maintaining strict adherence to React 19 rules of purity.
* **Dual Display Spectrogram**: Toggle button allows the user to switch between:
  1. **Mode n Heatmap**: Colors the spectrogram using the discrete `MODE_PALETTE` mapping the toroidal mode number $n \in [-6, 6]$.
  2. **Log Power Heatmap**: Colors the spectrogram using the continuous `POWER_SEQUENTIAL` colormap.
* **Phase fits**:
  * Renders the toroidal phase fit ($\phi$ vs phase, slope = $n$, from `phase_fit` node) using `<NodeView />`.
  * Generates and renders a poloidal phase fit ($\theta$ vs phase, slope = $m$) featuring straight-field-line $\theta^*$ corrections.
* **Coherence Gating & Noise Reduction**: Integrated the "Coherence Gate" slider in the sidebar to dynamically mask/filter out background noise from the spectrogram heatmap in real time. Cells below the threshold are mapped to `null`, allowing the coherent mode branches to stand out with high contrast.
* **Time Cursor Scrubber Slider**: Added an interactive slider control in the sidebar for `t0` time cursor scrubbing, linked with the spectrogram vertical scrubber line.
* **Auto-Initialization**: Auto-initializes the shared time cursor `cursorMs` to the beginning of the spectrogram time window (the first data cell) on load, rather than starting at `0`, ensuring it is aligned with active shot data.
* **Multi-Frequency Mode Propagation**: Enhanced the simulation to generate multiple simultaneous coherent mode frequencies ($n=2$ main, $n=1$ sideband, and $n=3$ high-frequency branch) behaving as an overlapping superposition on the spectrogram, sub-interval spectrum plots, and wave-stripes heatmaps.
* **Frequency-Aware Mode-Number Mapping**: Updated the n-mode mapping algorithm to evaluate cell frequencies relative to active mode trajectories (for both synthetic and static mock cases). This correctly maps and colors the multiple concurrent modes as distinct integers ($n=1$, $n=2$, and $n=3$), ensuring all modes show up correctly on the discrete Z-axis colorscale, rather than mapping them all to a single value.
* **High-Density Grid Resolution**: Doubled the time resolution (down to $10\text{ ms}$) and increased the frequency resolution by $2.5\times$ (down to $0.2\text{ kHz}$) in the synthetic generator, producing very sharp, smooth mode tracks on the heatmaps. Also doubled the spatial and temporal density of the toroidal/poloidal wave-stripes grids (down to $5^\circ$ spatial steps and $0.5\text{ ms}$ temporal steps) to show high-fidelity rotating mode waves.
* **Physical Error Bars**: Added horizontal (`error_x`) and vertical (`error_y`) error bars to scatter points in the toroidal and poloidal phase fits. The position error bars (`error_x`) reflect the physical alignment tolerances ($1.2^\circ$ for poloidal, $1.5^\circ$ for toroidal), while the phase error bars (`error_y`) scale dynamically with both `coherenceThreshold` and the `btCompMode` alignment compensation (shrinking as coherence increases and compensation cleans the signal).

All files are fully type-safe, compile cleanly under TypeScript, and pass ESLint rules successfully.

---

## 6. Comprehensive Rotational Mode (MODESPEC) Layout Plan

Based on the August 2026 Magnetic Hackathon requirements and the layout guidelines established during our design interview, the full Rotational View will follow a split-pane grid with a collapsible side control panel and an automatic fallback data source handler:

```
+-------------------------------------------------------------------------------+
| COLLAPSIBLE SIDEBAR    | PINNED TOP PANEL: spectrogram heatmap (t vs f)       |
|                        | [Toggle: n-mode / log power]                         |
| Shot Picker            | (Shows vertical dashed line at global cursorMs)      |
|                        +------------------------------------------------------+
| fmin, fmax sliders     | TABBED BOTTOM PANEL:                                 |
|                        |                                                      |
| fittype:               | [ Tab 1: Sub-Interval ] [ Tab 2: Array ] [ Tab 3: ]  |
| - 0: circular          |   - Raw dB/dt time trace (4ms window)                |
| - 1: toroidicity       |   - Coherence vs frequency (0 to 1.0)                |
| - 2: PEST theta*       |   - Toroidal n vs frequency                          |
|                        |   - Log cross-power vs frequency (log scale)         |
| Data Source Indicator  |                                                      |
+-------------------------------------------------------------------------------+
```

### 6.1 Panel Details

#### 1. Collapsible Sidebar Panel
* **Shot & Range Parameters**: Controls shot number, $t_{min}$, $t_{max}$, $f_{min}$, and $f_{max}$.
* **Fit Mode Options (`fittype`)**:
  * `0`: Circular (straight $\theta$)
  * `1`: Toroidicity modulation ($\theta - \lambda_1 \sin \theta$)
  * `2`: PEST straight-field-line ($\theta - \lambda_1 \sin \theta - \lambda_2 \sin 2\theta$)
* **Smoothing & Thresholds**: FFT smoothing points slider and coherence threshold masking slider.
* **Advanced Parameters (Collapsible section)**:
  * **FFT Window Size & Overlap**: Dropdown (`256` to `2048`) and slider (`0-90%`). Generates dynamic time/frequency resolution spacing based on the Fourier uncertainty principle ($\Delta t \cdot \Delta f \approx \text{const}$).
  * **Custom Probes ($\phi_1, \phi_2$)**: Integrates specific toroidal angles dynamically as active markers on the toroidal phase fit diagram.
  * **PEST Shaping Coefficients ($\lambda_1$, $\lambda_2$)**: Warps both the poloidal phase fit line and poloidal wave stripes contours in real time.
  * **$B_t$ Alignment Compensation**: Simulates $B_t$ leakage phase scatter ($22^\circ$ for `None`, $4^\circ$ for `Analog`, and $1^\circ$ for `Digital`), giving visual feedback of compensation performance.
  * **Armor Shielding Cutoff ($f_{\text{3dB}}$)**: Simulates graphite tile shielding by applying first-order low-pass filtering to the power matrix, fading out high-frequency modes in real time.
* **Data Source Indicator**: A badge reflecting the active data source:
  * **Mock files (static)**: Loaded from `public/mock/{shot}/` when files are present.
  * **Synthetic generator (dynamic)**: Local mock data generator falls back automatically if no static files exist, allowing fully interactive parameter sweeps.

#### 2. Pinned Top Panel: Spectrogram
* **Heatmap rendering**: x-axis = Time (ms), y-axis = Frequency (kHz).
* **Color representation**:
  * Toggles between mode numbers ($n \in [-6, 6]$) using the discrete `MODE_PALETTE` or log power using the continuous `POWER_SEQUENTIAL` colormap.
* **Linked Scrubber**: A dashed vertical line marks `cursorMs`. Clicking or dragging on the spectrogram updates `cursorMs` in the global Zustand store.

#### 3. Tabbed Bottom Panel: Sub-Interval & Mode Fits
* **Tab 1: Sub-Interval Spectrum**:
  * Stacked subplots sharing the frequency axis:
    * Raw signal segment: White trace on black for $dB/dt$ in a 4ms window around the cursor.
    * Coherence: Emerald curve vs frequency.
    * Toroidal n: Scatter markers indicating the dominant mode number at coherent peaks.
    * Log Cross-Power: Violet log curve vs frequency.
* **Tab 2: Array Data (Rotating Wave Stripes)**:
  * Stacked 2D contour maps representing raw signal profiles over time:
    * Toroidal array: Toroidal angle $\phi$ ($0\text{--}360^\circ$) vs. Time (ms).
    * Poloidal array: Poloidal angle $\theta$ ($-100\text{--}300^\circ$) vs. Time (ms).
    * Diagonal stripes visually trace the rotation speed and helicity of the modes.
* **Tab 3: Mode Structure Fits**:
  * Double-column display matching the toroidal and poloidal arrays at the selected cursor time and frequency:
    * Left (Toroidal): Coherence vs. $\phi$, and Phase vs. $\phi$ with fit line $\Phi = n\phi$.
    * Right (Poloidal): Coherence vs. $\theta$, and Phase vs. $\theta$ with PEST fit line $\Phi = m\theta^*$ overlaid.

---

## 7. Spectrogram Bug Fixes (June 2026)

During code review of `RotatingTab.tsx`, four rendering bugs were diagnosed and fixed. Three were confirmed as active; the remaining four were determined to be non-issues after code inspection.

### 7.1 Fixed Bugs

#### Bug 1 (Critical): Discrete colorscale interpolates between palette entries

- **Root cause**: `MODE_PALETTE.map((c, i) => [i / 12, c])` created 13 single stops at evenly spaced positions (0, 1/12, 2/12, …, 1). Plotly linearly interpolated between stops, so ~80% of the colorbar displayed blended colors instead of pure palette entries. A cell with n=2 received a mix of colors[7] and colors[8] instead of a solid `#d53e4f`.
- **Fix**: Replaced with a **dual-stop-per-bin** construction. For each of the 13 palette colors, two identical stops are emitted at the bin boundaries:
  ```typescript
  for (let i = 0; i < n; i++) {
    s.push([i / n, MODE_PALETTE[i]], [(i + 1) / n, MODE_PALETTE[i]]);
  }
  ```
  This gives 26 stops. Plotly never interpolates between identical colors, so each integer n-value maps to a pure, unblended palette color.

#### Bug 2 (Linked): zrange off by 0.5 bin for n-mode

- **Root cause**: `zrange: [-6, 6]` with 13 bins meant bin width = 12/13 ≈ 0.92. A z-value of n=2 mapped to position (2+6)/12 ≈ 0.667, off-center from its intended bin.
- **Fix**: Changed zrange to `[-6.5, 6.5]`. Bin width = 13/13 = 1.0. Value n maps to position (n+6.5)/13, exactly centered in bin index `n + 6`:
  - n = -6 → position 0.5/13 → bin [0/13, 1/13] → color[0] ✓
  - n = 0 → position 6.5/13 → bin [6/13, 7/13] → color[6] ✓
  - n = 6 → position 12.5/13 → bin [12/13, 13/13] → color[12] ✓

#### Bug 3 (Appearance): Colorbar shows scientific float labels instead of integers

- **Root cause**: Plotly auto-generates tick values at evenly-spaced positions, producing labels like `-4.62`, `-1.54`, etc. for a heatmap with range [-6.5, 6.5].
- **Fix**: Added explicit `tickvals` and `ticktext` arrays on the colorbar when in discrete mode, showing clean integer mode numbers:
  ```typescript
  tickvals: [-6, -4, -2, 0, 2, 4, 6],
  ticktext: ["-6", "-4", "-2", "0", "2", "4", "6"],
  ```

#### Bug 4 (Robustness): Coherence gate uses hardcoded power threshold

- **Root cause**: `powerThreshold = -2.7 + coherenceThreshold * 1.5` was calibrated only for synthetic data (log-power range ≈ -3 to 0). For static mock files with different power levels (e.g., shot 164672), the threshold could gate all cells or none.
- **Fix**: Computed the threshold adaptively from the actual data range:
  ```typescript
  const allZ = filteredZ.flat().filter(v => v !== null && !isNaN(v));
  const zMin = allZ.length ? Math.min(...allZ) : -3;
  const zMax = allZ.length ? Math.max(...allZ) : 0;
  const powerThreshold = zMin + coherenceThreshold * (zMax - zMin);
  ```
  This gates the bottom `coherenceThreshold` fraction of the data's actual power range, adapting naturally to any dataset.

### 7.2 Non-Issues (Confirmed Correct)

| Reported Bug | Status | Reason |
|---|---|---|
| zmin/zmax not reset on toggle | ✅ Not a bug | `processedSpecNode` is memoized with `displayMode` in deps; both branches set correct `zrange` |
| heatmapgl NaN rendering | ✅ Not a bug | Code uses `type: "heatmap"` (not `heatmapgl`); Plotly renders `null` as transparent |
| Axis transposition (x/y swapped) | ✅ Not a bug | `zMatrix[fIdx][tIdx]` matches `x=times, y=freqs` — correct Plotly convention |
| FFT parameter mismatch | ✅ Not applicable | Synthetic generator has fixed time/freq resolution; not real FFT parameters |

---

## 8. Sidebar Control Changes (June 2026)

### 8.1 fmin/fmax sliders → number inputs

- **What**: Replaced the two `<input type="range">` slider controls for `f_min` and `f_max` with `<input type="number">` text fields.
- **Why**: Sliders are imprecise for frequency range selection — the user must drag blindly to a specific value. Type-in boxes give direct, keyboard-accessible control with immediate visual feedback of the current value in the input itself (no separate label readout needed).
- **Styling**: Follows the existing `probePhi1`/`probePhi2` number input pattern (`var(--panel-2)` background, `var(--border-2)` border, 11px font, `borderRadius: 4px`).
- **Bounds**: No `min`/`max`/`step` attributes — unbounded, allowing any valid frequency value. Validation defaults to `0` on empty input via `parseInt(e.target.value) || 0`.
- **File**: `RotatingTab.tsx` lines 720–746.

---

## 9. Resizable Layout (June 2026)

Implemented 7 draggable dividers across the MODESPEC view using a lightweight `DraggableDivider` component (`src/lib/DraggableDivider.tsx`). All handlers use `requestAnimationFrame` throttling and functional state updates to avoid layout jank during drag.

| # | Divider | Direction | Adjusts | File location |
|---|---------|-----------|---------|---------------|
| 1 | Sidebar ↔ Dashboard | horizontal | Sidebar width (40–500px) | `RotatingTab.tsx` between sidebar & dashboard containers |
| 2 | Spectrogram ↔ Panels | vertical | Spectrogram height vs Panel 1 height | `RotatingTab.tsx` between spectrogram card & panel 1 |
| 3 | Panel 1 ↔ Panel 2 | vertical | Panel 1 height vs Panel 2 height | `RotatingTab.tsx` between panel 1 & panel 2 |
| 4 | Panel 2 ↔ Panel 3 | vertical | Panel 2 height vs Panel 3 height | `RotatingTab.tsx` between panel 2 & panel 3 |
| 5 | Sub-Interval left / right | horizontal | Raw signal width vs spectrum width (100–800px) | `renderSubInterval()` internal layout |
| 6 | Array toroidal / poloidal | horizontal | Toroidal wave width vs poloidal wave width | `renderArrayContour()` internal layout |
| 7 | Mode toroidal / poloidal | horizontal | Toroidal phase width vs poloidal phase width | `renderModeStructure()` internal layout |

### Implementation details

- **`DraggableDivider.tsx`**: 7px hit target, rAF-throttled mousemove, `stopPropagation` to prevent parent handlers, `document.body` cursor/user-select lock during drag.
- **State**: Each divider adjusts a dedicated `useState` integer (sidebar width in px, panel heights in px, sub-panel split widths in px). Adjacent-panel dividers (e.g. spec vs panel1) use compensating `+d` / `-d` functional updates so total column height stays constant.
- **Sidebar collapse**: When collapsed, the divider hides (`sidebarExpanded` gated). On re-expand, the previous drag-set width restores from state.
- **Performance**: No `useRef` direct DOM manipulation — React state updates with functional updaters avoid stale closures. 7 divider states cause at most 1 re-render per animation frame during drag.

### Files changed
- `gui/web/src/lib/DraggableDivider.tsx` — new file (51 lines)
- `gui/web/src/components/tabs/RotatingTab.tsx` — +8 state variables, +7 drag handlers, modified outer layout, dashboard, and all 3 sub-panel renders
