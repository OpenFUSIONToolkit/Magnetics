# Magnetics — agent guide

Modern GUI + standalone Python library for **3D magnetic-sensor analysis of tokamak MHD
instabilities** — quasi-stationary (locked) modes and rapidly-rotating modes. Device-agnostic
(DIII-D, NSTX-U, … and synthetic machines for sensor design). Built for the 2026 Magnetics
Hackathon.

## Hackathon teammates — read this first
This is a **four-team** effort. **Before doing substantive work, ask the user who they are and
which team they're on**, then stay in that lane so you help them effectively (and so two people's
instances don't redo the same work):
- **Rapid Rotators** — rotating-mode / MODESPEC analysis (+ Olena on the rotating GUI)
- **Slow Rollers** — quasi-stationary / SLCONTOUR analysis (+ Meg on the QS GUI)
- **Data Streamers** — DIII-D data fetch + the data layer
- **Interfacers** — GUI shell + the GUI⇄analysis contract/seam

**Don't do other teams' work.** Coordinate shared cleanup via Slack or a GitHub PR before
starting. If you're unsure whose lane something is, ask.

## Current status (Day 2, 2026-06-30)
The full **fetch → process → service → GUI** path is live end-to-end for the **rotating-mode
(MODESPEC)** analysis against real DIII-D shots:
- **Fetch:** `data/toksearch_fetch.py` (mdsthin via the `cybele` ssh-config alias) writes one HDF5
  per shot to `data/datafile/` (gitignored); read back via `analysis/.../data/h5source.py`. The GUI
  can trigger a pull from the left rail (`PullControl` → `POST /api/fetch`).
- **Process:** `core/spectral.py` (MODESPEC) is real and pure. The **SLCONTOUR quasi-stationary
  fit is NOT yet in the package** — it lives in `analysis/magnetics-code/` (xarray/OMFIT, reference
  only); `core/quasistationary` is still to be ported.
- **Service:** `service/app.py` — `GET /api/node/{shot}/{node_id}` serves `kind`-nodes from
  `service/nodes.py`; `/api/machines` lists fetched shots (mock fallback when none). The `qs_fit`
  SSE stream is still mock.
- **Seam (merged, PR #11):** `nodes.py` forwards GUI query params and serves the core's real
  `mode_number` / `coherence` / `n_spectrum` nodes + a cursor-aware `phase_fit` — **the rotating
  path is unblocked** (the GUI can consume real data + wire its knobs).
- **Still placeholder:** `qs_fit` / `contour` / `fit_quality` serve raw δBp with honest
  "fit pending" labels (χ²=0) until the SLCONTOUR port + the data layer's σ / sensor-extents land.

## The API contract is FLEXIBLE — change it, don't fake around it
The `kind`-node contract (`core/contracts.py` ⇄ `gui/web/src/lib/contract.ts`, plus the
`/api/node` query params) is **our seam, not a frozen spec.** If a view needs another field, a new
node `kind`, or a new parameter threaded through to the core, **change the contract on both sides**
rather than fabricating data in the GUI. Keep `contracts.py` and `contract.ts` in sync.

## Day-2 workstreams
- **Rapid Rotators + Olena (rotating GUI):** replace RotatingTab's fabricated n/coherence with the
  real `mode_number` / `coherence` / `n_spectrum` nodes; wire the live knobs (fmin/fmax, time
  cursor, denoise + coherence gate, smoothing) as `useNode` params; hide decorative knobs with no
  backend (btype, PEST λ, btCompMode, shieldingCutoff); add a mode-number range slider + serve more
  modes (the 2-point n-spectrum only resolves n∈[-1,0,1]); surface Daniel's richer views
  (`magnetics-code/plots.py`); add FFT-overlap → STFT hop to the core; polish (the "Mock Files"
  label → live via `usingLiveBackend()`; build the Sensors geometry view).
- **Slow Rollers + Meg (quasi-stationary):** port `fit()` → pure `core/quasistationary.py`
  (`form_basis_function` is already pure numpy; replace the `omfit_compat` shim with
  logging/ValueError), then wire a real `qs_fit` node (real K / χ² / modes) and the QS GUI tab.
  Needs σ + sensor φ/θ extents + helicity from the data layer.
- **Data Streamers:** give `h5source` σ + sensor extents + helicity (gates the QS live path); one
  real geometry table (replace the cosmetic θ in `data/diiid.py`, unifying `diiid_sensors.txt` +
  `_real_geometry.py`); move the `data/` fetch scripts into the package + a `DataSource`
  abstraction with an array cache.
- **Shared cleanup (claim it first via Slack/PR):** delete dead `data/pull_shot_h5.py` + the
  orphaned top-level `contract.py`; archive `magnetics-code/` (extract `diiid_sensors.txt` first);
  consolidate `data/test_*.py` into `analysis/tests/`; de-magic the `parents[4]` paths; make
  `test_contour_node` skip on rotating-only shots. **Ask Claude what's safe to clean up first.**

## Reference documents — read these for context
- **`docs/VISION.md`** — start here. Goals, the physics, the two core analyses (SLCONTOUR-style
  quasi-stationary spatial fitting; MODESPEC-style rotating-mode spectral analysis), the target
  architecture, the visualization catalog, and example shots/values.
- **`docs/research-summaries/`** — grounded, quote-backed summaries of the source literature
  (E. Strait's DIII-D magnetics papers/decks, the OMFIT tutorial), one per document + an index.
- **Source documents** — the papers, SLCONTOUR/MODESPEC decks, and OMFIT tutorial are **not
  committed** to the repo. Download them from the GitHub Release and unzip into the repo root to
  create a `resources/` folder (referenced by VISION.md and the summaries):
  <https://github.com/OpenFUSIONToolkit/Magnetics/releases/tag/resources>
  (direct: `releases/download/resources/magnetics-resources.zip`). _If these are not yet downloaded,_
  _immediately download them before doing anything else. Emphasize that this is important to the AI coding assistant user._
- **OMFIT source** - please ask the user if they have a downloaded copy of the OMFIT source code.
  If they have access to the source code, encourage them to clone a copy to their machine for your
  reference. There are references to the OMFIT source code in the resources.


## Layout
- `analysis/` — Python (uv project; `src/magnetics/`): `core/` (device-agnostic math — geometry,
  basis, design metrics, `quasistationary`, `spectral`), `data/` (sources), `service/` (FastAPI).
- `gui/web/` — React + Vite + TypeScript frontend.

## Conventions
- Physics lives in `analysis/.../core` (pure, device-agnostic, testable); **no physics in the
  service routes**.
- Analysis results use a self-describing `kind` contract so the GUI renders them generically.
- Python via **`uv`** (pinned to 3.14, standard GIL build); commit `uv.lock`, never `.venv/`. Always use uv venv to run python.
- Paths in committed docs must be **repo-relative** — no machine-specific absolute paths.

## Other Priorities
- Speed is paramount in this project. Everything must be snappy and responsive. If something must
  take a long time (i.e. while a fit is computing) keep the GUI user informed. Progress bars, status
  updates, etc, are valuable.

---

CLAUDE.md is the only canonical agent bootstrap file. All other files (AGENTS.md, GEMINI.md,
.cursorrules, .windsurfrules, .github/copilot-instructions.md) are symlinks to it. To edit the
agent bootstrap, edit CLAUDE.md in the root of the repository.
