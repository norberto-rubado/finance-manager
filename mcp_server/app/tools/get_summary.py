"""MCP tool: get_summary — spec § 8.1 read #2。

backend endpoint: GET /api/summary
出参 breakdown[].group_key → breakdown[].group(MCP 简化命名)。
"""
from __future__ import annotations

from typing import Any

from mcp import types as mcp_types

from app.backend_client import get_backend_client
from app.errors import MCPToolError
from app.tools import register
from app.tools._helpers import error_envelope, pick, text_envelope

_TOOL = mcp_types.Tool(
    name="get_summary",
    description=(
        "Aggregate transactions over a period and group by category/account/merchant. "
        "Use period in {day,week,month,year} (default month) and "
        "group_by in {category,account,merchant} (default category). "
        "Optional date_from/date_to (ISO 8601) override the period window. "
        "Returns total_expense, total_income, and breakdown rows."
    ),
    inputSchema={
        "type": "object",
        "properties": {
            "period": {
                "type": "string",
                "enum": ["day", "week", "month", "year"],
                "default": "month",
            },
            "group_by": {
                "type": "string",
                "enum": ["category", "account", "merchant"],
                "default": "category",
            },
            "date_from": {"type": "string", "description": "ISO 8601 datetime, inclusive"},
            "date_to": {"type": "string", "description": "ISO 8601 datetime, inclusive"},
        },
        "required": [],
    },
)


def _trim_breakdown_row(row: dict) -> dict:
    """spec § 8.1 read #2:group_key → group(其他字段直传)。"""
    return {
        "group": row.get("group_key"),
        "group_id": row.get("group_id"),
        "amount": row.get("amount"),
        "count": row.get("count"),
    }


async def _handler(args: dict[str, Any]) -> list[mcp_types.TextContent]:
    client = get_backend_client()
    try:
        data = await client.get(
            "/api/summary",
            params=pick(args, "period", "group_by", "date_from", "date_to"),
        )
    except MCPToolError as e:
        return error_envelope(e)
    out = {
        "period": data.get("period"),
        "date_from": data.get("date_from"),
        "date_to": data.get("date_to"),
        "group_by": data.get("group_by"),
        "total_expense": data.get("total_expense"),
        "total_income": data.get("total_income"),
        "breakdown": [_trim_breakdown_row(r) for r in data.get("breakdown", [])],
    }
    return text_envelope(out)


register(_TOOL, _handler)
