"""Generate sb_orders' ``orders.json`` once with the fixed seed (20261101).

The output is committed; the server only reads it (S9.1 item 3). S9.2 fixes
the shape: 120 fictional orders O-2001 to O-2120, spread over the 40 shared
customers (S9.1 item 9) and the four statuses pending, shipped, delivered and
cancelled. Every value comes from one ``random.Random(SEED)`` draw in a fixed
order, so re-running this module rewrites the same bytes.

An order's field order is ``id, customer_id, status, total, currency, items,
created_at`` and each line's ``total`` is the sum of its item subtotals. The
first numeric leaf is therefore ``total`` (S6 S04), and ``currency`` is always
``USD`` (S9.2). Products, prices and people are fictional (S9.1 item 8).

Run from the repository root:

    uv run python -m skeptic_agent.sandboxes.sb_orders.data.generate
"""

import json
import random
from datetime import timedelta
from pathlib import Path

from skeptic_agent.sandboxes.sb_common.clock import format_iso, parse_instant
from skeptic_agent.sandboxes.sb_common.data import load_customers

SEED = 20261101
"""The fixed generator seed every sandbox shares (S9.1)."""

OUTPUT = Path(__file__).resolve().parent / "orders.json"
"""Where the committed table lives."""

ORDER_COUNT = 120
"""S9.2: O-2001 to O-2120."""

FIRST_ORDER = 2001
"""The first order number."""

STATUSES = ("pending", "shipped", "delivered", "cancelled")
"""The four order statuses (S9.2)."""

STATUS_PER_ORDER = ORDER_COUNT // len(STATUSES)
"""The balanced share each status gets; 120 is divisible by 4."""

CURRENCY = "USD"
"""Every order is priced in US dollars (S9.2)."""

PRODUCTS: tuple[tuple[str, str, float], ...] = (
    ("P-101", "Aurora Desk Lamp", 49.90),
    ("P-102", "Borealis Keyboard", 119.00),
    ("P-103", "Cascade Mug", 14.50),
    ("P-104", "Drift Notebook", 9.75),
    ("P-105", "Ember Headphones", 89.00),
    ("P-106", "Fjord Backpack", 74.25),
    ("P-107", "Glacier Bottle", 21.00),
    ("P-108", "Harbor Stand", 64.00),
    ("P-109", "Island Cable", 12.99),
    ("P-110", "Juniper Sleeve", 34.50),
    ("P-111", "Kestrel Mouse", 42.00),
    ("P-112", "Lumen Monitor", 249.00),
)
"""The fictional product catalogue: (product id, name, unit price)."""

_EPOCH = parse_instant("2026-07-01T00:00:00Z")
_CREATED_SPAN_S = 123 * 24 * 3600
"""Orders were placed over about four months before the frozen instant."""

_ITEM_LIMIT = 3
"""An order has one to three distinct lines."""


def _items(rng: random.Random) -> list[dict[str, object]]:
    """Build one order's line items.

    Args:
        rng: The shared generator.

    Returns:
        One to three items, each with ``product_id``, ``name``, ``quantity``,
        ``unit_price`` and ``subtotal``.
    """
    count = rng.randint(1, _ITEM_LIMIT)
    chosen = rng.sample(PRODUCTS, count)
    items: list[dict[str, object]] = []
    for product_id, name, price in chosen:
        quantity = rng.randint(1, 3)
        items.append(
            {
                "product_id": product_id,
                "name": name,
                "quantity": quantity,
                "unit_price": price,
                "subtotal": round(quantity * price, 2),
            }
        )
    return items


def build_orders() -> dict[str, dict[str, object]]:
    """Build the order table deterministically.

    Returns:
        ``{order_id: order}`` where each order has ``id``, ``customer_id``,
        ``status``, ``total``, ``currency``, ``items`` and ``created_at``, in
        O-2001..O-2120 order.
    """
    rng = random.Random(SEED)
    customers = load_customers()
    statuses = [status for status in STATUSES for _ in range(STATUS_PER_ORDER)]
    rng.shuffle(statuses)
    orders: dict[str, dict[str, object]] = {}
    for index in range(ORDER_COUNT):
        order_id = f"O-{FIRST_ORDER + index}"
        items = _items(rng)
        total = round(sum(float(str(item["subtotal"])) for item in items), 2)
        created = _EPOCH + timedelta(seconds=rng.randrange(_CREATED_SPAN_S))
        customer = customers[index % len(customers)]
        orders[order_id] = {
            "id": order_id,
            "customer_id": customer["id"],
            "status": statuses[index],
            "total": total,
            "currency": CURRENCY,
            "items": items,
            "created_at": format_iso(created),
        }
    return orders


def write(path: Path = OUTPUT) -> None:
    """Write the order table to ``path``.

    Args:
        path: The destination file.
    """
    text = json.dumps(build_orders(), ensure_ascii=False, indent=2) + "\n"
    path.write_text(text, encoding="utf-8", newline="\n")


if __name__ == "__main__":
    write()
