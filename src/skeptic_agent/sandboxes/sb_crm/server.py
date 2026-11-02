"""The sb_crm tools (S9.2): three read tools and two write tools.

``search_customers`` (name, email, city, tier and note text), ``get_customer``
and ``list_notes`` read; ``update_customer_email`` and ``add_note`` write.
The 40 customers come from the shared ``sb_common/data/customers.json``
(C-1001 to C-1040), so the ids agree with sb_orders and sb_mail (S9.1 item 9).
The 80 notes come from the committed ``data/notes.json``.

Field order matters for the S6 S04 ``numeric_corruption`` factor and S05
``wrong_entity``. A customer's insertion order is ``id, name, email, tier,
city, created_at``; there is no non-identifier number in it, so S04 on a
customer is not applicable (S6 allows that), while S05's ``entity_arg`` is the
``query`` and its decoy is another customer. A write result is ``status,
customer_id, ...``; ``status`` is a word, so S04 on it scales the next number.

``update_customer_email`` is idempotent: repeating it stores the same email
and returns the same result. ``add_note`` is not idempotent: every call adds a
note with a new id, and a failing write changes nothing and writes no state
file (S10 ``phantom_write`` compares the result against the state).
"""

import copy
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from skeptic_agent.sandboxes.sb_common.clock import now_iso
from skeptic_agent.sandboxes.sb_common.data import load_customers, load_json
from skeptic_agent.sandboxes.sb_common.server import (
    SandboxTool,
    ToolFailure,
    ToolSpec,
    make_server,
    run_sandbox,
)
from skeptic_agent.sandboxes.sb_common.state import SandboxState

NAME = "sb_crm"
"""The server name (S9.1 item 2)."""

NOTES_FILE = Path(__file__).resolve().parent / "data" / "notes.json"
"""The committed note table the server reads (S9.1 item 3)."""

TEXT_LIMIT = 500
"""The longest note text ``add_note`` accepts."""


class SearchArguments(BaseModel):
    """The arguments of ``search_customers``."""

    query: str = Field(description="Text to find in a customer's name, email, city, tier or notes.")


class CustomerArguments(BaseModel):
    """The arguments of ``get_customer`` and ``list_notes``."""

    customer_id: str = Field(description="The customer id, for example 'C-1001'.")


class EmailArguments(BaseModel):
    """The arguments of ``update_customer_email``."""

    customer_id: str = Field(description="The customer id, for example 'C-1001'.")
    email: str = Field(description="The new email address, for example 'ada@example.com'.")


class NoteArguments(BaseModel):
    """The arguments of ``add_note``."""

    customer_id: str = Field(description="The customer id, for example 'C-1001'.")
    text: str = Field(description="The note text, at most 500 characters.")


class Customer(BaseModel):
    """One customer (S9.2 ``customer`` fields)."""

    id: str
    name: str
    email: str
    tier: Literal["basic", "silver", "gold", "enterprise"]
    city: str
    created_at: str


class Customers(BaseModel):
    """The customers a search matched."""

    customers: list[Customer]


class Note(BaseModel):
    """One CRM note."""

    model_config = ConfigDict(extra="forbid")

    id: str
    customer_id: str
    text: str
    created_at: str


class Notes(BaseModel):
    """The notes of one customer."""

    notes: list[Note]


class EmailUpdate(BaseModel):
    """The result of ``update_customer_email`` (S9.2 ``status, customer_id, ...``)."""

    status: Literal["ok"]
    customer_id: str
    email: str


class NoteAdded(BaseModel):
    """The result of ``add_note`` (S9.2 ``status, customer_id, ...``)."""

    status: Literal["ok"]
    customer_id: str
    note_id: str


def load_notes() -> list[dict[str, Any]]:
    """Read the committed notes as a fresh copy.

    Returns:
        One dict per note, in file order.
    """
    notes: list[dict[str, Any]] = load_json(NOTES_FILE)
    return copy.deepcopy(notes)


