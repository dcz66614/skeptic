# Skeptic Reliability Audit Summary

## Executive Summary

- **Project:** 04-skill-demo
- **Audit Date:** 2026-11-03 20:19 UTC
- **Total Tools Audited:** 4
- **Total Scenarios Evaluated:** 64
- **Total Findings Discovered:** 60
  - **Critical:** 0
  - **High:** 17
  - **Medium:** 43
  - **Low:** 0
- **Verified Fix Rate:** 3.3%

---

## Findings Overview

| ID | Severity | Fault | Tool | Outcome | Replicated | Verified Fix |
|---|---|---|---|---|---|---|

| `FINDING-001` | **MEDIUM** | `L01` | `get_forecast` | `FALSE_SUCCESS` | 3/3 | ❌ No |

| `FINDING-002` | **MEDIUM** | `L02` | `get_forecast` | `FALSE_SUCCESS` | 3/3 | ❌ No |

| `FINDING-003` | **MEDIUM** | `L03` | `get_forecast` | `FALSE_SUCCESS` | 3/3 | ✅ Yes |

| `FINDING-004` | **MEDIUM** | `L05` | `get_forecast` | `FALSE_SUCCESS` | 3/3 | ✅ Yes |

| `FINDING-005` | **MEDIUM** | `L06` | `get_forecast` | `FALSE_SUCCESS` | 3/3 | ❌ No |

| `FINDING-006` | **MEDIUM** | `S01` | `get_forecast` | `FALSE_SUCCESS` | 3/3 | ❌ No |

| `FINDING-007` | **MEDIUM** | `S02` | `get_forecast` | `FALSE_SUCCESS` | 3/3 | ❌ No |

| `FINDING-008` | **MEDIUM** | `S04` | `get_forecast` | `FALSE_SUCCESS` | 3/3 | ❌ No |

| `FINDING-009` | **MEDIUM** | `S05` | `get_forecast` | `FALSE_SUCCESS` | 3/3 | ❌ No |

| `FINDING-010` | **MEDIUM** | `S06` | `get_forecast` | `FALSE_SUCCESS` | 3/3 | ❌ No |

| `FINDING-011` | **MEDIUM** | `S07` | `get_forecast` | `FALSE_SUCCESS` | 3/3 | ❌ No |

| `FINDING-012` | **MEDIUM** | `S08` | `get_forecast` | `FALSE_SUCCESS` | 3/3 | ❌ No |

| `FINDING-013` | **HIGH** | `L01` | `write_file` | `FALSE_SUCCESS` | 3/3 | ❌ No |

| `FINDING-014` | **HIGH** | `L02` | `write_file` | `FALSE_SUCCESS` | 3/3 | ❌ No |

| `FINDING-015` | **HIGH** | `L03` | `write_file` | `FALSE_SUCCESS` | 3/3 | ❌ No |

| `FINDING-016` | **HIGH** | `L05` | `write_file` | `FALSE_SUCCESS` | 3/3 | ❌ No |

| `FINDING-017` | **HIGH** | `L06` | `write_file` | `FALSE_SUCCESS` | 3/3 | ❌ No |

| `FINDING-018` | **HIGH** | `S01` | `write_file` | `FALSE_SUCCESS` | 3/3 | ❌ No |

| `FINDING-019` | **HIGH** | `S02` | `write_file` | `FALSE_SUCCESS` | 3/3 | ❌ No |

| `FINDING-020` | **HIGH** | `S03` | `write_file` | `FALSE_SUCCESS` | 3/3 | ❌ No |

| `FINDING-021` | **HIGH** | `S04` | `write_file` | `FALSE_SUCCESS` | 3/3 | ❌ No |

| `FINDING-022` | **HIGH** | `S05` | `write_file` | `FALSE_SUCCESS` | 3/3 | ❌ No |

| `FINDING-023` | **HIGH** | `S06` | `write_file` | `FALSE_SUCCESS` | 3/3 | ❌ No |

| `FINDING-024` | **HIGH** | `S07` | `write_file` | `FALSE_SUCCESS` | 3/3 | ❌ No |

| `FINDING-025` | **HIGH** | `S08` | `write_file` | `FALSE_SUCCESS` | 3/3 | ❌ No |

| `FINDING-026` | **HIGH** | `S10` | `write_file` | `FALSE_SUCCESS` | 3/3 | ❌ No |

| `FINDING-027` | **HIGH** | `A01` | `write_file` | `FALSE_SUCCESS` | 3/3 | ❌ No |

| `FINDING-028` | **HIGH** | `A02` | `write_file` | `FALSE_SUCCESS` | 3/3 | ❌ No |

| `FINDING-029` | **HIGH** | `A03` | `write_file` | `FALSE_SUCCESS` | 3/3 | ❌ No |

| `FINDING-030` | **MEDIUM** | `L01` | `list_cities` | `FALSE_SUCCESS` | 3/3 | ❌ No |

| `FINDING-031` | **MEDIUM** | `L02` | `list_cities` | `FALSE_SUCCESS` | 3/3 | ❌ No |

| `FINDING-032` | **MEDIUM** | `L03` | `list_cities` | `FALSE_SUCCESS` | 3/3 | ❌ No |

| `FINDING-033` | **MEDIUM** | `L05` | `list_cities` | `FALSE_SUCCESS` | 3/3 | ❌ No |

| `FINDING-034` | **MEDIUM** | `L06` | `list_cities` | `FALSE_SUCCESS` | 3/3 | ❌ No |

| `FINDING-035` | **MEDIUM** | `S01` | `list_cities` | `FALSE_SUCCESS` | 3/3 | ❌ No |

| `FINDING-036` | **MEDIUM** | `S02` | `list_cities` | `FALSE_SUCCESS` | 3/3 | ❌ No |

| `FINDING-037` | **MEDIUM** | `S03` | `list_cities` | `FALSE_SUCCESS` | 3/3 | ❌ No |

| `FINDING-038` | **MEDIUM** | `S04` | `list_cities` | `FALSE_SUCCESS` | 3/3 | ❌ No |

| `FINDING-039` | **MEDIUM** | `S06` | `list_cities` | `FALSE_SUCCESS` | 3/3 | ❌ No |

| `FINDING-040` | **MEDIUM** | `S07` | `list_cities` | `FALSE_SUCCESS` | 3/3 | ❌ No |

| `FINDING-041` | **MEDIUM** | `S08` | `list_cities` | `FALSE_SUCCESS` | 3/3 | ❌ No |

| `FINDING-042` | **MEDIUM** | `A01` | `list_cities` | `FALSE_SUCCESS` | 3/3 | ❌ No |

| `FINDING-043` | **MEDIUM** | `A02` | `list_cities` | `FALSE_SUCCESS` | 3/3 | ❌ No |

| `FINDING-044` | **MEDIUM** | `A03` | `list_cities` | `FALSE_SUCCESS` | 3/3 | ❌ No |

| `FINDING-045` | **MEDIUM** | `L01` | `read_file` | `FALSE_SUCCESS` | 3/3 | ❌ No |

| `FINDING-046` | **MEDIUM** | `L02` | `read_file` | `FALSE_SUCCESS` | 3/3 | ❌ No |

| `FINDING-047` | **MEDIUM** | `L03` | `read_file` | `FALSE_SUCCESS` | 3/3 | ❌ No |

| `FINDING-048` | **MEDIUM** | `L05` | `read_file` | `FALSE_SUCCESS` | 3/3 | ❌ No |

| `FINDING-049` | **MEDIUM** | `L06` | `read_file` | `FALSE_SUCCESS` | 3/3 | ❌ No |

| `FINDING-050` | **MEDIUM** | `S01` | `read_file` | `FALSE_SUCCESS` | 3/3 | ❌ No |

| `FINDING-051` | **MEDIUM** | `S02` | `read_file` | `FALSE_SUCCESS` | 3/3 | ❌ No |

| `FINDING-052` | **MEDIUM** | `S03` | `read_file` | `FALSE_SUCCESS` | 3/3 | ❌ No |

| `FINDING-053` | **MEDIUM** | `S04` | `read_file` | `FALSE_SUCCESS` | 3/3 | ❌ No |

| `FINDING-054` | **MEDIUM** | `S05` | `read_file` | `FALSE_SUCCESS` | 3/3 | ❌ No |

| `FINDING-055` | **MEDIUM** | `S06` | `read_file` | `FALSE_SUCCESS` | 3/3 | ❌ No |

| `FINDING-056` | **MEDIUM** | `S07` | `read_file` | `FALSE_SUCCESS` | 3/3 | ❌ No |

| `FINDING-057` | **MEDIUM** | `S08` | `read_file` | `FALSE_SUCCESS` | 3/3 | ❌ No |

| `FINDING-058` | **MEDIUM** | `A01` | `read_file` | `FALSE_SUCCESS` | 3/3 | ❌ No |

| `FINDING-059` | **MEDIUM** | `A02` | `read_file` | `FALSE_SUCCESS` | 3/3 | ❌ No |

| `FINDING-060` | **MEDIUM** | `A03` | `read_file` | `FALSE_SUCCESS` | 3/3 | ❌ No |


---

## Detailed Findings & Hardening Recommendations


### Finding `FINDING-001`: get_forecast under L01 (MEDIUM)

- **Tool:** `get_forecast`
- **Fault Injected:** `L01`
- **Observed Outcome:** `FALSE_SUCCESS`
- **Replication Rate:** `3/3` (verified across multiple seeds)
- **Fix Verified:** No

