"""Generate sb_mail's ``inbox.json`` once with the fixed seed (20261101).

The output is committed; the server only reads it (S9.1 item 3). S9.2 fixes
the shape: 25 inbox messages with ``id``, ``from``, ``to``, ``subject``,
``body`` and ``received_at``. The senders are the shared customers from
``sb_common/data/customers.json`` (S9.1 item 9), so a sender's address matches
the same customer in sb_crm and sb_orders. Every name and address is fictional
(S9.1 item 8); nothing here is delivered or resolvable.

Run from the repository root:

    uv run python -m skeptic_agent.sandboxes.sb_mail.data.generate
"""

import json
import random
from datetime import timedelta
from pathlib import Path

from skeptic_agent.sandboxes.sb_common.clock import format_iso, parse_instant
from skeptic_agent.sandboxes.sb_common.data import load_customers

SEED = 20261101
"""The fixed generator seed every sandbox shares (S9.1)."""

OUTPUT = Path(__file__).resolve().parent / "inbox.json"
"""Where the committed inbox lives."""

EMAIL_COUNT = 25
"""S9.2: the inbox holds 25 messages."""

MAILBOX = "support@example.com"
"""The fictional mailbox the customers write to."""

FIRST_ID = 1001
"""The first email number; ids run M-1001 upwards."""

_EPOCH = parse_instant("2026-10-19T08:00:00Z")
"""The first message arrives twelve days before the frozen instant."""

_STEP_HOURS = 9
"""Consecutive messages are about nine hours apart."""

SUBJECTS = (
    "Question about my latest invoice",
    "Delivery status for my order",
    "Updating the billing address",
    "Request for a quarterly report",
    "Issue with the sandbox pilot",
    "Renewal terms for next year",
    "Meeting follow-up",
    "Password reset for the portal",
    "Feedback on the new dashboard",
)
"""The fictional subject lines."""

BODIES = (
    "Hello, could you confirm the amount on invoice INV-2041? Thank you.",
    "My order has not arrived yet. Could you check the delivery status?",
    "We moved offices last month. Please update the billing address on file.",
    "Please send the usage report for the third quarter when convenient.",
    "The sandbox pilot stopped accepting calls this morning. Can you investigate?",
    "We would like to review the renewal terms before the end of the month.",
    "Thanks for the meeting today. The notes are attached to our shared folder.",
    "I cannot sign in to the customer portal after the recent maintenance.",
    "The new dashboard is much clearer. One chart still shows the wrong label.",
)
"""The fictional message bodies."""


def build_inbox() -> list[dict[str, object]]:
    """Build the inbox deterministically.

    Returns:
        One dict per email with ``id``, ``from``, ``to``, ``subject``,
        ``body`` and ``received_at``, ordered by id and time.
    """
    rng = random.Random(SEED)
    customers = load_customers()
    emails: list[dict[str, object]] = []
    for index in range(EMAIL_COUNT):
        customer = customers[index]
        number = FIRST_ID + index
        received = _EPOCH + timedelta(hours=index * _STEP_HOURS, minutes=rng.randrange(60))
        emails.append(
            {
                "id": f"M-{number}",
                "from": customer["email"],
                "to": MAILBOX,
                "subject": SUBJECTS[index % len(SUBJECTS)],
                "body": f"{BODIES[rng.randrange(len(BODIES))]} — {customer['name']}",
                "received_at": format_iso(received),
            }
        )
    return emails


def write(path: Path = OUTPUT) -> None:
    """Write the inbox to ``path``.

    Args:
        path: The destination file.
    """
    text = json.dumps(build_inbox(), ensure_ascii=False, indent=2) + "\n"
    path.write_text(text, encoding="utf-8", newline="\n")


if __name__ == "__main__":
    write()
