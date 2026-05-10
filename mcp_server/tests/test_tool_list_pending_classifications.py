"""MCP tool: list_pending_classifications — backend GET /api/transactions/pending-classifications。"""
from __future__ import annotations

import json
from urllib.parse import parse_qs, urlparse

import httpx
import pytest

from app.tools import get_handler, get_tool_definitions


def _setup_tool(mock_backend, response_payload):
    captured: list[httpx.Request] = []

    def handler(req: httpx.Request) -> httpx.Response:
        captured.append(req)
        return httpx.Response(200, json=response_payload)

    mock_backend(handler)
    import app.tools.list_pending_classifications  # noqa: F401
    return captured


@pytest.fixture
def sample() -> dict:
    return {
        "items": [
            {
                "id": 11, "account_id": 5, "statement_import_id": 3,
                "tx_kind": "expense", "tx_time": "2026-05-08T12:30:00",
                "post_time": None, "amount": "23.50", "currency": "CNY",
                "amount_settled_cny": "23.50",
                "merchant_raw": "瑞幸咖啡", "merchant_normalized": "瑞幸咖啡",
                "description_raw": None,
                "category_id": None, "classification_confidence": None,
                "source": "alipay",
                "is_mirror": False, "mirror_of_id": None,
            },
            {
                "id": 12, "account_id": 6, "statement_import_id": 3,
                "tx_kind": "expense", "tx_time": "2026-05-08T15:00:00",
                "post_time": None, "amount": "78.00", "currency": "CNY",
                "amount_settled_cny": "78.00",
                "merchant_raw": "未知商户", "merchant_normalized": None,
                "description_raw": None,
                "category_id": None, "classification_confidence": None,
                "source": "wechat",
                "is_mirror": False, "mirror_of_id": None,
            },
        ],
        "total": 2, "limit": 20, "offset": 0,
    }


def test_list_pending_classifications_tool_definition_present():
    import app.tools.list_pending_classifications  # noqa: F401
    defs = get_tool_definitions()
    names = [t.name for t in defs]
    assert "list_pending_classifications" in names


async def test_list_pending_classifications(mock_backend, sample):
    captured = _setup_tool(mock_backend, sample)
    handler = get_handler("list_pending_classifications")
    assert handler is not None

    result = await handler({"limit": 50, "offset": 5})
    assert len(captured) == 1
    req = captured[0]
    assert req.url.path == "/api/transactions/pending-classifications"
    qs = parse_qs(urlparse(str(req.url)).query)
    assert qs["limit"] == ["50"]
    assert qs["offset"] == ["5"]

    payload = json.loads(result[0].text)
    assert "transactions" in payload
    txs = payload["transactions"]
    assert len(txs) == 2

    expected_keys = {"id", "time", "amount", "merchant", "suggested_categories"}
    for tx in txs:
        # 严格 5 字段
        assert set(tx.keys()) == expected_keys
        # suggested_categories 当前永远是 [](V2 才接 rapidfuzz)
        assert tx["suggested_categories"] == []

    # rename + 数据透传
    tx0 = txs[0]
    assert tx0["id"] == 11
    assert tx0["time"] == "2026-05-08T12:30:00"
    assert tx0["amount"] == "23.50"
    assert tx0["merchant"] == "瑞幸咖啡"

    # 第 2 条 merchant_normalized=None,fallback 到 merchant_raw
    tx1 = txs[1]
    assert tx1["merchant"] == "未知商户"
