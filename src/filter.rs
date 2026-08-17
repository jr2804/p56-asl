//! Temporal smoothing of the rectified signal — Process 2 of ITU-T Rec. P.56.
//!
//! The reference implementation applies a cascade of two first-order
//! low-pass filters to the rectified signal `|x|`:
//!
//! ```text
//! p[n] = g·p[n-1] + (1 − g)·|x[n]|        g = e^(−1/(f·T)),  T = 0.03 s
//! q[n] = g·q[n-1] + (1 − g)·p[n]
//! ```
//!
//! The envelope `q` is then compared against the histogram thresholds.
//! [`TimeDomainFilter`] is the exact reference-equivalent path and the
//! correctness baseline; it is the only implementation.

/// Temporal smoothing filter producing the envelope `q` per sample.
pub trait SmoothingFilter {
    /// Filters one block of rectified samples; `envelope` receives the
    /// smoothed value `q[n]` for each input sample.
    fn process(&mut self, abs_samples: &[f64], envelope: &mut Vec<f64>);

    /// Resets the internal filter state (`p`, `q`) to zero.
    fn reset(&mut self);
}

/// Exact reference-equivalent filter: sample-wise recursion with state
/// carried across blocks. Bit-identical to the C reference when the same
/// samples are fed in the same order.
#[derive(Debug, Clone)]
pub struct TimeDomainFilter {
    g: f64,
    p: f64,
    q: f64,
}

impl TimeDomainFilter {
    /// Creates the filter for the given sampling frequency.
    pub fn new(sample_rate: f64) -> Self {
        let g = (-1.0 / (sample_rate * crate::constants::SMOOTHING_TIME_CONSTANT_S)).exp();
        Self { g, p: 0.0, q: 0.0 }
    }

    /// Current envelope state `q` (diagnostic access).
    #[allow(dead_code)]
    pub fn envelope(&self) -> f64 {
        self.q
    }
}

impl SmoothingFilter for TimeDomainFilter {
    fn process(&mut self, abs_samples: &[f64], envelope: &mut Vec<f64>) {
        envelope.clear();
        envelope.reserve(abs_samples.len());
        let g = self.g;
        let one_minus_g = 1.0 - g;
        for &x in abs_samples {
            self.p = g * self.p + one_minus_g * x;
            self.q = g * self.q + one_minus_g * self.p;
            envelope.push(self.q);
        }
    }

    fn reset(&mut self) {
        self.p = 0.0;
        self.q = 0.0;
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn dc_gain_is_one() {
        // A constant input of 1.0 must converge to 1.0.
        let mut f = TimeDomainFilter::new(8_000.0);
        let mut env = Vec::new();
        for _ in 0..20 {
            f.process(&[1.0; 256], &mut env);
        }
        let last = *env.last().unwrap();
        assert!((last - 1.0).abs() < 1e-6, "envelope {last}");
    }

    #[test]
    fn zero_input_decays_to_zero() {
        let mut f = TimeDomainFilter::new(8_000.0);
        let mut env = Vec::new();
        f.process(&[0.5; 256], &mut env);
        // Decay time constant is f·T = 240 samples per pole; ~30 time
        // constants of zeros drives the cascade well below 1e-9.
        f.process(&[0.0; 8_192], &mut env);
        assert!(*env.last().unwrap() < 1e-9);
    }

    #[test]
    fn state_carries_across_blocks() {
        // Splitting the input across process calls must be bit-identical
        // to a single call over the concatenated samples.
        let input: Vec<f64> = (0..512).map(|k| (k as f64 * 0.137).sin().abs()).collect();
        let mut whole = TimeDomainFilter::new(8_000.0);
        let mut env_whole = Vec::new();
        whole.process(&input, &mut env_whole);

        let mut split = TimeDomainFilter::new(8_000.0);
        let mut env_split = Vec::new();
        let mut tail = Vec::new();
        split.process(&input[..128], &mut tail);
        env_split.extend_from_slice(&tail);
        split.process(&input[128..384], &mut tail);
        env_split.extend_from_slice(&tail);
        split.process(&input[384..], &mut tail);
        env_split.extend_from_slice(&tail);

        assert_eq!(env_whole, env_split);
        assert_eq!(whole.envelope(), split.envelope());
    }
}
