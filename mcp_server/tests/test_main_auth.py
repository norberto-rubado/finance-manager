"""MCP server bearer self-check 流程测试。"""
from __future__ import annotations

import httpx
import pytest

from app.main import _verify_token_self_check


async def test_verify_token_success(monkeypatch):
    monkeypatch.setenv("MCP_API_TOKEN", "good-token")
    monkeypatch.setenv("MCP_BACKEND_URL", "http://test-backend:8000")

    handler_calls = []

    async def fake_post(self, url, **kwargs):
        handler_calls.append((url, kwargs.get("headers")))
        return httpx.Response(
            200,
            json={"user_id": 1, "username": "admin", "scopes": "read,write"},
        )

    monkeypatch.setattr("httpx.AsyncClient.post", fake_post)

    await _verify_token_self_check()  # 不 raise

    assert handler_calls
    url, headers = handler_calls[0]
    assert url == "/api/admin/tokens/verify"
    assert headers["Authorization"] == "Bearer good-token"


async def test_verify_token_invalid_exits_with_code_2(monkeypatch):
    monkeypatch.setenv("MCP_API_TOKEN", "bad-token")
    monkeypatch.setenv("MCP_BACKEND_URL", "http://test-backend:8000")

    async def fake_post(self, url, **kwargs):
        return httpx.Response(401, json={"detail": "invalid token"})

    monkeypatch.setattr("httpx.AsyncClient.post", fake_post)

    with pytest.raises(SystemExit) as exc_info:
        await _verify_token_self_check()
    assert exc_info.value.code == 2


async def test_verify_token_backend_5xx_exits_with_code_3(monkeypatch):
    monkeypatch.setenv("MCP_API_TOKEN", "good-token")
    monkeypatch.setenv("MCP_BACKEND_URL", "http://test-backend:8000")

    async def fake_post(self, url, **kwargs):
        return httpx.Response(503, text="db down")

    monkeypatch.setattr("httpx.AsyncClient.post", fake_post)

    with pytest.raises(SystemExit) as exc_info:
        await _verify_token_self_check()
    assert exc_info.value.code == 3
