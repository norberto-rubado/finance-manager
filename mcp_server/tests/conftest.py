"""MCP server tests 共享 fixture — MockTransport backend client。"""
from __future__ import annotations

from collections.abc import Callable

import httpx
import pytest

from app.backend_client import (
    BackendClient,
    reset_backend_client_for_tests,
    set_backend_client_for_tests,
)
from app.config import reset_settings_for_tests


@pytest.fixture(autouse=True)
def reset_singletons():
    """每个 test 前后清掉单例 — 避免 client / settings 跨测试污染。"""
    reset_backend_client_for_tests()
    reset_settings_for_tests()
    yield
    reset_backend_client_for_tests()
    reset_settings_for_tests()


@pytest.fixture
def mock_backend(
    monkeypatch,
) -> Callable[[Callable[[httpx.Request], httpx.Response]], BackendClient]:
    """返回工厂函数:传 handler 进来 → 注入 BackendClient(走 MockTransport)。

    用法:
        async def handler(req: httpx.Request) -> httpx.Response:
            assert req.url.path == "/api/transactions"
            return httpx.Response(200, json={...})

        client = mock_backend(handler)
        # 工具 handler 直接 await get_backend_client().get(...) → 命中 mock
    """
    monkeypatch.setenv("MCP_API_TOKEN", "test-token-do-not-use")
    monkeypatch.setenv("MCP_BACKEND_URL", "http://test-backend:8000")

    def _factory(handler: Callable[[httpx.Request], httpx.Response]) -> BackendClient:
        transport = httpx.MockTransport(handler)
        client = BackendClient(
            base_url="http://test-backend:8000",
            api_token="test-token-do-not-use",
            transport=transport,
        )
        set_backend_client_for_tests(client)
        return client

    return _factory


@pytest.fixture
def setup_tool(mock_backend):
    """Generic factory for tool tests:

        captured = setup_tool("app.tools.list_transactions", payload, status=200)
        result = await get_handler("list_transactions")({...})

    Returns the captured request list. Pass status= to test error paths.
    """
    import importlib

    def _setup(module_path: str, response_payload: dict, *, status: int = 200):
        captured: list[httpx.Request] = []

        def handler(req: httpx.Request) -> httpx.Response:
            captured.append(req)
            return httpx.Response(status, json=response_payload)

        mock_backend(handler)
        importlib.import_module(module_path)
        return captured

    return _setup
