"""Skeptic command-line interface."""

import asyncio
import json
import sys
from typing import Annotated

import typer

from skeptic_agent import __version__
from skeptic_agent.faults.catalog import FAULT_CLASSES, catalogue
from skeptic_agent.proxy.http import run_http_proxy
from skeptic_agent.proxy.stdio import StdioProxy

app = typer.Typer(add_completion=False, invoke_without_command=True)
proxy_app = typer.Typer(no_args_is_help=True)
faults_app = typer.Typer(no_args_is_help=True)
app.add_typer(proxy_app, name="proxy")
app.add_typer(faults_app, name="faults")

DEFAULT_LISTEN: str = "127.0.0.1:8765"
"""The default ``--listen`` of ``skeptic proxy http`` (S2)."""


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


@faults_app.command("list")
def faults_list(
    fault_class: Annotated[
        str | None,
        typer.Option("--class", help="Only show loud, silent or adversarial faults."),
    ] = None,
    as_json: Annotated[bool, typer.Option("--json", help="Print the catalogue as JSON.")] = False,
) -> None:
    """List the fault catalogue of S6 (S2).

    Args:
        fault_class: A fault class to filter by.
        as_json: When true, print one JSON array instead of a table.

    Raises:
        typer.Exit: With code 2 when ``fault_class`` is not a known class.
    """
    wanted = fault_class.lower() if fault_class is not None else None
    if wanted is not None and wanted not in FAULT_CLASSES:
        typer.echo(f"error: unknown fault class: {fault_class!r}", err=True)
        raise typer.Exit(code=2)
    entries = [entry for entry in catalogue() if wanted is None or entry["class"] == wanted]
    if as_json:
        typer.echo(json.dumps(entries, ensure_ascii=False, indent=2))
        return
    for entry in entries:
        typer.echo(
            f"{entry['id']}  {entry['class']:<11}  {entry['name']:<24}  "
            f"{entry['persistence']:<11}  {entry['target']}"
        )


@proxy_app.command("stdio", context_settings={"allow_extra_args": True})
def proxy_stdio(
    ctx: typer.Context,
    config: Annotated[str | None, typer.Option("--config", help="Config file path.")] = None,
    profile: Annotated[
        str | None, typer.Option("--profile", help="Fault profile id or path.")
    ] = None,
    guards: Annotated[
        str | None, typer.Option("--guards", help="Guard list or preset name.")
    ] = None,
    record: Annotated[
        str | None, typer.Option("--record", help="Cassette output directory.")
    ] = None,
    seed: Annotated[int, typer.Option("--seed", help="Episode seed.")] = 0,
    episode_id: Annotated[
        str | None, typer.Option("--episode-id", help="Episode identifier.")
    ] = None,
    scenario: Annotated[str | None, typer.Option("--scenario", help="Scenario file.")] = None,
    state_file: Annotated[str | None, typer.Option("--state-file", help="State file path.")] = None,
) -> None:
    """Run the stdio proxy in front of an upstream MCP server.

    Everything after ``--`` is the upstream command.

    Args:
        ctx: The Typer context; ``ctx.args`` holds the upstream command.
        config: Config file path.
        profile: Fault profile id or path.
        guards: Guard list or preset name.
        record: Cassette output directory.
        seed: Episode seed.
        episode_id: Episode identifier.
        scenario: Scenario file.
        state_file: State file path.

    Raises:
        typer.Exit: With the upstream's exit code.
    """
    del config, profile, guards, record, scenario, state_file
    command = list(ctx.args)
    if "--" in sys.argv:
        command = sys.argv[sys.argv.index("--") + 1 :]
    if command and command[0] == "--":
        command = command[1:]
    if not command:
        typer.echo("error: missing upstream command after --", err=True)
        raise typer.Exit(code=2)
    proxy = StdioProxy(command, episode_id=episode_id or "stdio", seed=seed)
    raise typer.Exit(code=asyncio.run(proxy.run()))


@proxy_app.command("http")
def proxy_http(
    upstream: Annotated[str, typer.Option("--upstream", help="Upstream MCP endpoint URL.")],
    listen: Annotated[
        str, typer.Option("--listen", help="Listen address as HOST:PORT.")
    ] = DEFAULT_LISTEN,
    config: Annotated[str | None, typer.Option("--config", help="Config file path.")] = None,
    profile: Annotated[
        str | None, typer.Option("--profile", help="Fault profile id or path.")
    ] = None,
    guards: Annotated[
        str | None, typer.Option("--guards", help="Guard list or preset name.")
    ] = None,
    record: Annotated[
        str | None, typer.Option("--record", help="Cassette output directory.")
    ] = None,
    seed: Annotated[int, typer.Option("--seed", help="Episode seed.")] = 0,
    episode_id: Annotated[
        str | None, typer.Option("--episode-id", help="Episode identifier.")
    ] = None,
    scenario: Annotated[str | None, typer.Option("--scenario", help="Scenario file.")] = None,
    state_file: Annotated[str | None, typer.Option("--state-file", help="State file path.")] = None,
) -> None:
    """Run the streamable HTTP proxy in front of an upstream MCP endpoint (S2, S4.1).

    Args:
        upstream: The upstream MCP endpoint URL.
        listen: The listen address as ``HOST:PORT``.
        config: Config file path.
        profile: Fault profile id or path.
        guards: Guard list or preset name.
        record: Cassette output directory.
        seed: Episode seed.
        episode_id: Episode identifier.
        scenario: Scenario file.
        state_file: State file path.

    Raises:
        typer.Exit: With code 2 when ``listen`` is not ``HOST:PORT``.
    """
    del config, profile, guards, record, scenario, state_file
    host, port = parse_listen(listen)
    run_http_proxy(
        upstream,
        host=host,
        port=port,
        episode_id=episode_id or "http",
        seed=seed,
    )


def parse_listen(value: str) -> tuple[str, int]:
    """Split a ``HOST:PORT`` option value.

    Args:
        value: The ``--listen`` value.

    Returns:
        The host and the port.

    Raises:
        typer.BadParameter: When the value has no port or no host.
    """
    host, separator, port = value.rpartition(":")
    if not separator or not host:
        raise typer.BadParameter(f"expected HOST:PORT, got {value!r}")
    try:
        number = int(port)
    except ValueError:
        raise typer.BadParameter(f"expected a numeric port, got {port!r}") from None
    if not 0 < number < 65536:
        raise typer.BadParameter(f"port out of range: {number}")
    return host, number


if __name__ == "__main__":
    app()
