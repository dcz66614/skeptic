"""Unit tests: the sb_orders and sb_calendar data (S9.1 items 3 and 9, S9.2, S33)."""

import itertools
import json
from datetime import datetime
from pathlib import Path

import pytest

from skeptic_agent.sandboxes.sb_calendar import server as calendar
from skeptic_agent.sandboxes.sb_calendar.data import generate as calendar_generate
from skeptic_agent.sandboxes.sb_common.data import load_customers
from skeptic_agent.sandboxes.sb_orders import server as orders
from skeptic_agent.sandboxes.sb_orders.data import generate as orders_generate

pytestmark = pytest.mark.unit


def test_orders_generator_is_deterministic() -> None:
    """Two calls with the fixed seed produce the same table."""
    assert orders_generate.build_orders() == orders_generate.build_orders()


def test_committed_orders_data_matches_the_generator() -> None:
    """The committed file is exactly what ``generate.write`` would produce."""
    committed = json.loads(orders.ORDERS_FILE.read_text(encoding="utf-8"))
    assert committed == orders_generate.build_orders()


def test_orders_shape_is_the_s9_2_shape() -> None:
    """120 orders O-2001 to O-2120 over all four statuses (S9.2)."""
    table = orders_generate.build_orders()
    assert list(table) == [f"O-{2001 + index}" for index in range(120)]
    assert len(table) == orders_generate.ORDER_COUNT
    assert {order["status"] for order in table.values()} == set(orders_generate.STATUSES)


def test_orders_field_order_puts_total_before_items() -> None:
    """The order's first numeric leaf is ``total`` (S6 S04)."""
    order = next(iter(orders_generate.build_orders().values()))
    assert list(order) == [
        "id",
        "customer_id",
        "status",
        "total",
        "currency",
        "items",
        "created_at",
    ]
    assert isinstance(order["total"], float)


def test_orders_items_and_totals_agree() -> None:
    """Each total is the sum of the item subtotals, in USD."""
    for order in orders_generate.build_orders().values():
        assert order["currency"] == "USD"
        items = order["items"]
        assert 1 <= len(items) <= 3
        for item in items:
            assert set(item) == {"product_id", "name", "quantity", "unit_price", "subtotal"}
            assert item["subtotal"] == round(item["quantity"] * item["unit_price"], 2)
        assert order["total"] == round(sum(item["subtotal"] for item in items), 2)


def test_orders_link_to_the_shared_customers() -> None:
    """Every order's customer id exists in the shared table (S9.1 item 9)."""
    ids = {str(customer["id"]) for customer in load_customers()}
    for order in orders_generate.build_orders().values():
        assert order["customer_id"] in ids


def test_calendar_generator_is_deterministic() -> None:
    """Two calls with the fixed seed produce the same events."""
    assert calendar_generate.build_events() == calendar_generate.build_events()


def test_committed_calendar_data_matches_the_generator() -> None:
    """The committed file is exactly what ``generate.write`` would produce."""
    committed = json.loads(calendar.EVENTS_FILE.read_text(encoding="utf-8"))
    assert committed == calendar_generate.build_events()


def test_calendar_shape_is_the_s9_2_shape() -> None:
    """60 events E-4001 upwards over the 14 days 2026-11-01 to 2026-11-14."""
    events = calendar_generate.build_events()
    assert len(events) == calendar_generate.EVENT_COUNT
    assert list(events) == [f"E-{4001 + index}" for index in range(60)]
    days = {str(event["start"])[:10] for event in events.values()}
    assert days == {f"2026-11-{day:02d}" for day in range(1, 15)}


def test_calendar_events_have_the_s9_2_fields_and_offset() -> None:
    """Every event has its six fields and ``+08:00`` start/end instants."""
    for event in calendar_generate.build_events().values():
        assert list(event) == ["id", "title", "start", "end", "attendees", "location"]
        assert event["start"].endswith("+08:00")
        assert event["end"].endswith("+08:00")
        assert datetime.fromisoformat(str(event["start"])) < datetime.fromisoformat(
            str(event["end"])
        )
        assert isinstance(event["attendees"], list)
        assert len(set(event["attendees"])) == len(event["attendees"])
        assert event["location"] in calendar_generate.LOCATIONS


def test_calendar_events_do_not_overlap_on_a_day() -> None:
    """Events are half-open windows and never overlap inside one day."""
    by_day: dict[str, list[tuple[str, str]]] = {}
    for event in calendar_generate.build_events().values():
        by_day.setdefault(str(event["start"])[:10], []).append(
            (str(event["start"]), str(event["end"]))
        )
    for windows in by_day.values():
        ordered = sorted(windows)
        for (_, first_end), (second_start, _) in itertools.pairwise(ordered):
            assert first_end <= second_start


def test_calendar_attendees_come_from_the_shared_customers() -> None:
    """Every attendee is a fictional name from the shared customer table."""
    names = {str(customer["name"]) for customer in load_customers()}
    attendees = {
        attendee
        for event in calendar_generate.build_events().values()
        for attendee in event["attendees"]
    }
    assert attendees <= names


def test_data_files_are_committed() -> None:
    """S9.1 item 3: the data is generated once and committed, not at run time."""
    assert isinstance(orders.ORDERS_FILE, Path)
    assert orders.ORDERS_FILE.is_file()
    assert calendar.EVENTS_FILE.is_file()
