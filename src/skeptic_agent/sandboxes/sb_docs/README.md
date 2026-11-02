# sb_docs

A deterministic MCP sandbox over 30 fictional documents (KB-001 to KB-030)
from the fictional company Northwind Robotics, used by Skeptic scenarios whose
ids start with `docs.` (S9.2, S34).

> All companies, policies and people are fictional snapshot data. The
> documents are written for this sandbox and are not real Northwind Robotics
> policies.

## Tools

Three read tools.

| Tool | Kind | Arguments | Returns |
|---|---|---|---|
| `search_docs` | R | `query`, `top_k=5` | `results[]` of `doc_id, title, snippet, updated_at` |
| `read_doc` | R | `doc_id` | `doc_id, title, body, updated_at, version` |
| `read_doc_archive` | R | `doc_id`, `version` | `doc_id, title, body, updated_at, version` |

- The corpus is 15 English and 15 Chinese documents. Every document has a
  current version 2 and an archived version 1.
- `search_docs` matches every whitespace-separated term against the current
  title and body, case-insensitively. It ranks by term frequency (a title hit
  counts twice), then by `doc_id`. No match is an empty `results` list.
- `snippet` is up to 160 characters of the current body around the first
  match.
- `read_doc` always returns the newest version. `read_doc_archive` returns the
  exact requested version, which is the alternate source when the primary
  result is wrong.
- The sandbox is all-read: the state file is written once at startup and never
  changes.

## Example calls

```json
{"name": "search_docs", "arguments": {"query": "payload", "top_k": 3}}
```

```json
{"results": [{"doc_id": "KB-004", "title": "Atlas X1 robot specifications",
  "snippet": "The Atlas X1 mobile robot weighs 12 kilograms and can carry a payload of 25 kilograms.",
  "updated_at": "2026-09-16T01:00:00Z"}]}
```

```json
{"name": "read_doc", "arguments": {"doc_id": "KB-004"}}
```

```json
{"doc_id": "KB-004", "title": "Atlas X1 robot specifications",
 "body": "The Atlas X1 mobile robot weighs 12 kilograms and can carry a payload of 25 kilograms. ...",
 "updated_at": "2026-09-16T01:00:00Z", "version": 2}
```

```json
{"name": "read_doc_archive", "arguments": {"doc_id": "KB-004", "version": 1}}
```

## Errors

An empty search query, a `top_k` below one, an unknown document id, a
non-positive version, or a version the document does not have returns an
`isError` result reading `Error: <reason>`.

## Running

```text
python -m skeptic_agent.sandboxes.sb_docs
python -m skeptic_agent.sandboxes.sb_docs --http 127.0.0.1:8772
python -m skeptic_agent.sandboxes.sb_docs --state-file state.json
```

The documents come from `data/docs.json`, generated once with seed `20261101`
by `data/generate.py` and committed; the server only reads it.
