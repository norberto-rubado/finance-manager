"""MCP tool: list_transactions — backend GET /api/transactions 的 wrapper。"""
from __future__ import annotations

import json
from urllib.parse import parse_qs, urlparse

import httpx
import pytest

from app.tools import get_handler, get_tool_definitions


def _setup_tool(mock_backend, response_payload):
    """共享 setup:注册 tool + 注入 mock backend。返回 captured_request: list[httpx.Request]。"""
    captured: list[httpx.Request] = []

    def handler(req: httpx.Request) -> httpx.Response:
        captured.append(req)
        return httpx.Response(200, json=response_payload)

    mock_backend(handler)
    # import 触发 register
    import app.tools.list_transactions  # noqa: F401
    return captured


@pytest.fixture
def sample_backend_response() -> dict:
    return {
        "items": [
            {
                "id": 1, "account_id": 5, "statement_import_id": 3,
                "tx_kind": "expense", "tx_time": "2026-05-08T12:30:00",
                "post_time": None, "amount": "23.50", "currency": "CNY",
                "amount_settled_cny": "23.50",
                "merchant_raw": "瑞幸咖啡", "merchant_normalized": "瑞幸咖啡",
                "description_raw": None,
                "category_id": 11, "classification_confidence": 1.0,
                "source": "alipay",
                "is_mirror": False, "mirror_of_id": None,
            },
            {
                "id": 2, "account_id": 6, "statement_import_id": 3,
                "tx_kind": "income", "tx_time": "2026-05-08T09:00:00",
                "post_time": None, "amount": "5000.00", "currency": "CNY",
                "amount_settled_cny": "5000.00",
                "merchant_raw": "工资", "merchant_normalized": "工资",
                "description_raw": None,
                "category_id": None, "classification_confidence": None,
                "source": "manual",
                "is_mirror": False, "mirror_of_id": None,
            },
        ],
        "total": 2, "limit": 50, "offset": 0,
    }


def test_list_transactions_tool_definition_present():
    import app.tools.list_transactions  # noqa: F401
    defs = get_tool_definitions()
    names = [t.name for t in defs]
    assert "list_transactions" in names


async def test_list_transactions_minimal_call(mock_backend, sample_backend_response):
    captured = _setup_tool(mock_backend, sample_backend_response)
    handler = get_handler("list_transactions")
    assert handler is not None

    result = await handler({})
    assert len(result) == 1
    payload = json.loads(result[0].text)
    # spec § 8.1 出参精简到 5 字段
    assert "transactions" in payload
    items = payload["transactions"]
    assert len(items) == 2
    for item in items:
        assert set(item.keys()) >= {"id", "time", "amount", "merchant", "category"}
    assert items[0]["id"] == 1
    assert items[0]["time"] == "2026-05-08T12:30:00"
    assert items[0]["amount"] == "23.50"
    assert items[0]["merchant"] == "瑞幸咖啡"
    assert items[0]["category"] == 11
    assert items[1]["category"] is None  # 未分类
    # captured 用于 sanity check 没被未使用警告吃掉
    assert len(captured) == 1


async def test_list_transactions_passes_filters_to_backend(
    mock_backend, sample_backend_response,
):
    captured = _setup_tool(mock_backend, sample_backend_response)
    handler = get_handler("list_transactions")

    await handler({
        "date_from": "2026-05-01T00:00:00",
        "date_to": "2026-05-31T23:59:59",
        "account_id": 5,
        "category_id": 11,
        "kind": "expense",
        "limit": 100,
        "offset": 50,
    })
    assert len(captured) == 1
    req = captured[0]
    assert req.url.path == "/api/transactions"
    qs = parse_qs(urlparse(str(req.url)).query)
    assert qs["date_from"] == ["2026-05-01T00:00:00"]
    assert qs["date_to"] == ["2026-05-31T23:59:59"]
    assert qs["account_id"] == ["5"]
    assert qs["category_id"] == ["11"]
    assert qs["kind"] == ["expense"]
    assert qs["limit"] == ["100"]
    assert qs["offset"] == ["50"]


async def test_list_transactions_omits_none_filters(mock_backend, sample_backend_response):
    """MCP 入参 None / 缺省 → 不传 backend(让 backend 用其 default)。"""
    captured = _setup_tool(mock_backend, sample_backend_response)
    handler = get_handler("list_transactions")
    await handler({"limit": 10})
    qs = parse_qs(urlparse(str(captured[0].url)).query)
    assert "date_from" not in qs
    assert "category_id" not in qs
    assert qs["limit"] == ["10"]


async def test_list_transactions_handles_404_via_error_envelope(mock_backend):
    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={"detail": "not found"})

    mock_backend(handler)
    import app.tools.list_transactions  # noqa: F401
    h = get_handler("list_transactions")

    result = await h({})
    payload = json.loads(result[0].text)
    assert "error" in payload
    assert payload["error"]["code"] == "NOT_FOUND"


async def test_list_transactions_input_schema_valid_json_schema():
    """inputSchema 必须是合法 JSON Schema(SDK 会用,但不验证;手动 sanity check)。"""
    import app.tools.list_transactions  # noqa: F401
    defs = get_tool_definitions()
    tool = next(t for t in defs if t.name == "list_transactions")
    schema = tool.inputSchema
    assert schema["type"] == "object"
    assert "properties" in schema
    # 每个 property 至少有 type
    for name, prop in schema["properties"].items():
        assert "type" in prop, f"property {name} missing 'type'"
