# sb_stocks

A deterministic, read-only MCP sandbox with a fictional market snapshot of 8
tickers over 60 trading days ending 2026-10-30, used by Skeptic scenarios
whose ids start with `stocks.` (S9.2, S32).

> All tickers, companies and prices are fictional snapshot data.

## Tools

All five tools are read-only.

| Tool | Arguments | Returns |
|---|---|---|
| `get_quote` | `ticker` | `ticker, price, currency ("USD"), change_pct, as_of` |
| `get_quote_delayed` | `ticker` | the same fields, `as_of` 15 minutes earlier |
| `get_history` | `ticker`, `start`, `end` (`YYYY-MM-DD`) | `ticker, bars[{date, open, high, low, close, volume}]` |
| `get_company_profile` | `ticker` | `ticker, name, sector, currency, listed_at, employees, headquarters` |
| `screen` | `sector`, `min_price`, `max_price` | `results[]` of the quotes in the sector and inclusive price range |

`get_quote_delayed` is the alternate view of `get_quote` (the S8 recovery
path). It reports the same last close with an earlier timestamp, because the
committed snapshot has no intraday walk.

- Tickers: `ACME`, `BOLT`, `CRUX`, `DYNA`, `ECHO`, `FLUX`, `GRIT`, `HELX`
  (case-insensitive arguments).
- `price` is the last close on 2026-10-30; `change_pct` is the change against
  the previous close, in percent.
- `bars` cover 2026-08-10 to 2026-10-30, weekdays only.
- Sectors: `energy`, `healthcare`, `logistics`, `manufacturing`, `media`,
  `technology`. `screen` returns an empty `results` list when nothing
  matches.

## Example calls

```json
{"name": "get_quote", "arguments": {"ticker": "ACME"}}
```

```json
{"ticker": "ACME", "price": 127.41, "currency": "USD", "change_pct": -0.86,
 "as_of": "2026-10-30T20:00:00Z"}
```

```json
{"name": "get_history", "arguments": {"ticker": "ACME",
  "start": "2026-10-26", "end": "2026-10-30"}}
```

```json
{"ticker": "ACME", "bars": [{"date": "2026-10-26", "open": 129.12,
  "high": 130.68, "low": 127.51, "close": 129.07, "volume": 1075535}]}
```

The example above shows the first of the five bars 2026-10-26 to 2026-10-30.

## Errors

An unknown ticker, an invalid date, a date after the last trading day, a
reversed window, a window with no bar, an unknown sector, or a price range
whose minimum exceeds its maximum returns an `isError` result reading
`Error: <reason>`.

## Running

```text
python -m skeptic_agent.sandboxes.sb_stocks
python -m skeptic_agent.sandboxes.sb_stocks --http 127.0.0.1:8768
python -m skeptic_agent.sandboxes.sb_stocks --state-file state.json
```

The data comes from `data/market.json`, generated once with seed `20261101`
by `data/generate.py` and committed; the server only reads it.
