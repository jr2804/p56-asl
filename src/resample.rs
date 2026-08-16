//! Input resampling to an arbitrary target rate.
//!
//! The P.56 algorithm requires at least 16 kHz; the CLI additionally
//! offers resampling to any `--fs`. Inputs are resampled with rubato's
//! `FftFixedIn<f32>` (FFT-domain, high quality). [`Resampler`] is
//! **stateful**: the rubato instance carries its internal overlap across
//! `process` calls, and an input-side buffer accumulates samples until a
//! full chunk is available. Leftover input samples are padded with zeros
//! and flushed by [`Resampler::flush`].

use crate::error::{Error, Result};
use rubato::{FftFixedIn, Resampler as _};

/// Internal processing rate required by P.56.
pub const TARGET_RATE: u32 = 16_000;

/// Chunk size fed to rubato (input frames per `process` call). Chosen as a
/// power of two so the output frame count is predictable; 1024 gives
/// latency of ~64 ms at 16 kHz output and low FFT overhead.
const CHUNK_SIZE: usize = 1024;

/// Stateful resampler: any input rate -> any target rate, mono, f32.
pub struct Resampler {
    resampler: FftFixedIn<f32>,
    /// Input samples waiting for a full chunk (interleaved mono).
    pending: Vec<f32>,
    /// Output produced ahead of consumption.
    output_queue: Vec<f32>,
    /// Configured input rate in Hz.
    sample_rate: u32,
    /// Configured output rate in Hz.
    target_rate: u32,
    /// True once [`Self::flush`] drained the pending input.
    flushed: bool,
    /// Total output samples already returned to the caller.
    delivered: usize,
}

impl Resampler {
    /// Creates a resampler from `sample_rate` to `target_rate` (both in
    /// Hz, positive). Rates equal to the target still work but should be
    /// bypassed by the caller (the meter does so for 16 kHz input).
    ///
    /// # Errors
    ///
    /// Returns [`Error::InvalidSampleRate`] when `sample_rate` is not
    /// positive, or construction fails inside rubato.
    pub fn new(sample_rate: u32, target_rate: u32) -> Result<Self> {
        if sample_rate == 0 {
            return Err(Error::InvalidSampleRate { sample_rate: 0.0 });
        }
        if target_rate == 0 {
            return Err(Error::InvalidSampleRate {
                sample_rate: target_rate as f64,
            });
        }
        let resampler =
            FftFixedIn::<f32>::new(sample_rate as usize, target_rate as usize, CHUNK_SIZE, 1, 1)
                .map_err(|e| Error::Resampler(e.to_string()))?;
        Ok(Self {
            resampler,
            pending: Vec::with_capacity(CHUNK_SIZE),
            output_queue: Vec::new(),
            sample_rate,
            target_rate,
            flushed: false,
            delivered: 0,
        })
    }

    /// Number of input samples needed before rubato produces output
    /// (diagnostic access).
    #[allow(dead_code)]
    pub fn chunk_size(&self) -> usize {
        CHUNK_SIZE
    }

    /// Feeds input samples; returns all 16 kHz output available so far in
    /// call order. May be empty until a full chunk accumulates.
    pub fn process(&mut self, samples: &[f32]) -> Result<Vec<f32>> {
        if self.flushed {
            return Err(Error::Resampler(
                "process() called after flush()".to_string(),
            ));
        }
        self.pending.extend_from_slice(samples);
        let mut out = std::mem::take(&mut self.output_queue);
        while self.pending.len() >= CHUNK_SIZE {
            let chunk: Vec<f32> = self.pending.drain(..CHUNK_SIZE).collect();
            let waves = self
                .resampler
                .process(&[chunk], None)
                .map_err(|e| Error::Resampler(e.to_string()))?;
            // mono: exactly one channel
            out.extend_from_slice(&waves[0]);
        }
        self.delivered += out.len();
        Ok(out)
    }

    /// Zero-pads the pending input to a final chunk and returns the final
    /// output. Consumes the resampler state; `process` must not be called
    /// afterwards. `total_input` is the total number of input samples fed
    /// (used to trim resampler ramp-up delay from the output length so the
    /// output sample count matches `ceil(total_input * 16000 / rate)`).
    pub fn flush(&mut self, total_input: u64) -> Result<Vec<f32>> {
        if self.flushed {
            return Ok(Vec::new());
        }
        self.flushed = true;
        let mut out = std::mem::take(&mut self.output_queue);
        if !self.pending.is_empty() {
            let mut chunk = self.pending.clone();
            chunk.resize(CHUNK_SIZE, 0.0);
            let waves = self
                .resampler
                .process(&[chunk], None)
                .map_err(|e| Error::Resampler(e.to_string()))?;
            out.extend_from_slice(&waves[0]);
        }
        // Trim to expected length: total_input * ratio, rounded. `delivered`
        // counts output already returned by `process`, so the final total
        // matches round(total_input * target_rate / rate).
        let expected = ((total_input as f64) * (self.target_rate as f64 / self.sample_rate as f64))
            .round() as usize;
        if self.delivered + out.len() > expected {
            let keep = expected.saturating_sub(self.delivered);
            out.truncate(keep);
        }
        self.delivered += out.len();
        Ok(out)
    }

    /// Configured input sampling rate in Hz (diagnostic access).
    #[allow(dead_code)]
    pub fn rate(&self) -> u32 {
        self.sample_rate
    }

    /// Configured output sampling rate in Hz (diagnostic access).
    #[allow(dead_code)]
    pub fn target(&self) -> u32 {
        self.target_rate
    }
}
