"""MCP tool: bulk_update_category_by_merchant — spec § 8.1 write #3。

backend endpoint: POST /api/transactions/bulk-update-by-merchant
Bulk-update all transactions whose merchant_normalized matches pattern;
optionally also creates a merchant_rule so future imports auto-classify.
"""
from __future__ import annotations

from typing import Any

from mcp import types as mcp_types

from app.backend_client import get_backend_client
from app.errors import MCPToolError
from app.tools import register
from app.tools._helpers import error_envelope, text_envelope

_TOOL = mcp_types.Tool(
    name="bulk_update_category_by_merchant",
    description=(
        "Bulk-update all transactions whose merchant_normalized matches the "
        "pattern. Required: pattern (1-255 chars), category (target category.id). "
        "Optional: match_kind (exact|contains|regex|fuzzy, default contains), "
        "also_add_rule (default true). When also_add_rule=true, also creates a "
        "merchant_rule so future imports auto-classify."
    ),
    inputSchema={
        "type": "object",
        "properties": {
            "pattern": {"type": "string", "minLength": 1, "maxLength": 255},
            "category": {"type": "integer", "description": "target category.id"},
            "match_kind": {
                "type": "string",
                "enum": ["exact", "contains", "regex", "fuzzy"],
                "default": "contains",
            },
            "also_add_rule": {"type": "boolean", "default": True},
        },
        "required": ["pattern", "category"],
    },
)


def _to_body(args: dict[str, Any]) -> dict[str, Any]:
    """MCP 入参 → backend BulkUpdateByMerchantIn(category→category_id + 默认值)。"""
    return {
        "pattern": args["pattern"],
        "category_id": args["category"],
        "match_kind": args.get("match_kind", "contains"),
        "also_add_rule": args.get("also_add_rule", True),
    }


async def _handler(args: dict[str, Any]) -> list[mcp_types.TextContent]:
    client = get_backend_client()
    try:
        data = await client.post(
            "/api/transactions/bulk-update-by-merchant",
            json=_to_body(args),
        )
    except MCPToolError as e:
        return error_envelope(e)
    out = {
        "affected_count": data["affected_count"],
        "rule_id": data.get("rule_id"),
    }
    return text_envelope(out)


register(_TOOL, _handler)
