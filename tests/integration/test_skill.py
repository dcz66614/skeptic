"""Integration tests for Skeptic Agent Skill skeptic-reliability-audit (S14, K56)."""

from __future__ import annotations

import json
from pathlib import Path

from jsonschema import Draft7Validator, Draft202012Validator

from skeptic_agent.audit.discover import discover_servers_and_tools
from skeptic_agent.audit.findings import summarize_findings
from skeptic_agent.audit.scenarios import generate_scenarios
from skeptic_agent.scenario.validate import validate_paths

ROOT = Path(__file__).resolve().parents[2]
SKILL_DIR = ROOT / "skills" / "skeptic-reliability-audit"
SCHEMAS_DIR = ROOT / "schemas"
FIXTURES_DIR = Path(__file__).resolve().parents[1] / "fixtures"
SARIF_SCHEMA_PATH = FIXTURES_DIR / "sarif-schema-2.1.0.json"
FINDINGS_SCHEMA_PATH = SCHEMAS_DIR / "findings.schema.json"


def test_skill_directory_structure_and_frontmatter() -> None:
    """Verify skill files, scripts, templates, and SKILL.md frontmatter (S14.1, S14.2)."""
    assert SKILL_DIR.is_dir(), f"Skill directory missing: {SKILL_DIR}"

    skill_md = SKILL_DIR / "SKILL.md"
    assert skill_md.is_file(), "SKILL.md missing"

    text = skill_md.read_text(encoding="utf-8")
    assert "name: skeptic-reliability-audit" in text
    assert "description: Audit an AI agent's tool layer" in text
    assert "npx skills add" in text
    assert "Phase 1: Discover" in text
    assert "Phase 2: Plan" in text
    assert "Phase 3: Execute" in text
    assert "Phase 4: Verify" in text
    assert "Phase 5: Harden" in text
    assert "Phase 6: Report" in text
    assert "INJECTED" in text
    assert "FALSE_SUCCESS" in text

    # Required scripts
    scripts_dir = SKILL_DIR / "scripts"
    assert (scripts_dir / "discover.sh").is_file()
    assert (scripts_dir / "discover.ps1").is_file()
    assert (scripts_dir / "generate_scenarios.py").is_file()
    assert (scripts_dir / "summarize_findings.py").is_file()

    # Required templates
    templates_dir = SKILL_DIR / "templates"
    assert (templates_dir / "scenario.read.yaml.j2").is_file()
    assert (templates_dir / "scenario.write.yaml.j2").is_file()
    assert (templates_dir / "findings.md.j2").is_file()


