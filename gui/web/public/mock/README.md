# Mock data — TEST FIXTURES ONLY

**These files are fake.** They exist so the GUI can be built and tested **before**
the Python analysis module and the data connectors (Data Streamers team) are wired
up. They are *not* a data source and must never be treated as one.

In production, **the Python module is the sole source of data** — it sends
self-describing `kind`-nodes to the GUI over the API. Nothing is read from disk.

## How the switch works (see `src/lib/api.ts`)

| `VITE_API_BASE` | Source |
|---|---|
| unset (default) | these mock files in `public/mock/` |
| `http://127.0.0.1:8000` | the live Python/FastAPI service (real data) |

The header badge shows which is active: `○ mock data` vs `● live backend`.

## Shape

Each file is one `kind`-node matching `src/lib/contract.ts`
(`contour` / `heatmap` / `scatter2d` / `line` / `metrics`). When the backend is
up it serves the same shapes at `/api/node/{machine}/{nodeId}`, so the GUI swaps
from mock to real with zero view changes.

Regenerate / extend these only as testing aids — never to stand in for real
measurements.
