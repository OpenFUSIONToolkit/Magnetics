"""SLCONTOUR quasi-stationary pipeline — a local translation of the OMFIT
magnetics module (self-contained; no real OMFIT/MDSplus dependency, see
``omfit_compat``). Driven by the service's QS nodes through ``core.qs_bridge``.

Reference code, slated for porting into ``magnetics.core.quasistationary``
(issue #40); excluded from lint/typecheck until that port lands.
"""
