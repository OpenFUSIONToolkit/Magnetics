"""Regression tests for the Crucible-confirmed data-layer fixes.

P2  load_wall read the old flat wall schema after the segmented migration → (None,None)
P5  remote_dir flowed unquoted / as an option into cluster shell commands
"""

from __future__ import annotations

import pytest

from magnetics._slcontour.omfit_compat import load_wall
from magnetics.data.fetch import remote


# ── P2: load_wall resolves the segmented wall schema ────────────────────────
def test_load_wall_resolves_segmented_schema():
    """After the wall was migrated to {segments:[...]}, load_wall read the old flat
    keys and returned (None, None), dropping the vessel outline from the sensor map."""
    r, z = load_wall("DIII-D", 184927)
    assert r is not None and z is not None
    assert len(r) == len(z) > 0
    # a None shot (device-level / plotting) takes the latest segment, not (None, None)
    r0, z0 = load_wall("DIII-D")
    assert r0 is not None and len(r0) > 0


# ── P5: remote_dir shell/option-injection boundary ──────────────────────────
@pytest.mark.parametrize("safe", ["~/magnetics_fetch", "/scratch/u/fetch", "rel/dir", "~/a.b-c_d"])
def test_validate_remote_dir_accepts_safe_paths(safe):
    assert remote._validate_remote_dir(safe) == safe


@pytest.mark.parametrize(
    "bad",
    ["~/my fetch", "$(touch x)", "a;b", "a&&b", "`id`", "a|b", "a>b", "-tmp", "--help"],
)
def test_validate_remote_dir_rejects_metacharacters_and_options(bad):
    with pytest.raises(ValueError):
        remote._validate_remote_dir(bad)
