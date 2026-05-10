"""MCP tool: find_merchant — backend GET /api/transactions/merchants 的 wrapper。"""
from __future__ import annotations

import json
from urllib.parse import parse_qs, urlparse

import httpx
import pytest

from app.tools import get_handler, get_tool_definitions


def _setup_tool(mock_backend, response_payload, status: int = 200):
    captured: list[httpx.Request] = []

    def handler(req: httpx.Request) -> httpx.Response:
        captured.append(req)
        return httpx.Response(status, json=response_payload)

    mock_backend(handler)
    import app.tools.find_merchant  # noqa: F401
    return captured


@pytest.fixture
def sample() -> dict:
    return {
        "items": [
            {
                "normalized": "瑞幸咖啡",
                "count": 12,
                "total_amount": "456.00",
                "sample_categories": [11, 12],
            },
            {
                "normalized": "瑞幸咖啡(深圳店)",
                "count": 3,
                "total_amount": "78.00",
                "sample_categories": [11],
            },
        ],
    }


def test_find_merchant_tool_definition_present():
    import app.tools.find_merchant  # noqa: F401
    defs = get_tool_definitions()
    names = [t.name for t in defs]
    assert "find_merchant" in names


async def test_find_merchant_passes_keyword(mock_backend, sample):
    captured = _setup_tool(mock_backend, sample)
    handler = get_handler("find_merchant")
    assert handler is not None

    await handler({"keyword": "瑞幸", "limit": 30})
    assert len(captured) == 1
    req = captured[0]
    assert req.url.path == "/api/transactions/merchants"
    qs = parse_qs(urlparse(str(req.url)).query)
    assert qs["keyword"] == ["瑞幸"]
    assert qs["limit"] == ["30"]


async def test_find_merchant_returns_aggregated_items(mock_backend, sample):
    _setup_tool(mock_backend, sample)
    handler = get_handler("find_merchant")

    result = await handler({"keyword": "瑞幸"})
    payload = json.loads(result[0].text)
    # 顶层 key 应为 merchants(rename from items)
    assert "merchants" in payload
    assert "items" not in payload
    merchants = payload["merchants"]
    assert len(merchants) == 2
    # 每条字段直传(normalized/count/total_amount/sample_categories)
    m0 = merchants[0]
    assert m0["normalized"] == "瑞幸咖啡"
    assert m0["count"] == 12
    assert m0["total_amount"] == "456.00"
    assert m0["sample_categories"] == [11, 12]


async def test_find_merchant_missing_keyword_validation(mock_backend):
    """backend 422 → VALIDATION_ERROR envelope。"""
    _setup_tool(
        mock_backend,
        {"detail": "keyword required"},
        status=422,
    )
    handler = get_handler("find_merchant")
    # 入参不传 keyword(MCP 入参 schema 标 required,但工具不做客户端校验,
    # backend 422 → 我们走 envelope)
    result = await handler({})
    payload = json.loads(result[0].text)
    assert "error" in payload
    assert payload["error"]["code"] == "VALIDATION_ERROR"
