"""Homework 1: the remaining commerce-agent tools.

The three lecture tools (`search_help_center`, `get_order`, `issue_refund`)
are implemented in agent/agent.py and are worked examples of the pattern:
check permissions first, go through agent/db.py for data, and return a
structured dict, never a prose error. The homework tools follow the same
pattern. agent/agent.py already wraps each function below as an SDK tool, so
once a function works here it works in chat with no further wiring.

Result convention (see agent/auth.py):
  - Success: a dict with "ok": True plus the payload fields named in each
    docstring.
  - Failure: {"ok": False, "error": <code>, "reason": <human-readable str>}.

Run the contract tests with: uv run pytest tests/test_hw_holes.py -k hw1
They are marked xfail and flip to passing as you implement each function.
"""

from __future__ import annotations

from typing import Any

from agent import db
from agent.auth import AuthContext, can_cancel_order, permission_denied
from agent.helpcenter import load_policy_docs
from agent.killswitch import kill_switch

MAX_SEARCH_LIMIT = 25
DEFAULT_ORDER_LIMIT = 20


def get_policy(ctx: AuthContext, policy_id: str) -> dict[str, Any]:
    """Fetch one policy doc by its exact id. Risk tier: read.

    Every role may read every policy doc (the corpus is public help-center
    content), so this tool needs no permission check.

    Args:
        ctx: The caller's auth context. Unused here, but every tool takes it.
        policy_id: An exact policy id, e.g. "cw-returns" or
            "store-juniper-home-goods-policy". Matching is exact and
            case-sensitive; ids are the `policy_id` front-matter field of the
            files in data/policies/.

    Returns:
        On success: {"ok": True, "policy_id": str, "title": str,
        "audience": str, "body": str} where body is the markdown body of the
        doc without the front matter.
        If no doc has that id: {"ok": False, "error": "not_found",
        "reason": ...} naming the id that was requested.

    Implementation notes:
        agent.helpcenter.load_policy_docs() returns every parsed doc.
    """
    for doc in load_policy_docs():
        if doc.policy_id == policy_id:
            return {
                "ok": True,
                "policy_id": doc.policy_id,
                "title": doc.title,
                "audience": doc.audience,
                "body": doc.body,
            }
    return {
        "ok": False,
        "error": "not_found",
        "reason": f"Policy '{policy_id}' not found",
    }


def search_products(
    ctx: AuthContext,
    query: str,
    store: str | None = None,
    max_price_usd: float | None = None,
    limit: int = 5,
) -> dict[str, Any]:
    """Search the product catalog. Risk tier: read.

    Every role may search products. Matching is deterministic keyword
    matching, not semantic search: a product matches when every whitespace
    token of `query` appears case-insensitively as a substring of the
    product's title or description.

    Args:
        ctx: The caller's auth context.
        query: Free-text query. Must be non-empty after stripping whitespace;
            otherwise return {"ok": False, "error": "invalid_argument",
            "reason": ...}.
        store: Optional store filter. Matched with
            agent.db.get_store_by_name (case-insensitive name or slug). If
            given and no store matches, return {"ok": False, "error":
            "not_found", "reason": ...} naming the store string.
        max_price_usd: Optional inclusive price ceiling. If given and not
            strictly positive, return an "invalid_argument" error.
        limit: Maximum products to return. Clamp to the range
            [1, MAX_SEARCH_LIMIT]; do not error on out-of-range values.

    Returns:
        {"ok": True, "products": [...], "count": <len(products)>} where each
        product is {"product_id": int, "store_id": int, "title": str,
        "price_usd": float}. Sort matches by price_usd ascending, then by
        product_id ascending, and truncate to `limit`. No matches is still a
        success: {"ok": True, "products": [], "count": 0}.

    Implementation notes:
        agent.db.list_products(conn, store_id) gives the candidate set.
        Use `with db.connection() as conn:` to close the database automatically.
    """
    stripped_query = query.strip()
    if not stripped_query:
        return {
            "ok": False,
            "error": "invalid_argument",
            "reason": "query must be a non-empty string",
        }

    if max_price_usd is not None and max_price_usd <= 0:
        return {
            "ok": False,
            "error": "invalid_argument",
            "reason": "max_price_usd must be positive",
        }

    clamped_limit = max(1, min(limit, MAX_SEARCH_LIMIT))

    with db.connection() as conn:
        store_id = None
        if store is not None:
            matched_store = db.get_store_by_name(conn, store)
            if matched_store is None:
                return {
                    "ok": False,
                    "error": "not_found",
                    "reason": f"Store '{store}' not found",
                }
            store_id = matched_store.id

        candidates = db.list_products(conn, store_id=store_id)

    query_tokens = stripped_query.lower().split()
    matched_products = []

    for product in candidates:
        text = f"{product.title} {product.description}".lower()
        if all(token in text for token in query_tokens):
            if max_price_usd is not None and product.price_usd > max_price_usd:
                continue
            matched_products.append(product)

    matched_products.sort(key=lambda p: (p.price_usd, p.id))
    truncated = matched_products[:clamped_limit]

    products_payload = [
        {
            "product_id": p.id,
            "store_id": p.store_id,
            "title": p.title,
            "price_usd": p.price_usd,
        }
        for p in truncated
    ]

    return {
        "ok": True,
        "products": products_payload,
        "count": len(products_payload),
    }


