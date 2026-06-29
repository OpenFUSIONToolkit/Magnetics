# Magnetics — agent guide

Modern GUI + standalone Python library for **3D magnetic-sensor analysis of tokamak MHD
instabilities** — quasi-stationary (locked) modes and rapidly-rotating modes. Device-agnostic
(DIII-D, NSTX-U, … and synthetic machines for sensor design). Built for the 2026 Magnetics
Hackathon.

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
  (direct: `releases/download/resources/magnetics-resources.zip`).


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

---

CLAUDE.md is the only canonical agent bootstrap file. All other files (AGENTS.md, GEMINI.md,
.cursorrules, .windsurfrules, .github/copilot-instructions.md) are symlinks to it. To edit the
agent bootstrap, edit CLAUDE.md in the root of the repository.
