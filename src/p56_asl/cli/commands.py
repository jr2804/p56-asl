"""CLI command implementations for Extended ITU-T Rec. P.56 - Active Speech Level (ASL)."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any

import numpy as np
import soundfile as sf
import typer

from p56_asl import ActiveSpeechLevelMeter, PreFilter, Resampler
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
    SubtypeOption,
    TimeDurationOption,
    TimeStartOption,
    parse_channels,
    parse_db,
)

_BLOCK = 65_536
_METER_BLOCK = 256
_CLIPPING_SUBTYPES = frozenset({"PCM_8", "PCM_16", "PCM_24", "PCM_32"})


def register(app: typer.Typer) -> None:
    """Register the CLI commands on `app` (called from app.py after `app` exists)."""
    app.command(name="measure")(measure)
    app.command(name="calc", hidden=True, help="Alias for measure.")(measure)
    app.command(name="calculate", hidden=True, help="Alias for measure.")(measure)
    app.command(name="calibrate", context_settings={"ignore_unknown_options": True})(calibrate)
    app.command(
        name="scale",
        hidden=True,
        help="Alias for calibrate.",
        context_settings={"ignore_unknown_options": True},
    )(calibrate)


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
    info = _sf_info(input_path)
    rate, _ = _pipeline(info.samplerate, fs, band)
    selected = _selected(channels, info.channels)
    src_rate = int(info.samplerate)

    results: list[dict[str, Any]] = []
    for c in selected:
        meter = ActiveSpeechLevelMeter(sample_rate=float(rate))  # noqa: ARG001
        prefilter = PreFilter(band, float(rate)) if band else None
        rs = _new_resampler(src_rate, rate) if src_rate != rate else None
        n_processed: int = 0
        try:
            for raw in _iter_channel(input_path, info, c, time_start, time_duration):
                block = np.asarray(rs.process(raw), dtype=np.float32) if rs is not None else raw
                if prefilter is not None:
                    block = np.asarray(prefilter.process(block), dtype=np.float32)
                n_processed += len(block)
                for i in range(0, len(block), _METER_BLOCK):
                    meter.process_block(block[i : i + _METER_BLOCK])
            if rs is not None:
                tail = np.asarray(rs.flush(), dtype=np.float32)
                if tail.size:
                    if prefilter is not None:
                        tail = np.asarray(prefilter.process(tail), dtype=np.float32)
                    n_processed += len(tail)
                    for i in range(0, len(tail), _METER_BLOCK):
                        meter.process_block(tail[i : i + _METER_BLOCK])
        except (sf.LibsndfileError, OSError) as exc:  # pragma: no cover
            raise typer.BadParameter(f"could not read {input_path}: {exc}") from exc
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
                "sample_count": n_processed,
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
        typer.echo(f"  Peak positive:       {r['peak_positive']:+.6f}")
        typer.echo(f"  Peak negative:       {r['peak_negative']:+.6f}")
        typer.echo(f"  Peak abs:            {r['peak_abs']:+.6f}")
        typer.echo(f"  Samples:             {r['sample_count']}")


def calibrate(
    input_path: InputPathArg,
    gain_db: GainDbArg,
    output_path: OutputPathArg = None,
    fs: FsCalibrateOption = None,
    band: PreFilterOption = None,
    time_start: TimeStartOption = 0.0,
    time_duration: TimeDurationOption = None,
    channels: ChannelsCalibrateOption = None,
    subtype: SubtypeOption = None,
) -> None:
    """Scale a WAV file by a dB gain (selected channels only)."""
    info = _sf_info(input_path)
    gain = parse_db(gain_db)
    factor = 10.0 ** (gain / 20.0)
    rate, _ = _pipeline(info.samplerate, fs, band)
    selected = _selected(channels, info.channels)
    dst_subtype = subtype if subtype is not None else info.subtype
    dst = output_path if output_path is not None else input_path
    try:
        _stream_calibrate(
            input_path,
            dst,
            info,
            rate,
            selected,
            band,
            factor,
            time_start,
            time_duration,
            dst_subtype,
        )
    except (sf.LibsndfileError, OSError, ValueError) as e:  # pragma: no cover
        raise typer.BadParameter(f"could not write {dst}: {e}") from e
    if dst_subtype in _CLIPPING_SUBTYPES:
        _warn_if_clipping(dst)
    typer.echo(f"Calibrated {len(selected)} channel(s) by {gain:+.2f} dB -> {dst}")


def _sf_info(path: Path) -> Any:
    try:
        return sf.info(path)
    except (sf.LibsndfileError, OSError) as exc:  # pragma: no cover
        raise typer.BadParameter(f"could not read {path}: {exc}") from exc


def _selected(channels: str | None, n: int) -> list[int]:
    try:
        sel = parse_channels(channels, n)
    except typer.BadParameter as e:  # pragma: no cover
        raise typer.BadParameter(str(e)) from e
    return sel if sel is not None else list(range(n))


def _pipeline(source_rate: int, fs: int | None, band: str | None) -> tuple[int, PreFilter | None]:
    if band is not None and band.upper() not in {"NB", "SWB", "FB"}:
        raise typer.BadParameter(f"--pre-filter must be NB, SWB or FB, got {band!r}")
    rate = fs if fs is not None else source_rate
    if rate <= 0:
        raise typer.BadParameter(f"--fs must be positive, got {rate}")  # pragma: no cover  # pragma: no cover
    return rate, PreFilter(band, float(rate)) if band else None


def _iter_channel(path: Path, info: Any, channel: int, time_start: float, time_duration: float | None) -> Any:
    start, leftover = _window(info, time_start, time_duration)
    with sf.SoundFile(path) as src:
        src.seek(start)
        while leftover > 0:
            frames = src.read(min(_BLOCK, leftover), always_2d=True, dtype="float32")
            if frames.size == 0:  # pragma: no cover
                return
            leftover -= len(frames)
            yield np.ascontiguousarray(frames[:, channel], dtype=np.float32)


def _stream_calibrate(
    src_path: Path,
    dst_path: Path,
    info: Any,
    rate: int,
    selected: list[int],
    band: str | None,
    factor: float,
    time_start: float,
    time_duration: float | None,
    dst_subtype: str,
) -> None:
    src_rate = int(info.samplerate)
    n_ch = info.channels
    resample = src_rate != rate
    if resample and Resampler is None:  # pragma: no cover
        raise typer.BadParameter("native extension not built; run `mise run rust-dev`")
    resamplers = [_new_resampler(src_rate, rate) for _ in range(n_ch)] if resample else []
    prefilters = {c: PreFilter(band, float(rate)) for c in selected} if band else {}

    fd, tmp_name = tempfile.mkstemp(suffix=".wav", dir=dst_path.parent)
    os.close(fd)
    tmp = Path(tmp_name)
    try:
        with sf.SoundFile(str(tmp), "w", samplerate=rate, channels=n_ch, subtype=dst_subtype) as dst:
            for block in _iter_all(src_path, info, time_start, time_duration):
                if resample:
                    cols = [np.asarray(resamplers[c].process(block[:, c].astype(np.float32, copy=False)), dtype=np.float64) for c in range(n_ch)]
                    # rubato can emit different lengths per channel if states drift; pad to max.
                    n = max((len(x) for x in cols), default=0)
                    if n == 0:  # pragma: no cover
                        continue
                    out = np.zeros((n, n_ch), dtype=np.float64)
                    for c, col in enumerate(cols):
                        out[: len(col), c] = col
                else:
                    out = block.copy()
                for c in selected:
                    ch = out[:, c]
                    pf = prefilters.get(c)
                    if pf is not None:
                        ch = np.asarray(pf.process(ch.astype(np.float32, copy=False)), dtype=np.float64)
                    out[:, c] = ch * factor
                dst.write(out)
            if resample:
                tails = [np.asarray(rs.flush(), dtype=np.float64) for rs in resamplers]
                n = max((len(t) for t in tails), default=0)
                if n:
                    out = np.zeros((n, n_ch), dtype=np.float64)
                    for c, t in enumerate(tails):
                        out[: len(t), c] = t
                    for c in selected:
                        ch = out[:, c]
                        pf = prefilters.get(c)
                        if pf is not None:
                            ch = np.asarray(pf.process(ch.astype(np.float32, copy=False)), dtype=np.float64)
                        out[:, c] = ch * factor
                    dst.write(out)
        tmp.replace(dst_path)
    except Exception:
        tmp.unlink(missing_ok=True)
        raise


def _new_resampler(src_rate: int, dst_rate: int) -> Any:
    """Constructs a resampler; clear error when the native build is missing."""
    if Resampler is None:  # pragma: no cover
        raise typer.BadParameter("native extension not built; run `mise run rust-dev`")
    return Resampler(src_rate, dst_rate)


def _iter_all(path: Path, info: Any, time_start: float, time_duration: float | None) -> Any:
    start, leftover = _window(info, time_start, time_duration)
    with sf.SoundFile(path) as src:
        src.seek(start)
        while leftover > 0:
            frames = src.read(min(_BLOCK, leftover), always_2d=True, dtype="float64")
            if frames.size == 0:  # pragma: no cover
                return
            leftover -= len(frames)
            yield np.ascontiguousarray(frames, dtype=np.float64)


def _window(info: Any, time_start: float, time_duration: float | None) -> tuple[int, int]:
    src_rate = int(info.samplerate)
    start = max(0, int(round(time_start * src_rate)))
    if start >= info.frames:
        raise typer.BadParameter(f"--time-start {time_start}s is beyond the end of file ({info.frames} frames)")
    remaining = info.frames - start
    if time_duration is not None:
        remaining = min(remaining, int(round(time_duration * src_rate)))
    return start, remaining


def _warn_if_clipping(path: Path) -> None:
    data, _ = sf.read(path, always_2d=True, dtype="float64")
    peak = float(np.max(np.abs(data)))
    if peak >= 1.0:
        typer.echo(f"warning: {path.name}: clipping in output (peak {peak:.4f} >= 1.0)", err=True)
