"""Data loader and cassette inspector for report generation (S12, E49)."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from skeptic_agent.runner.matrix import build_summary_doc


@dataclass
class ToolCallDiff:
    """Representation of an intercepted tool call with raw vs final comparison."""

    seq: int
    t_ms: int
    tool: str
    arguments: dict[str, Any]
    raw_result: Any | None = None
    raw_error: Any | None = None
    final_result: Any | None = None
    final_error: Any | None = None
    fault: dict[str, Any] | None = None
    guards: list[dict[str, Any]] = field(default_factory=list)
    dropped: bool = False
    modified: bool = False

    def to_dict(self) -> dict[str, Any]:
        """Convert to JSON-serializable dictionary."""
        return {
            "seq": self.seq,
            "t_ms": self.t_ms,
            "tool": self.tool,
            "arguments": self.arguments,
            "raw_result": self.raw_result,
            "raw_error": self.raw_error,
            "final_result": self.final_result,
            "final_error": self.final_error,
            "fault": self.fault,
            "guards": self.guards,
            "dropped": self.dropped,
            "modified": self.modified,
        }


@dataclass
class EpisodeReportDetail:
    """Consolidated episode information for reports and interactive exploration."""

    episode_id: str
    scenario_id: str
    sandbox: str
    seed: int
    outcome: str
    fault_id: str | None = None
    fault_class: str | None = None
    recoverability: str | None = None
    kind: str | None = None
    final_answer: str = ""
    checks: list[dict[str, Any]] = field(default_factory=list)
    forbid_hits: list[dict[str, Any]] = field(default_factory=list)
    flags: dict[str, Any] = field(default_factory=dict)
    usage: dict[str, Any] = field(default_factory=dict)
    cassette_path: str = ""
    error: str | None = None
    tool_calls: list[ToolCallDiff] = field(default_factory=list)
    raw_transcript: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Convert to JSON-serializable dictionary."""
        return {
            "episode_id": self.episode_id,
            "scenario_id": self.scenario_id,
            "sandbox": self.sandbox,
            "seed": self.seed,
            "outcome": self.outcome,
            "fault_id": self.fault_id,
            "fault_class": self.fault_class,
            "recoverability": self.recoverability,
            "kind": self.kind,
            "final_answer": self.final_answer,
            "checks": self.checks,
            "forbid_hits": self.forbid_hits,
            "flags": self.flags,
            "usage": self.usage,
            "cassette_path": self.cassette_path,
            "error": self.error,
            "tool_calls": [tc.to_dict() for tc in self.tool_calls],
            "raw_transcript": self.raw_transcript,
        }


@dataclass
class RunData:
    """All loaded run artifacts and parsed details ready for report formatting."""

    run_dir: Path
    summary: dict[str, Any]
    episodes: list[EpisodeReportDetail]

    @property
    def run_id(self) -> str:
        return str(self.summary.get("run_id", "unknown"))

    @property
    def sks_score(self) -> float:
        try:
            return float(self.summary["agents"][0]["metrics"]["SKS"]["estimate"])
        except (KeyError, IndexError, TypeError, ValueError):
            return 0.0

    @property
    def sks_ci(self) -> tuple[float, float]:
        try:
            sks_obj = self.summary["agents"][0]["metrics"]["SKS"]
            return float(sks_obj.get("low", 0.0)), float(sks_obj.get("high", 0.0))
        except (KeyError, IndexError, TypeError, ValueError):
            return 0.0, 0.0

    @property
    def is_partial_sks(self) -> bool:
        try:
            return bool(self.summary["agents"][0]["metrics"]["SKS"].get("partial", False))
        except (KeyError, IndexError, TypeError):
            return False


