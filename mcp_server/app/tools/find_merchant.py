"""MCP tool: find_merchant — spec § 8.1 read #4。

backend endpoint: GET /api/transactions/merchants
出参 items → merchants(顶层 rename),每条字段直传。
"""
from __future__ import annotations

from typing import Any

from mcp import types as mcp_types

from app.backend_client import get_backend_client
from app.errors import MCPToolError
from app.tools import register
from app.tools._helpers import error_envelope, pick, text_envelope

_TOOL = mcp_types.Tool(
    name="find_merchant",
    description=(
        "Search merchants by substring keyword and aggregate count + total + "
        "sample categories. Required keyword (1-128 chars); "
        "optional limit (1-200, default 50). "
        "Returns one row per distinct normalized merchant matching the keyword."
    ),
    inputSchema={
        "type": "object",
        "properties": {
            "keyword": {
                "type": "string",
                "minLength": 1,
                "maxLength": 128,
                "description": "substring of merchant_normalized",
            },
            "limit": {
                "type": "integer",
                "minimum": 1,
                "maximum": 200,
                "default": 50,
            },
        },
        "required": ["keyword"],
    },
)


async def _handler(args: dict[str, Any]) -> list[mcp_types.TextContent]:
    client = get_backend_client()
    try:
        data = await client.get(
            "/api/transactions/merchants",
            params=pick(args, "keyword", "limit"),
        )
    except MCPToolError as e:
        return error_envelope(e)
    out = {
        "merchants": data.get("items", []),
    }
    return text_envelope(out)


register(_TOOL, _handler)
