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
//!
//! # FFT-domain design (extended implementation)
//!
//! The cascade is a single LTI system with transfer function
//!
//! ```text
//!        ⎛  1 − g   ⎞²
//! H(z) = ⎜ ──────── ⎟
//!        ⎝ 1 − g z⁻¹ ⎠
//! ```
//!
//! Process 2 can therefore run **blockwise** on fixed `2^N` blocks: take the
//! DFT of the block of `|x|`, multiply bin-wise by `H(e^{jω_k})` sampled on
//! the DFT grid, and inverse-transform. Because the IIR filter is infinite,
//! plain circular convolution is only an approximation — an overlap-save
//! scheme must carry the previous block's tail (or state is propagated
//! exactly by processing the filter state separately). This is the key
//! design challenge of the blockwise implementation and is tracked as an
//! open item; [`TimeDomainFilter`] is the exact reference-equivalent path
//! and the correctness baseline.
//!
//! [`fft_filter_response`] precomputes `H(e^{jω_k})` on the DFT grid for a
//! given block size without requiring an FFT library, ready for the
//! blockwise filter once the convolution backend is chosen.

/// Transfer function of the cascade at the DFT-bin frequencies.
///
/// Returns the complex frequency response `H(e^{j·2π·k/N})` for
/// `k = 0..N/2` (non-negative bins; the rest follow by Hermitian symmetry).
/// `g` is the smoothing coefficient `e^(−1/(f·T))`.
///
/// Reserved for the blockwise FFT-domain implementation (see module docs);
/// not yet wired into the processing path.
#[allow(dead_code)]
pub fn fft_filter_response(g: f64, block_size: usize) -> Vec<(f64, f64)> {
    let half = block_size / 2 + 1;
    let num = (1.0 - g) * (1.0 - g);
    let mut response = Vec::with_capacity(half);
    for k in 0..half {
        let omega = 2.0 * std::f64::consts::PI * k as f64 / block_size as f64;
        let re = g * omega.cos();
        let im = -g * omega.sin();
        // 1 / (1 − g·z⁻¹) with z⁻¹ = e^(−jω) → denominator 1 − g·(cos ω − j sin ω)
        let den_re = 1.0 - re;
        let den_im = -im;
        let den_sq = den_re * den_re + den_im * den_im;
        let mag = num / den_sq;
        let phase = den_im.atan2(den_re);
        let (sin_p, cos_p) = phase.sin_cos();
        response.push((mag * cos_p, mag * sin_p));
    }
    response
}

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

    /// The smoothing coefficient `g = e^(−1/(f·T))` (diagnostic access).
    #[allow(dead_code)]
    pub fn coefficient(&self) -> f64 {
        self.g
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

    #[test]
    fn fft_response_dc_bin_is_one() {
        let g = (-1.0f64 / (8_000.0 * 0.03)).exp();
        let resp = fft_filter_response(g, 256);
        assert!((resp[0].0 - 1.0).abs() < 1e-9); // bin 0: H(1) = 1
        assert!(resp[0].1.abs() < 1e-9); // no phase at DC
    }
}
