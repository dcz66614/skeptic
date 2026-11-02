# sb_sqlshop

A deterministic MCP sandbox over an in-memory SQLite shop, used by Skeptic
scenarios whose ids start with `sqlshop.` (S9.2, S34).

> All products, orders and prices are fictional snapshot data. The customers
> are the fictional people shared with sb_crm, sb_orders and sb_mail
> (C-1001 to C-1040).

## Tools

Three read tools.

| Tool | Kind | Arguments | Returns |
|---|---|---|---|
| `get_schema` | R | none | `tables[]` of `name, columns[]` (`name, type, not_null, primary_key`) |
| `run_query` | R | `sql` | `columns[], rows[[...]], row_count` |
| `run_query_replica` | R | `sql` | `columns[], rows[[...]], row_count` |

- The database is built in memory from `data/shop.sql` on every call:
  `products` (40), `customers` (40), `orders` (120) and `order_items` (300).
- `run_query` and `run_query_replica` accept exactly one `SELECT` statement.
  `run_query_replica` is the alternate source; it runs the same statement on a
  fresh copy of the same committed data.
- The sandbox is all-read: the state file is written once at startup and never
  changes.

## Example calls

```json
{"name": "get_schema", "arguments": {}}
```

```json
{"tables": [{"name": "products", "columns": [{"name": "product_id",
  "type": "TEXT", "not_null": false, "primary_key": true}]}]}
```

```json
{"name": "run_query", "arguments": {"sql": "SELECT product_id, name, price FROM products ORDER BY product_id LIMIT 2"}}
```

```json
{"columns": ["product_id", "name", "price"],
 "rows": [["P-1001", "Atlas Arm X1", 665.87], ["P-1002", "Borealis Arm S2", 866.97]],
 "row_count": 2}
```

```json
{"name": "run_query_replica", "arguments": {"sql": "SELECT COUNT(*) AS n FROM orders"}}
```

## Errors

An empty statement, more than one statement, a statement that does not start
with `SELECT`, and any SQLite syntax or name error return an `isError` result
reading `Error: <reason>`; the database is never modified.

## Running

```text
python -m skeptic_agent.sandboxes.sb_sqlshop
python -m skeptic_agent.sandboxes.sb_sqlshop --http 127.0.0.1:8773
python -m skeptic_agent.sandboxes.sb_sqlshop --state-file state.json
```

The database script is generated once with seed `20261101` by
`data/generate.py` and committed; the server only reads it.
