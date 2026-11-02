"""The sb_weather tools (S9.2): four read-only forecast tools.

``get_forecast`` is the primary tool, ``get_forecast_v2`` its alternate with
the v2 field names, and ``get_forecast_consensus`` the third source for S09
(scenarios name these tools in ``alternates``). The forecast table is built
once from the committed ``data/forecasts.json``; the state dict holds it, so
the sandbox can still write a state file like every other sandbox
(S9.1 item 4).

``condition`` is one of ``clear``, ``partly cloudy``, ``cloudy``, ``rain`` or
``showers``; ``get_forecast_v2``'s ``summary`` is that as a sentence. The
dates are ISO ``YYYY-MM-DD``; the ``day`` argument of the v2 tool is a date
in the same form.
"""

import copy
from datetime import date as Date
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field

from skeptic_agent.sandboxes.sb_common.data import load_json
from skeptic_agent.sandboxes.sb_common.server import (
    SandboxTool,
    ToolFailure,
    ToolSpec,
    make_server,
    run_sandbox,
)
from skeptic_agent.sandboxes.sb_common.state import SandboxState

NAME = "sb_weather"
"""The server name (S9.1 item 2)."""

FORECASTS_FILE = Path(__file__).resolve().parent / "data" / "forecasts.json"
"""The committed forecast table the server reads (S9.1 item 3)."""

CITY_ORDER = (
    "Paris",
    "Lyon",
    "Berlin",
    "Munich",
    "Tokyo",
    "Osaka",
    "Beijing",
    "Shanghai",
    "Hangzhou",
    "New York",
    "Boston",
    "Sydney",
)
"""The 12 cities in S9.2 order."""

Condition = Literal["clear", "partly cloudy", "cloudy", "rain", "showers"]
"""The condition vocabulary of the table."""


class NoArguments(BaseModel):
    """No arguments; the S9.1 read tools still publish an object schema."""


class CityArguments(BaseModel):
    """The arguments of ``get_forecast`` and ``get_forecast_consensus``."""

    city: str = Field(description="The city name, for example 'Paris'.")
    date: str = Field(description="The forecast date, YYYY-MM-DD.")


class ForecastV2Arguments(BaseModel):
    """The arguments of the alternate tool, with the v2 field names."""

    location: str = Field(description="The location name, for example 'Paris'.")
    day: str = Field(description="The forecast day, YYYY-MM-DD.")


class Cities(BaseModel):
    """The cities the sandbox knows."""

    cities: list[str]


class Forecast(BaseModel):
    """One day's forecast (S9.2 ``forecast`` fields)."""

    city: str
    date: str
    max_c: float
    min_c: float
    condition: Condition
    unit: Literal["C"]
    issued_at: str


class ForecastV2(BaseModel):
    """One day's forecast under the v2 names (S9.2 ``v2`` fields)."""

    location: str
    day: str
    max_temp_c: float
    min_temp_c: float
    summary: str
    updated: str


class Consensus(BaseModel):
    """The consensus maximum of one day (S9.2 ``consensus`` fields)."""

    city: str
    date: str
    max_c: float
    sources: list[str]


def load_forecasts() -> dict[str, dict[str, dict[str, Any]]]:
    """Read the committed table as a fresh copy.

    Returns:
        ``{city: {date: entry}}``, in the generator's order.
    """
    table = load_json(FORECASTS_FILE)
    return copy.deepcopy(table)


def _table(tool: SandboxTool) -> dict[str, dict[str, dict[str, Any]]]:
    """Return the state's table, typed for the tools.

    Args:
        tool: The bound tool.

    Returns:
        The ``{city: {date: entry}}`` dict.
    """
    table: dict[str, dict[str, dict[str, Any]]] = tool.data["forecasts"]
    return table


def _day(value: str) -> str:
    """Validate a date argument and return it in ``YYYY-MM-DD``.

    Args:
        value: The client's date.

    Returns:
        The same date, normalised.

    Raises:
        ToolFailure: When the value is not an ISO date.
    """
    try:
        return Date.fromisoformat(value).isoformat()
    except ValueError:
        raise ToolFailure(f"invalid date {value!r}, expected YYYY-MM-DD") from None


def _entry(tool: SandboxTool, city: str, date: str) -> dict[str, Any]:
    """Look up one day of one city.

    Args:
        tool: The bound tool.
        city: The city name.
        date: The date in ``YYYY-MM-DD``.

    Returns:
        The day's entry.

    Raises:
        ToolFailure: On an unknown city or a date outside 2026-11-01 to
            2026-11-14.
    """
    table = _table(tool)
    if city not in table:
        raise ToolFailure(f"unknown city {city!r}; see list_cities")
    days = table[city]
    if date not in days:
        raise ToolFailure(f"no forecast for {city!r} on {date}")
    return days[date]


