# sb_weather

A deterministic, read-only MCP sandbox with a fictional weather snapshot of
12 cities over 14 days (2026-11-01 to 2026-11-14), used by Skeptic scenarios
whose ids start with `weather.` (S9.2, S31).

> All forecasts are fictional snapshot data. Only the city names are real.

## Tools

All four tools are read-only.

| Tool | Arguments | Returns |
|---|---|---|
| `list_cities` | — | `cities` (the 12 city names, S9.2 order) |
| `get_forecast` | `city`, `date` (`YYYY-MM-DD`) | `city, date, max_c, min_c, condition, unit ("C"), issued_at` |
| `get_forecast_v2` | `location`, `day` (`YYYY-MM-DD`) | `location, day, max_temp_c, min_temp_c, summary, updated` |
| `get_forecast_consensus` | `city`, `date` (`YYYY-MM-DD`) | `city, date, max_c, sources` |

`get_forecast_v2` is the alternate view of `get_forecast` (the recovery path
of S8 scenarios) and `get_forecast_consensus` is the third source S09 needs.

- Cities: Paris, Lyon, Berlin, Munich, Tokyo, Osaka, Beijing, Shanghai,
  Hangzhou, New York, Boston, Sydney.
- `condition` is one of `clear`, `partly cloudy`, `cloudy`, `rain`, `showers`;
  the v2 `summary` is the same, sentence-cased.
- `issued_at` and `updated` are relative to the frozen clock, `06:00` on the
  forecast day (`2026-11-0xT06:00:00Z`).
- The first seven days have two model sources; `get_forecast_consensus`
  returns their mean (`sources: ["source_a", "source_b"]`). Later days have a
  single source.

## Example calls

```json
{"name": "get_forecast", "arguments": {"city": "Paris", "date": "2026-11-02"}}
```

```json
{"city": "Paris", "date": "2026-11-02", "max_c": 14.5, "min_c": 7.7,
 "condition": "partly cloudy", "unit": "C", "issued_at": "2026-11-02T06:00:00Z"}
```

```json
{"name": "get_forecast_consensus", "arguments": {"city": "Paris", "date": "2026-11-02"}}
```

```json
{"city": "Paris", "date": "2026-11-02", "max_c": 14.6, "sources": ["source_a", "source_b"]}
```

## Errors

An unknown city, an unparseable date or a day outside 2026-11-01 to
2026-11-14 returns an `isError` result whose text is `Error: <reason>`.

## Running

```text
python -m skeptic_agent.sandboxes.sb_weather
python -m skeptic_agent.sandboxes.sb_weather --http 127.0.0.1:8766
python -m skeptic_agent.sandboxes.sb_weather --state-file state.json
```

The data comes from `data/forecasts.json`, generated once with seed
`20261101` by `data/generate.py` and committed; the server only reads it.
