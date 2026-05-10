"""MCP tool: list_pending_dedup_pairs — backend GET /api/dedup/pending 的 wrapper。"""
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
    import app.tools.list_pending_dedup_pairs  # noqa: F401
    return captured


@pytest.fixture
def sample() -> dict:
    # backend PendingPairListOut: {items: [DedupPairOut], total: N}
    return {
        "items": [
            {
                "id": 101,
                "user_id": 1,
                "primary_tx_id": 555,
                "mirror_tx_id": 777,
                "match_kind": "amount_time",
                "confidence": 0.92,
                "status": "pending",
                "reasoning": "amount=23.50 within 60s; merchant prefix matched",
                "created_at": "2026-05-08T20:00:00",
                "decided_at": None,
            },
            {
                "id": 102,
                "user_id": 1,
                "primary_tx_id": 556,
                "mirror_tx_id": 778,
                "match_kind": "amount_only",
                "confidence": 0.71,
                "status": "pending",
                "reasoning": "amount only match, time delta 4h",
                "created_at": "2026-05-08T20:01:00",
                "decided_at": None,
            },
        ],
        "total": 2,
    }


def test_list_pending_dedup_pairs_tool_definition_present():
    import app.tools.list_pending_dedup_pairs  # noqa: F401
    defs = get_tool_definitions()
    names = [t.name for t in defs]
    assert "list_pending_dedup_pairs" in names


async def test_list_pending_dedup_pairs(mock_backend, sample):
    captured = _setup_tool(mock_backend, sample)
    handler = get_handler("list_pending_dedup_pairs")
    assert handler is not None

    result = await handler({"limit": 50, "offset": 10})
    assert len(captured) == 1
    req = captured[0]
    assert req.url.path == "/api/dedup/pending"
    qs = parse_qs(urlparse(str(req.url)).query)
    assert qs["limit"] == ["50"]
    assert qs["offset"] == ["10"]

    payload = json.loads(result[0].text)
    assert "pairs" in payload
    pairs = payload["pairs"]
    assert len(pairs) == 2

    expected_keys = {"id", "primary", "mirror", "match_kind", "confidence", "reasoning"}
    for p in pairs:
        # 严格 6 字段:不含 status/created_at/decided_at/user_id
        assert set(p.keys()) == expected_keys

    # rename + 数据透传
    p0 = pairs[0]
    assert p0["id"] == 101
    assert p0["primary"] == 555
    assert p0["mirror"] == 777
    assert p0["match_kind"] == "amount_time"
    assert p0["confidence"] == 0.92
    assert p0["reasoning"] == "amount=23.50 within 60s; merchant prefix matched"
