# Skeptic Agent Skill Demo: Reliability Audit (K56)

This demo workspace demonstrates an end-to-end reliability audit of an AI agent's tool layer using the **`skeptic-reliability-audit`** Agent Skill.

---

## Workspace Architecture

The workspace configures **2 MCP servers** in `.mcp.json`:
1. **`weather`** (`sb_weather`):
   - `get_forecast`: Retrieve city forecast data (temperatures, weather conditions).
   - `list_cities`: List supported forecast cities.
2. **`files`** (`sb_files`):
   - `read_file`: Read file contents.
   - `list_dir`: List directory contents.
   - `stat`: Query file metadata and size.
   - `write_file`: Create or update files on disk (write operation).

```json
{
  "mcpServers": {
    "weather": {
      "command": "python",
      "args": ["-m", "skeptic_agent.sandboxes.sb_weather"]
    },
    "files": {
      "command": "python",
      "args": ["-m", "skeptic_agent.sandboxes.sb_files"]
    }
  }
}
```

---

## Installing the Skill

### Option 1: Skills CLI
```bash
npx skills add <ORG>/skeptic
```

### Option 2: Manual Installation
In environments where `npx` or network access is restricted:
1. Copy `skills/skeptic-reliability-audit/` into `.agents/skills/` or your agent runtime skills path:
   ```bash
   mkdir -p .agents/skills
   cp -r ../../skills/skeptic-reliability-audit .agents/skills/
   ```
2. Verify that `skeptic` CLI is installed:
   ```bash
   skeptic --version
   ```

---

## Executing the 6-Phase Audit

### Phase 1: Discover Tools & Endpoints
Inspects client configurations, connects to both MCP servers, and indexes tool schemas.
```bash
bash ../../skills/skeptic-reliability-audit/scripts/discover.sh . audit/discovery.json
```
**Artifact:** `audit/discovery.json`

---

### Phase 2: Plan Scenarios & Profile
Generates 2 scenarios per read tool and 1 scenario per write tool (total: 11 scenarios), with clean tool calls deriving ground truth answers. Also emits the fixed composite audit profile (`silent-core` + `loud-core` + `adversarial-core`).
```bash
python ../../skills/skeptic-reliability-audit/scripts/generate_scenarios.py \
  --discovery audit/discovery.json \
  --out audit/scenarios \
  --profile audit/profile.yaml
```
**Artifacts:**
- `audit/scenarios/*.yaml` (11 scenarios, validated via `skeptic scenario validate`)
- `audit/profile.yaml` (19 core fault injections)

---

### Phase 3: Execute Baseline Run (Seed 1)
Evaluates agent reliability under fault injection with plain prompting and no guardrails.
```bash
skeptic run \
  --scenario audit/scenarios \
  --profile audit/profile.yaml \
  --agent reference:fake/gullible \
  --seeds 1 \
  --max-cost-usd 3 \
  --out audit/runs/baseline
```
**Artifacts:** `audit/runs/baseline/results.jsonl`, `audit/runs/baseline/summary.json`, cassettes.

---

### Phase 4: Verify Replication (Seeds 2, 3)
Re-evaluates candidate problematic episodes across seeds 2 and 3. Only issues replicating in $\ge 2/3$ runs are retained.
```bash
skeptic run \
  --scenario audit/scenarios \
  --profile audit/profile.yaml \
  --agent reference:fake/gullible \
  --seeds 2,3 \
  --max-cost-usd 3 \
  --out audit/runs/verify
```
**Artifacts:** `audit/runs/verify/results.jsonl`.

---

### Phase 5: Harden & Compare
Applies recommended guardrails (`--guards recommended`) and evidence contract prompting (`--prompt-variant evidence_contract`).
```bash
skeptic run \
  --scenario audit/scenarios \
  --profile audit/profile.yaml \
  --agent reference:fake/gullible \
  --guards recommended \
  --prompt-variant evidence_contract \
  --seeds 1 \
  --out audit/runs/hardened

skeptic compare audit/runs/baseline audit/runs/hardened
```
**Artifacts:** `audit/runs/hardened/results.jsonl`.

---

### Phase 6: Report Deliverables
Synthesizes findings, checks replication, confirms verified fixes, and generates SARIF and markdown reports.
```bash
python ../../skills/skeptic-reliability-audit/scripts/summarize_findings.py \
  --runs audit/runs/baseline \
  --verify audit/runs/verify \
  --hardened audit/runs/hardened \
  --out audit
```

**Deliverables:**
- **`findings.json`**: Conforms to `schemas/findings.schema.json`.
- **`skeptic.sarif`**: Conforms to SARIF 2.1.0 standard.
- **`summary.md`**: Executive summary and detailed vulnerability recommendations.
