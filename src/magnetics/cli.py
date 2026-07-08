"""One-command launcher for non-developer users.

`magnetics` starts the FastAPI service (which serves the bundled GUI on a single
origin) and opens it in the default web browser. This is the counterpart to the
developer `run.sh` flow, but needs no Node/dev stack — the GUI is shipped inside
the wheel (see ``service.app._webapp_dir``).

Examples:
    magnetics                     # auto-pick a free port, open the browser
    magnetics --port 8000         # fixed port
    magnetics --no-browser        # headless (e.g. on a server / in CI)
"""

from __future__ import annotations

import argparse
import socket
import threading
import time
import webbrowser


def _free_port(host: str, start: int = 8000, tries: int = 100) -> int:
    """First free TCP port at/above ``start`` on ``host`` (matches run.sh)."""
    for port in range(start, start + tries):
        with socket.socket() as s:
            try:
                s.bind((host, port))
                return port
            except OSError:
                continue
    # Everything in the window is busy — let the OS assign any free port.
    with socket.socket() as s:
        s.bind((host, 0))
        return s.getsockname()[1]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        prog="magnetics",
        description="Start the magnetics GUI and open it in your browser.",
    )
    ap.add_argument("--host", default="127.0.0.1", help="bind address (default: 127.0.0.1)")
    ap.add_argument(
        "--port",
        type=int,
        default=None,
        help="port to serve on (default: first free port from 8000)",
    )
    ap.add_argument(
        "--no-browser",
        action="store_true",
        help="do not open a web browser (e.g. headless server)",
    )
    args = ap.parse_args(argv)

    # Deferred so `magnetics --help` stays fast and needs no heavy imports.
    import uvicorn

    from magnetics.service.app import _webapp_dir, app

    if _webapp_dir() is None:
        print(
            "warning: no bundled GUI found — only the /api/* routes will be served. "
            "(This build has no staged frontend; reinstall a release wheel for the GUI.)"
        )

    port = args.port if args.port is not None else _free_port(args.host)
    url = f"http://{args.host}:{port}"
    server = uvicorn.Server(uvicorn.Config(app, host=args.host, port=port))

    if not args.no_browser:

        def _open_when_ready() -> None:
            # Open only once the server has bound, so the first request succeeds.
            while not server.started:
                time.sleep(0.05)
            webbrowser.open(url)

        threading.Thread(target=_open_when_ready, daemon=True).start()

    print(f"  magnetics GUI: {url}   (Ctrl-C to stop)")
    server.run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
