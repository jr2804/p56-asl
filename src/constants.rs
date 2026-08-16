//! Algorithm constants from ITU-T Rec. P.56.
//!
//! Values mirror the reference C implementation (`ref/sv-p56.c`, v2.3):
//! `T`, `H`, `M`, `MIN_LOG_OFFSET` and the threshold progression base.

/// Smoothing time constant of the envelope detector, in seconds (`T`).
pub const SMOOTHING_TIME_CONSTANT_S: f64 = 0.03;

/// Hangover time, in seconds (`H`).
pub const HANGOVER_TIME_S: f64 = 0.20;

/// Margin between the measured level and the noise floor, in dB (`M`).
pub const MARGIN_DB: f64 = 15.9;

/// Offset added inside `log10` to avoid singularities with all-zero data.
pub const MIN_LOG_OFFSET: f64 = 1.0e-20;

/// Maximum supported bit depth (reference: `SVP56_MAX_NO_BITS`).
pub const MAX_BIT_DEPTH: u32 = 32;

/// Minimum supported bit depth (extended implementation).
pub const MIN_BIT_DEPTH: u32 = 8;

/// Default bit depth of the input signal (extended implementation).
pub const DEFAULT_BIT_DEPTH: u32 = 24;

/// Default 0 dB reference: unit amplitude, i.e. dBov.
pub const REF_DB: f64 = 0.0;

/// Active speech level reported for silence, in dB (reference behaviour).
pub const SILENCE_LEVEL_DB: f64 = -100.0;
