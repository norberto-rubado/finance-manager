"""MCP tool: get_account_balances — backend GET /api/accounts 的 wrapper。"""
from __future__ import annotations

import json

import httpx
import pytest

from app.tools import get_handler, get_tool_definitions


def _setup_tool(mock_backend, response_payload):
    captured: list[httpx.Request] = []

    def handler(req: httpx.Request) -> httpx.Response:
        captured.append(req)
        return httpx.Response(200, json=response_payload)

    mock_backend(handler)
    import app.tools.get_account_balances  # noqa: F401
    return captured


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


async def test_get_account_balances_returns_trimmed_fields(mock_backend, sample):
    captured = _setup_tool(mock_backend, sample)
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
