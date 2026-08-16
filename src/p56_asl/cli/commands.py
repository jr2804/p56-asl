"""CLI command implementations for Extended ITU-T Rec. P.56 - Active Speech Level (ASL)."""

from __future__ import annotations

import typer

from p56_asl.cli.app import app

# Default command (runs when no command provided)


@app.command()
def default() -> None:
    """Default command showing welcome message."""
    typer.echo("Welcome to Extended ITU-T Rec. P.56 - Active Speech Level (ASL)!")
    typer.echo("Use --help to see available commands.")
