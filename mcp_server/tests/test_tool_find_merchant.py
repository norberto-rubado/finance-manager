"""MCP tool: find_merchant — backend GET /api/transactions/merchants 的 wrapper。"""
from __future__ import annotations

import json
from urllib.parse import parse_qs, urlparse

import pytest

from app.tools import get_handler, get_tool_definitions


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


async def test_find_merchant_passes_keyword(setup_tool, sample):
    captured = setup_tool("app.tools.find_merchant", sample)
    handler = get_handler("find_merchant")
    assert handler is not None

    await handler({"keyword": "瑞幸", "limit": 30})
    assert len(captured) == 1
    req = captured[0]
    assert req.url.path == "/api/transactions/merchants"
    qs = parse_qs(urlparse(str(req.url)).query)
    assert qs["keyword"] == ["瑞幸"]
    assert qs["limit"] == ["30"]


async def test_find_merchant_returns_aggregated_items(setup_tool, sample):
    setup_tool("app.tools.find_merchant", sample)
    handler = get_handler("find_merchant")

    result = await handler({"keyword": "瑞幸"})
    payload = json.loads(result[0].text)
    # 顶层 key 应为 merchants(rename from items)
    assert "merchants" in payload
    assert "items" not in payload
    merchants = payload["merchants"]
    assert len(merchants) == 2
    # 每条字段直传(normalized/count/total_amount/sample_categories) — 严格 4 字段
    expected_keys = {"normalized", "count", "total_amount", "sample_categories"}
    for m in merchants:
        assert set(m.keys()) == expected_keys
    m0 = merchants[0]
    assert m0["normalized"] == "瑞幸咖啡"
    assert m0["count"] == 12
    assert m0["total_amount"] == "456.00"
    assert m0["sample_categories"] == [11, 12]


async def test_find_merchant_missing_keyword_validation(setup_tool):
    """backend 422 → VALIDATION_ERROR envelope。"""
    setup_tool(
        "app.tools.find_merchant",
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


def test_find_merchant_input_schema_valid_json_schema():
    import app.tools.find_merchant  # noqa: F401
    defs = get_tool_definitions()
    tool = next(t for t in defs if t.name == "find_merchant")
    schema = tool.inputSchema
    assert schema["type"] == "object"
    assert "properties" in schema
    for name, prop in schema["properties"].items():
        assert "type" in prop, f"property {name} missing 'type'"
    # find_merchant 必传 keyword
    assert "keyword" in schema.get("required", [])
