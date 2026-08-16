//! P.56 protection pre-filters (clause 10.2/Table 3, Annex B, Annex C).
//!
//! The tolerance corridors are given as upper-limit and lower-limit
//! responses relative to 1 kHz. Between the tabulated anchor frequencies
//! the limits interpolate linearly in log10(f) (Figure 2 shows straight
//! transitions), and outside the outermost anchors the corridor extends
//! with constant slope up to the ripple floor/ceiling:
//!
//! ```text
//! upper limit:  −49.75 dB ─╮ rise ╭──── +0.25 dB ──╮ fall ╭− −49.75 dB
//! lower limit:        −∞ ──╯      ╰── −0.25 dB ─────╯     ╰─ −∞
//! ```
//!
//! Implementation: cascaded RBJ biquads (direct form 1), each section
//! prewarped at the same corner frequency; per-section Q values follow
//! the classical Butterworth pole geometry (or Chebyshev for the FB low
//! pass, whose 20 kHz→70 kHz upper transition is steeper than any
//! Butterworth can satisfy while staying within −0.25 dB at 20 kHz).
//!
//! All designs were verified against the corridor on a dense log grid
//! (see `tests::corridor_compliance`).

use crate::error::{Error, Result};

/// Band selector for the protection filter.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Band {
    /// Narrowband, clause 10.2 / Table 3 / Figure 2.
    Nb,
    /// Super-wideband, Annex B / Table B.1.
    Swb,
    /// Full band, Annex C / Table C.1.
    Fb,
}

impl Band {
    /// Case-insensitive name (`"NB"`, `"SWB"`, `"FB"`).
    ///
    /// # Errors
    ///
    /// [`Error::InvalidBand`] for unknown names.
    pub fn parse(name: &str) -> Result<Self> {
        match name.trim().to_ascii_uppercase().as_str() {
            "NB" => Ok(Self::Nb),
            "SWB" => Ok(Self::Swb),
            "FB" => Ok(Self::Fb),
            other => Err(Error::InvalidBand(other.to_string())),
        }
    }

    /// Canonical lower-case name.
    pub fn as_str(self) -> &'static str {
        match self {
            Self::Nb => "nb",
            Self::Swb => "swb",
            Self::Fb => "fb",
        }
    }

    /// Tolerance corridor of this band, as `(frequency, relative level in
    /// dB)` anchor pairs for the upper and the lower limit.
    pub fn corridor(self) -> Corridor {
        match self {
            // Table 3.
            Self::Nb => Corridor {
                upper: &[
                    (16.0, -49.75),
                    (160.0, 0.25),
                    (7000.0, 0.25),
                    (70000.0, -49.75),
                ],
                lower: &[(200.0, -0.25), (5500.0, -0.25)],
            },
            // Table B.1.
            Self::Swb => Corridor {
                upper: &[
                    (16.0, -49.75),
                    (50.0, 0.25),
                    (14000.0, 0.25),
                    (70000.0, -49.75),
                ],
                lower: &[(70.0, -0.25), (12000.0, -0.25)],
            },
            // Table C.1.
            Self::Fb => Corridor {
                upper: &[
                    (9.0, -49.75),
                    (20.0, 0.25),
                    (20000.0, 0.25),
                    (70000.0, -49.75),
                ],
                lower: &[(30.0, -0.25), (18000.0, -0.25)],
            },
        }
    }
}

/// Piecewise-linear (in log10 f) tolerance corridor.
pub struct Corridor {
    /// Upper-limit anchors, ascending in frequency.
    pub upper: &'static [(f64, f64)],
    /// Lower-limit anchors (flat segment endpoints).
    pub lower: &'static [(f64, f64)],
}

impl Corridor {
    /// Upper limit at `f` in dB, linear in log10 between anchors, clamped
    /// to the anchor levels outside.
    pub fn upper_db(&self, f: f64) -> f64 {
        interp_log(self.upper, f)
    }

    /// Lower limit at `f` in dB (`f64::NEG_INFINITY` outside the flat
    /// segment).
    pub fn lower_db(&self, f: f64) -> f64 {
        if f < self.lower[0].0 || f > self.lower[1].0 {
            f64::NEG_INFINITY
        } else {
            -0.25
        }
    }
}