def list_my_orders(ctx: AuthContext) -> dict[str, Any]:
    """List recent orders in the caller's own scope. Risk tier: read.

    Role behavior, straight from the access matrix in SPEC.md:
        - shopper: the caller's own orders.
        - merchant: the caller's store's orders (ctx.store_id).
        - support: support staff have no orders of their own and look up
          specific orders with get_order instead, so return {"ok": False,
          "error": "invalid_argument", "reason": ...} saying exactly that.

    Returns:
        For shopper and merchant: {"ok": True, "orders": [...],
        "count": <len(orders)>} where each order is
        agent.db.Order.to_public_dict() and the list holds at most
        DEFAULT_ORDER_LIMIT orders, newest first (agent.db.list_orders_for_user
        and list_orders_for_store already sort and limit this way).

    Implementation notes:
        No permission check is needed beyond the role dispatch, because the
        scope is baked into which query you run. That is the point of the
        tool: the model cannot ask for someone else's orders through it.
    """
    with db.connection() as conn:
        if ctx.role == "shopper":
            orders = db.list_orders_for_user(conn, ctx.user_id, limit=DEFAULT_ORDER_LIMIT)
        elif ctx.role == "merchant":
            if ctx.store_id is None:
                return {
                    "ok": False,
                    "error": "invalid_argument",
                    "reason": "Merchant missing store_id in context",
                }
            orders = db.list_orders_for_store(conn, ctx.store_id, limit=DEFAULT_ORDER_LIMIT)
        elif ctx.role == "support":
            return {
                "ok": False,
                "error": "invalid_argument",
                "reason": "Support staff have no orders of their own and look up specific orders with get_order instead",
            }
        else:
            return {
                "ok": False,
                "error": "invalid_argument",
                "reason": f"Unknown role '{ctx.role}'",
            }

    orders_payload = [o.to_public_dict() for o in orders]
    return {
        "ok": True,
        "orders": orders_payload,
        "count": len(orders_payload),
    }


def cancel_order(ctx: AuthContext, order_id: int, reason: str) -> dict[str, Any]:
    """Cancel an order. Risk tier: write.

    This is the homework's write tool, and it must enforce two independent
    rules in this order:

    1. The access matrix (scope): use agent.auth.can_cancel_order. Shoppers
       may cancel only their own orders, merchants only their own store's
       orders, support any order. On failure return
       agent.auth.permission_denied(...) with a reason naming the role and
       the order id. Scope is checked before the status rule so that an
       out-of-scope caller learns nothing about the order's state.
    2. The pre-shipment rule (facts.yaml `cancel_cutoff`): only orders whose
       status is exactly "placed" can be cancelled, for every role. If the
       order is in scope but its status is not "placed", return
       {"ok": False, "error": "not_eligible", "reason": ...} that names the
       current status and states that orders can be cancelled only before
       shipment.

    Args:
        ctx: The caller's auth context.
        order_id: The order to cancel.
        reason: Free-text reason from the user; not validated.

    Returns:
        If no order has this id: {"ok": False, "error": "not_found",
        "reason": ...}.
        On success: {"ok": True, "order_id": order_id, "status": "cancelled"}
        after persisting the new status with agent.db.set_order_status.

    Implementation notes:
        Fetch with agent.db.get_order. Note the argument order of
        can_cancel_order(ctx, order_user_id, order_store_id).

    The Module 4 kill switch is checked first (before the scope and
    status rules and before your code), so that a paused write tool touches
    nothing. It is provided; the default ("off") returns None and falls
    through to your implementation.
    """
    paused = kill_switch("cancel_order")
    if paused is not None:
        return {"ok": False, "error": "paused", "reason": paused}
    with db.connection() as conn:
        order = db.get_order(conn, order_id)
        if order is None:
            return {
                "ok": False,
                "error": "not_found",
                "reason": f"Order {order_id} not found",
            }

        # 1. Access matrix (scope check comes first)
        if not can_cancel_order(ctx, order.user_id, order.store_id):
            return permission_denied(
                f"Role {ctx.role!r} user {ctx.user_id} cannot cancel order {order_id}"
            )

        # 2. Pre-shipment rule (status must be 'placed')
        if order.status != "placed":
            return {
                "ok": False,
                "error": "not_eligible",
                "reason": f"Order status is {order.status!r}; orders can be cancelled only before shipment",
            }

        db.set_order_status(conn, order_id, "cancelled")

    return {
        "ok": True,
        "order_id": order_id,
        "status": "cancelled",
    }


