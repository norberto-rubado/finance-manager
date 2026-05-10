"""MCP tool: add_transaction — backend POST /api/transactions/manual。"""
from __future__ import annotations

import json

import pytest

from app.tools import get_handler, get_tool_definitions


@pytest.fixture
def sample() -> dict:
    """Typical TransactionOut from POST /api/transactions/manual."""
    return {
        "id": 999,
        "account_id": 1,
        "statement_import_id": None,
        "tx_kind": "expense",
        "tx_time": "2026-05-10T08:30:00",
        "post_time": None,
        "amount": "23.50",
        "currency": "CNY",
        "amount_settled_cny": "23.50",
        "merchant_raw": "瑞幸咖啡",
        "merchant_normalized": "瑞幸咖啡",
        "description_raw": None,
        "category_id": 11,
        "classification_confidence": 1.0,
        "source": "manual",
        "is_mirror": False,
        "mirror_of_id": None,
    }


def test_add_transaction_tool_definition_present():
    import app.tools.add_transaction  # noqa: F401
    defs = get_tool_definitions()
    names = [t.name for t in defs]
    assert "add_transaction" in names


async def test_add_transaction_minimal(setup_tool, sample):
    """Happy path: only required fields → backend body has correct renames + defaults."""
    captured = setup_tool("app.tools.add_transaction", sample)
    h = get_handler("add_transaction")
    assert h is not None

    result = await h({
        "time": "2026-05-10T08:30:00",
        "amount": "23.50",
        "merchant": "瑞幸咖啡",
        "account": 1,
    })

    # Single backend POST /api/transactions/manual
    assert len(captured) == 1
    req = captured[0]
    assert req.method == "POST"
    assert req.url.path == "/api/transactions/manual"

    body = json.loads(req.content)
    # Field renames: time→tx_time, account→account_id, kind→tx_kind (default expense)
    assert body == {
        "tx_time": "2026-05-10T08:30:00",
        "amount": "23.50",
        "currency": "CNY",          # default
        "merchant": "瑞幸咖啡",
        "account_id": 1,
        "tx_kind": "expense",       # default
    }
    # No optional keys leak through
    assert "category_id" not in body
    assert "description" not in body

    payload = json.loads(result[0].text)
    assert set(payload.keys()) == {"transaction_id", "applied_rule", "classified_category"}
    assert payload["transaction_id"] == 999
    assert payload["applied_rule"] is None  # V2 placeholder
    assert payload["classified_category"] == 11


async def test_add_transaction_with_explicit_category_and_kind(setup_tool, sample):
    """All optional fields pass through with correct renames."""
    captured = setup_tool("app.tools.add_transaction", sample)
    h = get_handler("add_transaction")

    await h({
        "time": "2026-05-10T08:30:00",
        "amount": "100.00",
        "currency": "USD",
        "merchant": "Starbucks",
        "category": 11,
        "account": 5,
        "kind": "income",
        "description": "refund or whatever",
    })

    req = captured[0]
    body = json.loads(req.content)
    assert body == {
        "tx_time": "2026-05-10T08:30:00",
        "amount": "100.00",
        "currency": "USD",
        "merchant": "Starbucks",
        "account_id": 5,
        "tx_kind": "income",
        "category_id": 11,
        "description": "refund or whatever",
    }


async def test_add_transaction_account_not_found(setup_tool):
    """backend 404 → NOT_FOUND envelope。"""
    setup_tool(
        "app.tools.add_transaction",
        {"detail": "account 9999 not found"},
        status=404,
    )
    h = get_handler("add_transaction")

    result = await h({
        "time": "2026-05-10T08:30:00",
        "amount": "23.50",
        "merchant": "X",
        "account": 9999,
    })
    payload = json.loads(result[0].text)
    assert "error" in payload
    assert payload["error"]["code"] == "NOT_FOUND"


def test_add_transaction_input_schema_valid_json_schema():
    import app.tools.add_transaction  # noqa: F401
    defs = get_tool_definitions()
    tool = next(t for t in defs if t.name == "add_transaction")
    schema = tool.inputSchema
    assert schema["type"] == "object"
    assert "properties" in schema
    for name, prop in schema["properties"].items():
        assert "type" in prop, f"property {name} missing 'type'"
    # required keys per spec
    required = set(schema.get("required", []))
    assert required == {"time", "amount", "merchant", "account"}
