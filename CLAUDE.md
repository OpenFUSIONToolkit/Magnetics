# Magnetics — agent guide

Modern GUI + standalone Python library for **3D magnetic-sensor analysis of tokamak MHD
instabilities** — quasi-stationary (locked) modes and rapidly-rotating modes. Device-agnostic
(DIII-D, NSTX-U, … and synthetic machines for sensor design).

## Architecture — how it fits together
The full **fetch → process → service → GUI** path runs end-to-end for **both** the
**rotating-mode (MODESPEC)** and the **quasi-stationary (SLCONTOUR)** analyses against real shots:
- **Fetch:** `magnetics.data.fetch.toksearch` (mdsthin via the `cybele` ssh-config alias, or a
  cluster-side `python -m` run orchestrated by `fetch/remote.py`) writes one HDF5 per shot to
  `data/datafile/` (gitignored); read back via `magnetics.data.h5source`. The GUI can trigger a
  pull from the left rail (`PullControl` → `POST /api/fetch`).
- **Process:** `core/spectral.py` (MODESPEC) is real and pure. The SLCONTOUR quasi-stationary fit
  runs end-to-end via the reference pipeline in `magnetics._slcontour/` (xarray, self-contained
  OMFIT shim) adapted by `core/qs_bridge` — real K / χ² / modes for shots pulled with the Bp LFS
  midplane array. A pure `core/quasistationary` port exists but is not yet wired in production (#40).
- **Service:** `service/app.py` — `GET /api/node/{shot}/{node_id}` serves `kind`-nodes from
  `service/nodes.py`; `/api/machines` lists fetched shots (mock fallback when none).
- **Nodes / seam:** `nodes.py` forwards GUI query params and serves the core's real `mode_number` /
  `coherence` / `n_spectrum` nodes + a cursor-aware `phase_fit` for the rotating path, and `qs_fit` /
  `phi_t` / `fit_quality` / `chi_sq_t` / sensor-map / signal nodes for the QS fit. A shot pulled
  rotating-only (no Bp LFS midplane array) returns a clean 422 and the QS tab shows a "no
  quasi-stationary array" banner.
- **Devices:** availability + geometry live in `data/device/*.json`. DIII-D sensor availability and
  positions are shot-indexed (segmented back to shot 124400 legacy dense set / 151593 3D-upgrade);
  the Sensors tab renders wall + vacuum vessel + perturbation coils + saddle loops (2D honoring each
  loop's tilt). Devices whose sensors live in an MDSplus tree (NSTX/NSTX-U, KSTAR; `access:
  "mdsplus_tree"`) fetch via mdsthin + a named sensor set; the node builders resolve the recorded
  `device_id` and classify channels by **sensor-set membership** (not DIII-D pointname families), so
  the rotating/MODESPEC nodes and the Sensors view render those shots too.

Known gaps / open work: per-sensor σ from the data layer (the QS fit currently uses a constant σ;
helicity is computed from Ip·Bt); finishing the pure `core/quasistationary` port and wiring it in
place of the `_slcontour` reference pipeline (#40); real equilibrium plotting in the Sensors tab
(#43); Br saddle-loop geometry corrections (#44).

## The API contract is FLEXIBLE — change it, don't fake around it
The `kind`-node contract (`core/contracts.py` ⇄ `gui/web/src/lib/contract.ts`, plus the
`/api/node` query params) is **our seam, not a frozen spec.** If a view needs another field, a new
node `kind`, or a new parameter threaded through to the core, **change the contract on both sides**
rather than fabricating data in the GUI. Keep `contracts.py` and `contract.ts` in sync.

## Reference documents — read these for context
- **`docs/VISION.md`** — start here. Goals, the physics, the two core analyses (SLCONTOUR-style
  quasi-stationary spatial fitting; MODESPEC-style rotating-mode spectral analysis), the target
  architecture, the visualization catalog, and example shots/values.
- **`docs/research-summaries/`** — grounded, quote-backed summaries of the source literature
  (E. Strait's DIII-D magnetics papers/decks, the OMFIT tutorial), one per document + an index.
- **Source documents** — the papers, SLCONTOUR/MODESPEC decks, and OMFIT tutorial are **not
  committed** to the repo. Download them for full context on the physics and the source algorithms
  from the GitHub Release and unzip into the repo root to create a `resources/` folder (referenced
  by VISION.md and the summaries):
  <https://github.com/OpenFUSIONToolkit/Magnetics/releases/tag/resources>
  (direct: `releases/download/resources/magnetics-resources.zip`).
- **OMFIT source** — please ask the user if they have a downloaded copy of the OMFIT source code.
  If they have access to it, encourage them to clone a copy to their machine for your reference —
  there are references to the OMFIT source code in the resources.

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
- **Verify GUI behavior changes with Playwright.** When a change affects the frontend's *behavior*
  (control state/defaults, data flow, what renders, error handling) — not just styling — drive the
  running app with Playwright and assert the actual DOM/behavior, rather than relying on `tsc` or
  unit tests alone. Start the app (`./run-dev.sh`), then script the interaction (e.g. select a device,
  read back the control values / node responses). This is how the NSTX device-aware `PullControl`
  and the live pull were validated.
- **Run the CI gates locally before committing frontend/typing changes:** `uv run ty check src/magnetics`
  (Python types) and `cd gui/web && npm run lint` (eslint) — `tsc --noEmit` alone does **not** catch
  what CI's `ty` and `eslint` jobs do (e.g. `react-hooks/set-state-in-effect`).

## Git Workflow

This project uses a GitFlow-lite model (http://nvie.com/posts/a-successful-git-branching-model):

- Two long-lived branches: `main` and `develop`.
- `develop` is the integration branch — all branches merge here via pull request.
- `main` is updated only at release-ready stages, via PR from `develop`.

**IMPORTANT:** Do all work on a branch off `develop` and open a PR back into `develop`.
No direct commits to `develop` or `main`. Changes go through a PR so they can be reviewed
before landing.

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
