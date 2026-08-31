---
title: "0001 — Rust core via PyO3"
---

## 0001 — Rust core via PyO3

**Date**: 2026-08-16
**Status**: Accepted

### Context

P.56 measurement is strictly sample-serial: every sample updates the
envelope recursion and up to 23 histogram bins. Measuring hours of audio in
pure Python (or NumPy vectorizations that cannot express the sequential
recursion) is orders of magnitude too slow, while a C extension would
reintroduce the memory-safety burden the reference implementation carries.

### Decision

The entire numerical core (meter, histogram, pre-filters, resampler) is
implemented in Rust and exposed to Python via PyO3/maturin as
`p56_asl._native`. The Python package only marshals NumPy arrays and
provides the CLI.

### Consequences

- Compiled speed with memory safety; no `unsafe` FFI beyond PyO3.
- The build requires a Rust toolchain (maturin); a missing or stale native
  module fails loudly at `import p56_asl` — there is no Python fallback.
- API surface is typed via `src/p56_asl/_native.pyi`.