def parse_cassette_file(cassette_file: Path) -> tuple[list[ToolCallDiff], list[dict[str, Any]]]:
    """Parse a cassette JSONL file to extract tool call diffs and full message sequence.

    Args:
        cassette_file: Path to the cassette JSONL file.

    Returns:
        (tool_calls, raw_transcript) tuple.
    """
    if not cassette_file.is_file():
        return [], []

    messages: list[dict[str, Any]] = []
    try:
        with open(cassette_file, encoding="utf-8") as f:
            for line in f:
                line_str = line.strip()
                if not line_str:
                    continue
                try:
                    messages.append(json.loads(line_str))
                except json.JSONDecodeError:
                    continue
    except OSError:
        return [], []

    # Map request id to c2s tools/call message
    pending_c2s: dict[Any, dict[str, Any]] = {}
    tool_calls: list[ToolCallDiff] = []
    transcript: list[dict[str, Any]] = []

    for msg in messages:
        mtype = msg.get("type")
        if mtype != "msg":
            continue

        transcript.append(msg)
        mdir = msg.get("dir")
        raw = msg.get("raw") or {}
        final = msg.get("final") or {}

        if mdir == "c2s":
            # Check if this is tools/call
            if raw.get("method") == "tools/call":
                req_id = raw.get("id")
                if req_id is not None:
                    pending_c2s[req_id] = msg
        elif mdir == "s2c":
            resp_id = raw.get("id") if raw else final.get("id")
            c2s_msg = pending_c2s.pop(resp_id, None)

            # If response corresponds to a tools/call request
            if c2s_msg:
                c2s_raw = c2s_msg.get("raw") or {}
                params = c2s_raw.get("params") or {}
                tool_name = str(params.get("name", "unknown"))
                arguments = params.get("arguments") or {}

                raw_result = raw.get("result") if raw else None
                raw_error = raw.get("error") if raw else None
                final_result = final.get("result") if final else None
                final_error = final.get("error") if final else None

                fault_info = msg.get("fault") or c2s_msg.get("fault")
                guards_list = msg.get("guards") or c2s_msg.get("guards") or []
                dropped = bool(msg.get("dropped", False))

                # Modified if raw != final, or fault / guard intervened
                modified = (raw != final) or bool(fault_info) or bool(guards_list) or dropped

                tc_args = arguments if isinstance(arguments, dict) else {"_args": arguments}
                tool_calls.append(
                    ToolCallDiff(
                        seq=int(msg.get("seq", len(tool_calls))),
                        t_ms=int(msg.get("t_ms", 0)),
                        tool=tool_name,
                        arguments=tc_args,
                        raw_result=raw_result,
                        raw_error=raw_error,
                        final_result=final_result,
                        final_error=final_error,
                        fault=fault_info,
                        guards=guards_list if isinstance(guards_list, list) else [],
                        dropped=dropped,
                        modified=modified,
                    )
                )

    return tool_calls, transcript


