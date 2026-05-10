"""MCP tool: list_pending_dedup_pairs — spec § 8.1 read #5。

backend endpoint: GET /api/dedup/pending
出参精简:每条只返 {id, primary, mirror, match_kind, confidence, reasoning};
顶层 key items → pairs。primary_tx_id → primary, mirror_tx_id → mirror。
"""
from __future__ import annotations

from typing import Any

from mcp import types as mcp_types

from app.backend_client import get_backend_client
from app.errors import MCPToolError
from app.tools import register
from app.tools._helpers import error_envelope, pick, text_envelope

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
        data = await client.get(
            "/api/dedup/pending",
            params=pick(args, "limit", "offset"),
        )
    except MCPToolError as e:
        return error_envelope(e)
    out = {
        "pairs": [_trim_pair(p) for p in data.get("items", [])],
    }
    return text_envelope(out)


register(_TOOL, _handler)
