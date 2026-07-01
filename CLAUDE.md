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

## Current status (Day 3, 2026-07-01)
The full **fetch → process → service → GUI** path is live end-to-end for **both** the
**rotating-mode (MODESPEC)** and the **quasi-stationary (SLCONTOUR)** analyses against real
DIII-D shots:
- **Fetch:** `magnetics.data.fetch.toksearch` (mdsthin via the `cybele` ssh-config alias, or a
  cluster-side `python -m` run orchestrated by `fetch/remote.py`) writes one HDF5 per shot to
  `data/datafile/` (gitignored); read back via `magnetics.data.h5source`. The GUI can trigger a
  pull from the left rail (`PullControl` → `POST /api/fetch`).
- **Process:** `core/spectral.py` (MODESPEC) is real and pure. The **SLCONTOUR quasi-stationary
  fit is now live end-to-end** via the reference pipeline in `magnetics._slcontour/` (xarray,
  self-contained OMFIT shim) adapted by `core/qs_bridge` — real K / χ² / modes for shots pulled
  with the Bp LFS midplane array. The pure `core/quasistationary` port exists but is not yet wired
  in production (#40).
- **Service:** `service/app.py` — `GET /api/node/{shot}/{node_id}` serves `kind`-nodes from
  `service/nodes.py`; `/api/machines` lists fetched shots (mock fallback when none). The `qs_fit`
  SSE stream is still mock.
- **Seam (merged, PR #11):** `nodes.py` forwards GUI query params and serves the core's real
  `mode_number` / `coherence` / `n_spectrum` nodes + a cursor-aware `phase_fit` — **the rotating
  path is unblocked** (the GUI can consume real data + wire its knobs).
- **QS live (Day-3 night):** `qs_fit` / `phi_t` / `fit_quality` / `chi_sq_t` / sensor-map / signal
  nodes serve the **real** SLCONTOUR fit. Shots pulled rotating-only (no Bp LFS midplane array)
  return a clean 422 and the QS tab shows a "no quasi-stationary array" banner. Remaining fidelity
  gap: the data layer's per-sensor σ / helicity (fit currently uses a constant σ).
- **Geometry shot-indexed (Day-3 night):** `data/device/diiid.json` sensor availability + positions
  are now segmented back to shot 124400 (legacy dense set) / 151593 (3D-upgrade). The Sensors tab
  renders wall + vacuum vessel + perturbation coils + saddle loops (2D honoring each loop's tilt).
- **NSTX/NSTX-U live (branch `feature/nstxu-data-fetch`):** the fetch is **device-generic** — a
  device with `access:"mdsplus_tree"` (`nstx.json`: `fastmag` tree, `flux.pppl.gov`→`skylark:8501`)
  fetches each sensor node with a server-side value-window subscript + per-shot `gain`/`na`
  (`raw*gain/na`), converting the native seconds time base to ms. `_ssh_tunnel` reuses a live
  `ssh flux` ControlMaster via `-O forward` (no fresh Duo). The h5 records `device_id`; the node
  builders resolve it and classify NSTX channels by **sensor-set membership** (not DIII-D pointname
  families), so the rotating/MODESPEC nodes + the Sensors view render NSTX shots. Validated live on
  **NSTX-U 204718** (All Mirnov). Follow-ups: legacy NSTX (<200000) uses a different per-era tree
  (fetch honors a per-segment `tree`, but `nstx.json` only carries the NSTX-U value); QS/SLCONTOUR
  for NSTX; cluster/toksearch backend for PPPL; GUI PullControl NSTX-sensible default window (raw
  fastmag is ~20 M samples/channel, so a narrow window is required).

## The API contract is FLEXIBLE — change it, don't fake around it
The `kind`-node contract (`core/contracts.py` ⇄ `gui/web/src/lib/contract.ts`, plus the
`/api/node` query params) is **our seam, not a frozen spec.** If a view needs another field, a new
node `kind`, or a new parameter threaded through to the core, **change the contract on both sides**
rather than fabricating data in the GUI. Keep `contracts.py` and `contract.ts` in sync.

## Day-3 workstreams (last day: 2026-07-02)
- **Rapid Rotators + Olena (rotating GUI):** replace RotatingTab's fabricated n/coherence with the
  real `mode_number` / `coherence` / `n_spectrum` nodes; wire the live knobs (fmin/fmax, time
  cursor, denoise + coherence gate, smoothing) as `useNode` params; hide decorative knobs with no
  backend (btype, PEST λ, btCompMode, shieldingCutoff); add a mode-number range slider + serve more
  modes (the 2-point n-spectrum only resolves n∈[-1,0,1]); surface Daniel's richer views
  (`magnetics/_slcontour/plots.py`); add FFT-overlap → STFT hop to the core; polish (the "Mock Files"
  label → live via `usingLiveBackend()`; build the Sensors geometry view).
- **Slow Rollers + Meg (quasi-stationary):** the real `qs_fit` node (K / χ² / modes) + the QS GUI
  tab are **live** (Day-3 night). Remaining: finish the pure `core/quasistationary.py` port and
  wire it in place of the `_slcontour` reference pipeline (#40); consume real per-sensor σ +
  helicity once the data layer provides them (the fit currently uses a constant σ).
- **Data Streamers:** the DIII-D geometry table is now **shot-indexed** (`diiid.json` segmented to
  124400 / 151593; the cosmetic θ in `magnetics/data/diiid.py` — now a thin shim over the
  device-agnostic `data/device_geom.py` — is superseded by the real device table). NSTX/NSTX-U
  fetch + node rendering landed on `feature/nstxu-data-fetch` (see the NSTX status bullet above).
  Remaining: give `h5source` per-sensor σ + helicity (last QS-fidelity gap); a `DataSource`
  abstraction with an array cache; populate the shot-segmented legacy-NSTX tree/wall from the
  `config_hf/hn.mm` files; import other-device geometry the same way.
- **Structural cleanup (LANDED — PR #41, Day-2 night):** the project was hoisted to the repo root
  (`analysis/` removed), the loose `data/` scripts folded into `magnetics.data` (+ `fetch/`),
  `magnetics-code/` relocated to `magnetics._slcontour/`, `data/test_*.py` consolidated into
  `tests/`, every `sys.path`/`parents[4]` hack removed, the GUI build bundled for the wheel, and a
  `ty` typecheck CI gate added (green). `data/pull_shot_h5.py` + the orphaned `contract.py` were
  already gone.
- **Test coverage + QS/geometry fixes (LANDED — `refactor/overnight-cleanup`, Day-3 night):** the
  QS pipeline was fixed (segmented-schema geometry read → all-NaN → SVD failure; + a `float('*')`
  whole-shot-sentinel crash), the DIII-D geometry was shot-indexed, and a full test build-out
  landed: a **synthetic-shot fixture** (`tests/synthetic_shot.py`, generated at test time — **no
  tokamak data is ever committed**) that un-skips the ~30 node-builder tests in CI, FastAPI
  TestClient + QS end-to-end + contract-meta + pure-function tests (Python 212 passing), a React
  error boundary + `NodeView` fallback, and extracted/tested GUI helpers (frontend 24 tests).
  **Still open:** `test_contour_node`'s inner skip on rotating-only shots, trimming the legacy
  `/api/{machine}/{result}` mock routes, the docs sweep for `analysis/`-era references, and real
  equilibrium plotting in the Sensors tab (#43) + Br saddle-loop geometry corrections (#44).

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
The Python project **is the repo root** (a uv project, served as a webapp). `src/magnetics/`:
- `core/` — device-agnostic math (geometry, basis, design metrics, `quasistationary`, `spectral`).
- `data/` — sources + `fetch/` (toksearch/mdsthin pulls, cluster orchestration); device configs
  in `data/device/*.json`.
- `service/` — FastAPI; the built GUI is bundled at `service/webapp/` and served here.
- `_slcontour/` — the reference SLCONTOUR translation (self-contained OMFIT shim), pending port
  into `core/quasistationary` (issue #40); **excluded from lint/typecheck** until then.

Tests in `tests/`, maintainer scripts in `scripts/`. `gui/web/` — React + Vite + TypeScript
frontend (its `dist/` is staged into `service/webapp/` for the wheel).

## Conventions
- Physics lives in `src/magnetics/core` (pure, device-agnostic, testable); **no physics in the
  service routes**.
- Analysis results use a self-describing `kind` contract so the GUI renders them generically.
- Python via **`uv`** (pinned to 3.14, standard GIL build); commit `uv.lock`, never `.venv/`. Always use uv venv to run python.
- Paths in committed docs must be **repo-relative** — no machine-specific absolute paths.
- **Never commit real tokamak data** (DIII-D/NSTX/… measured signals or shot files — `*.h5`
  is gitignored). Tests use **synthetic fixtures generated at test time** (`tests/synthetic_shot.py`,
  wired via `tests/conftest.py`): real channel *names* and the committed device *geometry* are fine,
  but fabricate the *signals*. This keeps the suite deterministic and the repo data-free.

## Git Workflow

This project uses a GitFlow-lite model (http://nvie.com/posts/a-successful-git-branching-model):

- Two long-lived branches: `main` and `develop`.
- `develop` is the integration branch — all branches merge here via pull request.
- `main` is updated only at release-ready stages, via PR from `develop`.

**IMPORTANT:** Do all work on a branch off `develop` and open a PR back into `develop`.
No direct commits to `develop` or `main`. This is a four-team effort — cross-team changes
go through a PR so another team can review before it lands (see "Don't do other teams' work").

### Branch Naming

Branches use a typed prefix and a lowercase hyphen-separated description:

| Prefix | Purpose | Branches from | Merges into |
|---|---|---|---|
| `feature/` | New functionality | `develop` | `develop` |
| `bugfix/` | Non-critical bug fixes | `develop` | `develop` |
| `hotfix/` | Critical production fix | `main` | `main` + `develop` |
| `performance/` | Performance improvements | `develop` | `develop` |
| `refactor/` | Refactoring without behavior change | `develop` | `develop` |
| `docs/` | Documentation only | `develop` | `develop` |
| `test/` | Test additions/improvements | `develop` | `develop` |
| `experiment/` | Exploratory work, may not merge | `develop` | — |

Examples: `feature/array-mode-spectrogram`, `bugfix/stft-hop-offset`,
`refactor/quasistationary-port`, `performance/wire-transfer`.

Author-named branches (e.g. `nlogan/`) are not used — git history already records authorship.
(Some existing branches predate this convention; it applies to new branches going forward.)

### Hotfix Workflow

Hotfixes address critical bugs in `main` that cannot wait for the next release:

1. Branch `hotfix/description` from the current tagged `main` commit.
2. Fix the bug with one or more commits.
3. Merge into `main` via PR; tag the merge commit with a new patch version (e.g. `v0.1.1`).
4. Merge the same branch into `develop` so the fix is not lost.

### Versioning

Semantic versioning: `v{major}.{minor}.{patch}` — major = breaking change,
minor = backward-compatible feature, patch = bug fix. Tags are applied to merge commits on `main`.

### Commit Messages

Keep commits clean and reviewable:

- One logical change per commit; don't bundle unrelated edits.
- Subject line in the imperative mood, ≤72 chars, no trailing period.
- Optional `scope:` prefix naming the touched area, matching existing history
  (e.g. `PullControl: default to the fast remote backend`, `mode_number: cap array STFT columns`).
- Add a body (blank line after the subject) only when the *why* isn't obvious from the diff.
- **Always format Python before committing.** Any time you commit changes that touch Python,
  first run the ruff formatter through uv — `uv run ruff format .` (from the repo root) — and stage
  the result. CI enforces this with `ruff format --check`, so an unformatted commit fails the build.

## Other Priorities
- Speed is paramount in this project. Everything must be snappy and responsive. If something must
  take a long time (i.e. while a fit is computing) keep the GUI user informed. Progress bars, status
  updates, etc, are valuable.

---

CLAUDE.md is the only canonical agent bootstrap file. All other files (AGENTS.md, GEMINI.md,
.cursorrules, .windsurfrules, .github/copilot-instructions.md) are symlinks to it. To edit the
agent bootstrap, edit CLAUDE.md in the root of the repository.
