---
title: "0002 — Sample-exact filtering, no FFT acceleration"
---

## 0002 — Sample-exact filtering, no FFT acceleration

**Date**: 2026-08-18
**Status**: Accepted

### Context

The meter must reproduce the ITU-T G.191 reference implementation
(`sv-p56.c`) within ±0.1 dB, pinned by conformance tests against reference
fixtures. FFT-domain filtering or downsampled envelope analysis could
speed up the pre-filter and envelope recursion, but would change the
numerical result and break sample-exact conformance.

### Decision

All filters run sample-serially in f64/f32 exactly as the reference does:
the envelope is a cascade of two first-order recursions, the protection
pre-filter is a transposed direct-form II biquad cascade with per-rate
prewarped coefficients. No downsampling, no per-block power averaging, no
FFT path.

### Consequences

- Benchmark RTF is ≈ 0.001–0.002 (≈ 500–1000× faster than realtime), so
  acceleration is pointless for this workload anyway.
- Conformance is structural, not tuned: the same arithmetic as the
  reference, hence matching results by construction.
- If future targets ever need SIMD, the exact sample-serial path stays the
  correctness baseline any accelerated path must match bit-for-bit.