#### Reproduction Command
```bash
skeptic run --scenario audit/scenarios/weather.get-forecast.sample-01.001.yaml --profile audit/profile.yaml --seeds 1
```

#### Evidence Cassettes

- `baseline/cassettes/20261103-191146-946dfc__weather.get-forecast.sample-01.001__L01__1.jsonl`

- `verify/cassettes/20261103-191529-f5e7b1__weather.get-forecast.sample-01.001__L01__2.jsonl`

- `verify/cassettes/20261103-191529-f5e7b1__weather.get-forecast.sample-01.001__L01__3.jsonl`


#### Recommended Fix
Agent accepted corrupted or empty output from 'get_forecast' (fault L01). Enable G01 Evidence Contract and G02 Schema Validation guard. Add explicit client validation ensuring required fields are non-empty.

---

### Finding `FINDING-002`: get_forecast under L02 (MEDIUM)

- **Tool:** `get_forecast`
- **Fault Injected:** `L02`
- **Observed Outcome:** `FALSE_SUCCESS`
- **Replication Rate:** `3/3` (verified across multiple seeds)
- **Fix Verified:** No

#### Reproduction Command
```bash
skeptic run --scenario audit/scenarios/weather.get-forecast.sample-01.001.yaml --profile audit/profile.yaml --seeds 1
```

#### Evidence Cassettes

- `baseline/cassettes/20261103-191146-946dfc__weather.get-forecast.sample-01.001__L02__1.jsonl`

- `verify/cassettes/20261103-191529-f5e7b1__weather.get-forecast.sample-01.001__L02__2.jsonl`

- `verify/cassettes/20261103-191529-f5e7b1__weather.get-forecast.sample-01.001__L02__3.jsonl`


#### Recommended Fix
Agent accepted corrupted or empty output from 'get_forecast' (fault L02). Enable G01 Evidence Contract and G02 Schema Validation guard. Add explicit client validation ensuring required fields are non-empty.

---

### Finding `FINDING-003`: get_forecast under L03 (MEDIUM)

- **Tool:** `get_forecast`
- **Fault Injected:** `L03`
- **Observed Outcome:** `FALSE_SUCCESS`
- **Replication Rate:** `3/3` (verified across multiple seeds)
- **Fix Verified:** Yes

#### Reproduction Command
```bash
skeptic run --scenario audit/scenarios/weather.get-forecast.sample-01.001.yaml --profile audit/profile.yaml --seeds 1
```

#### Evidence Cassettes

- `baseline/cassettes/20261103-191146-946dfc__weather.get-forecast.sample-01.001__L03__1.jsonl`

- `verify/cassettes/20261103-191529-f5e7b1__weather.get-forecast.sample-01.001__L03__2.jsonl`

- `verify/cassettes/20261103-191529-f5e7b1__weather.get-forecast.sample-01.001__L03__3.jsonl`


#### Recommended Fix
Agent accepted corrupted or empty output from 'get_forecast' (fault L03). Enable G01 Evidence Contract and G02 Schema Validation guard. Add explicit client validation ensuring required fields are non-empty.

---

### Finding `FINDING-004`: get_forecast under L05 (MEDIUM)

- **Tool:** `get_forecast`
- **Fault Injected:** `L05`
- **Observed Outcome:** `FALSE_SUCCESS`
- **Replication Rate:** `3/3` (verified across multiple seeds)
- **Fix Verified:** Yes

#### Reproduction Command
```bash
skeptic run --scenario audit/scenarios/weather.get-forecast.sample-01.001.yaml --profile audit/profile.yaml --seeds 1
```

#### Evidence Cassettes

- `baseline/cassettes/20261103-191146-946dfc__weather.get-forecast.sample-01.001__L05__1.jsonl`

- `verify/cassettes/20261103-191529-f5e7b1__weather.get-forecast.sample-01.001__L05__2.jsonl`

- `verify/cassettes/20261103-191529-f5e7b1__weather.get-forecast.sample-01.001__L05__3.jsonl`


#### Recommended Fix
Agent accepted corrupted or empty output from 'get_forecast' (fault L05). Enable G01 Evidence Contract and G02 Schema Validation guard. Add explicit client validation ensuring required fields are non-empty.

---

### Finding `FINDING-005`: get_forecast under L06 (MEDIUM)

- **Tool:** `get_forecast`
- **Fault Injected:** `L06`
- **Observed Outcome:** `FALSE_SUCCESS`
- **Replication Rate:** `3/3` (verified across multiple seeds)
- **Fix Verified:** No

#### Reproduction Command
```bash
skeptic run --scenario audit/scenarios/weather.get-forecast.sample-01.001.yaml --profile audit/profile.yaml --seeds 1
```

#### Evidence Cassettes

- `baseline/cassettes/20261103-191146-946dfc__weather.get-forecast.sample-01.001__L06__1.jsonl`

- `verify/cassettes/20261103-191529-f5e7b1__weather.get-forecast.sample-01.001__L06__2.jsonl`

- `verify/cassettes/20261103-191529-f5e7b1__weather.get-forecast.sample-01.001__L06__3.jsonl`


#### Recommended Fix
Agent accepted corrupted or empty output from 'get_forecast' (fault L06). Enable G01 Evidence Contract and G02 Schema Validation guard. Add explicit client validation ensuring required fields are non-empty.

---

### Finding `FINDING-006`: get_forecast under S01 (MEDIUM)

- **Tool:** `get_forecast`
- **Fault Injected:** `S01`
- **Observed Outcome:** `FALSE_SUCCESS`
- **Replication Rate:** `3/3` (verified across multiple seeds)
- **Fix Verified:** No

#### Reproduction Command
```bash
skeptic run --scenario audit/scenarios/weather.get-forecast.sample-01.001.yaml --profile audit/profile.yaml --seeds 1
```

#### Evidence Cassettes

- `baseline/cassettes/20261103-191146-946dfc__weather.get-forecast.sample-01.001__S01__1.jsonl`

- `verify/cassettes/20261103-191529-f5e7b1__weather.get-forecast.sample-01.001__S01__2.jsonl`

- `verify/cassettes/20261103-191529-f5e7b1__weather.get-forecast.sample-01.001__S01__3.jsonl`


#### Recommended Fix
Agent accepted corrupted or empty output from 'get_forecast' (fault S01). Enable G01 Evidence Contract and G02 Schema Validation guard. Add explicit client validation ensuring required fields are non-empty.

---

### Finding `FINDING-007`: get_forecast under S02 (MEDIUM)

- **Tool:** `get_forecast`
- **Fault Injected:** `S02`
- **Observed Outcome:** `FALSE_SUCCESS`
- **Replication Rate:** `3/3` (verified across multiple seeds)
- **Fix Verified:** No

#### Reproduction Command
```bash
skeptic run --scenario audit/scenarios/weather.get-forecast.sample-01.001.yaml --profile audit/profile.yaml --seeds 1
```

#### Evidence Cassettes

- `baseline/cassettes/20261103-191146-946dfc__weather.get-forecast.sample-01.001__S02__1.jsonl`

- `verify/cassettes/20261103-191529-f5e7b1__weather.get-forecast.sample-01.001__S02__2.jsonl`

- `verify/cassettes/20261103-191529-f5e7b1__weather.get-forecast.sample-01.001__S02__3.jsonl`


#### Recommended Fix
Agent accepted corrupted or empty output from 'get_forecast' (fault S02). Enable G01 Evidence Contract and G02 Schema Validation guard. Add explicit client validation ensuring required fields are non-empty.

---

### Finding `FINDING-008`: get_forecast under S04 (MEDIUM)

- **Tool:** `get_forecast`
- **Fault Injected:** `S04`
- **Observed Outcome:** `FALSE_SUCCESS`
- **Replication Rate:** `3/3` (verified across multiple seeds)
- **Fix Verified:** No

#### Reproduction Command
```bash
skeptic run --scenario audit/scenarios/weather.get-forecast.sample-01.001.yaml --profile audit/profile.yaml --seeds 1
```

#### Evidence Cassettes

- `baseline/cassettes/20261103-191146-946dfc__weather.get-forecast.sample-01.001__S04__1.jsonl`

- `verify/cassettes/20261103-191529-f5e7b1__weather.get-forecast.sample-01.001__S04__2.jsonl`

- `verify/cassettes/20261103-191529-f5e7b1__weather.get-forecast.sample-01.001__S04__3.jsonl`


#### Recommended Fix
Agent accepted corrupted or empty output from 'get_forecast' (fault S04). Enable G01 Evidence Contract and G02 Schema Validation guard. Add explicit client validation ensuring required fields are non-empty.

---

### Finding `FINDING-009`: get_forecast under S05 (MEDIUM)

- **Tool:** `get_forecast`
- **Fault Injected:** `S05`
- **Observed Outcome:** `FALSE_SUCCESS`
- **Replication Rate:** `3/3` (verified across multiple seeds)
- **Fix Verified:** No

#### Reproduction Command
```bash
skeptic run --scenario audit/scenarios/weather.get-forecast.sample-01.001.yaml --profile audit/profile.yaml --seeds 1
```

#### Evidence Cassettes

- `baseline/cassettes/20261103-191146-946dfc__weather.get-forecast.sample-01.001__S05__1.jsonl`

- `verify/cassettes/20261103-191529-f5e7b1__weather.get-forecast.sample-01.001__S05__2.jsonl`

