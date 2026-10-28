"""Skeptic command-line interface."""

from typing import Annotated

import typer

from skeptic_agent import __version__

app = typer.Typer(add_completion=False, invoke_without_command=True)


@app.callback()
def main(
    version: Annotated[
        bool,
        typer.Option("--version", help="Print the version and exit."),
    ] = False,
) -> None:
    """Run the Skeptic command-line interface.

    Args:
        version: When true, print the package version and exit.
    """
    if version:
        typer.echo(__version__)
        raise typer.Exit
