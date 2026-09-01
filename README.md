# p56-asl

**p56-asl** is a Python library and CLI for measuring active speech level (ASL)
according to [ITU-T Rec. P.56](https://www.itu.int/rec/T-REC-P.56) — the standard
used in telecom voice-quality testing. It combines a high-performance Rust core
with Python bindings, giving you both a programmatic API and a scriptable
command-line tool.

> Unlike most P.56 implementations, this one is **bit-exact with the ITU
> reference C code** (validated against G.191 test vectors) while remaining
> MIT-licensed and pip-installable.

<!-- markdownlint-disable MD033 -->
<p align="center">
  <a href="https://pypi.org/project/p56-asl/"><img alt="PyPI" src="https://img.shields.io/badge/pypi-p56--asl-3776ab?logo=python"></a>
  <a href="https://jr2804.github.io/p56-asl/license/"><img alt="License" src="https://img.shields.io/badge/license-MIT-green.svg"></a>
  <a href="https://github.com/jr2804/p56-asl/actions"><img alt="CI" src="https://github.com/jr2804/p56-asl/actions/workflows/ci.yml/badge.svg"></a>
</p>
<!-- markdownlint-enable MD033 -->

---

## Features

- **Bit-Exact P.56 Compliance**: Validated against ITU-T G.191 reference test
  vectors — the same algorithm telecom labs use.
- **Extended Measurement Mode**: Measures above full-scale signals (up to +40 dB)
  with automatic calibration — the standard P.56 cannot do this.
- **Three Interfaces**: Python library, CLI tool, and direct Rust API — use
  whatever fits your pipeline.
- **High Performance**: Rust core handles multi-gigabyte WAV files without loading
  them fully into memory.
- **Flexible I/O**: Reads any format [soundfile](https://python-soundfile.readthedocs.io/)
  supports (WAV, FLAC, OGG) and resamples to 16 kHz automatically when needed.

## Installation

```bash
pip install p56-asl
```

Requires Python 3.13+.

## Quick Start

### Python API

```python
from p56_asl import ActiveSpeechLevelMeter
import soundfile as sf

# Read a mono WAV file
samples, sr = sf.read("input.wav", dtype="float32")

# Measure active speech level
meter = ActiveSpeechLevelMeter(sample_rate=sr)
meter.process_block(samples)
result = meter.finish()

print(f"ASL: {result.active_speech_level_db:.2f} dB")
print(f"Activity factor: {result.activity_factor:.2%}")
```

### CLI

```bash
# Measure a WAV file
p56-asl measure input.wav

# JSON output with options
p56-asl measure input.wav --pre-filter nb --format json

# Calibrate (amplify by +3.01 dB)
p56-asl calibrate input.wav 3.01 output.wav
```

See the [CLI reference](https://jr2804.github.io/p56-asl/reference/cli/) for
all options.

## Documentation

Full documentation with API reference, architecture decisions, and the P.56
method explanation is available at:

→ **<https://jr2804.github.io/p56-asl**>

## Development

```bash
git clone https://github.com/jr2804/p56-asl.git
cd p56-asl
mise dev          # install tools + deps
mise test         # run test suite
mise lint         # ruff + ty + codespell
mise docs-serve   # live preview at http://localhost:8000
```

Pre-commit hooks, contributing guidelines, and the full tech stack are
documented in the [Contributing guide](https://jr2804.github.io/p56-asl/contributing/).

## License

MIT — see the [license page](https://jr2804.github.io/p56-asl/license/) for
details.
