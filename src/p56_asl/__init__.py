"""p56_asl package."""

from __future__ import annotations

import importlib.metadata

try:
    __version__ = importlib.metadata.version(__name__)
except importlib.metadata.PackageNotFoundError:
    __version__ = "0.0.0"  # Fallback for development mode

# The Rust core is compiled into `p56_asl._native` by maturin. Import it
# lazily so that pure-Python use (e.g. the CLI help) works without a build;
# the CLI commands fail with a clear error when the native build is missing.
try:
    from p56_asl._native import ActiveSpeechLevelMeter, Measurement, PreFilter, Resampler
except ImportError:  # pragma: no cover - native extension not built yet
    ActiveSpeechLevelMeter = None  # type: ignore
    Measurement = None  # type: ignore
    PreFilter = None  # type: ignore
    Resampler = None  # type: ignore[invalid-assignment]

from p56_asl.wav import WavInfo, read_wav, write_wav

__all__ = [
    "ActiveSpeechLevelMeter",
    "Measurement",
    "PreFilter",
    "Resampler",
    "WavInfo",
    "__version__",
    "read_wav",
    "write_wav",
]