fn interp_log(anchors: &'static [(f64, f64)], f: f64) -> f64 {
    let a = anchors;
    debug_assert!(a.len() >= 2);
    if f <= a[0].0 {
        return a[0].1;
    }
    if f >= a[a.len() - 1].0 {
        return a[a.len() - 1].1;
    }
    for w in a.windows(2) {
        if f <= w[1].0 {
            let t = ((f / w[0].0).log10()) / ((w[1].0 / w[0].0).log10());
            return w[0].1 + t * (w[1].1 - w[0].1);
        }
    }
    unreachable!("f between first and last anchor")
}

/// One RBJ biquad section, direct form 1.
#[derive(Debug, Clone, Copy, PartialEq)]
struct Biquad {
    b0: f64,
    b1: f64,
    b2: f64,
    a1: f64,
    a2: f64,
    z1: f64,
    z2: f64,
}

impl Biquad {
    fn new(b0: f64, b1: f64, b2: f64, a1: f64, a2: f64) -> Self {
        Self {
            b0,
            b1,
            b2,
            a1,
            a2,
            z1: 0.0,
            z2: 0.0,
        }
    }

    /// Low-pass biquad: exact bilinear image of the normalized analog
    /// section `H(s) = 1/(s² + s/Q + 1)`, prewarped at `fc` (digital `fc`
    /// maps to the analog corner). Unlike the RBJ cookbook formulas, the
    /// cascade of sections reproduces the analog prototype exactly under
    /// the warping `Ω(f) = tan(πf/fs)/tan(πfc/fs)`, which matters for
    /// corners near Nyquist (e.g. FB at 44.1/48 kHz).
    fn lowpass(fs: f64, fc: f64, q: f64) -> Self {
        let c = (std::f64::consts::PI * fc / fs).tan();
        let a0 = 1.0 + c / q + c * c;
        Self::normalized(
            c * c,
            2.0 * c * c,
            c * c,
            a0,
            2.0 * (c * c - 1.0),
            1.0 - c / q + c * c,
        )
    }

    /// High-pass biquad: exact bilinear image of `H(s) = s²/(s² + s/Q + 1)`,
    /// prewarped at `fc` (see [`Self::lowpass`]).
    fn highpass(fs: f64, fc: f64, q: f64) -> Self {
        let c = (std::f64::consts::PI * fc / fs).tan();
        let a0 = 1.0 + c / q + c * c;
        Self::normalized(1.0, -2.0, 1.0, a0, 2.0 * (c * c - 1.0), 1.0 - c / q + c * c)
    }

    fn normalized(b0: f64, b1: f64, b2: f64, a0: f64, a1: f64, a2: f64) -> Self {
        Self::new(b0 / a0, b1 / a0, b2 / a0, a1 / a0, a2 / a0)
    }

    #[inline]
    fn tick(&mut self, x: f64) -> f64 {
        let y = self.b0 * x + self.z1;
        self.z1 = self.b1 * x - self.a1 * y + self.z2;
        self.z2 = self.b2 * x - self.a2 * y;
        y
    }

    /// Complex frequency response at frequency `f`.
    fn response_at(&self, f: f64, fs: f64) -> (f64, f64) {
        // z = e^{jw}, evaluate H(z) = (b0 + b1 z^-1 + b2 z^-2)/(1 + a1 z^-1 + a2 z^-2)
        let w = 2.0 * std::f64::consts::PI * f / fs;
        let (cw, sw) = (w.cos(), w.sin());
        // z^-1 = cw - j·sw
        let (z1r, z1i) = (cw, -sw);
        let (z2r, z2i) = ((2.0 * cw * cw - 1.0), (-2.0 * cw * sw)); // z^-2
        let num = (
            self.b0 + self.b1 * z1r + self.b2 * z2r,
            self.b1 * z1i + self.b2 * z2i,
        );
        let den = (
            1.0 + self.a1 * z1r + self.a2 * z2r,
            self.a1 * z1i + self.a2 * z2i,
        );
        // num / den
        let d = den.0 * den.0 + den.1 * den.1;
        (
            (num.0 * den.0 + num.1 * den.1) / d,
            (num.1 * den.0 - num.0 * den.1) / d,
        )
    }
}

