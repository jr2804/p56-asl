//! Error type for the P.56 meter.

use std::fmt;

/// Errors produced while constructing or running the meter.
#[derive(Debug, Clone, PartialEq)]
pub enum Error {
    /// Bit depth outside the supported range `[MIN_BIT_DEPTH, MAX_BIT_DEPTH]`.
    InvalidBitDepth { bit_depth: u32, min: u32, max: u32 },
    /// Sampling frequency must be positive.
    InvalidSampleRate { sample_rate: f64 },
    /// Block size must be a positive power of two.
    InvalidBlockSize { block_size: usize },
    /// No samples were supplied to `finish()`.
    NoSamples,
    /// Resampler construction or processing failure.
    Resampler(String),
    /// Unknown pre-filter band name (expected `NB`, `SWB` or `FB`).
    InvalidBand(String),
}

impl fmt::Display for Error {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::InvalidBitDepth {
                bit_depth,
                min,
                max,
            } => write!(f, "bit depth {bit_depth} out of range [{min}, {max}]"),
            Self::InvalidSampleRate { sample_rate } => {
                write!(f, "sample rate {sample_rate} must be > 0")
            }
            Self::InvalidBlockSize { block_size } => {
                write!(f, "block size {block_size} must be a positive power of two")
            }
            Self::NoSamples => write!(f, "no samples processed"),
            Self::Resampler(msg) => write!(f, "resampler error: {msg}"),
            Self::InvalidBand(name) => {
                write!(
                    f,
                    "unknown pre-filter band {name:?} (expected NB, SWB or FB)"
                )
            }
        }
    }
}

impl std::error::Error for Error {}

/// Result alias for the P.56 meter.
pub type Result<T> = std::result::Result<T, Error>;
