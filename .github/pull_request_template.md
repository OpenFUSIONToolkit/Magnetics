## Summary
<!-- What does this change do, and why? 1–3 sentences. -->

## Related issue
<!-- e.g. Closes #123 -->

## Type of change
- [ ] Analysis core (`src/magnetics/core`)
- [ ] Data source (`src/magnetics/data`)
- [ ] Service / API (`src/magnetics/service`)
- [ ] Web GUI (`gui/web`)
- [ ] Docs
- [ ] Other:

## How I tested it
<!-- Commands you ran / what you checked. -->

## Checklist
- [ ] CI is green (analysis: `ruff` + `pytest`; web: `lint` + `build`)
- [ ] **No secrets/credentials** (tokens, SSH keys, MDSplus/cluster logins) committed
- [ ] **No large files or tokamak data** committed
- [ ] Physics kept in `core` (device-agnostic); none added to service routes
- [ ] Docs updated if behavior/usage changed
