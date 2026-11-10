"""The K57 composite action and its CI workflow match the task card."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

pytestmark = pytest.mark.unit

REPO_ROOT = Path(__file__).resolve().parents[2]
ACTION_PATH = REPO_ROOT / "action.yml"
EXAMPLE_WORKFLOW = REPO_ROOT / "examples" / "03-github-action" / "workflow.yml"
CI_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "example-github-action.yml"

STEP_NAMES = [
    "Setup uv",
    "Install pinned skeptic-agent",
    "skeptic run",
    "skeptic report",
    "Upload report artifact",
    "Write report.md to the job summary",
    "skeptic gate",
]


def _load(path: Path) -> dict[str, object]:
    loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert isinstance(loaded, dict)
    return loaded


def test_action_is_composite_with_card_inputs() -> None:
    action = _load(ACTION_PATH)
    runs = action["runs"]
    assert isinstance(runs, dict)
    assert runs["using"] == "composite"
    inputs = action["inputs"]
    assert isinstance(inputs, dict)
    assert set(inputs) == {
        "config",
        "suite",
        "agent",
        "profile",
        "guards",
        "min-sks",
        "max-cost-usd",
        "upload-report",
    }
    assert inputs["agent"]["required"] is True
    assert inputs["suite"]["default"] == "smoke"
    assert inputs["profile"]["default"] == "silent-core"
    assert inputs["guards"]["default"] == ""
    assert inputs["config"]["default"] == ""
    assert str(inputs["min-sks"]["default"]) == "70"
    assert str(inputs["max-cost-usd"]["default"]) == "5"
    assert str(inputs["upload-report"]["default"]) == "true"
    outputs = action["outputs"]
    assert isinstance(outputs, dict)
    assert set(outputs) == {"sks", "fsr", "report-path"}
    for name in ("sks", "fsr", "report-path"):
        value = outputs[name]["value"]
        assert isinstance(value, str)
        assert "steps.publish.outputs." + name in value


def test_action_steps_follow_the_card() -> None:
    action = _load(ACTION_PATH)
    runs = action["runs"]
    assert isinstance(runs, dict)
    steps = runs["steps"]
    assert isinstance(steps, list)
    assert [step["name"] for step in steps] == STEP_NAMES

    assert steps[0]["uses"] == "astral-sh/setup-uv@v6"
    assert steps[0]["with"]["python-version"] == "3.12"

    install = steps[1]["run"]
    assert "uv sync --locked --project" in install
    assert "skeptic --version" in install
    assert "pip install" not in install

    run_step = steps[2]["run"]
    for flag in (
        "--suite",
        "--agent",
        "--profile",
        "--max-cost-usd",
        "--out",
        "--ledger",
        "skeptic.yaml",
    ):
        assert flag in run_step
    assert "--guards" in run_step

    assert "skeptic report" in steps[3]["run"]

    upload = steps[4]
    assert upload["if"] == "inputs.upload-report == 'true'"
    assert upload["uses"] == "actions/upload-artifact@v4"
    assert upload["with"]["name"] == "skeptic-report"

    summary = steps[5]
    assert summary["id"] == "publish"
    assert "report.md" in summary["run"]
    assert "GITHUB_STEP_SUMMARY" in summary["run"]
    assert "GITHUB_OUTPUT" in summary["run"]
    assert "sks=" in summary["run"]
    assert "fsr=" in summary["run"]
    assert "report-path=" in summary["run"]

    gate = steps[6]["run"]
    assert "skeptic gate" in gate
    assert "--min-sks" in gate


def test_example_workflow_is_the_ci_workflow() -> None:
    example = EXAMPLE_WORKFLOW.read_bytes()
    ci = CI_WORKFLOW.read_bytes()
    assert example == ci
    assert b"\r\n" not in example

    workflow = _load(EXAMPLE_WORKFLOW)
    jobs = workflow["jobs"]
    assert isinstance(jobs, dict)
    pass_job = jobs["pass"]
    fail_job = jobs["gate-fail"]
    confirm = jobs["gate-fail-was-red"]
    assert isinstance(pass_job, dict)
    assert isinstance(fail_job, dict)
    assert isinstance(confirm, dict)

    pass_action = pass_job["steps"][1]
    assert pass_action["uses"] == "./"
    assert pass_action["with"]["agent"] == "reference:fake/oracle_follower"
    assert pass_action["with"]["suite"] == "smoke"
    assert pass_action["with"]["profile"] == "none"
    assert str(pass_action["with"]["min-sks"]) == "70"

    fail_action = fail_job["steps"][1]
    assert fail_job["continue-on-error"] is True
    assert fail_action["uses"] == "./"
    assert fail_action["continue-on-error"] is True
    assert fail_action["with"]["agent"] == "reference:fake/oracle_follower"
    assert str(fail_action["with"]["min-sks"]) == "101"
    assert str(fail_action["with"]["upload-report"]) == "false"
    assert fail_job["steps"][2]["if"] == "steps.skeptic.outcome == 'failure'"
    assert confirm["needs"] == "gate-fail"
    assert 'outcome" != "failure"' in confirm["steps"][0]["run"]