def _customers(tool: SandboxTool) -> dict[str, dict[str, Any]]:
    """Return the state's customers keyed by id.

    Args:
        tool: The bound tool.

    Returns:
        The ``{customer_id: customer}`` dict.
    """
    customers: dict[str, dict[str, Any]] = tool.data["customers"]
    return customers


def _notes(tool: SandboxTool) -> list[dict[str, Any]]:
    """Return the state's note list.

    Args:
        tool: The bound tool.

    Returns:
        The mutable list of notes.
    """
    notes: list[dict[str, Any]] = tool.data["notes"]
    return notes


def _customer(tool: SandboxTool, customer_id: str) -> dict[str, Any]:
    """Look up one customer.

    Args:
        tool: The bound tool.
        customer_id: The client's customer id.

    Returns:
        The customer entry.

    Raises:
        ToolFailure: When the id is not in the shared table.
    """
    code = customer_id.strip().upper()
    customers = _customers(tool)
    if code not in customers:
        raise ToolFailure(f"unknown customer {customer_id!r}")
    return customers[code]


def _email(value: str) -> str:
    """Validate a replacement email address.

    Args:
        value: The client's email.

    Returns:
        The email, lower-cased.

    Raises:
        ToolFailure: When the value is not a plain ``local@domain`` address.
    """
    address = value.strip()
    local, separator, domain = address.partition("@")
    if not separator or not local or not domain or "@" in domain or "." not in domain:
        raise ToolFailure(f"invalid email {value!r}")
    if any(character.isspace() for character in address):
        raise ToolFailure(f"invalid email {value!r}")
    return address.lower()


def _note_text(value: str) -> str:
    """Validate new note text.

    Args:
        value: The client's note text.

    Returns:
        The text with its surrounding whitespace removed.

    Raises:
        ToolFailure: When the text is empty or longer than ``TEXT_LIMIT``.
    """
    text = value.strip()
    if not text:
        raise ToolFailure("note text must not be empty")
    if len(text) > TEXT_LIMIT:
        raise ToolFailure(f"note text is longer than {TEXT_LIMIT} characters")
    return text


def _next_note_id(notes: list[dict[str, Any]]) -> str:
    """Return the next free note id.

    Args:
        notes: The current notes.

    Returns:
        ``N-<number>`` one past the highest existing note id.
    """
    numbers = [int(str(note["id"]).removeprefix("N-")) for note in notes]
    return f"N-{max(numbers) + 1}"


async def search_customers(arguments: SearchArguments, tool: SandboxTool) -> Customers:
    """Find the customers matching a query.

    A customer matches when the lower-cased query occurs in the id, name,
    email, city or tier, or in the text of any of the customer's notes. An
    empty query lists every customer, which is a useful "all" view.

    Args:
        arguments: The query.
        tool: The bound tool.

    Returns:
        The matches, ordered by customer id.

    Raises:
        ToolFailure: Never; an unknown query has no matches.
    """
    needle = arguments.query.strip().lower()
    notes_by_customer: dict[str, str] = {}
    for note in _notes(tool):
        owner = str(note["customer_id"])
        notes_by_customer[owner] = f"{notes_by_customer.get(owner, '')} {note['text']}".lower()
    customers = _customers(tool)
    matches: list[Customer] = []
    for code in sorted(customers):
        customer = customers[code]
        haystack = " ".join(
            str(customer[field]) for field in ("id", "name", "email", "city", "tier")
        ).lower() + notes_by_customer.get(code, "")
        if needle in haystack:
            matches.append(Customer.model_validate(customer))
    return Customers(customers=matches)


async def get_customer(arguments: CustomerArguments, tool: SandboxTool) -> Customer:
    """Return one customer.

    Args:
        arguments: The customer id.
        tool: The bound tool.

    Returns:
        The customer.

    Raises:
        ToolFailure: On an unknown id.
    """
    return Customer.model_validate(_customer(tool, arguments.customer_id))


