# Leaderboard

The Agent Skepticism Leaderboard (智能体较真榜) ranks agent configurations by Skeptic Score. Configurations whose SKS confidence intervals overlap share one rank group.

The leaderboard pages are not published yet. The official S16.2 leaderboard run has not been done, so this preview claims no official leaderboard results. The generator is `site/build.py`.

A leaderboard run is a `skeptic.matrix/v1` file expanded across profiles and seeds. The model list for that run is `bench/leaderboard/models.yaml` (`skeptic.models/v1`). How SKS is computed is on the [metrics](concepts/metrics.md) page.
