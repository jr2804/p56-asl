"""CLI arguments, options, and flags for Extended ITU-T Rec. P.56 - Active Speech Level (ASL)."""

from __future__ import annotations

import re
from enum import StrEnum
from pathlib import Path
from typing import Annotated

import typer

# Application name for environment variables
APP_NAME_UPPERCASE = "P56_ASL"


# --- Typer parameter type aliases (single source of truth for commands.py) ---

InputPathArg = Annotated[Path, typer.Argument(help="Input WAV file.", exists=True, readable=True)]
GainDbArg = Annotated[str, typer.Argument(help="Gain in dB, e.g. 3.01, +3.01 or -3.01 (no sign = +).")]
OutputPathArg = Annotated[Path | None, typer.Argument(help="Output WAV file; omitted: calibrate in place.")]
FsOption = Annotated[
    int | None,
    typer.Option("--fs", min=1, help="Resample to this sampling rate (Hz) before analysis."),
]
FsCalibrateOption = Annotated[
    int | None,
    typer.Option("--fs", min=1, help="Resample to this sampling rate (Hz) before calibration and writing."),
]
PreFilterOption = Annotated[
    str | None,
    typer.Option("--pre-filter", case_sensitive=False, help="P.56 protection pre-filter band: NB, SWB or FB."),
]
TimeStartOption = Annotated[float, typer.Option("--time-start", min=0.0, help="Start time (s).")]
TimeDurationOption = Annotated[
    float | None,
    typer.Option("--time-duration", min=0.0, help="Duration (s); default: to EOF."),
]
ChannelsOption = Annotated[
    str | None,
    typer.Option("--channels", help="Channels to analyze: 1-indexed int or comma list (e.g. 1,2). Default: all."),
]
ChannelsCalibrateOption = Annotated[
    str | None,
    typer.Option(
        "--channels",
        help="Channels to calibrate: 1-indexed int or comma list. Unselected channels are copied unchanged. Default: all.",
    ),
]


class OutputFormat(StrEnum):
    """Output format for `measure`."""

    TEXT = "text"
    JSON = "json"


OutputFormatOption = Annotated[OutputFormat, typer.Option("--format", "-f", help="Output format.")]


def parse_channels(value: str | None, max_channels: int) -> list[int] | None:
    """Parses a 1-indexed channel selection.

    Accepts a single integer (`"2"`) or a comma-separated list
    (`"1,2"`, `"2, 4"`); blanks around separators are tolerated.
    Returns `None` (all channels) or a sorted, de-duplicated list of
    0-indexed channel indices.

    Raises `typer.BadParameter` on syntax or range errors.
    """
    if value is None or not value.strip():
        return None
    parts = [p.strip() for p in value.split(",")]
    if any(not p for p in parts):
        raise typer.BadParameter(f"empty channel element in {value!r}")
    if any(not re.fullmatch(r"\d+", p) for p in parts):
        raise typer.BadParameter(f"channel indices must be integers, got {value!r}")
    idx = sorted({int(p) for p in parts})
    for i in idx:
        if not 1 <= i <= max_channels:
            raise typer.BadParameter(f"channel {i} out of range 1..{max_channels} (1-indexed)")
    return [i - 1 for i in idx]


def parse_db(value: str) -> float:
    """Parses a dB gain like `3.01`, `+3.01`, `-3.01` or `+0`.

    A missing sign means `+`. Raises `typer.BadParameter` on garbage.
    """
    v = value.strip()
    if not re.fullmatch(r"[+-]?(\d+\.?\d*|\.\d+)([eE][+-]?\d+)?", v):
        raise typer.BadParameter(f"invalid dB value {value!r}")
    return float(v)
