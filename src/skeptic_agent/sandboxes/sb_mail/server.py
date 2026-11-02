"""The sb_mail tools (S9.2): three read tools and one write tool.

``list_inbox``, ``read_email`` and ``search_mail`` read; ``send_email`` writes
to the state's ``outbox``. The 25 inbox messages are the committed
``data/inbox.json``; their senders are the shared customers from
``sb_common/data/customers.json`` (S9.1 item 9), so a sender's address matches
the same customer in sb_crm and sb_orders.

S9.2 fixes the email fields verbatim: ``id, from, to, subject, body,
received_at``. ``from`` is a Python keyword, so the model stores it as
``from_`` with the alias ``from``; the shared result wrapper dumps by alias,
so the wire field is exactly ``from``. A send result is ``status,
message_id``.

``send_email`` accepts any syntactically valid address, including the reserved
``@exfil.example`` domain the injection scenarios watch. It never resolves or
delivers anything; the message only grows the outbox (S9.2).
"""

import copy
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from skeptic_agent.sandboxes.sb_common.clock import now_iso
from skeptic_agent.sandboxes.sb_common.data import load_json
from skeptic_agent.sandboxes.sb_common.server import (
    SandboxTool,
    ToolFailure,
    ToolSpec,
    make_server,
    run_sandbox,
)
from skeptic_agent.sandboxes.sb_common.state import SandboxState

NAME = "sb_mail"
"""The server name (S9.1 item 2)."""

INBOX_FILE = Path(__file__).resolve().parent / "data" / "inbox.json"
"""The committed inbox the server reads (S9.1 item 3)."""

SENDER = "me@example.com"
"""The fictional mailbox's own address, used as ``from`` on sends."""

DEFAULT_LIMIT = 20
"""The ``list_inbox`` default limit (S9.2)."""

MAX_LIMIT = 100
"""The largest ``list_inbox`` limit accepted."""

SUBJECT_LIMIT = 200
"""The longest subject ``send_email`` accepts."""

BODY_LIMIT = 20_000
"""The longest body ``send_email`` accepts."""

FOLDERS = ("inbox", "outbox")
"""The two folders ``list_inbox`` can list."""


class ListArguments(BaseModel):
    """The arguments of ``list_inbox``."""

    folder: str = Field(default="inbox", description="The folder to list: 'inbox' or 'outbox'.")
    limit: int = Field(default=DEFAULT_LIMIT, description="The maximum number of messages.")


class EmailArguments(BaseModel):
    """The arguments of ``read_email``."""

    email_id: str = Field(description="The email id, for example 'M-1001'.")


class SearchArguments(BaseModel):
    """The arguments of ``search_mail``."""

    query: str = Field(
        description="Text to find in an email's id, sender, recipient, subject or body."
    )


class SendArguments(BaseModel):
    """The arguments of ``send_email``."""

    to: str = Field(description="The recipient address, for example 'ada@example.com'.")
    subject: str = Field(description="The subject, at most 200 characters.")
    body: str = Field(description="The body, at most 20000 characters.")


class Email(BaseModel):
    """One email (S9.2 ``email`` fields)."""

    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    id: str
    from_: str = Field(alias="from")
    to: str
    subject: str
    body: str
    received_at: str


class Emails(BaseModel):
    """The emails a listing or search matched."""

    emails: list[Email]


class Sent(BaseModel):
    """The result of ``send_email`` (S9.2 ``status, message_id``)."""

    status: Literal["ok"]
    message_id: str


def load_inbox() -> list[dict[str, Any]]:
    """Read the committed inbox as a fresh copy.

    Returns:
        One dict per email, in file order.
    """
    emails: list[dict[str, Any]] = load_json(INBOX_FILE)
    return copy.deepcopy(emails)


def _inbox(tool: SandboxTool) -> list[dict[str, Any]]:
    """Return the state's inbox list.

    Args:
        tool: The bound tool.

    Returns:
        The mutable inbox list.
    """
    emails: list[dict[str, Any]] = tool.data["inbox"]
    return emails


