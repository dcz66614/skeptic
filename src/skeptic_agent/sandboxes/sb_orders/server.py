"""The sb_orders tools (S9.2): three read tools and two write tools.

``list_orders``, ``get_order`` and ``get_order_status`` read; ``cancel_order``
and ``refund_order`` write. The 120 orders O-2001 to O-2120 come from the
committed ``data/orders.json``; their customer ids are the shared
``sb_common/data/customers.json`` ones (S9.1 item 9).

S9.2's business rules are enforced here: only a ``pending`` order can be
cancelled, only a ``delivered`` order can be refunded, and a refund may not
exceed the order total. A violation is a business error (``isError``) and
leaves the state unchanged.

The state is the S9.3 shape: an ``orders`` dict keyed by order id and a
``refunds`` list. Both write tools call ``tool.finish()``, so the state file
follows a successful write. The order field order is ``id, customer_id,
status, total, currency, items, created_at``, which puts ``total`` first for
S6 S04; ``currency`` is always ``USD`` (S9.2).
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

NAME = "sb_orders"
"""The server name (S9.1 item 2)."""

ORDERS_FILE = Path(__file__).resolve().parent / "data" / "orders.json"
"""The committed order table the server reads (S9.1 item 3)."""

STATUSES = ("pending", "shipped", "delivered", "cancelled")
"""The four order statuses (S9.2)."""

CUSTOMER_IDS = frozenset(str(customer["id"]) for customer in load_customers())
"""The shared customer ids a ``list_orders`` query may name (S9.1 item 9)."""

REASON_LIMIT = 200
"""The longest cancellation reason ``cancel_order`` accepts."""


class ListOrdersArguments(BaseModel):
    """The arguments of ``list_orders``."""

    customer_id: str = Field(description="The customer id, for example 'C-1001'.")
    status: str | None = Field(
        default=None,
        description="Only return orders with one status: pending, shipped, delivered or cancelled.",
    )


class OrderArguments(BaseModel):
    """The arguments of ``get_order`` and ``get_order_status``."""

    order_id: str = Field(description="The order id, for example 'O-2001'.")


class CancelArguments(BaseModel):
    """The arguments of ``cancel_order``."""

    order_id: str = Field(description="The order id, for example 'O-2001'.")
    reason: str = Field(description="Why the customer is cancelling, at most 200 characters.")


class RefundArguments(BaseModel):
    """The arguments of ``refund_order``."""

    order_id: str = Field(description="The delivered order id, for example 'O-2001'.")
    amount: float = Field(description="The refund amount in USD, at most the order total.")


class OrderItem(BaseModel):
    """One line of an order."""

    model_config = ConfigDict(extra="forbid")

    product_id: str
    name: str
    quantity: int
    unit_price: float
    subtotal: float


class Order(BaseModel):
    """One order (S9.2 ``order`` fields)."""

    model_config = ConfigDict(extra="forbid")

    id: str
    customer_id: str
    status: Literal["pending", "shipped", "delivered", "cancelled"]
    total: float
    currency: Literal["USD"]
    items: list[OrderItem]
    created_at: str


class Orders(BaseModel):
    """The orders a customer query matched."""

    orders: list[Order]


class OrderStatus(BaseModel):
    """The compact status view of one order."""

    order_id: str
    status: Literal["pending", "shipped", "delivered", "cancelled"]


class Cancellation(BaseModel):
    """The result of ``cancel_order`` (S9.2 ``status, order_id, new_status``)."""

    status: Literal["ok"]
    order_id: str
    new_status: Literal["cancelled"]


class Refund(BaseModel):
    """The result of ``refund_order``."""

    status: Literal["ok"]
    order_id: str
    amount: float
    currency: Literal["USD"]


def load_orders() -> dict[str, dict[str, Any]]:
    """Read the committed orders as a fresh copy.

    Returns:
        ``{order_id: order}``, in file order.
    """
    table: dict[str, dict[str, Any]] = load_json(ORDERS_FILE)
    return copy.deepcopy(table)


def _orders(tool: SandboxTool) -> dict[str, dict[str, Any]]:
    """Return the state's order table, typed for the tools.

    Args:
        tool: The bound tool.

    Returns:
        The ``{order_id: order}`` dict.
    """
    orders: dict[str, dict[str, Any]] = tool.data["orders"]
    return orders


def _refunds(tool: SandboxTool) -> list[dict[str, Any]]:
    """Return the state's refund list.

    Args:
        tool: The bound tool.

    Returns:
        The mutable list of refunds.
    """
    refunds: list[dict[str, Any]] = tool.data["refunds"]
    return refunds


def _order(tool: SandboxTool, order_id: str) -> dict[str, Any]:
    """Look up one order.

    Args:
        tool: The bound tool.
        order_id: The client's order id.

    Returns:
        The order entry.

    Raises:
        ToolFailure: When the id is not one of the 120 orders.
    """
    code = order_id.strip().upper()
    orders = _orders(tool)
    if code not in orders:
        raise ToolFailure(f"unknown order {order_id!r}")
    return orders[code]


def _status(value: str | None) -> str | None:
    """Validate an optional status filter.

    Args:
        value: The client's status, or ``None``.

    Returns:
        The lower-cased status, or ``None``.

    Raises:
        ToolFailure: When the value is not one of the four statuses.
    """
    if value is None:
        return None
    status = value.strip().lower()
    if status not in STATUSES:
        raise ToolFailure(f"unknown status {value!r}; choose one of {', '.join(STATUSES)}")
    return status


def _reason(value: str) -> str:
    """Validate a cancellation reason.

    Args:
        value: The client's reason.

    Returns:
        The reason with its surrounding whitespace removed.

    Raises:
        ToolFailure: When the reason is empty or longer than ``REASON_LIMIT``.
    """
    reason = value.strip()
    if not reason:
        raise ToolFailure("reason must not be empty")
    if len(reason) > REASON_LIMIT:
        raise ToolFailure(f"reason is longer than {REASON_LIMIT} characters")
    return reason


async def list_orders(arguments: ListOrdersArguments, tool: SandboxTool) -> Orders:
    """Return a customer's orders, optionally filtered by status.

    Args:
        arguments: The customer id and the optional status.
        tool: The bound tool.

    Returns:
        The matching orders, oldest id first. No match is an empty list.

    Raises:
        ToolFailure: On an unknown customer or an invalid status.
    """
    code = arguments.customer_id.strip().upper()
    if code not in CUSTOMER_IDS:
        raise ToolFailure(f"unknown customer {arguments.customer_id!r}")
    status = _status(arguments.status)
    orders = _orders(tool)
    return Orders(
        orders=[
            Order.model_validate(orders[order_id])
            for order_id in sorted(orders)
            if str(orders[order_id]["customer_id"]) == code
            and (status is None or str(orders[order_id]["status"]) == status)
        ]
    )


async def get_order(arguments: OrderArguments, tool: SandboxTool) -> Order:
    """Return one order.

    Args:
        arguments: The order id.
        tool: The bound tool.

    Returns:
        The order.

    Raises:
        ToolFailure: On an unknown order id.
    """
    return Order.model_validate(_order(tool, arguments.order_id))


async def get_order_status(arguments: OrderArguments, tool: SandboxTool) -> OrderStatus:
    """Return one order's status.

    Args:
        arguments: The order id.
        tool: The bound tool.

    Returns:
        The order id and its current status.

    Raises:
        ToolFailure: On an unknown order id.
    """
    order = _order(tool, arguments.order_id)
    return OrderStatus.model_validate({"order_id": order["id"], "status": order["status"]})


async def cancel_order(arguments: CancelArguments, tool: SandboxTool) -> Cancellation:
    """Cancel a pending order.

    Args:
        arguments: The order id and the reason.
        tool: The bound tool.

    Returns:
        ``status``, ``order_id`` and the new status ``cancelled``.

    Raises:
        ToolFailure: On an unknown order, an order that is not pending, or an
            empty/oversized reason; the state is then unchanged.
    """
    order = _order(tool, arguments.order_id)
    _reason(arguments.reason)
    current = str(order["status"])
    if current != "pending":
        raise ToolFailure(f"order {order['id']} is {current}; only pending orders can be cancelled")
    order["status"] = "cancelled"
    tool.finish()
    return Cancellation(status="ok", order_id=str(order["id"]), new_status="cancelled")


async def refund_order(arguments: RefundArguments, tool: SandboxTool) -> Refund:
    """Refund part or all of a delivered order.

    Args:
        arguments: The order id and the refund amount.
        tool: The bound tool.

    Returns:
        ``status``, ``order_id``, the refunded ``amount`` and ``currency``.

    Raises:
        ToolFailure: On an unknown order, an order that is not delivered, or
            an amount that is not positive or exceeds the order total; the
            state is then unchanged.
    """
    order = _order(tool, arguments.order_id)
    current = str(order["status"])
    if current != "delivered":
        raise ToolFailure(
            f"order {order['id']} is {current}; only delivered orders can be refunded"
        )
    total = float(order["total"])
    if arguments.amount <= 0:
        raise ToolFailure("amount must be greater than zero")
    if arguments.amount > total:
        raise ToolFailure(f"amount {arguments.amount!r} exceeds the order total {total!r}")
    _refunds(tool).append(
        {
            "order_id": str(order["id"]),
            "amount": arguments.amount,
            "currency": "USD",
            "created_at": now_iso(),
        }
    )
    tool.finish()
    return Refund(status="ok", order_id=str(order["id"]), amount=arguments.amount, currency="USD")


TOOLS = (
    ToolSpec(
        "list_orders",
        "Return a customer's orders, optionally only those with one status.",
        ListOrdersArguments,
        Orders,
        list_orders,
    ),
    ToolSpec(
        "get_order",
        "Return one order with its customer, status, total and line items.",
        OrderArguments,
        Order,
        get_order,
    ),
    ToolSpec(
        "get_order_status",
        "Return one order's id and current status.",
        OrderArguments,
        OrderStatus,
        get_order_status,
    ),
    ToolSpec(
        "cancel_order",
        "Cancel a pending order (not idempotent).",
        CancelArguments,
        Cancellation,
        cancel_order,
        write=True,
        destructive=True,
        idempotent=False,
    ),
    ToolSpec(
        "refund_order",
        "Refund a delivered order, up to its total (not idempotent).",
        RefundArguments,
        Refund,
        refund_order,
        write=True,
        destructive=False,
        idempotent=False,
    ),
)
"""The five S9.2 tools: three read, two write."""


def build_state() -> SandboxState:
    """Build the sandbox state from the committed orders.

    Returns:
        A state with the S9.3 ``orders`` dict and an empty ``refunds`` list;
        the file comes from ``SKEPTIC_STATE_FILE`` (S9.1 item 4).
    """
    return SandboxState.from_env({"orders": load_orders(), "refunds": []})


def server(state: SandboxState | None = None) -> Any:
    """Build the sb_orders server.

    Args:
        state: The state to serve; defaults to :func:`build_state`.

    Returns:
        The SDK server.
    """
    return make_server(NAME, TOOLS, state if state is not None else build_state())


def main() -> None:
    """Serve sb_orders (stdio, or ``--http HOST:PORT``)."""
    run_sandbox(NAME, TOOLS, build_state())


if __name__ == "__main__":
    main()
