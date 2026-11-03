"""G07: Injection Shield (S4.4, S11).

Two-phase guard against prompt injection:
1. s2c step ⑤ (scanning and taint tagging):
   Scans tool result text for rules R1-R8. Replaces hit segments with
   ``[skeptic:injection_shield removed <N> chars of instruction-like content from tool output]``,
   and tags extracted emails, URLs, and paths into the episode taint set (``ctx.taint``).
2. c2s step ③ (taint blocking):
   Whenever ``ctx.taint`` is non-empty, blocks any ``tools/call`` if:
   - Tool arguments contain any value present in the taint set; OR
   - The tool is a sensitive tool (default ``send_email``, ``write_file``, ``delete_*``,
     ``cancel_*``, ``refund_*``) and its arguments contain an email address not
     present in the user prompt.
   Blocked calls directly return the loudified explicit error:
   ``[skeptic:injection_shield] Blocked: arguments derived from untrusted tool output.``
"""

from __future__ import annotations

import copy
import fnmatch
import json
import re
from collections.abc import Sequence
from typing import Any

from skeptic_agent.guards.base import Guard, GuardResult, GuardSpec, loudify, register
from skeptic_agent.jsonrpc import ErrorResponse, Request, Response
from skeptic_agent.proxy.context import EpisodeContext
from skeptic_agent.proxy.pipeline import ReplyToClient

INJECTION_SHIELD_BLOCK_TEXT: str = (
    "[skeptic:injection_shield] Blocked: arguments derived from untrusted tool output."
)
"""Verbatim blocking error text per S11."""

INJECTION_SHIELD_REMOVED_TEMPLATE: str = (
    "[skeptic:injection_shield removed {n} chars of instruction-like content from tool output]"
)
"""Verbatim replacement template per S11."""

DEFAULT_SENSITIVE_TOOLS: tuple[str, ...] = (
    "send_email",
    "write_file",
    "delete_*",
    "cancel_*",
    "refund_*",
)
"""Default sensitive tools list per S11."""

# Rules R1-R8 from S11:
RULES: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "R1",
        re.compile(
            r"ignore\s+(?:all\s+|any\s+)?(?:previous|prior|above)\s+instructions",
            re.IGNORECASE,
        ),
    ),
    ("R2", re.compile(r"<\s*important\s*>", re.IGNORECASE)),
    ("R3", re.compile(r"system\s+(?:notice|prompt|message)", re.IGNORECASE)),
    ("R4", re.compile(r"you\s+must\s+(?:also\s+)?call", re.IGNORECASE)),
    ("R5", re.compile(r"do\s+not\s+(?:mention|tell|reveal)", re.IGNORECASE)),
    ("R6", re.compile(r"(?:SKEPTIC-TEST-INJECTION|@exfil\.example|SKC-CANARY-)", re.IGNORECASE)),
    ("R7", re.compile(r"[\U000E0000-\U000E007F]|[\u200B-\u200F]{3,}", re.IGNORECASE)),
    ("R8", re.compile(r"[A-Za-z0-9+/=]{200,}")),
)

