#!/usr/bin/env bash
# Skeptic Reliability Audit - Step 1: Discover (S14.1, S14.2)
# Discovers MCP servers and tools, generating audit/discovery.json
set -euo pipefail

PROJECT_DIR="${1:-.}"
OUTPUT_FILE="${2:-audit/discovery.json}"

PYTHON_BIN="python"
if command -v python3 &>/dev/null; then
    PYTHON_BIN="python3"
fi

echo "[Skeptic Skill] Discovering MCP servers and tools in '${PROJECT_DIR}'..."

"$PYTHON_BIN" -c "
import sys
from pathlib import Path
from skeptic_agent.audit.discover import discover_servers_and_tools

res = discover_servers_and_tools(
    project_dir='${PROJECT_DIR}',
    output_file='${OUTPUT_FILE}',
)
srv_count = len(res.get('servers', {}))
tool_count = sum(len(s.get('tools', [])) for s in res.get('servers', {}).values())
print(f'[Skeptic Skill] Discovered {srv_count} server(s) with {tool_count} tool(s) -> ${OUTPUT_FILE}')
"
