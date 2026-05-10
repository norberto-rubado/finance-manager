"""MCP tool: find_merchant — spec § 8.1 read #4。

backend endpoint: GET /api/transactions/merchants
出参 items → merchants(顶层 rename),每条字段直传。
"""
from __future__ import annotations

import json
from typing import Any

from mcp import types as mcp_types

from app.backend_client import get_backend_client
from app.errors import MCPToolError
from app.tools import register

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


def _to_query(args: dict[str, Any]) -> dict[str, str | int]:
    """剔除 None,把 MCP 入参直传 backend query string(参数名一致)。"""
    out: dict[str, str | int] = {}
    for k in ("keyword", "limit"):
        if k in args and args[k] is not None:
            out[k] = args[k]
    return out


async def _handler(args: dict[str, Any]) -> list[mcp_types.TextContent]:
    client = get_backend_client()
    try:
        data = await client.get(
            "/api/transactions/merchants", params=_to_query(args),
        )
    except MCPToolError as e:
        return [mcp_types.TextContent(
            type="text",
            text=json.dumps({"error": e.to_dict()}, ensure_ascii=False),
        )]
    out = {
        "merchants": data.get("items", []),
    }
    return [mcp_types.TextContent(type="text", text=json.dumps(out, ensure_ascii=False))]


register(_TOOL, _handler)