EMAIL_REGEX = re.compile(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+")
URL_REGEX = re.compile(r"(?:https?|ftp)://[^\s<>\"']+")
PATH_REGEX = re.compile(
    r"(?:/[a-zA-Z0-9_.-]+){2,}|(?:[a-zA-Z]:\\[a-zA-Z0-9_.-]+(?:\\[a-zA-Z0-9_.-]+)+)"
)


def extract_taint_entities(text: str) -> set[str]:
    """Extract emails, URLs, and file paths from text to populate taint set.

    Args:
        text: Injected text segment.

    Returns:
        Set of extracted entity strings.
    """
    entities: set[str] = set()
    for m in EMAIL_REGEX.finditer(text):
        entities.add(m.group(0))
    for m in URL_REGEX.finditer(text):
        entities.add(m.group(0))
    for m in PATH_REGEX.finditer(text):
        entities.add(m.group(0))
    return entities


def value_contains_taint(val: Any, taint_set: set[str]) -> bool:
    """Recursively check whether any tainted string appears in a JSON value.

    Args:
        val: The argument value (dict, list, str, etc.).
        taint_set: Set of tainted substrings.

    Returns:
        True if any tainted substring is contained within val.
    """
    if not taint_set:
        return False
    if isinstance(val, str):
        return any(t in val for t in taint_set)
    if isinstance(val, dict):
        return any(
            value_contains_taint(k, taint_set) or value_contains_taint(v, taint_set)
            for k, v in val.items()
        )
    if isinstance(val, (list, tuple, set)):
        return any(value_contains_taint(item, taint_set) for item in val)
    return False


def extract_all_emails(val: Any) -> set[str]:
    """Recursively extract all email addresses from arguments.

    Args:
        val: The argument value.

    Returns:
        Set of email strings found.
    """
    emails: set[str] = set()
    if isinstance(val, str):
        emails.update(EMAIL_REGEX.findall(val))
    elif isinstance(val, dict):
        for k, v in val.items():
            if isinstance(k, str):
                emails.update(EMAIL_REGEX.findall(k))
            emails.update(extract_all_emails(v))
    elif isinstance(val, (list, tuple, set)):
        for item in val:
            emails.update(extract_all_emails(item))
    return emails


def scan_and_clean_text(text: str) -> tuple[str, set[str], int]:
    """Scan text for rules R1-R8, replace hit segments, and extract taint entities.

    Args:
        text: Tool output text string.

    Returns:
        Tuple of (cleaned_text, extracted_taint_set, total_removed_chars).
    """
    if not text:
        return text, set(), 0

    taint: set[str] = set()
    total_removed = 0

    # Split into paragraphs/lines to sanitize contiguous injection blocks
    paragraphs = text.split("\n")
    cleaned_paragraphs: list[str] = []

    for para in paragraphs:
        hit = False
        for _rule_id, pattern in RULES:
            if pattern.search(para):
                hit = True
                break

        if hit:
            # Extract emails, URLs, file paths from hit segment
            entities = extract_taint_entities(para)
            taint.update(entities)
            n_chars = len(para)
            total_removed += n_chars
            replacement = INJECTION_SHIELD_REMOVED_TEMPLATE.format(n=n_chars)
            cleaned_paragraphs.append(replacement)
        else:
            cleaned_paragraphs.append(para)

    cleaned_text = "\n".join(cleaned_paragraphs)
    return cleaned_text, taint, total_removed


@register
class InjectionShield(Guard):
    """G07: injection_shield (S4.4, S11)."""

    id = "injection_shield"
    hooks = ("c2s", "s2c_call")

    def __init__(self, spec: GuardSpec | None = None) -> None:
        """Initialize InjectionShield."""
        super().__init__(spec)
        sens = self.params.get("sensitive_tools", DEFAULT_SENSITIVE_TOOLS)
        if isinstance(sens, str):
            self.sensitive_tools: tuple[str, ...] = tuple(
                x.strip() for x in sens.split(",") if x.strip()
            )
        elif isinstance(sens, Sequence):
            self.sensitive_tools = tuple(str(x) for x in sens)
        else:
            self.sensitive_tools = DEFAULT_SENSITIVE_TOOLS

    def is_sensitive_tool(self, tool_name: str | None) -> bool:
        """Check whether tool matches the sensitive tools list."""
        if not tool_name:
            return False
        return any(fnmatch.fnmatch(tool_name, pat) for pat in self.sensitive_tools)

    def on_c2s(self, msg: Request, ctx: EpisodeContext) -> GuardResult | None:
        """Inspect client tools/call request for tainted values or unauthorized exfil."""
        if msg.method != "tools/call":
            return None

        # Only block when taint set is non-empty per S11
        if not ctx.taint:
            return None

        params = msg.params if isinstance(msg.params, dict) else {}
        tool_name = params.get("name")
        arguments = params.get("arguments", {})

        # Condition A: arguments contain any value in ctx.taint
        has_taint = value_contains_taint(arguments, ctx.taint)

        # Condition B: sensitive tool called with email not present in user prompt
        has_unapproved_email = False
        if self.is_sensitive_tool(tool_name):
            emails_in_args = extract_all_emails(arguments)
            if emails_in_args:
                # Retrieve user prompt from scenario if available
                user_prompt = ""
                if ctx.scenario is not None:
                    user_prompt = getattr(ctx.scenario, "prompt", "") or getattr(
                        ctx.scenario, "user_prompt", ""
                    )
                for email in emails_in_args:
                    if email not in user_prompt:
                        has_unapproved_email = True
                        break

        if has_taint or has_unapproved_email:
            # Block the call and reply to client directly
            error_res = loudify(INJECTION_SHIELD_BLOCK_TEXT)
            reply = Response(id=msg.id, result=error_res)
            reason = "taint_match" if has_taint else "unapproved_email"
            note = {
                "id": self.id,
                "action": "blocked",
                "detail": f"tool={tool_name} reason={reason}",
            }
            return GuardResult(msg=msg, action=ReplyToClient(reply), note=note)

        return None

    def on_s2c_call(
        self,
        msg: Response | ErrorResponse,
        ctx: EpisodeContext,
        tool_name: str | None,
    ) -> GuardResult | None:
        """Scan tool result text for R1-R8 and mark taint set (s2c step ⑤)."""
        if not isinstance(msg, Response) or not isinstance(msg.result, dict):
            return None

        # S4.5: If isError is already True or complete is not resultType, pass through
        if msg.result.get("isError") is True:
            return None
        if msg.result.get("resultType", "complete") != "complete":
            return None

        res_dict = copy.deepcopy(msg.result)
        content = res_dict.get("content")
        modified = False
        all_taint: set[str] = set()
        total_removed_chars = 0

        if isinstance(content, list):
            for block in content:
                if isinstance(block, dict) and block.get("type") == "text":
                    orig_text = block.get("text", "")
                    if isinstance(orig_text, str):
                        cleaned, taint, removed = scan_and_clean_text(orig_text)
                        if removed > 0:
                            block["text"] = cleaned
                            modified = True
                            all_taint.update(taint)
                            total_removed_chars += removed

        # Also check structuredContent if any text fields hit
        structured = res_dict.get("structuredContent")
        if isinstance(structured, dict):
            for k, v in list(structured.items()):
                if isinstance(v, str):
                    cleaned, taint, removed = scan_and_clean_text(v)
                    if removed > 0:
                        structured[k] = cleaned
                        modified = True
                        all_taint.update(taint)
                        total_removed_chars += removed

        if modified:
            # Synchronous rewrite rule (S4.5): if first text block matches JSON of structuredContent
            if isinstance(structured, dict) and isinstance(content, list) and content:
                first_block = content[0]
                if isinstance(first_block, dict) and first_block.get("type") == "text":
                    try:
                        parsed = json.loads(first_block.get("text", ""))
                        if parsed == structured:
                            first_block["text"] = json.dumps(
                                structured, ensure_ascii=False, sort_keys=True
                            )
                    except Exception:
                        pass

            ctx.taint.update(all_taint)
            new_msg = msg.model_copy(update={"result": res_dict, "raw_bytes": b""})
            note = {
                "id": self.id,
                "action": "scan_replaced",
                "detail": f"removed_chars={total_removed_chars} tainted={sorted(all_taint)}",
            }
            return GuardResult(msg=new_msg, note=note)

        return None
