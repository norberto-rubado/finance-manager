"""MCP tool: confirm_dedup_pair — backend POST /api/dedup/{pair_id}/confirm。"""
from __future__ import annotations

import json

import pytest

from app.tools import get_handler, get_tool_definitions


@pytest.fixture
def sample_pair() -> dict:
    """Typical DedupPairOut after confirm."""
    return {
        "id": 7,
        "primary_tx_id": 100,
        "mirror_tx_id": 200,
        "match_kind": "bridge",
        "confidence": 0.85,
        "status": "confirmed",
        "reasoning": None,
    }


def test_confirm_dedup_pair_tool_definition_present():
    import app.tools.confirm_dedup_pair  # noqa: F401
    defs = get_tool_definitions()
    names = [t.name for t in defs]
    assert "confirm_dedup_pair" in names


async def test_confirm_action(setup_tool, sample_pair):
    """action=confirm → POST /api/dedup/{pair_id}/confirm body {action: confirm}."""
    captured = setup_tool("app.tools.confirm_dedup_pair", sample_pair)
    h = get_handler("confirm_dedup_pair")
    assert h is not None

    result = await h({"pair_id": 7, "action": "confirm"})

    assert len(captured) == 1
    req = captured[0]
    assert req.method == "POST"
    assert req.url.path == "/api/dedup/7/confirm"

    body = json.loads(req.content)
    assert body == {"action": "confirm"}

    payload = json.loads(result[0].text)
    assert set(payload.keys()) == {
        "ok", "primary_tx_id", "mirror_tx_id", "action_taken",
    }
    assert payload == {
        "ok": True,
        "primary_tx_id": 100,
        "mirror_tx_id": 200,
        "action_taken": "confirmed",
    }


async def test_reject_action(setup_tool):
    """action=reject still hits /confirm endpoint with body {action: reject};
    backend returns status=rejected → action_taken='rejected'."""
    rejected_payload = {
        "id": 7,
        "primary_tx_id": 100,
        "mirror_tx_id": 200,
        "match_kind": "bridge",
        "confidence": 0.85,
        "status": "rejected",
        "reasoning": None,
    }
    captured = setup_tool("app.tools.confirm_dedup_pair", rejected_payload)
    h = get_handler("confirm_dedup_pair")

    result = await h({"pair_id": 7, "action": "reject"})

    req = captured[0]
    assert req.url.path == "/api/dedup/7/confirm"
    body = json.loads(req.content)
    assert body == {"action": "reject"}

    payload = json.loads(result[0].text)
    assert payload["action_taken"] == "rejected"
    assert payload["ok"] is True


async def test_pair_not_found(setup_tool):
    """backend 404 → NOT_FOUND envelope。"""
    setup_tool(
        "app.tools.confirm_dedup_pair",
        {"detail": "dedup pair 9999 not found"},
        status=404,
    )
    h = get_handler("confirm_dedup_pair")
    result = await h({"pair_id": 9999, "action": "confirm"})
    payload = json.loads(result[0].text)
    assert "error" in payload
    assert payload["error"]["code"] == "NOT_FOUND"


async def test_already_decided_conflict(setup_tool):
    """backend 409 (pair already in confirmed/rejected state) → CONFLICT envelope。"""
    setup_tool(
        "app.tools.confirm_dedup_pair",
        {"detail": "pair already decided"},
        status=409,
    )
    h = get_handler("confirm_dedup_pair")
    result = await h({"pair_id": 7, "action": "confirm"})
    payload = json.loads(result[0].text)
    assert "error" in payload
    assert payload["error"]["code"] == "CONFLICT"


def test_confirm_dedup_pair_input_schema_valid_json_schema():
    import app.tools.confirm_dedup_pair  # noqa: F401
    defs = get_tool_definitions()
    tool = next(t for t in defs if t.name == "confirm_dedup_pair")
    schema = tool.inputSchema
    assert schema["type"] == "object"
    assert "properties" in schema
    for name, prop in schema["properties"].items():
        assert "type" in prop, f"property {name} missing 'type'"
    required = set(schema.get("required", []))
    assert required == {"pair_id", "action"}
    # action enum strict
    assert set(schema["properties"]["action"]["enum"]) == {"confirm", "reject"}
