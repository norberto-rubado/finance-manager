"""MCP tool: confirm_dedup_pair — spec § 8.1 write #4 (last of 10 tools)。

backend endpoint: POST /api/dedup/{pair_id}/confirm body {"action": "confirm"|"reject"}
Confirm or reject a pending dedup_pair, marking the mirror transaction
accordingly. Backend's /confirm endpoint accepts both actions via body.
"""
from __future__ import annotations

from typing import Any

from mcp import types as mcp_types

from app.backend_client import get_backend_client
from app.errors import MCPToolError
from app.tools import register
from app.tools._helpers import error_envelope, text_envelope

_TOOL = mcp_types.Tool(
    name="confirm_dedup_pair",
    description=(
        "Confirm or reject a pending dedup_pair, marking the mirror transaction "
        "accordingly. Required: pair_id (dedup_pair.id), "
        "action (confirm | reject)."
    ),
    inputSchema={
        "type": "object",
        "properties": {
            "pair_id": {"type": "integer"},
            "action": {"type": "string", "enum": ["confirm", "reject"]},
        },
        "required": ["pair_id", "action"],
    },
)


async def _handler(args: dict[str, Any]) -> list[mcp_types.TextContent]:
    client = get_backend_client()
    pair_id = args["pair_id"]
    action = args["action"]
    try:
        data = await client.post(
            f"/api/dedup/{pair_id}/confirm",
            json={"action": action},
        )
    except MCPToolError as e:
        return error_envelope(e)
    out = {
        "ok": True,
        "primary_tx_id": data["primary_tx_id"],
        "mirror_tx_id": data["mirror_tx_id"],
        "action_taken": data["status"],   # "confirmed" | "rejected"
    }
    return text_envelope(out)


register(_TOOL, _handler)
