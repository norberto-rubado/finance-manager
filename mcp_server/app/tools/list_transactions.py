"""MCP tool: list_transactions — spec § 8.1 read #1。

backend endpoint: GET /api/transactions
出参精简:每条只返 {id, time, amount, merchant, category}。
"""
from __future__ import annotations

from typing import Any

from mcp import types as mcp_types

from app.backend_client import get_backend_client
from app.errors import MCPToolError
from app.tools import register
from app.tools._helpers import error_envelope, pick, text_envelope

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
        data = await client.get(
            "/api/transactions",
            params=pick(
                args,
                "date_from", "date_to", "account_id", "category_id",
                "kind", "source", "keyword", "limit", "offset",
            ),
        )
    except MCPToolError as e:
        return error_envelope(e)
    out = {
        "transactions": [_trim_transaction(t) for t in data.get("items", [])],
        "total": data.get("total"),
        "limit": data.get("limit"),
        "offset": data.get("offset"),
    }
    return text_envelope(out)


register(_TOOL, _handler)
