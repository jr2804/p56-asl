"""Extended ITU-T Rec. P.56 active speech level measurement.

Rust-core implementation of the P.56 speech voltmeter with blockwise
streaming, P.56 protection pre-filters (NB/SWB/FB), resampling, and an
extended mode that auto-calibrates the amplitude reference for signals
whose peaks exceed full scale.
"""

from __future__ import annotations

import importlib.metadata

try:
    __version__ = importlib.metadata.version(__name__)
except importlib.metadata.PackageNotFoundError:
    __version__ = "0.0.0"  # Fallback for development mode

# The Rust core is compiled into `p56_asl._native` by maturin. A missing
# build is a hard error: importing the package fails loudly.
from p56_asl._native import ActiveSpeechLevelMeter, Measurement, PreFilter, Resampler

__all__ = [
    "ActiveSpeechLevelMeter",
    "Measurement",
    "PreFilter",
    "Resampler",
    "__version__",
]
