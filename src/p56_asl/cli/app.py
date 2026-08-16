"""Typer CLI app for Extended ITU-T Rec. P.56 - Active Speech Level (ASL)."""

from __future__ import annotations

from importlib.metadata import version

import typer

_DESC = (
    "An extended version of the ITU-T Rec. P.56 Active Speech Level (ASL). "
    "Complies with reference C-implementation but re-implemented in Rust and MIT-licensed."
)

app = typer.Typer(
    name="p56_asl",
    help=_DESC,
    add_completion=True,
    no_args_is_help=True,
)

# Import commands after `app` exists to register them (import at module
# top would create a circular import: commands imports app from here).
from p56_asl.cli import commands  # noqa: E402, F401


@app.callback(invoke_without_command=True)
def _callback(
    version: bool = typer.Option(
        False,
        "--version",
        "-v",
        help="Show version and exit",
        is_eager=True,
    ),
) -> None:
    """Show version and exit."""
    if version:
        typer.echo(_get_version())
        raise typer.Exit()


# Version management
def _get_version() -> str:
    """Get application version from package metadata."""
    try:
        return version("p56_asl")
    except Exception:
        return "0.0.0"  # Fallback for development mode


def main() -> None:
    """Entry point for the CLI application."""
    app()
