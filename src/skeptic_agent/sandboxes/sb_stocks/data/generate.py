"""Generate the sb_stocks market snapshot once with the fixed seed (20261101).

The output, ``market.json``, is committed; the server only reads it
(S9.1 item 3). Every value comes from one ``random.Random(SEED)`` draw in a
fixed order, so re-running this module rewrites the same bytes.

S9.2 fixes the shape: 8 fictional tickers over 60 trading days ending on the
day before the frozen instant (2026-11-01), so the last bar is 2026-10-30
(the 31st is a Saturday). Each ticker also has a company profile with a real
sector name for ``screen``; ``sector`` is a plain lowercase word (the S04
integer factor applies to it cleanly). The S03 anchor is ``as_of`` and
``last_trade``: both are the last trading day, so moving them ``days`` back
makes the quote visibly stale.

Run from the repository root:

    uv run python -m skeptic_agent.sandboxes.sb_stocks.data.generate
"""

import json
import random
from datetime import timedelta
from pathlib import Path

from skeptic_agent.sandboxes.sb_common.clock import parse_instant

SEED = 20261101
"""The fixed generator seed every sandbox shares (S9.1)."""

OUTPUT = Path(__file__).resolve().parent / "market.json"
"""Where the committed table lives."""

TICKERS = ("ACME", "BOLT", "CRUX", "DYNA", "ECHO", "FLUX", "GRIT", "HELX")
"""The 8 fictional tickers (S9.2)."""

BASES: dict[str, tuple[float, str, str, str]] = {
    "ACME": (128.0, "manufacturing", "Acme Fabrication", "2019-04-12"),
    "BOLT": (46.5, "energy", "Bolt Grid Power", "2017-09-01"),
    "CRUX": (213.75, "technology", "Crux Analytics", "2020-02-24"),
    "DYNA": (86.2, "logistics", "Dyna Freight", "2018-06-15"),
    "ECHO": (31.4, "media", "Echo Soundworks", "2021-11-05"),
    "FLUX": (172.9, "technology", "Flux Semiconductor", "2016-03-30"),
    "GRIT": (58.6, "manufacturing", "Grit Machine Works", "2015-08-19"),
    "HELX": (402.3, "healthcare", "Helx Bioworks", "2022-01-10"),
}
"""The 8 fictional companies: (base price, sector, name, listing date)."""

LAST_TRADE = "2026-10-30"
"""The last trading bar: the Friday before the frozen Saturday."""

AS_OF = "2026-10-30T20:00:00Z"
"""The quote time: after the last close (S9.2 ``as_of``, the S03 anchor)."""

DAYS = 60
"""S9.2: 60 trading days ending 2026-10-30."""

CLOSE_DIGITS = 2
"""The price precision; quotes and bars share it."""


def _trading_days() -> list[str]:
    """Return the 60 trading dates, oldest first.

    Returns:
        ISO dates, skipping Saturdays and Sundays, ending on ``LAST_TRADE``.
    """
    start = parse_instant(f"{LAST_TRADE}T00:00:00Z")
    dates: list[str] = []
    offset = 0
    while len(dates) < DAYS:
        day = start - timedelta(days=offset)
        if day.weekday() < 5:
            dates.append(day.strftime("%Y-%m-%d"))
        offset += 1
    dates.reverse()
    return dates


def _drift(ticker: str, index: int) -> float:
    """Draw one day's move of a ticker.

    Args:
        ticker: The ticker, part of the seed so draw order never matters.
        index: The trading-day index.

    Returns:
        A per-day fractional change in about ``[-1.2%, 1.2%]``.
    """
    return random.Random(f"{SEED}|{ticker}|close|{index}").uniform(-0.012, 0.012)


def build_bars(ticker: str, base: float, dates: list[str]) -> list[dict[str, object]]:
    """Build one ticker's 60 bars deterministically.

    Args:
        ticker: The ticker code.
        base: The ticker's budget anchor price.
        dates: The 60 trading dates, oldest first.

    Returns:
        One bar per date with ``date``, ``open``, ``high``, ``low``,
        ``close`` and ``volume``. ``close`` walks by :func:`_drift`; the
        open, high and low stay within a few percent of it.
    """
    bars: list[dict[str, object]] = []
    price = base
    for index, date in enumerate(dates):
        close = round(price * (1.0 + _drift(ticker, index)), CLOSE_DIGITS)
        open_price = round(close * (1.0 + _drift(ticker, index + 1000) * 0.35), CLOSE_DIGITS)
        spread = abs(_drift(ticker, index + 2000)) + 0.004
        high = round(max(open_price, close) * (1.0 + spread), CLOSE_DIGITS)
        low = round(min(open_price, close) * (1.0 - spread), CLOSE_DIGITS)
        volume = 100_000 + random.Random(f"{SEED}|{ticker}|volume|{index}").randrange(1_900_000)
        bars.append(
            {
                "date": date,
                "open": open_price,
                "high": high,
                "low": low,
                "close": close,
                "volume": volume,
            }
        )
        price = close
    return bars


def build_market() -> dict[str, dict[str, object]]:
    """Build the market table deterministically.

    Returns:
        ``{ticker: entry}`` where each entry has ``ticker``, ``name``,
        ``sector``, ``currency``, ``listed_at``, ``as_of``, ``price``,
        ``change_pct`` and ``bars`` (the S9.2 fields plus the profile's).
    """
    dates = _trading_days()
    market: dict[str, dict[str, object]] = {}
    for ticker in TICKERS:
        base, sector, name, listed = BASES[ticker]
        bars = build_bars(ticker, base, dates)
        last = float(str(bars[-1]["close"]))
        previous = float(str(bars[-2]["close"]))
        market[ticker] = {
            "ticker": ticker,
            "name": name,
            "sector": sector,
            "currency": "USD",
            "listed_at": f"{listed}T00:00:00Z",
            "as_of": AS_OF,
            "price": last,
            "change_pct": round((last - previous) / previous * 100.0, 2),
            "bars": bars,
        }
    return market


def write(path: Path = OUTPUT) -> None:
    """Write the market table to ``path``.

    Args:
        path: The destination file.
    """
    text = json.dumps(build_market(), ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    path.write_text(text, encoding="utf-8", newline="\n")


if __name__ == "__main__":
    write()
