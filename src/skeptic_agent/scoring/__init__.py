"""Scoring package: evaluation checks, outcomes, judge, metrics, and bootstrap (E46, E47)."""

from skeptic_agent.scoring.bootstrap import (
    compute_bootstrap_ci,
    intervals_overlap,
    rank_configurations,
)
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
from skeptic_agent.scoring.metrics import (
    DEFAULT_SKS_WEIGHTS,
    ConfidenceInterval,
    PointMetrics,
    ReportMetrics,
    SKSScore,
    calculate_sks,
    compute_metrics,
    compute_point_metrics,
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
    "DEFAULT_SKS_WEIGHTS",
    "HONEST_FAILURE_MARKERS",
    "ConfidenceInterval",
    "EpisodeScore",
    "JudgeConfig",
    "JudgeVerdict",
    "LLMJudge",
    "Outcome",
    "OutcomeType",
    "PointMetrics",
    "ReportMetrics",
    "SKSScore",
    "calculate_sks",
    "check_injection_complied",
    "classify_outcome",
    "compute_bootstrap_ci",
    "compute_metrics",
    "compute_point_metrics",
    "detect_loop",
    "detect_problem",
    "evaluate_check",
    "evaluate_checks",
    "evaluate_forbid",
    "extract_c2s_tool_calls",
    "extract_numbers",
    "intervals_overlap",
    "match_args",
    "matches_honest_failure",
    "rank_configurations",
    "score_episode",
    "spot_check_with_judge",
]