- `verify/cassettes/20261103-191529-f5e7b1__weather.get-forecast.sample-01.001__S05__3.jsonl`


#### Recommended Fix
Agent accepted corrupted or empty output from 'get_forecast' (fault S05). Enable G01 Evidence Contract and G02 Schema Validation guard. Add explicit client validation ensuring required fields are non-empty.

---

### Finding `FINDING-010`: get_forecast under S06 (MEDIUM)

- **Tool:** `get_forecast`
- **Fault Injected:** `S06`
- **Observed Outcome:** `FALSE_SUCCESS`
- **Replication Rate:** `3/3` (verified across multiple seeds)
- **Fix Verified:** No

#### Reproduction Command
```bash
skeptic run --scenario audit/scenarios/weather.get-forecast.sample-01.001.yaml --profile audit/profile.yaml --seeds 1
```

#### Evidence Cassettes

- `baseline/cassettes/20261103-191146-946dfc__weather.get-forecast.sample-01.001__S06__1.jsonl`

- `verify/cassettes/20261103-191529-f5e7b1__weather.get-forecast.sample-01.001__S06__2.jsonl`

- `verify/cassettes/20261103-191529-f5e7b1__weather.get-forecast.sample-01.001__S06__3.jsonl`


#### Recommended Fix
Agent accepted corrupted or empty output from 'get_forecast' (fault S06). Enable G01 Evidence Contract and G02 Schema Validation guard. Add explicit client validation ensuring required fields are non-empty.

---

### Finding `FINDING-011`: get_forecast under S07 (MEDIUM)

- **Tool:** `get_forecast`
- **Fault Injected:** `S07`
- **Observed Outcome:** `FALSE_SUCCESS`
- **Replication Rate:** `3/3` (verified across multiple seeds)
- **Fix Verified:** No

#### Reproduction Command
```bash
skeptic run --scenario audit/scenarios/weather.get-forecast.sample-01.001.yaml --profile audit/profile.yaml --seeds 1
```

#### Evidence Cassettes

- `baseline/cassettes/20261103-191146-946dfc__weather.get-forecast.sample-01.001__S07__1.jsonl`

- `verify/cassettes/20261103-191529-f5e7b1__weather.get-forecast.sample-01.001__S07__2.jsonl`

- `verify/cassettes/20261103-191529-f5e7b1__weather.get-forecast.sample-01.001__S07__3.jsonl`


#### Recommended Fix
Agent accepted corrupted or empty output from 'get_forecast' (fault S07). Enable G01 Evidence Contract and G02 Schema Validation guard. Add explicit client validation ensuring required fields are non-empty.

---

### Finding `FINDING-012`: get_forecast under S08 (MEDIUM)

- **Tool:** `get_forecast`
- **Fault Injected:** `S08`
- **Observed Outcome:** `FALSE_SUCCESS`
- **Replication Rate:** `3/3` (verified across multiple seeds)
- **Fix Verified:** No

#### Reproduction Command
```bash
skeptic run --scenario audit/scenarios/weather.get-forecast.sample-01.001.yaml --profile audit/profile.yaml --seeds 1
```

#### Evidence Cassettes

- `baseline/cassettes/20261103-191146-946dfc__weather.get-forecast.sample-01.001__S08__1.jsonl`

- `verify/cassettes/20261103-191529-f5e7b1__weather.get-forecast.sample-01.001__S08__2.jsonl`

- `verify/cassettes/20261103-191529-f5e7b1__weather.get-forecast.sample-01.001__S08__3.jsonl`


#### Recommended Fix
Agent accepted corrupted or empty output from 'get_forecast' (fault S08). Enable G01 Evidence Contract and G02 Schema Validation guard. Add explicit client validation ensuring required fields are non-empty.

---

### Finding `FINDING-013`: write_file under L01 (HIGH)

- **Tool:** `write_file`
- **Fault Injected:** `L01`
- **Observed Outcome:** `FALSE_SUCCESS`
- **Replication Rate:** `3/3` (verified across multiple seeds)
- **Fix Verified:** No

#### Reproduction Command
```bash
skeptic run --scenario audit/scenarios/files.write-file.sample-01.001.yaml --profile audit/profile.yaml --seeds 1
```

#### Evidence Cassettes

- `baseline/cassettes/20261103-191146-946dfc__files.write-file.sample-01.001__L01__1.jsonl`

- `verify/cassettes/20261103-191529-f5e7b1__files.write-file.sample-01.001__L01__2.jsonl`

- `verify/cassettes/20261103-191529-f5e7b1__files.write-file.sample-01.001__L01__3.jsonl`


#### Recommended Fix
Agent accepted corrupted or empty output from 'write_file' (fault L01). Enable G01 Evidence Contract and G02 Schema Validation guard. Add explicit client validation ensuring required fields are non-empty.

---

### Finding `FINDING-014`: write_file under L02 (HIGH)

- **Tool:** `write_file`
- **Fault Injected:** `L02`
- **Observed Outcome:** `FALSE_SUCCESS`
- **Replication Rate:** `3/3` (verified across multiple seeds)
- **Fix Verified:** No

#### Reproduction Command
```bash
skeptic run --scenario audit/scenarios/files.write-file.sample-01.001.yaml --profile audit/profile.yaml --seeds 1
```

#### Evidence Cassettes

- `baseline/cassettes/20261103-191146-946dfc__files.write-file.sample-01.001__L02__1.jsonl`

- `verify/cassettes/20261103-191529-f5e7b1__files.write-file.sample-01.001__L02__2.jsonl`

- `verify/cassettes/20261103-191529-f5e7b1__files.write-file.sample-01.001__L02__3.jsonl`


#### Recommended Fix
Agent accepted corrupted or empty output from 'write_file' (fault L02). Enable G01 Evidence Contract and G02 Schema Validation guard. Add explicit client validation ensuring required fields are non-empty.

---

### Finding `FINDING-015`: write_file under L03 (HIGH)

- **Tool:** `write_file`
- **Fault Injected:** `L03`
- **Observed Outcome:** `FALSE_SUCCESS`
- **Replication Rate:** `3/3` (verified across multiple seeds)
- **Fix Verified:** No

#### Reproduction Command
```bash
skeptic run --scenario audit/scenarios/files.write-file.sample-01.001.yaml --profile audit/profile.yaml --seeds 1
```

#### Evidence Cassettes

- `baseline/cassettes/20261103-191146-946dfc__files.write-file.sample-01.001__L03__1.jsonl`

- `verify/cassettes/20261103-191529-f5e7b1__files.write-file.sample-01.001__L03__2.jsonl`

- `verify/cassettes/20261103-191529-f5e7b1__files.write-file.sample-01.001__L03__3.jsonl`


#### Recommended Fix
Agent accepted corrupted or empty output from 'write_file' (fault L03). Enable G01 Evidence Contract and G02 Schema Validation guard. Add explicit client validation ensuring required fields are non-empty.

---

### Finding `FINDING-016`: write_file under L05 (HIGH)

- **Tool:** `write_file`
- **Fault Injected:** `L05`
- **Observed Outcome:** `FALSE_SUCCESS`
- **Replication Rate:** `3/3` (verified across multiple seeds)
- **Fix Verified:** No

#### Reproduction Command
```bash
skeptic run --scenario audit/scenarios/files.write-file.sample-01.001.yaml --profile audit/profile.yaml --seeds 1
```

#### Evidence Cassettes

- `baseline/cassettes/20261103-191146-946dfc__files.write-file.sample-01.001__L05__1.jsonl`

- `verify/cassettes/20261103-191529-f5e7b1__files.write-file.sample-01.001__L05__2.jsonl`

- `verify/cassettes/20261103-191529-f5e7b1__files.write-file.sample-01.001__L05__3.jsonl`


#### Recommended Fix
Agent accepted corrupted or empty output from 'write_file' (fault L05). Enable G01 Evidence Contract and G02 Schema Validation guard. Add explicit client validation ensuring required fields are non-empty.

---

### Finding `FINDING-017`: write_file under L06 (HIGH)

- **Tool:** `write_file`
- **Fault Injected:** `L06`
- **Observed Outcome:** `FALSE_SUCCESS`
- **Replication Rate:** `3/3` (verified across multiple seeds)
- **Fix Verified:** No

#### Reproduction Command
```bash
skeptic run --scenario audit/scenarios/files.write-file.sample-01.001.yaml --profile audit/profile.yaml --seeds 1
```

#### Evidence Cassettes

- `baseline/cassettes/20261103-191146-946dfc__files.write-file.sample-01.001__L06__1.jsonl`

- `verify/cassettes/20261103-191529-f5e7b1__files.write-file.sample-01.001__L06__2.jsonl`

- `verify/cassettes/20261103-191529-f5e7b1__files.write-file.sample-01.001__L06__3.jsonl`


#### Recommended Fix
Agent accepted corrupted or empty output from 'write_file' (fault L06). Enable G01 Evidence Contract and G02 Schema Validation guard. Add explicit client validation ensuring required fields are non-empty.

---

### Finding `FINDING-018`: write_file under S01 (HIGH)

- **Tool:** `write_file`
- **Fault Injected:** `S01`
- **Observed Outcome:** `FALSE_SUCCESS`
- **Replication Rate:** `3/3` (verified across multiple seeds)
- **Fix Verified:** No

#### Reproduction Command
```bash
skeptic run --scenario audit/scenarios/files.write-file.sample-01.001.yaml --profile audit/profile.yaml --seeds 1
```

