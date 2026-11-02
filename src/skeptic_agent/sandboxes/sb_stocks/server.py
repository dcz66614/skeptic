"""The sb_stocks tools (S9.2): five read-only market tools.

``get_quote`` is the primary tool, ``get_quote_delayed`` its alternate with a
fixed 15-minute delay (``as_of`` 15 minutes earlier, so the two timestamps
differ), ``get_history`` returns the committed bars of a window,
``get_company_profile`` the fictional company behind a ticker, and ``screen``
filters the quotes by sector and price.

Field order matters for the S6 S04 ``numeric_corruption`` "first numeric
leaf". A quote's insertion order is ``ticker, price, currency, change_pct,
as_of``, so its first numeric leaf is ``price``. A history's is ``ticker``
then ``bars``, so its first numeric leaf is the first bar's ``open``; inside a
bar ``volume`` comes after the prices. S04 on a history therefore scales the
first day's prices, and the other days disagree, which is the detectable
signal. A profile's is ``ticker, name, sector,
currency, listed_at, employees, headquarters``; ``sector`` is a lowercase word
on purpose, so ``factor=10`` on a profile multiplies ``employees`` instead of
turning a sector into a number, and S05's decoy is a sector word.

The tickers, companies and every price are fictional (S9.1 item 8).
"""

import copy
from datetime import date as Date
from datetime import timedelta
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from skeptic_agent.sandboxes.sb_common.clock import format_iso, parse_instant
from skeptic_agent.sandboxes.sb_common.data import load_json
from skeptic_agent.sandboxes.sb_common.server import (
    SandboxTool,
    ToolFailure,
    ToolSpec,
    make_server,
    run_sandbox,
)
from skeptic_agent.sandboxes.sb_common.state import SandboxState

NAME = "sb_stocks"
"""The server name (S9.1 item 2)."""

MARKET_FILE = Path(__file__).resolve().parent / "data" / "market.json"
"""The committed market snapshot the server reads (S9.1 item 3)."""

TICKER_ORDER = ("ACME", "BOLT", "CRUX", "DYNA", "ECHO", "FLUX", "GRIT", "HELX")
"""The 8 fictional tickers in S9.2 order."""

LAST_BAR = "2026-10-30"
"""The newest trading bar; every window and the quote end here (S9.2)."""

DELAYED = timedelta(minutes=15)
"""``get_quote_delayed`` lags the primary by a fixed exchange delay."""

HEADQUARTERS: dict[str, str] = {
    "ACME": "Detroit, USA",
    "BOLT": "Oslo, Norway",
    "CRUX": "Cambridge, USA",
    "DYNA": "Rotterdam, Netherlands",
    "ECHO": "Austin, USA",
    "FLUX": "Hsinchu, Taiwan",
    "GRIT": "Sheffield, UK",
    "HELX": "Basel, Switzerland",
}
"""Each fictional company's (real) headquarters city; the companies are not."""

EMPLOYEES: dict[str, int] = {
    "ACME": 2400,
    "BOLT": 1350,
    "CRUX": 780,
    "DYNA": 3100,
    "ECHO": 410,
    "FLUX": 5200,
    "GRIT": 960,
    "HELX": 640,
}
"""Each fiction's head count; an integer leaf no identifier rule excludes."""

SECTORS = ("energy", "healthcare", "logistics", "manufacturing", "media", "technology")
"""The sector names ``screen`` accepts; they drive ``screen``'s error text."""


class TickerArguments(BaseModel):
    """The arguments of the single-ticker tools."""

    ticker: str = Field(description="The ticker, for example 'ACME'.")


class HistoryArguments(BaseModel):
    """The arguments of ``get_history``."""

    ticker: str = Field(description="The ticker, for example 'ACME'.")
    start: str = Field(description="The first bar's date, YYYY-MM-DD.")
    end: str = Field(description="The last bar's date, YYYY-MM-DD.")


class ScreenArguments(BaseModel):
    """The arguments of ``screen``."""

    sector: str = Field(description="The sector, for example 'technology'.")
    min_price: float = Field(description="The lowest price, inclusive.")
    max_price: float = Field(description="The highest price, inclusive.")


