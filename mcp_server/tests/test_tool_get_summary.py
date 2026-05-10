"""MCP tool: get_summary — backend GET /api/summary 的 wrapper。"""
from __future__ import annotations

import json
from urllib.parse import parse_qs, urlparse

import pytest

from app.tools import get_handler, get_tool_definitions


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


async def test_get_summary_default(setup_tool, sample):
    """空入参 → 不传 period/group_by(让 backend 用 default);出参 group_key→group。"""
    captured = setup_tool("app.tools.get_summary", sample)
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
    # breakdown rename: group_key → group(严格 4 字段)
    assert len(payload["breakdown"]) == 2
    expected_breakdown_keys = {"group", "group_id", "amount", "count"}
    for row in payload["breakdown"]:
        assert set(row.keys()) == expected_breakdown_keys
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


async def test_get_summary_passes_period_and_group_by(setup_tool, sample):
    captured = setup_tool("app.tools.get_summary", sample)
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


async def test_get_summary_handles_404_via_error_envelope(setup_tool):
    setup_tool("app.tools.get_summary", {"detail": "not found"}, status=404)
    h = get_handler("get_summary")

    result = await h({})
    payload = json.loads(result[0].text)
    assert "error" in payload
    assert payload["error"]["code"] == "NOT_FOUND"


def test_get_summary_input_schema_valid_json_schema():
    import app.tools.get_summary  # noqa: F401
    defs = get_tool_definitions()
    tool = next(t for t in defs if t.name == "get_summary")
    schema = tool.inputSchema
    assert schema["type"] == "object"
    assert "properties" in schema
    for name, prop in schema["properties"].items():
        assert "type" in prop, f"property {name} missing 'type'"
