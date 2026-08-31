---
title: "0003 — Extended mode auto-calibration"
---

## 0003 — Extended mode auto-calibration

**Date**: 2026-08-16
**Status**: Accepted

### Context

Float WAV material is not bounded to $[-1, 1]$. The reference P.56
implementation is undefined for peaks above full scale: the top histogram
bins saturate and the margin analysis can no longer locate the envelope.
Rejecting such files outright would make the library unusable on
unnormalized float material.

### Decision

An optional extended mode (`auto_calibrate=True`) watches the block peak.
Whenever a block peak exceeds the current `max_amplitude`, the reference is
doubled until it covers the peak; all 23 histogram thresholds shift up by
+6.02 dB and the activity counters slide down by the same number of bins,
so every counter stays attached to the absolute level it was measuring.

### Consequences

- Unnormalized float input is measured correctly instead of saturating.
- The calibration only moves the grid — it never changes what is measured.
  Results are invariant to when calibration triggers (pinned by a
  bit-identical test against fixed-reference runs).
- The CLI does not expose the option; it is a library feature.
