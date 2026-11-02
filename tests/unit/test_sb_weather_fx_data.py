"""Unit tests: the sb_weather and sb_fx data (S9.1 item 3, S9.2, S31)."""

import json
from pathlib import Path

import pytest

from skeptic_agent.sandboxes.sb_common import clock
from skeptic_agent.sandboxes.sb_fx import server as fx
from skeptic_agent.sandboxes.sb_fx.data import generate as fx_generate
from skeptic_agent.sandboxes.sb_weather import server as weather
from skeptic_agent.sandboxes.sb_weather.data import generate as weather_generate

pytestmark = pytest.mark.unit


def test_weather_generator_is_deterministic() -> None:
    """Two calls with the fixed seed produce the same table."""
    assert weather_generate.build_forecasts() == weather_generate.build_forecasts()


def test_committed_weather_data_matches_the_generator() -> None:
    """The committed file is exactly what ``generate.write`` would produce."""
    committed = json.loads(weather.FORECASTS_FILE.read_text(encoding="utf-8"))
    assert committed == weather_generate.build_forecasts()


def test_weather_shape_is_the_s9_2_shape() -> None:
    """12 cities over 14 days, 2026-11-01 to 2026-11-14 (S9.2)."""
    table = weather_generate.build_forecasts()
    assert list(table) == list(weather_generate.CITIES)
    assert len(table) == 12
    days = list(next(iter(table.values())))
    assert days[0] == "2026-11-01"
    assert days[-1] == "2026-11-14"
    assert all(len(city_days) == 14 for city_days in table.values())


def test_weather_entries_follow_the_forecast_fields() -> None:
    """Every entry has the S9.2 forecast fields and a sane temperature pair."""
    for city, days in weather_generate.build_forecasts().items():
        for day, entry in days.items():
            assert set(entry) >= {
                "city",
                "date",
                "max_c",
                "min_c",
                "condition",
                "unit",
                "issued_at",
            }
            assert entry["city"] == city
            assert entry["date"] == day
            assert entry["unit"] == "C"
            assert entry["condition"] in weather_generate.CONDITIONS
            assert float(entry["min_c"]) < float(entry["max_c"])
            assert str(entry["issued_at"]).endswith("T06:00:00Z")


def test_weather_sources_cover_the_first_seven_days_only() -> None:
    """The consensus needs two sources; both exist for 2026-11-01 to 11-07."""
    table = weather_generate.build_forecasts()
    first, last = table["Paris"], table["Paris"]
    assert "source_b" in first["2026-11-01"]
    assert "source_b" in last["2026-11-07"]
    assert "source_b" not in last["2026-11-08"]


def test_fx_generator_is_deterministic() -> None:
    """Two calls with the fixed seed produce the same table."""
    assert fx_generate.build_rates() == fx_generate.build_rates()


def test_committed_fx_data_matches_the_generator() -> None:
    """The committed file is exactly what ``generate.write`` would produce."""
    committed = json.loads(fx.RATES_FILE.read_text(encoding="utf-8"))
    assert committed == fx_generate.build_rates()


def test_fx_shape_is_the_s9_2_shape() -> None:
    """7 currencies over 14 days, 2026-10-19 to 2026-11-01 (S9.2)."""
    table = fx_generate.build_rates()
    assert list(table) == list(fx_generate.CURRENCIES)
    days = list(next(iter(table.values())))
    assert days[0] == "2026-10-19"
    assert days[-1] == "2026-11-01"
    assert all(len(currency_days) == 14 for currency_days in table.values())


def test_fx_usd_is_a_ones_column() -> None:
    """USD is the unit the table quotes against, so it is exactly ``1.0``."""
    rates = fx_generate.build_rates()
    assert set(rates["USD"].values()) == {1.0}


def test_fx_issued_matches_the_frozen_clock() -> None:
    """The quote time of the last day is the frozen day at 08:00 (S9.1 item 3)."""
    assert fx_generate.issued(13) == clock.format_iso(clock.parse_instant("2026-11-01T08:00:00Z"))


def test_weather_and_fx_data_files_are_committed() -> None:
    """S9.1 item 3: the data is generated once and committed, not at run time."""
    assert isinstance(weather.FORECASTS_FILE, Path)
    assert weather.FORECASTS_FILE.is_file()
    assert fx.RATES_FILE.is_file()
