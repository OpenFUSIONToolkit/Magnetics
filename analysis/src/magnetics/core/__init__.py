"""Device-agnostic analysis core (pure functions, no I/O, no GUI)."""

from magnetics.core.spectral import (
    CrossSpectrumResult,
    ModeAtFrequencyResult,
    SpectrogramResult,
    ToroidalFitResult,
    compute_spectrogram,
    cross_spectrum,
    denoise_spectrogram,
    downsample,
    extract_mode_at_frequency,
    fit_toroidal_mode,
    integrate_bdot,
    stft_layout,
)

__all__ = [
    "CrossSpectrumResult",
    "ModeAtFrequencyResult",
    "SpectrogramResult",
    "ToroidalFitResult",
    "compute_spectrogram",
    "cross_spectrum",
    "denoise_spectrogram",
    "downsample",
    "extract_mode_at_frequency",
    "fit_toroidal_mode",
    "integrate_bdot",
    "stft_layout",
]
