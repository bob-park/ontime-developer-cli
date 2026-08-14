from __future__ import annotations

import typer

app = typer.Typer(help="OnTime Developer CLI", no_args_is_help=True)


@app.callback()
def main() -> None:
    """OnTime Developer CLI."""


def run() -> None:
    app()
