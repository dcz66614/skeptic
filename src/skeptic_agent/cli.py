"""Skeptic command-line interface."""

import asyncio
import importlib
import json
import os
import sys
from pathlib import Path
from typing import Annotated, Any

import typer

from skeptic_agent import __version__
from skeptic_agent.faults.catalog import FAULT_CLASSES, catalogue
from skeptic_agent.proxy.http import run_http_proxy
from skeptic_agent.proxy.pipeline import FaultStage, new_pipeline
from skeptic_agent.proxy.stdio import StdioProxy
from skeptic_agent.record.replay import (
    ON_MISS_ERROR,
    ON_MISS_LIVE,
    ON_MISS_VALUES,
    Cassette,
    ReplayError,
    ReplayServer,
)

app = typer.Typer(add_completion=False, invoke_without_command=True)
proxy_app = typer.Typer(no_args_is_help=True)
faults_app = typer.Typer(no_args_is_help=True)
sandbox_app = typer.Typer(no_args_is_help=True)
scenario_app = typer.Typer(no_args_is_help=True)
app.add_typer(proxy_app, name="proxy")
app.add_typer(faults_app, name="faults")
app.add_typer(sandbox_app, name="sandbox")
app.add_typer(scenario_app, name="scenario")

DEFAULT_LISTEN: str = "127.0.0.1:8765"
"""The default ``--listen`` of ``skeptic proxy http`` (S2)."""

SANDBOXES = {
    "weather": "sb_weather",
    "fx": "sb_fx",
    "stocks": "sb_stocks",
    "crm": "sb_crm",
    "orders": "sb_orders",
    "calendar": "sb_calendar",
    "docs": "sb_docs",
    "sqlshop": "sb_sqlshop",
    "mail": "sb_mail",
    "files": "sb_files",
}
"""The built-in sandboxes ``skeptic sandbox run`` can start (S2, S9.2).

S31 adds ``weather`` and ``fx``; S32 adds ``stocks`` and ``crm``; S33 adds
``orders`` and ``calendar``; S34 adds ``docs`` and ``sqlshop``; S35 adds
``mail`` and ``files``.
"""


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


@sandbox_app.command("run", context_settings={"allow_extra_args": True})
def sandbox_run(
    ctx: typer.Context,
    name: str = typer.Argument(help="The built-in sandbox name, for example 'weather'."),
) -> None:
    """Start a built-in sandbox over stdio (S2, S9.1 item 2).

    Everything after ``--`` is passed to the sandbox module, so
    ``skeptic sandbox run weather -- --http 127.0.0.1:8766`` serves Streamable
    HTTP and ``--state-file PATH`` sets the state file.

    Args:
        ctx: The Typer context; ``ctx.args`` holds the sandbox's arguments.
        name: The sandbox name from :data:`SANDBOXES`.

    Raises:
        typer.Exit: With code 2 on an unknown name or a sandbox usage error,
            otherwise with the sandbox module's own exit code.
    """
    module = SANDBOXES.get(name)
    if module is None:
        known = ", ".join(sorted(SANDBOXES))
        typer.echo(f"error: unknown sandbox {name!r}; choose one of {known}", err=True)
        raise typer.Exit(code=2)
    command = list(ctx.args)
    if "--" in sys.argv:
        command = sys.argv[sys.argv.index("--") + 1 :]
    if command and command[0] == "--":
        command = command[1:]
    try:
        package = importlib.import_module(f"skeptic_agent.sandboxes.{module}.server")
    except ImportError as error:
        typer.echo(f"error: cannot load sandbox {name!r}: {error}", err=True)
        raise typer.Exit(code=2) from error
    sys.argv = [f"skeptic sandbox run {name}", *command]
    try:
        package.main()
    except SystemExit as exit_info:
        code = exit_info.code if isinstance(exit_info.code, int) else 0
        raise typer.Exit(code=code) from exit_info


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
    del config, guards, record
    command = list(ctx.args)
    if "--" in sys.argv:
        command = sys.argv[sys.argv.index("--") + 1 :]
    if command and command[0] == "--":
        command = command[1:]
    if not command:
        typer.echo("error: missing upstream command after --", err=True)
        raise typer.Exit(code=2)

    scenario_dict: dict[str, Any] | None = None
    if scenario:
        from skeptic_agent.scenario.model import load_scenario

        try:
            scenario_obj = load_scenario(scenario)
            scenario_dict = scenario_obj.to_dict()
        except Exception as exc:
            typer.echo(f"error loading scenario {scenario!r}: {exc}", err=True)
            raise typer.Exit(code=3) from exc

    fault_stage: FaultStage
    if profile and profile.lower() != "none":
        from skeptic_agent.faults.base import FaultSpec
        from skeptic_agent.faults.engine import FaultEngine, load_profile_source, spec_from_entry

        cat_entry = next((e for e in catalogue() if e["id"] == profile), None)
        if cat_entry is not None:
            target = "$primary"
            if profile == "S09":
                target = "$conflict_b"
            elif profile == "S10":
                target = "$write"
            spec = FaultSpec(
                fault_id=profile,
                tool=target,
                call_index=1,
                probability=1.0,
                persistence=cat_entry["persistence"],
                params=dict(cat_entry["params"]),
            )
            fault_stage = FaultEngine([spec], scenario=scenario_dict)
        else:
            try:
                prof = load_profile_source(profile)
                specs = [spec_from_entry(e) for e in prof.faults]
                fault_stage = FaultEngine(specs, scenario=scenario_dict)
            except Exception as exc:
                typer.echo(f"error loading profile {profile!r}: {exc}", err=True)
                raise typer.Exit(code=3) from exc
    elif scenario_dict is not None:
        from skeptic_agent.faults.engine import FaultEngine

        fault_stage = FaultEngine([], scenario=scenario_dict)
    else:
        fault_stage = FaultStage()

    if state_file:
        os.environ["SKEPTIC_STATE_FILE"] = state_file

    pipeline = new_pipeline(fault=fault_stage)
    proxy = StdioProxy(command, pipeline=pipeline, episode_id=episode_id or "stdio", seed=seed)
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


