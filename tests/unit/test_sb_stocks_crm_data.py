"""Unit tests: the sb_stocks and sb_crm data (S9.1 items 3 and 9, S9.2, S32)."""

import json
from pathlib import Path

import pytest

from skeptic_agent.sandboxes.sb_common.data import load_customers
from skeptic_agent.sandboxes.sb_crm import server as crm
from skeptic_agent.sandboxes.sb_crm.data import generate as crm_generate
from skeptic_agent.sandboxes.sb_stocks import server as stocks
from skeptic_agent.sandboxes.sb_stocks.data import generate as stocks_generate

pytestmark = pytest.mark.unit


def test_stocks_generator_is_deterministic() -> None:
    """Two calls with the fixed seed produce the same table."""
    assert stocks_generate.build_market() == stocks_generate.build_market()


def test_committed_stocks_data_matches_the_generator() -> None:
    """The committed file is exactly what ``generate.write`` would produce."""
    committed = json.loads(stocks.MARKET_FILE.read_text(encoding="utf-8"))
    assert committed == stocks_generate.build_market()


def test_stocks_shape_is_the_s9_2_shape() -> None:
    """8 fictional tickers over 60 trading days ending 2026-10-30 (S9.2)."""
    table = stocks_generate.build_market()
    assert list(table) == list(stocks_generate.TICKERS)
    assert len(table) == 8
    bars = table["ACME"]["bars"]
    assert len(bars) == 60
    assert bars[0]["date"] == "2026-08-10"
    assert bars[-1]["date"] == "2026-10-30"


def test_stocks_bars_skip_weekends() -> None:
    """Trading days are weekdays only."""
    bars = stocks_generate.build_market()["BOLT"]["bars"]
    weekend = [bar["date"] for bar in bars if bar["date"] in {"2026-08-15", "2026-08-16"}]
    assert weekend == []


def test_stocks_bars_are_well_formed() -> None:
    """Every bar has its six fields and ``low <= open, close <= high``."""
    for entry in stocks_generate.build_market().values():
        for bar in entry["bars"]:
            assert set(bar) == {"date", "open", "high", "low", "close", "volume"}
            assert bar["low"] <= bar["open"] <= bar["high"]
            assert bar["low"] <= bar["close"] <= bar["high"]
            assert bar["volume"] > 0


def test_stocks_quote_matches_the_last_bar() -> None:
    """Each quote price is the last close, and ``change_pct`` is set."""
    for entry in stocks_generate.build_market().values():
        assert entry["price"] == entry["bars"][-1]["close"]
        assert entry["currency"] == "USD"
        assert entry["as_of"] == stocks_generate.AS_OF
        assert isinstance(entry["change_pct"], float)


def test_stocks_sectors_are_lowercase_words() -> None:
    """S9.2/S04: a sector is a plain word, not a number or an acronym."""
    sectors = {entry["sector"] for entry in stocks_generate.build_market().values()}
    assert sectors <= set(stocks.SECTORS)
    assert all(sector.isalpha() and sector.islower() for sector in sectors)


def test_stocks_profiles_cover_every_ticker() -> None:
    """Every ticker has a fictional company with an integer head count."""
    for ticker in stocks_generate.TICKERS:
        assert ticker in stocks.EMPLOYEES
        assert ticker in stocks.HEADQUARTERS


def test_crm_generator_is_deterministic() -> None:
    """Two calls with the fixed seed produce the same notes."""
    assert crm_generate.build_notes() == crm_generate.build_notes()


def test_committed_crm_data_matches_the_generator() -> None:
    """The committed notes are exactly what ``generate.write`` would produce."""
    committed = json.loads(crm.NOTES_FILE.read_text(encoding="utf-8"))
    assert committed == crm_generate.build_notes()


def test_crm_shape_is_the_s9_2_shape() -> None:
    """40 shared customers, 80 notes, two per customer (S9.2)."""
    notes = crm_generate.build_notes()
    assert len(load_customers()) == 40
    assert len(notes) == 80
    per_customer: dict[str, int] = {}
    for note in notes:
        per_customer[str(note["customer_id"])] = per_customer.get(str(note["customer_id"]), 0) + 1
    assert set(per_customer.values()) == {2}
    assert len(per_customer) == 40


def test_crm_notes_link_to_the_shared_customers() -> None:
    """Every note's customer id exists in the shared table (S9.1 item 9)."""
    ids = {str(customer["id"]) for customer in load_customers()}
    for note in crm_generate.build_notes():
        assert note["customer_id"] in ids
        assert set(note) == {"id", "customer_id", "text", "created_at"}


def test_data_files_are_committed() -> None:
    """S9.1 item 3: the data is generated once and committed, not at run time."""
    assert isinstance(stocks.MARKET_FILE, Path)
    assert stocks.MARKET_FILE.is_file()
    assert crm.NOTES_FILE.is_file()
