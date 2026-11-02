# sb_orders

A deterministic MCP sandbox over 120 fictional orders (O-2001 to O-2120) for
the 40 shared customers, used by Skeptic scenarios whose ids start with
`orders.` (S9.2, S33).

> All product names, people, prices and orders are fictional snapshot data;
> the customer ids are the ones shared with sb_crm and sb_mail (S9.1 item 9).

## Tools

Three read tools, two write tools.

| Tool | Kind | Arguments | Returns |
|---|---|---|---|
| `list_orders` | R | `customer_id`, `status?` | `orders[]` of `id, customer_id, status, total, currency, items[], created_at` |
| `get_order` | R | `order_id` | `id, customer_id, status, total, currency, items[], created_at` |
| `get_order_status` | R | `order_id` | `order_id, status` |
| `cancel_order` | W | `order_id`, `reason` | `status ("ok"), order_id, new_status ("cancelled")` |
| `refund_order` | W | `order_id`, `amount` | `status ("ok"), order_id, amount, currency ("USD")` |

- Every order is priced in `USD`; `total` is the sum of its items'
  `subtotal`s. An item has `product_id`, `name`, `quantity`, `unit_price` and
  `subtotal`.
- `list_orders` returns the customer's orders in id order. `status` is
  optional and filters to `pending`, `shipped`, `delivered` or `cancelled`.
- Only a `pending` order can be cancelled. A successful cancel sets its state
  to `cancelled` and returns `new_status: "cancelled"`.
- Only a `delivered` order can be refunded. The amount must be greater than
  zero and at most the order total; every refund is appended to the state's
  `refunds` list.
- The state is the S9.3 shape: `orders` (keyed by id) plus `refunds` and
  `updated_at`. Both write tools update the state file after they succeed.

## Example calls

```json
{"name": "list_orders", "arguments": {"customer_id": "C-1001"}}
```

```json
{"orders": [{"id": "O-2001", "customer_id": "C-1001", "status": "shipped",
  "total": 521.97, "currency": "USD", "items": [{"product_id": "P-102",
  "name": "Borealis Keyboard", "quantity": 3, "unit_price": 119.0,
  "subtotal": 357.0}], "created_at": "2026-07-07T20:31:01Z"}]}
```

```json
{"name": "cancel_order",
 "arguments": {"order_id": "O-2002", "reason": "Customer changed their mind."}}
```

```json
{"status": "ok", "order_id": "O-2002", "new_status": "cancelled"}
```

```json
{"name": "refund_order", "arguments": {"order_id": "O-2011", "amount": 120.0}}
```

```json
{"status": "ok", "order_id": "O-2011", "amount": 120.0, "currency": "USD"}
```

## Errors

An unknown customer or order id, an invalid status, an empty or oversized
reason, cancelling an order that is not pending, and refunding an order that
is not delivered (or refunding zero or more than the total) return an
`isError` result reading `Error: <reason>`. A failed write leaves the state
unchanged.

## Running

```text
python -m skeptic_agent.sandboxes.sb_orders
python -m skeptic_agent.sandboxes.sb_orders --http 127.0.0.1:8770
python -m skeptic_agent.sandboxes.sb_orders --state-file state.json
```

The orders come from `data/orders.json`, generated once with seed `20261101`
by `data/generate.py` and committed; the server only reads it. The customer
ids come from the shared `sb_common/data/customers.json`.
