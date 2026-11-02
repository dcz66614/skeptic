"""Scoring package: evaluation checks, outcome classification, and judge (E46, S10.2)."""

from skeptic_agent.scoring.checks import (
    evaluate_check,
    evaluate_checks,
    evaluate_forbid,
    extract_c2s_tool_calls,
    extract_numbers,
    match_args,
)
from skeptic_agent.scoring.judge import (
    JudgeConfig,
    JudgeVerdict,
    LLMJudge,
    spot_check_with_judge,
)
from skeptic_agent.scoring.outcome import (
    ALL_OUTCOMES,
    HONEST_FAILURE_MARKERS,
    EpisodeScore,
    Outcome,
    OutcomeType,
    check_injection_complied,
    classify_outcome,
    detect_loop,
    detect_problem,
    matches_honest_failure,
    score_episode,
)

__all__ = [
    "ALL_OUTCOMES",
    "HONEST_FAILURE_MARKERS",
    "EpisodeScore",
    "JudgeConfig",
    "JudgeVerdict",
    "LLMJudge",
    "Outcome",
    "OutcomeType",
    "check_injection_complied",
    "classify_outcome",
    "detect_loop",
    "detect_problem",
    "evaluate_check",
    "evaluate_checks",
    "evaluate_forbid",
    "extract_c2s_tool_calls",
    "extract_numbers",
    "match_args",
    "matches_honest_failure",
    "score_episode",
    "spot_check_with_judge",
]
