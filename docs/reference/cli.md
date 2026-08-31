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

Output formats via `--format`/`-f`:

=== "text (default)"

    ```text
    File: speech.wav
    Sample rate: 16000 Hz
    Channel 1:
      Active speech level: -25.02 dB
      Activity factor:     90.0 %
      RMS level:           -25.48 dB
      DC level:            +0.000277
      Peak positive:       +0.980743
      Peak negative:       -0.613037
      Peak abs:            +0.980743
      Samples:             105472
    ```

=== "json"

    Machine-readable payload with per-channel results at the analysis rate:

    ```json
    {
      "file": "speech.wav",
      "pre_filter": null,
      "channels": [1],
      "results": [
        {
          "channel": 1,
          "active_speech_level_db": -25.022884533542687,
          "activity_factor": 0.9004373859222891,
          "rms_db": -25.478349348593284,
          "dc_level": 0.0002773950979547593,
          "peak_positive": 0.980743408203125,
          "peak_negative": -0.613037109375,
          "peak_abs": 0.980743408203125,
          "sample_count": 105472,
          "sample_rate": 16000
        }
      ]
    }
    ```

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
| `--subtype`      | input subtype  | `calibrate` output libsndfile subtype (e.g. `PCM_16`, `PCM_24`, `FLOAT`, `DOUBLE`, `FLAC`); the container follows the output extension. |

## Supported WAV formats

- PCM 8/16/24/32-bit integer (`WAVE_FORMAT_PCM` and the extensible variant)
- IEEE float 32/64-bit (`WAVE_FORMAT_IEEE_FLOAT`)

Integer data is normalized to $[-1, 1]$ on read. On write, the output uses
`--subtype` (default: the input's subtype); out-of-range values are clipped
with a warning for fixed-point output, while float output (`FLOAT`/`DOUBLE`)
keeps values beyond $\pm 1$ unclipped.
