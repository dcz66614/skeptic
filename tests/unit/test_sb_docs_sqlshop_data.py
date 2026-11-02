"""Unit tests: the sb_docs and sb_sqlshop data (S9.1 item 3, S9.2, S34)."""

import json
import re
import sqlite3
from pathlib import Path

import pytest

from skeptic_agent.sandboxes.sb_common.data import load_customers
from skeptic_agent.sandboxes.sb_docs import server as docs
from skeptic_agent.sandboxes.sb_docs.data import generate as docs_generate
from skeptic_agent.sandboxes.sb_sqlshop import server as sqlshop
from skeptic_agent.sandboxes.sb_sqlshop.data import generate as sqlshop_generate

pytestmark = pytest.mark.unit

INSTANT = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")


def _database() -> sqlite3.Connection:
    """Build the committed shop database in memory.

    Returns:
        A connection holding the S9.2 tables.
    """
    connection = sqlite3.connect(":memory:")
    connection.executescript(sqlshop.load_script())
    return connection


def _is_chinese(text: str) -> bool:
    """Tell whether a text contains a CJK character.

    Args:
        text: The text to inspect.

    Returns:
        ``True`` when at least one character is in the CJK range.
    """
    return any("\u4e00" <= character <= "\u9fff" for character in text)


def test_docs_generator_is_deterministic() -> None:
    """Two calls with the fixed seed produce the same records."""
    assert docs_generate.build_documents() == docs_generate.build_documents()


def test_committed_docs_data_matches_the_generator() -> None:
    """The committed file is exactly what the generator produces."""
    committed = json.loads(docs.DOCS_FILE.read_text(encoding="utf-8"))
    assert committed == docs_generate.build_documents()


def test_docs_shape_is_the_s9_2_shape() -> None:
    """30 documents KB-001 to KB-030, each with versions 1 and 2 (S9.2)."""
    records = docs_generate.build_documents()
    assert len(records) == docs_generate.DOC_COUNT * 2
    assert [record["doc_id"] for record in records] == [
        doc_id for index in range(1, 31) for doc_id in (f"KB-{index:03d}", f"KB-{index:03d}")
    ]
    for index in range(0, len(records), 2):
        assert [record["version"] for record in records[index : index + 2]] == [1, 2]


def test_docs_records_have_the_s9_2_fields() -> None:
    """Every record has the five fields in S9.2 order and a UTC timestamp."""
    for record in docs_generate.build_documents():
        assert list(record) == ["doc_id", "title", "body", "updated_at", "version"]
        assert INSTANT.match(str(record["updated_at"]))
        assert str(record["body"]).strip()


def test_docs_are_half_english_and_half_chinese() -> None:
    """The 30 current documents split 15/15 between the two languages."""
    current = docs_generate.build_documents()[1::2]
    assert len(current) == 30
    chinese = [record for record in current if _is_chinese(str(record["title"]))]
    assert len(chinese) == 15
    assert len(current) - len(chinese) == 15


def test_docs_archive_differs_from_the_current_version() -> None:
    """Each archived body is an older text and is stamped earlier."""
    records = docs_generate.build_documents()
    for archived, current in zip(records[::2], records[1::2], strict=True):
        assert archived["body"] != current["body"]
        assert str(archived["updated_at"]) < str(current["updated_at"])


def test_data_files_are_committed() -> None:
    """S9.1 item 3: both generators' outputs are committed."""
    assert isinstance(docs.DOCS_FILE, Path)
    assert docs.DOCS_FILE.is_file()
    assert isinstance(sqlshop.SHOP_SQL, Path)
    assert sqlshop.SHOP_SQL.is_file()


def test_shop_generator_is_deterministic() -> None:
    """Two calls with the fixed seed produce the same script."""
    assert sqlshop_generate.build_sql() == sqlshop_generate.build_sql()


def test_committed_shop_data_matches_the_generator() -> None:
    """The committed script is exactly what the generator produces."""
    assert sqlshop.load_script() == sqlshop_generate.build_sql()


def test_shop_tables_have_the_s9_2_row_counts() -> None:
    """40 products, 40 customers, 120 orders and 300 order items (S9.2)."""
    connection = _database()
    try:
        counts = {
            table: connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            for table in sqlshop.TABLES
        }
    finally:
        connection.close()
    assert counts == {"products": 40, "customers": 40, "orders": 120, "order_items": 300}


def test_shop_customers_are_the_shared_ones() -> None:
    """The customer table uses the shared C-1001..C-1040 ids (S9.1 item 9)."""
    wanted = {str(customer["id"]) for customer in load_customers()}
    connection = _database()
    try:
        found = {
            row[0] for row in connection.execute("SELECT customer_id FROM customers").fetchall()
        }
    finally:
        connection.close()
    assert found == wanted


def test_shop_order_statuses_are_balanced() -> None:
    """All four S9.2 statuses appear 30 times each."""
    connection = _database()
    try:
        counts = dict(
            connection.execute("SELECT status, COUNT(*) FROM orders GROUP BY status").fetchall()
        )
    finally:
        connection.close()
    assert counts == {"pending": 30, "shipped": 30, "delivered": 30, "cancelled": 30}


def test_shop_totals_are_the_sum_of_their_items() -> None:
    """Every order total equals the sum of its line items."""
    connection = _database()
    try:
        mismatches = connection.execute(
            "SELECT o.order_id FROM orders o "
            "JOIN (SELECT order_id, SUM(quantity * unit_price) AS computed "
            "      FROM order_items GROUP BY order_id) i "
            "ON o.order_id = i.order_id "
            "WHERE ROUND(o.total, 2) != ROUND(i.computed, 2)"
        ).fetchall()
        item_count = connection.execute("SELECT COUNT(*) FROM order_items").fetchone()[0]
    finally:
        connection.close()
    assert mismatches == []
    assert item_count == sqlshop_generate.ORDER_ITEM_COUNT


def test_shop_items_reference_existing_rows() -> None:
    """Every order item points at a committed order and product."""
    connection = _database()
    try:
        missing = connection.execute(
            "SELECT oi.order_item_id FROM order_items oi "
            "LEFT JOIN orders o ON oi.order_id = o.order_id "
            "LEFT JOIN products p ON oi.product_id = p.product_id "
            "WHERE o.order_id IS NULL OR p.product_id IS NULL"
        ).fetchall()
        orders = {row[0] for row in connection.execute("SELECT order_id FROM orders")}
    finally:
        connection.close()
    assert missing == []
    assert orders == {f"O-{3001 + index}" for index in range(120)}
