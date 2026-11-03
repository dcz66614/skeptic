"""G08: Tool Definition Drift Lock (S4.4, S11).

Guards against runtime tool definition drift (A02, A03, L07):
- Intercepts ``tools/list`` responses (s2c tools/list step ②):
  On first observation of each tool, computes and records:
  ``sha256(canonical(name, description, inputSchema))``.
  When the hash changes in subsequent listings:
  - Prints warning to stderr.
  - mode=pin (default): returns the initially approved definition.
  - mode=strip: removes the drifted tool from the list.
- Intercepts ``tools/call`` requests (c2s):
  For drifted tools, validates arguments against the initial approved ``inputSchema``.
  If arguments do not conform (or if tool was stripped), directly blocks the call:
  ``[skeptic:drift_lock] Tool definition changed after approval; call blocked.``
"""

from __future__ import annotations

import copy
import hashlib
import json
import sys
from typing import Any, Literal

import jsonschema

from skeptic_agent.guards.base import Guard, GuardResult, GuardSpec, loudify, register
from skeptic_agent.jsonrpc import ErrorResponse, Request, Response
from skeptic_agent.proxy.context import EpisodeContext
from skeptic_agent.proxy.pipeline import ReplyToClient

DRIFT_LOCK_BLOCKED_TEXT: str = (
    "[skeptic:drift_lock] Tool definition changed after approval; call blocked."
)
"""Verbatim blocking error text per S11."""


def canonical_tool_hash(tool: dict[str, Any]) -> str:
    """Compute sha256 of canonical(name, description, inputSchema) per S11.

    Args:
        tool: Tool definition dictionary from tools/list.

    Returns:
        Hex-encoded sha256 digest string.
    """
    canonical_repr = {
        "description": tool.get("description", ""),
        "inputSchema": tool.get("inputSchema", {}),
        "name": tool.get("name", ""),
    }
    raw = json.dumps(canonical_repr, sort_keys=True, ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


@register
class DriftLock(Guard):
    """G08: drift_lock (S4.4, S11)."""

    id = "drift_lock"
    hooks = ("s2c_list", "c2s")

    def __init__(self, spec: GuardSpec | None = None) -> None:
        """Initialize DriftLock."""
        super().__init__(spec)
        raw_mode = str(self.params.get("mode", "pin")).strip().lower()
        self.mode: Literal["pin", "strip"] = "strip" if raw_mode == "strip" else "pin"
        self._initial_tools: dict[str, dict[str, Any]] = {}
        self._initial_hashes: dict[str, str] = {}
        self._drifted_tools: set[str] = set()

    def reset(self) -> None:
        """Reset internal tool snapshots and drift tracking."""
        self._initial_tools.clear()
        self._initial_hashes.clear()
        self._drifted_tools.clear()

    def on_s2c_list(self, msg: Response | ErrorResponse, ctx: EpisodeContext) -> GuardResult | None:
        """Inspect tools/list response, detect definition drift, and pin or strip."""
        if not isinstance(msg, Response) or not isinstance(msg.result, dict):
            return None

        tools = msg.result.get("tools")
        if not isinstance(tools, list):
            return None

        modified = False
        new_tools_list: list[dict[str, Any]] = []
        action_notes: list[dict[str, Any]] = []

        # If scenario carries pre-approved tools and we have not seeded them yet:
        if not self._initial_tools and ctx.scenario is not None:
            scen_tools = getattr(ctx.scenario, "tools", None)
            if isinstance(scen_tools, list):
                for st in scen_tools:
                    if isinstance(st, dict) and "name" in st:
                        s_name = str(st["name"])
                        self._initial_tools[s_name] = copy.deepcopy(st)
                        self._initial_hashes[s_name] = canonical_tool_hash(st)

        for tool in tools:
            if not isinstance(tool, dict) or "name" not in tool:
                new_tools_list.append(tool)
                continue

            name = str(tool["name"])
            curr_hash = canonical_tool_hash(tool)

            if name not in self._initial_tools:
                # First time seeing this tool: record baseline
                self._initial_tools[name] = copy.deepcopy(tool)
                self._initial_hashes[name] = curr_hash
                new_tools_list.append(tool)
            else:
                old_hash = self._initial_hashes[name]
                if curr_hash != old_hash:
                    # Definition drift detected!
                    self._drifted_tools.add(name)
                    sys.stderr.write(
                        f"[skeptic:drift_lock] Warning: Tool definition for '{name}' "
                        f"changed after approval (hash {old_hash[:8]} -> {curr_hash[:8]})\n"
                    )
                    sys.stderr.flush()

                    if self.mode == "pin":
                        # Return the initially recorded definition
                        pinned_def = copy.deepcopy(self._initial_tools[name])
                        new_tools_list.append(pinned_def)
                        modified = True
                        action_notes.append(
                            {"id": self.id, "action": "drift_pin", "detail": f"tool={name}"}
                        )
                    elif self.mode == "strip":
                        # Exclude the tool from the list
                        modified = True
                        action_notes.append(
                            {"id": self.id, "action": "drift_strip", "detail": f"tool={name}"}
                        )
                else:
                    new_tools_list.append(tool)

        if modified:
            new_result = copy.deepcopy(msg.result)
            new_result["tools"] = new_tools_list
            new_msg = msg.model_copy(update={"result": new_result, "raw_bytes": b""})
            note = (
                action_notes[0] if action_notes else {"id": self.id, "action": f"drift_{self.mode}"}
            )
            return GuardResult(msg=new_msg, note=note)

        return None

    def on_c2s(self, msg: Request, ctx: EpisodeContext) -> GuardResult | None:
        """Validate calls to drifted tools against initial inputSchema."""
        del ctx
        if msg.method != "tools/call":
            return None

        params = msg.params if isinstance(msg.params, dict) else {}
        tool_name = params.get("name")
        if not tool_name or tool_name not in self._drifted_tools:
            return None

        # If stripped, all calls are blocked
        if self.mode == "strip":
            error_res = loudify(DRIFT_LOCK_BLOCKED_TEXT)
            reply = Response(id=msg.id, result=error_res)
            note = {
                "id": self.id,
                "action": "blocked",
                "detail": f"tool={tool_name} reason=stripped",
            }
            return GuardResult(msg=msg, action=ReplyToClient(reply), note=note)

        # In pin mode, validate arguments against initial inputSchema
        initial_def = self._initial_tools.get(tool_name)
        if not initial_def:
            return None

        input_schema = initial_def.get("inputSchema")
        if isinstance(input_schema, dict) and input_schema:
            arguments = params.get("arguments", {})
            try:
                jsonschema.Draft202012Validator(input_schema).validate(arguments)
            except jsonschema.ValidationError:
                # Arguments fail approved schema validation
                error_res = loudify(DRIFT_LOCK_BLOCKED_TEXT)
                reply = Response(id=msg.id, result=error_res)
                note = {
                    "id": self.id,
                    "action": "blocked",
                    "detail": f"tool={tool_name} reason=schema_mismatch",
                }
                return GuardResult(msg=msg, action=ReplyToClient(reply), note=note)

        return None
