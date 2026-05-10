"""Tool registry — 每个 tool 模块在 import 时往这里 register。

Task 7-16 各自 import 后,TOOL_REGISTRY 被填满 10 项。
本 Task 6 只定义 registry 数据结构 + 占位。
"""
from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from mcp import types as mcp_types

ToolHandler = Callable[[dict[str, Any]], Awaitable[list[mcp_types.TextContent]]]


# (tool_name → (Tool definition, handler async fn))
TOOL_REGISTRY: dict[str, tuple[mcp_types.Tool, ToolHandler]] = {}


def register(tool: mcp_types.Tool, handler: ToolHandler) -> None:
    if tool.name in TOOL_REGISTRY:
        raise RuntimeError(f"duplicate tool registration: {tool.name}")
    TOOL_REGISTRY[tool.name] = (tool, handler)


def get_tool_definitions() -> list[mcp_types.Tool]:
    return [defn for defn, _ in TOOL_REGISTRY.values()]


def get_handler(name: str) -> ToolHandler | None:
    pair = TOOL_REGISTRY.get(name)
    return pair[1] if pair else None
