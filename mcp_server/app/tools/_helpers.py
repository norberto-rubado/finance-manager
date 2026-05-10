"""Shared helpers for MCP tool handlers — DRY across 6+ tools.

Reviewers noted after Tasks 7-12 that the same 3 patterns repeat in every
tool: param allowlist + None-strip, JSON envelope wrapping, try/except
backend call. Extracted here so Tasks 13-16 (write tools) inherit the
pattern from day one.
"""
from __future__ import annotations

import json
from typing import Any

from mcp import types as mcp_types

from app.errors import MCPToolError


def pick(args: dict[str, Any], *keys: str) -> dict[str, Any]:
    """Allowlist + None-strip. Replaces inline `for k in (...): if k in args and args[k] is not None`."""
    return {k: args[k] for k in keys if k in args and args[k] is not None}


def text_envelope(payload: dict) -> list[mcp_types.TextContent]:
    """Wrap a result dict as MCP TextContent with UTF-8 JSON (Chinese-safe)."""
    return [mcp_types.TextContent(
        type="text",
        text=json.dumps(payload, ensure_ascii=False),
    )]


def error_envelope(exc: MCPToolError) -> list[mcp_types.TextContent]:
    """Wrap an MCPToolError as the spec § 8.3 JSON envelope inside TextContent."""
    return text_envelope({"error": exc.to_dict()})