/// Butterworth section Q values for even order `n`:
/// `Q_k = 1/(2·cos θ_k)` with poles at angles θ_k = (2k+1)π/(2n)
/// from the negative real axis (ascending Q, classic table order).
fn butterworth_qs(n: usize) -> Vec<f64> {
    let m = n / 2;
    let mut qs = Vec::with_capacity(m);
    for k in 0..m {
        let theta = (2.0 * k as f64 + 1.0) * std::f64::consts::PI / (2.0 * n as f64);
        qs.push(1.0 / (2.0 * theta.cos()));
    }
    qs
}

/// SWB low-pass corner (Hz) at sampling rate `fs` with Nyquist `nyq`.
///
/// The corridor's lower limit of −0.25 dB binds up to 12 kHz; the
/// upper limit falls steeply from 14 kHz on. A Butterworth-8 keeps
/// enough margin on both. Because bilinear warping squeezes the
/// digital transition near Nyquist, the corner is rate-adaptive: the
/// inverse prewarp that puts the 12 kHz point on the −0.08 dB contour
/// (Ω ≈ 0.7795), clamped to [14.25 kHz, 15.2 kHz] and 0.98·Nyquist.
fn swb_lp_corner(fs: f64, nyq: f64) -> f64 {
    // tan(π·12000/fs) / tan(π·fc/fs) = 0.7795 → solve for fc.
    let om = (std::f64::consts::PI * 12000.0 / fs).tan();
    let fc = fs / std::f64::consts::PI * (om / 0.7795).atan();
    fc.clamp(14250.0, 15200.0).min(0.98 * nyq)
}

/// Chebyshev type-I section parameters `(ω_k, Q_k)` for even order `n`,
/// ripple `r` dB. Poles on the ellipse: p_k = −σ_k ± jν_k with
/// σ_k = sinh(a)·sin θ_k, ν_k = cosh(a)·cos θ_k, θ_k = (2k+1)π/(2n),
/// a = asinh(1/ε)/n. The conjugate pair factors into
/// `s² + 2σ_k·s + (σ_k² + ν_k²)`, so the section corner is
/// `ω_k = √(σ_k² + ν_k²) = √(sinh²(a) + cos²θ_k)` — **not** the pole
/// imaginary part ν_k — and `Q_k = ω_k/(2σ_k)`.
///
/// Unlike Butterworth (poles on the unit circle, so unity-corner
/// sections suffice), Chebyshev poles sit on an ellipse: each section
/// has its own corner ω_k relative to the ripple edge. Sections are
/// built with unit DC gain, so the prototype has DC gain 1 and dips
/// to −r dB at the ripple valleys — well inside the ±0.25 dB corridor.
fn chebyshev1_sections(n: usize, r: f64) -> Vec<(f64, f64)> {
    let eps = (10f64.powf(r / 10.0) - 1.0).sqrt();
    let a = (1.0 / n as f64) * (1.0 / eps).asinh();
    let mut sections = Vec::with_capacity(n / 2);
    for k in 0..n / 2 {
        let theta = (2.0 * k as f64 + 1.0) * std::f64::consts::PI / (2.0 * n as f64);
        let sigma = a.sinh() * theta.sin();
        let nu = a.cosh() * theta.cos();
        let corner = (sigma * sigma + nu * nu).sqrt();
        sections.push((corner, corner / (2.0 * sigma)));
    }
    sections
}

/// P.56 protection pre-filter: a fixed biquad cascade implementing the
/// tolerance corridor of the selected band at a given sampling rate.
///
/// Stateful and streaming-safe: [`Self::process`] may be called with
/// arbitrary block lengths and the state carries across calls.
///
/// # Design (verified against the corridors, see module tests)
///
/// | Band | High pass | Low pass |
/// |------|-----------|----------|
/// | NB | Butterworth-8 @ 150 Hz | Butterworth-6 @ 7.3 kHz |
/// | SWB | Butterworth-12 @ 50 Hz | Butterworth-8 @ 14.25–15.2 kHz (rate-adaptive) |
/// | FB | Butterworth-14 @ 24 Hz | Chebyshev-I n=10, 0.15 dB @ 20 kHz |
///
/// The low-pass half is omitted when the Nyquist frequency does not exceed
/// the band's in-band ceiling (e.g. NB at 16 kHz input: everything above
/// 7 kHz is outside the corridor anyway and the upper-limit ceiling of
/// +0.25 dB is satisfied by the passband itself). When the Nyquist
/// frequency exceeds the ceiling but the corner would land too close to
/// it (bilinear warping), the corner is pulled to 0.98·Nyquist.
#[derive(Debug, Clone)]
pub struct PreFilter {
    band: Band,
    sections: Vec<Biquad>,
    fs: f64,
}

