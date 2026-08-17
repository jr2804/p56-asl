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
        // Feed the leftover input (zero-padded), then push additional
        // zero chunks through the FFT stages so the pipeline's internal
        // latency fully drains; downsampling configurations hold back
        // up to one chunk's worth of output.
        let mut sent = self.pending.len();
        if !self.pending.is_empty() {
            let mut chunk = self.pending.clone();
            chunk.resize(CHUNK_SIZE, 0.0);
            let waves = self
                .resampler
                .process(&[chunk], None)
                .map_err(|e| Error::Resampler(e.to_string()))?;
            out.extend_from_slice(&waves[0]);
        }
        self.pending.clear();
        let expected = ((total_input as f64) * (self.target_rate as f64 / self.sample_rate as f64))
            .round() as usize;
        let mut guard = 0;
        while self.delivered + out.len() < expected && guard < CHUNK_SIZE {
            let zeros = vec![0.0f32; CHUNK_SIZE];
            let waves = self
                .resampler
                .process(&[zeros], None)
                .map_err(|e| Error::Resampler(e.to_string()))?;
            sent += CHUNK_SIZE;
            let produced = waves[0].len();
            out.extend_from_slice(&waves[0]);
            if produced == 0 {
                break;
            }
            guard += 1;
        }
        // Trim to expected length: total_input * ratio, rounded. `delivered`
        // counts output already returned by `process`, so the final total
        // matches round(total_input * target_rate / rate).
        if self.delivered + out.len() > expected {
            let keep = expected.saturating_sub(self.delivered);
            out.truncate(keep);
        }
        self.delivered += out.len();
        let _ = sent;
        Ok(out)
    }

    /// Resets the internal state; the resampler can be reused afterwards
    /// (e.g. after a meter `reset()` between measurements).
    pub fn reset(&mut self) {
        self.resampler.reset();
        self.pending.clear();
        self.output_queue.clear();
        self.flushed = false;
        self.delivered = 0;
    }

    /// Configured input sampling rate in Hz.
    pub fn source_rate(&self) -> u32 {
        self.sample_rate
    }

    /// Configured output sampling rate in Hz.
    pub fn target_rate(&self) -> u32 {
        self.target_rate
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    const TOL: f32 = 1e-3;

    /// Amplitude/frequency fidelity after arbitrary-rate resampling:
    /// a sine must keep its level within 0.1 dB and its frequency
    /// (measured via zero crossings) within 0.1 %.
    #[test]
    fn sine_fidelity() {
        for &(src, dst) in &[
            (8_000u32, 16_000u32),
            (44_100, 16_000),
            (48_000, 8_000),
            (16_000, 48_000),
        ] {
            let f = 997.0f64;
            let n = (src as f64 * 1.0) as usize;
            let input: Vec<f32> = (0..n)
                .map(|i| {
                    (2.0 * std::f64::consts::PI * f * i as f64 / src as f64).sin() as f32 * 0.5
                })
                .collect();
            let mut r = Resampler::new(src, dst).unwrap();
            let mut out = r.process(&input).unwrap();
            out.extend(r.flush(input.len() as u64).unwrap());
            let n_out = out.len();
            assert!(
                (n_out as f64 - n as f64 * dst as f64 / src as f64).abs() <= 2.0,
                "length {n_out} vs expected {}",
                n as f64 * dst as f64 / src as f64
            );
            // amplitude via RMS over the steady part
            let skip = n_out / 4;
            let rms = (out[skip..]
                .iter()
                .map(|x| (*x as f64) * (*x as f64))
                .sum::<f64>()
                / (n_out - skip) as f64)
                .sqrt();
            let want = 0.5 / std::f64::consts::SQRT_2;
            assert!(
                (20.0 * (rms / want).log10()).abs() < 0.1,
                "{src}->{dst}: rms {rms} vs {want}"
            );
            // frequency via mean half-period distance between ascending
            // zero crossings (central portion only: flush zero-padding
            // splatters the tail)
            let mut xs = Vec::new();
            let lo = n_out / 4;
            let hi = n_out * 3 / 4;
            for i in (lo + 1)..hi {
                if out[i - 1] < 0.0 && out[i] >= 0.0 {
                    xs.push(i as f64);
                }
            }
            let periods: Vec<f64> = xs.windows(2).map(|w| w[1] - w[0]).collect();
            let mean_period = periods.iter().sum::<f64>() / periods.len() as f64;
            let f_meas = dst as f64 / mean_period;
            assert!(
                (f_meas / f - 1.0).abs() < 1e-3,
                "{src}->{dst}: measured {f_meas} Hz"
            );
        }
    }

    /// Streaming equivalence: chunked feeding matches one-shot.
    #[test]
    fn streaming_equivalence() {
        let src = 48_000u32;
        let input: Vec<f32> = (0..src as usize / 2)
            .map(|i| ((i as f64 * 0.03).sin() * 0.4 + (i as f64 * 0.0011).sin() * 0.2) as f32)
            .collect();
        let mut one_shot = Resampler::new(src, 16_000).unwrap();
        let mut a = one_shot.process(&input).unwrap();
        a.extend(one_shot.flush(input.len() as u64).unwrap());

        let mut chunked = Resampler::new(src, 16_000).unwrap();
        let mut b = Vec::new();
        for chunk in input.chunks(777) {
            b.extend(chunked.process(chunk).unwrap());
        }
        b.extend(chunked.flush(input.len() as u64).unwrap());

        assert_eq!(a.len(), b.len());
        for (x, y) in a.iter().zip(b.iter()) {
            assert!((x - y).abs() < TOL, "mismatch: {x} vs {y}");
        }
    }

    /// Total output must equal round(input * target / source) and
    /// `process` after `flush` must fail.
    #[test]
    fn length_and_finality() {
        let mut r = Resampler::new(44_100, 16_000).unwrap();
        let n = 44_100usize; // 1 s -> expect exactly 16_000
        let input: Vec<f32> = (0..n).map(|i| (i as f32 * 0.01).sin() * 0.2).collect();
        let mut out = r.process(&input).unwrap();
        out.extend(r.flush(n as u64).unwrap());
        assert_eq!(out.len(), 16_000);

        assert!(r.process(&[0.0]).is_err());
        // second flush returns empty, no error
        assert!(r.flush(0).unwrap().is_empty());
    }

    /// Invalid rates are rejected.
    #[test]
    fn rejects_zero_rate() {
        assert!(Resampler::new(0, 16_000).is_err());
        assert!(Resampler::new(8_000, 0).is_err());
    }
}