def _summary(condition: str) -> str:
    """Render a condition as the v2 ``summary``.

    Args:
        condition: One of the S9.2 conditions.

    Returns:
        The condition as a sentence, for example ``Partly cloudy``.
    """
    return condition[:1].upper() + condition[1:]


async def list_cities(arguments: NoArguments, tool: SandboxTool) -> Cities:
    """List the cities the sandbox has forecasts for.

    Args:
        arguments: The validated arguments, unused.
        tool: The bound tool.

    Returns:
        The cities in S9.2 order.
    """
    del arguments
    return Cities(cities=[city for city in CITY_ORDER if city in _table(tool)])


async def get_forecast(arguments: CityArguments, tool: SandboxTool) -> Forecast:
    """Return one city's forecast for one day.

    Args:
        arguments: The city and date.
        tool: The bound tool.

    Returns:
        The forecast.

    Raises:
        ToolFailure: On an invalid date, an unknown city or a day outside the
            table.
    """
    entry = _entry(tool, arguments.city, _day(arguments.date))
    return Forecast.model_validate(entry)


async def get_forecast_v2(arguments: ForecastV2Arguments, tool: SandboxTool) -> ForecastV2:
    """Return one location's forecast under the v2 names (the alternate tool).

    Args:
        arguments: The location and day.
        tool: The bound tool.

    Returns:
        The forecast with ``max_temp_c``, ``min_temp_c``, ``summary`` and
        ``updated``.

    Raises:
        ToolFailure: On an invalid day, an unknown location or a day outside
            the table.
    """
    entry = _entry(tool, arguments.location, _day(arguments.day))
    return ForecastV2(
        location=str(entry["city"]),
        day=str(entry["date"]),
        max_temp_c=float(entry["max_c"]),
        min_temp_c=float(entry["min_c"]),
        summary=_summary(str(entry["condition"])),
        updated=str(entry["issued_at"]),
    )


async def get_forecast_consensus(arguments: CityArguments, tool: SandboxTool) -> Consensus:
    """Return the two sources' consensus maximum (the S09 third source).

    The consensus is the mean of ``max_c`` and the second model's
    ``source_b``, rounded like every temperature. Days outside the first
    seven carry no second model, so their consensus is the single source.

    Args:
        arguments: The city and date.
        tool: The bound tool.

    Returns:
        The consensus maximum, with the names of the sources behind it.

    Raises:
        ToolFailure: On an invalid date, an unknown city or a day outside the
            table.
    """
    entry = _entry(tool, arguments.city, _day(arguments.date))
    primary = float(entry["max_c"])
    if "source_b" not in entry:
        return Consensus(
            city=str(entry["city"]),
            date=str(entry["date"]),
            max_c=primary,
            sources=["source_a"],
        )
    return Consensus(
        city=str(entry["city"]),
        date=str(entry["date"]),
        max_c=round((primary + float(entry["source_b"])) / 2, 1),
        sources=["source_a", "source_b"],
    )


TOOLS = (
    ToolSpec(
        "list_cities",
        "List the cities this weather service has forecasts for.",
        NoArguments,
        Cities,
        list_cities,
    ),
    ToolSpec(
        "get_forecast",
        "Return the forecast (max/min Celsius, condition) for a city and date.",
        CityArguments,
        Forecast,
        get_forecast,
    ),
    ToolSpec(
        "get_forecast_v2",
        "Return the forecast under the v2 field names for a location and day.",
        ForecastV2Arguments,
        ForecastV2,
        get_forecast_v2,
    ),
    ToolSpec(
        "get_forecast_consensus",
        "Return the consensus maximum of the two model sources for a city and date.",
        CityArguments,
        Consensus,
        get_forecast_consensus,
    ),
)
"""The four S9.2 read tools."""


def build_state() -> SandboxState:
    """Build the sandbox state from the committed table.

    Returns:
        A state whose ``forecasts`` key holds the table; the file comes from
        ``SKEPTIC_STATE_FILE`` (S9.1 item 4).
    """
    return SandboxState.from_env({"forecasts": load_forecasts()})


def server(state: SandboxState | None = None) -> Any:
    """Build the sb_weather server.

    Args:
        state: The state to serve; defaults to :func:`build_state`.

    Returns:
        The SDK server.
    """
    return make_server(NAME, TOOLS, state if state is not None else build_state())


def main() -> None:
    """Serve sb_weather (stdio, or ``--http HOST:PORT``)."""
    run_sandbox(NAME, TOOLS, build_state())


if __name__ == "__main__":
    main()
