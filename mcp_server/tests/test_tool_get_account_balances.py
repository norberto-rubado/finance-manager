"""MCP tool: get_account_balances — backend GET /api/accounts 的 wrapper。"""
from __future__ import annotations

import json

import pytest

from app.tools import get_handler, get_tool_definitions


@pytest.fixture
def sample() -> dict:
    return {
        "items": [
            {
                "id": 1,
                "name": "支付宝余额",
                "type": "alipay",
                "institution": "Alipay",
                "last4": None,
                "currency": "CNY",
                "archived": False,
                "latest_balance": "1234.56",
                "latest_balance_at": "2026-05-08T20:00:00",
            },
            {
                "id": 2,
                "name": "交行借记卡",
                "type": "bank_debit",
                "institution": "BoCom",
                "last4": "1234",
                "currency": "CNY",
                "archived": False,
                "latest_balance": "0",
                "latest_balance_at": None,
            },
        ],
    }


def test_get_account_balances_tool_definition_present():
    import app.tools.get_account_balances  # noqa: F401
    defs = get_tool_definitions()
    names = [t.name for t in defs]
    assert "get_account_balances" in names


async def test_get_account_balances_returns_trimmed_fields(setup_tool, sample):
    captured = setup_tool("app.tools.get_account_balances", sample)
    handler = get_handler("get_account_balances")
    assert handler is not None

    result = await handler({})
    assert len(result) == 1
    payload = json.loads(result[0].text)
    # 顶层 key 应为 accounts(不是 backend 的 items)
    assert "accounts" in payload
    assert "items" not in payload
    accounts = payload["accounts"]
    assert len(accounts) == 2

    expected_keys = {"id", "name", "type", "last4", "latest_balance", "latest_balance_at"}
    for acc in accounts:
        # 严格 6 字段:不含 institution/currency/archived
        assert set(acc.keys()) == expected_keys

    # 数据透传 sanity check
    assert accounts[0]["id"] == 1
    assert accounts[0]["name"] == "支付宝余额"
    assert accounts[0]["type"] == "alipay"
    assert accounts[0]["last4"] is None
    assert accounts[0]["latest_balance"] == "1234.56"
    assert accounts[0]["latest_balance_at"] == "2026-05-08T20:00:00"

    assert accounts[1]["last4"] == "1234"
    assert accounts[1]["latest_balance"] == "0"
    assert accounts[1]["latest_balance_at"] is None

    # 路径校验
    assert len(captured) == 1
    assert captured[0].url.path == "/api/accounts"


async def test_get_account_balances_handles_404_via_error_envelope(setup_tool):
    setup_tool("app.tools.get_account_balances", {"detail": "not found"}, status=404)
    h = get_handler("get_account_balances")

    result = await h({})
    payload = json.loads(result[0].text)
    assert "error" in payload
    assert payload["error"]["code"] == "NOT_FOUND"


def test_get_account_balances_input_schema_valid_json_schema():
    import app.tools.get_account_balances  # noqa: F401
    defs = get_tool_definitions()
    tool = next(t for t in defs if t.name == "get_account_balances")
    schema = tool.inputSchema
    assert schema["type"] == "object"
    assert "properties" in schema
    # properties 是空 dict(get_account_balances 无入参) — 循环就是 no-op
    for name, prop in schema["properties"].items():
        assert "type" in prop, f"property {name} missing 'type'"
    # 同时校验 required key 存在(应为空 list)
    assert "required" in schema