impl PreFilter {
    /// Builds the protection filter for `band` at sampling rate `fs` (Hz).
    ///
    /// # Errors
    ///
    /// Returns [`Error::InvalidSampleRate`] for non-positive rates or
    /// rates below 4 kHz (the narrowest corridor anchor needs at least
    /// that bandwidth).
    pub fn new(band: Band, fs: f64) -> Result<Self> {
        if !fs.is_finite() || fs < 4000.0 {
            return Err(Error::InvalidSampleRate { sample_rate: fs });
        }
        let nyquist = fs / 2.0;
        let mut sections = Vec::new();
        match band {
            Band::Nb => {
                for q in butterworth_qs(8) {
                    sections.push(Biquad::highpass(fs, 150.0, q));
                }
                if nyquist > 7000.0 {
                    let fc = 7300.0f64.min(0.98 * nyquist);
                    for q in butterworth_qs(6) {
                        sections.push(Biquad::lowpass(fs, fc, q));
                    }
                }
            }
            Band::Swb => {
                for q in butterworth_qs(12) {
                    sections.push(Biquad::highpass(fs, 50.0, q));
                }
                if nyquist > 14000.0 {
                    for q in butterworth_qs(8) {
                        sections.push(Biquad::lowpass(fs, swb_lp_corner(fs, nyquist), q));
                    }
                }
            }
            Band::Fb => {
                for q in butterworth_qs(14) {
                    sections.push(Biquad::highpass(fs, 24.0, q));
                }
                if nyquist > 20000.0 {
                    let fc = 20000.0f64.min(0.98 * nyquist);
                    // Map each analog pole frequency ω_k onto the digital
                    // axis under the cascade-wide prewarp: the section
                    // corner is tan⁻¹(ω_k·tan(π·fc/fs)) scaled back to Hz.
                    let edge = (std::f64::consts::PI * fc / fs).tan();
                    for (w, q) in chebyshev1_sections(10, 0.15) {
                        let fc_k = fs / std::f64::consts::PI * (w * edge).atan();
                        sections.push(Biquad::lowpass(fs, fc_k, q));
                    }
                }
            }
        }
        Ok(Self { band, sections, fs })
    }

    /// Processes samples in place; state carries across calls.
    pub fn process(&mut self, samples: &mut [f32]) {
        for x in samples.iter_mut() {
            let mut y = f64::from(*x);
            for sec in &mut self.sections {
                y = sec.tick(y);
            }
            *x = y as f32;
        }
    }

    /// Resets the filter state (impulse response re-starts).
    pub fn reset(&mut self) {
        for sec in &mut self.sections {
            sec.z1 = 0.0;
            sec.z2 = 0.0;
        }
    }

    /// Magnitude response `|H(f)|` at frequency `f` (Hz), cascading all
    /// sections. `f` is clamped to Nyquist internally.
    pub fn magnitude_at(&self, f: f64) -> f64 {
        let f = f.min(0.499_999 * self.fs);
        let mut mag2 = 1.0;
        for sec in &self.sections {
            let (re, im) = sec.response_at(f, self.fs);
            mag2 *= re * re + im * im;
        }
        mag2.sqrt()
    }

    /// Response in dB relative to the response at 1 kHz.
    pub fn response_db(&self, f: f64) -> f64 {
        20.0 * (self.magnitude_at(f) / self.magnitude_at(1000.0)).log10()
    }

