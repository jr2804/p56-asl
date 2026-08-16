//! Active speech level meter — ITU-T Rec. P.56 main loop.
//!
//! Port of the reference `speech_voltmeter` / `bin_interp` semantics
//! (`ref/sv-p56.c`, v2.3) restructured for **blockwise** processing: the
//! caller feeds fixed-size blocks (power-of-two length) and all internal
//! state — envelope filter, histogram counters, energy accumulators —
//! carries across blocks.
//!
//! The sample-wise loops inside [`ActiveSpeechLevelMeter::process_block`]
//! are ordered exactly like the reference so the results are bit-identical;
//! the FFT-domain envelope filtering (see [`crate::filter`]) is the
//! planned blockwise acceleration.

use crate::constants::{HANGOVER_TIME_S, MARGIN_DB, MIN_LOG_OFFSET, REF_DB, SILENCE_LEVEL_DB};
use crate::error::{Error, Result};
use crate::filter::{SmoothingFilter, TimeDomainFilter};
use crate::histogram::Histogram;
use crate::params::Params;

/// Results of a completed measurement.
#[derive(Debug, Clone, Copy, PartialEq)]
pub struct Measurement {
    /// Active speech level, in dB re. `max_amplitude` (dBov by default).
    pub active_speech_level_db: f64,
    /// Activity factor, in `0..1` (reference reports it in percent).
    pub activity_factor: f64,
    /// Long-term RMS level, in dB re. `max_amplitude`.
    pub rms_db: f64,
    /// Average (DC) level of the input samples.
    pub dc_level: f64,
    /// Maximum positive sample.
    pub peak_positive: f64,
    /// Maximum negative sample (≤ 0).
    pub peak_negative: f64,
    /// Maximum absolute sample.
    pub peak_abs: f64,
    /// Number of processed samples.
    pub sample_count: u64,
}

/// Active speech level meter.
///
/// Stateful: feed blocks of samples with [`Self::process_block`], then call
/// [`Self::finish`] to obtain the measurement. [`Self::reset`] clears all
/// accumulated state while keeping the configuration.
pub struct ActiveSpeechLevelMeter {
    params: Params,
    histogram: Histogram,
    filter: TimeDomainFilter,
    /// Hangover length in samples: `I = floor(H · f + 0.5)`.
    hangover_limit: u64,
    /// Number of samples since last reset.
    n: u64,
    /// Sum of samples (`s`).
    s: f64,
    /// Squared sum of samples (`sq`).
    sq: f64,
    /// Maximum absolute value since last reset.
    max: f64,
    /// Maximum positive value since last reset.
    max_p: f64,
    /// Maximum negative value since last reset.
    max_n: f64,
    /// Current `max_amplitude` (may be adapted by auto-calibration).
    max_amplitude: f64,
}

impl ActiveSpeechLevelMeter {
    /// Creates a meter from validated [`Params`].
    ///
    /// # Errors
    ///
    /// Returns an error when the parameters fail [`Params::validate`].
    pub fn new(params: Params) -> Result<Self> {
        params.validate()?;
        let hangover_limit = (HANGOVER_TIME_S * params.sample_rate + 0.5).floor() as u64;
        let mut histogram = Histogram::new(params.bit_depth);
        histogram.reset(hangover_limit);
        Ok(Self {
            filter: TimeDomainFilter::new(params.sample_rate),
            histogram,
            hangover_limit,
            n: 0,
            s: 0.0,
            sq: 0.0,
            max: 0.0,
            max_p: 0.0,
            max_n: 0.0,
            max_amplitude: params.max_amplitude,
            params,
        })
    }

    /// The configuration this meter was created with.
    pub fn params(&self) -> &Params {
        &self.params
    }

    /// Resets all accumulated state. Configuration (including a calibrated
    /// `max_amplitude`) is kept.
    pub fn reset(&mut self) {
        self.histogram.reset(self.hangover_limit);
        self.filter.reset();
        self.n = 0;
        self.s = 0.0;
        self.sq = 0.0;
        self.max = 0.0;
        self.max_p = 0.0;
        self.max_n = 0.0;
    }

    /// Processes one block of samples (length may be any power-of-two block
    /// size, but must be `<=` `params.block_size`; see note below).
    ///
    /// Sample-wise operation order matches the reference
    /// `speech_voltmeter` exactly: peak tracking, then Process 1 (energy),
    /// then Process 2 (envelope) and Process 3 (histogram counting).
    ///
    /// # Errors
    ///
    /// Returns [`Error::InvalidBlockSize`] if the block is longer than
    /// `params.block_size`.
    pub fn process_block(&mut self, samples: &[f32]) -> Result<()> {
        if samples.len() > self.params.block_size {
            return Err(Error::InvalidBlockSize {
                block_size: samples.len(),
            });
        }
        let block = samples.len();
        let mut abs_samples = Vec::with_capacity(block);
        let mut envelope = Vec::with_capacity(block);

        for &sample in samples {
            let x = f64::from(sample);
            // Peak tracking.
            let ax = x.abs();
            if ax > self.max {
                self.max = ax;
            }
            if x > self.max_p {
                self.max_p = x;
            }
            if x < self.max_n {
                self.max_n = x;
            }
            // Process 1: energy statistics.
            self.sq += x * x;
            self.s += x;
            self.n += 1;
            abs_samples.push(ax);
        }

        // Process 2: temporal smoothing (blockwise in one pass).
        self.filter.process(&abs_samples, &mut envelope);

        // Process 3: threshold counting on the envelope.
        for &q in &envelope {
            self.histogram.count(q, self.hangover_limit);
        }

        self.calibrate_if_needed(block);
        Ok(())
    }

