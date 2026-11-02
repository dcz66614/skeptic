"""Generate sb_crm's ``notes.json`` once with the fixed seed (20261101).

The output is committed; the server only reads it and the shared
``sb_common/data/customers.json`` (S9.1 items 3 and 9). Customers are not
generated here: S9.1 item 9 gives sb_crm the same 40 customers as sb_orders
and sb_mail, so it reads the shared table. S9.2 fixes the shape: 80 notes, two
per customer.

Each note links to a customer id from the shared table and carries a short
English or Chinese remark, so ``search_customers`` can use the notes as a
third way to find a customer. Every name is fictional (S9.1 item 8).

Run from the repository root:

    uv run python -m skeptic_agent.sandboxes.sb_crm.data.generate
"""

import json
import random
from datetime import timedelta
from pathlib import Path

from skeptic_agent.sandboxes.sb_common.clock import format_iso, parse_instant
from skeptic_agent.sandboxes.sb_common.data import load_customers

SEED = 20261101
"""The fixed generator seed every sandbox shares (S9.1)."""

OUTPUT = Path(__file__).resolve().parent / "notes.json"
"""Where the committed table lives."""

NOTES_PER_CUSTOMER = 2
"""S9.2: 40 customers, 80 notes."""

TOPICS = (
    "Renewal call scheduled next week.",
    "Asked about the enterprise upgrade.",
    "Prefers email contact over phone.",
    "Requested a quarterly usage report.",
    "Downgraded after the summer campaign.",
    "Interested in the sandbox pilot programme.",
    "Moved offices; billing address updated.",
    "Complained about slow support response.",
)
"""The notes' opening lines; a Chinese half follows in ``TOPICS_ZH``."""

TOPICS_ZH = (
    "已安排在续约电话。",
    "询问企业版升级方案。",
    "希望以邮件方式联系。",
    "要求每季度提供用量报告。",
    "夏季活动后降级到基础版。",
    "对沙箱试点项目感兴趣。",
    "已更新办公地址与账单地址。",
    "投诉支持响应过慢。",
)
"""The Chinese half of the note texts."""

_EPOCH = parse_instant("2026-03-01T00:00:00Z")
_NOTE_SPAN_S = 240 * 24 * 3600
"""Notes were written over about eight months before the frozen instant."""


def build_notes() -> list[dict[str, object]]:
    """Build the note table deterministically.

    Returns:
        One dict per note with ``id``, ``customer_id``, ``text`` and
        ``created_at``, ordered by ``id`` (N-3001 upwards).
    """
    rng = random.Random(SEED)
    customers = load_customers()
    notes: list[dict[str, object]] = []
    number = 3001
    for customer in customers:
        for index in range(NOTES_PER_CUSTOMER):
            language = "en" if (number + index) % 2 == 0 else "zh"
            topics = TOPICS if language == "en" else TOPICS_ZH
            text = topics[rng.randrange(len(topics))]
            offset = rng.randrange(_NOTE_SPAN_S)
            notes.append(
                {
                    "id": f"N-{number}",
                    "customer_id": customer["id"],
                    "text": text,
                    "created_at": format_iso(_EPOCH + timedelta(seconds=offset)),
                }
            )
            number += 1
    return notes


def write(path: Path = OUTPUT) -> None:
    """Write the table to ``path``.

    Args:
        path: The destination file.
    """
    text = json.dumps(build_notes(), ensure_ascii=False, indent=2) + "\n"
    path.write_text(text, encoding="utf-8", newline="\n")


if __name__ == "__main__":
    write()
