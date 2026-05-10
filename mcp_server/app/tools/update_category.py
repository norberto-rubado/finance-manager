"""MCP tool: update_category — spec § 8.1 write #2。

backend endpoints: GET /api/transactions/{id} (capture before_category) +
PATCH /api/transactions/{id} (apply change). Two backend calls per
invocation —— spec want output {ok, before_category, after_category}, but
backend PATCH only returns the after-state, so we GET first to capture before.
"""
from __future__ import annotations

from typing import Any

from mcp import types as mcp_types

from app.backend_client import get_backend_client
from app.errors import MCPToolError
from app.tools import register
from app.tools._helpers import error_envelope, text_envelope

_TOOL = mcp_types.Tool(
    name="update_category",
    description=(
        "Update one transaction's category. Required: transaction_id, "
        "category (target category.id). Returns before+after category_id."
    ),
    inputSchema={
        "type": "object",
        "properties": {
            "transaction_id": {"type": "integer"},
            "category": {"type": "integer", "description": "target category.id"},
        },
        "required": ["transaction_id", "category"],
    },
)


async def _handler(args: dict[str, Any]) -> list[mcp_types.TextContent]:
    client = get_backend_client()
    tx_id = args["transaction_id"]
    target_category = args["category"]
    try:
        before = await client.get(f"/api/transactions/{tx_id}")
        after = await client.patch(
            f"/api/transactions/{tx_id}",
            json={"category_id": target_category},
        )
    except MCPToolError as e:
        return error_envelope(e)
    out = {
        "ok": True,
        "before_category": before["category_id"],
        "after_category": after["category_id"],
    }
    return text_envelope(out)


register(_TOOL, _handler)
