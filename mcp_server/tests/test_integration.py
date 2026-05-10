"""MCP server 集成自检 — 10 工具齐全 + dispatch 正常。"""
from __future__ import annotations

import pytest

from app.main import _register_all_tools
from app.tools import TOOL_REGISTRY, get_handler, get_tool_definitions

_EXPECTED_TOOLS = {
    "list_transactions",
    "get_summary",
    "get_account_balances",
    "find_merchant",
    "list_pending_dedup_pairs",
    "list_pending_classifications",
    "add_transaction",
    "update_category",
    "bulk_update_category_by_merchant",
    "confirm_dedup_pair",
}


@pytest.fixture(autouse=True)
def _register_once():
    _register_all_tools()


def test_all_10_tools_registered():
    names = {t.name for t in get_tool_definitions()}
    missing = _EXPECTED_TOOLS - names
    extra = names - _EXPECTED_TOOLS
    assert not missing, f"missing tools: {missing}"
    assert not extra, f"unexpected extra tools: {extra}"


def test_each_tool_has_handler_and_schema():
    for name in _EXPECTED_TOOLS:
        h = get_handler(name)
        assert h is not None, f"{name} missing handler"
        defn = next(t for t in get_tool_definitions() if t.name == name)
        assert defn.description, f"{name} missing description"
        assert defn.inputSchema["type"] == "object"
        assert "properties" in defn.inputSchema


def test_unknown_tool_raises():
    """main._call_tool 遇未知 tool 抛 ValueError(MCP SDK 把 ValueError 转协议错误)。"""
    import asyncio

    from app.main import _call_tool
    with pytest.raises(ValueError):
        asyncio.run(_call_tool("nonexistent_tool", {}))


def test_register_all_tools_idempotent():
    """跑 _register_all_tools 第二次,不抛(因为 importlib.import_module 走 sys.modules cache)。"""
    _register_all_tools()
    assert len(TOOL_REGISTRY) == 10
