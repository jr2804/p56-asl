"""CLI command implementations for Extended ITU-T Rec. P.56 - Active Speech Level (ASL)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
import typer

from p56_asl import ActiveSpeechLevelMeter, PreFilter, Resampler
from p56_asl.cli.app import app
from p56_asl.cli.args import (
    ChannelsCalibrateOption,
    ChannelsOption,
    FsCalibrateOption,
    FsOption,
    GainDbArg,
    InputPathArg,
    OutputFormat,
    OutputFormatOption,
    OutputPathArg,
    PreFilterOption,
    TimeDurationOption,
    TimeStartOption,
    parse_channels,
    parse_db,
)
from p56_asl.wav import WavInfo, read_wav, write_wav

# Processing block size for streaming file operations (frames per step).
_BLOCK = 65536


@app.command(name="measure")
@app.command(name="calc", hidden=True, help="Alias for measure.")
@app.command(name="calculate", hidden=True, help="Alias for measure.")
def measure(
    input_path: InputPathArg,
    fs: FsOption = None,
    band: PreFilterOption = None,
    time_start: TimeStartOption = 0.0,
    time_duration: TimeDurationOption = None,
    channels: ChannelsOption = None,
    output_format: OutputFormatOption = OutputFormat.TEXT,
) -> None:
    """Measure the active speech level (P.56) of a WAV file."""
    frames, info, selected = _read_selection(input_path, time_start, time_duration, channels)
    if band is not None and band.upper() not in {"NB", "SWB", "FB"}:
        raise typer.BadParameter(f"--pre-filter must be NB, SWB or FB, got {band!r}")
    rate, prefilter = _pipeline(info, fs, band)
    data = _resampled_channels(frames, info.sample_rate, rate, selected)

    results: list[dict[str, Any]] = []
    for k, c in enumerate(selected):
        ch = np.ascontiguousarray(data[:, k], dtype=np.float32)
        if prefilter is not None:
            prefilter.reset()
            ch = np.asarray(prefilter.process(ch), dtype=np.float32)
        meter = ActiveSpeechLevelMeter(sample_rate=float(rate), bit_depth=32, max_amplitude=1.0)
        for i in range(0, len(ch), _BLOCK):
            meter.process_block(ch[i : i + _BLOCK])
        m = meter.finish()
        results.append(
            {
                "channel": c + 1,
                "active_speech_level_db": m.active_speech_level_db,
                "activity_factor": m.activity_factor,
                "rms_db": m.rms_db,
                "dc_level": m.dc_level,
                "peak_positive": m.peak_positive,
                "peak_negative": m.peak_negative,
                "peak_abs": m.peak_abs,
                "sample_count": len(ch),
                "sample_rate": rate,
            }
        )

    if output_format is OutputFormat.JSON:
        typer.echo(
            json.dumps(
                {
                    "file": str(input_path),
                    "pre_filter": band.upper() if band else None,
                    "channels": [r["channel"] for r in results],
                    "results": results,
                },
                indent=2,
            )
        )
        return
    typer.echo(f"File: {input_path}")
    typer.echo(f"Sample rate: {rate} Hz")
    if band:
        typer.echo(f"Pre-filter: {band.upper()}")
    for r in results:
        typer.echo(f"Channel {r['channel']}:")
        typer.echo(f"  Active speech level: {r['active_speech_level_db']:.2f} dB")
        typer.echo(f"  Activity factor:     {r['activity_factor'] * 100:.1f} %")
        typer.echo(f"  RMS level:           {r['rms_db']:.2f} dB")
        typer.echo(f"  DC level:            {r['dc_level']:+.6f}")
        typer.echo(f"  Peak positive:       {r['peak_positive']:.6f}")
        typer.echo(f"  Peak negative:       {r['peak_negative']:.6f}")
        typer.echo(f"  Peak abs:            {r['peak_abs']:.6f}")
        typer.echo(f"  Samples:             {r['sample_count']}")


@app.command(name="calibrate", context_settings={"ignore_unknown_options": True})
@app.command(name="scale", hidden=True, help="Alias for calibrate.", context_settings={"ignore_unknown_options": True})
def calibrate(
    input_path: InputPathArg,
    gain_db: GainDbArg,
    output_path: OutputPathArg = None,
    fs: FsCalibrateOption = None,
    band: PreFilterOption = None,
    time_start: TimeStartOption = 0.0,
    time_duration: TimeDurationOption = None,
    channels: ChannelsCalibrateOption = None,
) -> None:
    """Scale a WAV file by a dB gain (selected channels only)."""
    frames, info, selected = _read_selection(input_path, time_start, time_duration, channels)
    if band is not None and band.upper() not in {"NB", "SWB", "FB"}:
        raise typer.BadParameter(f"--pre-filter must be NB, SWB or FB, got {band!r}")
    gain = parse_db(gain_db)
    factor = 10.0 ** (gain / 20.0)
    rate, prefilter = _pipeline(info, fs, band)

    if rate == info.sample_rate:
        # same rate: scale (and optionally pre-filter) selected channels
        out = frames.copy()
        for c in selected:
            ch = out[:, c]
            if prefilter is not None:
                prefilter.reset()
                ch = np.asarray(prefilter.process(ch.astype(np.float32, copy=False)), dtype=np.float64)
            out[:, c] = ch * factor
    else:
        # rate change applies to the whole file: resample every channel
        # (unselected pass through the resampler unchanged, then the
        # selected ones are pre-filtered and scaled)
        out = _resampled_channels(frames, info.sample_rate, rate, list(range(info.channels)))
        for c in selected:
            ch = out[:, c]
            if prefilter is not None:
                prefilter.reset()
                ch = np.asarray(prefilter.process(ch.astype(np.float32, copy=False)), dtype=np.float64)
            out[:, c] = ch * factor

    dst = output_path if output_path is not None else input_path
    write_wav(
        dst,
        out,
        WavInfo(
            sample_rate=rate,
            channels=info.channels,
            bit_depth=info.bit_depth,
            is_float=info.is_float,
        ),
    )
    typer.echo(f"Calibrated {len(selected)} channel(s) by {gain:+.2f} dB -> {dst}")


def _read_selection(
    path: Path,
    time_start: float,
    time_duration: float | None,
    channels: str | None,
) -> tuple[np.ndarray, WavInfo, list[int]]:
    """Reads a WAV file applying time and channel selection.

    Returns `(frames, info, selected)` where `frames` is the full
    (time-selected) multi-channel array and `selected` holds 0-indexed
    selected channel indices.
    """
    frames, info = read_wav(path)
    n = len(frames)
    i0 = max(0, int(round(time_start * info.sample_rate)))
    if i0 >= n:
        msg = f"--time-start {time_start}s is beyond the end of file ({n} frames)"
        raise typer.BadParameter(msg)
    i1 = n
    if time_duration is not None:
        if time_duration < 0:
            raise typer.BadParameter(f"--time-duration must be >= 0, got {time_duration}")
        i1 = min(n, i0 + int(round(time_duration * info.sample_rate)))
    frames = frames[i0:i1]
    try:
        selected = parse_channels(channels, info.channels)
    except typer.BadParameter as exc:
        raise typer.BadParameter(str(exc)) from exc
    if selected is None:
        selected = list(range(info.channels))
    return frames, info, selected


def _pipeline(info: WavInfo, fs: int | None, band: str | None) -> tuple[int, PreFilter | None]:
    """Builds (processing rate, pre-filter) for the CLI options."""
    rate = fs if fs is not None else info.sample_rate
    if rate <= 0:
        raise typer.BadParameter(f"--fs must be positive, got {rate}")
    prefilter = PreFilter(band, float(rate)) if band else None
    return rate, prefilter


def _resampled_channels(frames: np.ndarray, source_rate: int, target_rate: int, selected: list[int]) -> np.ndarray:
    """Resamples the selected channels to `target_rate` and returns them
    as an `(n_out, len(selected))` float64 array.
    """
    if source_rate == target_rate:
        return frames[:, selected].copy()
    if Resampler is None:  # pragma: no cover - native extension not built
        raise typer.BadParameter("native extension not built; run `mise run rust-dev`")
    out_ch: list[np.ndarray] = []
    for c in selected:
        rs = Resampler(source_rate, target_rate)
        mono = frames[:, c].astype(np.float32, copy=False)
        acc = rs.process(mono)
        acc.extend(rs.flush())
        out_ch.append(np.asarray(acc, dtype=np.float64))
    return np.column_stack(out_ch)
