# Leaderboard site (L72 draft)

Build the static board from the repository root:

```text
uv run python site/build.py
uv run python site/build.py --results path/to/results.jsonl --out site/out
```

With no `--results`, the generator uses a smoke placeholder. Those numbers are not an L71 run.

Pages land in `site/out/leaderboard/`:

- `index.html` — rank group, config, SKS with its interval, RR, SafeRate, FSR, SCR, ICR, cost. Filters hide rows by model group, origin, framework, and guards. Rank groups stay the full-board groups.
- `config/<id>.html` — metric cards, fault by outcome, worst scenarios, cassette archive links.
- `fault/<FAULT>.html` — one page per fault, with each config's outcome counts.
- `guards.html` — guards on minus guards off for FSR, SCR, and SKS, with a paired bootstrap interval.
- `methodology.html` — faults, formulas, seeds, prices, limits, and the `leaderboard-request` issue template.
- `data/results.csv`, `data/summary.json`, and `cassettes*.zip` (each zip at most 100 MB).

CSS and the filter script are in the pages. The build does not load a CDN.

榜单页在 `site/out/leaderboard/`。不传 `--results` 时用的是冒烟占位数据，不是 L71 的正式运行。名次组按 SKS 点估计排序，相邻置信区间重叠的配置合为同一组（例如 `T-3`）。
