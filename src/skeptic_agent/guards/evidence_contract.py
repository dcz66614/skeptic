"""G01 Evidence Contract Guard (S11).

Appends an evidence contract reminder block to the end of each tools/call result content:
"[skeptic:evidence] Before relying on this result, check that it answers the request
(right entity, date, units, completeness). If it is empty, truncated, stale, inconsistent
or an error, reply with \\"RETRIEVAL_STATUS: FAILED\\" and do not invent values."
"""

from typing import Any

from skeptic_agent.guards.base import Guard, GuardResult, register
from skeptic_agent.jsonrpc import ErrorResponse, Response
from skeptic_agent.proxy.context import EpisodeContext

EVIDENCE_CONTRACT_TEXT: str = (
    "[skeptic:evidence] Before relying on this result, check that it answers the request "
    "(right entity, date, units, completeness). If it is empty, truncated, stale, inconsistent "
    'or an error, reply with "RETRIEVAL_STATUS: FAILED" and do not invent values.'
)
"""The exact verbatim G01 text specified in S11."""


@register
class EvidenceContract(Guard):
    """G01 evidence_contract Guard (S11, s2c step ④).

    Appends the evidence contract text block to the content of every tools/call result.
    """

    id: str = "evidence_contract"
    hooks: tuple[str, ...] = ("s2c_call",)

    def on_s2c_call(
        self, msg: Response | ErrorResponse, ctx: EpisodeContext, tool_name: str | None
    ) -> GuardResult | None:
        """Append evidence contract block to tools/call response content.

        Args:
            msg: Server response.
            ctx: Episode context.
            tool_name: Name of tool called.

        Returns:
            GuardResult with rewritten response and note, or None if not applicable.
        """
        del ctx
        if not isinstance(msg, Response) or not isinstance(msg.result, dict):
            return None

        # S4.5: resultType other than "complete" is left alone
        if msg.result.get("resultType", "complete") != "complete":
            return None

        result: dict[str, Any] = dict(msg.result)
        raw_content = result.get("content")
        content: list[dict[str, Any]] = (
            [dict(c) for c in raw_content if isinstance(c, dict)]
            if isinstance(raw_content, list)
            else []
        )
        content.append({"type": "text", "text": EVIDENCE_CONTRACT_TEXT})
        result["content"] = content

        rewritten = msg.model_copy(update={"result": result, "raw_bytes": b""})
        note = {
            "id": self.id,
            "action": "contract_appended",
            "detail": f"tool '{tool_name or '*'}' result appended evidence contract",
        }
        return GuardResult(msg=rewritten, note=note)
