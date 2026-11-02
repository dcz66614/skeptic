"""The sb_fx tools (S9.2): four read-only foreign-exchange tools.

``get_rate`` is the primary tool, ``get_rate_backup`` its alternate taking a
``"USD/CNY"`` pair, and ``convert`` applies a rate to an amount. The
committed table stores USD-per-unit for each of the 7 currencies; every pair
is derived from it, so the two rate tools cannot disagree.

``convert``'s ``currency`` is the quote currency, the unit of ``result``
(S9.2); that is the field S08 rewrites (a ``USD`` to ``EUR`` unit swap).
``amount`` may be negative (a refund) but not zero, and the amount must be
fine enough for the quote currency (no more than two decimals for USD, HKD
and CNY; whole units for JPY).
"""

import copy
from datetime import date as Date
from datetime import timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any, Literal

from mcp.server import MCPServer
from pydantic import BaseModel, ConfigDict, Field

from skeptic_agent.sandboxes.sb_common.clock import parse_instant
from skeptic_agent.sandboxes.sb_common.data import load_json
from skeptic_agent.sandboxes.sb_common.server import (
    SandboxTool,
    ToolFailure,
    ToolSpec,
    make_server,
    run_sandbox,
)
from skeptic_agent.sandboxes.sb_common.state import SandboxState

NAME = "sb_fx"
"""The server name (S9.1 item 2)."""

RATES_FILE = Path(__file__).resolve().parent / "data" / "rates.json"
"""The committed USD-per-unit table the server reads (S9.1 item 3)."""

START_DAY = parse_instant("2026-10-19T00:00:00Z")
"""The first rate day (S9.2)."""

DAYS = 14
"""S9.2: 14 days, 2026-10-19 to 2026-11-01."""

SMALLEST_DECIMALS: dict[str, int] = {"USD": 2, "EUR": 2, "CNY": 2, "HKD": 2, "SGD": 2, "JPY": 0}
"""The finest amount each quote currency has (JPY has no subunit in use)."""

CURRENCY_ORDER = ("USD", "EUR", "CNY", "JPY", "GBP", "HKD", "SGD")
"""The 7 currencies in S9.2 order."""

BACKUP_SPREAD = 0.002
"""The backup quote is 0.2% worse than the primary, so it stays a second view."""


class NoArguments(BaseModel):
    """No arguments; the S9.1 read tools still publish an object schema.

    An unexpected argument is rejected rather than silently ignored.
    """

    model_config = ConfigDict(extra="forbid")


class RateArguments(BaseModel):
    """The arguments of ``get_rate`` and ``convert``."""

    base: str = Field(description="The base currency code, for example 'USD'.")
    quote: str = Field(description="The quote currency code, for example 'CNY'.")
    date: str = Field(description="The rate date, YYYY-MM-DD.")


class ConvertArguments(RateArguments):
    """The arguments of ``convert``."""

    amount: float = Field(description="The amount in the base currency.")


class BackupArguments(BaseModel):
    """The arguments of the alternate tool, which takes one pair string."""

    pair: str = Field(description="The currency pair, for example 'USD/CNY'.")
    date: str = Field(description="The rate date, YYYY-MM-DD.")


class Currencies(BaseModel):
    """The currencies the sandbox quotes."""

    currencies: list[str]


class Rate(BaseModel):
    """One currency pair on one day (S9.2 ``rate`` fields)."""

    base: str
    quote: str
    date: str
    rate: float
    unit: Literal["quote_per_base"]
    source: str


class Conversion(BaseModel):
    """One conversion (S9.2 ``convert`` fields)."""

    amount: float
    base: str
    quote: str
    date: str
    rate: float
    result: float
    currency: str


def load_rates() -> dict[str, dict[str, float]]:
    """Read the committed table as a fresh copy.

    Returns:
        ``{currency: {date: usd_per_unit}}``.
    """
    loaded: Any = load_json(RATES_FILE)
    table: dict[str, dict[str, float]] = loaded
    return copy.deepcopy(table)


