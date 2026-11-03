"""Skeptic MCP Server mode implementation (S14.3, ADR-0004, K55).

Provides high-level MCPServer exposing:
- list_faults: The S6 fault catalogue, optionally filtered by class.
- list_suites: Built-in suites and their scenario counts.
- run_suite: Synchronous execution of a test suite with budget control (<= 10 USD) and timeout.
- get_report: Retrieve report content in markdown or json format.
- explain_episode: Detail an episode outcome and compare tool results before/after faults.
"""

from __future__ import annotations

import inspect
import json
import os
from collections.abc import Sequence
from pathlib import Path
from typing import Annotated, Any, Literal

from mcp.server import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import CallToolResult, TextContent
from pydantic import AliasChoices, Field

from skeptic_agent.faults.catalog import FAULT_CLASSES, catalogue
from skeptic_agent.report.json_report import generate_json_report
from skeptic_agent.report.loader import load_run_data
from skeptic_agent.report.md_report import generate_md_report
from skeptic_agent.runner.matrix import ROOT_DIR, execute_run
from skeptic_agent.scenario.suites import list_suites, resolve_suite_scenarios

MAX_ALLOWED_COST_USD: float = 10.0
"""The maximum budget permitted for run_suite over MCP (S14.3, K55)."""


def resolve_run_dir(
    run_id: str,
    episode_id: str | None = None,
    custom_base: Path | str | None = None,
) -> Path:
    """Resolve a run directory from a run_id or fallback to episode_id prefix.

    Args:
        run_id: The run identifier or directory path.
        episode_id: Optional episode ID to deduce run_id if not found directly.
        custom_base: Optional base directory to search in.

    Returns:
        The existing run directory Path.

    Raises:
        ToolError: If no matching run directory can be found.
    """
    candidates_to_try: list[str] = [run_id]
    if episode_id and ":" in episode_id:
        extracted = episode_id.split(":")[0]
        if extracted and extracted != run_id:
            candidates_to_try.append(extracted)

    for cand in candidates_to_try:
        if custom_base is not None:
            p = Path(custom_base) / cand
            if p.is_dir():
                return p

        p_direct = Path(cand)
        if p_direct.is_dir():
            return p_direct

        env_dir = os.environ.get("SKEPTIC_RUNS_DIR")
        if env_dir:
            p = Path(env_dir) / cand
            if p.is_dir():
                return p

        search_dirs = [
            ROOT_DIR / "runs" / cand,
            Path("runs") / cand,
            Path(".skeptic") / "runs" / cand,
        ]
        for s in search_dirs:
            if s.is_dir():
                return s

    raise ToolError(f"Run directory not found for run_id: {run_id!r}")


