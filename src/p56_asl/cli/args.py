"""CLI arguments, options, and flags for Extended ITU-T Rec. P.56 - Active Speech Level (ASL)."""

from __future__ import annotations

import re
from enum import StrEnum

import typer

# Application name for environment variables
APP_NAME_UPPERCASE = "P56_ASL"


class OutputFormat(StrEnum):
    """Output format for `measure`."""

    TEXT = "text"
    JSON = "json"


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
