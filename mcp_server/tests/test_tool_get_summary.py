"""MCP tool: get_summary — backend GET /api/summary 的 wrapper。"""
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
    import app.tools.get_summary  # noqa: F401
    return captured


@pytest.fixture
def sample() -> dict:
    return {
        "period": "month",
        "date_from": "2026-05-01T00:00:00",
        "date_to": "2026-06-01T00:00:00",
        "group_by": "category",
        "total_expense": "1234.56",
        "total_income": "5000.00",
        "breakdown": [
            {"group_key": "餐饮/咖啡", "group_id": 11, "amount": "456.00", "count": 12},
            {"group_key": "购物/淘宝", "group_id": 12, "amount": "778.56", "count": 5},
        ],
    }


def test_get_summary_tool_definition_present():
    import app.tools.get_summary  # noqa: F401
    defs = get_tool_definitions()
    names = [t.name for t in defs]
    assert "get_summary" in names


async def test_get_summary_default(mock_backend, sample):
    """空入参 → 不传 period/group_by(让 backend 用 default);出参 group_key→group。"""
    captured = _setup_tool(mock_backend, sample)
    handler = get_handler("get_summary")
    assert handler is not None

    result = await handler({})
    assert len(result) == 1
    payload = json.loads(result[0].text)
    # 顶层字段直传
    assert payload["period"] == "month"
    assert payload["date_from"] == "2026-05-01T00:00:00"
    assert payload["date_to"] == "2026-06-01T00:00:00"
    assert payload["group_by"] == "category"
    assert payload["total_expense"] == "1234.56"
    assert payload["total_income"] == "5000.00"
    # breakdown rename: group_key → group
    assert len(payload["breakdown"]) == 2
    row0 = payload["breakdown"][0]
    assert row0["group"] == "餐饮/咖啡"
    assert "group_key" not in row0
    assert row0["group_id"] == 11
    assert row0["amount"] == "456.00"
    assert row0["count"] == 12
    # 入参为空 → 不应有 query string
    assert len(captured) == 1
    qs = parse_qs(urlparse(str(captured[0].url)).query)
    assert "period" not in qs
    assert "group_by" not in qs
    assert "date_from" not in qs


async def test_get_summary_passes_period_and_group_by(mock_backend, sample):
    captured = _setup_tool(mock_backend, sample)
    handler = get_handler("get_summary")

    await handler({
        "period": "week",
        "group_by": "merchant",
        "date_from": "2026-05-01T00:00:00",
        "date_to": "2026-05-08T00:00:00",
    })
    assert len(captured) == 1
    req = captured[0]
    assert req.url.path == "/api/summary"
    qs = parse_qs(urlparse(str(req.url)).query)
    assert qs["period"] == ["week"]
    assert qs["group_by"] == ["merchant"]
    assert qs["date_from"] == ["2026-05-01T00:00:00"]
    assert qs["date_to"] == ["2026-05-08T00:00:00"]