    /// Extended auto-calibration: if the block's peak exceeds the current
    /// `max_amplitude`, double `max_amplitude` (and the thresholds with it)
    /// until the peak fits. Open design point — semantics pending the
    /// dedicated discussion.
    fn calibrate_if_needed(&mut self, block_len: usize) {
        if !self.params.auto_calibrate || self.max <= self.max_amplitude {
            return;
        }
        let mut factor = 1.0;
        while self.max >= factor * self.max_amplitude {
            factor *= 2.0;
        }
        if factor > 1.0 {
            self.max_amplitude *= factor;
            self.histogram.scale_thresholds(factor);
        }
        let _ = block_len;
    }

    /// Computes the final measurement from the accumulated state.
    ///
    /// Port of the reference `speech_voltmeter` tail: silence detection,
    /// then serial threshold iteration with `bin_interp` interpolation.
    ///
    /// # Errors
    ///
    /// Returns [`Error::NoSamples`] if no samples were processed.
    pub fn finish(&self) -> Result<Measurement> {
        if self.n == 0 {
            return Err(Error::NoSamples);
        }
        let dc_level = self.s / self.n as f64;
        let long_term_level = 10.0 * (self.sq / self.n as f64 + MIN_LOG_OFFSET).log10();
        let rms_db = long_term_level - REF_DB;
        let mut activity_factor = 0.0;
        let mut active_level = SILENCE_LEVEL_DB;

        let a = self.histogram.activity();
        let c = self.histogram.thresholds();

        // Test the lowest active counter; if 0, this is silence.
        if a[0] != 0 {
            let adb = 10.0 * (self.sq / a[0] as f64 + MIN_LOG_OFFSET).log10();
            let cdb = 20.0 * c[0].log10();
            // Silence when the measured level is below the margin.
            if adb - cdb >= MARGIN_DB {
                // Proceed serially for the remaining thresholds.
                for j in 1..a.len() {
                    if a[j] != 0 {
                        let adb = 10.0 * (self.sq / a[j] as f64 + MIN_LOG_OFFSET).log10();
                        let cdb = 20.0 * (c[j] + MIN_LOG_OFFSET).log10();
                        let delta = adb - cdb;
                        if delta <= MARGIN_DB {
                            // Interpolate between threshold j-1 and j.
                            let amdb = 10.0 * (self.sq / a[j - 1] as f64 + MIN_LOG_OFFSET).log10();
                            let cmdb = 20.0 * (c[j - 1] + MIN_LOG_OFFSET).log10();
                            active_level = bin_interp(adb, amdb, cdb, cmdb, MARGIN_DB, 0.5);
                            activity_factor =
                                10.0_f64.powf((long_term_level - active_level) / 10.0);
                            active_level -= REF_DB;
                            break;
                        }
                    }
                }
            }
        }

        Ok(Measurement {
            active_speech_level_db: active_level,
            activity_factor,
            rms_db,
            dc_level,
            peak_positive: self.max_p,
            peak_negative: self.max_n,
            peak_abs: self.max,
            sample_count: self.n,
        })
    }
}

/// Binary interpolation between two (count, threshold) points in the dB
/// domain, ported exactly from the reference `bin_interp` including the
/// tolerance relaxation after 20 iterations.
///
/// `upcount`/`upthr` are the (level, threshold) of the upper point,
/// `lwcount`/`lwthr` of the lower point, `margin` the P.56 margin in dB
/// and `tol` the convergence tolerance in dB.
pub fn bin_interp(
    upcount: f64,
    lwcount: f64,
    upthr: f64,
    lwthr: f64,
    margin: f64,
    tol: f64,
) -> f64 {
    let tol = tol.abs();
    let mut iterno = 1u64;

    // Check if the extreme counts are not already the true active value.
    if ((upcount - upthr) - margin).abs() < tol {
        return upcount;
    }
    if ((lwcount - lwthr) - margin).abs() < tol {
        return lwcount;
    }

    // Initialize the first middle for the given bounds.
    let mut midcount = (upcount + lwcount) / 2.0;
    let mut midthr = (upthr + lwthr) / 2.0;
    let mut upcount = upcount;
    let mut upthr = upthr;
    let mut lwcount = lwcount;
    let mut lwthr = lwthr;
    let mut tol = tol;

    // Iterate until the tolerance is met.
    loop {
        let diff = (midcount - midthr) - margin;
        if diff.abs() <= tol {
            break;
        }
        // If not converged within 20 iterations, relax tolerance by 10%.
        iterno += 1;
        if iterno > 20 {
            tol *= 1.1;
        }
        if diff > tol {
            // New bounds are the upper and middle activities.
            midcount = (upcount + midcount) / 2.0;
            midthr = (upthr + midthr) / 2.0;
            lwcount = midcount;
            lwthr = midthr;
        } else {
            // New bounds are the middle and lower activities.
            midcount = (midcount + lwcount) / 2.0;
            midthr = (midthr + lwthr) / 2.0;
            upcount = midcount;
            upthr = midthr;
        }
    }

    midcount
}