def _outbox(tool: SandboxTool) -> list[dict[str, Any]]:
    """Return the state's outbox list.

    Args:
        tool: The bound tool.

    Returns:
        The mutable outbox list.
    """
    emails: list[dict[str, Any]] = tool.data["outbox"]
    return emails


def _all(tool: SandboxTool) -> list[dict[str, Any]]:
    """Return the inbox and outbox together.

    Args:
        tool: The bound tool.

    Returns:
        The combined list, inbox first.
    """
    return [*_inbox(tool), *_outbox(tool)]


def _newest(emails: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Sort emails newest first.

    Args:
        emails: The emails to sort.

    Returns:
        A new list ordered by ``received_at`` then id, descending.
    """
    return sorted(emails, key=lambda email: (email["received_at"], email["id"]), reverse=True)


def _email(tool: SandboxTool, email_id: str) -> dict[str, Any]:
    """Look up one email in the inbox or the outbox.

    Args:
        tool: The bound tool.
        email_id: The client's email id.

    Returns:
        The email entry.

    Raises:
        ToolFailure: When the id is in neither folder.
    """
    code = email_id.strip().upper()
    for email in _all(tool):
        if str(email["id"]).upper() == code:
            return email
    raise ToolFailure(f"unknown email {email_id!r}")


def _folder(value: str) -> str:
    """Validate a folder name.

    Args:
        value: The client's folder.

    Returns:
        The lower-cased folder name.

    Raises:
        ToolFailure: When the folder is not ``inbox`` or ``outbox``.
    """
    folder = value.strip().lower()
    if folder not in FOLDERS:
        raise ToolFailure(f"unknown folder {value!r}")
    return folder


def _mailbox(value: str) -> str:
    """Validate a recipient address.

    Args:
        value: The client's address.

    Returns:
        The address, lower-cased.

    Raises:
        ToolFailure: When the value is not a plain ``local@domain`` address.
    """
    address = value.strip()
    local, separator, domain = address.partition("@")
    if not separator or not local or not domain or "@" in domain or "." not in domain:
        raise ToolFailure(f"invalid email address {value!r}")
    if any(character.isspace() for character in address):
        raise ToolFailure(f"invalid email address {value!r}")
    return address.lower()


def _subject(value: str) -> str:
    """Validate a subject line.

    Args:
        value: The client's subject.

    Returns:
        The subject without its surrounding whitespace.

    Raises:
        ToolFailure: When it is empty or longer than ``SUBJECT_LIMIT``.
    """
    subject = value.strip()
    if not subject:
        raise ToolFailure("subject must not be empty")
    if len(subject) > SUBJECT_LIMIT:
        raise ToolFailure(f"subject is longer than {SUBJECT_LIMIT} characters")
    return subject


def _body(value: str) -> str:
    """Validate a message body.

    Args:
        value: The client's body.

    Returns:
        The body without its surrounding whitespace.

    Raises:
        ToolFailure: When it is empty or longer than ``BODY_LIMIT``.
    """
    body = value.strip()
    if not body:
        raise ToolFailure("body must not be empty")
    if len(body) > BODY_LIMIT:
        raise ToolFailure(f"body is longer than {BODY_LIMIT} characters")
    return body


def _next_message_id(tool: SandboxTool) -> str:
    """Return the next free outbound message id.

    Args:
        tool: The bound tool.

    Returns:
        ``M-<number>`` one past the highest existing message id, starting at
        M-5001 so an outbound id never collides with the committed inbox.
    """
    numbers = [int(str(email["id"]).removeprefix("M-")) for email in _all(tool)]
    return f"M-{max([5000, *numbers]) + 1}"


async def list_inbox(arguments: ListArguments, tool: SandboxTool) -> Emails:
    """List one folder's messages, newest first.

    Args:
        arguments: The folder and the maximum number of messages.
        tool: The bound tool.

    Returns:
        Up to ``limit`` messages. A limit above the folder size returns all.

    Raises:
        ToolFailure: On an unknown folder or a limit below one or above
            ``MAX_LIMIT``.
    """
    folder = _folder(arguments.folder)
    if arguments.limit < 1:
        raise ToolFailure("limit must be greater than zero")
    if arguments.limit > MAX_LIMIT:
        raise ToolFailure(f"limit is greater than {MAX_LIMIT}")
    emails = _inbox(tool) if folder == "inbox" else _outbox(tool)
    return Emails(
        emails=[Email.model_validate(email) for email in _newest(emails)[: arguments.limit]]
    )


async def read_email(arguments: EmailArguments, tool: SandboxTool) -> Email:
    """Return one email, from either the inbox or the outbox.

    Args:
        arguments: The email id.
        tool: The bound tool.

    Returns:
        The email.

    Raises:
        ToolFailure: On an unknown email id.
    """
    return Email.model_validate(_email(tool, arguments.email_id))


async def search_mail(arguments: SearchArguments, tool: SandboxTool) -> Emails:
    """Search the inbox and outbox for every query term.

    Every whitespace-separated term must occur, case-insensitively, in the id,
    sender, recipient, subject or body. The matches are newest first.

    Args:
        arguments: The query.
        tool: The bound tool.

    Returns:
        The matching emails; no match is an empty list.

    Raises:
        ToolFailure: When the query is empty or only whitespace.
    """
    terms = arguments.query.lower().split()
    if not terms:
        raise ToolFailure("query must not be empty")
    matches: list[dict[str, Any]] = []
    for email in _all(tool):
        haystack = " ".join(
            str(email[field]) for field in ("id", "from", "to", "subject", "body")
        ).lower()
        if all(term in haystack for term in terms):
            matches.append(email)
    return Emails(emails=[Email.model_validate(email) for email in _newest(matches)])


async def send_email(arguments: SendArguments, tool: SandboxTool) -> Sent:
    """Append a message to the outbox (non-idempotent write).

    Args:
        arguments: The recipient, subject and body.
        tool: The bound tool.

    Returns:
        ``status`` and the new ``message_id``.

    Raises:
        ToolFailure: On an invalid recipient, an empty or oversized subject or
            body; the state is then unchanged.
    """
    recipient = _mailbox(arguments.to)
    subject = _subject(arguments.subject)
    body = _body(arguments.body)
    message_id = _next_message_id(tool)
    _outbox(tool).append(
        {
            "id": message_id,
            "from": SENDER,
            "to": recipient,
            "subject": subject,
            "body": body,
            "received_at": now_iso(),
        }
    )
    tool.finish()
    return Sent(status="ok", message_id=message_id)


TOOLS = (
    ToolSpec(
        "list_inbox",
        "List one mail folder's messages, newest first (default inbox, 20 messages).",
        ListArguments,
        Emails,
        list_inbox,
    ),
    ToolSpec(
        "read_email",
        "Return one email's sender, recipient, subject, body and received time.",
        EmailArguments,
        Email,
        read_email,
    ),
    ToolSpec(
        "search_mail",
        "Search the inbox and outbox for emails containing every query term.",
        SearchArguments,
        Emails,
        search_mail,
    ),
    ToolSpec(
        "send_email",
        "Append a message to the outbox (not idempotent).",
        SendArguments,
        Sent,
        send_email,
        write=True,
        destructive=False,
        idempotent=False,
    ),
)


def build_state() -> SandboxState:
    """Build the sandbox state from the committed inbox and an empty outbox.

    Returns:
        A state whose ``inbox`` and ``outbox`` keys hold the message lists;
        the file comes from ``SKEPTIC_STATE_FILE`` (S9.1 item 4, S9.2).
    """
    return SandboxState.from_env({"inbox": load_inbox(), "outbox": []})


def server(state: SandboxState | None = None) -> Any:
    """Build the sb_mail server.

    Args:
        state: The state to serve; defaults to :func:`build_state`.

    Returns:
        The SDK server.
    """
    return make_server(NAME, TOOLS, state if state is not None else build_state())


def main() -> None:
    """Serve sb_mail (stdio, or ``--http HOST:PORT``)."""
    run_sandbox(NAME, TOOLS, build_state())


if __name__ == "__main__":
    main()
