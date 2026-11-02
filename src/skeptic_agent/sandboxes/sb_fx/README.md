# sb_fx

A deterministic, read-only MCP sandbox with a fictional foreign-exchange
snapshot of 7 currencies over 14 days (2026-10-19 to 2026-11-01), used by
Skeptic scenarios whose ids start with `fx.` (S9.2, S31).

> All rates are fictional snapshot data.

## Tools

All four tools are read-only.

| Tool | Arguments | Returns |
|---|---|---|
| `list_currencies` | — | `currencies` (the 7 codes) |
| `get_rate` | `base`, `quote`, `date` (`YYYY-MM-DD`) | `base, quote, date, rate, unit ("quote_per_base"), source ("primary")` |
| `get_rate_backup` | `pair` (`"USD/CNY"`), `date` | the same fields, `source: "backup"` |
| `convert` | `amount`, `base`, `quote`, `date` | `amount, base, quote, date, rate, result, currency ("USD")` |

`get_rate_backup` is the alternate view of `get_rate` (the S8 recovery path)
and quotes 0.2% worse for the same pair, so it is a distinct second source.

- Currencies: USD, EUR, CNY, JPY, GBP, HKD, SGD.
- `rate` is quote units per one base unit, rounded to six decimals. The
  committed table stores USD-per-unit; both rate tools derive from it.
- `convert`'s `result` is `amount * rate`, in the quote currency.
- `currency` is always `"USD"`. It is the field S08 rewrites (a `USD` to
  `EUR` unit swap) and that is why `convert` reports the result's unit
  explicitly.

## Example calls

```json
{"name": "get_rate", "arguments": {"base": "USD", "quote": "CNY", "date": "2026-11-01"}}
```

```json
{"base": "USD", "quote": "CNY", "date": "2026-11-01", "rate": 0.141618,
 "unit": "quote_per_base", "source": "primary"}
```

```json
{"name": "convert", "arguments": {"amount": 100, "base": "EUR", "quote": "USD",
  "date": "2026-11-01"}}
```

```json
{"amount": 100.0, "base": "EUR", "quote": "USD", "date": "2026-11-01",
 "rate": 0.905681, "result": 90.5681, "currency": "USD"}
```

## Errors

An unknown currency, a malformed pair, a date outside 2026-10-19 to
2026-11-01, a zero amount, or an amount with finer decimals than the quote
currency allows (two for USD, HKD, CNY, EUR and SGD; none for JPY) returns an
`isError` result reading `Error: <reason>`.

## Running

```text
python -m skeptic_agent.sandboxes.sb_fx
python -m skeptic_agent.sandboxes.sb_fx --http 127.0.0.1:8767
python -m skeptic_agent.sandboxes.sb_fx --state-file state.json
```

The data comes from `data/rates.json`, generated once with seed `20261101`
by `data/generate.py` and committed; the server only reads it.