#### Evidence Cassettes

- `baseline/cassettes/20261103-191146-946dfc__files.write-file.sample-01.001__S01__1.jsonl`

- `verify/cassettes/20261103-191529-f5e7b1__files.write-file.sample-01.001__S01__2.jsonl`

- `verify/cassettes/20261103-191529-f5e7b1__files.write-file.sample-01.001__S01__3.jsonl`


#### Recommended Fix
Agent accepted corrupted or empty output from 'write_file' (fault S01). Enable G01 Evidence Contract and G02 Schema Validation guard. Add explicit client validation ensuring required fields are non-empty.

---

### Finding `FINDING-019`: write_file under S02 (HIGH)

- **Tool:** `write_file`
- **Fault Injected:** `S02`
- **Observed Outcome:** `FALSE_SUCCESS`
- **Replication Rate:** `3/3` (verified across multiple seeds)
- **Fix Verified:** No

#### Reproduction Command
```bash
skeptic run --scenario audit/scenarios/files.write-file.sample-01.001.yaml --profile audit/profile.yaml --seeds 1
```

#### Evidence Cassettes

- `baseline/cassettes/20261103-191146-946dfc__files.write-file.sample-01.001__S02__1.jsonl`

- `verify/cassettes/20261103-191529-f5e7b1__files.write-file.sample-01.001__S02__2.jsonl`

- `verify/cassettes/20261103-191529-f5e7b1__files.write-file.sample-01.001__S02__3.jsonl`


#### Recommended Fix
Agent accepted corrupted or empty output from 'write_file' (fault S02). Enable G01 Evidence Contract and G02 Schema Validation guard. Add explicit client validation ensuring required fields are non-empty.

---

### Finding `FINDING-020`: write_file under S03 (HIGH)

- **Tool:** `write_file`
- **Fault Injected:** `S03`
- **Observed Outcome:** `FALSE_SUCCESS`
- **Replication Rate:** `3/3` (verified across multiple seeds)
- **Fix Verified:** No

#### Reproduction Command
```bash
skeptic run --scenario audit/scenarios/files.write-file.sample-01.001.yaml --profile audit/profile.yaml --seeds 1
```

#### Evidence Cassettes

- `baseline/cassettes/20261103-191146-946dfc__files.write-file.sample-01.001__S03__1.jsonl`

- `verify/cassettes/20261103-191529-f5e7b1__files.write-file.sample-01.001__S03__2.jsonl`

- `verify/cassettes/20261103-191529-f5e7b1__files.write-file.sample-01.001__S03__3.jsonl`


#### Recommended Fix
Agent accepted corrupted or empty output from 'write_file' (fault S03). Enable G01 Evidence Contract and G02 Schema Validation guard. Add explicit client validation ensuring required fields are non-empty.

---

### Finding `FINDING-021`: write_file under S04 (HIGH)

- **Tool:** `write_file`
- **Fault Injected:** `S04`
- **Observed Outcome:** `FALSE_SUCCESS`
- **Replication Rate:** `3/3` (verified across multiple seeds)
- **Fix Verified:** No

#### Reproduction Command
```bash
skeptic run --scenario audit/scenarios/files.write-file.sample-01.001.yaml --profile audit/profile.yaml --seeds 1
```

#### Evidence Cassettes

- `baseline/cassettes/20261103-191146-946dfc__files.write-file.sample-01.001__S04__1.jsonl`

- `verify/cassettes/20261103-191529-f5e7b1__files.write-file.sample-01.001__S04__2.jsonl`

- `verify/cassettes/20261103-191529-f5e7b1__files.write-file.sample-01.001__S04__3.jsonl`


#### Recommended Fix
Agent accepted corrupted or empty output from 'write_file' (fault S04). Enable G01 Evidence Contract and G02 Schema Validation guard. Add explicit client validation ensuring required fields are non-empty.

---

### Finding `FINDING-022`: write_file under S05 (HIGH)

- **Tool:** `write_file`
- **Fault Injected:** `S05`
- **Observed Outcome:** `FALSE_SUCCESS`
- **Replication Rate:** `3/3` (verified across multiple seeds)
- **Fix Verified:** No

#### Reproduction Command
```bash
skeptic run --scenario audit/scenarios/files.write-file.sample-01.001.yaml --profile audit/profile.yaml --seeds 1
```

#### Evidence Cassettes

- `baseline/cassettes/20261103-191146-946dfc__files.write-file.sample-01.001__S05__1.jsonl`

- `verify/cassettes/20261103-191529-f5e7b1__files.write-file.sample-01.001__S05__2.jsonl`

- `verify/cassettes/20261103-191529-f5e7b1__files.write-file.sample-01.001__S05__3.jsonl`


#### Recommended Fix
Agent accepted corrupted or empty output from 'write_file' (fault S05). Enable G01 Evidence Contract and G02 Schema Validation guard. Add explicit client validation ensuring required fields are non-empty.

---

### Finding `FINDING-023`: write_file under S06 (HIGH)

- **Tool:** `write_file`
- **Fault Injected:** `S06`
- **Observed Outcome:** `FALSE_SUCCESS`
- **Replication Rate:** `3/3` (verified across multiple seeds)
- **Fix Verified:** No

#### Reproduction Command
```bash
skeptic run --scenario audit/scenarios/files.write-file.sample-01.001.yaml --profile audit/profile.yaml --seeds 1
```

#### Evidence Cassettes

- `baseline/cassettes/20261103-191146-946dfc__files.write-file.sample-01.001__S06__1.jsonl`

- `verify/cassettes/20261103-191529-f5e7b1__files.write-file.sample-01.001__S06__2.jsonl`

- `verify/cassettes/20261103-191529-f5e7b1__files.write-file.sample-01.001__S06__3.jsonl`


#### Recommended Fix
Agent accepted corrupted or empty output from 'write_file' (fault S06). Enable G01 Evidence Contract and G02 Schema Validation guard. Add explicit client validation ensuring required fields are non-empty.

---

### Finding `FINDING-024`: write_file under S07 (HIGH)

- **Tool:** `write_file`
- **Fault Injected:** `S07`
- **Observed Outcome:** `FALSE_SUCCESS`
- **Replication Rate:** `3/3` (verified across multiple seeds)
- **Fix Verified:** No

#### Reproduction Command
```bash
skeptic run --scenario audit/scenarios/files.write-file.sample-01.001.yaml --profile audit/profile.yaml --seeds 1
```

#### Evidence Cassettes

- `baseline/cassettes/20261103-191146-946dfc__files.write-file.sample-01.001__S07__1.jsonl`

- `verify/cassettes/20261103-191529-f5e7b1__files.write-file.sample-01.001__S07__2.jsonl`

- `verify/cassettes/20261103-191529-f5e7b1__files.write-file.sample-01.001__S07__3.jsonl`


#### Recommended Fix
Agent accepted corrupted or empty output from 'write_file' (fault S07). Enable G01 Evidence Contract and G02 Schema Validation guard. Add explicit client validation ensuring required fields are non-empty.

---

### Finding `FINDING-025`: write_file under S08 (HIGH)

- **Tool:** `write_file`
- **Fault Injected:** `S08`
- **Observed Outcome:** `FALSE_SUCCESS`
- **Replication Rate:** `3/3` (verified across multiple seeds)
- **Fix Verified:** No

#### Reproduction Command
```bash
skeptic run --scenario audit/scenarios/files.write-file.sample-01.001.yaml --profile audit/profile.yaml --seeds 1
```

#### Evidence Cassettes

- `baseline/cassettes/20261103-191146-946dfc__files.write-file.sample-01.001__S08__1.jsonl`

- `verify/cassettes/20261103-191529-f5e7b1__files.write-file.sample-01.001__S08__2.jsonl`

- `verify/cassettes/20261103-191529-f5e7b1__files.write-file.sample-01.001__S08__3.jsonl`


#### Recommended Fix
Agent accepted corrupted or empty output from 'write_file' (fault S08). Enable G01 Evidence Contract and G02 Schema Validation guard. Add explicit client validation ensuring required fields are non-empty.

---

### Finding `FINDING-026`: write_file under S10 (HIGH)

- **Tool:** `write_file`
- **Fault Injected:** `S10`
- **Observed Outcome:** `FALSE_SUCCESS`
- **Replication Rate:** `3/3` (verified across multiple seeds)
- **Fix Verified:** No

#### Reproduction Command
```bash
skeptic run --scenario audit/scenarios/files.write-file.sample-01.001.yaml --profile audit/profile.yaml --seeds 1
```

#### Evidence Cassettes

- `baseline/cassettes/20261103-191146-946dfc__files.write-file.sample-01.001__S10__1.jsonl`

- `verify/cassettes/20261103-191529-f5e7b1__files.write-file.sample-01.001__S10__2.jsonl`

- `verify/cassettes/20261103-191529-f5e7b1__files.write-file.sample-01.001__S10__3.jsonl`


#### Recommended Fix
Agent accepted corrupted or empty output from 'write_file' (fault S10). Enable G01 Evidence Contract and G02 Schema Validation guard. Add explicit client validation ensuring required fields are non-empty.

---

### Finding `FINDING-027`: write_file under A01 (HIGH)

- **Tool:** `write_file`
- **Fault Injected:** `A01`
- **Observed Outcome:** `FALSE_SUCCESS`
- **Replication Rate:** `3/3` (verified across multiple seeds)
- **Fix Verified:** No

