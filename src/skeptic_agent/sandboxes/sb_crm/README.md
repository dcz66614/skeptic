# sb_crm

A deterministic MCP sandbox over a fictional customer table of 40 customers
(C-1001 to C-1040) and 80 notes, used by Skeptic scenarios whose ids start
with `crm.` (S9.2, S32).

> All names, emails, companies and notes are fictional snapshot data; the
> customer table is the one shared with sb_orders and sb_mail (S9.1 item 9).

## Tools

Three read tools, two write tools.

| Tool | Kind | Arguments | Returns |
|---|---|---|---|
| `search_customers` | R | `query` | `customers[]` of `id, name, email, tier, city, created_at` |
| `get_customer` | R | `customer_id` | `id, name, email, tier, city, created_at` |
| `update_customer_email` | W | `customer_id`, `email` | `status ("ok"), customer_id, email` |
| `add_note` | W | `customer_id`, `text` | `status ("ok"), customer_id, note_id` |
| `list_notes` | R | `customer_id` | `notes[]` of `id, customer_id, text, created_at` |

- `search_customers` matches the query (case-insensitive) against the id,
  name, email, city, tier and the text of the customer's notes. An empty
  query lists every customer. No match is an empty `customers` list, not an
  error.
- `update_customer_email` is idempotent: repeating it stores the same email
  and returns the same result.
- `add_note` is not idempotent: each call appends a note with a new id
  (`N-3081`, `N-3082`, ...). Note text may not be empty or longer than 500
  characters.
- The state holds `customers` (keyed by id) and `notes` (S9.2). Both write
  tools update the state file after they succeed.

## Example calls

```json
{"name": "search_customers", "arguments": {"query": "Paris"}}
```

```json
{"customers": [{"id": "C-1001", "name": "Ada Castillo",
  "email": "ada.castillo.01@example.com", "tier": "enterprise",
  "city": "Paris", "created_at": "2025-03-31T22:15:32Z"}]}
```

```json
{"name": "update_customer_email",
 "arguments": {"customer_id": "C-1004", "email": "dmitri.rossi.04@example.com"}}
```

```json
{"status": "ok", "customer_id": "C-1004", "email": "dmitri.rossi.04@example.com"}
```

## Errors

An unknown customer id, an invalid email, and empty or oversized note text
return an `isError` result reading `Error: <reason>`, and a failed write
leaves the state unchanged. `search_customers` never fails on a query.

## Running

```text
python -m skeptic_agent.sandboxes.sb_crm
python -m skeptic_agent.sandboxes.sb_crm --http 127.0.0.1:8769
python -m skeptic_agent.sandboxes.sb_crm --state-file state.json
```

The customers come from the shared `sb_common/data/customers.json`; the notes
come from `data/notes.json`, generated once with seed `20261101` by
`data/generate.py` and committed. The server only reads both.
