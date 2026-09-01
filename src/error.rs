//! Error type for the P.56 meter.

use rubato::{ResampleError, ResamplerConstructionError};

/// Errors produced while constructing or running the meter.
#[derive(Debug, thiserror::Error)]
pub enum Error {
    /// Bit depth outside the supported range `[MIN_BIT_DEPTH, MAX_BIT_DEPTH]`.
    #[error("bit depth {bit_depth} out of range [{min}, {max}]")]
    InvalidBitDepth { bit_depth: u32, min: u32, max: u32 },
    /// Sampling frequency must be positive.
    #[error("sample rate {sample_rate} must be > 0")]
    InvalidSampleRate { sample_rate: f64 },
    /// Block size must be a positive power of two.
    #[error("block size {block_size} must be a positive power of two")]
    InvalidBlockSize { block_size: usize },
    /// No samples were supplied to `finish()`.
    #[error("no samples processed")]
    NoSamples,
    /// Resampler construction failure.
    #[error("resampler construction error: {0}")]
    ResamplerConstruction(#[from] ResamplerConstructionError),
    /// Resampler processing failure.
    #[error("resampler error: {0}")]
    Resampler(#[from] ResampleError),
    /// Resampler used in the wrong phase.
    #[error("resampler error: {0}")]
    ResamplerState(String),
    /// Unknown pre-filter band name (expected `NB`, `SWB` or `FB`).
    #[error("unknown pre-filter band {0:?} (expected NB, SWB or FB)")]
    InvalidBand(String),
}

/// Result alias for the P.56 meter.
pub type Result<T> = std::result::Result<T, Error>;
