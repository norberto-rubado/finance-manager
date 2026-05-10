"""MCP tool: update_category — backend GET /api/transactions/{id} (capture before)
+ PATCH /api/transactions/{id} (apply change)。
"""
from __future__ import annotations

import json

import httpx

from app.tools import get_handler, get_tool_definitions


def _tx_payload(tx_id: int, *, category_id: int | None) -> dict:
    """Minimal TransactionOut shape — only fields update_category cares about."""
    return {
        "id": tx_id,
        "account_id": 1,
        "statement_import_id": 3,
        "tx_kind": "expense",
        "tx_time": "2026-05-08T12:30:00",
        "post_time": None,
        "amount": "23.50",
        "currency": "CNY",
        "amount_settled_cny": "23.50",
        "merchant_raw": "瑞幸咖啡",
        "merchant_normalized": "瑞幸咖啡",
        "description_raw": None,
        "category_id": category_id,
        "classification_confidence": None,
        "source": "alipay",
        "is_mirror": False,
        "mirror_of_id": None,
    }


def test_update_category_tool_definition_present():
    import app.tools.update_category  # noqa: F401
    defs = get_tool_definitions()
    names = [t.name for t in defs]
    assert "update_category" in names


async def test_update_category_returns_before_and_after(mock_backend):
    """Two-step GET-then-PATCH — needs custom handler beyond setup_tool's
    static payload (since GET returns before-state and PATCH returns after-state).
    """
    captured: list[httpx.Request] = []

    def handler(req: httpx.Request) -> httpx.Response:
        captured.append(req)
        if req.method == "GET" and req.url.path == "/api/transactions/50":
            return httpx.Response(200, json=_tx_payload(50, category_id=11))
        if req.method == "PATCH" and req.url.path == "/api/transactions/50":
            assert json.loads(req.content) == {"category_id": 22}
            return httpx.Response(200, json=_tx_payload(50, category_id=22))
        return httpx.Response(500, json={"detail": "unexpected"})

    mock_backend(handler)
    import app.tools.update_category  # noqa: F401
    h = get_handler("update_category")
    result = await h({"transaction_id": 50, "category": 22})

    # Must hit GET then PATCH in order
    assert len(captured) == 2
    assert captured[0].method == "GET"
    assert captured[1].method == "PATCH"

    payload = json.loads(result[0].text)
    assert set(payload.keys()) == {"ok", "before_category", "after_category"}
    assert payload == {"ok": True, "before_category": 11, "after_category": 22}


async def test_update_category_tx_not_found(setup_tool):
    """backend 404 (on initial GET) → NOT_FOUND envelope。"""
    setup_tool(
        "app.tools.update_category",
        {"detail": "transaction 999 not found"},
        status=404,
    )
    h = get_handler("update_category")
    result = await h({"transaction_id": 999, "category": 22})
    payload = json.loads(result[0].text)
    assert "error" in payload
    assert payload["error"]["code"] == "NOT_FOUND"


def test_update_category_input_schema_valid_json_schema():
    import app.tools.update_category  # noqa: F401
    defs = get_tool_definitions()
    tool = next(t for t in defs if t.name == "update_category")
    schema = tool.inputSchema
    assert schema["type"] == "object"
    assert "properties" in schema
    for name, prop in schema["properties"].items():
        assert "type" in prop, f"property {name} missing 'type'"
    required = set(schema.get("required", []))
    assert required == {"transaction_id", "category"}