@app.command("replay", context_settings={"allow_extra_args": True})
def replay(
    ctx: typer.Context,
    cassette: Annotated[str, typer.Option("--cassette", help="Cassette file to replay.")],
    on_miss: Annotated[
        str,
        typer.Option("--on-miss", help="Answer a match miss with 'error' or send it 'live'."),
    ] = ON_MISS_ERROR,
) -> None:
    """Serve a cassette as a stdio MCP server (S2).

    Everything after ``--`` is the live upstream command; ``--on-miss live``
    requires it. A match miss is answered with a JSON-RPC error otherwise.

    Args:
        ctx: The Typer context; ``ctx.args`` holds the live command.
        cassette: The cassette file to replay.
        on_miss: ``error`` or ``live``.

    Raises:
        typer.Exit: With code 2 on a usage error, 3 on an invalid cassette or a
            failed live upstream start.
    """
    if on_miss not in ON_MISS_VALUES:
        typer.echo(f"error: --on-miss must be one of {', '.join(ON_MISS_VALUES)}", err=True)
        raise typer.Exit(code=2)
    command = list(ctx.args)
    if "--" in sys.argv:
        command = sys.argv[sys.argv.index("--") + 1 :]
    if command and command[0] == "--":
        command = command[1:]
    if on_miss == ON_MISS_LIVE and not command:
        typer.echo("error: --on-miss live needs an upstream command after --", err=True)
        raise typer.Exit(code=2)
    try:
        loaded = Cassette.load(Path(cassette))
    except ReplayError as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(code=3) from exc
    server = ReplayServer(
        loaded,
        on_miss=on_miss,
        live_command=command if on_miss == ON_MISS_LIVE else None,
    )
    raise typer.Exit(code=asyncio.run(server.run()))


@scenario_app.command("validate")
def scenario_validate(
    paths: Annotated[
        list[str],
        typer.Argument(help="Scenario file or directory paths to validate."),
    ],
    as_json: Annotated[
        bool,
        typer.Option("--json", help="Print the validation report as JSON."),
    ] = False,
) -> None:
    """Validate scenario documents against schema and S8.4 semantic rules (S2, S8.4).

    Args:
        paths: File or directory paths to validate.
        as_json: Whether to print results as JSON.

    Raises:
        typer.Exit: With code 0 when valid, 2 on usage/IO error, 3 when validation fails.
    """
    from skeptic_agent.scenario.validate import validate_paths

    report = validate_paths(paths)
    if as_json:
        payload = {
            "valid": report.valid,
            "scenario_count": report.scenario_count,
            "errors": [
                {
                    "rule": err.rule,
                    "message": err.message,
                    "scenario_id": err.scenario_id,
                    "path": err.path,
                }
                for err in report.errors
            ],
        }
        typer.echo(json.dumps(payload, ensure_ascii=False, indent=2))
        raise typer.Exit(code=0 if report.valid else 3)

    if report.scenario_count == 0:
        typer.echo("error: no scenario files found in the provided paths", err=True)
        raise typer.Exit(code=2)

    if report.valid:
        typer.echo(f"PASS: {report.scenario_count} scenario(s) passed validation.")
        raise typer.Exit(code=0)

    typer.echo(
        f"FAIL: {len(report.errors)} error(s) found in {report.scenario_count} scenario(s):",
        err=True,
    )
    for err in report.errors:
        loc = f"[{err.path}] " if err.path else ""
        rule_tag = f"[Rule {err.rule}]" if isinstance(err.rule, int) else f"[{err.rule}]"
        typer.echo(f"  {loc}{rule_tag} {err.message}", err=True)
    raise typer.Exit(code=3)