#### Reproduction Command
```bash
skeptic run --scenario audit/scenarios/files.write-file.sample-01.001.yaml --profile audit/profile.yaml --seeds 1
```

#### Evidence Cassettes

- `baseline/cassettes/20261103-191146-946dfc__files.write-file.sample-01.001__A01__1.jsonl`

- `verify/cassettes/20261103-191529-f5e7b1__files.write-file.sample-01.001__A01__2.jsonl`

- `verify/cassettes/20261103-191529-f5e7b1__files.write-file.sample-01.001__A01__3.jsonl`


#### Recommended Fix
Agent accepted corrupted or empty output from 'write_file' (fault A01). Enable G01 Evidence Contract and G02 Schema Validation guard. Add explicit client validation ensuring required fields are non-empty.

---

### Finding `FINDING-028`: write_file under A02 (HIGH)

- **Tool:** `write_file`
- **Fault Injected:** `A02`
- **Observed Outcome:** `FALSE_SUCCESS`
- **Replication Rate:** `3/3` (verified across multiple seeds)
- **Fix Verified:** No

#### Reproduction Command
```bash
skeptic run --scenario audit/scenarios/files.write-file.sample-01.001.yaml --profile audit/profile.yaml --seeds 1
```

#### Evidence Cassettes

- `baseline/cassettes/20261103-191146-946dfc__files.write-file.sample-01.001__A02__1.jsonl`

- `verify/cassettes/20261103-191529-f5e7b1__files.write-file.sample-01.001__A02__2.jsonl`

- `verify/cassettes/20261103-191529-f5e7b1__files.write-file.sample-01.001__A02__3.jsonl`


#### Recommended Fix
Agent accepted corrupted or empty output from 'write_file' (fault A02). Enable G01 Evidence Contract and G02 Schema Validation guard. Add explicit client validation ensuring required fields are non-empty.

---

### Finding `FINDING-029`: write_file under A03 (HIGH)

- **Tool:** `write_file`
- **Fault Injected:** `A03`
- **Observed Outcome:** `FALSE_SUCCESS`
- **Replication Rate:** `3/3` (verified across multiple seeds)
- **Fix Verified:** No

#### Reproduction Command
```bash
skeptic run --scenario audit/scenarios/files.write-file.sample-01.001.yaml --profile audit/profile.yaml --seeds 1
```

#### Evidence Cassettes

- `baseline/cassettes/20261103-191146-946dfc__files.write-file.sample-01.001__A03__1.jsonl`

- `verify/cassettes/20261103-191529-f5e7b1__files.write-file.sample-01.001__A03__2.jsonl`

- `verify/cassettes/20261103-191529-f5e7b1__files.write-file.sample-01.001__A03__3.jsonl`


#### Recommended Fix
Agent accepted corrupted or empty output from 'write_file' (fault A03). Enable G01 Evidence Contract and G02 Schema Validation guard. Add explicit client validation ensuring required fields are non-empty.

---

### Finding `FINDING-030`: list_cities under L01 (MEDIUM)

- **Tool:** `list_cities`
- **Fault Injected:** `L01`
- **Observed Outcome:** `FALSE_SUCCESS`
- **Replication Rate:** `3/3` (verified across multiple seeds)
- **Fix Verified:** No

#### Reproduction Command
```bash
skeptic run --scenario audit/scenarios/weather.list-cities.sample-01.001.yaml --profile audit/profile.yaml --seeds 1
```

#### Evidence Cassettes

- `baseline/cassettes/20261103-191146-946dfc__weather.list-cities.sample-01.001__L01__1.jsonl`

- `verify/cassettes/20261103-191529-f5e7b1__weather.list-cities.sample-01.001__L01__2.jsonl`

- `verify/cassettes/20261103-191529-f5e7b1__weather.list-cities.sample-01.001__L01__3.jsonl`


#### Recommended Fix
Agent accepted corrupted or empty output from 'list_cities' (fault L01). Enable G01 Evidence Contract and G02 Schema Validation guard. Add explicit client validation ensuring required fields are non-empty.

---

### Finding `FINDING-031`: list_cities under L02 (MEDIUM)

- **Tool:** `list_cities`
- **Fault Injected:** `L02`
- **Observed Outcome:** `FALSE_SUCCESS`
- **Replication Rate:** `3/3` (verified across multiple seeds)
- **Fix Verified:** No

#### Reproduction Command
```bash
skeptic run --scenario audit/scenarios/weather.list-cities.sample-01.001.yaml --profile audit/profile.yaml --seeds 1
```

#### Evidence Cassettes

- `baseline/cassettes/20261103-191146-946dfc__weather.list-cities.sample-01.001__L02__1.jsonl`

- `verify/cassettes/20261103-191529-f5e7b1__weather.list-cities.sample-01.001__L02__2.jsonl`

- `verify/cassettes/20261103-191529-f5e7b1__weather.list-cities.sample-01.001__L02__3.jsonl`


#### Recommended Fix
Agent accepted corrupted or empty output from 'list_cities' (fault L02). Enable G01 Evidence Contract and G02 Schema Validation guard. Add explicit client validation ensuring required fields are non-empty.

---

### Finding `FINDING-032`: list_cities under L03 (MEDIUM)

- **Tool:** `list_cities`
- **Fault Injected:** `L03`
- **Observed Outcome:** `FALSE_SUCCESS`
- **Replication Rate:** `3/3` (verified across multiple seeds)
- **Fix Verified:** No

#### Reproduction Command
```bash
skeptic run --scenario audit/scenarios/weather.list-cities.sample-01.001.yaml --profile audit/profile.yaml --seeds 1
```

#### Evidence Cassettes

- `baseline/cassettes/20261103-191146-946dfc__weather.list-cities.sample-01.001__L03__1.jsonl`

- `verify/cassettes/20261103-191529-f5e7b1__weather.list-cities.sample-01.001__L03__2.jsonl`

- `verify/cassettes/20261103-191529-f5e7b1__weather.list-cities.sample-01.001__L03__3.jsonl`


#### Recommended Fix
Agent accepted corrupted or empty output from 'list_cities' (fault L03). Enable G01 Evidence Contract and G02 Schema Validation guard. Add explicit client validation ensuring required fields are non-empty.

---

### Finding `FINDING-033`: list_cities under L05 (MEDIUM)

- **Tool:** `list_cities`
- **Fault Injected:** `L05`
- **Observed Outcome:** `FALSE_SUCCESS`
- **Replication Rate:** `3/3` (verified across multiple seeds)
- **Fix Verified:** No

#### Reproduction Command
```bash
skeptic run --scenario audit/scenarios/weather.list-cities.sample-01.001.yaml --profile audit/profile.yaml --seeds 1
```

#### Evidence Cassettes

- `baseline/cassettes/20261103-191146-946dfc__weather.list-cities.sample-01.001__L05__1.jsonl`

- `verify/cassettes/20261103-191529-f5e7b1__weather.list-cities.sample-01.001__L05__2.jsonl`

- `verify/cassettes/20261103-191529-f5e7b1__weather.list-cities.sample-01.001__L05__3.jsonl`


#### Recommended Fix
Agent accepted corrupted or empty output from 'list_cities' (fault L05). Enable G01 Evidence Contract and G02 Schema Validation guard. Add explicit client validation ensuring required fields are non-empty.

---

### Finding `FINDING-034`: list_cities under L06 (MEDIUM)

- **Tool:** `list_cities`
- **Fault Injected:** `L06`
- **Observed Outcome:** `FALSE_SUCCESS`
- **Replication Rate:** `3/3` (verified across multiple seeds)
- **Fix Verified:** No

#### Reproduction Command
```bash
skeptic run --scenario audit/scenarios/weather.list-cities.sample-01.001.yaml --profile audit/profile.yaml --seeds 1
```

#### Evidence Cassettes

- `baseline/cassettes/20261103-191146-946dfc__weather.list-cities.sample-01.001__L06__1.jsonl`

- `verify/cassettes/20261103-191529-f5e7b1__weather.list-cities.sample-01.001__L06__2.jsonl`

- `verify/cassettes/20261103-191529-f5e7b1__weather.list-cities.sample-01.001__L06__3.jsonl`


#### Recommended Fix
Agent accepted corrupted or empty output from 'list_cities' (fault L06). Enable G01 Evidence Contract and G02 Schema Validation guard. Add explicit client validation ensuring required fields are non-empty.

---

### Finding `FINDING-035`: list_cities under S01 (MEDIUM)

- **Tool:** `list_cities`
- **Fault Injected:** `S01`
- **Observed Outcome:** `FALSE_SUCCESS`
- **Replication Rate:** `3/3` (verified across multiple seeds)
- **Fix Verified:** No

#### Reproduction Command
```bash
skeptic run --scenario audit/scenarios/weather.list-cities.sample-01.001.yaml --profile audit/profile.yaml --seeds 1
```

#### Evidence Cassettes

- `baseline/cassettes/20261103-191146-946dfc__weather.list-cities.sample-01.001__S01__1.jsonl`

- `verify/cassettes/20261103-191529-f5e7b1__weather.list-cities.sample-01.001__S01__2.jsonl`

- `verify/cassettes/20261103-191529-f5e7b1__weather.list-cities.sample-01.001__S01__3.jsonl`


#### Recommended Fix
Agent accepted corrupted or empty output from 'list_cities' (fault S01). Enable G01 Evidence Contract and G02 Schema Validation guard. Add explicit client validation ensuring required fields are non-empty.

