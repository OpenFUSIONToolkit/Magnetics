#!/usr/bin/env python3
"""
Print the contents of an HDF5 file (e.g. one written by toksearch_fetch.py).

Usage:
    python data/inspect_h5.py path/to/file.h5
    python data/inspect_h5.py                      # defaults to data/shot_184927.h5
"""

import argparse
from pathlib import Path

import h5py

DEFAULT_H5 = Path(__file__).resolve().parent / "shot_184927.h5"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Print the contents of an HDF5 file.")

    ap.add_argument(
        "path",
        nargs="?",
        default=str(DEFAULT_H5),
        help=f"HDF5 file to inspect (default: {DEFAULT_H5})",
    )
    args = ap.parse_args(argv)
    path = args.path

    if not Path(path).is_file():
        ap.error(f"no such file: {path}")

    with h5py.File(path, "r") as h5:
        print(f"File: {path}\n")

        # top-level (file) attributes
        if h5.attrs:
            print("Attributes:")
            for k, v in h5.attrs.items():
                if hasattr(v, "size") and v.size > 8:
                    print(f"  {k}: <{v.size} items> {v[:8]} ...")
                else:
                    print(f"  {k}: {v}")
            print()

        # walk groups / datasets
        print("Contents:")

        def show(name, obj):
            indent = "  " * (name.count("/") + 1)
            if isinstance(obj, h5py.Dataset):
                print(f"{indent}{name}  shape={obj.shape} dtype={obj.dtype}")
            else:
                print(f"{indent}{name}/")

        h5.visititems(show)

        n_groups = sum(1 for _, o in _walk(h5) if isinstance(o, h5py.Group))
        n_dsets = sum(1 for _, o in _walk(h5) if isinstance(o, h5py.Dataset))
        print(f"\n{n_groups} groups, {n_dsets} datasets")
    return 0


def _walk(h5):
    items = []
    h5.visititems(lambda n, o: items.append((n, o)))
    return items


if __name__ == "__main__":
    raise SystemExit(main())
