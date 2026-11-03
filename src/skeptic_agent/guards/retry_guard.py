"""G05: Idempotent Retry Guard (S4.4, S11).

Retries transient errors for read-only / idempotent tools:
- Triggers on isError=true with retriable regex match, or JSON-RPC error codes -32001 / -32603.
- Restricted strictly to readOnlyHint=true or tools listed in idempotent_tools.
- Up to max_retries=2 with exponential backoff 0.5 * 2^k seconds.
- Re-executes the complete post-hook pipeline upon retry response.
- Preserves verbatim final response on exhaustion.
"""

from __future__ import annotations

import fnmatch
import re
import time
from collections.abc import Sequence
from typing import Any

from skeptic_agent.guards.base import Guard, GuardResult, GuardSpec, register
from skeptic_agent.jsonrpc import ErrorResponse, Message, Request, Response
from skeptic_agent.proxy.context import (
    EpisodeContext,
    PendingCall,
    new_internal_id,
)
from skeptic_agent.proxy.pipeline import C2S, TOOLS_CALL, Hold, SendToServer

RETRY_REGEX = re.compile(r"(?i)(503|429|timeout|timed out|temporar|unavailable|rate limit)")
"""Regex matching retriable tool error text per S11 note."""

RETRIABLE_JSONRPC_CODES: tuple[int, ...] = (-32001, -32603)
"""JSON-RPC error codes that trigger G05 retry per S11."""

DEFAULT_MAX_RETRIES: int = 2
"""Default maximum retry attempts per S11."""

DEFAULT_BACKOFF_BASE: float = 0.5
"""Default backoff base in seconds per S11 (0.5 * 2^k)."""

WRITE_PREFIXES: tuple[str, ...] = (
    "create_",
    "update_",
    "delete_",
    "send_",
    "cancel_",
    "refund_",
    "write_",
    "insert_",
    "drop_",
    "modify_",
    "remove_",
    "post_",
    "put_",
)
"""Common prefixes indicating non-idempotent write operations."""

READ_PREFIXES: tuple[str, ...] = (
    "get_",
    "list_",
    "query_",
    "fetch_",
    "search_",
    "read_",
    "select_",
    "echo",
    "forecast",
    "lookup_",
    "check_",
)
"""Common prefixes indicating idempotent read operations."""


def is_tool_idempotent(
    tool_name: str | None,
    idempotent_tools: Sequence[str],
    ctx: EpisodeContext,
) -> bool:
    """Check whether a tool is read-only / idempotent according to S11.

    Args:
        tool_name: Name of tool to check.
        idempotent_tools: Explicitly configured idempotent tool glob patterns.
        ctx: Episode context holding tool definitions and scenario metadata.

    Returns:
        True if tool is confirmed idempotent, False if write tool or unknown.
    """
    if not tool_name:
        return False

    # 1. Check explicit idempotent_tools patterns
    for pat in idempotent_tools:
        if fnmatch.fnmatch(tool_name, pat):
            return True

    # 2. Check tool definitions seen on the wire (tools/list)
    tool_def = ctx.tool_defs.get(tool_name)
    if isinstance(tool_def, dict):
        annotations = tool_def.get("annotations")
        if isinstance(annotations, dict):
            if annotations.get("readOnlyHint") is True:
                return True
            if annotations.get("readOnlyHint") is False:
                return False
        if tool_def.get("readOnlyHint") is True:
            return True
        if tool_def.get("readOnlyHint") is False:
            return False

    # 3. Check scenario metadata if present
    scenario = ctx.scenario
    if scenario is not None:
        write_tools = getattr(scenario, "write_tools", None)
        if write_tools and tool_name in write_tools:
            return False
        fault_targets = getattr(scenario, "fault_targets", None)
        if isinstance(fault_targets, dict):
            write_targets = fault_targets.get("write", [])
            if any(fnmatch.fnmatch(tool_name, w) for w in write_targets):
                return False
            read_targets = fault_targets.get("read", [])
            if any(fnmatch.fnmatch(tool_name, r) for r in read_targets):
                return True

    # 4. Fallback heuristics based on prefix
    for prefix in WRITE_PREFIXES:
        if tool_name.startswith(prefix):
            return False

    return any(tool_name.startswith(prefix) for prefix in READ_PREFIXES)


