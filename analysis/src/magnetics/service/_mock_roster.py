"""Mock-machine composition — which real DIII-D probes each synthetic machine
exposes, and the array labels shown in its Sensors view.

POSITIONS ARE NOT STORED HERE. Every sensor's (r, z, φ, θ) resolves through the
canonical, shot-aware device table (``data/device/diiid.json`` via ``data.diiid``)
— the single source of geometry truth. This file carries only mock *composition*:
the sensor-name roster (a real subset, per the seeding shot) and the descriptive
array labels. MOCK-A <- shot 164672 (dense); MOCK-B <- shot 147131 (sparse legacy).
"""
from __future__ import annotations

#: machine -> {"sensors": [pointname, ...], "arrays": [{family,label,kind,count}, ...]}
ROSTER: dict[str, dict] = {
    'MOCK-A': {
        "sensors": [
            'MPI66M020D', 'MPI66M067D', 'MPI66M097D', 'MPI66M127D', 'MPI66M132D', 'MPI66M137D',
            'MPI66M157D', 'MPI66M200D', 'MPI66M247D', 'MPI66M277D', 'MPI66M307D', 'MPI66M312D',
            'MPI66M322D', 'MPI66M340D', 'MPID66M307', 'MPID66M127', 'MPID66M020', 'MPID66M200',
            'MPID66M067', 'MPID67A217', 'MPID67A037', 'MPID67A337', 'MPID67A277', 'MPID67A022',
            'MPID67A097', 'MPID67A052', 'MPID67A157', 'MPID79A272', 'MPID79A147', 'MPID79A222',
            'MPID79A072', 'MPID5A199', 'MPID4A199', 'MPID3A199', 'MPID2A199', 'MPID1A341',
            'MPID1A011', 'MPID1A274', 'MPID1A049', 'MPID1A244', 'MPID1A139', 'MPID1A199',
            'MPID1A109', 'MPID1B049', 'MPID1B011', 'MPID1B109', 'MPID1B341', 'MPID1B199',
            'MPID1B244', 'MPID1B139', 'MPID1B274', 'MPID2B199', 'MPID3B199', 'MPID4B199',
            'MPID5B199', 'MPID79B067', 'MPID79B277', 'MPID79B142', 'MPID79B217', 'MPID67B022',
            'MPID67B277', 'MPID67B052', 'MPID67B157', 'MPID67B337', 'MPID67B097', 'MPID67B037',
            'MPID67B217', 'MPID66M277', 'MPID66M097', 'MPID66M247', 'MPID66M340', 'MPID66M157',
        ],
        "arrays": [
            {'family': 'MPID', 'label': 'Bp pairs · 2D', 'kind': 'Bp', 'count': 58},
            {'family': 'MPI66M', 'label': 'LFS toroidal Mirnov', 'kind': 'Bp', 'count': 14},
        ],
    },
    'MOCK-B': {
        "sensors": [
            'MPI66M067D', 'MPI66M137D', 'MPI66M157D', 'MPI66M307D', 'MPI66M322D', 'MPI66M340D',
            'MPID66M127', 'MPID66M067', 'MPID67A037', 'MPID67A022', 'MPID67A097', 'MPID67A157',
            'MPID67B157', 'MPID67B097', 'MPID66M097', 'MPID66M157',
        ],
        "arrays": [
            {'family': 'MPID', 'label': 'Bp pairs · 2D', 'kind': 'Bp', 'count': 10},
            {'family': 'MPI66M', 'label': 'LFS toroidal Mirnov', 'kind': 'Bp', 'count': 6},
        ],
    },
}
