"""Generate sb_sqlshop's ``shop.sql`` once with the fixed seed (20261101).

The output is committed; the server only reads it (S9.1 item 3). S9.2 fixes
the tables and row counts: 40 products, 40 customers, 120 orders and 300
order items in one SQLite database. The customers are the shared
``sb_common/data/customers.json`` ones (C-1001 to C-1040), so the ids agree
with sb_crm, sb_orders and sb_mail (S9.1 item 9). Products and orders are
fictional.

Every value comes from one ``random.Random(SEED)`` draw in a fixed order, so
re-running this module rewrites the same bytes.

Run from the repository root:

    uv run python -m skeptic_agent.sandboxes.sb_sqlshop.data.generate
"""

import random
from datetime import timedelta
from pathlib import Path

from skeptic_agent.sandboxes.sb_common.clock import format_iso, parse_instant
from skeptic_agent.sandboxes.sb_common.data import load_customers

SEED = 20261101
"""The fixed generator seed every sandbox shares (S9.1)."""

OUTPUT = Path(__file__).resolve().parent / "shop.sql"
"""Where the committed database script lives."""

PRODUCT_COUNT = 40
"""S9.2: products has 40 rows."""

CUSTOMER_COUNT = 40
"""S9.2: customers has 40 rows, shared with the other sandboxes."""

ORDER_COUNT = 120
"""S9.2: orders has 120 rows."""

ORDER_ITEM_COUNT = 300
"""S9.2: order_items has 300 rows."""

CURRENCY = "USD"
"""Every price is in US dollars."""

STATUSES = ("pending", "shipped", "delivered", "cancelled")
"""The order statuses; 120 is divisible by 4."""

STATUS_PER_ORDER = ORDER_COUNT // len(STATUSES)
"""The balanced share each status gets."""

FIRST_PRODUCT = 1001
"""Product ids run P-1001 upwards."""

FIRST_ORDER = 3001
"""Order ids run O-3001 upwards."""

FIRST_ITEM = 5001
"""Order item ids run OI-5001 upwards."""

PRODUCT_PREFIXES = (
    "Atlas",
    "Borealis",
    "Cascade",
    "Drift",
    "Ember",
    "Fjord",
    "Glacier",
    "Harbor",
    "Island",
    "Juniper",
)
"""The fictional product family names."""

PRODUCT_KINDS = (
    "Arm",
    "Sensor",
    "Controller",
    "Battery",
    "Gripper",
    "Dock",
    "Cable",
    "Module",
)
"""The fictional product kinds, which double as categories."""

PRODUCT_VARIANTS = ("X1", "S2", "M4", "L7", "C3", "D5", "R8", "T6")
"""The fictional product revisions."""

_EPOCH = parse_instant("2026-07-01T00:00:00Z")
"""The earliest order timestamp."""

_ORDER_SPAN_DAYS = 123
"""Orders were placed over about four months before the frozen instant."""


def _quote(value: object) -> str:
    """Render a value as an SQL string literal.

    Args:
        value: The value to quote.

    Returns:
        The single-quoted literal with embedded quotes doubled.
    """
    return "'" + str(value).replace("'", "''") + "'"