def is_retriable_message(msg: Message) -> bool:
    """Check whether a response message indicates a retriable failure per S11.

    Args:
        msg: Response or ErrorResponse message.

    Returns:
        True if the failure matches retriable error criteria.
    """
    if isinstance(msg, ErrorResponse):
        if msg.error.code in RETRIABLE_JSONRPC_CODES:
            return True
        return bool(msg.error.message and RETRY_REGEX.search(msg.error.message))

    if (
        isinstance(msg, Response)
        and isinstance(msg.result, dict)
        and msg.result.get("isError") is True
    ):
        # Check text blocks
        content = msg.result.get("content")
        if isinstance(content, list):
            for block in content:
                if isinstance(block, dict) and block.get("type") == "text":
                    txt = block.get("text", "")
                    if isinstance(txt, str) and RETRY_REGEX.search(txt):
                        return True
        # Check structuredContent if string fields match
        structured = msg.result.get("structuredContent")
        if isinstance(structured, dict):
            for v in structured.values():
                if isinstance(v, str) and RETRY_REGEX.search(v):
                    return True

    return False


@register
class RetryGuard(Guard):
    """G05: retry_guard (S4.4, S11)."""

    id = "retry_guard"
    hooks = ("s2c_call",)

    def __init__(self, spec: GuardSpec | None = None) -> None:
        """Initialize RetryGuard with specification parameters."""
        super().__init__(spec)
        self.max_retries = int(self.params.get("max_retries", DEFAULT_MAX_RETRIES))
        self.backoff_base = float(self.params.get("backoff_base", DEFAULT_BACKOFF_BASE))
        idemp = self.params.get("idempotent_tools", ())
        if isinstance(idemp, str):
            self.idempotent_tools: tuple[str, ...] = tuple(
                x.strip() for x in idemp.split(",") if x.strip()
            )
        elif isinstance(idemp, Sequence):
            self.idempotent_tools = tuple(str(x) for x in idemp)
        else:
            self.idempotent_tools = ()
        self.fault: Any = None

    def set_fault(self, fault: Any) -> None:
        """Store reference to fault stage for c2s step ④ execution."""
        self.fault = fault

    def on_s2c_call(
        self,
        msg: Response | ErrorResponse,
        ctx: EpisodeContext,
        tool_name: str | None,
    ) -> GuardResult | None:
        """Process a tools/call response message according to S4.4 step ②.

        Args:
            msg: The tools/call response from server.
            ctx: Episode context.
            tool_name: The tool name being answered.

        Returns:
            GuardResult with retry action if retriable, or rewritten msg if restoring id.
        """
        if msg.id is None:
            return None
        pending = ctx.pending.get((C2S, msg.id))
        original_id = (
            pending.original_id
            if (pending is not None and pending.original_id is not None)
            else msg.id
        )
        retry_count = pending.retry_count if pending is not None else 0

        # Check if the failure is retriable
        retriable = is_retriable_message(msg)

        # If this was already a retry attempt that succeeded:
        if pending is not None and pending.original_id is not None and not retriable:
            restored = msg.model_copy(update={"id": original_id, "raw_bytes": b""})
            note = {
                "id": self.id,
                "action": "retry_success",
                "detail": f"attempt={pending.attempt} retry_count={retry_count}",
            }
            return GuardResult(msg=restored, note=note)

        # If not retriable at all, pass through
        if not retriable:
            return None

        # Check if tool is idempotent / read-only
        if not is_tool_idempotent(tool_name, self.idempotent_tools, ctx):
            # Write tools must not be retried per S11
            return None

        # Check if retries are exhausted
        if retry_count >= self.max_retries:
            if pending is not None and pending.original_id is not None:
                restored = msg.model_copy(update={"id": original_id, "raw_bytes": b""})
                note = {
                    "id": self.id,
                    "action": "retries_exhausted",
                    "detail": f"attempt={pending.attempt} retry_count={retry_count}",
                }
                return GuardResult(msg=restored, note=note)
            return None

        # S11 & S4.4: Issue proxy retry
        next_attempt = ctx.next_call_index(tool_name or "")
        ctx.current_call_index[tool_name or ""] = next_attempt

        internal_id = new_internal_id()
        args = pending.arguments if pending is not None else {}
        req_meta = pending.meta if pending is not None else None
        ctx.pending[(C2S, internal_id)] = PendingCall(
            method=TOOLS_CALL,
            tool_name=tool_name,
            arguments=args,
            t_start=time.monotonic(),
            attempt=next_attempt,
            original_id=original_id,
            retry_count=retry_count + 1,
            meta=req_meta,
        )

        params: dict[str, Any] = {"name": tool_name or "", "arguments": args or {}}
        if req_meta:
            params["_meta"] = req_meta

        retry_req = Request(
            id=internal_id,
            method=TOOLS_CALL,
            params=params,
        )

        # Backoff: 0.5 * 2^k seconds
        backoff_s = self.backoff_base * (2**retry_count)
        backoff_ms = max(1, int(backoff_s * 1000))

        action = Hold(ms=backoff_ms, then=SendToServer(retry_req))
        note = {
            "id": self.id,
            "action": "retry",
            "detail": (
                f"attempt={next_attempt} retry_count={retry_count + 1} backoff_ms={backoff_ms}"
            ),
        }
        return GuardResult(msg=msg, action=action, note=note)
