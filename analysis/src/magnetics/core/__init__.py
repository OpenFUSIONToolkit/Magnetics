"""Device-agnostic analysis core (pure functions, no I/O, no GUI)."""

from magnetics.core.spectral import (
    CrossSpectrumResult,
    ModeAtFrequencyResult,
    SpectrogramResult,
    compute_spectrogram,
    cross_spectrum,
    denoise_spectrogram,
    downsample,
    extract_mode_at_frequency,
    integrate_bdot,
)

__all__ = [
    "CrossSpectrumResult",
    "ModeAtFrequencyResult",
    "SpectrogramResult",
    "compute_spectrogram",
    "cross_spectrum",
    "denoise_spectrogram",
    "downsample",
    "extract_mode_at_frequency",
    "integrate_bdot",
]