async def update_customer_email(arguments: EmailArguments, tool: SandboxTool) -> EmailUpdate:
    """Replace a customer's email (idempotent write).

    Args:
        arguments: The customer id and the new email.
        tool: The bound tool.

    Returns:
        ``status``, ``customer_id`` and the stored ``email``.

    Raises:
        ToolFailure: On an unknown id or an invalid email; the state is then
            unchanged.
    """
    customer = _customer(tool, arguments.customer_id)
    email = _email(arguments.email)
    customer["email"] = email
    customers = _customers(tool)
    customers[str(customer["id"])] = customer
    tool.finish()
    return EmailUpdate(status="ok", customer_id=str(customer["id"]), email=email)


async def add_note(arguments: NoteArguments, tool: SandboxTool) -> NoteAdded:
    """Append a note to a customer (non-idempotent write).

    Args:
        arguments: The customer id and the note text.
        tool: The bound tool.

    Returns:
        ``status``, ``customer_id`` and the new ``note_id``.

    Raises:
        ToolFailure: On an unknown id or invalid text; the state is then
            unchanged.
    """
    customer = _customer(tool, arguments.customer_id)
    text = _note_text(arguments.text)
    notes = _notes(tool)
    note_id = _next_note_id(notes)
    notes.append(
        {
            "id": note_id,
            "customer_id": str(customer["id"]),
            "text": text,
            "created_at": now_iso(),
        }
    )
    tool.finish()
    return NoteAdded(status="ok", customer_id=str(customer["id"]), note_id=note_id)


async def list_notes(arguments: CustomerArguments, tool: SandboxTool) -> Notes:
    """Return the notes of one customer, oldest first.

    Args:
        arguments: The customer id.
        tool: The bound tool.

    Returns:
        The customer's notes.

    Raises:
        ToolFailure: On an unknown id.
    """
    customer = _customer(tool, arguments.customer_id)
    return Notes(
        notes=[
            Note.model_validate(note)
            for note in _notes(tool)
            if note["customer_id"] == customer["id"]
        ]
    )


TOOLS = (
    ToolSpec(
        "search_customers",
        "Find customers whose name, email, city, tier or notes contain a query.",
        SearchArguments,
        Customers,
        search_customers,
    ),
    ToolSpec(
        "get_customer",
        "Return one customer's id, name, email, tier, city and sign-up date.",
        CustomerArguments,
        Customer,
        get_customer,
    ),
    ToolSpec(
        "update_customer_email",
        "Replace a customer's email address (idempotent).",
        EmailArguments,
        EmailUpdate,
        update_customer_email,
        write=True,
        destructive=False,
        idempotent=True,
    ),
    ToolSpec(
        "add_note",
        "Append a note to a customer (not idempotent).",
        NoteArguments,
        NoteAdded,
        add_note,
        write=True,
        destructive=False,
        idempotent=False,
    ),
    ToolSpec(
        "list_notes",
        "Return the notes recorded for one customer, oldest first.",
        CustomerArguments,
        Notes,
        list_notes,
    ),
)
"""The five S9.2 tools: three read, two write."""


def build_state() -> SandboxState:
    """Build the sandbox state from the shared customers and the notes.

    Returns:
        A state whose ``customers`` key is the shared table keyed by id and
        whose ``notes`` key is the committed note list (S9.1 items 4 and 9,
        S9.2 ``customers``/``notes``).
    """
    customers = {str(customer["id"]): customer for customer in load_customers()}
    return SandboxState.from_env({"customers": customers, "notes": load_notes()})


def server(state: SandboxState | None = None) -> Any:
    """Build the sb_crm server.

    Args:
        state: The state to serve; defaults to :func:`build_state`.

    Returns:
        The SDK server.
    """
    return make_server(NAME, TOOLS, state if state is not None else build_state())


def main() -> None:
    """Serve sb_crm (stdio, or ``--http HOST:PORT``)."""
    run_sandbox(NAME, TOOLS, build_state())


if __name__ == "__main__":
    main()