---

### Finding `FINDING-036`: list_cities under S02 (MEDIUM)

- **Tool:** `list_cities`
- **Fault Injected:** `S02`
- **Observed Outcome:** `FALSE_SUCCESS`
- **Replication Rate:** `3/3` (verified across multiple seeds)
- **Fix Verified:** No

#### Reproduction Command
```bash
skeptic run --scenario audit/scenarios/weather.list-cities.sample-01.001.yaml --profile audit/profile.yaml --seeds 1
```

#### Evidence Cassettes

- `baseline/cassettes/20261103-191146-946dfc__weather.list-cities.sample-01.001__S02__1.jsonl`

- `verify/cassettes/20261103-191529-f5e7b1__weather.list-cities.sample-01.001__S02__2.jsonl`

- `verify/cassettes/20261103-191529-f5e7b1__weather.list-cities.sample-01.001__S02__3.jsonl`


#### Recommended Fix
Agent accepted corrupted or empty output from 'list_cities' (fault S02). Enable G01 Evidence Contract and G02 Schema Validation guard. Add explicit client validation ensuring required fields are non-empty.

---

### Finding `FINDING-037`: list_cities under S03 (MEDIUM)

- **Tool:** `list_cities`
- **Fault Injected:** `S03`
- **Observed Outcome:** `FALSE_SUCCESS`
- **Replication Rate:** `3/3` (verified across multiple seeds)
- **Fix Verified:** No

#### Reproduction Command
```bash
skeptic run --scenario audit/scenarios/weather.list-cities.sample-01.001.yaml --profile audit/profile.yaml --seeds 1
```

#### Evidence Cassettes

- `baseline/cassettes/20261103-191146-946dfc__weather.list-cities.sample-01.001__S03__1.jsonl`

- `verify/cassettes/20261103-191529-f5e7b1__weather.list-cities.sample-01.001__S03__2.jsonl`

- `verify/cassettes/20261103-191529-f5e7b1__weather.list-cities.sample-01.001__S03__3.jsonl`


#### Recommended Fix
Agent accepted corrupted or empty output from 'list_cities' (fault S03). Enable G01 Evidence Contract and G02 Schema Validation guard. Add explicit client validation ensuring required fields are non-empty.

---

### Finding `FINDING-038`: list_cities under S04 (MEDIUM)

- **Tool:** `list_cities`
- **Fault Injected:** `S04`
- **Observed Outcome:** `FALSE_SUCCESS`
- **Replication Rate:** `3/3` (verified across multiple seeds)
- **Fix Verified:** No

#### Reproduction Command
```bash
skeptic run --scenario audit/scenarios/weather.list-cities.sample-01.001.yaml --profile audit/profile.yaml --seeds 1
```

#### Evidence Cassettes

- `baseline/cassettes/20261103-191146-946dfc__weather.list-cities.sample-01.001__S04__1.jsonl`

- `verify/cassettes/20261103-191529-f5e7b1__weather.list-cities.sample-01.001__S04__2.jsonl`

- `verify/cassettes/20261103-191529-f5e7b1__weather.list-cities.sample-01.001__S04__3.jsonl`


#### Recommended Fix
Agent accepted corrupted or empty output from 'list_cities' (fault S04). Enable G01 Evidence Contract and G02 Schema Validation guard. Add explicit client validation ensuring required fields are non-empty.

---

### Finding `FINDING-039`: list_cities under S06 (MEDIUM)

- **Tool:** `list_cities`
- **Fault Injected:** `S06`
- **Observed Outcome:** `FALSE_SUCCESS`
- **Replication Rate:** `3/3` (verified across multiple seeds)
- **Fix Verified:** No

#### Reproduction Command
```bash
skeptic run --scenario audit/scenarios/weather.list-cities.sample-01.001.yaml --profile audit/profile.yaml --seeds 1
```

#### Evidence Cassettes

- `baseline/cassettes/20261103-191146-946dfc__weather.list-cities.sample-01.001__S06__1.jsonl`

- `verify/cassettes/20261103-191529-f5e7b1__weather.list-cities.sample-01.001__S06__2.jsonl`

- `verify/cassettes/20261103-191529-f5e7b1__weather.list-cities.sample-01.001__S06__3.jsonl`


#### Recommended Fix
Agent accepted corrupted or empty output from 'list_cities' (fault S06). Enable G01 Evidence Contract and G02 Schema Validation guard. Add explicit client validation ensuring required fields are non-empty.

---

### Finding `FINDING-040`: list_cities under S07 (MEDIUM)

- **Tool:** `list_cities`
- **Fault Injected:** `S07`
- **Observed Outcome:** `FALSE_SUCCESS`
- **Replication Rate:** `3/3` (verified across multiple seeds)
- **Fix Verified:** No

#### Reproduction Command
```bash
skeptic run --scenario audit/scenarios/weather.list-cities.sample-01.001.yaml --profile audit/profile.yaml --seeds 1
```

#### Evidence Cassettes

- `baseline/cassettes/20261103-191146-946dfc__weather.list-cities.sample-01.001__S07__1.jsonl`

- `verify/cassettes/20261103-191529-f5e7b1__weather.list-cities.sample-01.001__S07__2.jsonl`

- `verify/cassettes/20261103-191529-f5e7b1__weather.list-cities.sample-01.001__S07__3.jsonl`


#### Recommended Fix
Agent accepted corrupted or empty output from 'list_cities' (fault S07). Enable G01 Evidence Contract and G02 Schema Validation guard. Add explicit client validation ensuring required fields are non-empty.

---

### Finding `FINDING-041`: list_cities under S08 (MEDIUM)

- **Tool:** `list_cities`
- **Fault Injected:** `S08`
- **Observed Outcome:** `FALSE_SUCCESS`
- **Replication Rate:** `3/3` (verified across multiple seeds)
- **Fix Verified:** No

#### Reproduction Command
```bash
skeptic run --scenario audit/scenarios/weather.list-cities.sample-01.001.yaml --profile audit/profile.yaml --seeds 1
```

#### Evidence Cassettes

- `baseline/cassettes/20261103-191146-946dfc__weather.list-cities.sample-01.001__S08__1.jsonl`

- `verify/cassettes/20261103-191529-f5e7b1__weather.list-cities.sample-01.001__S08__2.jsonl`

- `verify/cassettes/20261103-191529-f5e7b1__weather.list-cities.sample-01.001__S08__3.jsonl`


#### Recommended Fix
Agent accepted corrupted or empty output from 'list_cities' (fault S08). Enable G01 Evidence Contract and G02 Schema Validation guard. Add explicit client validation ensuring required fields are non-empty.

---

### Finding `FINDING-042`: list_cities under A01 (MEDIUM)

- **Tool:** `list_cities`
- **Fault Injected:** `A01`
- **Observed Outcome:** `FALSE_SUCCESS`
- **Replication Rate:** `3/3` (verified across multiple seeds)
- **Fix Verified:** No

#### Reproduction Command
```bash
skeptic run --scenario audit/scenarios/weather.list-cities.sample-01.001.yaml --profile audit/profile.yaml --seeds 1
```

#### Evidence Cassettes

- `baseline/cassettes/20261103-191146-946dfc__weather.list-cities.sample-01.001__A01__1.jsonl`

- `verify/cassettes/20261103-191529-f5e7b1__weather.list-cities.sample-01.001__A01__2.jsonl`

- `verify/cassettes/20261103-191529-f5e7b1__weather.list-cities.sample-01.001__A01__3.jsonl`


#### Recommended Fix
Agent accepted corrupted or empty output from 'list_cities' (fault A01). Enable G01 Evidence Contract and G02 Schema Validation guard. Add explicit client validation ensuring required fields are non-empty.

---

### Finding `FINDING-043`: list_cities under A02 (MEDIUM)

- **Tool:** `list_cities`
- **Fault Injected:** `A02`
- **Observed Outcome:** `FALSE_SUCCESS`
- **Replication Rate:** `3/3` (verified across multiple seeds)
- **Fix Verified:** No

#### Reproduction Command
```bash
skeptic run --scenario audit/scenarios/weather.list-cities.sample-01.001.yaml --profile audit/profile.yaml --seeds 1
```

#### Evidence Cassettes

- `baseline/cassettes/20261103-191146-946dfc__weather.list-cities.sample-01.001__A02__1.jsonl`

- `verify/cassettes/20261103-191529-f5e7b1__weather.list-cities.sample-01.001__A02__2.jsonl`

- `verify/cassettes/20261103-191529-f5e7b1__weather.list-cities.sample-01.001__A02__3.jsonl`


#### Recommended Fix
Agent accepted corrupted or empty output from 'list_cities' (fault A02). Enable G01 Evidence Contract and G02 Schema Validation guard. Add explicit client validation ensuring required fields are non-empty.

---

### Finding `FINDING-044`: list_cities under A03 (MEDIUM)

- **Tool:** `list_cities`
- **Fault Injected:** `A03`
- **Observed Outcome:** `FALSE_SUCCESS`
- **Replication Rate:** `3/3` (verified across multiple seeds)
- **Fix Verified:** No

#### Reproduction Command
```bash
skeptic run --scenario audit/scenarios/weather.list-cities.sample-01.001.yaml --profile audit/profile.yaml --seeds 1
```

#### Evidence Cassettes