def create_server(name: str = "skeptic") -> MCPServer[Any]:
    """Create and configure the Skeptic MCP server (S14.3, ADR-0004).

    Args:
        name: Name of the server instance (defaults to 'skeptic').

    Returns:
        An MCPServer instance with all S14.3 tools registered.
    """
    server: MCPServer[Any] = MCPServer(name)

    # 1. list_faults
    async def list_faults_handler(**kwargs: Any) -> CallToolResult:
        """List the S6 fault catalogue, optionally filtered by class."""
        raw_class = kwargs.get("class") or kwargs.get("class_") or kwargs.get("fault_class")
        wanted = raw_class.lower() if raw_class is not None else None
        if wanted is not None and wanted not in FAULT_CLASSES:
            raise ToolError(f"Unknown fault class: {raw_class!r}. Must be one of {FAULT_CLASSES}")
        entries = catalogue(wanted)
        return CallToolResult(
            content=[
                TextContent(
                    type="text",
                    text=json.dumps(entries, indent=2, ensure_ascii=False),
                )
            ],
            structured_content={"faults": entries},
        )

    class_param = inspect.Parameter(
        "class_",
        inspect.Parameter.KEYWORD_ONLY,
        annotation=Annotated[
            Literal["loud", "silent", "adversarial"] | None,
            Field(
                validation_alias=AliasChoices("class", "fault_class", "class_"),
                serialization_alias="class",
                default=None,
                description="Filter faults by class ('loud', 'silent', or 'adversarial')",
            ),
        ],
        default=None,
    )
    list_faults_handler.__signature__ = inspect.Signature(  # type: ignore[attr-defined]
        [class_param],
        return_annotation=CallToolResult,
    )
    list_faults_handler.__name__ = "list_faults"
    list_faults_handler.__doc__ = (
        "List the S6 fault catalogue, optionally filtered by class (S14.3)."
    )
    server.add_tool(list_faults_handler)

    # 2. list_suites
    @server.tool(
        name="list_suites",
        description="List built-in test suites and their scenario counts (S14.3).",
    )
    def list_suites_tool() -> CallToolResult:
        suites = list_suites()
        return CallToolResult(
            content=[
                TextContent(
                    type="text",
                    text=json.dumps(suites, indent=2, ensure_ascii=False),
                )
            ],
            structured_content=suites,
        )

    # 3. run_suite
    @server.tool(
        name="run_suite",
        description="Run a test suite synchronously with budget cap and timeout (S14.3).",
    )
    async def run_suite_tool(
        suite: Annotated[
            str,
            Field(description="Benchmark suite identifier (e.g. 'smoke')"),
        ],
        agent: Annotated[
            str,
            Field(description="Agent specification ('adapter:model')"),
        ],
        profile: Annotated[
            str,
            Field(description="Fault profile identifier ('silent-core', 'none', etc.)"),
        ],
        max_cost_usd: Annotated[
            float,
            Field(
                ge=0.0,
                le=MAX_ALLOWED_COST_USD,
                description=f"Cumulative budget limit in USD (must be <= {MAX_ALLOWED_COST_USD})",
            ),
        ],
        guards: Annotated[
            str | list[str] | None,
            Field(
                default=None,
                description="Guard preset or list of guards (defaults to 'none')",
            ),
        ] = None,
        seeds: Annotated[
            list[int] | None,
            Field(default=None, description="Random seeds (defaults to [1])"),
        ] = None,
        timeout_seconds: Annotated[
            float,
            Field(
                default=1800.0,
                description="Max execution timeout in seconds (default 1800.0, i.e. 30 min)",
            ),
        ] = 1800.0,
        out_dir: Annotated[
            str | None,
            Field(default=None, description="Optional custom output directory"),
        ] = None,
    ) -> CallToolResult:
        if max_cost_usd > MAX_ALLOWED_COST_USD or max_cost_usd < 0.0:
            msg = (
                f"Parameter error: max_cost_usd must be <= {MAX_ALLOWED_COST_USD} "
                f"and >= 0.0, got {max_cost_usd}"
            )
            raise ToolError(msg)

        try:
            resolved_scenarios = resolve_suite_scenarios(suite)
            if not resolved_scenarios:
                raise ToolError(f"No scenarios found for suite: {suite!r}")
        except Exception as exc:
            if isinstance(exc, ToolError):
                raise
            raise ToolError(f"Error resolving suite {suite!r}: {exc}") from exc

        target_out: Path | None = None
        if out_dir is not None:
            target_out = Path(out_dir)
        elif os.environ.get("SKEPTIC_RUNS_DIR"):
            target_out = Path(os.environ["SKEPTIC_RUNS_DIR"])

        seeds_list: Sequence[int] = seeds if seeds is not None else (1,)
        guards_arg = guards if guards is not None else "none"

        try:
            summary_doc = await execute_run(
                suite=suite,
                agent=agent,
                profile=profile,
                guards=guards_arg,
                seeds=seeds_list,
                max_cost_usd=max_cost_usd,
                out_dir=target_out,
                timeout_seconds=timeout_seconds,
            )
        except Exception as exc:
            raise ToolError(f"Error executing run_suite: {exc}") from exc

        run_id = str(summary_doc.get("run_id", ""))

        # Build S10.5 simplified summary
        simplified: dict[str, Any] = {
            "run_id": run_id,
            "time": summary_doc.get("time"),
            "version": summary_doc.get("version"),
            "command": summary_doc.get("command"),
            "git_sha": summary_doc.get("git_sha"),
            "config": summary_doc.get("config"),
            "agents": summary_doc.get("agents", []),
            "by_fault": summary_doc.get("by_fault", {}),
            "by_sandbox": summary_doc.get("by_sandbox", {}),
            "worst_scenarios": summary_doc.get("worst_scenarios", []),
            "guard_actions": summary_doc.get("guard_actions", {}),
            "total_cost_usd": summary_doc.get("total_cost_usd", 0.0),
        }

        if summary_doc.get("agents"):
            primary_metrics = summary_doc["agents"][0].get("metrics", {})
            simplified["sks"] = primary_metrics.get("SKS", {})
            simplified["metrics"] = primary_metrics

        is_partial = False
        for ag in summary_doc.get("agents", []):
            if ag.get("metrics", {}).get("SKS", {}).get("partial"):
                is_partial = True
                break
        simplified["partial"] = is_partial

        result_payload = {
            "run_id": run_id,
            "summary": simplified,
            "partial": is_partial,
        }

        return CallToolResult(
            content=[
                TextContent(
                    type="text",
                    text=json.dumps(result_payload, indent=2, ensure_ascii=False),
                )
            ],
            structured_content=result_payload,
        )

    # 4. get_report
    @server.tool(
        name="get_report",
        description="Retrieve benchmark evaluation report in markdown or JSON format (S14.3).",
    )
    def get_report_tool(
        run_id: Annotated[
            str,
            Field(description="Run ID of the completed benchmark run"),
        ],
        format: Annotated[
            Literal["md", "json"],
            Field(description="Report format: 'md' or 'json'"),
        ],
    ) -> CallToolResult:
        if format not in ("md", "json"):
            raise ToolError(f"Invalid report format: {format!r}. Must be 'md' or 'json'.")

        run_dir = resolve_run_dir(run_id)

        if format == "md":
            md_path = run_dir / "report.md"
            if md_path.is_file():
                content_text = md_path.read_text(encoding="utf-8")
            else:
                run_data = load_run_data(run_dir)
                generate_md_report(run_data, md_path)
                content_text = md_path.read_text(encoding="utf-8")
            return CallToolResult(
                content=[TextContent(type="text", text=content_text)],
                structured_content={"format": "md", "content": content_text},
            )
        else:
            json_path = run_dir / "report.json"
            if json_path.is_file():
                content_text = json_path.read_text(encoding="utf-8")
                parsed_json = json.loads(content_text)
            else:
                run_data = load_run_data(run_dir)
                generate_json_report(run_data, json_path)
                content_text = json_path.read_text(encoding="utf-8")
                parsed_json = json.loads(content_text)
            return CallToolResult(
                content=[TextContent(type="text", text=content_text)],
                structured_content=parsed_json,
            )

    # 5. explain_episode
    @server.tool(
        name="explain_episode",
        description="Explain episode outcome and compare tool results before/after faults (S14.3).",
    )
    def explain_episode_tool(
        run_id: Annotated[
            str,
            Field(description="Run ID containing the episode"),
        ],
        episode_id: Annotated[
            str,
            Field(description="Target episode ID to explain"),
        ],
    ) -> CallToolResult:
        run_dir = resolve_run_dir(run_id, episode_id=episode_id)
        run_data = load_run_data(run_dir)

        target_ep = next(
            (ep for ep in run_data.episodes if ep.episode_id == episode_id),
            None,
        )
        if target_ep is None:
            raise ToolError(f"Episode {episode_id!r} not found in run {run_id!r}")

        lines = [
            f"# Episode Explanation: {target_ep.episode_id}",
            f"- **Scenario**: `{target_ep.scenario_id}`",
            f"- **Sandbox**: `{target_ep.sandbox}`",
            f"- **Outcome**: `{target_ep.outcome}`",
            f"- **Fault**: `{target_ep.fault_id or 'none'}`",
            f"- **Fault Class**: `{target_ep.fault_class or 'none'}`",
            f"- **Recoverability**: `{target_ep.recoverability or 'none'}`",
            f"- **Seed**: {target_ep.seed}",
        ]
        if target_ep.final_answer:
            lines.append(f"- **Final Answer**: {target_ep.final_answer[:300]}")
        if target_ep.error:
            lines.append(f"- **Error**: {target_ep.error}")

        lines.append("\n## Tool Calls Comparison (Before vs After Fault):")
        if not target_ep.tool_calls:
            lines.append("*(No tool calls recorded or no diffs in cassette)*")
        else:
            for tc in target_ep.tool_calls:
                lines.append(f"\n### Call #{tc.seq}: `{tc.tool}`")
                lines.append(f"- **Arguments**: `{json.dumps(tc.arguments, ensure_ascii=False)}`")
                raw_val = tc.raw_result if tc.raw_result is not None else tc.raw_error
                lines.append(
                    f"- **Raw Upstream Result**: {json.dumps(raw_val, ensure_ascii=False)}"
                )
                final_val = tc.final_result if tc.final_result is not None else tc.final_error
                lines.append(
                    f"- **Final Delivered Result**: {json.dumps(final_val, ensure_ascii=False)}"
                )
                fault_str = json.dumps(tc.fault, ensure_ascii=False) if tc.fault else "none"
                lines.append(f"- **Fault Injected**: {fault_str}")
                lines.append(f"- **Modified**: {tc.modified} | **Dropped**: {tc.dropped}")
                if tc.guards:
                    guards_str = json.dumps(tc.guards, ensure_ascii=False)
                    lines.append(f"- **Guards Interventions**: {guards_str}")

        structured_diff = {
            "episode_id": target_ep.episode_id,
            "scenario_id": target_ep.scenario_id,
            "sandbox": target_ep.sandbox,
            "seed": target_ep.seed,
            "outcome": target_ep.outcome,
            "fault_id": target_ep.fault_id,
            "fault_class": target_ep.fault_class,
            "recoverability": target_ep.recoverability,
            "final_answer": target_ep.final_answer,
            "tool_calls": [tc.to_dict() for tc in target_ep.tool_calls],
        }

        return CallToolResult(
            content=[TextContent(type="text", text="\n".join(lines))],
            structured_content=structured_diff,
        )

    return server
