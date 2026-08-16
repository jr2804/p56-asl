"""p56_asl package."""

from __future__ import annotations

import importlib.metadata

try:
    __version__ = importlib.metadata.version(__name__)
except importlib.metadata.PackageNotFoundError:
    __version__ = "0.0.0"  # Fallback for development mode

# The Rust core is compiled into `p56_asl._native` by maturin. Import it
# lazily so that pure-Python use (e.g. the CLI help) works without a build.
try:
    from p56_asl._native import ActiveSpeechLevelMeter, Measurement, PreFilter, Resampler
except ImportError:  # pragma: no cover - native extension not built yet
    ActiveSpeechLevelMeter = None  # type: ignore[assignment,misc]
    Measurement = None  # type: ignore[assignment,misc]
    PreFilter = None  # type: ignore[assignment,misc]
    Resampler = None  # type: ignore[assignment,misc]

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
