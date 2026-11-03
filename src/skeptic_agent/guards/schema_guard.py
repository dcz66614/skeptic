"""G02 Schema Guard (S11).

Validates tool outputs against their declared outputSchema:
- When a tool declares outputSchema in tools/list:
  - Validates structuredContent against outputSchema using jsonschema.
  - If no structuredContent is present, parses text as JSON and validates against outputSchema.
  - If outputSchema is declared but neither structuredContent nor parseable JSON text is
    present, validation fails.
- In addition: if the same tool in a previous call in this episode returned valid JSON,
  but in this call failed to parse as JSON, validation fails.
- On failure, results are loudified with the verbatim error template:
  "[skeptic:schema_guard] Tool output failed validation: <first error, max 200 chars>.
   Treat this result as unusable; retry, use another source, or report failure."
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

import jsonschema

from skeptic_agent.guards.base import Guard, GuardResult, GuardSpec, loudify, register
from skeptic_agent.jsonrpc import ErrorResponse, Response
from skeptic_agent.proxy.context import EpisodeContext

SCHEMA_GUARD_TEXT_TEMPLATE: str = (
    "[skeptic:schema_guard] Tool output failed validation: {detail}. "
    "Treat this result as unusable; retry, use another source, or report failure."
)
"""The exact verbatim G02 text template specified in S11."""


def _first_text(result: dict[str, Any]) -> str | None:
    """Extract text from the first type=='text' block in result['content']."""
    content = result.get("content")
    if not isinstance(content, list):
        return None
    for block in content:
        if isinstance(block, dict) and block.get("type") == "text":
            text = block.get("text")
            if isinstance(text, str):
                return text
    return None


def _scenario_tool_defs(scenario: Any) -> dict[str, dict[str, Any]]:
    """Extract tool definitions dictionary from scenario."""
    if scenario is None:
        return {}
    scen_dict = scenario.model_dump() if hasattr(scenario, "model_dump") else scenario
    if not isinstance(scen_dict, dict):
        return {}
    tool_defs = scen_dict.get("tool_defs")
    if isinstance(tool_defs, dict):
        return {str(k): v for k, v in tool_defs.items() if isinstance(v, dict)}
    tools = scen_dict.get("tools")
    if isinstance(tools, list):
        res: dict[str, dict[str, Any]] = {}
        for t in tools:
            if isinstance(t, dict) and "name" in t:
                res[str(t["name"])] = t
        return res
    return {}


def _lookup_output_schema(
    ctx: EpisodeContext, tool_name: str | None, params: Mapping[str, Any]
) -> dict[str, Any] | None:
    """Look up outputSchema for a tool from params, ctx.tool_defs, or scenario."""
    if not tool_name:
        return None

    # 1. Direct configuration in params
    schemas = params.get("schemas")
    if isinstance(schemas, dict) and tool_name in schemas:
        schema = schemas[tool_name]
        if isinstance(schema, dict):
            return schema
    single_schema = params.get("output_schema") or params.get("outputSchema")
    if isinstance(single_schema, dict):
        return single_schema

    # 2. Seen on wire in ctx.tool_defs
    wire_def = ctx.tool_defs.get(tool_name)
    if isinstance(wire_def, dict):
        schema = wire_def.get("outputSchema") or wire_def.get("output_schema")
        if isinstance(schema, dict):
            return schema

    # 3. Present in scenario
    scen_defs = _scenario_tool_defs(ctx.scenario)
    scen_tool = scen_defs.get(tool_name)
    if isinstance(scen_tool, dict):
        schema = scen_tool.get("outputSchema") or scen_tool.get("output_schema")
        if isinstance(schema, dict):
            return schema

    return None


def _format_schema_error(err: jsonschema.ValidationError) -> str:
    """Format the first jsonschema validation error, capped at 200 characters."""
    json_path = getattr(err, "json_path", "")
    if json_path and json_path != "$":
        msg = f"{json_path}: {err.message}"
    elif err.path:
        path_str = "." + ".".join(str(p) for p in err.path)
        msg = f"{path_str}: {err.message}"
    else:
        msg = str(err.message)

    # Ensure max 200 chars and strip trailing period for clean sentence construction
    return msg[:200].rstrip(".")


@register
class SchemaGuard(Guard):
    """G02 schema_guard Guard (S11, s2c step ③).

    Validates tool outputs against declared outputSchema and catches JSON drift.
    """

    id: str = "schema_guard"
    hooks: tuple[str, ...] = ("s2c_call",)

    def __init__(self, spec: GuardSpec | None = None) -> None:
        """Initialize SchemaGuard."""
        super().__init__(spec)
        self._episode_id: str | None = None
        self._prev_json: dict[str, bool] = {}

    def reset(self) -> None:
        """Reset per-episode state."""
        self._prev_json.clear()

    def on_s2c_call(
        self, msg: Response | ErrorResponse, ctx: EpisodeContext, tool_name: str | None
    ) -> GuardResult | None:
        """Validate tool response against outputSchema or previous JSON state.

        Args:
            msg: Server response.
            ctx: Episode context.
            tool_name: Name of tool called.

        Returns:
            GuardResult with loudified error response and note if validation fails,
            None otherwise.
        """
        if not isinstance(msg, Response) or not isinstance(msg.result, dict):
            return None

        # S4.5: resultType other than "complete" is left alone
        if msg.result.get("resultType", "complete") != "complete":
            return None

        # Already an error result: do not overwrite
        if msg.result.get("isError") is True:
            return None

        # Reset state on new episode
        if self._episode_id != ctx.episode_id:
            self._episode_id = ctx.episode_id
            self.reset()

        tool_key = tool_name or ""
        result = msg.result
        structured = result.get("structuredContent")
        text = _first_text(result)

        # Determine if current output can be interpreted as JSON instance
        instance: Any = None
        is_json = False

        if structured is not None:
            instance = structured
            is_json = True
        elif text is not None:
            try:
                instance = json.loads(text)
                is_json = True
            except (ValueError, TypeError):
                instance = None
                is_json = False

        output_schema = _lookup_output_schema(ctx, tool_name, self.params)
        detail: str | None = None

        if output_schema is not None:
            if not is_json:
                detail = "missing structuredContent and text is not valid JSON"
            else:
                try:
                    validator_cls = jsonschema.validators.validator_for(output_schema)
                    validator = validator_cls(output_schema)
                    errors = sorted(
                        validator.iter_errors(instance),
                        key=lambda e: (list(e.path), str(e.message)),
                    )
                    if errors:
                        detail = _format_schema_error(errors[0])
                except Exception as exc:  # Guard against malformed schema specification
                    detail = f"schema validation error: {exc}"[:200].rstrip(".")
        else:
            # S11: If same tool previously returned JSON and now fails to parse, loudify
            prev_was_json = self._prev_json.get(tool_key, False)
            if prev_was_json and not is_json:
                detail = "unparseable JSON (previous result was valid JSON)"

        # Update JSON status for this tool if it succeeded in producing JSON
        if is_json:
            self._prev_json[tool_key] = True

        if detail is None:
            return None

        loud_text = SCHEMA_GUARD_TEXT_TEMPLATE.format(detail=detail)
        loud_res = loudify(loud_text, meta=result.get("_meta"))
        rewritten = msg.model_copy(update={"result": loud_res, "raw_bytes": b""})
        note = {
            "id": self.id,
            "action": "loudify",
            "detail": detail,
        }
        return GuardResult(msg=rewritten, note=note)
