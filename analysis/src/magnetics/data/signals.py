#!/usr/bin/env python3
"""
DIII-D magnetics signal catalog and analysis-type downselection.

Single source of truth for the PTDATA pointnames pulled by the OMFIT `magnetics`
module, grouped by sensor type, plus the mapping from *analysis type* to the
subset of signals that analysis actually needs.

The two core analyses need different data (see docs/VISION.md sec 4):

  * quasi-stationary (SLCONTOUR): spatial fit of a locked/slow mode at single
    time slices -> wants the *integrated* poloidal-field probes (MPID) and the
    saddle loops (Br) for internal/external separation. Time-domain Fourier is
    not used, so the time base can be trimmed/decimated to slash data volume.

  * rotating (MODESPEC): spectrogram / FFT of a rotating mode -> wants the *raw*
    dB/dt (bdot) probes at full sample rate. Decimation would corrupt the FFT,
    so it is disabled by default for this analysis.

This module is pure data + tiny helpers: no network, no heavy deps, importable
and unit-testable on its own (including under the repo's Python 3.14).
"""

from __future__ import annotations

# --- Sensor groups (DIII-D 3D set, from the OMFIT magnetics module's ----------
#     diiid_sensors.txt; mirrors data/pull_shot_h5.py) ------------------------

# Integrated poloidal-field probes (Bp) -- the SLCONTOUR spatial-fit workhorse.
MPID = [
    "MPID66M020",
    "MPID66M067",
    "MPID66M097",
    "MPID66M127",
    "MPID66M157",
    "MPID66M200",
    "MPID66M247",
    "MPID66M277",
    "MPID66M307",
    "MPID66M340",
    "MPID67A022",
    "MPID67A037",
    "MPID67A052",
    "MPID67A097",
    "MPID67A157",
    "MPID67A217",
    "MPID67A277",
    "MPID67A337",
    "MPID67B022",
    "MPID67B037",
    "MPID67B052",
    "MPID67B097",
    "MPID67B157",
    "MPID67B217",
    "MPID67B277",
    "MPID67B337",
    "MPID79A072",
    "MPID79A147",
    "MPID79A222",
    "MPID79A272",
    "MPID79B067",
    "MPID79B142",
    "MPID79B217",
    "MPID79B277",
    "MPID1A011",
    "MPID1A049",
    "MPID1A109",
    "MPID1A139",
    "MPID1A199",
    "MPID1A244",
    "MPID1A274",
    "MPID1A341",
    "MPID1B011",
    "MPID1B049",
    "MPID1B109",
    "MPID1B139",
    "MPID1B199",
    "MPID1B244",
    "MPID1B274",
    "MPID1B341",
    "MPID2A199",
    "MPID2B199",
    "MPID3A199",
    "MPID3B199",
    "MPID4A199",
    "MPID4B199",
    "MPID5A199",
    "MPID5B199",
]
# Raw bdot probes (un-integrated dB/dt) -- the MODESPEC spectral workhorse.
MPI_BDOT = [
    "MPI66M020D",
    "MPI66M067D",
    "MPI66M097D",
    "MPI66M127D",
    "MPI66M132D",
    "MPI66M137D",
    "MPI66M157D",
    "MPI66M200D",
    "MPI66M247D",
    "MPI66M277D",
    "MPI66M307D",
    "MPI66M312D",
    "MPI66M322D",
    "MPI66M340D",
]
# Floor/fast Bp probes.
MPIF = [
    "MPIF2A139",
    "MPIF2B139",
    "MPIF3A139",
    "MPIF3B139",
    "MPIF4A139",
    "MPIF4B139",
    "MPIF5A139",
    "MPIF5B139",
]
# Saddle loops measuring radial field (Br) -- ISLD / ISLF / ESLD.
ISLD = [
    "ISLD66M017",
    "ISLD66M042",
    "ISLD66M072",
    "ISLD66M102",
    "ISLD66M132",
    "ISLD66M197",
    "ISLD66M252",
    "ISLD66M312",
    "ISLD67A017",
    "ISLD67A052",
    "ISLD67A072",
    "ISLD67A112",
    "ISLD67A132",
    "ISLD67A197",
    "ISLD67A252",
    "ISLD67A312",
    "ISLD67B017",
    "ISLD67B052",
    "ISLD67B072",
    "ISLD67B112",
    "ISLD67B132",
    "ISLD67B197",
    "ISLD67B252",
    "ISLD67B312",
    "ISLD79A072",
    "ISLD79A147",
    "ISLD79A222",
    "ISLD79A272",
    "ISLD79B067",
    "ISLD79B142",
    "ISLD79B217",
    "ISLD79B277",
    "ISLD1A011",
    "ISLD1A049",
    "ISLD1A109",
    "ISLD1A139",
    "ISLD1A199",
    "ISLD1A244",
    "ISLD1A274",
    "ISLD1A341",
    "ISLD1B011",
    "ISLD1B049",
    "ISLD1B109",
    "ISLD1B139",
    "ISLD1B199",
    "ISLD1B244",
    "ISLD1B274",
    "ISLD1B341",
    "ISLD2A199",
    "ISLD2B199",
    "ISLD3A199",
    "ISLD3B199",
    "ISLD4A199",
    "ISLD4B199",
    "ISLD5A199",
    "ISLD5B199",
]
ISLF = [
    "ISLF2A139",
    "ISLF2B139",
    "ISLF3A139",
    "ISLF3B139",
    "ISLF4A139",
    "ISLF4B139",
    "ISLF5A139",
    "ISLF5B139",
]
ESLD = [
    "ESLD66M019",
    "ESLD66M079",
    "ESLD66M139",
    "ESLD66M199",
    "ESLD66M259",
    "ESLD66M319",
]
# 3D coils: C-coil, internal I-coils (upper/lower), and their PCS/RLC currents.
COILS = [
    "C19",
    "C79",
    "C139",
    "C199",
    "C259",
    "C319",
    "IU30",
    "IU90",
    "IU150",
    "IU210",
    "IU270",
    "IU330",
    "IL30",
    "IL90",
    "IL150",
    "IL210",
    "IL270",
    "IL330",
    "PCC19",
    "PCC79",
    "PCC139",
    "PCC199",
    "PCC259",
    "PCC319",
    "PCIU30",
    "PCIU90",
    "PCIU150",
    "PCIU210",
    "PCIU270",
    "PCIU330",
    "PCIL30",
    "PCIL90",
    "PCIL150",
    "PCIL210",
    "PCIL270",
    "PCIL330",
    "RLC19",
    "RLC79",
    "RLC139",
    "RLC199",
    "RLC259",
    "RLC319",
]
# Plasma params for helicity / context.
AUX = ["ip", "bt"]

