"""BackendClient httpx wrapper:auth header 注入 + 错误映射(spec § 8.3)。"""
from __future__ import annotations

import httpx
import pytest

from app.errors import (
    AUTH_FAILED,
    BACKEND_ERROR,
    CONFLICT,
    NOT_FOUND,
    VALIDATION_ERROR,
    MCPToolError,
)


def _client_with_handler(handler):
    from app.backend_client import BackendClient

    return BackendClient(
        base_url="http://test-backend:8000",
        api_token="t-test",
        transport=httpx.MockTransport(handler),
    )


async def test_get_injects_auth_header_and_returns_json():
    seen_headers = {}

    def handler(req: httpx.Request) -> httpx.Response:
        seen_headers.update(req.headers)
        return httpx.Response(200, json={"ok": True})

    client = _client_with_handler(handler)
    data = await client.get("/api/health")
    assert data == {"ok": True}
    assert seen_headers["authorization"] == "Bearer t-test"


async def test_post_returns_empty_dict_on_204():
    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(204)

    client = _client_with_handler(handler)
    data = await client.post("/api/x", json={"y": 1})
    assert data == {}


@pytest.mark.parametrize(
    "status,expected_code",
    [
        (401, AUTH_FAILED),
        (404, NOT_FOUND),
        (409, CONFLICT),
        (400, VALIDATION_ERROR),
        (422, VALIDATION_ERROR),
        (500, BACKEND_ERROR),
        (503, BACKEND_ERROR),
    ],
)
async def test_status_to_mcp_error(status, expected_code):
    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(status, json={"detail": f"backend says {status}"})

    client = _client_with_handler(handler)
    with pytest.raises(MCPToolError) as exc_info:
        await client.get("/api/anything")
    assert exc_info.value.code == expected_code
    assert "backend says" in exc_info.value.message


async def test_backend_error_includes_status_in_data():
    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(503, text="db down")

    client = _client_with_handler(handler)
    with pytest.raises(MCPToolError) as exc_info:
        await client.get("/api/health")
    assert exc_info.value.code == BACKEND_ERROR
    assert exc_info.value.data == {"status": 503}