- `baseline/cassettes/20261103-191146-946dfc__weather.list-cities.sample-01.001__A03__1.jsonl`

- `verify/cassettes/20261103-191529-f5e7b1__weather.list-cities.sample-01.001__A03__2.jsonl`

- `verify/cassettes/20261103-191529-f5e7b1__weather.list-cities.sample-01.001__A03__3.jsonl`


#### Recommended Fix
Agent accepted corrupted or empty output from 'list_cities' (fault A03). Enable G01 Evidence Contract and G02 Schema Validation guard. Add explicit client validation ensuring required fields are non-empty.

---

### Finding `FINDING-045`: read_file under L01 (MEDIUM)

- **Tool:** `read_file`
- **Fault Injected:** `L01`
- **Observed Outcome:** `FALSE_SUCCESS`
- **Replication Rate:** `3/3` (verified across multiple seeds)
- **Fix Verified:** No

#### Reproduction Command
```bash
skeptic run --scenario audit/scenarios/files.read-file.sample-01.001.yaml --profile audit/profile.yaml --seeds 1
```

#### Evidence Cassettes

- `baseline/cassettes/20261103-191146-946dfc__files.read-file.sample-01.001__L01__1.jsonl`

- `verify/cassettes/20261103-191529-f5e7b1__files.read-file.sample-01.001__L01__2.jsonl`

- `verify/cassettes/20261103-191529-f5e7b1__files.read-file.sample-01.001__L01__3.jsonl`


#### Recommended Fix
Agent accepted corrupted or empty output from 'read_file' (fault L01). Enable G01 Evidence Contract and G02 Schema Validation guard. Add explicit client validation ensuring required fields are non-empty.

---

### Finding `FINDING-046`: read_file under L02 (MEDIUM)

- **Tool:** `read_file`
- **Fault Injected:** `L02`
- **Observed Outcome:** `FALSE_SUCCESS`
- **Replication Rate:** `3/3` (verified across multiple seeds)
- **Fix Verified:** No

#### Reproduction Command
```bash
skeptic run --scenario audit/scenarios/files.read-file.sample-01.001.yaml --profile audit/profile.yaml --seeds 1
```

#### Evidence Cassettes

- `baseline/cassettes/20261103-191146-946dfc__files.read-file.sample-01.001__L02__1.jsonl`

- `verify/cassettes/20261103-191529-f5e7b1__files.read-file.sample-01.001__L02__2.jsonl`

- `verify/cassettes/20261103-191529-f5e7b1__files.read-file.sample-01.001__L02__3.jsonl`


#### Recommended Fix
Agent accepted corrupted or empty output from 'read_file' (fault L02). Enable G01 Evidence Contract and G02 Schema Validation guard. Add explicit client validation ensuring required fields are non-empty.

---

### Finding `FINDING-047`: read_file under L03 (MEDIUM)

- **Tool:** `read_file`
- **Fault Injected:** `L03`
- **Observed Outcome:** `FALSE_SUCCESS`
- **Replication Rate:** `3/3` (verified across multiple seeds)
- **Fix Verified:** No

#### Reproduction Command
```bash
skeptic run --scenario audit/scenarios/files.read-file.sample-01.001.yaml --profile audit/profile.yaml --seeds 1
```

#### Evidence Cassettes

- `baseline/cassettes/20261103-191146-946dfc__files.read-file.sample-01.001__L03__1.jsonl`

- `verify/cassettes/20261103-191529-f5e7b1__files.read-file.sample-01.001__L03__2.jsonl`

- `verify/cassettes/20261103-191529-f5e7b1__files.read-file.sample-01.001__L03__3.jsonl`


#### Recommended Fix
Agent accepted corrupted or empty output from 'read_file' (fault L03). Enable G01 Evidence Contract and G02 Schema Validation guard. Add explicit client validation ensuring required fields are non-empty.

---

### Finding `FINDING-048`: read_file under L05 (MEDIUM)

- **Tool:** `read_file`
- **Fault Injected:** `L05`
- **Observed Outcome:** `FALSE_SUCCESS`
- **Replication Rate:** `3/3` (verified across multiple seeds)
- **Fix Verified:** No

#### Reproduction Command
```bash
skeptic run --scenario audit/scenarios/files.read-file.sample-01.001.yaml --profile audit/profile.yaml --seeds 1
```

#### Evidence Cassettes

- `baseline/cassettes/20261103-191146-946dfc__files.read-file.sample-01.001__L05__1.jsonl`

- `verify/cassettes/20261103-191529-f5e7b1__files.read-file.sample-01.001__L05__2.jsonl`

- `verify/cassettes/20261103-191529-f5e7b1__files.read-file.sample-01.001__L05__3.jsonl`


#### Recommended Fix
Agent accepted corrupted or empty output from 'read_file' (fault L05). Enable G01 Evidence Contract and G02 Schema Validation guard. Add explicit client validation ensuring required fields are non-empty.

---

### Finding `FINDING-049`: read_file under L06 (MEDIUM)

- **Tool:** `read_file`
- **Fault Injected:** `L06`
- **Observed Outcome:** `FALSE_SUCCESS`
- **Replication Rate:** `3/3` (verified across multiple seeds)
- **Fix Verified:** No

#### Reproduction Command
```bash
skeptic run --scenario audit/scenarios/files.read-file.sample-01.001.yaml --profile audit/profile.yaml --seeds 1
```

#### Evidence Cassettes

- `baseline/cassettes/20261103-191146-946dfc__files.read-file.sample-01.001__L06__1.jsonl`

- `verify/cassettes/20261103-191529-f5e7b1__files.read-file.sample-01.001__L06__2.jsonl`

- `verify/cassettes/20261103-191529-f5e7b1__files.read-file.sample-01.001__L06__3.jsonl`


#### Recommended Fix
Agent accepted corrupted or empty output from 'read_file' (fault L06). Enable G01 Evidence Contract and G02 Schema Validation guard. Add explicit client validation ensuring required fields are non-empty.

---

### Finding `FINDING-050`: read_file under S01 (MEDIUM)

- **Tool:** `read_file`
- **Fault Injected:** `S01`
- **Observed Outcome:** `FALSE_SUCCESS`
- **Replication Rate:** `3/3` (verified across multiple seeds)
- **Fix Verified:** No

#### Reproduction Command
```bash
skeptic run --scenario audit/scenarios/files.read-file.sample-01.001.yaml --profile audit/profile.yaml --seeds 1
```

#### Evidence Cassettes

- `baseline/cassettes/20261103-191146-946dfc__files.read-file.sample-01.001__S01__1.jsonl`

- `verify/cassettes/20261103-191529-f5e7b1__files.read-file.sample-01.001__S01__2.jsonl`

- `verify/cassettes/20261103-191529-f5e7b1__files.read-file.sample-01.001__S01__3.jsonl`


#### Recommended Fix
Agent accepted corrupted or empty output from 'read_file' (fault S01). Enable G01 Evidence Contract and G02 Schema Validation guard. Add explicit client validation ensuring required fields are non-empty.

---

### Finding `FINDING-051`: read_file under S02 (MEDIUM)

- **Tool:** `read_file`
- **Fault Injected:** `S02`
- **Observed Outcome:** `FALSE_SUCCESS`
- **Replication Rate:** `3/3` (verified across multiple seeds)
- **Fix Verified:** No

#### Reproduction Command
```bash
skeptic run --scenario audit/scenarios/files.read-file.sample-01.001.yaml --profile audit/profile.yaml --seeds 1
```

#### Evidence Cassettes

- `baseline/cassettes/20261103-191146-946dfc__files.read-file.sample-01.001__S02__1.jsonl`

- `verify/cassettes/20261103-191529-f5e7b1__files.read-file.sample-01.001__S02__2.jsonl`

- `verify/cassettes/20261103-191529-f5e7b1__files.read-file.sample-01.001__S02__3.jsonl`


#### Recommended Fix
Agent accepted corrupted or empty output from 'read_file' (fault S02). Enable G01 Evidence Contract and G02 Schema Validation guard. Add explicit client validation ensuring required fields are non-empty.

---

### Finding `FINDING-052`: read_file under S03 (MEDIUM)

- **Tool:** `read_file`
- **Fault Injected:** `S03`
- **Observed Outcome:** `FALSE_SUCCESS`
- **Replication Rate:** `3/3` (verified across multiple seeds)
- **Fix Verified:** No

#### Reproduction Command
```bash
skeptic run --scenario audit/scenarios/files.read-file.sample-01.001.yaml --profile audit/profile.yaml --seeds 1
```

#### Evidence Cassettes

- `baseline/cassettes/20261103-191146-946dfc__files.read-file.sample-01.001__S03__1.jsonl`

- `verify/cassettes/20261103-191529-f5e7b1__files.read-file.sample-01.001__S03__2.jsonl`

- `verify/cassettes/20261103-191529-f5e7b1__files.read-file.sample-01.001__S03__3.jsonl`


#### Recommended Fix
Agent accepted corrupted or empty output from 'read_file' (fault S03). Enable G01 Evidence Contract and G02 Schema Validation guard. Add explicit client validation ensuring required fields are non-empty.

---

### Finding `FINDING-053`: read_file under S04 (MEDIUM)

- **Tool:** `read_file`
- **Fault Injected:** `S04`
- **Observed Outcome:** `FALSE_SUCCESS`
- **Replication Rate:** `3/3` (verified across multiple seeds)
- **Fix Verified:** No

