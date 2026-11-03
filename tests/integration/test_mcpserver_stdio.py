"""Integration tests for Skeptic MCP Server running over stdio (S14.3, K55)."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

pytestmark = pytest.mark.integration

ROOT = Path(__file__).resolve().parents[2]


def _build_stdio_params(runs_dir: Path) -> StdioServerParameters:
    """Build StdioServerParameters invoking skeptic mcp serve."""
    args = ["-m", "skeptic_agent.cli", "mcp", "serve"]
    env = dict(os.environ)
    env["PYTHONPATH"] = str(ROOT / "src")
    env["SKEPTIC_RUNS_DIR"] = str(runs_dir)
    return StdioServerParameters(command=sys.executable, args=args, env=env)


@pytest.mark.asyncio
async def test_stdio_mcp_server_full_flow(tmp_path: Path) -> None:
    """Verify skeptic mcp serve starts over stdio and responds to all tools."""
    runs_dir = tmp_path / "runs"
    runs_dir.mkdir()
    params = _build_stdio_params(runs_dir)

    async with (
        stdio_client(params) as (read_stream, write_stream),
        ClientSession(read_stream, write_stream) as session,
    ):
        await session.initialize()

        # 1. list_tools
        tools_res = await session.list_tools()
        tool_names = [t.name for t in tools_res.tools]
        assert "list_faults" in tool_names
        assert "list_suites" in tool_names
        assert "run_suite" in tool_names
        assert "get_report" in tool_names
        assert "explain_episode" in tool_names

        # 2. list_suites
        suites_call = await session.call_tool("list_suites", {})
        assert not suites_call.is_error
        assert suites_call.structured_content is not None
        assert "smoke" in suites_call.structured_content
        assert suites_call.structured_content["smoke"] == 20

        # 3. list_faults
        faults_call = await session.call_tool("list_faults", {"class": "loud"})
        assert not faults_call.is_error
        assert faults_call.structured_content is not None
        assert len(faults_call.structured_content["faults"]) == 7

        # 4. run_suite budget cap validation (> 10 USD fails)
        bad_budget_call = await session.call_tool(
            "run_suite",
            {
                "suite": "smoke",
                "agent": "reference:fake/oracle_follower",
                "profile": "none",
                "max_cost_usd": 15.0,
            },
        )
        assert bad_budget_call.is_error
        err_text = bad_budget_call.content[0].text if bad_budget_call.content else ""
        assert "less than or equal to 10" in err_text or "max_cost_usd" in err_text

        # 5. run_suite acceptance run (FakeLLM, smoke suite, max_cost_usd=0.1)
        run_out = tmp_path / "stdio_smoke_run"
        run_call = await session.call_tool(
            "run_suite",
            {
                "suite": "smoke",
                "agent": "reference:fake/oracle_follower",
                "profile": "none",
                "max_cost_usd": 0.1,
                "out_dir": str(run_out),
            },
        )
        assert not run_call.is_error
        assert run_call.structured_content is not None
        payload = run_call.structured_content
        assert "run_id" in payload
        assert "summary" in payload
        summary = payload["summary"]
        assert "sks" in summary
        assert "metrics" in summary
        assert (run_out / "results.jsonl").is_file()
        assert (run_out / "summary.json").is_file()

        # 6. get_report
        report_md_call = await session.call_tool(
            "get_report",
            {"run_id": str(run_out), "format": "md"},
        )
        assert not report_md_call.is_error
        assert len(report_md_call.content) > 0
        assert "Skeptic" in report_md_call.content[0].text

        # 7. explain_episode
        results_lines = (run_out / "results.jsonl").read_text(encoding="utf-8").splitlines()
        first_ep = json.loads(results_lines[0])
        first_ep_id = first_ep["episode_id"]

        explain_call = await session.call_tool(
            "explain_episode",
            {"run_id": str(run_out), "episode_id": first_ep_id},
        )
        assert not explain_call.is_error
        assert explain_call.structured_content is not None
        assert explain_call.structured_content["episode_id"] == first_ep_id
        assert explain_call.structured_content["outcome"] == first_ep["outcome"]
