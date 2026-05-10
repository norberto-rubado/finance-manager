"""MCP tool: list_pending_classifications — spec § 8.1 read #6。

backend endpoint: GET /api/transactions/pending-classifications
出参精简:每条只返 {id, time, amount, merchant, suggested_categories};
顶层 key items → transactions。suggested_categories 当前固定 []
(V2 后端会接 rapidfuzz 推荐)。
"""
from __future__ import annotations

from typing import Any

from mcp import types as mcp_types

from app.backend_client import get_backend_client
from app.errors import MCPToolError
from app.tools import register
from app.tools._helpers import error_envelope, pick, text_envelope

_TOOL = mcp_types.Tool(
    name="list_pending_classifications",
    description=(
        "List uncategorized (category_id IS NULL) non-mirror transactions for "
        "agent to classify. Optional limit (1-200, default 20) and "
        "offset (default 0). Returns transactions with id/time/amount/merchant/"
        "suggested_categories (suggested_categories is currently always [], "
        "reserved for V2 backend rapidfuzz suggestions)."
    ),
    inputSchema={
        "type": "object",
        "properties": {
            "limit": {
                "type": "integer",
                "minimum": 1,
                "maximum": 200,
                "default": 20,
            },
            "offset": {"type": "integer", "minimum": 0, "default": 0},
        },
        "required": [],
    },
)


def _trim_transaction(tx: dict) -> dict:
    """spec § 8.1 read #6 出参字段精简:tx_time→time, merchant_normalized→merchant
    (fallback merchant_raw),suggested_categories 当前固定 []。"""
    return {
        "id": tx["id"],
        "time": tx["tx_time"],
        "amount": tx["amount"],
        "merchant": tx.get("merchant_normalized") or tx.get("merchant_raw"),
        "suggested_categories": [],
    }


async def _handler(args: dict[str, Any]) -> list[mcp_types.TextContent]:
    client = get_backend_client()
    try:
        data = await client.get(
            "/api/transactions/pending-classifications",
            params=pick(args, "limit", "offset"),
        )
    except MCPToolError as e:
        return error_envelope(e)
    out = {
        "transactions": [_trim_transaction(t) for t in data.get("items", [])],
    }
    return text_envelope(out)


register(_TOOL, _handler)
