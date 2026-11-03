"""Unit tests for Skeptic MCP Server mode (S14.3, K55)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from mcp import Client
from mcp.server.mcpserver.exceptions import ToolError

from skeptic_agent.mcpserver.server import (
    create_server,
    resolve_run_dir,
)

pytestmark = pytest.mark.asyncio


async def test_list_faults_all() -> None:
    """list_faults without parameters returns all 20 catalogued faults."""
    server = create_server()
    async with Client(server) as client:
        res = await client.call_tool("list_faults", {})
        assert not res.is_error
        assert res.structured_content is not None
        faults = res.structured_content.get("faults")
        assert isinstance(faults, list)
        assert len(faults) == 20
        ids = [f["id"] for f in faults]
        assert "L01" in ids
        assert "S01" in ids
        assert "A01" in ids


async def test_list_faults_filtered() -> None:
    """list_faults filters correctly by class."""
    server = create_server()
    async with Client(server) as client:
        # Loud
        res_loud = await client.call_tool("list_faults", {"class": "loud"})
        assert not res_loud.is_error
        faults_loud = res_loud.structured_content["faults"]
        assert len(faults_loud) == 7
        assert all(f["class"] == "loud" for f in faults_loud)

        # Silent
        res_silent = await client.call_tool("list_faults", {"class": "silent"})
        assert not res_silent.is_error
        faults_silent = res_silent.structured_content["faults"]
        assert len(faults_silent) == 10
        assert all(f["class"] == "silent" for f in faults_silent)

        # Adversarial
        res_adv = await client.call_tool("list_faults", {"class": "adversarial"})
        assert not res_adv.is_error
        faults_adv = res_adv.structured_content["faults"]
        assert len(faults_adv) == 3
        assert all(f["class"] == "adversarial" for f in faults_adv)


async def test_list_faults_alias() -> None:
    """list_faults accepts fault_class alias."""
    server = create_server()
    async with Client(server) as client:
        res = await client.call_tool("list_faults", {"fault_class": "loud"})
        assert not res.is_error
        assert len(res.structured_content["faults"]) == 7


async def test_list_faults_invalid_class() -> None:
    """list_faults rejects unknown fault class."""
    server = create_server()
    async with Client(server) as client:
        res = await client.call_tool("list_faults", {"class": "invalid_class"})
        assert res.is_error
        assert (
            "Input should be" in res.content[0].text or "Unknown fault class" in res.content[0].text
        )


async def test_list_suites() -> None:
    """list_suites returns scenario counts for built-in suites."""
    server = create_server()
    async with Client(server) as client:
        res = await client.call_tool("list_suites", {})
        assert not res.is_error
        assert res.structured_content is not None
        assert "smoke" in res.structured_content
        assert res.structured_content["smoke"] == 20


async def test_run_suite_max_cost_usd_limit() -> None:
    """run_suite enforces max_cost_usd <= 10.0 and rejects values exceeding it."""
    server = create_server()
    async with Client(server) as client:
        # > 10.0 USD
        res_exceeded = await client.call_tool(
            "run_suite",
            {
                "suite": "smoke",
                "agent": "reference:fake/oracle_follower",
                "profile": "none",
                "max_cost_usd": 15.0,
            },
        )
        assert res_exceeded.is_error
        assert (
            "less than or equal to 10" in res_exceeded.content[0].text
            or "max_cost_usd" in res_exceeded.content[0].text
        )

        # < 0 USD
        res_neg = await client.call_tool(
            "run_suite",
            {
                "suite": "smoke",
                "agent": "reference:fake/oracle_follower",
                "profile": "none",
                "max_cost_usd": -1.0,
            },
        )
        assert res_neg.is_error


async def test_run_suite_invalid_suite() -> None:
    """run_suite reports error on unknown suite."""
    server = create_server()
    async with Client(server) as client:
        res = await client.call_tool(
            "run_suite",
            {
                "suite": "nonexistent_suite_xyz",
                "agent": "reference:fake/oracle_follower",
                "profile": "none",
                "max_cost_usd": 0.1,
            },
        )
        assert res.is_error


async def test_run_suite_acceptance_fake_llm(tmp_path: Path) -> None:
    """Acceptance criterion for K55:

    SDK client calls run_suite (FakeLLM, smoke suite, max_cost_usd=0.1) and returns summary.
    """
    server = create_server()
    out_dir = tmp_path / "acceptance_run"

    async with Client(server) as client:
        res = await client.call_tool(
            "run_suite",
            {
                "suite": "smoke",
                "agent": "reference:fake/oracle_follower",
                "profile": "none",
                "max_cost_usd": 0.1,
                "out_dir": str(out_dir),
            },
        )

        assert not res.is_error
        assert res.structured_content is not None
        payload = res.structured_content
        assert "run_id" in payload
        assert "summary" in payload

        summary = payload["summary"]
        assert summary["run_id"] == payload["run_id"]
        assert "sks" in summary
        assert "metrics" in summary
        assert "agents" in summary
        assert len(summary["agents"]) >= 1

        # Check files were written in tmp_path
        assert (out_dir / "results.jsonl").is_file()
        assert (out_dir / "summary.json").is_file()

        # Check get_report md & json (first time generates, second time reads cached)
        res_md = await client.call_tool(
            "get_report",
            {"run_id": str(out_dir), "format": "md"},
        )
        assert not res_md.is_error
        assert "Skeptic 评测报告" in res_md.content[0].text or "Report" in res_md.content[0].text

        res_md_cached = await client.call_tool(
            "get_report",
            {"run_id": str(out_dir), "format": "md"},
        )
        assert not res_md_cached.is_error
        assert (
            "Skeptic 评测报告" in res_md_cached.content[0].text
            or "Report" in res_md_cached.content[0].text
        )

        res_json = await client.call_tool(
            "get_report",
            {"run_id": str(out_dir), "format": "json"},
        )
        assert not res_json.is_error
        assert res_json.structured_content.get("run_id") == payload["run_id"]

        res_json_cached = await client.call_tool(
            "get_report",
            {"run_id": str(out_dir), "format": "json"},
        )
        assert not res_json_cached.is_error
        assert res_json_cached.structured_content.get("run_id") == payload["run_id"]

        # Check explain_episode
        results_lines = (out_dir / "results.jsonl").read_text(encoding="utf-8").splitlines()
        first_ep = json.loads(results_lines[0])
        first_ep_id = first_ep["episode_id"]

        res_exp = await client.call_tool(
            "explain_episode",
            {"run_id": str(out_dir), "episode_id": first_ep_id},
        )
        assert not res_exp.is_error
        assert res_exp.structured_content is not None
        assert res_exp.structured_content["episode_id"] == first_ep_id
        assert res_exp.structured_content["outcome"] == first_ep["outcome"]
        assert "tool_calls" in res_exp.structured_content


async def test_get_report_errors(tmp_path: Path) -> None:
    """get_report rejects invalid format and missing run directory."""
    server = create_server()
    async with Client(server) as client:
        # Invalid format
        res_fmt = await client.call_tool(
            "get_report",
            {"run_id": str(tmp_path), "format": "xml"},
        )
        assert res_fmt.is_error

        # Missing run directory
        res_missing = await client.call_tool(
            "get_report",
            {"run_id": "nonexistent_run_id_00000000_111111", "format": "md"},
        )
        assert res_missing.is_error


async def test_explain_episode_errors(tmp_path: Path) -> None:
    """explain_episode reports error on missing run or missing episode."""
    server = create_server()
    async with Client(server) as client:
        # Missing run
        res_missing_run = await client.call_tool(
            "explain_episode",
            {
                "run_id": "nonexistent_run_id_00000000_111111",
                "episode_id": "some:ep:clean:1",
            },
        )
        assert res_missing_run.is_error

        # Run directory exists with empty results.jsonl but missing episode
        dummy_run = tmp_path / "dummy_run"
        dummy_run.mkdir()
        (dummy_run / "results.jsonl").write_text("", encoding="utf-8")
        res_missing_ep = await client.call_tool(
            "explain_episode",
            {
                "run_id": str(dummy_run),
                "episode_id": "some:ep:clean:1",
            },
        )
        assert res_missing_ep.is_error


async def test_run_suite_timeout_partial(tmp_path: Path) -> None:
    """run_suite with extremely short timeout triggers partial=True on multi-episode run."""
    server = create_server()
    out_dir = tmp_path / "timeout_run"

    async with Client(server) as client:
        res = await client.call_tool(
            "run_suite",
            {
                "suite": "smoke",
                "agent": "reference:fake/oracle_follower",
                "profile": "silent-core",
                "max_cost_usd": 0.1,
                "timeout_seconds": 0.0001,
                "out_dir": str(out_dir),
            },
        )
        assert not res.is_error
        payload = res.structured_content
        assert payload["partial"] is True
        assert payload["summary"]["partial"] is True


async def test_resolve_run_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """resolve_run_dir searches direct path, env var, and candidate dirs."""
    # Direct path
    assert resolve_run_dir(str(tmp_path)) == tmp_path

    # Custom base
    custom_run = tmp_path / "my_run"
    custom_run.mkdir()
    assert resolve_run_dir("my_run", custom_base=tmp_path) == custom_run

    # Env var
    env_dir = tmp_path / "env_runs"
    env_run = env_dir / "test_run"
    env_run.mkdir(parents=True)
    monkeypatch.setenv("SKEPTIC_RUNS_DIR", str(env_dir))
    assert resolve_run_dir("test_run") == env_run

    # Not found raises ToolError
    with pytest.raises(ToolError):
        resolve_run_dir("definitely_not_existing_run_id_404")


async def test_cli_mcp_serve_invalid_transport() -> None:
    """CLI skeptic mcp serve rejects invalid transport with exit code 2."""
    from typer.testing import CliRunner

    from skeptic_agent.cli import app

    runner = CliRunner()
    result = runner.invoke(app, ["mcp", "serve", "--transport", "ftp"])
    assert result.exit_code == 2
    assert "unknown transport" in result.output


async def test_explain_episode_with_rich_details(tmp_path: Path) -> None:
    """explain_episode formats final_answer, error, and tool guards properly."""
    server = create_server()
    run_dir = tmp_path / "rich_run"
    run_dir.mkdir()

    cassettes_dir = run_dir / "cassettes"
    cassettes_dir.mkdir()
    cassette_file = cassettes_dir / "ep1.jsonl"
    cassette_file.write_text(
        json.dumps(
            {
                "type": "msg",
                "dir": "c2s",
                "seq": 1,
                "raw": {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "tools/call",
                    "params": {"name": "get_weather", "arguments": {"city": "Tokyo"}},
                },
            }
        )
        + "\n"
        + json.dumps(
            {
                "type": "msg",
                "dir": "s2c",
                "seq": 2,
                "raw": {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "result": {"content": [{"type": "text", "text": "temp=20"}]},
                },
                "final": {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "result": {"content": [{"type": "text", "text": "temp=25"}]},
                },
                "fault": {"id": "S02"},
                "guards": [{"name": "evidence_contract"}],
                "modified": True,
                "dropped": False,
            }
        )
        + "\n",
        encoding="utf-8",
    )

    results_file = run_dir / "results.jsonl"
    results_file.write_text(
        json.dumps(
            {
                "episode_id": "20261103-120000-abcdef:weather.test.001:S02:1",
                "scenario_id": "weather.test.001",
                "sandbox": "sb_weather",
                "seed": 1,
                "outcome": "SILENT_CORRUPTION",
                "fault": {"id": "S02"},
                "final_answer": "The weather is 25C.",
                "error": "Timeout warning",
                "cassette": "cassettes/ep1.jsonl",
            }
        )
        + "\n",
        encoding="utf-8",
    )

    async with Client(server) as client:
        res = await client.call_tool(
            "explain_episode",
            {
                "run_id": str(run_dir),
                "episode_id": "20261103-120000-abcdef:weather.test.001:S02:1",
            },
        )
        assert not res.is_error
        text = res.content[0].text
        assert "The weather is 25C." in text
        assert "Timeout warning" in text
        assert "Guards Interventions" in text
        assert "Fault Injected" in text
