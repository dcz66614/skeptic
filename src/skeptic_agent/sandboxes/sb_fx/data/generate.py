"""Generate the sb_fx rate table once with the fixed seed (20261101).

The output, ``rates.json``, is committed; the server only reads it
(S9.1 item 3). Every value comes from one ``random.Random(SEED)`` draw in a
fixed order, so re-running this module rewrites the same bytes.

S9.2 fixes the shape: 7 currencies over 14 days (2026-10-19 to 2026-11-01)
against USD. The table stores the USD-per-unit rate of each currency and the
server derives every pair, so ``get_rate`` and ``get_rate_backup`` always
agree. ``get_rate``'s ``source`` is ``"primary"``; the backup tool appends
a fixed spread, which keeps it a distinct (slightly worse) quote.

Run from the repository root:

    uv run python -m skeptic_agent.sandboxes.sb_fx.data.generate
"""

import json
import random
from datetime import timedelta
from pathlib import Path

from skeptic_agent.sandboxes.sb_common.clock import format_iso, parse_instant

SEED = 20261101
"""The fixed generator seed every sandbox shares (S9.1)."""

OUTPUT = Path(__file__).resolve().parent / "rates.json"
"""Where the committed table lives."""

CURRENCIES: dict[str, float] = {
    "USD": 1.0,
    "EUR": 1.09,
    "CNY": 0.14,
    "JPY": 0.0066,
    "GBP": 1.32,
    "HKD": 0.128,
    "SGD": 0.77,
}
"""The 7 currencies (S9.2) and their base USD-per-unit rate."""

START_DAY = parse_instant("2026-10-19T00:00:00Z")
"""The first rate day (S9.2)."""

DAYS = 14
"""S9.2: 14 days, 2026-10-19 to 2026-11-01."""

RATE_DIGITS = 6
"""The rate precision, enough for JPY per unit."""


def build_rates() -> dict[str, dict[str, float]]:
    """Build the USD-per-unit table deterministically.

    Returns:
        ``{currency: {date: usd_per_unit}}`` for all 7 currencies over the
        14 days. USD is exactly ``1.0`` on every day.
    """
    table: dict[str, dict[str, float]] = {}
    for code, base in CURRENCIES.items():
        days: dict[str, float] = {}
        for offset in range(DAYS):
            date = (START_DAY + timedelta(days=offset)).strftime("%Y-%m-%d")
            if code == "USD":
                days[date] = 1.0
                continue
            drift = random.Random(f"{SEED}|{code}|{date}").uniform(-0.015, 0.015)
            days[date] = round(base * (1.0 + drift), RATE_DIGITS)
        table[code] = days
    return table


def issued(offset: int) -> str:
    """Return the quote time of a day's rates.

    Args:
        offset: Days after ``2026-10-19``.

    Returns:
        The frozen day at 08:00 UTC, as the S9.1 ``...Z`` string.
    """
    return format_iso(START_DAY + timedelta(days=offset, hours=8))


def write(path: Path = OUTPUT) -> None:
    """Write the table to ``path``.

    Args:
        path: The destination file.
    """
    text = json.dumps(build_rates(), ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    path.write_text(text, encoding="utf-8", newline="\n")


if __name__ == "__main__":
    write()