def _table(tool: SandboxTool) -> dict[str, dict[str, float]]:
    """Return the state's rate table, typed for the tools.

    Args:
        tool: The bound tool.

    Returns:
        The ``{currency: {date: usd_per_unit}}`` dict.
    """
    table: dict[str, dict[str, float]] = tool.data["rates"]
    return table


def _date(value: str) -> str:
    """Validate a date argument against the S9.2 window.

    Args:
        value: The client's date.

    Returns:
        The date as ``YYYY-MM-DD``, which is also the table key.

    Raises:
        ToolFailure: When the value is not an ISO date or is outside
            2026-10-19 to 2026-11-01.
    """
    try:
        day = Date.fromisoformat(value).isoformat()
    except ValueError:
        raise ToolFailure(f"invalid date {value!r}, expected YYYY-MM-DD") from None
    start = START_DAY.date().isoformat()
    end = (START_DAY.date() + timedelta(days=DAYS - 1)).isoformat()
    if not start <= day <= end:
        raise ToolFailure(f"no rates on {day}; the table covers {start} to {end}")
    return day


def _check_currency(tool: SandboxTool, code: str) -> str:
    """Validate a currency code.

    Args:
        tool: The bound tool.
        code: The client's code.

    Returns:
        The code, upper-cased.

    Raises:
        ToolFailure: When the code is not one of the 7 currencies.
    """
    upper = code.strip().upper()
    if upper not in _table(tool):
        raise ToolFailure(f"unknown currency {code!r}; see list_currencies")
    return upper


def _check_amount(amount: float, currency: str) -> float:
    """Validate an amount against the quote currency's granularity.

    Args:
        amount: The client's amount; a negative amount is a refund.
        currency: The quote currency.

    Returns:
        The amount as a float.

    Raises:
        ToolFailure: When the amount is zero or has finer decimals than the
            currency allows.
    """
    if amount == 0:
        raise ToolFailure("amount must not be zero")
    decimals = SMALLEST_DECIMALS[currency]
    if Decimal(str(amount)).quantize(Decimal(1).scaleb(-decimals)) != Decimal(str(amount)):
        raise ToolFailure(f"amount {amount!r} has finer than {decimals} decimals for {currency}")
    return amount


def _quote_per_base(
    table: dict[str, dict[str, float]],
    base: str,
    quote: str,
    day: str,
    rounded: bool = True,
) -> float:
    """Derive the quote-per-base rate from the USD-per-unit table.

    The table stores the USD value of one unit of each currency, so one
    ``base`` is worth ``table[base]`` dollars and one ``quote``
    ``table[quote]`` dollars. A unit of ``base`` therefore buys
    ``table[base] / table[quote]`` units of ``quote``.

    Args:
        table: The ``{currency: {date: usd_per_unit}}`` dict.
        base: The base currency.
        quote: The quote currency.
        day: The rate date, which is also the table key.
        rounded: Whether to round to six decimals (the backup applies its
            spread to the unrounded value).

    Returns:
        The quote units per one base unit.
    """
    rate = table[base][day] / table[quote][day]
    return round(rate, 6) if rounded else rate


async def list_currencies(arguments: NoArguments, tool: SandboxTool) -> Currencies:
    """List the currencies the sandbox quotes against USD.

    Args:
        arguments: The validated arguments, unused.
        tool: The bound tool.

    Returns:
        The codes in S9.2 order.
    """
    del arguments
    return Currencies(currencies=[code for code in CURRENCY_ORDER if code in _table(tool)])


async def get_rate(arguments: RateArguments, tool: SandboxTool) -> Rate:
    """Return the primary quote of a pair on one day.

    Args:
        arguments: The base, quote and date.
        tool: The bound tool.

    Returns:
        The quote-per-base rate.

    Raises:
        ToolFailure: On an invalid date or an unknown currency.
    """
    day = _date(arguments.date)
    base = _check_currency(tool, arguments.base)
    quote = _check_currency(tool, arguments.quote)
    table = _table(tool)
    return Rate(
        base=base,
        quote=quote,
        date=day,
        rate=_quote_per_base(table, base, quote, day),
        unit="quote_per_base",
        source="primary",
    )