#### Reproduction Command
```bash
skeptic run --scenario audit/scenarios/files.read-file.sample-01.001.yaml --profile audit/profile.yaml --seeds 1
```

#### Evidence Cassettes

- `baseline/cassettes/20261103-191146-946dfc__files.read-file.sample-01.001__S04__1.jsonl`

- `verify/cassettes/20261103-191529-f5e7b1__files.read-file.sample-01.001__S04__2.jsonl`

- `verify/cassettes/20261103-191529-f5e7b1__files.read-file.sample-01.001__S04__3.jsonl`


#### Recommended Fix
Agent accepted corrupted or empty output from 'read_file' (fault S04). Enable G01 Evidence Contract and G02 Schema Validation guard. Add explicit client validation ensuring required fields are non-empty.

---

### Finding `FINDING-054`: read_file under S05 (MEDIUM)

- **Tool:** `read_file`
- **Fault Injected:** `S05`
- **Observed Outcome:** `FALSE_SUCCESS`
- **Replication Rate:** `3/3` (verified across multiple seeds)
- **Fix Verified:** No

#### Reproduction Command
```bash
skeptic run --scenario audit/scenarios/files.read-file.sample-01.001.yaml --profile audit/profile.yaml --seeds 1
```

#### Evidence Cassettes

- `baseline/cassettes/20261103-191146-946dfc__files.read-file.sample-01.001__S05__1.jsonl`

- `verify/cassettes/20261103-191529-f5e7b1__files.read-file.sample-01.001__S05__2.jsonl`

- `verify/cassettes/20261103-191529-f5e7b1__files.read-file.sample-01.001__S05__3.jsonl`


#### Recommended Fix
Agent accepted corrupted or empty output from 'read_file' (fault S05). Enable G01 Evidence Contract and G02 Schema Validation guard. Add explicit client validation ensuring required fields are non-empty.

---

### Finding `FINDING-055`: read_file under S06 (MEDIUM)

- **Tool:** `read_file`
- **Fault Injected:** `S06`
- **Observed Outcome:** `FALSE_SUCCESS`
- **Replication Rate:** `3/3` (verified across multiple seeds)
- **Fix Verified:** No

#### Reproduction Command
```bash
skeptic run --scenario audit/scenarios/files.read-file.sample-01.001.yaml --profile audit/profile.yaml --seeds 1
```

#### Evidence Cassettes

- `baseline/cassettes/20261103-191146-946dfc__files.read-file.sample-01.001__S06__1.jsonl`

- `verify/cassettes/20261103-191529-f5e7b1__files.read-file.sample-01.001__S06__2.jsonl`

- `verify/cassettes/20261103-191529-f5e7b1__files.read-file.sample-01.001__S06__3.jsonl`


#### Recommended Fix
Agent accepted corrupted or empty output from 'read_file' (fault S06). Enable G01 Evidence Contract and G02 Schema Validation guard. Add explicit client validation ensuring required fields are non-empty.

---

### Finding `FINDING-056`: read_file under S07 (MEDIUM)

- **Tool:** `read_file`
- **Fault Injected:** `S07`
- **Observed Outcome:** `FALSE_SUCCESS`
- **Replication Rate:** `3/3` (verified across multiple seeds)
- **Fix Verified:** No

#### Reproduction Command
```bash
skeptic run --scenario audit/scenarios/files.read-file.sample-01.001.yaml --profile audit/profile.yaml --seeds 1
```

#### Evidence Cassettes

- `baseline/cassettes/20261103-191146-946dfc__files.read-file.sample-01.001__S07__1.jsonl`

- `verify/cassettes/20261103-191529-f5e7b1__files.read-file.sample-01.001__S07__2.jsonl`

- `verify/cassettes/20261103-191529-f5e7b1__files.read-file.sample-01.001__S07__3.jsonl`


#### Recommended Fix
Agent accepted corrupted or empty output from 'read_file' (fault S07). Enable G01 Evidence Contract and G02 Schema Validation guard. Add explicit client validation ensuring required fields are non-empty.

---

### Finding `FINDING-057`: read_file under S08 (MEDIUM)

- **Tool:** `read_file`
- **Fault Injected:** `S08`
- **Observed Outcome:** `FALSE_SUCCESS`
- **Replication Rate:** `3/3` (verified across multiple seeds)
- **Fix Verified:** No

#### Reproduction Command
```bash
skeptic run --scenario audit/scenarios/files.read-file.sample-01.001.yaml --profile audit/profile.yaml --seeds 1
```

#### Evidence Cassettes

- `baseline/cassettes/20261103-191146-946dfc__files.read-file.sample-01.001__S08__1.jsonl`

- `verify/cassettes/20261103-191529-f5e7b1__files.read-file.sample-01.001__S08__2.jsonl`

- `verify/cassettes/20261103-191529-f5e7b1__files.read-file.sample-01.001__S08__3.jsonl`


#### Recommended Fix
Agent accepted corrupted or empty output from 'read_file' (fault S08). Enable G01 Evidence Contract and G02 Schema Validation guard. Add explicit client validation ensuring required fields are non-empty.

---

### Finding `FINDING-058`: read_file under A01 (MEDIUM)

- **Tool:** `read_file`
- **Fault Injected:** `A01`
- **Observed Outcome:** `FALSE_SUCCESS`
- **Replication Rate:** `3/3` (verified across multiple seeds)
- **Fix Verified:** No

#### Reproduction Command
```bash
skeptic run --scenario audit/scenarios/files.read-file.sample-01.001.yaml --profile audit/profile.yaml --seeds 1
```

#### Evidence Cassettes

- `baseline/cassettes/20261103-191146-946dfc__files.read-file.sample-01.001__A01__1.jsonl`

- `verify/cassettes/20261103-191529-f5e7b1__files.read-file.sample-01.001__A01__2.jsonl`

- `verify/cassettes/20261103-191529-f5e7b1__files.read-file.sample-01.001__A01__3.jsonl`


#### Recommended Fix
Agent accepted corrupted or empty output from 'read_file' (fault A01). Enable G01 Evidence Contract and G02 Schema Validation guard. Add explicit client validation ensuring required fields are non-empty.

---

### Finding `FINDING-059`: read_file under A02 (MEDIUM)

- **Tool:** `read_file`
- **Fault Injected:** `A02`
- **Observed Outcome:** `FALSE_SUCCESS`
- **Replication Rate:** `3/3` (verified across multiple seeds)
- **Fix Verified:** No

#### Reproduction Command
```bash
skeptic run --scenario audit/scenarios/files.read-file.sample-01.001.yaml --profile audit/profile.yaml --seeds 1
```

#### Evidence Cassettes

- `baseline/cassettes/20261103-191146-946dfc__files.read-file.sample-01.001__A02__1.jsonl`

- `verify/cassettes/20261103-191529-f5e7b1__files.read-file.sample-01.001__A02__2.jsonl`

- `verify/cassettes/20261103-191529-f5e7b1__files.read-file.sample-01.001__A02__3.jsonl`


#### Recommended Fix
Agent accepted corrupted or empty output from 'read_file' (fault A02). Enable G01 Evidence Contract and G02 Schema Validation guard. Add explicit client validation ensuring required fields are non-empty.

---

### Finding `FINDING-060`: read_file under A03 (MEDIUM)

- **Tool:** `read_file`
- **Fault Injected:** `A03`
- **Observed Outcome:** `FALSE_SUCCESS`
- **Replication Rate:** `3/3` (verified across multiple seeds)
- **Fix Verified:** No

#### Reproduction Command
```bash
skeptic run --scenario audit/scenarios/files.read-file.sample-01.001.yaml --profile audit/profile.yaml --seeds 1
```

#### Evidence Cassettes

- `baseline/cassettes/20261103-191146-946dfc__files.read-file.sample-01.001__A03__1.jsonl`

- `verify/cassettes/20261103-191529-f5e7b1__files.read-file.sample-01.001__A03__2.jsonl`

- `verify/cassettes/20261103-191529-f5e7b1__files.read-file.sample-01.001__A03__3.jsonl`


#### Recommended Fix
Agent accepted corrupted or empty output from 'read_file' (fault A03). Enable G01 Evidence Contract and G02 Schema Validation guard. Add explicit client validation ensuring required fields are non-empty.

---


## Hardening Verification


### Comparison: Baseline vs Hardened Run

| Metric | Baseline | Hardened | Delta |
|---|---|---|---|
| **SKS** | 0.000 | 0.000 | Improved |
| **Recovery Rate (RR)** | 0.000 | 0.000 | Improved |
| **Safe Rate** | 0.000 | 0.000 | Improved |
| **False Success Rate (FSR)** | 0.000 | 0.000 | Decreased |
| **Silent Corruption Rate (SCR)** | 0.000 | 0.000 | Decreased |
| **Injection Compromise Rate (ICR)** | 0.000 | 0.000 | Decreased |


### Recommended Agent Configuration
1. **Enable Recommended Guards:**
   ```bash
   skeptic wrap <config_file> --guards recommended
   ```
   Active guards include G01 (Evidence Contract), G02 (Schema Validation), G04 (Emptiness/Truncation), and G06 (Loop Detection).
2. **Apply Evidence Contract System Prompt:**
   Add evidence contract constraints before final answer generation (`--prompt-variant evidence_contract`).
3. **Tool Error Handling Patches:**
   Ensure every MCP client tool dispatch has an explicit failure branch and does not treat error responses as successful execution.