def _products(rng: random.Random) -> list[dict[str, object]]:
    """Build the product table.

    Args:
        rng: The shared generator.

    Returns:
        One dict per product with ``product_id``, ``name``, ``category``,
        ``price`` and ``stock``.
    """
    products: list[dict[str, object]] = []
    for index in range(PRODUCT_COUNT):
        prefix = PRODUCT_PREFIXES[index % len(PRODUCT_PREFIXES)]
        kind = PRODUCT_KINDS[(index // len(PRODUCT_PREFIXES)) % len(PRODUCT_KINDS)]
        variant = PRODUCT_VARIANTS[index % len(PRODUCT_VARIANTS)]
        products.append(
            {
                "product_id": f"P-{FIRST_PRODUCT + index}",
                "name": f"{prefix} {kind} {variant}",
                "category": kind.lower(),
                "price": round(rng.uniform(12.0, 900.0), 2),
                "stock": rng.randrange(0, 401),
            }
        )
    return products


def _order_items(
    rng: random.Random,
    order: dict[str, object],
    products: list[dict[str, object]],
    serial: int,
    count: int,
) -> list[dict[str, object]]:
    """Build the item lines of one order.

    Args:
        rng: The shared generator.
        order: The order the lines belong to.
        products: The product table.
        serial: The first order-item number.
        count: How many lines this order has.

    Returns:
        One dict per line with ``order_item_id``, ``order_id``,
        ``product_id``, ``quantity`` and ``unit_price``.
    """
    items: list[dict[str, object]] = []
    for offset, product in enumerate(rng.sample(products, count)):
        items.append(
            {
                "order_item_id": f"OI-{serial + offset}",
                "order_id": order["order_id"],
                "product_id": product["product_id"],
                "quantity": rng.randint(1, 4),
                "unit_price": product["price"],
            }
        )
    return items


def build_tables() -> dict[str, list[dict[str, object]]]:
    """Build every table deterministically.

    Returns:
        ``{table: rows}`` for ``products``, ``customers``, ``orders`` and
        ``order_items``.
    """
    rng = random.Random(SEED)
    products = _products(rng)
    customers = [
        {
            "customer_id": customer["id"],
            "name": customer["name"],
            "email": customer["email"],
            "city": customer["city"],
            "tier": customer["tier"],
        }
        for customer in load_customers()
    ]
    statuses = [status for status in STATUSES for _ in range(STATUS_PER_ORDER)]
    rng.shuffle(statuses)
    orders: list[dict[str, object]] = []
    order_items: list[dict[str, object]] = []
    serial = FIRST_ITEM
    for index in range(ORDER_COUNT):
        order = {
            "order_id": f"O-{FIRST_ORDER + index}",
            "customer_id": customers[index % len(customers)]["customer_id"],
            "status": statuses[index],
            "total": 0.0,
            "created_at": "",
        }
        lines = 2 if index < ORDER_COUNT // 2 else 3
        items = _order_items(rng, order, products, serial, lines)
        serial += lines
        order["total"] = round(
            sum(int(str(item["quantity"])) * float(str(item["unit_price"])) for item in items),
            2,
        )
        created = _EPOCH + timedelta(seconds=rng.randrange(_ORDER_SPAN_DAYS * 24 * 3600))
        order["created_at"] = format_iso(created)
        orders.append(order)
        order_items.extend(items)
    return {
        "products": products,
        "customers": customers,
        "orders": orders,
        "order_items": order_items,
    }


def _insert(table: str, columns: tuple[str, ...], rows: list[dict[str, object]]) -> list[str]:
    """Render the INSERT statements of one table.

    Args:
        table: The table name.
        columns: The column names, in table order.
        rows: The rows to insert.

    Returns:
        One statement per row.
    """
    names = ", ".join(columns)
    statements: list[str] = []
    for row in rows:
        values = ", ".join(
            _quote(row[column]) if isinstance(row[column], str) else str(row[column])
            for column in columns
        )
        statements.append(f"INSERT INTO {table} ({names}) VALUES ({values});")
    return statements


def build_sql() -> str:
    """Render the whole database script.

    Returns:
        The CREATE TABLE and INSERT statements, newline-terminated.
    """
    tables = build_tables()
    lines = [
        "-- Generated by skeptic_agent.sandboxes.sb_sqlshop.data.generate.",
        f"-- Seed {SEED}; fictional data, do not edit by hand.",
        "",
        "CREATE TABLE products (",
        "  product_id TEXT PRIMARY KEY,",
        "  name TEXT NOT NULL,",
        "  category TEXT NOT NULL,",
        "  price REAL NOT NULL,",
        "  stock INTEGER NOT NULL",
        ");",
        "",
        "CREATE TABLE customers (",
        "  customer_id TEXT PRIMARY KEY,",
        "  name TEXT NOT NULL,",
        "  email TEXT NOT NULL,",
        "  city TEXT NOT NULL,",
        "  tier TEXT NOT NULL",
        ");",
        "",
        "CREATE TABLE orders (",
        "  order_id TEXT PRIMARY KEY,",
        "  customer_id TEXT NOT NULL,",
        "  status TEXT NOT NULL,",
        "  total REAL NOT NULL,",
        "  created_at TEXT NOT NULL,",
        "  FOREIGN KEY (customer_id) REFERENCES customers (customer_id)",
        ");",
        "",
        "CREATE TABLE order_items (",
        "  order_item_id TEXT PRIMARY KEY,",
        "  order_id TEXT NOT NULL,",
        "  product_id TEXT NOT NULL,",
        "  quantity INTEGER NOT NULL,",
        "  unit_price REAL NOT NULL,",
        "  FOREIGN KEY (order_id) REFERENCES orders (order_id),",
        "  FOREIGN KEY (product_id) REFERENCES products (product_id)",
        ");",
        "",
    ]
    lines.extend(
        _insert(
            "products",
            ("product_id", "name", "category", "price", "stock"),
            tables["products"],
        )
    )
    lines.append("")
    lines.extend(
        _insert(
            "customers",
            ("customer_id", "name", "email", "city", "tier"),
            tables["customers"],
        )
    )
    lines.append("")
    lines.extend(
        _insert(
            "orders",
            ("order_id", "customer_id", "status", "total", "created_at"),
            tables["orders"],
        )
    )
    lines.append("")
    lines.extend(
        _insert(
            "order_items",
            ("order_item_id", "order_id", "product_id", "quantity", "unit_price"),
            tables["order_items"],
        )
    )
    return "\n".join(lines) + "\n"


def write(path: Path = OUTPUT) -> None:
    """Write the database script to ``path``.

    Args:
        path: The destination file.
    """
    path.write_text(build_sql(), encoding="utf-8", newline="\n")


if __name__ == "__main__":
    write()
