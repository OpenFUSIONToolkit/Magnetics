"""magnetics — device-agnostic 3D magnetic-sensor analysis of tokamak MHD instabilities.

Importable as a plain library (e.g. in a Jupyter notebook): `import magnetics`.
The core analysis pulls only numpy/scipy/matplotlib; the FastAPI service is an
optional extra (`pip install magnetics[service]` / `uv sync --extra service`) so
notebook users never need a web stack. See docs/CONTRACT.md and docs/VISION.md.
"""

__version__ = "0.1.0"
