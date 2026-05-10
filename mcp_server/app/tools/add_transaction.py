"""MCP tool: add_transaction — spec § 8.1 write #1。

backend endpoint: POST /api/transactions/manual
入参字段做 MCP→backend rename(time→tx_time, account→account_id,
kind→tx_kind, category→category_id);出参精简到
{transaction_id, applied_rule, classified_category}。
"""
from __future__ import annotations

from typing import Any

from mcp import types as mcp_types

from app.backend_client import get_backend_client
from app.errors import MCPToolError
from app.tools import register
from app.tools._helpers import error_envelope, text_envelope

_TOOL = mcp_types.Tool(
    name="add_transaction",
    description=(
        "Create a manual transaction (source=manual). "
        "Required: time (ISO 8601 datetime), amount (decimal string e.g. '23.50'), "
        "merchant (1-255 chars), account (account.id). "
        "Optional: currency (default CNY), kind "
        "(expense|income|neutral|refund, default expense), description, "
        "category (category.id). Optionally pass category id to skip auto-classify; "
        "otherwise the backend rule engine fills it in."
    ),
    inputSchema={
        "type": "object",
        "properties": {
            "time": {"type": "string", "description": "ISO 8601 datetime"},
            "amount": {"type": "string", "description": "decimal string e.g. '23.50'"},
            "currency": {"type": "string", "default": "CNY"},
            "merchant": {"type": "string", "minLength": 1, "maxLength": 255},
            "category": {"type": "integer", "description": "optional category.id"},
            "account": {"type": "integer", "description": "account.id"},
            "kind": {
                "type": "string",
                "enum": ["expense", "income", "neutral", "refund"],
                "default": "expense",
            },
            "description": {"type": "string"},
        },
        "required": ["time", "amount", "merchant", "account"],
    },
)


def _to_body(args: dict[str, Any]) -> dict[str, Any]:
    """MCP 入参 → backend TransactionCreateIn shape(field rename + 默认值)。"""
    body: dict[str, Any] = {
        "tx_time": args["time"],
        "amount": args["amount"],
        "currency": args.get("currency", "CNY"),
        "merchant": args["merchant"],
        "account_id": args["account"],
        "tx_kind": args.get("kind", "expense"),
    }
    if args.get("category") is not None:
        body["category_id"] = args["category"]
    if args.get("description") is not None:
        body["description"] = args["description"]
    return body


async def _handler(args: dict[str, Any]) -> list[mcp_types.TextContent]:
    client = get_backend_client()
    try:
        data = await client.post(
            "/api/transactions/manual",
            json=_to_body(args),
        )
    except MCPToolError as e:
        return error_envelope(e)
    out = {
        "transaction_id": data["id"],
        # backend 不返 rule_id;V2 占位
        "applied_rule": None,
        "classified_category": data.get("category_id"),
    }
    return text_envelope(out)


register(_TOOL, _handler)
