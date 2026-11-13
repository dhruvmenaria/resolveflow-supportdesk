import re

# Fictional records only; the lookup is deterministic and never calls a real commerce system.
ORDERS = {
    "ORD-2048": {"status": "delivered", "item": "ceramic pour-over set", "delivered_on": "2026-11-10", "customer_ref": "cust-1001"},
    "ORD-2051": {"status": "in_transit", "item": "linen table runner", "eta": "2026-11-17", "customer_ref": "cust-1002"},
}


def lookup_order(message: str, customer_ref: str) -> dict | None:
    found = re.search(r"\bORD-[0-9]{4}\b", message.upper())
    if not found:
        return None
    order = ORDERS.get(found.group())
    if not order or order["customer_ref"] != customer_ref:
        return {"order_ref": found.group(), "found": False}
    return {"order_ref": found.group(), "found": True, **order}
