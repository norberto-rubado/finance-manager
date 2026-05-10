"""MCP tool: list_transactions — spec § 8.1 read #1。

backend endpoint: GET /api/transactions
出参精简:每条只返 {id, time, amount, merchant, category}。
"""
from __future__ import annotations

import json
from typing import Any

from mcp import types as mcp_types

from app.backend_client import get_backend_client
from app.errors import MCPToolError
from app.tools import register

_TOOL = mcp_types.Tool(
    name="list_transactions",
    description=(
        "List transactions with optional filters. "
        "Use date_from/date_to (ISO 8601) for time range, account_id / category_id "
        "for scope, kind in {expense,income,neutral,refund} for type. "
        "Optional keyword (substring of merchant_normalized) and source "
        "(channel: bank/alipay/wechat/conversation/manual) filters available. "
        "Returns paginated list with summary fields per row."
    ),
    inputSchema={
        "type": "object",
        "properties": {
            "date_from": {"type": "string", "description": "ISO 8601 datetime, inclusive"},
            "date_to": {"type": "string", "description": "ISO 8601 datetime, inclusive"},
            "account_id": {"type": "integer", "description": "filter by account.id"},
            "category_id": {"type": "integer", "description": "filter by category.id"},
            "kind": {
                "type": "string",
                "enum": ["expense", "income", "neutral", "refund"],
            },
            "source": {
                "type": "string",
                "enum": ["bank", "alipay", "wechat", "conversation", "manual"],
            },
            "keyword": {"type": "string", "description": "substring of merchant_normalized"},
            "limit": {"type": "integer", "minimum": 1, "maximum": 500, "default": 50},
            "offset": {"type": "integer", "minimum": 0, "default": 0},
        },
        "required": [],
    },
)


def _to_query(args: dict[str, Any]) -> dict[str, str | int]:
    """剔除 None,把 MCP 入参直传 backend query string(参数名一致)。"""
    out: dict[str, str | int] = {}
    for k in ("date_from", "date_to", "account_id", "category_id",
              "kind", "source", "keyword", "limit", "offset"):
        if k in args and args[k] is not None:
            out[k] = args[k]
    return out


def _trim_transaction(tx: dict) -> dict:
    """spec § 8.1 read #1 出参字段精简。"""
    return {
        "id": tx["id"],
        "time": tx["tx_time"],
        "amount": tx["amount"],
        "merchant": tx.get("merchant_normalized") or tx.get("merchant_raw"),
        "category": tx.get("category_id"),
    }


async def _handler(args: dict[str, Any]) -> list[mcp_types.TextContent]:
    client = get_backend_client()
    try:
        data = await client.get("/api/transactions", params=_to_query(args))
    except MCPToolError as e:
        return [mcp_types.TextContent(
            type="text",
            text=json.dumps({"error": e.to_dict()}, ensure_ascii=False),
        )]
    out = {
        "transactions": [_trim_transaction(t) for t in data.get("items", [])],
        "total": data.get("total"),
        "limit": data.get("limit"),
        "offset": data.get("offset"),
    }
    return [mcp_types.TextContent(type="text", text=json.dumps(out, ensure_ascii=False))]


register(_TOOL, _handler)