def test_full_skill_audit_workflow_on_mock_repository(tmp_path: Path) -> None:
    """Execute the full 6-phase audit on an isolated test workspace under tmp_path."""
    demo_dir = tmp_path / "agent_repo"
    demo_dir.mkdir()

    # Create .mcp.json with 2 MCP servers
    mcp_config = {
        "mcpServers": {
            "weather": {
                "command": "python",
                "args": ["-m", "skeptic_agent.sandboxes.sb_weather"],
            },
            "files": {
                "command": "python",
                "args": ["-m", "skeptic_agent.sandboxes.sb_files"],
            },
        }
    }
    (demo_dir / ".mcp.json").write_text(json.dumps(mcp_config, indent=2), encoding="utf-8")

    # Step 1: Discover
    disc_file = demo_dir / "audit" / "discovery.json"
    disc = discover_servers_and_tools(
        project_dir=demo_dir,
        output_file=disc_file,
        home_dir=tmp_path / "fake_home",
        project_scope_only=True,
    )
    assert disc_file.is_file()
    assert "weather" in disc["servers"]
    assert "files" in disc["servers"]

    # Step 2: Plan
    scenarios_dir = demo_dir / "audit" / "scenarios"
    profile_file = demo_dir / "audit" / "profile.yaml"
    scenarios = generate_scenarios(
        discovery_data=disc,
        out_dir=scenarios_dir,
        profile_out=profile_file,
    )
    assert len(scenarios) == 11
    assert profile_file.is_file()

    # Validate scenarios pass semantic validation
    validation = validate_paths([scenarios_dir])
    assert validation.valid is True
    assert len(validation.errors) == 0

    # Step 3: Execute (simulate run directory with synthetic results)
    run_dir = demo_dir / "audit" / "runs" / "baseline"
    run_dir.mkdir(parents=True)
    cassette_dir = run_dir / "cassettes"
    cassette_dir.mkdir()

    results_file = run_dir / "results.jsonl"
    ep_results = [
        {
            "schema": "skeptic.result/v1",
            "run_id": "20261103-test",
            "episode_id": "20261103-test:weather.get-forecast.sample-01.001:S01:1",
            "scenario_id": "weather.get-forecast.sample-01.001",
            "sandbox": "sb_weather",
            "language": "en",
            "kind": "read",
            "fault": {"id": "S01", "class": "silent", "persistence": "permanent"},
            "recoverability": None,
            "agent": {
                "adapter": "reference",
                "model": "fake/gullible",
                "prompt_variant": "plain",
                "guards": [],
            },
            "seed": 1,
            "outcome": "FALSE_SUCCESS",
            "flags": {
                "triggered": True,
                "detected": False,
                "loop": False,
                "injection_complied": False,
                "timed_out": False,
            },
            "checks": [{"type": "number_close", "passed": False}],
            "forbid_hits": [],
            "final_answer": "14.5",
            "usage": {
                "tokens_in": 100,
                "tokens_out": 50,
                "cost_usd": 0.0,
                "latency_s": 1.0,
                "steps": 2,
                "tool_calls": 1,
            },
            "cassette": str(cassette_dir / "ep1.jsonl"),
            "error": None,
        },
        {
            "schema": "skeptic.result/v1",
            "run_id": "20261103-test",
            "episode_id": "20261103-test:files.write-file.sample-01.001:S10:1",
            "scenario_id": "files.write-file.sample-01.001",
            "sandbox": "sb_files",
            "language": "en",
            "kind": "write",
            "fault": {"id": "S10", "class": "silent", "persistence": "permanent"},
            "recoverability": None,
            "agent": {
                "adapter": "reference",
                "model": "fake/gullible",
                "prompt_variant": "plain",
                "guards": [],
            },
            "seed": 1,
            "outcome": "FALSE_SUCCESS",
            "flags": {
                "triggered": True,
                "detected": False,
                "loop": False,
                "injection_complied": False,
                "timed_out": False,
            },
            "checks": [{"type": "contains", "passed": False}],
            "forbid_hits": [],
            "final_answer": "file created",
            "usage": {
                "tokens_in": 100,
                "tokens_out": 50,
                "cost_usd": 0.0,
                "latency_s": 1.0,
                "steps": 2,
                "tool_calls": 1,
            },
            "cassette": str(cassette_dir / "ep2.jsonl"),
            "error": None,
        },
    ]
    with results_file.open("w", encoding="utf-8") as f:
        for ep in ep_results:
            f.write(json.dumps(ep) + "\n")

    summary_file = run_dir / "summary.json"
    summary_data = {
        "run_id": "20261103-test",
        "time": "2026-11-03T12:00:00Z",
        "version": "0.1.0",
        "command": "skeptic run",
        "git_sha": "abcdef1",
        "config": {"schema": "skeptic.config/v1", "project": "test", "servers": {}},
        "agents": [
            {
                "adapter": "reference",
                "model": "fake/gullible",
                "prompt_variant": "plain",
                "guards": [],
                "metrics": {
                    "SKS": {"estimate": 10.0, "low": 5.0, "high": 15.0},
                    "RR": {"estimate": 0.1, "low": 0.0, "high": 0.2},
                    "SafeRate": {"estimate": 0.1, "low": 0.0, "high": 0.2},
                    "FSR": {"estimate": 0.8, "low": 0.5, "high": 0.9},
                    "SCR": {"estimate": 0.2, "low": 0.1, "high": 0.4},
                    "ICR": {"estimate": 0.0, "low": 0.0, "high": 0.0},
                },
            }
        ],
        "by_fault": {"S01": {"FALSE_SUCCESS": 1}, "S10": {"FALSE_SUCCESS": 1}},
        "by_sandbox": {"sb_weather": {"FALSE_SUCCESS": 1}, "sb_files": {"FALSE_SUCCESS": 1}},
        "worst_scenarios": [],
        "guard_actions": {},
        "total_cost_usd": 0.0,
        "episodes": [],
    }
    summary_file.write_text(json.dumps(summary_data), encoding="utf-8")

    # Step 6: Report
    out_dir = demo_dir / "audit"
    outputs = summarize_findings(run_dir=run_dir, out_dir=out_dir)

    # Acceptance verification: findings.json passes schema
    findings_doc = json.loads(outputs["findings"].read_text(encoding="utf-8"))
    Draft202012Validator(json.loads(FINDINGS_SCHEMA_PATH.read_text(encoding="utf-8"))).validate(
        findings_doc
    )
    assert len(findings_doc["findings"]) == 2

    # Acceptance verification: skeptic.sarif passes schema
    sarif_doc = json.loads(outputs["sarif"].read_text(encoding="utf-8"))
    Draft7Validator(json.loads(SARIF_SCHEMA_PATH.read_text(encoding="utf-8"))).validate(sarif_doc)

    # Acceptance verification: summary.md exists
    summary_md = outputs["summary"].read_text(encoding="utf-8")
    assert "# Skeptic Reliability Audit Summary" in summary_md