    /// Maximum corridor violation in dB (positive = violation) on a dense
    /// log-frequency grid from 5 Hz to the relevant corridor extent
    /// (70 kHz or Nyquist). Diagnostics and tests.
    pub fn max_violation_db(&self) -> f64 {
        let corridor = self.band.corridor();
        let f_hi = corridor
            .upper
            .last()
            .map(|p| p.0)
            .unwrap_or(70000.0)
            .min(0.499_999 * self.fs);
        let f_lo = corridor.upper[0].0 * 0.6;
        let n = 4000;
        let mut worst = f64::NEG_INFINITY;
        for i in 0..=n {
            let f = f_lo * (f_hi / f_lo).powf(i as f64 / n as f64);
            let r = self.response_db(f);
            let viol_up = r - corridor.upper_db(f);
            let viol_lo = corridor.lower_db(f) - r;
            worst = worst.max(viol_up).max(viol_lo);
        }
        worst
    }

    /// The band this filter implements.
    pub fn band(&self) -> Band {
        self.band
    }

    /// The sampling rate this filter was designed for, in Hz.
    pub fn fs(&self) -> f64 {
        self.fs
    }

    /// Number of biquad sections.
    pub fn num_sections(&self) -> usize {
        self.sections.len()
    }
}
#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn diag_response() {
        for &(band, fs) in &[
            (Band::Nb, 8000.0),
            (Band::Swb, 48000.0),
            (Band::Fb, 44100.0),
        ] {
            let pf = PreFilter::new(band, fs).unwrap();
            let corridor = band.corridor();
            let mut worst = (f64::NEG_INFINITY, 0.0);
            let f_hi = corridor.upper.last().unwrap().0.min(0.499_999 * fs);
            for i in 0..=2000 {
                let f = 5.4 * (f_hi / 5.4).powf(i as f64 / 2000.0);
                let r = pf.response_db(f);
                let viol = (r - corridor.upper_db(f)).max(corridor.lower_db(f) - r);
                if viol > worst.0 {
                    worst = (viol, f);
                }
            }
            println!(
                "{band:?}@{fs}: worst viol {:+.3} dB at {:.1} Hz (sections={})",
                worst.0,
                worst.1,
                pf.num_sections()
            );
            for f in [30.0, 50.0, 70.0, 100.0, 1000.0] {
                println!(
                    "  f={f:8.1} resp={:+.3} dB  lower={:+.3}",
                    pf.response_db(f),
                    corridor.lower_db(f)
                );
            }
            if band == Band::Swb {
                for (i, s) in pf.sections.iter().enumerate() {
                    println!(
                        "  sec[{i}] b=({:.6e},{:.6e},{:.6e}) a=({:.6e},{:.6e})",
                        s.b0, s.b1, s.b2, s.a1, s.a2
                    );
                }
            }
            if band == Band::Fb {
                for (i, s) in pf.sections.iter().enumerate() {
                    let (re, im) = s.response_at(19956.0, fs);
                    let (re1, im1) = s.response_at(1000.0, fs);
                    println!(
                        "  sec[{i}] |H(19956)|={:.6} |H(1000)|={:.6} b=({:.6e},{:.6e},{:.6e}) a=({:.6e},{:.6e})",
                        (re * re + im * im).sqrt(),
                        (re1 * re1 + im1 * im1).sqrt(),
                        s.b0, s.b1, s.b2, s.a1, s.a2
                    );
                }
            }
        }
    }

    #[test]
    fn band_parse() {
        assert_eq!(Band::parse("nb").unwrap(), Band::Nb);
        assert_eq!(Band::parse("SWB").unwrap(), Band::Swb);
        assert_eq!(Band::parse(" Fb ").unwrap(), Band::Fb);
        assert!(Band::parse("wb").is_err());
    }

    #[test]
    fn corridor_interpolation() {
        let c = Band::Nb.corridor();
        assert!((c.upper_db(16.0) - (-49.75)).abs() < 1e-12);
        assert!((c.upper_db(160.0) - 0.25).abs() < 1e-12);
        // halfway (in log10) between 16 and 160 → −24.75
        let mid = (16.0 * 160.0f64).sqrt();
        assert!((c.upper_db(mid) - (-24.75)).abs() < 1e-9);
        assert_eq!(c.lower_db(1000.0), -0.25);
        assert_eq!(c.lower_db(100.0), f64::NEG_INFINITY);
    }

    #[test]
    fn butterworth_qs_sane() {
        let qs = butterworth_qs(4);
        assert_eq!(qs.len(), 2);
        assert!((qs[0] - 0.54119610).abs() < 1e-7); // classic 4th order Qs
        assert!((qs[1] - 1.30656296).abs() < 1e-7);
    }

    #[test]
    fn magnitude_of_identity_corridor_nb_at_16k() {
        // NB @ 16 kHz keeps the LP (Nyquist 8 kHz > 7 kHz): corner pulled to 0.98·8k = 7.84k
        let pf = PreFilter::new(Band::Nb, 16000.0).unwrap();
        assert!(pf.num_sections() >= 4);
    }

    /// Dense-grid compliance for all bands at representative rates.
    #[test]
    fn corridor_compliance() {
        let cases: &[(Band, f64)] = &[
            (Band::Nb, 8000.0),
            (Band::Nb, 16000.0),
            (Band::Nb, 44100.0),
            (Band::Nb, 48000.0),
            (Band::Swb, 16000.0),
            (Band::Swb, 32000.0),
            (Band::Swb, 48000.0),
            (Band::Swb, 96000.0),
            (Band::Fb, 44100.0),
            (Band::Fb, 48000.0),
            (Band::Fb, 96000.0),
        ];
        for &(band, fs) in cases {
            let pf = PreFilter::new(band, fs).unwrap();
            let v = pf.max_violation_db();
            assert!(
                v <= 0.03,
                "{band:?} @ {fs} Hz violates corridor by {v:.4} dB"
            );
        }
    }

    /// Streaming equivalence: feeding the filter in chunks must give the
    /// same output as one-shot processing.
    #[test]
    fn streaming_equivalence() {
        let mut one_shot = PreFilter::new(Band::Nb, 16000.0).unwrap();
        let mut chunked = PreFilter::new(Band::Nb, 16000.0).unwrap();
        let sig: Vec<f32> = (0..5000)
            .map(|i| (i as f32 * 0.05).sin() * 0.5 + (i as f32 * 0.001).sin() * 0.3)
            .collect();
        let mut a = sig.clone();
        one_shot.process(&mut a);
        let mut b = Vec::new();
        for chunk in sig.chunks(37) {
            let mut c = chunk.to_vec();
            chunked.process(&mut c);
            b.extend_from_slice(&c);
        }
        for (x, y) in a.iter().zip(b.iter()) {
            assert!((x - y).abs() < 1e-6, "streaming mismatch: {x} vs {y}");
        }
    }

    /// A 1 kHz sine must pass essentially unattenuated (relative level
    /// within ±0.1 dB), a 5 Hz component must be crushed.
    #[test]
    fn sine_rejection() {
        let mut pf = PreFilter::new(Band::Nb, 48000.0).unwrap();
        let fs = 48000.0f64;
        let mut pass: Vec<f32> = (0..48000)
            .map(|i| (2.0 * std::f64::consts::PI * 1000.0 * i as f64 / fs).sin() as f32)
            .collect();
        pf.process(&mut pass);
        // RMS of a unit sine is 1/sqrt(2) ≈ 0.7071.
        let rms_pass = (pass[10000..]
            .iter()
            .map(|x| (*x as f64) * (*x as f64))
            .sum::<f64>()
            / (pass.len() - 10000) as f64)
            .sqrt();
        assert!(
            (20.0 * (rms_pass / std::f64::consts::FRAC_1_SQRT_2).log10()).abs() < 0.1,
            "passband loss too high: {rms_pass}"
        );
        let mut stop: Vec<f32> = (0..48000)
            .map(|i| (2.0 * std::f64::consts::PI * 5.0 * i as f64 / fs).sin() as f32)
            .collect();
        pf.process(&mut stop);
        // Skip the startup transient, as above.
        let rms_stop = (stop[10000..]
            .iter()
            .map(|x| (*x as f64) * (*x as f64))
            .sum::<f64>()
            / (stop.len() - 10000) as f64)
            .sqrt();
        assert!(rms_stop < 0.01, "stopband leakage: {rms_stop}");
    }
}
