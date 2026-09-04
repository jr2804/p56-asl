---
title: API Reference
---

The Python API exposes the Rust core: the P.56 meter, the protection
pre-filters, and the resampler. All numerical work happens in the compiled
extension; the Python layer only marshals NumPy arrays.

::: p56_asl

## `ActiveSpeechLevelMeter`

Stateful P.56 speech voltmeter. Feed blocks of samples with
`process_block`, then call `finish` for the result. Results are in dB re.
full scale (`1.0`); see [Measuring Above Full Scale](extended-mode.md) for
the extended mode.

```python
meter = ActiveSpeechLevelMeter(sample_rate=16000.0, block_size=256)
for block in stream:
    meter.process_block(block)      # NDArray[np.float32 | np.float64]
result = meter.finish()             # Measurement
```

### Constructor

```python
ActiveSpeechLevelMeter(
    sample_rate: float = 8000.0,
    block_size: int = 256,
    max_amplitude: float = 1.0,
    auto_calibrate: bool = False,
)
```

| Parameter       | Default | Description                                                              |
| --------------- | ------- | ------------------------------------------------------------------------ |
| `sample_rate`   | `8000`  | Analysis sample rate in Hz.                                              |
| `block_size`    | `256`   | Upper bound on the chunk length accepted by `process_block`.              |
| `max_amplitude` | `1.0`   | Amplitude reference; the histogram grid spans `max_amplitude / 2` downward in −6.02 dB steps. |
| `auto_calibrate`| `False` | Extended mode: double `max_amplitude` (and shift the grid +6.02 dB) whenever a block peak exceeds it. |

!!! note "`block_size` is a guard, not a window"

    Feeding one large block or many small ones is bit-identical: all
    algorithmic state (envelope filters, histogram, accumulators) carries
    across calls. `block_size` only bounds per-call buffer length.

### Methods

| Method                     | Description                                              |
| -------------------------- | -------------------------------------------------------- |
| `process_block(samples)`   | Feed one block (`NDArray[np.float32 \| np.float64]`); must not exceed `block_size`. |
| `finish() -> Measurement`  | Finalize and return the measurement. Errors if no samples were fed. |
| `reset()`                  | Clear all accumulated state, keep the configuration.     |

### Properties

| Property         | Type    | Description                                    |
| ---------------- | ------- | ---------------------------------------------- |
| `sample_rate`    | `float` | Analysis rate.                                 |
| `block_size`     | `int`   | Configured chunk bound.                        |
| `max_amplitude`  | `float` | Current reference (adapted by auto-calibration). |
| `auto_calibrate` | `bool`  | Whether extended mode is active.               |

## `Measurement`

Result of a completed measurement. Values are dB re. full scale (`1.0`),
i.e. dBov.

| Property                  | Type    | Description                                   |
| ------------------------- | ------- | --------------------------------------------- |
| `active_speech_level_db`  | `float` | Active speech level, dBov.                    |
| `activity_factor`         | `float` | Fraction of time the signal is active, `0..1`.|
| `rms_db`                  | `float` | Long-term RMS level, dBov.                    |
| `dc_level`                | `float` | Average (DC) level of the input samples.      |
| `peak_positive`           | `float` | Maximum positive sample.                      |
| `peak_negative`           | `float` | Maximum negative sample (≤ 0).                |
| `peak_abs`                | `float` | Maximum absolute sample.                      |
| `sample_count`            | `int`   | Number of processed samples.                  |

## `PreFilter`

P.56 protection pre-filter (band-limited speech weighting). Three bands are
available, covering the frequency ranges defined in ITU-T Rec. P.56
Tables 3 / B.1 / C.1 — see [P.56 Pre-Filter Bands](prefilter-bands.md).

```python
pf = PreFilter(band="NB", fs=48000.0)
filtered = pf.process(block)     # NDArray[np.float32]
```

| Parameter | Values        | Description                                    |
| --------- | ------------- | ---------------------------------------------- |
| `band`    | `"NB"`, `"SWB"`, `"FB"` | Narrowband / super-wideband / fullband. |
| `fs`      | `float`       | Sample rate in Hz (coefficients are prewarped for it). |

### Methods

| Method                     | Description                                        |
| -------------------------- | -------------------------------------------------- |
| `process(samples) -> NDArray[np.float32]` | Apply the filter; the input array is processed in place and returned. |
| `reset()`                  | Clear the filter state (the sections keep their coefficients). |
| `response_db(f) -> float`  | Magnitude response at frequency `f` in dB (verification aid). |

!!! warning "In-place filtering"

    `PreFilter.process` modifies the caller's buffer and returns it. Pass
    `samples.copy()` if you need the original signal afterwards.

### Properties

| Property       | Type    | Description                            |
| -------------- | ------- | -------------------------------------- |
| `band`         | `str`   | The configured band.                   |
| `sample_rate`  | `float` | The configured rate.                   |
| `num_sections` | `int`   | Biquad section count (14/20/24 for NB/SWB/FB). |

## `Resampler`

Sample-rate conversion for analysis and calibration. Stateful — call
`process` with input blocks, then `flush` to drain the tail.

```python
rs = Resampler(sample_rate=44100, target_rate=48000)
out = rs.process(block)          # list[float]
out += rs.flush()                # residual tail samples
```

| Parameter     | Type  | Description                   |
| ------------- | ----- | ----------------------------- |
| `sample_rate` | `int` | Input rate in Hz.             |
| `target_rate` | `int` | Output rate in Hz.            |

### Methods

| Method                       | Description                                  |
| ---------------------------- | -------------------------------------------- |
| `process(samples) -> list[float]` | Resample one block of input.           |
| `flush() -> list[float]`     | Drain the resampler tail after the last block. |

### Properties

| Property      | Type  | Description        |
| ------------- | ----- | ------------------ |
| `sample_rate` | `int` | Input rate.        |
| `target_rate` | `int` | Output rate.       |

## Command line interface

`p56-asl measure` and `p56-asl calibrate` — see the
[CLI Reference](cli.md). The CLI applies the same Rust core; it does not
currently expose `auto_calibrate` or the raw resampler/pre-filter objects.

