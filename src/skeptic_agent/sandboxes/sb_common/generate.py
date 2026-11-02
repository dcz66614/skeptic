"""Generate ``customers.json`` once with the fixed S9.1 seed (20261101).

The output is committed; servers only read it (S9.1 item 3). Re-running this
module rewrites the file with the same bytes, because every choice comes from
a single ``random.Random(SEED)`` draw in a fixed order. All names, emails and
companies are fictional; only the city names are real (S9.1 item 8).

Run from the repository root:

    uv run python -m skeptic_agent.sandboxes.sb_common.generate
"""

import json
import random
from datetime import timedelta
from pathlib import Path

from skeptic_agent.sandboxes.sb_common.clock import format_iso, parse_instant

SEED = 20261101
"""The fixed generator seed every sandbox shares (S9.1)."""

CUSTOMER_COUNT = 40
"""The number of customers, C-1001 to C-1040 (S9.1 item 9)."""

OUTPUT = Path(__file__).resolve().parent / "data" / "customers.json"
"""Where the committed table lives (``sb_common/data/customers.json``)."""

TIERS = ("basic", "silver", "gold", "enterprise")
"""The tier names, lightest first."""

FIRST_NAMES = (
    "Ada",
    "Bruno",
    "Chloé",
    "Dmitri",
    "Elena",
    "Farid",
    "Greta",
    "Hiro",
    "Ines",
    "Jonas",
    "Keiko",
    "Lars",
    "Mei",
    "Nadia",
    "Omar",
    "Pia",
    "Quentin",
    "Rosa",
    "Sven",
    "Tara",
)

LAST_NAMES = (
    "Almeida",
    "Brandt",
    "Castillo",
    "Dubois",
    "Eriksen",
    "Fischer",
    "Gómez",
    "Hansen",
    "Ito",
    "Jensen",
    "Kowalski",
    "Lindgren",
    "Mori",
    "Novak",
    "Okafor",
    "Petrov",
    "Quintero",
    "Rossi",
    "Sato",
    "Thorne",
)

CITIES = (
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

_EPOCH = parse_instant("2025-01-01T00:00:00Z")
_CREATED_SPAN_S = 640 * 24 * 3600
"""Customers joined over about 21 months before the frozen instant."""


def build_customers() -> list[dict[str, object]]:
    """Build the customer table deterministically.

    Returns:
        One dict per customer with ``id``, ``name``, ``email``, ``tier``,
        ``city`` and ``created_at``, sorted by id.
    """
    rng = random.Random(SEED)
    customers: list[dict[str, object]] = []
    for index in range(CUSTOMER_COUNT):
        customer_id = f"C-{1001 + index}"
        first = FIRST_NAMES[index % len(FIRST_NAMES)]
        last = LAST_NAMES[rng.randrange(len(LAST_NAMES))]
        email = f"{first}.{last}.{index + 1:02d}@example.com".lower().replace("ó", "o")
        offset = rng.randrange(_CREATED_SPAN_S)
        created = _EPOCH + timedelta(seconds=offset)
        customers.append(
            {
                "id": customer_id,
                "name": f"{first} {last}",
                "email": email,
                "tier": TIERS[rng.randrange(len(TIERS))],
                "city": CITIES[rng.randrange(len(CITIES))],
                "created_at": format_iso(created),
            }
        )
    return customers


def write(path: Path = OUTPUT) -> None:
    """Write the table to ``path``.

    Args:
        path: The destination file.
    """
    text = json.dumps(build_customers(), ensure_ascii=False, indent=2) + "\n"
    path.write_text(text, encoding="utf-8", newline="\n")


if __name__ == "__main__":
    write()
