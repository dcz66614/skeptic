# Skeptic Reliability Audit - Step 1: Discover (S14.1, S14.2)
# Discovers MCP servers and tools, generating audit/discovery.json
param(
    [string]$ProjectDir = ".",
    [string]$OutputFile = "audit/discovery.json"
)

$ErrorActionPreference = "Stop"

Write-Host "[Skeptic Skill] Discovering MCP servers and tools in '$ProjectDir'..."

python -c @"
import sys
from pathlib import Path
from skeptic_agent.audit.discover import discover_servers_and_tools

res = discover_servers_and_tools(
    project_dir=r'$ProjectDir',
    output_file=r'$OutputFile',
)
srv_count = len(res.get('servers', {}))
tool_count = sum(len(s.get('tools', [])) for s in res.get('servers', {}).values())
print(f'[Skeptic Skill] Discovered {srv_count} server(s) with {tool_count} tool(s) -> $OutputFile')
"@