class Bar(BaseModel):
    """One trading day of one ticker (S9.2 ``bars`` elements).

    ``volume`` comes after the prices so the first numeric leaf of a history
    is a price (the bar's ``open``), per the S6 S04 note.
    """

    model_config = ConfigDict(extra="forbid")

    date: str
    open: float
    high: float
    low: float
    close: float
    volume: int


class Quote(BaseModel):
    """One ticker's latest quote (S9.2 ``quote`` fields, the S04 target)."""

    ticker: str
    price: float
    currency: Literal["USD"]
    change_pct: float
    as_of: str


class History(BaseModel):
    """A window of bars (S9.2 ``history`` fields)."""

    ticker: str
    bars: list[Bar]


class CompanyProfile(BaseModel):
    """One fictional company (S9.2 ``get_company_profile`` fields)."""

    ticker: str
    name: str
    sector: str
    currency: Literal["USD"]
    listed_at: str
    employees: int
    headquarters: str


class ScreenResult(BaseModel):
    """The quotes ``screen`` matched."""

    results: list[Quote]


def load_market() -> dict[str, dict[str, Any]]:
    """Read the committed market snapshot as a fresh copy.

    Returns:
        ``{ticker: entry}``, in the generator's order.
    """
    table: dict[str, dict[str, Any]] = load_json(MARKET_FILE)
    return copy.deepcopy(table)


def _table(tool: SandboxTool) -> dict[str, dict[str, Any]]:
    """Return the state's market table, typed for the tools.

    Args:
        tool: The bound tool.

    Returns:
        The ``{ticker: entry}`` dict.
    """
    table: dict[str, dict[str, Any]] = tool.data["market"]
    return table


def _entry(tool: SandboxTool, ticker: str) -> dict[str, Any]:
    """Look up one ticker.

    Args:
        tool: The bound tool.
        ticker: The client's ticker; case-insensitive.

    Returns:
        The ticker's entry.

    Raises:
        ToolFailure: When the ticker is not one of the 8.
    """
    code = ticker.strip().upper()
    table = _table(tool)
    if code not in table:
        raise ToolFailure(f"unknown ticker {ticker!r}")
    return table[code]


def _quote(entry: dict[str, Any]) -> Quote:
    """Build the S9.2 quote of one entry.

    Args:
        entry: The ticker's market entry.

    Returns:
        The quote, with ``price`` the last close.
    """
    return Quote(
        ticker=str(entry["ticker"]),
        price=float(entry["price"]),
        currency="USD",
        change_pct=float(entry["change_pct"]),
        as_of=str(entry["as_of"]),
    )


def _day(value: str, name: str) -> str:
    """Validate a date argument against the trading calendar.

    Args:
        value: The client's date.
        name: The argument name, for the error text.

    Returns:
        The date as ``YYYY-MM-DD``.

    Raises:
        ToolFailure: When the value is not an ISO date or is after the last
            trading bar.
    """
    try:
        day = Date.fromisoformat(value).isoformat()
    except ValueError:
        raise ToolFailure(f"invalid {name} {value!r}, expected YYYY-MM-DD") from None
    if day > LAST_BAR:
        raise ToolFailure(f"{name} {day} is after the last trading day {LAST_BAR}")
    return day


async def get_quote(arguments: TickerArguments, tool: SandboxTool) -> Quote:
    """Return the latest quote of a ticker.

    Args:
        arguments: The ticker.
        tool: The bound tool.

    Returns:
        The quote.

    Raises:
        ToolFailure: On an unknown ticker.
    """
    return _quote(_entry(tool, arguments.ticker))


async def get_quote_delayed(arguments: TickerArguments, tool: SandboxTool) -> Quote:
    """Return the delayed quote of a ticker (the alternate tool).

    The delayed view carries the same last close (the committed snapshot has
    no intraday walk) but its ``as_of`` lags the primary by the fixed
    exchange delay, so the timestamps differ.

    Args:
        arguments: The ticker.
        tool: The bound tool.

    Returns:
        The quote, with ``as_of`` 15 minutes earlier.

    Raises:
        ToolFailure: On an unknown ticker.
    """
    quote = _quote(_entry(tool, arguments.ticker))
    moment = parse_instant(quote.as_of) - DELAYED
    return quote.model_copy(update={"as_of": format_iso(moment)})


