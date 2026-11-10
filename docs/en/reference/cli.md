# CLI

The entry point is `skeptic` (`skeptic_agent.cli:app`). Global flag: `--version`, which prints the package version and exits 0.

Agent specs used by `run` have the form `<adapter>:<model>`.

| Adapter | Model |
|---|---|
| `reference` | `openrouter/<vendor>/<model>`, `openai/<model>`, `compat/<model>`, or `fake/<script>` |
| `openai-agents`, `langgraph`, `crewai`, `pydantic-ai` | the same model forms; each needs its extra installed |
| `command` | `command:<preset>`, where `preset` selects `agents.<preset>.cmd` |

FakeLLM scripts shipped for tests: `fake/oracle_follower`, `fake/gullible`, `fake/honest`, `fake/looper`. They do not call the network.

## Commands

| Command | Role |
|---|---|
| `skeptic init` | Discover MCP client configs and write `skeptic.yaml` |
| `skeptic wrap FILE` | Point selected servers at `skeptic proxy`, or restore the backup |
| `skeptic proxy stdio` | Stdio proxy in front of an upstream command |
| `skeptic proxy http` | Streamable HTTP proxy |
| `skeptic replay` | Serve a cassette as a stdio server |
| `skeptic faults list` | Print the fault catalogue |
| `skeptic sandbox run NAME` | Start a built-in sandbox |
| `skeptic scenario validate PATHS` | Schema and semantic checks |
| `skeptic scenario oracle PATHS` | Run the scripted oracle |
| `skeptic run` | Expand episodes, run them, write `results.jsonl` and `summary.json` |
| `skeptic bench run` | Run a matrix file |
| `skeptic report RUN_DIR` | Write the six report formats |
| `skeptic compare RUN_A RUN_B` | Metric deltas and confidence intervals |
| `skeptic gate RUN_DIR` | Threshold check |
| `skeptic mcp serve` | MCP server mode |

### `skeptic init`

`--path DIR` (default `.`), `--yes` (overwrite `skeptic.yaml`), `--dry-run`, `--json`. `--dry-run --json` prints the discovery and does not write the file. Exit 1 when no server is found. Exit 2 when the file exists and `--yes` was not passed.

### `skeptic wrap FILE`

`--server NAME` (repeatable) or `--all`, `--profile ID` (default `silent-core`), `--guards LIST`, `--undo`. The original file is copied to `FILE.skeptic.bak` before the first wrap. `--undo` restores that backup byte for byte and then deletes it. You must pass `--all` or at least one `--server`.

### `skeptic proxy stdio`

`skeptic proxy stdio [options] -- COMMAND [ARGS...]`. Options: `--config FILE`, `--profile ID-or-path`, `--guards LIST-or-preset`, `--record DIR`, `--seed INT` (default 0), `--episode-id STR`, `--scenario FILE`, `--state-file PATH`. The command after `--` is required.

### `skeptic proxy http`

`--upstream URL` is required. `--listen HOST:PORT` defaults to `127.0.0.1:8765`. The other proxy options match stdio.

### `skeptic replay`

`--cassette FILE`, `--on-miss error|live`. `live` requires an upstream command after `--`.

### `skeptic faults list`

`--class loud|silent|adversarial`, `--json`. An unknown class exits 2.

### `skeptic sandbox run NAME`

Default transport is stdio. Arguments after `--` go to the sandbox, including `--http HOST:PORT` and `--state-file PATH`. Names are the built-in sandboxes: `weather`, `fx`, `stocks`, `crm`, `orders`, `calendar`, `docs`, `sqlshop`, `mail`, `files`.

### `skeptic scenario validate PATHS`

`--json`. Exit 0 when every file passes, 3 when validation fails, 2 when no scenario file is found.

### `skeptic scenario oracle PATHS`

`--faults none|all|ID,ID`, `--write-recoverability FILE`, `--seed INT` (default 0). Exit 1 when the clean oracle fails.

### `skeptic run`

`--suite NAME` or repeatable `--scenario PATH`. `--agent SPEC` (default `reference:fake/oracle_follower`). `--profile ID` (default `silent-core`). `--guards LIST-or-preset` (default `none`). `--prompt-variant plain|evidence_contract` (default `plain`). `--seeds 1,2,3` (default `1`). `--concurrency N` (default 4). `--max-cost-usd F`. `--out DIR` (default `runs/<run_id>`). `--resume`. `--ledger PATH`.

The run id looks like `20261105-142233-a1b2c3` (UTC timestamp plus 6 hex characters). Hitting the budget stops new episodes and exits 5. Results already finished are kept.

### `skeptic bench run`

`--matrix FILE`, `--resume`, `--max-cost-usd F`, `--concurrency N`, `--out DIR`, `--ledger PATH`, `--dry-run`, `--count`. `--count` prints the episode total and exits. `--dry-run` prints the expanded config and the same total.

### `skeptic report RUN_DIR`

`--format html,md,json,junit,sarif,badge` (that is the default; pass a subset or `all`). `--out DIR` defaults to the run directory. Files: `report.html`, `report.md`, `report.json`, `junit.xml`, `skeptic.sarif`, `badge.svg`.

### `skeptic compare RUN_A RUN_B`

`--format md|json` (default `md`).

### `skeptic gate RUN_DIR`

`--min-sks F`, `--max-fsr F`, `--max-icr F`. When a flag is omitted, the values in the run's config are used (`min_sks` 70, `max_fsr` 0.10, `max_icr` 0.00 if the file does not set them). Exit 10 on failure.

### `skeptic mcp serve`

`--transport stdio|streamable-http|sse` (default `stdio`), `--host` (default `127.0.0.1`), `--port` (default `8765`). Tools: `list_faults`, `list_suites`, `run_suite`, `get_report`, `explain_episode`. `run_suite` requires `max_cost_usd` and rejects a value above 10.

## Exit codes

| Code | Meaning |
|---|---|
| 0 | Success |
| 1 | Unclassified error |
| 2 | Usage error |
| 3 | Invalid config or schema |
| 4 | Upstream process failed to start |
| 5 | Budget ceiling reached |
| 10 | Gate failed |

The [configuration reference](config.md) is the file `init` writes. The [quickstart](../quickstart.md) runs the FakeLLM path end to end.
