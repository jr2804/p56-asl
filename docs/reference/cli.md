---
title: CLI Reference
---

The `p56-asl` command line tool measures and calibrates WAV files. Both
commands share the same selection and processing options; all processing
(pre-filter, resampling, measurement) uses the Rust core.

```bash
uv run p56-asl --help        # or: python -m p56_asl --help
```

## measure

Measures the active speech level of a WAV file. Aliases: `calc`,
`calculate`. One result set is printed per selected channel.

```bash
p56-asl measure INPUT.wav [OPTIONS]
```

```text
File: speech.wav
Sample rate: 16000 Hz
Pre-filter: NB
Channel 1:
  Active speech level: -18.71 dB
  Activity factor:     99.1 %
  RMS level:           -18.75 dB
  ...
```

Use `--format json` for machine-readable output; the payload contains the
per-channel `active_speech_level_db`, `activity_factor`, `rms_db`,
`dc_level`, `peak_positive`, `peak_negative`, `peak_abs`, `sample_count`
(at the analysis rate) and `sample_rate`.

## calibrate

Scales a WAV file by a dB gain. Alias: `scale`. With an output path the
result is written there; without one the input file is calibrated in place.

```bash
p56-asl calibrate INPUT.wav 3.01 OUTPUT.wav   # +3.01 dB
p56-asl calibrate INPUT.wav -3.01             # in place, -3.01 dB
```

The gain accepts an explicit sign (`+3.01`, `-3.01`); no sign means `+`.
Only the selected channels are calibrated; unselected channels are copied
unchanged. When `--fs` is given, the whole file is resampled and the output
carries the new sampling rate.

## Options

Both commands accept:

| Option           | Default        | Description                                                       |
| ---------------- | -------------- | ----------------------------------------------------------------- |
| `--fs`           | file rate      | Resample to this rate (Hz) before analysis/calibration and write. |
| `--pre-filter`   | none           | P.56 protection pre-filter band: `NB`, `SWB` or `FB` (see [Pre-filter bands](prefilter-bands.md)). |
| `--time-start`   | `0.0`          | Start of the analysis window (s).                                  |
| `--time-duration`| to end of file | Length of the analysis window (s).                                 |
| `--channels`     | all channels   | 1-indexed channel or comma list, e.g. `1`, `1,2`, `2, 4`; blanks around separators are tolerated. |

`measure` additionally accepts `--format`/`-f` (`text` or `json`).

## Supported WAV formats

- PCM 8/16/24/32-bit integer (`WAVE_FORMAT_PCM` and the extensible variant)
- IEEE float 32/64-bit (`WAVE_FORMAT_IEEE_FLOAT`)

Integer data is normalized to $[-1, 1]$ on read; on write, out-of-range
values are clipped and the file keeps its original bit depth and integer/float
encoding.
