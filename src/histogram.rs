//! Amplitude histogram: thresholds, activity counts and hangover counters
//! (Process 3 of ITU-T Rec. P.56).

/// Histogram of the smoothed envelope `q` against a geometric threshold
/// progression, with hangover counting.
///
/// Mirrors the reference state (`a[]`, `c[]`, `hang[]` in `SVP56_state`):
/// thresholds run geometrically from `2^-(bitno-1)` up to `0.5`, activity
/// counts how many envelope samples are (or have recently been) above each
/// threshold, and hangover extends the count by `H` seconds below threshold.
#[derive(Debug, Clone)]
pub struct Histogram {
    /// Threshold levels `c[j]`, in ascending order (index `0` = lowest).
    thresholds: Vec<f64>,
    /// Activity count `a[j]` per threshold.
    activity: Vec<u64>,
    /// Hangover counter `hang[j]` per threshold.
    hangover: Vec<u64>,
}

impl Histogram {
    /// Creates the histogram for the given bit depth.
    ///
    /// Thresholds follow the reference initialization: geometric
    /// progression starting at `0.5` and halving `bit_depth - 1` times
    /// (`c[0] = 2^-(bitno-1)`, `c[thres_no-1] = 0.5`). Hangover counters
    /// start at the full hangover length, as in the reference.
    pub fn new(bit_depth: u32) -> Self {
        let thres_no = (bit_depth - 1) as usize;
        let mut thresholds = Vec::with_capacity(thres_no);
        // Same iteration order as the reference: fill from the top down.
        thresholds.resize(thres_no, 0.0);
        let mut x = 0.5;
        for j in 1..=thres_no {
            thresholds[thres_no - j] = x;
            x /= 2.0;
        }
        Self {
            thresholds,
            activity: vec![0; thres_no],
            hangover: vec![0; thres_no],
        }
    }

    /// Hangover counters `hang[j]` (test/diagnostic access).
    #[allow(dead_code)]
    pub fn hangover_counters(&self) -> &[u64] {
        &self.hangover
    }

    /// Resets the counters; thresholds are kept.
    pub fn reset(&mut self, hangover_init: u64) {
        self.activity.fill(0);
        self.hangover.fill(hangover_init);
    }

    /// Number of thresholds in use (`bit_depth - 1`) (diagnostic access).
    #[cfg(test)]
    pub fn len(&self) -> usize {
        self.thresholds.len()
    }

    /// Threshold levels, ascending.
    pub fn thresholds(&self) -> &[f64] {
        &self.thresholds
    }

    /// Activity counts, aligned with [`Self::thresholds`].
    pub fn activity(&self) -> &[u64] {
        &self.activity
    }

    /// Applies one envelope sample `q` to every threshold, following the
    /// reference counting rule:
    ///
    /// * `q >= c[j]` → count and reset hangover;
    /// * `q < c[j]` and hangover not yet exhausted → count and extend
    ///   hangover;
    /// * otherwise → do nothing.
    ///
    /// `hangover_limit` is `I = floor(H · f + 0.5)`, the hangover length in
    /// samples.
    pub fn count(&mut self, q: f64, hangover_limit: u64) {
        for j in 0..self.thresholds.len() {
            if q >= self.thresholds[j] {
                self.activity[j] += 1;
                self.hangover[j] = 0;
            } else if self.hangover[j] < hangover_limit {
                self.activity[j] += 1;
                self.hangover[j] += 1;
            }
        }
    }

    /// Scales all thresholds by `factor` (used by the auto-calibration
    /// mode when the signal peak exceeds `max_amplitude`).
    ///
    /// When `factor` is an exact power of two the geometric grid maps
    /// onto itself (`c_new[j] = c_old[j + k]` for `factor = 2^k`), so the
    /// accumulated activity counts and hangover counters shift down by
    /// `k` bins to stay attached to their original threshold levels. The
    /// top `k` bins (absolute levels above the old grid) start fresh.
    pub fn scale_thresholds(&mut self, factor: f64) {
        let k = factor.log2().round();
        if k >= 1.0 && (factor / 2.0_f64.powf(k) - 1.0).abs() < 1e-9 {
            let k = k as usize;
            let len = self.thresholds.len();
            self.activity.copy_within(k..len, 0);
            self.hangover.copy_within(k..len, 0);
            for j in len - k..len {
                self.activity[j] = 0;
                // Saturated hangover = "not recently active", matching a
                // fresh meter (hang < I is false for any realistic I).
                self.hangover[j] = u64::MAX;
            }
        }
        for t in &mut self.thresholds {
            *t *= factor;
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn threshold_progression_matches_reference() {
        // 16 bit → 15 thresholds, c[0] = 2^-15, c[14] = 0.5.
        let h = Histogram::new(16);
        assert_eq!(h.len(), 15);
        assert_eq!(h.thresholds()[0], 2.0_f64.powi(-15));
        assert_eq!(h.thresholds()[14], 0.5);
        // Geometric: each step halves the previous.
        for w in h.thresholds().windows(2) {
            assert_eq!(w[1], w[0] * 2.0);
        }
    }

    #[test]
    fn hangover_extends_activity_below_threshold() {
        let mut h = Histogram::new(16);
        h.reset(5);
        let threshold = h.thresholds()[0]; // lowest
                                           // 3 samples above, then 10 below (hangover limit 5).
        for _ in 0..3 {
            h.count(threshold * 2.0, 5);
        }
        for _ in 0..10 {
            h.count(0.0, 5);
        }
        // 3 above + 5 hangover samples = 8.
        assert_eq!(h.activity()[0], 8);
        assert_eq!(h.hangover_counters()[0], 5);
    }

    #[test]
    fn scaling_thresholds_keeps_progression() {
        let mut h = Histogram::new(16);
        h.scale_thresholds(2.0);
        assert_eq!(h.thresholds()[14], 1.0);
        assert_eq!(h.thresholds()[0], 2.0_f64.powi(-14));
    }
}