@scenario_app.command("oracle")
def scenario_oracle(
    paths: Annotated[
        list[str],
        typer.Argument(help="Scenario file or directory paths to execute."),
    ],
    faults: Annotated[
        str,
        typer.Option(
            "--faults",
            help="Faults to evaluate: 'none', 'all', or comma-separated fault IDs.",
        ),
    ] = "none",
    write_recoverability: Annotated[
        str | None,
        typer.Option(
            "--write-recoverability",
            help="Path to write recoverability cache JSON.",
        ),
    ] = None,
    seed: Annotated[
        int,
        typer.Option("--seed", help="Episode seed for fault RNG."),
    ] = 0,
) -> None:
    """Execute scripted Oracle client and evaluate recoverability (S2, S8.3).

    Args:
        paths: Scenario files or directories.
        faults: 'none', 'all', or comma-separated list of IDs (e.g. 'S04').
        write_recoverability: Destination file for recoverability cache.
        seed: Random seed.

    Raises:
        typer.Exit: With code 0 when successful, 1 when clean Oracle run fails, 2 on usage error.
    """
    from skeptic_agent.scenario.model import load_scenario
    from skeptic_agent.scenario.oracle import run_oracle
    from skeptic_agent.scenario.recoverability import (
        RecoverabilityCache,
        load_recoverability,
        save_recoverability,
    )

    scenario_files: list[Path] = []
    for p in paths:
        path_obj = Path(p)
        if path_obj.is_dir():
            scenario_files.extend(sorted(path_obj.glob("**/*.yaml")))
            scenario_files.extend(sorted(path_obj.glob("**/*.yml")))
        elif path_obj.is_file():
            scenario_files.append(path_obj)
        else:
            typer.echo(f"error: path not found: {p}", err=True)
            raise typer.Exit(code=2)

    if not scenario_files:
        typer.echo("error: no scenario files found", err=True)
        raise typer.Exit(code=2)

    fault_list: list[str | None]
    if faults.strip().lower() == "none":
        fault_list = [None]
    elif faults.strip().lower() == "all":
        fault_list = [entry["id"] for entry in catalogue()]
    else:
        fault_list = [f.strip() for f in faults.split(",") if f.strip()]

    cache: RecoverabilityCache = {}
    if write_recoverability and Path(write_recoverability).is_file():
        cache = load_recoverability(write_recoverability)

    clean_mode = fault_list == [None]
    clean_failed = False

    for file_path in scenario_files:
        try:
            scenario = load_scenario(file_path)
        except Exception as exc:
            typer.echo(f"error loading scenario {file_path}: {exc}", err=True)
            raise typer.Exit(code=2) from exc

        if scenario.id not in cache:
            cache[scenario.id] = {}

        for fault_item in fault_list:
            tag = fault_item or "none"
            result = run_oracle(scenario, fault=fault_item, seed=seed)
            if clean_mode:
                if result.success:
                    typer.echo(f"{scenario.id}: PASS")
                else:
                    err_msg = result.step_results[-1].error if result.step_results else "unknown"
                    typer.echo(f"{scenario.id}: FAIL ({err_msg})", err=True)
                    clean_failed = True
            else:
                cache[scenario.id][tag] = result.recoverability
                typer.echo(f"{scenario.id} [{tag}]: {result.recoverability}")

    if write_recoverability:
        save_recoverability(cache, write_recoverability)
        typer.echo(f"Wrote recoverability cache to {write_recoverability}")

    if clean_mode and clean_failed:
        raise typer.Exit(code=1)

    raise typer.Exit(code=0)


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