# Stable mapping name -> group, so callers (and tests) can introspect the set.
GROUPS: dict[str, list[str]] = {
    "MPID": MPID,
    "MPI_BDOT": MPI_BDOT,
    "MPIF": MPIF,
    "ISLD": ISLD,
    "ISLF": ISLF,
    "ESLD": ESLD,
    "COILS": COILS,
    "AUX": AUX,
}

# --- Analysis-type downselection ---------------------------------------------
# Which sensor groups each analysis pulls. Order is preserved and duplicates are
# removed by `signals_for()`.
ANALYSIS_GROUPS: dict[str, list[str]] = {
    # SLCONTOUR spatial fit: integrated Bp + saddle Br (+ coils as applied-field
    # reference + ip/bt context). No raw bdot.
    "quasi-stationary": ["MPID", "ISLD", "ISLF", "ESLD", "COILS", "AUX"],
    # MODESPEC spectral: raw dB/dt probes at full rate (+ fast Bp + coils + aux).
    # No integrated MPID and no saddle loops.
    "rotating": ["MPI_BDOT", "MPIF", "COILS", "AUX"],
    # Everything (the original full pull).
    "both": list(GROUPS),
}

# Per-analysis data-reduction policy. `decimate_ok` gates whether the fetcher is
# allowed to downsample server-side: safe for spatial slices, unsafe for FFTs.
REDUCTION: dict[str, dict[str, bool]] = {
    "quasi-stationary": {"decimate_ok": True},
    "rotating": {"decimate_ok": False},
    "both": {"decimate_ok": False},
}

ANALYSES = tuple(ANALYSIS_GROUPS)

# --- EFIT tree signals --------------------------------------------------------
# Some quantities are NOT in PTDATA: plasma shape from equilibrium
# reconstruction (e.g. elongation kappa) lives in the EFIT MDSplus tree. These
# are fetched by (tree, node), not ptdata2(), so they are catalogued separately
# from the pointname GROUPS. Each entry maps a friendly HDF5 channel name to a
# list of (tree, node) candidates tried in order -- the first that opens and
# returns data wins. Several EFIT trees exist per shot (efit01/02 post-shot,
# efitrt1 real-time); we prefer the standard automatic efit01.
TREE_SIGNALS: dict[str, list[tuple[str, str]]] = {
    "kappa": [
        ("efit01", r"\kappa"),
        ("efit01", r"\top.results.aeqdsk:kappa"),
        ("efit02", r"\kappa"),
        ("efitrt1", r"\kappa"),
    ],
}

# Which tree signals each analysis pulls. Elongation is shape context useful to
# both analyses (helicity / mode-fit context), so all sets request it.
ANALYSIS_TREE_SIGNALS: dict[str, list[str]] = {
    "quasi-stationary": ["kappa"],
    "rotating": ["kappa"],
    "both": ["kappa"],
}


def signals_for(analysis: str) -> list[str]:
    """Return the de-duplicated, ordered pointname list for an analysis type."""
    try:
        group_names = ANALYSIS_GROUPS[analysis]
    except KeyError:
        raise ValueError(
            f"unknown analysis {analysis!r}; choose from {', '.join(ANALYSES)}"
        ) from None
    seen: set[str] = set()
    out: list[str] = []
    for gname in group_names:
        for pt in GROUPS[gname]:
            if pt not in seen:
                seen.add(pt)
                out.append(pt)
    return out


def tree_signals_for(analysis: str) -> dict[str, list[tuple[str, str]]]:
    """Return {channel_name: [(tree, node), ...]} EFIT-tree signals for an analysis.

    These are fetched from the MDSplus EFIT tree (openTree + node), not via
    ptdata2(); the candidate list is tried in order until one returns data.
    """
    try:
        names = ANALYSIS_TREE_SIGNALS[analysis]
    except KeyError:
        raise ValueError(
            f"unknown analysis {analysis!r}; choose from {', '.join(ANALYSES)}"
        ) from None
    return {name: TREE_SIGNALS[name] for name in names}


def decimate_allowed(analysis: str) -> bool:
    """Whether server-side decimation is permitted for this analysis type."""
    if analysis not in REDUCTION:
        raise ValueError(f"unknown analysis {analysis!r}; choose from {', '.join(ANALYSES)}")
    return REDUCTION[analysis]["decimate_ok"]


if __name__ == "__main__":  # quick human-readable summary
    for name in ANALYSES:
        sigs = signals_for(name)
        trees = tree_signals_for(name)
        print(
            f"{name:16s} {len(sigs):3d} ptdata + {len(trees)} tree signals "
            f"{list(trees) if trees else ''}  (decimate_ok="
            f"{decimate_allowed(name)})"
        )
