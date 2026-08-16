---
title: P.56 Pre-Filter Bands
---

The `--pre-filter` option of `p56-asl measure` and `p56-asl calibrate` applies the
P.56 *protection filter* before the active speech level analysis. P.56 specifies
this filter as a pair of tolerance limits (an upper and a lower response limit
relative to the response at 1 kHz) rather than as an exact transfer function. Any
filter whose magnitude response stays inside the corridor between the two limits
conforms.

This page documents the three standardized bands, the tolerance values as
tabulated in the Recommendation, and the filter designs this crate implements to
meet them.

## Tolerance corridors

All three bands share the same corridor shape: an upper limit that falls to
−49.75 dB outside the passband and may peak at +0.25 dB inside it, and a lower
limit of −0.25 dB that applies between the two lower-edge frequencies and is
unbounded (−∞) outside them.

| Band | Clause | Signal bandwidth |
| ---- | ------ | ----------------- |
| NB | clause 10.2, Table 3, Figure 2 | 300–3 400 Hz (conventional telephony) |
| SWB | Annex B, Table B.1 | 50–14 000 Hz |
| FB | Annex C, Table C.1 | 20–20 000 Hz |

### NB — Table 3 (clause 10.2)

Upper limit response relative to 1 kHz:

| Frequency (Hz) | Limit (dB) |
| -------------- | ---------- |
| 16 | −49.75 |
| 160 | +0.25 |
| 7 000 | +0.25 |
| 70 000 | −49.75 |

Lower limit response relative to 1 kHz:

| Frequency (Hz) | Limit (dB) |
| -------------- | ---------- |
| under 200 | −∞ |
| 200 | −0.25 |
| 5 500 | −0.25 |
| over 5 500 | −∞ |

### SWB — Table B.1 (Annex B)

Upper limit response relative to 1 kHz:

| Frequency (Hz) | Limit (dB) |
| -------------- | ---------- |
| 16 | −49.75 |
| 50 | +0.25 |
| 14 000 | +0.25 |
| 70 000 | −49.75 |

Lower limit response relative to 1 kHz:

| Frequency (Hz) | Limit (dB) |
| -------------- | ---------- |
| under 70 | −∞ |
| 70 | −0.25 |
| 12 000 | −0.25 |
| over 12 000 | −∞ |

### FB — Table C.1 (Annex C)

Upper limit response relative to 1 kHz:

| Frequency (Hz) | Limit (dB) |
| -------------- | ---------- |
| 9 | −49.75 |
| 20 | +0.25 |
| 20 000 | +0.25 |
| 70 000 | −49.75 |

Lower limit response relative to 1 kHz:

| Frequency (Hz) | Limit (dB) |
| -------------- | ---------- |
| under 30 | −∞ |
| 30 | −0.25 |
| 18 000 | −0.25 |
| over 18 000 | −∞ |

## Interpolation rule

Between the tabulated anchors the limits interpolate linearly in
$\log_{10}(f)$, and outside the outermost anchors the corridor extends with the
constant anchor level. Figure 2 of the Recommendation draws these transitions as
straight lines on the log frequency axis, which fixes the interpolation rule.

## Implementation

The tolerance corridor constrains only the magnitude response. This crate
implements each band as a cascade of RBJ biquad sections (direct form 1),
streaming-safe for blockwise processing, with per-section Q values following the
Butterworth pole geometry (Chebyshev for the FB low pass):

| Band | High pass | Low pass |
| ---- | --------- | -------- |
| NB | Butterworth-8 @ 150 Hz | Butterworth-6 @ 7.3 kHz |
| SWB | Butterworth-12 @ 50 Hz | Butterworth-6 @ 14 kHz |
| FB | Butterworth-14 @ 24 Hz | Chebyshev-I n=10, 0.15 dB @ 20 kHz |

The low-pass half is omitted when the Nyquist frequency does not exceed the
band's in-band ceiling (for example, NB at 16 kHz input: everything above 7 kHz
sits outside the corridor anyway, and the passband itself satisfies the +0.25 dB
ceiling). When the Nyquist frequency exceeds the ceiling but the corner would
land too close to it, the corner moves to 0.98 × Nyquist to keep bilinear
warping inside tolerance.

Each design was verified against its corridor on a dense logarithmic grid; see
the `corridor_compliance` tests in `src/prefilter.rs`.

## Instrument requirements (context)

Clause 10.2 also sets noise requirements for a physical meter: the filter output
noise level must stay below −75 dBm fullband (20–20 000 Hz) and below −90 dBmp
telephone weighted. Annexes B/C additionally relax linearity and frequency
response accuracy for B-equivalent instruments on SWB/FB signals
(Tables B.2/B.3 and C.2/C.3); the tables below quote them for reference.

### Table B.2 — Linearity (SWB)

| Frequency (Hz) | Input range (dBV) | Accuracy (dB) |
| -------------- | ----------------- | ------------- |
| 100 to 4 000 | +16 to −45 | ±0.1 |
| 4 000 to 16 000 | +13 to −45 | ±0.3 |

### Table B.3 — Frequency response (SWB)

| Frequency (Hz) | Input range (dBV) | Accuracy (dB) |
| -------------- | ----------------- | ------------- |
| 100 to 4 000 | +16 to −45 | ±0.2 |
| 4 000 to 16 000 | +13 to −45 | ±0.4 |

### Table C.2 — Linearity (FB)

| Frequency (Hz) | Input range (dBV) | Accuracy (dB) |
| -------------- | ----------------- | ------------- |
| 100 to 4 000 | +16 to −45 | ±0.1 |
| 4 000 to 24 000 | +13 to −45 | ±0.3 |

### Table C.3 — Frequency response (FB)

| Frequency (Hz) | Input range (dBV) | Accuracy (dB) |
| -------------- | ----------------- | ------------- |
| 100 to 4 000 | +16 to −45 | ±0.2 |
| 4 000 to 24 000 | +13 to −45 | ±0.4 |