async def get_rate_backup(arguments: BackupArguments, tool: SandboxTool) -> Rate:
    """Return the backup quote of a pair on one day (the alternate tool).

    The backup quotes 0.2% worse than the primary for the same pair, so it is
    a second, distinct view rather than a copy.

    Args:
        arguments: The ``BASE/QUOTE`` pair and the date.
        tool: The bound tool.

    Returns:
        The backup quote-per-base rate, with ``source: "backup"``.

    Raises:
        ToolFailure: On an invalid date, a malformed pair or an unknown
            currency.
    """
    day = _date(arguments.date)
    base, separator, quote = arguments.pair.partition("/")
    if not separator or not base or not quote:
        raise ToolFailure(f"invalid pair {arguments.pair!r}, expected BASE/QUOTE")
    base_code = _check_currency(tool, base)
    quote_code = _check_currency(tool, quote)
    table = _table(tool)
    primary = _quote_per_base(table, base_code, quote_code, day, rounded=False)
    return Rate(
        base=base_code,
        quote=quote_code,
        date=day,
        rate=round(primary * (1.0 - BACKUP_SPREAD), 6),
        unit="quote_per_base",
        source="backup",
    )


async def convert(arguments: ConvertArguments, tool: SandboxTool) -> Conversion:
    """Convert an amount from the base currency to the quote currency.

    Args:
        arguments: The amount, base, quote and date.
        tool: The bound tool.

    Returns:
        The amount, the applied rate, the result and its ``currency`` (the
        quote code).

    Raises:
        ToolFailure: On an invalid date, an unknown currency or an amount that
            is zero or too fine for the quote currency.
    """
    day = _date(arguments.date)
    base = _check_currency(tool, arguments.base)
    quote = _check_currency(tool, arguments.quote)
    amount = _check_amount(arguments.amount, quote)
    table = _table(tool)
    rate = _quote_per_base(table, base, quote, day)
    return Conversion(
        amount=amount,
        base=base,
        quote=quote,
        date=day,
        rate=rate,
        result=float(Decimal(str(amount)) * Decimal(str(rate))),
        currency=quote,
    )


TOOLS = (
    ToolSpec(
        "list_currencies",
        "List the currency codes this service quotes.",
        NoArguments,
        Currencies,
        list_currencies,
    ),
    ToolSpec(
        "get_rate",
        "Return the quote-per-base rate of a pair on a date.",
        RateArguments,
        Rate,
        get_rate,
    ),
    ToolSpec(
        "get_rate_backup",
        "Return the backup quote of a 'BASE/QUOTE' pair on a date.",
        BackupArguments,
        Rate,
        get_rate_backup,
    ),
    ToolSpec(
        "convert",
        "Convert an amount from the base currency to the quote currency.",
        ConvertArguments,
        Conversion,
        convert,
    ),
)
"""The four S9.2 read tools."""


def build_state() -> SandboxState:
    """Build the sandbox state from the committed table.

    Returns:
        A state whose ``rates`` key holds the table; the file comes from
        ``SKEPTIC_STATE_FILE`` (S9.1 item 4).
    """
    return SandboxState.from_env({"rates": load_rates()})


def server(state: SandboxState | None = None) -> MCPServer[Any]:
    """Build the sb_fx server.

    Args:
        state: The state to serve; defaults to :func:`build_state`.

    Returns:
        The SDK server.
    """
    return make_server(NAME, TOOLS, state if state is not None else build_state())


def main() -> None:
    """Serve sb_fx (stdio, or ``--http HOST:PORT``)."""
    run_sandbox(NAME, TOOLS, build_state())


if __name__ == "__main__":
    main()