def load_run_data(run_dir: str | Path) -> RunData:
    """Load run results, summary, and cassette interactions from run directory.

    Args:
        run_dir: Path to directory containing results.jsonl and/or summary.json.

    Returns:
        Consolidated RunData.

    Raises:
        FileNotFoundError: If neither results.jsonl nor summary.json exists.
        ValueError: If neither can be decoded or validated.
    """
    path = Path(run_dir)
    dir_path = path.parent if path.is_file() else path

    summary_file = dir_path / "summary.json"
    results_file = dir_path / "results.jsonl"

    if not summary_file.is_file() and not results_file.is_file():
        raise FileNotFoundError(f"Neither summary.json nor results.jsonl found in {dir_path}")

    # 1. Load results.jsonl lines if present
    results_eps: list[dict[str, Any]] = []
    if results_file.is_file():
        with open(results_file, encoding="utf-8") as f:
            for line in f:
                line_str = line.strip()
                if line_str:
                    try:
                        results_eps.append(json.loads(line_str))
                    except json.JSONDecodeError:
                        continue

    # 2. Load summary.json or build it
    summary_doc: dict[str, Any]
    if summary_file.is_file():
        try:
            summary_doc = json.loads(summary_file.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            if not results_eps:
                raise ValueError(f"Failed to decode summary.json in {dir_path}: {exc}") from exc
            summary_doc = build_summary_doc(
                run_id=results_eps[0].get("run_id", "20261105-000000-000000"),
                episodes=results_eps,
                command="",
                config={},
            )
    else:
        # Build summary doc from results.jsonl
        default_run_id = (
            results_eps[0].get("run_id", "20261105-000000-000000")
            if results_eps
            else "20261105-000000-000000"
        )
        summary_doc = build_summary_doc(
            run_id=default_run_id,
            episodes=results_eps,
            command="",
            config={},
        )

    # Ensure episodes brief list is present on summary_doc
    if "episodes" not in summary_doc or not summary_doc["episodes"]:
        ep_briefs: list[dict[str, Any]] = []
        for ep in results_eps:
            ep_briefs.append(
                {
                    "episode_id": ep["episode_id"],
                    "scenario_id": ep["scenario_id"],
                    "sandbox": ep["sandbox"],
                    "seed": ep["seed"],
                    "outcome": ep["outcome"],
                    "fault_id": (ep.get("fault") or {}).get("id") if ep.get("fault") else None,
                    "kind": ep.get("kind"),
                    "cassette": ep.get("cassette", ""),
                }
            )
        if ep_briefs:
            summary_doc["episodes"] = ep_briefs

    # Build index of detailed episodes from results_eps
    detailed_by_id: dict[str, dict[str, Any]] = {
        ep["episode_id"]: ep for ep in results_eps if "episode_id" in ep
    }

    # Consolidated episodes
    consolidated_episodes: list[EpisodeReportDetail] = []
    ep_source_list = summary_doc.get("episodes") or results_eps

    for ep_item in ep_source_list:
        ep_id = ep_item.get("episode_id", "")
        detail = detailed_by_id.get(ep_id, ep_item)

        scen_id = detail.get("scenario_id", ep_item.get("scenario_id", ""))
        sandbox = detail.get("sandbox", ep_item.get("sandbox", ""))
        seed = int(detail.get("seed", ep_item.get("seed", 0)))
        outcome = detail.get("outcome", ep_item.get("outcome", "UNKNOWN"))

        f_info = detail.get("fault") or {}
        fault_id = f_info.get("id") if isinstance(f_info, dict) else ep_item.get("fault_id")
        fault_class = f_info.get("class") if isinstance(f_info, dict) else None

        recoverability = detail.get("recoverability")
        kind = detail.get("kind", ep_item.get("kind"))
        final_answer = detail.get("final_answer", "")
        checks = detail.get("checks", [])
        forbid_hits = detail.get("forbid_hits", [])
        flags = detail.get("flags", {})
        usage = detail.get("usage", {})
        cassette_rel = detail.get("cassette") or ep_item.get("cassette", "")
        error = detail.get("error")

        # Discover cassette file location
        tool_calls: list[ToolCallDiff] = []
        raw_transcript: list[dict[str, Any]] = []
        if cassette_rel:
            candidate_paths = [
                dir_path / cassette_rel,
                dir_path / "cassettes" / Path(cassette_rel).name,
                Path(cassette_rel),
            ]
            for c_path in candidate_paths:
                if c_path.is_file():
                    tool_calls, raw_transcript = parse_cassette_file(c_path)
                    break

        consolidated_episodes.append(
            EpisodeReportDetail(
                episode_id=ep_id,
                scenario_id=scen_id,
                sandbox=sandbox,
                seed=seed,
                outcome=outcome,
                fault_id=fault_id,
                fault_class=fault_class,
                recoverability=recoverability,
                kind=kind,
                final_answer=final_answer,
                checks=checks,
                forbid_hits=forbid_hits,
                flags=flags,
                usage=usage,
                cassette_path=cassette_rel,
                error=error,
                tool_calls=tool_calls,
                raw_transcript=raw_transcript,
            )
        )

    return RunData(
        run_dir=dir_path,
        summary=summary_doc,
        episodes=consolidated_episodes,
    )
