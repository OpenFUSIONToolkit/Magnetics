# Releasing `magnetics` to PyPI

The [`Release` workflow](../.github/workflows/release.yml) builds the wheel + sdist
(with the GUI bundled), smoke-tests the install in a clean Python 3.12 venv, and
publishes to PyPI on a version tag. Publishing uses **PyPI Trusted Publishing**
(OIDC) — there is no API token to manage.

## One-time setup (before the first release)

1. **Register the pending publisher on PyPI.** Log in to <https://pypi.org> as an
   owner of the project (or as whoever will own it), go to
   **Your projects → (project) → Publishing**, or for a brand-new name use
   **Account → Publishing → Add a pending publisher**, and enter:
   - **PyPI project name:** `magnetics`
   - **Owner:** `OpenFUSIONToolkit`
   - **Repository name:** `Magnetics`
   - **Workflow name:** `release.yml`
   - **Environment name:** `pypi`

   The project name `magnetics` is currently unclaimed; the pending publisher
   reserves it and lets the first tag push create the project.

2. **Create the `pypi` GitHub environment.** In the repo, **Settings →
   Environments → New environment → `pypi`**. Optionally add required reviewers so
   a human must approve each publish. The environment name must match the workflow
   (`environment: pypi`) and the pending publisher above.

> The pending publisher **must exist before the first tag push**, or the publish
> step fails auth. That failure is harmless — finish the setup and re-run the job.

## Cutting a release

Follows the repo's GitFlow-lite (see `CLAUDE.md`). Versioning is SemVer; the tag
must match `version` in `pyproject.toml` (the workflow enforces this).

1. On a branch off `develop`, bump `version` in `pyproject.toml` (and keep
   `src/magnetics/__init__.py:__version__` in step). Open a PR into `develop`.
2. Open a release PR `develop` → `main` and merge it.
3. Tag the merge commit on `main` and push the tag:
   ```bash
   git checkout main && git pull
   git tag vX.Y.Z
   git push origin vX.Y.Z
   ```
4. The `Release` workflow builds, smoke-tests, publishes to PyPI, and creates a
   GitHub Release with the artifacts attached.

## Dry run

Trigger the workflow manually (**Actions → Release → Run workflow**, or
`gh workflow run release.yml`). `workflow_dispatch` runs the **build + smoke test
only** and skips publishing, so you can validate the pipeline (GUI bundling, wheel
install, launcher boot) without cutting a release.

## What "installed" looks like for users

```bash
uvx magnetics                      # zero-install, ephemeral (uv provisions Python)
# or
pip install magnetics && magnetics # into an existing environment
```

Both start the service and open the bundled GUI in a browser. Shot data is written
to a per-user data directory (or `$MAGNETICS_DATA_DIR`); see the README.
