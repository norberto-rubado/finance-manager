"""tool registry register() 防重测试。"""
from __future__ import annotations

import pytest
from mcp import types as mcp_types

from app.tools import TOOL_REGISTRY, register


@pytest.fixture(autouse=True)
def _isolate_registry():
    """每个 test 前后做一次快照/还原 — 避免污染真实 TOOL_REGISTRY。"""
    snapshot = dict(TOOL_REGISTRY)
    TOOL_REGISTRY.clear()
    TOOL_REGISTRY.update(snapshot)
    yield
    TOOL_REGISTRY.clear()
    TOOL_REGISTRY.update(snapshot)


def test_register_raises_on_duplicate_name():
    async def handler(_args: dict) -> list[mcp_types.TextContent]:
        return []

    tool = mcp_types.Tool(name="dup_tool_xyz", description="test", inputSchema={"type": "object"})
    register(tool, handler)
    with pytest.raises(RuntimeError, match="duplicate tool registration"):
        register(tool, handler)
