"""MCP tool: bulk_update_category_by_merchant — backend
POST /api/transactions/bulk-update-by-merchant。"""
from __future__ import annotations

import json

import pytest

from app.tools import get_handler, get_tool_definitions


@pytest.fixture
def sample() -> dict:
    """Typical BulkUpdateResult."""
    return {"affected_count": 7, "rule_id": 42}


def test_bulk_update_tool_definition_present():
    import app.tools.bulk_update_category_by_merchant  # noqa: F401
    defs = get_tool_definitions()
    names = [t.name for t in defs]
    assert "bulk_update_category_by_merchant" in names


async def test_bulk_update_with_explicit_match_kind_and_no_rule(setup_tool, sample):
    """All optional fields explicit; verify body shape + result."""
    captured = setup_tool(
        "app.tools.bulk_update_category_by_merchant",
        {"affected_count": 3, "rule_id": None},
    )
    h = get_handler("bulk_update_category_by_merchant")
    assert h is not None

    result = await h({
        "pattern": "瑞幸",
        "category": 11,
        "match_kind": "regex",
        "also_add_rule": False,
    })

    assert len(captured) == 1
    req = captured[0]
    assert req.method == "POST"
    assert req.url.path == "/api/transactions/bulk-update-by-merchant"

    body = json.loads(req.content)
    assert body == {
        "pattern": "瑞幸",
        "category_id": 11,            # MCP "category" → backend "category_id"
        "match_kind": "regex",
        "also_add_rule": False,
    }

    payload = json.loads(result[0].text)
    assert set(payload.keys()) == {"affected_count", "rule_id"}
    assert payload == {"affected_count": 3, "rule_id": None}


async def test_bulk_update_default_also_add_rule_and_match_kind(setup_tool, sample):
    """Only required fields → defaults applied (match_kind=contains, also_add_rule=True)."""
    captured = setup_tool("app.tools.bulk_update_category_by_merchant", sample)
    h = get_handler("bulk_update_category_by_merchant")

    result = await h({"pattern": "瑞幸咖啡", "category": 11})

    req = captured[0]
    body = json.loads(req.content)
    assert body == {
        "pattern": "瑞幸咖啡",
        "category_id": 11,
        "match_kind": "contains",     # default
        "also_add_rule": True,        # default
    }

    payload = json.loads(result[0].text)
    assert payload == {"affected_count": 7, "rule_id": 42}


def test_bulk_update_input_schema_valid_json_schema():
    import app.tools.bulk_update_category_by_merchant  # noqa: F401
    defs = get_tool_definitions()
    tool = next(t for t in defs if t.name == "bulk_update_category_by_merchant")
    schema = tool.inputSchema
    assert schema["type"] == "object"
    assert "properties" in schema
    for name, prop in schema["properties"].items():
        assert "type" in prop, f"property {name} missing 'type'"
    required = set(schema.get("required", []))
    assert required == {"pattern", "category"}