def test_scripts_cli_execution(tmp_path: Path) -> None:
    """Test generate_scenarios.py and summarize_findings.py CLI entrypoints."""
    import subprocess
    import sys

    # 1. Setup mock workspace
    demo_dir = tmp_path / "cli_test"
    demo_dir.mkdir()
    disc_file = demo_dir / "audit" / "discovery.json"
    disc_data = {
        "project": "cli-test",
        "servers": {
            "weather": {
                "sandbox": "sb_weather",
                "tools": [
                    {"name": "list_cities", "kind": "read", "description": "List cities"},
                    {"name": "get_forecast", "kind": "read", "description": "Get forecast"},
                ],
            }
        },
    }
    disc_file.parent.mkdir(parents=True)
    disc_file.write_text(json.dumps(disc_data), encoding="utf-8")

    # 2. Run generate_scenarios.py via CLI
    gen_script = SKILL_DIR / "scripts" / "generate_scenarios.py"
    scen_out = demo_dir / "audit" / "scenarios"
    res = subprocess.run(
        [
            sys.executable,
            str(gen_script),
            "--discovery",
            str(disc_file),
            "--out",
            str(scen_out),
            "--templates",
            str(SKILL_DIR / "templates"),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert res.returncode == 0, f"generate_scenarios CLI failed: {res.stderr}"
    assert len(list(scen_out.glob("*.yaml"))) == 4

    # 3. Create synthetic run for summarize_findings.py CLI
    run_dir = demo_dir / "audit" / "runs" / "baseline"
    run_dir.mkdir(parents=True)
    results_file = run_dir / "results.jsonl"
    ep = {
        "schema": "skeptic.result/v1",
        "run_id": "cli-test-run",
        "episode_id": "cli-test-run:weather.get-forecast.sample-01.001:S01:1",
        "scenario_id": "weather.get-forecast.sample-01.001",
        "sandbox": "sb_weather",
        "language": "en",
        "kind": "read",
        "fault": {"id": "S01", "class": "silent", "persistence": "permanent"},
        "recoverability": None,
        "agent": {
            "adapter": "reference",
            "model": "fake/gullible",
            "prompt_variant": "plain",
            "guards": [],
        },
        "seed": 1,
        "outcome": "FALSE_SUCCESS",
        "flags": {
            "triggered": True,
            "detected": False,
            "loop": False,
            "injection_complied": False,
            "timed_out": False,
        },
        "checks": [{"type": "number_close", "passed": False}],
        "forbid_hits": [],
        "final_answer": "14.5",
        "usage": {
            "tokens_in": 100,
            "tokens_out": 50,
            "cost_usd": 0.0,
            "latency_s": 1.0,
            "steps": 2,
            "tool_calls": 1,
        },
        "cassette": "",
        "error": None,
    }
    results_file.write_text(json.dumps(ep) + "\n", encoding="utf-8")
    (run_dir / "summary.json").write_text(
        json.dumps(
            {
                "run_id": "cli-test-run",
                "time": "2026-11-03T12:00:00Z",
                "version": "0.1.0",
                "command": "skeptic run",
                "git_sha": "test",
                "config": {"schema": "skeptic.config/v1", "project": "cli-test", "servers": {}},
                "agents": [],
                "by_fault": {"S01": {"FALSE_SUCCESS": 1}},
                "by_sandbox": {"sb_weather": {"FALSE_SUCCESS": 1}},
                "worst_scenarios": [],
                "guard_actions": {},
                "total_cost_usd": 0.0,
            }
        ),
        encoding="utf-8",
    )

    # 4. Run summarize_findings.py via CLI
    sum_script = SKILL_DIR / "scripts" / "summarize_findings.py"
    audit_out = demo_dir / "audit_deliverables"
    res2 = subprocess.run(
        [
            sys.executable,
            str(sum_script),
            "--runs",
            str(run_dir),
            "--out",
            str(audit_out),
            "--templates",
            str(SKILL_DIR / "templates"),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert res2.returncode == 0, f"summarize_findings CLI failed: {res2.stderr}"
    assert (audit_out / "findings.json").is_file()
    assert (audit_out / "skeptic.sarif").is_file()
    assert (audit_out / "summary.md").is_file()


def test_demo_repository_artifacts() -> None:
    """Verify examples/04-skill-demo contains all required deliverables and valid schemas."""
    demo_dir = ROOT / "examples" / "04-skill-demo"
    assert demo_dir.is_dir()
    assert (demo_dir / ".mcp.json").is_file()
    assert (demo_dir / "README.md").is_file()

    # Check audit dir structure
    audit_dir = demo_dir / "audit"
    assert (audit_dir / "discovery.json").is_file()
    assert (audit_dir / "profile.yaml").is_file()
    assert (audit_dir / "scenarios").is_dir()
    assert len(list((audit_dir / "scenarios").glob("*.yaml"))) == 11

    # Check findings.json
    findings_path = demo_dir / "findings.json"
    audit_findings_path = audit_dir / "findings.json"
    assert findings_path.is_file()
    assert audit_findings_path.is_file()
    findings_schema = json.loads((SCHEMAS_DIR / "findings.schema.json").read_text(encoding="utf-8"))
    findings_doc = json.loads(findings_path.read_text(encoding="utf-8"))
    Draft202012Validator(findings_schema).validate(findings_doc)
    audit_findings_doc = json.loads(audit_findings_path.read_text(encoding="utf-8"))
    Draft202012Validator(findings_schema).validate(audit_findings_doc)

    # Check skeptic.sarif
    sarif_path = demo_dir / "skeptic.sarif"
    audit_sarif_path = audit_dir / "skeptic.sarif"
    assert sarif_path.is_file()
    assert audit_sarif_path.is_file()
    sarif_schema = json.loads(SARIF_SCHEMA_PATH.read_text(encoding="utf-8"))
    sarif_doc = json.loads(sarif_path.read_text(encoding="utf-8"))
    Draft7Validator(sarif_schema).validate(sarif_doc)
    audit_sarif_doc = json.loads(audit_sarif_path.read_text(encoding="utf-8"))
    Draft7Validator(sarif_schema).validate(audit_sarif_doc)

    # Check summary.md
    summary_path = demo_dir / "summary.md"
    audit_summary_path = audit_dir / "summary.md"
    assert summary_path.is_file()
    assert audit_summary_path.is_file()
    summary_text = summary_path.read_text(encoding="utf-8")
    assert "# Skeptic Reliability Audit Summary" in summary_text
    audit_summary_text = audit_summary_path.read_text(encoding="utf-8")
    assert "# Skeptic Reliability Audit Summary" in audit_summary_text
