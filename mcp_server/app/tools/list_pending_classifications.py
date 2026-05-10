"""MCP tool: list_pending_classifications — spec § 8.1 read #6。

backend endpoint: GET /api/transactions/pending-classifications
出参精简:每条只返 {id, time, amount, merchant, suggested_categories};
顶层 key items → transactions。suggested_categories 当前固定 []
(V2 后端会接 rapidfuzz 推荐)。
"""
from __future__ import annotations

import json
from typing import Any

from mcp import types as mcp_types

from app.backend_client import get_backend_client
from app.errors import MCPToolError
from app.tools import register

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


def _to_query(args: dict[str, Any]) -> dict[str, str | int]:
    """剔除 None,把 MCP 入参直传 backend query string(参数名一致)。"""
    out: dict[str, str | int] = {}
    for k in ("limit", "offset"):
        if k in args and args[k] is not None:
            out[k] = args[k]
    return out


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
            "/api/transactions/pending-classifications", params=_to_query(args),
        )
    except MCPToolError as e:
        return [mcp_types.TextContent(
            type="text",
            text=json.dumps({"error": e.to_dict()}, ensure_ascii=False),
        )]
    out = {
        "transactions": [_trim_transaction(t) for t in data.get("items", [])],
    }
    return [mcp_types.TextContent(type="text", text=json.dumps(out, ensure_ascii=False))]


register(_TOOL, _handler)