async def get_history(arguments: HistoryArguments, tool: SandboxTool) -> History:
    """Return the bars of a ticker between two dates.

    Args:
        arguments: The ticker and the inclusive window.
        tool: The bound tool.

    Returns:
        The bars in the window, oldest first.

    Raises:
        ToolFailure: On an unknown ticker, an invalid date, a future date, a
            reversed window or a window with no bar.
    """
    entry = _entry(tool, arguments.ticker)
    start = _day(arguments.start, "start")
    end = _day(arguments.end, "end")
    if start > end:
        raise ToolFailure(f"start {start} is after end {end}")
    bars = [Bar.model_validate(bar) for bar in entry["bars"] if start <= str(bar["date"]) <= end]
    if not bars:
        raise ToolFailure(f"no trading bars for {entry['ticker']!r} between {start} and {end}")
    return History(ticker=str(entry["ticker"]), bars=bars)


async def get_company_profile(arguments: TickerArguments, tool: SandboxTool) -> CompanyProfile:
    """Return the fictional company behind a ticker.

    Args:
        arguments: The ticker.
        tool: The bound tool.

    Returns:
        The company profile.

    Raises:
        ToolFailure: On an unknown ticker.
    """
    entry = _entry(tool, arguments.ticker)
    code = str(entry["ticker"])
    return CompanyProfile(
        ticker=code,
        name=str(entry["name"]),
        sector=str(entry["sector"]),
        currency="USD",
        listed_at=str(entry["listed_at"]),
        employees=EMPLOYEES[code],
        headquarters=HEADQUARTERS[code],
    )


async def screen(arguments: ScreenArguments, tool: SandboxTool) -> ScreenResult:
    """Return the quotes of a sector whose price is in a range.

    Args:
        arguments: The sector and the inclusive price range.
        tool: The bound tool.

    Returns:
        The matching quotes, in S9.2 ticker order. An empty list is a valid
        answer.

    Raises:
        ToolFailure: On an unknown sector or a range whose minimum exceeds
            its maximum.
    """
    sector = arguments.sector.strip().lower()
    if sector not in SECTORS:
        raise ToolFailure(f"unknown sector {arguments.sector!r}")
    if arguments.min_price > arguments.max_price:
        raise ToolFailure("min_price must not exceed max_price")
    table = _table(tool)
    return ScreenResult(
        results=[
            _quote(table[ticker])
            for ticker in TICKER_ORDER
            if sector == str(table[ticker]["sector"])
            and arguments.min_price <= float(table[ticker]["price"]) <= arguments.max_price
        ]
    )


TOOLS = (
    ToolSpec(
        "get_quote",
        "Return the latest price, change and timestamp of a ticker.",
        TickerArguments,
        Quote,
        get_quote,
    ),
    ToolSpec(
        "get_quote_delayed",
        "Return the exchange's delayed quote of a ticker (the alternate view).",
        TickerArguments,
        Quote,
        get_quote_delayed,
    ),
    ToolSpec(
        "get_history",
        "Return the daily OHLCV bars of a ticker between two dates, inclusive.",
        HistoryArguments,
        History,
        get_history,
    ),
    ToolSpec(
        "get_company_profile",
        "Return the company profile of a ticker (name, sector, head count).",
        TickerArguments,
        CompanyProfile,
        get_company_profile,
    ),
    ToolSpec(
        "screen",
        "Return the quotes of one sector whose price is inside a range.",
        ScreenArguments,
        ScreenResult,
        screen,
    ),
)
"""The five S9.2 read tools."""


def build_state() -> SandboxState:
    """Build the sandbox state from the committed snapshot.

    Returns:
        A state whose ``market`` key holds the table; the file comes from
        ``SKEPTIC_STATE_FILE`` (S9.1 item 4).
    """
    return SandboxState.from_env({"market": load_market()})


def server(state: SandboxState | None = None) -> Any:
    """Build the sb_stocks server.

    Args:
        state: The state to serve; defaults to :func:`build_state`.

    Returns:
        The SDK server.
    """
    return make_server(NAME, TOOLS, state if state is not None else build_state())


def main() -> None:
    """Serve sb_stocks (stdio, or ``--http HOST:PORT``)."""
    run_sandbox(NAME, TOOLS, build_state())


if __name__ == "__main__":
    main()
