//! Configuration of the active speech level meter.

use crate::constants::{DEFAULT_BIT_DEPTH, MAX_BIT_DEPTH, MIN_BIT_DEPTH};
use crate::error::{Error, Result};

/// Configuration for [`crate::actlevel::ActiveSpeechLevelMeter`].
///
/// Defaults follow the extended implementation: 24 bit resolution, unit
/// maximum amplitude (dBov convention, `max_amplitude = 1.0`), and
/// blockwise processing with a fixed power-of-two block size.
#[derive(Debug, Clone, Copy, PartialEq)]
pub struct Params {
    /// Sampling frequency of the input signal, in Hz.
    pub sample_rate: f64,
    /// Bit depth of the input signal, `8..=32`.
    pub bit_depth: u32,
    /// Block length in samples; must be a power of two (`2^N`).
    ///
    /// Blocks are the unit of input to [`crate::actlevel::ActiveSpeechLevelMeter::process_block`]
    /// and enable the FFT-domain implementation of the temporal smoothing
    /// filter (see [`crate::filter`]).
    pub block_size: usize,
    /// Maximum amplitude of the input signal, i.e. the 0 dB reference
    /// (default `1.0` → dBov).
    pub max_amplitude: f64,
    /// Extended mode: adapt `max_amplitude` to the observed signal peaks
    /// instead of requiring a fixed scale (see calibration design notes).
    pub auto_calibrate: bool,
}

impl Default for Params {
    fn default() -> Self {
        Self {
            sample_rate: 8_000.0,
            bit_depth: DEFAULT_BIT_DEPTH,
            block_size: 256,
            max_amplitude: 1.0,
            auto_calibrate: false,
        }
    }
}

impl Params {
    /// Validates the configuration.
    ///
    /// * `sample_rate` must be `> 0`.
    /// * `bit_depth` must lie in `[MIN_BIT_DEPTH, MAX_BIT_DEPTH]`.
    /// * `block_size` must be a positive power of two.
    pub fn validate(&self) -> Result<()> {
        if !self.sample_rate.is_finite() || self.sample_rate <= 0.0 {
            return Err(Error::InvalidSampleRate {
                sample_rate: self.sample_rate,
            });
        }
        if !(MIN_BIT_DEPTH..=MAX_BIT_DEPTH).contains(&self.bit_depth) {
            return Err(Error::InvalidBitDepth {
                bit_depth: self.bit_depth,
                min: MIN_BIT_DEPTH,
                max: MAX_BIT_DEPTH,
            });
        }
        if self.block_size == 0 || !self.block_size.is_power_of_two() {
            return Err(Error::InvalidBlockSize {
                block_size: self.block_size,
            });
        }
        Ok(())
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn defaults_are_valid() {
        Params::default().validate().unwrap();
    }

    #[test]
    fn rejects_zero_sample_rate() {
        let p = Params {
            sample_rate: 0.0,
            ..Default::default()
        };
        assert!(matches!(p.validate(), Err(Error::InvalidSampleRate { .. })));
    }

    #[test]
    fn rejects_out_of_range_bit_depth() {
        for bad in [7, 33] {
            let p = Params {
                bit_depth: bad,
                ..Default::default()
            };
            assert!(matches!(p.validate(), Err(Error::InvalidBitDepth { .. })));
        }
    }

    #[test]
    fn rejects_non_power_of_two_block() {
        for bad in [0, 3, 100, 255] {
            let p = Params {
                block_size: bad,
                ..Default::default()
            };
            assert!(matches!(p.validate(), Err(Error::InvalidBlockSize { .. })));
        }
    }

    #[test]
    fn accepts_power_of_two_blocks() {
        for good in [1usize, 2, 64, 256, 1024] {
            let p = Params {
                block_size: good,
                ..Default::default()
            };
            p.validate().unwrap();
        }
    }
}