def find_order(ctx: AuthContext, query: str) -> dict[str, Any]:
    """Search the caller's orders by product name. Risk tier: read.

    Takes a natural-language query (e.g., "earmuffs I bought last week")
    and searches the authenticated user's orders for products whose name
    matches. Use fuzzy string matching (e.g., thefuzz.fuzz.partial_ratio
    or SQLite LIKE) to find orders whose product name is close to the
    query.

    Access rules: a shopper searches only the shopper's own orders, a
    merchant searches orders from the merchant's store, and support staff
    can search any orders. Use agent.db.list_orders_for_user for shoppers
    and agent.db.list_orders_for_store for merchants. For support staff,
    use agent.db.list_orders_for_user with no user filter, or search
    across all orders.

    Args:
        ctx: The caller's auth context.
        query: A natural-language description of the product.

    Returns:
        {"ok": True, "orders": [...]} with a list of matching orders
        (at most 5), each as the dict returned by agent.db. If no orders
        match, return {"ok": True, "orders": []}.
    """
    stripped_query = query.strip().lower()
    if not stripped_query:
        return {"ok": True, "orders": []}

    try:
        from rapidfuzz import fuzz
    except ImportError:
        fuzz = None

    with db.connection() as conn:
        if ctx.role == "shopper":
            candidate_orders = db.list_orders_for_user(conn, ctx.user_id, limit=500)
        elif ctx.role == "merchant":
            if ctx.store_id is None:
                return {"ok": True, "orders": []}
            candidate_orders = db.list_orders_for_store(conn, ctx.store_id, limit=500)
        elif ctx.role == "support":
            rows = conn.execute(
                "SELECT * FROM orders ORDER BY ordered_at DESC, id DESC LIMIT 500"
            ).fetchall()
            candidate_orders = [db._order_from_row(row) for row in rows]
        else:
            return {"ok": True, "orders": []}

        if not candidate_orders:
            return {"ok": True, "orders": []}

        # Build product_id -> product mapping for candidate orders
        products = db.list_products(conn)
        product_map = {p.id: p for p in products}

        query_tokens = [t for t in stripped_query.split() if len(t) > 2]
        matched_orders = []

        for order in candidate_orders:
            product = product_map.get(order.product_id)
            if not product:
                continue

            title_lower = product.title.lower()
            desc_lower = product.description.lower()
            text_combined = f"{title_lower} {desc_lower}"

            # 1. Exact or Substring match
            if stripped_query in title_lower or stripped_query in text_combined:
                matched_orders.append(order.to_public_dict())
                continue

            # 2. Token overlap match
            if query_tokens and all(tok in text_combined for tok in query_tokens):
                matched_orders.append(order.to_public_dict())
                continue

            # 3. Fuzzy ratio match
            if fuzz is not None and (
                fuzz.partial_ratio(stripped_query, title_lower) >= 65
                or fuzz.partial_ratio(stripped_query, desc_lower) >= 65
            ):
                matched_orders.append(order.to_public_dict())

    return {
        "ok": True,
        "orders": matched_orders[:5],
    }
