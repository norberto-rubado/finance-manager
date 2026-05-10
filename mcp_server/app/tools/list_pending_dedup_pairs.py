"""MCP tool: list_pending_dedup_pairs — spec § 8.1 read #5。

backend endpoint: GET /api/dedup/pending
出参精简:每条只返 {id, primary, mirror, match_kind, confidence, reasoning};
顶层 key items → pairs。primary_tx_id → primary, mirror_tx_id → mirror。
"""
from __future__ import annotations

import json
from typing import Any

from mcp import types as mcp_types

from app.backend_client import get_backend_client
from app.errors import MCPToolError
from app.tools import register

_TOOL = mcp_types.Tool(
    name="list_pending_dedup_pairs",
    description=(
        "List dedup candidate pairs awaiting human/agent decision. "
        "Optional limit (1-200, default 20) and offset (default 0). "
        "Returns pair rows with primary/mirror tx ids, match_kind, "
        "confidence, and reasoning."
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


def _trim_pair(p: dict) -> dict:
    """spec § 8.1 read #5:rename primary_tx_id→primary, mirror_tx_id→mirror;
    drop status/created_at/decided_at/user_id。"""
    return {
        "id": p["id"],
        "primary": p.get("primary_tx_id"),
        "mirror": p.get("mirror_tx_id"),
        "match_kind": p.get("match_kind"),
        "confidence": p.get("confidence"),
        "reasoning": p.get("reasoning"),
    }


async def _handler(args: dict[str, Any]) -> list[mcp_types.TextContent]:
    client = get_backend_client()
    try:
        data = await client.get("/api/dedup/pending", params=_to_query(args))
    except MCPToolError as e:
        return [mcp_types.TextContent(
            type="text",
            text=json.dumps({"error": e.to_dict()}, ensure_ascii=False),
        )]
    out = {
        "pairs": [_trim_pair(p) for p in data.get("items", [])],
    }
    return [mcp_types.TextContent(type="text", text=json.dumps(out, ensure_ascii=False))]


register(_TOOL, _handler)
