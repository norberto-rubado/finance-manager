"""MCP tool: get_account_balances — spec § 8.1 read #3。

backend endpoint: GET /api/accounts
出参精简:每条只返 {id, name, type, last4, latest_balance, latest_balance_at};
顶层 key items → accounts。
"""
from __future__ import annotations

from typing import Any

from mcp import types as mcp_types

from app.backend_client import get_backend_client
from app.errors import MCPToolError
from app.tools import register
from app.tools._helpers import error_envelope, text_envelope

_TOOL = mcp_types.Tool(
    name="get_account_balances",
    description=(
        "List all accounts with their latest derived balance "
        "(income - expense - refund, excluding mirrors). "
        "No parameters; returns one row per account with id/name/type/last4/"
        "latest_balance/latest_balance_at."
    ),
    inputSchema={
        "type": "object",
        "properties": {},
        "required": [],
    },
)


def _trim_account(acc: dict) -> dict:
    """spec § 8.1 read #3 出参字段精简(drop institution/currency/archived)。"""
    return {
        "id": acc["id"],
        "name": acc.get("name"),
        "type": acc.get("type"),
        "last4": acc.get("last4"),
        "latest_balance": acc.get("latest_balance"),
        "latest_balance_at": acc.get("latest_balance_at"),
    }


async def _handler(args: dict[str, Any]) -> list[mcp_types.TextContent]:
    client = get_backend_client()
    try:
        data = await client.get("/api/accounts")
    except MCPToolError as e:
        return error_envelope(e)
    out = {
        "accounts": [_trim_account(a) for a in data.get("items", [])],
    }
    return text_envelope(out)


register(_TOOL, _handler)