#[cfg(test)]
mod tests {
    use super::*;

    fn meter(bit_depth: u32) -> ActiveSpeechLevelMeter {
        ActiveSpeechLevelMeter::new(Params {
            sample_rate: 8_000.0,
            bit_depth,
            block_size: 256,
            max_amplitude: 1.0,
            auto_calibrate: false,
        })
        .unwrap()
    }

    #[test]
    fn silence_reports_minus_100_db() {
        let mut m = meter(16);
        m.process_block(&[0.0; 256]).unwrap();
        m.process_block(&[0.0; 256]).unwrap();
        let meas = m.finish().unwrap();
        assert_eq!(meas.active_speech_level_db, SILENCE_LEVEL_DB);
        assert_eq!(meas.activity_factor, 0.0);
    }

    #[test]
    fn full_scale_sine_has_expected_level() {
        // 1 kHz sine at amplitude 1.0, 8 kHz, 16 bit: ASL ≈ −3.01 dBov.
        let mut m = meter(16);
        let mut block = [0.0f32; 256];
        for (k, s) in block.iter_mut().enumerate() {
            *s = (2.0 * std::f64::consts::PI * k as f64 / 8.0).sin() as f32;
        }
        for _ in 0..40 {
            m.process_block(&block).unwrap();
        }
        let meas = m.finish().unwrap();
        assert!(
            (meas.active_speech_level_db + 3.01).abs() < 0.1,
            "ASL = {}",
            meas.active_speech_level_db
        );
        // The rectified-sine envelope keeps a ripple of ~±0.06 around its
        // mean, so the reference semantics yield a factor just below 1.
        assert!(meas.activity_factor > 0.9);
    }

    #[test]
    fn finish_without_samples_errors() {
        let m = meter(16);
        assert_eq!(m.finish(), Err(Error::NoSamples));
    }

    #[test]
    fn oversized_block_rejected() {
        let mut m = meter(16);
        assert_eq!(
            m.process_block(&[0.0; 257]),
            Err(Error::InvalidBlockSize { block_size: 257 })
        );
    }

    #[test]
    fn reset_clears_state() {
        let mut m = meter(16);
        m.process_block(&[0.5; 256]).unwrap();
        m.reset();
        // After reset no samples have been processed; `finish` must error
        // exactly like a fresh meter (see `finish_without_samples_errors`).
        assert_eq!(m.finish(), Err(Error::NoSamples));
        m.process_block(&[0.0; 256]).unwrap();
        let meas = m.finish().unwrap();
        assert_eq!(meas.active_speech_level_db, SILENCE_LEVEL_DB);
        assert_eq!(meas.sample_count, 256);
        assert_eq!(meas.peak_abs, 0.0);
    }

    #[test]
    fn bin_interp_returns_upper_bound_for_margin_solution() {
        // upcount − upthr == margin → returns upcount immediately.
        let v = bin_interp(0.0, -10.0, -15.9, -20.0, MARGIN_DB, 0.5);
        assert_eq!(v, 0.0);
    }

    #[test]
    fn auto_calibration_doubles_thresholds_on_overflow() {
        // Signal peaks at 2.5 with max_amplitude 1.0 → factor 2.
        let mut m = ActiveSpeechLevelMeter::new(Params {
            sample_rate: 8_000.0,
            bit_depth: 16,
            block_size: 256,
            max_amplitude: 1.0,
            auto_calibrate: true,
        })
        .unwrap();
        let mut block = [0.0f32; 256];
        for (k, s) in block.iter_mut().enumerate() {
            *s = (2.5 * (2.0 * std::f64::consts::PI * k as f64 / 8.0).sin()) as f32;
        }
        m.process_block(&block).unwrap();
        assert_eq!(m.max_amplitude, 4.0); // 1 → 2 → 4, then 2.5 < 4
                                          // Thresholds were scaled by the same factor.
        assert_eq!(m.histogram.thresholds()[0], 2.0_f64.powi(-15) * 4.0);
    }
}
